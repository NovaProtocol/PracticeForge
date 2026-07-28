from __future__ import annotations

from shared.db import _engine, execute
from shared.sqlalchemy_models import Base, Problem, TestCase, Solution, ExecutionQueue, AutoSave


def run():
    Base.metadata.create_all(_engine)

    # Column type migrations (create_all doesn't modify existing columns)
    try:
        execute("ALTER TABLE execution_queue MODIFY COLUMN exec_type ENUM('run','submit','brute_force','submit_brute') DEFAULT 'run'")
    except Exception:
        pass
    try:
        execute("ALTER TABLE execution_queue MODIFY COLUMN stdout LONGTEXT")
    except Exception:
        pass
    try:
        row = query_one("SHOW COLUMNS FROM auto_saves LIKE 'active'")
        if not row:
            execute("ALTER TABLE auto_saves ADD COLUMN active BOOLEAN DEFAULT TRUE")
    except Exception:
        pass
