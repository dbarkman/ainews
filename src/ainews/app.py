"""FastAPI application.

The site links out. It stores and serves a title, a source, a timestamp and a
link — never article text. The publisher's RSS summary is held in the database
for classification and is deliberately not exposed by any endpoint.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import get_settings
from .db import query

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

app = FastAPI(title="AI News HQ", version=__version__, docs_url="/api/docs")

# Candidate window. Older than this and it is not news.
LOOKBACK_DAYS = 14
TIER_WEIGHT = {1: 1.00, 2: 0.85, 3: 0.60}
HALF_LIFE_HOURS = 36.0
MAX_PER_SOURCE = 2


def _parse_topics(raw: str | None) -> list[str]:
    if not raw:
        return []
    out, seen = [], set()
    for part in raw.split(","):
        slug = part.strip().lower()
        if slug and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out[:10]


def _score(row: dict, weights: dict[str, float]) -> float:
    published = row["published_at"] or row["fetched_at"]
    age_h = max(0.0, (datetime.utcnow() - published).total_seconds() / 3600.0)
    recency = math.pow(0.5, age_h / HALF_LIFE_HOURS)
    topic_w = weights.get(row["topic_slug"], 0.0) if weights else 1.0
    return topic_w * float(row["confidence"]) * TIER_WEIGHT.get(row["quality_tier"], 0.6) * recency


def _feed(topics: list[str], limit: int) -> list[dict]:
    cutoff = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    params: list = [cutoff]
    sql = """
        SELECT a.id, a.url, a.title, a.image_url, a.published_at, a.fetched_at,
               s.slug AS source_slug, s.name AS source_name, s.quality_tier,
               t.slug AS topic_slug, t.name AS topic_name, at.confidence
        FROM articles a
        JOIN sources s        ON s.id = a.source_id AND s.active = 1
        JOIN article_topics at ON at.article_id = a.id
        JOIN topics t          ON t.id = at.topic_id
        WHERE COALESCE(a.published_at, a.fetched_at) >= %s
    """
    if topics:
        sql += " AND t.slug IN (" + ",".join(["%s"] * len(topics)) + ")"
        params.extend(topics)
    sql += " ORDER BY COALESCE(a.published_at, a.fetched_at) DESC LIMIT 2000"

    rows = query(sql, params)

    # Weight earlier survey picks slightly higher than later ones.
    weights = {slug: 1.0 - (i * 0.06) for i, slug in enumerate(topics)} if topics else {}

    best: dict[int, dict] = {}
    for r in rows:
        r["_score"] = _score(r, weights)
        prev = best.get(r["id"])
        if prev is None or r["_score"] > prev["_score"]:
            best[r["id"]] = r

    ranked = sorted(best.values(), key=lambda r: r["_score"], reverse=True)

    # Diversity cap: no single source may dominate the digest.
    out, per_source = [], {}
    for r in ranked:
        n = per_source.get(r["source_slug"], 0)
        if n >= MAX_PER_SOURCE:
            continue
        per_source[r["source_slug"]] = n + 1
        published = r["published_at"] or r["fetched_at"]
        out.append({
            "id": r["id"],
            "title": r["title"],
            "url": r["url"],
            "image_url": r["image_url"],
            "published_at": published.replace(tzinfo=timezone.utc).isoformat(),
            "source": {"slug": r["source_slug"], "name": r["source_name"]},
            "topic": {"slug": r["topic_slug"], "name": r["topic_name"]},
            "why": f"matched your interest in {r['topic_name']}" if topics else "recent across all topics",
        })
        if len(out) >= limit:
            break
    return out


@app.get("/health")
async def health() -> JSONResponse:
    try:
        counts = await asyncio.to_thread(query, """
            SELECT (SELECT COUNT(*) FROM sources WHERE active=1) AS sources,
                   (SELECT COUNT(*) FROM articles) AS articles,
                   (SELECT COUNT(*) FROM articles
                     WHERE fetched_at >= NOW() - INTERVAL 24 HOUR) AS articles_24h,
                   (SELECT MAX(last_fetched_at) FROM sources) AS last_ingest
        """)
        row = counts[0]
    except Exception as exc:  # pragma: no cover - surfaced to the health check
        return JSONResponse(status_code=503,
                            content={"status": "error", "detail": type(exc).__name__})
    last = row["last_ingest"]
    stale = last is None or (datetime.utcnow() - last) > timedelta(hours=6)
    return JSONResponse(
        status_code=200 if not stale else 503,
        content={
            "status": "ok" if not stale else "stale",
            "version": __version__,
            "sources": row["sources"],
            "articles": row["articles"],
            "articles_24h": row["articles_24h"],
            "last_ingest": last.replace(tzinfo=timezone.utc).isoformat() if last else None,
        },
    )


@app.get("/api/topics")
async def api_topics() -> dict:
    rows = await asyncio.to_thread(query, """
        SELECT t.slug, t.name, t.description,
               (SELECT COUNT(*) FROM source_topics st WHERE st.topic_id = t.id) AS dedicated_sources
        FROM topics t ORDER BY t.display_order
    """)
    return {"topics": rows}


@app.get("/api/sources")
async def api_sources(topics: str | None = None) -> dict:
    slugs = _parse_topics(topics)
    sql = """
        SELECT s.slug, s.name, s.homepage_url, s.kind, s.quality_tier, s.blurb,
               GROUP_CONCAT(t.slug ORDER BY t.display_order) AS topic_slugs
        FROM sources s
        LEFT JOIN source_topics st ON st.source_id = s.id
        LEFT JOIN topics t         ON t.id = st.topic_id
        WHERE s.active = 1
    """
    params: list = []
    if slugs:
        sql += " AND s.id IN (SELECT st2.source_id FROM source_topics st2 JOIN topics t2 " \
               "ON t2.id = st2.topic_id WHERE t2.slug IN (" + ",".join(["%s"] * len(slugs)) + "))"
        params.extend(slugs)
    sql += " GROUP BY s.id ORDER BY s.quality_tier, s.name"
    rows = await asyncio.to_thread(query, sql, params)
    for r in rows:
        r["topics"] = (r.pop("topic_slugs") or "").split(",") if r.get("topic_slugs") else []
    return {"sources": rows}


@app.get("/api/feed")
async def api_feed(
    topics: str | None = None,
    limit: int = Query(default=7, ge=1),
) -> dict:
    capped = min(limit, get_settings().max_feed_items)
    slugs = _parse_topics(topics)
    items = await asyncio.to_thread(_feed, slugs, capped)
    return {"count": len(items), "limit": capped, "topics": slugs, "items": items}


@app.get("/")
async def index() -> FileResponse:
    path = STATIC_DIR / "index.html"
    if not path.exists():
        raise HTTPException(status_code=500, detail="static assets missing")
    return FileResponse(path)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
