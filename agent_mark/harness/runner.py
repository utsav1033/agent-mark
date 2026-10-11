"""
Loads a task YAML, runs it through an adapter (optionally k times), scores the
trajectory, decides success, and returns a structured result dict.

Success is decided by one of:
  - workspace tasks: programmatic verification (hidden tests / answer regex),
    see harness/workspace.py — deterministic, no LLM call
  - mock adapter: its pre-set judge result
  - everything else: the Gemini rubric judge

With repeat=1 (default) the result has a single run at the top level.
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

from agent_mark.adapters.base import Agent, Trajectory
from agent_mark.harness import workspace
from agent_mark.harness.scorer import score

log = logging.getLogger(__name__)


def load_task(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        task = yaml.safe_load(f)
    task["_dir"] = str(Path(path).parent)  # resolves workspace dirs next to the YAML
    return task


def _trajectory_to_dict(t: Trajectory) -> dict:
    return dataclasses.asdict(t)


def _decide_success(task: dict, agent: Agent, trajectory: Trajectory, workdir: Path | None) -> dict:
    if workdir is not None:
        return workspace.verify(task, workdir, trajectory.final_response)
    if hasattr(agent, "get_mock_judge"):
        return agent.get_mock_judge(task["prompt"]) or {
            "success": None,
            "reasoning": "judge-failed: no mock result for prompt",
        }
    from agent_mark.harness.judge import judge  # lazy: needs google-genai + GOOGLE_API_KEY

    return judge(
        prompt=task["prompt"],
        rubric=task.get("success_rubric", ""),
        response=trajectory.final_response,
    )


def _run_once(task: dict, agent: Agent, keep_workspace: bool = False) -> dict:
    """Execute the task once. Returns a single-run dict (no task metadata)."""
    workdir: Path | None = None
    try:
        if task.get("workspace"):
            workdir = workspace.prepare(task)
            try:
                trajectory: Trajectory = agent.run(task["prompt"], workdir=workdir)
            except TypeError as exc:
                if "workdir" in str(exc):
                    raise RuntimeError(
                        f"adapter {type(agent).__name__} cannot run workspace tasks (no workdir support)"
                    ) from exc
                raise
        else:
            trajectory = agent.run(task["prompt"])

        return {
            "trajectory": _trajectory_to_dict(trajectory),
            "scores": score(trajectory, task),
            "judge_result": _decide_success(task, agent, trajectory, workdir),
            "error": None,
        }

    except Exception as exc:
        log.exception("Task %s errored: %s", task.get("id"), exc)
        return {"trajectory": None, "scores": {}, "judge_result": None, "error": str(exc)}

    finally:
        if workdir is not None:
            if keep_workspace:
                log.info("Kept workspace for %s at %s", task.get("id"), workdir)
            else:
                workspace.cleanup(workdir)


def run_cost(run: dict) -> float:
    return float((run.get("trajectory") or {}).get("cost_usd") or 0.0)


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
    budget_left_usd: float | None = None,
    keep_workspace: bool = False,
) -> dict:
    """Run one task up to `repeat` times, stopping early if the $ budget runs out.

    Returns a result dict regardless of success or failure, and writes it to
    <results_dir>/<task_id>.json.
    """
    task_id = task["id"]
    log.info("Running task %s (repeat=%d)", task_id, repeat)

    runs: list[dict] = []
    spent = 0.0
    for i in range(repeat):
        if budget_left_usd is not None and spent >= budget_left_usd:
            log.warning("Budget exhausted — stopping %s after %d/%d runs", task_id, i, repeat)
            break
        if repeat > 1:
            log.info("  run %d/%d", i + 1, repeat)
        runs.append(_run_once(task, agent, keep_workspace=keep_workspace))
        spent += run_cost(runs[-1])

    first = runs[0]
    result: dict[str, Any] = {
        "task_id": task_id,
        "toolkit": task.get("toolkit", ""),
        "difficulty": task.get("difficulty", ""),
        "mutates": task.get("mutates", False),
        "prompt": task["prompt"],
        # Top-level fields from run 1
        "trajectory": first["trajectory"],
        "scores": first["scores"],
        "judge_result": first["judge_result"],
        "error": first["error"],
        "cost_usd": spent,
        "run_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    if repeat > 1:
        result["repeat"] = len(runs)
        result["runs"] = [{"run": i + 1, **r} for i, r in enumerate(runs)]
        result["pass_k"] = _compute_pass_k(runs)

    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)
    out_file = results_path / f"{task_id}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    log.info("Task %s done → %s", task_id, out_file)
    return result
