"""Guards the sandbox's process hygiene, the parts that are invisible until
they break on a real host.

Kept out of `test_executor_sandbox.py` on purpose: that module skips when bwrap
is absent, and these guards must run everywhere, because the bugs they protect
against only surface in the deployed container.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "executor" / "bwrap_executor.py"


def _function(name):
    tree = ast.parse(SRC.read_text())
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def _attrs(node):
    return {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def test_set_rlimits_does_not_set_rlimit_nproc():
    """RLIMIT_NPROC must not be applied to the bwrap process.

    Creating the sandbox user namespace is charged against the caller's
    RLIMIT_NPROC, and inside the container uid 0 is the host's root (no userns
    remapping), whose process count is already far above a small bound, so
    `unshare(CLONE_NEWUSER)` fails with EAGAIN and every run dies with
    "bwrap: Creating new namespace failed: Resource temporarily unavailable".
    Fork bombs are bounded by the pids cgroup, not this.
    """
    assert "RLIMIT_NPROC" not in _attrs(_function("_set_rlimits")), (
        "RLIMIT_NPROC must not be set on the bwrap process, it makes the user "
        "namespace fail with EAGAIN; see the note in _set_rlimits()."
    )


def test_every_sandbox_run_is_reaped():
    """`_run_sandboxed` must reap orphans after each run.

    The benchmark invokes the sandbox once per generated test case. One leaked
    child per run accumulated to 92 zombies, exhausted the container's pids
    cgroup (128), wedged gRPC's thread creation and stranded the queue in
    'running' (2026-10-08).
    """
    assert "reap_orphans" in {n.id for n in ast.walk(_function("_run_sandboxed")) if isinstance(n, ast.Name)}, (
        "_run_sandboxed must call reap_orphans() after the run."
    )


def test_sandbox_runs_in_their_own_session():
    """The sandbox must be its own process group, so a timeout can kill the tree.

    Killing bwrap alone leaves its children orphaned; they inherit the stdout
    pipe, so `communicate()` blocks forever even after the timeout fires.
    """
    run = _function("_run_sandboxed")
    kwargs = {k.arg for n in ast.walk(run) if isinstance(n, ast.Call) for k in n.keywords}
    assert "start_new_session" in kwargs, (
        "_run_sandboxed must start the sandbox with start_new_session=True so "
        "_kill_sandbox can killpg the whole tree."
    )
    assert "killpg" in _attrs(_function("_kill_sandbox")), (
        "_kill_sandbox must kill the sandbox's process group."
    )
