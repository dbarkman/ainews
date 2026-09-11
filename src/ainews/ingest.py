"""RSS/Atom poller.

Deliberately conservative: conditional GET so we do not re-download unchanged
feeds, a hard per-fetch entry cap so an archive-style feed cannot dump ten
thousand rows on first run, and metadata only. We store the publisher's own RSS
summary because it is what makes keyword classification work, but it is never
rendered — the site links out.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import feedparser
import httpx

from .catalog import SOURCES, TOPICS, classify
from .config import get_settings
from .db import connect

log = logging.getLogger("ainews.ingest")

# Several feeds (arXiv, OpenAI, Hugging Face) serve their whole archive.
MAX_ENTRIES_PER_FETCH = 25

TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid", "ref_src")


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    kept = [
        kv for kv in parts.query.split("&")
        if kv and not kv.split("=")[0].lower().startswith(TRACKING_PREFIXES)
    ]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path,
                       "&".join(kept), ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def entry_published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            try:
                return datetime(*st[:6], tzinfo=timezone.utc).replace(tzinfo=None)
            except (TypeError, ValueError):
                continue
    return None


def entry_image(entry) -> str | None:
    for media in (entry.get("media_content") or []):
        if media.get("url"):
            return media["url"][:1024]
    for thumb in (entry.get("media_thumbnail") or []):
        if thumb.get("url"):
            return thumb["url"][:1024]
    for link in (entry.get("links") or []):
        if str(link.get("type", "")).startswith("image/") and link.get("href"):
            return link["href"][:1024]
    return None


def sync_catalog() -> None:
    """Push the code-defined topics and sources into the database."""
    with connect() as conn, conn.cursor() as cur:
        for i, t in enumerate(TOPICS):
            cur.execute(
                "INSERT INTO topics (slug, name, description, display_order) VALUES (%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE name=VALUES(name), description=VALUES(description), "
                "display_order=VALUES(display_order)",
                (t.slug, t.name, t.description, i),
            )
        for s in SOURCES:
            cur.execute(
                "INSERT INTO sources (slug, name, homepage_url, feed_url, kind, quality_tier, blurb, active) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,1) "
                "ON DUPLICATE KEY UPDATE name=VALUES(name), homepage_url=VALUES(homepage_url), "
                "feed_url=VALUES(feed_url), kind=VALUES(kind), quality_tier=VALUES(quality_tier), "
                "blurb=VALUES(blurb)",
                (s.slug, s.name, s.homepage_url, s.feed_url, s.kind, s.quality_tier, s.blurb),
            )
            cur.execute("SELECT id FROM sources WHERE slug=%s", (s.slug,))
            sid = cur.fetchone()["id"]
            cur.execute("DELETE FROM source_topics WHERE source_id=%s", (sid,))
            for slug in s.topics:
                cur.execute(
                    "INSERT INTO source_topics (source_id, topic_id, weight) "
                    "SELECT %s, id, 1.00 FROM topics WHERE slug=%s",
                    (sid, slug),
                )
        conn.commit()
    log.info("catalog synced: %d topics, %d sources", len(TOPICS), len(SOURCES))


def fetch_source(client: httpx.Client, row: dict) -> tuple[int, str]:
    """Fetch one feed. Returns (new_articles, status)."""
    headers = {"User-Agent": get_settings().user_agent}
    if row.get("etag"):
        headers["If-None-Match"] = row["etag"]
    if row.get("last_modified"):
        headers["If-Modified-Since"] = row["last_modified"]

    try:
        resp = client.get(row["feed_url"], headers=headers, follow_redirects=True)
    except httpx.HTTPError as exc:
        return 0, f"error: {type(exc).__name__}"

    if resp.status_code == 304:
        return 0, "not-modified"
    if resp.status_code != 200:
        return 0, f"http {resp.status_code}"

    parsed = feedparser.parse(resp.content)
    entries = parsed.entries[:MAX_ENTRIES_PER_FETCH]
    if not entries:
        return 0, "0 entries"

    inherited = [t["slug"] for t in row["topics"]]
    new = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with connect() as conn, conn.cursor() as cur:
        for e in entries:
            link = (e.get("link") or "").strip()
            title = (e.get("title") or "").strip()
            if not link or not title:
                continue
            summary = (e.get("summary") or "")[:8000] or None
            cur.execute(
                "INSERT IGNORE INTO articles "
                "(source_id, url, url_hash, title, rss_summary, image_url, published_at, fetched_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (row["id"], normalize_url(link)[:768], url_hash(link), title[:512],
                 summary, entry_image(e), entry_published(e), now),
            )
            if cur.rowcount == 0:
                continue  # already had it
            new += 1
            article_id = cur.lastrowid

            if row["kind"] == "topical":
                pairs = [(slug, 1.00, "inherited") for slug in inherited]
            else:
                pairs = [(slug, conf, "keyword") for slug, conf in classify(title, summary)]

            for slug, conf, method in pairs:
                cur.execute(
                    "INSERT IGNORE INTO article_topics (article_id, topic_id, confidence, method) "
                    "SELECT %s, id, %s, %s FROM topics WHERE slug=%s",
                    (article_id, conf, method, slug),
                )

        cur.execute(
            "UPDATE sources SET etag=%s, last_modified=%s, last_fetched_at=%s, last_status=%s WHERE id=%s",
            (resp.headers.get("ETag"), resp.headers.get("Last-Modified"), now, "ok", row["id"]),
        )
        conn.commit()
    return new, "ok"


def run_once() -> int:
    sync_catalog()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, slug, feed_url, kind, etag, last_modified FROM sources WHERE active=1")
        sources = list(cur.fetchall())
        for s in sources:
            cur.execute(
                "SELECT t.slug FROM source_topics st JOIN topics t ON t.id=st.topic_id WHERE st.source_id=%s",
                (s["id"],),
            )
            s["topics"] = list(cur.fetchall())

    total = 0
    timeout = httpx.Timeout(get_settings().http_timeout)
    with httpx.Client(timeout=timeout) as client:
        for s in sources:
            new, status = fetch_source(client, s)
            total += new
            log.info("%-20s %-14s +%d", s["slug"], status, new)
            if status.startswith(("error", "http")):
                with connect() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE sources SET last_status=%s WHERE id=%s", (status, s["id"]))
                    conn.commit()
    log.info("ingest complete: %d new articles across %d sources", total, len(sources))
    return total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Poll all active feeds once.")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
