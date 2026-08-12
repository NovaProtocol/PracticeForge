"""Database layer using SQLAlchemy.

Keeps the same query/execute function signatures as the old PyMySQL version
so the rest of the codebase doesn't need to change.
"""

import os
import re

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from shared.sqlalchemy_models import Base

# Engine and session factory are built lazily on first use so that importing
# this module doesn't require MYSQL_* env vars to be set.
_engine = None
_Session = None


def _dsn() -> str:
    return (
        f"mysql+pymysql://{os.environ.get('MYSQL_USER', 'root')}:{os.environ['MYSQL_PASS']}"
        f"@{os.environ['MYSQL_HOST']}:{os.environ.get('MYSQL_PORT', '3306')}"
        f"/{os.environ['MYSQL_DATABASE']}"
    )


def get_engine():
    global _engine, _Session
    if _engine is None:
        engine = create_engine(_dsn(), pool_pre_ping=True, pool_recycle=300)
        _Session = sessionmaker(bind=engine)
        _engine = engine
    return _engine


def _convert(sql: str, params: tuple) -> tuple:
    """Convert PyMySQL %s placeholders to SQLAlchemy :pN named params."""
    if not params:
        return sql, {}
    # Replace each %s with :p0, :p1, etc.
    names = []
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
