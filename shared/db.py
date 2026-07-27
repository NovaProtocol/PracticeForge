from __future__ import annotations

import os
import threading

import pymysql
from pymysql.cursors import DictCursor

_local = threading.local()


def _create_conn():
    return pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ["MYSQL_PASS"],
        database=os.environ["MYSQL_DATABASE"],
        cursorclass=DictCursor,
        autocommit=True,
    )


def get_connection():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = _create_conn()
    else:
        try:
            _local.conn.ping(reconnect=True)
        except Exception:
            _local.conn = _create_conn()
    return _local.conn


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
