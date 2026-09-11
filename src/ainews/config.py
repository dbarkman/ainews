"""Runtime settings.

Environment is read lazily inside get_settings(), never at import time, so that
importing this module in a test or a migration does not require a configured host.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    http_timeout: float
    user_agent: str
    # Hard ceiling on how much any one request can ask for. The volume cap is a
    # product decision, not a preference, so it is enforced server side.
    max_feed_items: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        db_host=os.environ.get("AINEWS_DB_HOST", "127.0.0.1"),
        db_port=int(os.environ.get("AINEWS_DB_PORT", "3306")),
        db_user=os.environ.get("AINEWS_DB_USER", "ainews"),
        db_password=os.environ.get("AINEWS_DB_PASSWORD", ""),
        db_name=os.environ.get("AINEWS_DB_NAME", "ainews"),
        http_timeout=float(os.environ.get("AINEWS_HTTP_TIMEOUT", "20")),
        user_agent=os.environ.get(
            "AINEWS_USER_AGENT",
            "AINewsHQ/0.1 (+https://ainews.redmesastudios.com; feed reader)",
        ),
        max_feed_items=int(os.environ.get("AINEWS_MAX_FEED_ITEMS", "30")),
    )
