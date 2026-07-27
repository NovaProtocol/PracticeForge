import json
import sqlite3
from datetime import datetime

from .config import DB_PATH
from . import log


class Database:

    def __init__(self):
        self.conn = sqlite3.connect(str(DB_PATH))
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS problems (
                contest_id INTEGER NOT NULL,
                problem_index TEXT NOT NULL,
                title TEXT,
                api_data TEXT,
                html TEXT,
                ai_data TEXT,
                status TEXT DEFAULT 'pending',
                uploaded INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (contest_id, problem_index)
            )
        """)
        self.conn.commit()
        log.info(f"SQLite ready at {DB_PATH}")

    def close(self):
        self.conn.close()

    def sync_api(self, problems: list[dict]):
        self.conn.executemany(
            "INSERT OR IGNORE INTO problems (contest_id, problem_index, api_data) VALUES (?, ?, ?)",
            [(p["contestId"], p["index"], json.dumps(p)) for p in problems],
        )
        self.conn.commit()
        log.info(f"Synced {len(problems)} problems from CF API")

    def get_pending(self):
        cur = self.conn.execute(
            "SELECT contest_id, problem_index, api_data FROM problems WHERE uploaded = 0 "
            "ORDER BY contest_id ASC, problem_index ASC"
        )
        return cur.fetchall()

    def mark(self, cid: int, idx: str, **kwargs):
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values())
        self.conn.execute(
            f"UPDATE problems SET {sets}, updated_at = ? WHERE contest_id = ? AND problem_index = ?",
            [*vals, datetime.now().isoformat(), cid, idx],
        )
        self.conn.commit()

    def mark_uploaded(self, cid: int, idx: str):
        self.mark(cid, idx, uploaded=1, status="done")

    def mark_failed(self, cid: int, idx: str, reason: str):
        log.warn(f"{cid}/{idx} marked as failed: {reason}")
        self.mark(cid, idx, status=f"failed:{reason}")
