"""Thin PyMySQL helpers.

Traffic here is low and bursty, so a connection per unit of work in a worker
thread is simpler and easier to reason about than an async driver. All callers
go through asyncio.to_thread from the request path.
"""

from __future__ import annotations

import contextlib
from typing import Any, Iterator, Sequence

import pymysql
from pymysql.cursors import DictCursor

from .config import get_settings


@contextlib.contextmanager
def connect() -> Iterator[pymysql.connections.Connection]:
    s = get_settings()
    conn = pymysql.connect(
        host=s.db_host,
        port=s.db_port,
        user=s.db_user,
        password=s.db_password,
        database=s.db_name,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params: Sequence[Any] | None = None) -> list[dict]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params or ())
        return list(cur.fetchall())


def execute(sql: str, params: Sequence[Any] | None = None) -> int:
    with connect() as conn, conn.cursor() as cur:
        n = cur.execute(sql, params or ())
        conn.commit()
        return n
