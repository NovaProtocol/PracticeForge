"""Sandbox behavior tests for executor/bwrap_executor.py.

Nothing here touches the network or a real database: every test writes a
dummy script to disk and runs it inside the bwrap sandbox via
run_script_bwrap. Skipped when bwrap is not installed on the host.
"""

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap (bubblewrap) not installed on host",
)


@pytest.fixture(scope="module")
def bwrap_executor():
    from executor import bwrap_executor as mod

    return mod


def _write_script(tmp_path, name, code):
    script = tmp_path / name
    script.write_text(code)
    return str(script)


def test_hello_world_runs_and_returns_output(tmp_path, bwrap_executor):
    script = _write_script(tmp_path, "hello.py", "print('hello from sandbox')")
    result = bwrap_executor.run_script_bwrap(script, timeout=10)
    assert result["returncode"] == 0
    assert result["stdout"] == "hello from sandbox"
    assert result["stderr"] == ""


def test_infinite_loop_is_killed(tmp_path, bwrap_executor):
    script = _write_script(tmp_path, "loop.py", "while True:\n    pass\n")
    result = bwrap_executor.run_script_bwrap(script, timeout=3)
    assert result["returncode"] == -1
    assert "Time Limit Exceeded" in result["stderr"]


def test_sandbox_env_is_empty_and_has_no_secrets(tmp_path, bwrap_executor, monkeypatch):
    monkeypatch.setenv("SOLVESPACE_TEST_SECRET", "s3cr3t")
    script = _write_script(
        tmp_path,
        "env.py",
        "import os\nprint(os.environ.get('SOLVESPACE_TEST_SECRET'))\nprint(len(os.environ))\n",
    )
    result = bwrap_executor.run_script_bwrap(script, timeout=10)
    assert result["returncode"] == 0
    assert result["stdout"] == "None\n0"
