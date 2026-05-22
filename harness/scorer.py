"""
Programmatic scoring of a Trajectory against a task definition.

Scores are deterministic and do not require an LLM.
"""

from __future__ import annotations

from adapters.base import Trajectory


def score(trajectory: Trajectory, task: dict) -> dict[str, float]:
    """Return a dict of programmatic scores for a single task run."""
    return {
        "tool_correctness": _tool_correctness(trajectory, task),
        "efficiency": _efficiency(trajectory, task),
    }


def _tool_correctness(trajectory: Trajectory, task: dict) -> float:
    """1.0 if any expected tool was called, else 0.0. Skipped if no expected_tools."""
    expected: list[str] = task.get("expected_tools", [])
    if not expected:
        return 1.0  # no constraint specified — full credit

    called = {tc.name.upper() for tc in trajectory.tool_calls}
    return 1.0 if any(e.upper() in called for e in expected) else 0.0


def _efficiency(trajectory: Trajectory, task: dict) -> float:
    """min_tool_calls / actual_tool_calls, capped at 1.0. 1.0 if no calls made."""
    min_calls: int = task.get("min_tool_calls", 1)
    actual: int = len(trajectory.tool_calls)
    if actual == 0:
        return 0.0
    return min(1.0, min_calls / actual)
