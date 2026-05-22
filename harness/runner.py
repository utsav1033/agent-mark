"""
Loads a task YAML, runs it through an adapter, scores the trajectory,
judges success via Gemini, and returns a structured result dict.

Errors during a run are caught, logged, and recorded — they never crash the suite.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
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


def run_task(task: dict, agent: Agent, results_dir: str | Path = "results") -> dict:
    """Run one task. Returns a result dict regardless of success or failure."""
    task_id = task["id"]
    log.info("Running task %s", task_id)

    result: dict[str, Any] = {
        "task_id": task_id,
        "toolkit": task.get("toolkit", ""),
        "difficulty": task.get("difficulty", ""),
        "mutates": task.get("mutates", False),
        "prompt": task["prompt"],
        "trajectory": None,
        "scores": {},
        "judge_result": None,
        "error": None,
        "run_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    try:
        trajectory: Trajectory = agent.run(task["prompt"])
        result["trajectory"] = _trajectory_to_dict(trajectory)
        result["scores"] = score(trajectory, task)

        judge_result = judge(
            prompt=task["prompt"],
            rubric=task.get("success_rubric", ""),
            response=trajectory.final_response,
        )
        result["judge_result"] = judge_result

    except Exception as exc:
        log.exception("Task %s errored: %s", task_id, exc)
        result["error"] = str(exc)

    # Persist to results/
    results_path = Path(results_dir)
    results_path.mkdir(exist_ok=True)
    out_file = results_path / f"{task_id}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    log.info("Task %s done → %s", task_id, out_file)
    return result
