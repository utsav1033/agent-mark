"""
Workspace tasks: tasks that run inside a scratch copy of a small repository and are
verified programmatically instead of by an LLM judge.

Task layout (next to the task YAML):

    <id>.yaml
    <id>/repo/          copied into a fresh temp dir; the agent works here
    <id>/hidden_tests/  copied in only AFTER the agent finishes, then run
    <id>/solution/      reference solution, overlaid on repo/ by `agent-mark validate`

YAML fields used here:
    workspace: <id>            directory name next to the YAML
    verify: "<cmd>"            optional; default runs unittest over hidden_tests.
                               "{python}" is replaced with the current interpreter.
    expected_answer: <regex>   optional; must match the agent's final response
    must_not_modify: true      optional; any file change fails the task
    oracle_answer: "<text>"    optional; final response used by `validate`

Hidden tests are copied in after the run, so the agent can neither read nor edit
them. Verification is deterministic and costs nothing.
"""

from __future__ import annotations

import hashlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HIDDEN_DIR = "_hidden_tests"
DEFAULT_VERIFY = "{python} -m unittest discover -s " + HIDDEN_DIR + " -p 'test_*.py'"
VERIFY_TIMEOUT_S = 120


def task_root(task: dict) -> Path:
    return Path(task["_dir"]) / task["workspace"]


def prepare(task: dict) -> Path:
    """Copy the task's repo into a fresh temp dir and return its path."""
    workdir = Path(tempfile.mkdtemp(prefix=f"agent-mark-{task['id']}-"))
    shutil.copytree(task_root(task) / "repo", workdir, dirs_exist_ok=True)
    return workdir


def _snapshot(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def changed_files(task: dict, workdir: Path) -> list[str]:
    """Files added, removed or modified relative to the pristine repo."""
    before, after = _snapshot(task_root(task) / "repo"), _snapshot(workdir)
    after.pop(HIDDEN_DIR, None)
    after = {k: v for k, v in after.items() if not k.startswith(HIDDEN_DIR + "/")}
    return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))


def verify(task: dict, workdir: Path, final_response: str) -> dict:
    """Run all checks for a workspace task. Returns a judge-shaped result dict."""
    checks: list[str] = []
    ok = True
    changed = changed_files(task, workdir)

    if task.get("must_not_modify") and changed:
        ok = False
        checks.append(f"modified files on a read-only task: {', '.join(changed[:5])}")

    pattern = task.get("expected_answer")
    if pattern:
        if re.search(pattern, final_response or "", re.IGNORECASE | re.MULTILINE):
            checks.append("answer matched")
        else:
            ok = False
            checks.append(f"answer did not match /{pattern}/")

    hidden = task_root(task) / "hidden_tests"
    if hidden.is_dir() or task.get("verify"):
        if hidden.is_dir():
            dest = workdir / HIDDEN_DIR
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(hidden, dest)
        cmd = (task.get("verify") or DEFAULT_VERIFY).replace("{python}", shlex.quote(sys.executable))
        try:
            proc = subprocess.run(
                shlex.split(cmd), cwd=workdir, capture_output=True, text=True, timeout=VERIFY_TIMEOUT_S
            )
            tail = [ln for ln in (proc.stdout + proc.stderr).strip().splitlines() if ln.strip()][-1:] or [""]
            checks.append(f"tests exit {proc.returncode}: {tail[0][:200]}")
            ok = ok and proc.returncode == 0
        except subprocess.TimeoutExpired:
            ok = False
            checks.append(f"tests timed out after {VERIFY_TIMEOUT_S}s")

    return {
        "success": int(ok),
        "reasoning": "; ".join(checks) or "no checks defined",
        "method": "verify",
        "changed_files": changed,
    }


def cleanup(workdir: Path) -> None:
    shutil.rmtree(workdir, ignore_errors=True)


def validate(task: dict) -> tuple[bool, str]:
    """Check a workspace task is well-formed: untouched repo fails, reference passes."""
    # 1. Doing nothing must fail (otherwise the task measures nothing).
    wd = prepare(task)
    try:
        noop = verify(task, wd, "")
    finally:
        cleanup(wd)
    # 2. The reference solution must pass.
    wd = prepare(task)
    try:
        sol = task_root(task) / "solution"
        if sol.is_dir():
            shutil.copytree(sol, wd, dirs_exist_ok=True)
        oracle = verify(task, wd, task.get("oracle_answer", ""))
    finally:
        cleanup(wd)

    problems = []
    if noop["success"]:
        problems.append(f"no-op run PASSES ({noop['reasoning']})")
    if not oracle["success"]:
        problems.append(f"reference solution FAILS ({oracle['reasoning']})")
    return (not problems, "; ".join(problems) or "ok")
