"""
Programmatic scoring of a Trajectory against a task definition.

Scores are deterministic and do not require an LLM.
"""

from __future__ import annotations

from agent_mark.adapters.base import Trajectory


def score(trajectory: Trajectory, task: dict) -> dict[str, float]:
    """Return a dict of programmatic scores for a single task run."""
    return {
        "tool_correctness": _tool_correctness(trajectory, task),
        "efficiency": _efficiency(trajectory, task),
        "tool_error_rate": _tool_error_rate(trajectory),
        "within_max_calls": _within_max_calls(trajectory, task),
    }


def _tool_correctness(trajectory: Trajectory, task: dict) -> float:
    """1.0 if any expected tool was called, else 0.0. Skipped if no expected_tools."""
    expected: list[str] = task.get("expected_tools", [])
    if not expected:
        return 1.0  # no constraint specified — full credit

    called = {tc.name.upper() for tc in trajectory.tool_calls}
    return 1.0 if any(e.upper() in called for e in expected) else 0.0


def _efficiency(trajectory: Trajectory, task: dict) -> float:
    """min_tool_calls / actual_tool_calls, capped at 1.0. 0.0 if no calls made."""
    min_calls: int = task.get("min_tool_calls", 1)
    actual: int = len(trajectory.tool_calls)
    if actual == 0:
        return 0.0
    return min(1.0, min_calls / actual)


def _tool_error_rate(trajectory: Trajectory) -> float:
    """Fraction of tool calls whose result was an error (bad args, failed command, ...)."""
    if not trajectory.tool_calls:
        return 0.0
    errors = sum(
        1 for tc in trajectory.tool_calls
        if isinstance(tc.result, dict) and (tc.result.get("is_error") or "error" in tc.result)
    )
    return errors / len(trajectory.tool_calls)


def _within_max_calls(trajectory: Trajectory, task: dict) -> float:
    """1.0 if the agent stayed within max_tool_calls (or none is set), else 0.0."""
    max_calls = task.get("max_tool_calls")
    if max_calls is None:
        return 1.0
    return 1.0 if len(trajectory.tool_calls) <= max_calls else 0.0
