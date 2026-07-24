from __future__ import annotations

import os
import pymysql
from pymysql.cursors import DictCursor

_POOL = None


def get_connection():
    global _POOL
    if _POOL is None:
    _POOL = pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        user="root",
        password=os.environ["MYSQL_PASS"],
        database=os.environ["MYSQL_DATABASE"],
        cursorclass=DictCursor,
        autocommit=True,
    )
    return _POOL


def query(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> int:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount
