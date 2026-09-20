"""Exercise the surviving query functions in shared.models against SQLite.

shared.models talks to SQLAlchemy through shared.db, whose engine is built
from MYSQL_* env vars on first use. Tests swap in a temporary SQLite engine
(plus its sessionmaker) so nothing needs a real database. Only functions
whose SQL is MySQL-agnostic are covered, the MySQL-only upserts
(ON DUPLICATE KEY UPDATE) are out of scope.
"""

import pytest

pytest.importorskip("sqlalchemy")

from shared import db
from shared.models import (
    create_file,
    create_solution,
    get_all_tags,
    get_problem,
    get_problem_submissions,
    get_problems_summary,
    get_solution,
    get_solution_results,
    get_solutions,
    list_files,
    load_code,
    save_code,
)
from shared.sqlalchemy_models import Base


@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_Session", sessionmaker(bind=engine))


def _insert_problem(**kw):
    defaults = dict(
        contest_id=1,
        problem_index="A",
        title="Test problem",
        slug="1/A-test-problem",
        tags="[]",
        url="https://example.com/1/A",
    )
    defaults.update(kw)
    cols = ", ".join(defaults)
    vals = ", ".join("%s" for _ in defaults)
    return db.execute(
        f"INSERT INTO problems ({cols}) VALUES ({vals})",
        tuple(defaults.values()),
    )


def test_get_problems_summary(sqlite_db):
    alpha = _insert_problem(
        contest_id=1, problem_index="A", title="Alpha", slug="1/A-alpha", tags='["math","dp"]'
    )
    beta = _insert_problem(
        contest_id=1, problem_index="B", title="Beta", slug="1/B-beta", tags="[]"
    )
    gamma = _insert_problem(
        contest_id=2, problem_index="A", title="Gamma", slug="2/A-gamma", tags=None
    )
    create_solution(alpha, "print(1)", verdict="Accepted", passed=1, total=1)
    create_solution(alpha, "print(2)", verdict="Accepted", passed=1, total=1)

    summary = get_problems_summary()
    assert [p["id"] for p in summary] == [alpha, beta, gamma]
    by_id = {p["id"]: p for p in summary}
    assert by_id[alpha]["completion"] == "completed"
    assert by_id[alpha]["submission_count"] == 2
    assert by_id[alpha]["tags"] == ["math", "dp"]
    assert by_id[beta]["completion"] == "incomplete"
    assert by_id[beta]["tags"] == []
    assert by_id[gamma]["tags"] == []


def test_get_problem(sqlite_db):
    pid = _insert_problem(
        contest_id=1, problem_index="A", title="Alpha", slug="1/A-alpha", tags='["math"]'
    )
    row = get_problem(1, "A")
    assert row["id"] == pid
    assert row["title"] == "Alpha"
    assert row["tags"] == ["math"]


def test_get_problem_missing(sqlite_db):
    assert get_problem(99, "Z") is None


def test_get_all_tags(sqlite_db):
    _insert_problem(contest_id=1, problem_index="A", slug="1/A-a", tags='["math"]')
    _insert_problem(contest_id=1, problem_index="B", slug="1/B-b", tags='["dp","math"]')
    _insert_problem(contest_id=1, problem_index="C", slug="1/C-c", tags="[]")
    assert get_all_tags() == ["dp", "math"]


def test_solution_lifecycle(sqlite_db):
    pid = _insert_problem(contest_id=1, problem_index="A", title="Alpha")
    sid = create_solution(pid, "print(1)", verdict="Accepted", passed=1, total=1)
    row = get_solution(sid)
    assert row["problem_id"] == pid
    assert row["verdict"] == "Accepted"
    subs = get_problem_submissions(pid)
    assert [s["id"] for s in subs] == [sid]
    assert get_solution_results(sid) == {"result": "{}", "stdout": ""}


def test_get_solutions_joins_problem(sqlite_db):
    pid = _insert_problem(contest_id=1, problem_index="A", title="Alpha")
    create_solution(pid, "print(1)")
    rows = get_solutions()
    assert len(rows) == 1
    assert rows[0]["title"] == "Alpha"


def test_auto_save_lifecycle(sqlite_db):
    pid = _insert_problem(contest_id=1, problem_index="A", title="Alpha")
    assert list_files(pid) == []
    create_file(pid, "main.py", code="print(1)")
    save_code(pid, "print(2)", filename="main.py")
    files = list_files(pid)
    assert len(files) == 1
    assert files[0]["code"] == "print(2)"
    saved = load_code(pid, "main.py")
    assert saved["code"] == "print(2)"
    assert saved["last_ran"] is None
