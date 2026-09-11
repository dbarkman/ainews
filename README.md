# AI News HQ

A topic-matched AI news aggregator with a deliberate volume cap. A short survey
works out what you want to learn, and the site returns a small ranked digest plus
a list of sources worth following — then gets out of the way.

Live at <https://ainews.redmesastudios.com>.

## What it does and does not do

It stores and serves a **title, source, timestamp and link**. Headlines link
straight to the publisher. No article text is reproduced anywhere in the UI or
the API.

Ingestion reads publisher-provided RSS/Atom feeds only, sends a descriptive
User-Agent, and uses conditional GET so unchanged feeds are not re-downloaded.
The publisher's own RSS summary is stored in `articles.rss_summary` because it is
what makes keyword classification work — it is never returned by any endpoint.

## The two source kinds

This is the design decision the rest of the system rests on.

| Kind | Behaviour | Cost |
|---|---|---|
| `topical` | Covers one beat. Every article inherits the source's topics. | Free — no analysis |
| `broad` | Covers all of AI. Each article is matched to topics individually. | Keyword classification |

Only broad sources pay a classification cost, so adding a specialist feed is
free. Topics with no dedicated source are still served, via broad sources.

## Ranking

`topic weight × classifier confidence × source tier × recency`, with a 36-hour
half-life and a 14-day candidate window. A diversity cap of two articles per
source stops one prolific feed from owning the digest. The per-request item
limit is enforced server side — the cap is a product decision, not a preference.

## Layout

```
src/ainews/
  catalog.py   topics, keyword rules, seed sources   <- edit this to add a source
  ingest.py    RSS poller; run as a systemd timer
  app.py       FastAPI: /health, /api/topics, /api/sources, /api/feed
  db.py        PyMySQL helpers
  config.py    env-driven settings, read lazily
migrations/    schema, idempotent
static/        plain HTML/CSS/JS front end, no build step
deploy/        systemd units, Apache vhost, env template
```

## Adding a source

Append to `SOURCES` in `catalog.py`, then run the ingester once. `sync_catalog()`
upserts topics and sources on every pass, so the code is the source of truth and
no manual SQL is needed.

Verify the feed parses before committing it:

```bash
uv run python -c "import feedparser,httpx;d=feedparser.parse(httpx.get('FEED_URL',follow_redirects=True).content);print(len(d.entries),d.entries[0].title)"
```

## Local development

```bash
uv sync
uv run pytest
uv run python -m ainews          # http://127.0.0.1:8006
```

Needs a MariaDB reachable per the `AINEWS_DB_*` variables; see `deploy/env.example`.

## API

| Endpoint | Purpose |
|---|---|
| `GET /health` | Counts plus ingest freshness; 503 when the last ingest is over 6 hours old |
| `GET /api/topics` | The taxonomy |
| `GET /api/sources?topics=a,b` | Sources for those topics, split by kind |
| `GET /api/feed?topics=a,b&limit=7` | The ranked digest |

Deployment lives in [deploy/DEPLOY.md](deploy/DEPLOY.md).
