"""
Loads a task YAML, runs it through an adapter (optionally k times), scores the
trajectory, judges success, and returns a structured result dict.

With repeat=1 (default) the result shape is identical to previous versions.
With repeat=k the result gains two extra keys:
  runs     — list of per-run dicts (trajectory, scores, judge_result, error)
  pass_k   — {"1": 0|1|None, "2": ..., ...} for k = 1..repeat

Errors during a run are caught, logged, and recorded — they never crash the suite.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import time
from pathlib import Path
from typing import Any

import yaml

from adapters.base import Agent, Trajectory
from harness.scorer import score
from harness.judge import judge

log = logging.getLogger(__name__)


def load_task(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _trajectory_to_dict(t: Trajectory) -> dict:
    return {
        "prompt": t.prompt,
        "tool_calls": [dataclasses.asdict(tc) for tc in t.tool_calls],
        "final_response": t.final_response,
        "total_latency_ms": t.total_latency_ms,
        "input_tokens": t.input_tokens,
        "output_tokens": t.output_tokens,
    }


def _run_once(task: dict, agent: Agent) -> dict:
    """Execute the task once. Returns a single-run dict (no task metadata)."""
    try:
        trajectory: Trajectory = agent.run(task["prompt"])
        scores = score(trajectory, task)

        if hasattr(agent, "get_mock_judge"):
            judge_result = agent.get_mock_judge(task["prompt"]) or {
                "success": None,
                "reasoning": "judge-failed: no mock result for prompt",
            }
        else:
            judge_result = judge(
                prompt=task["prompt"],
                rubric=task.get("success_rubric", ""),
                response=trajectory.final_response,
            )

        return {
            "trajectory": _trajectory_to_dict(trajectory),
            "scores": scores,
            "judge_result": judge_result,
            "error": None,
        }

    except Exception as exc:
        log.exception("Task %s errored: %s", task.get("id"), exc)
        return {
            "trajectory": None,
            "scores": {},
            "judge_result": None,
            "error": str(exc),
        }


def _compute_pass_k(runs: list[dict]) -> dict[str, int | None]:
    """
    For each k in 1..len(runs), return 1 if the first k runs all succeeded,
    0 if any failed, None if any judge result was inconclusive.
    """
    pass_k: dict[str, int | None] = {}
    for k in range(1, len(runs) + 1):
        first_k = [r["judge_result"].get("success") if r.get("judge_result") else None for r in runs[:k]]
        if any(s is None for s in first_k):
            pass_k[str(k)] = None
        elif all(s == 1 for s in first_k):
            pass_k[str(k)] = 1
        else:
            pass_k[str(k)] = 0
    return pass_k


def run_task(
    task: dict,
    agent: Agent,
    results_dir: str | Path = "results",
    repeat: int = 1,
) -> dict:
    """Run one task repeat times. Returns a result dict regardless of success or failure."""
    task_id = task["id"]
    log.info("Running task %s (repeat=%d)", task_id, repeat)

    runs = []
    for i in range(repeat):
        if repeat > 1:
            log.info("  run %d/%d", i + 1, repeat)
        runs.append(_run_once(task, agent))

    first = runs[0]
    result: dict[str, Any] = {
        "task_id": task_id,
        "toolkit": task.get("toolkit", ""),
        "difficulty": task.get("difficulty", ""),
        "mutates": task.get("mutates", False),
        "prompt": task["prompt"],
        # Top-level fields from run 1 (backward-compatible)
        "trajectory": first["trajectory"],
        "scores": first["scores"],
        "judge_result": first["judge_result"],
        "error": first["error"],
        "run_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    if repeat > 1:
        result["repeat"] = repeat
        result["runs"] = [{"run": i + 1, **r} for i, r in enumerate(runs)]
        result["pass_k"] = _compute_pass_k(runs)

    results_path = Path(results_dir)
    results_path.mkdir(exist_ok=True)
    out_file = results_path / f"{task_id}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    log.info("Task %s done → %s", task_id, out_file)
    return result
