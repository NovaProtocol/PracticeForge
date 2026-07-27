"""Database layer using SQLAlchemy.

Keeps the same query/execute function signatures as the old PyMySQL version
so the rest of the codebase doesn't need to change.
"""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from shared.sqlalchemy_models import Base

DSN = (
    f"mysql+pymysql://{os.environ.get('MYSQL_USER', 'root')}:{os.environ['MYSQL_PASS']}"
    f"@{os.environ['MYSQL_HOST']}:{os.environ.get('MYSQL_PORT', '3306')}"
    f"/{os.environ['MYSQL_DATABASE']}"
)

_engine = create_engine(DSN, pool_pre_ping=True, pool_recycle=300)
_Session = sessionmaker(bind=_engine)


def get_session():
    return _Session()


def query(sql: str, params: tuple = ()) -> list[dict]:
    with _Session() as sess:
        result = sess.execute(text(sql), params)
        return [dict(r._mapping) for r in result]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> int:
    with _Session.begin() as sess:
        result = sess.execute(text(sql), params)
        return result.rowcount
