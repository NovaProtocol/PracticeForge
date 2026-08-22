"""Unit tests for the %s -> :pN placeholder conversion in shared.db.

The rest of the codebase writes PyMySQL-style SQL (%s placeholders);
shared.db._convert rewrites them into SQLAlchemy named params (:p0, :p1, ...)
so text() can bind them.
"""

from shared.db import _convert


def test_no_params_leaves_sql_untouched():
    sql = "SELECT * FROM problems ORDER BY id"
    assert _convert(sql, ()) == (sql, {})


def test_single_placeholder():
    sql, params = _convert("SELECT * FROM problems WHERE id = %s", (42,))
    assert sql == "SELECT * FROM problems WHERE id = :p0"
    assert params == {"p0": 42}


def test_placeholders_become_positional_named_params():
    sql, params = _convert(
        "SELECT * FROM problems WHERE contest_id = %s AND problem_index = %s",
        (1, "A"),
    )
    assert sql == ("SELECT * FROM problems WHERE contest_id = :p0 AND problem_index = :p1")
    assert params == {"p0": 1, "p1": "A"}


def test_repeated_values_get_distinct_params():
    sql, params = _convert(
        "SELECT * FROM solutions WHERE verdict = %s OR verdict = %s",
        ("Accepted", "Accepted"),
    )
    assert sql == "SELECT * FROM solutions WHERE verdict = :p0 OR verdict = :p1"
    assert params == {"p0": "Accepted", "p1": "Accepted"}


def test_many_placeholders_across_clauses():
    sql, params = _convert(
        "SELECT id FROM auto_saves WHERE problem_id = %s AND filename = %s AND active = %s",
        (7, "main.py", True),
    )
    assert sql == (
        "SELECT id FROM auto_saves WHERE problem_id = :p0 AND filename = :p1 AND active = :p2"
    )
    assert params == {"p0": 7, "p1": "main.py", "p2": True}


def test_extra_params_without_placeholders_are_harmless():
    # SQL without %s but with params: SQL is unchanged and the params dict is
    # built anyway; SQLAlchemy text() ignores unconsumed named params.
    sql = "SELECT COUNT(*) FROM problems"
    new_sql, params = _convert(sql, (1,))
    assert new_sql == sql
    assert params == {"p0": 1}
