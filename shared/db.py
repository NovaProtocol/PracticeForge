"""Database layer — async engine (aiomysql) + sync compat.

Per reference/fastapi/data.md: async engine via create_async_engine + aiomysql
for web layer; sync engine retained for executor and startup. Keeps same
query/execute signatures for backwards compat (models/startup).
"""

from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

_engine = None
_Session = None
_async_engine = None
_AsyncSession = None


def _dsn() -> str:
    from shared.config import get_config

    return get_config().db_url


def _async_dsn() -> str:
    # swap driver for async; sqlite -> aiosqlite for tests
    url = _dsn()
    if url.startswith("sqlite"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url.replace("+pymysql", "+aiomysql", 1)


def get_engine():
    global _engine, _Session
    if _engine is None:
        engine = create_engine(_dsn(), pool_pre_ping=True, pool_recycle=300)
        _Session = sessionmaker(bind=engine)
        _engine = engine
    return _engine


def get_async_engine():
    global _async_engine, _AsyncSession
    if _async_engine is None:
        _async_engine = create_async_engine(_async_dsn(), pool_pre_ping=True, pool_size=5)
        _AsyncSession = async_sessionmaker(_async_engine, class_=AsyncSession, expire_on_commit=False)
    return _async_engine


def get_async_sessionmaker():
    get_async_engine()
    return _AsyncSession


@asynccontextmanager
async def get_db():
    """FastAPI dependency — yields request-scoped AsyncSession."""
    factory = get_async_sessionmaker()
    async with factory() as session:
        yield session


def _convert(sql: str, params: tuple) -> tuple:
    """Convert PyMySQL %s placeholders to SQLAlchemy :pN named params."""
    if not params:
        return sql, {}
    names: list[int] = []

    def repl(m):
        names.append(len(names))
        return f":p{names[-1]}"

    new_sql = re.sub(r"%s", repl, sql)
    new_params = {f"p{i}": params[i] for i in range(len(params))}
    return new_sql, new_params


def query(sql: str, params: tuple = ()) -> list[dict]:
    get_engine()
    sql2, params2 = _convert(sql, params)
    with _Session() as sess:
        result = sess.execute(text(sql2), params2)
        return [dict(r._mapping) for r in result]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> int:
    get_engine()
    sql2, params2 = _convert(sql, params)
    with _Session.begin() as sess:
        result = sess.execute(text(sql2), params2)
        if result.lastrowid is not None:
            return result.lastrowid
        return result.rowcount


async def async_query(sql: str, params: tuple = ()) -> list[dict]:
    factory = get_async_sessionmaker()
    sql2, params2 = _convert(sql, params)
    async with factory() as sess:
        result = await sess.execute(text(sql2), params2)
        return [dict(r._mapping) for r in result]


async def async_query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = await async_query(sql, params)
    return rows[0] if rows else None


async def async_execute(sql: str, params: tuple = ()) -> int:
    factory = get_async_sessionmaker()
    sql2, params2 = _convert(sql, params)
    async with factory.begin() as sess:
        result = await sess.execute(text(sql2), params2)
        await sess.commit()
        if result.lastrowid is not None:
            return result.lastrowid
        return result.rowcount
