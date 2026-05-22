"""
Aggregates JSON result files from results/ into a markdown report.

Usage:
    from harness.report import generate_report
    md = generate_report("results/")
    print(md)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_results(results_dir: str | Path) -> list[dict]:
    p = Path(results_dir)
    results = []
    for f in sorted(p.glob("*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                results.append(json.load(fh))
        except Exception:
            pass
    return results


def _aggregate(results: list[dict], group_key: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for r in results:
        key = r.get(group_key, "unknown")
        groups.setdefault(key, []).append(r)

    out: dict[str, dict] = {}
    for key, items in groups.items():
        total = len(items)
        errored = sum(1 for r in items if r.get("error"))
        judged = [r for r in items if r.get("judge_result") and r["judge_result"].get("success") is not None]
        success_rate = sum(r["judge_result"]["success"] for r in judged) / len(judged) if judged else None
        tool_corr = [r["scores"]["tool_correctness"] for r in items if r.get("scores")]
        efficiency = [r["scores"]["efficiency"] for r in items if r.get("scores")]
        latencies = [r["trajectory"]["total_latency_ms"] for r in items if r.get("trajectory")]
        tokens = [
            r["trajectory"]["input_tokens"] + r["trajectory"]["output_tokens"]
            for r in items
            if r.get("trajectory")
        ]
        out[key] = {
            "total": total,
            "errored": errored,
            "success_rate": success_rate,
            "tool_correctness": _avg(tool_corr),
            "efficiency": _avg(efficiency),
            "avg_latency_ms": _avg(latencies),
            "avg_tokens": _avg(tokens),
        }
    return out


def _avg(vals: list[float]) -> float | None:
    return sum(vals) / len(vals) if vals else None


def _fmt(val: float | None, pct: bool = False) -> str:
    if val is None:
        return "—"
    if pct:
        return f"{val:.0%}"
    return f"{val:.1f}"


def _table(agg: dict[str, dict], label: str) -> str:
    lines = [
        f"| {label} | Tasks | Errors | Success | Tool Correct | Efficiency | Avg Latency (ms) | Avg Tokens |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for key, s in sorted(agg.items()):
        lines.append(
            f"| {key} | {s['total']} | {s['errored']} | {_fmt(s['success_rate'], pct=True)}"
            f" | {_fmt(s['tool_correctness'], pct=True)} | {_fmt(s['efficiency'], pct=True)}"
            f" | {_fmt(s['avg_latency_ms'])} | {_fmt(s['avg_tokens'])} |"
        )
    return "\n".join(lines)


def _example_trajectory(result: dict) -> str:
    traj = result.get("trajectory") or {}
    tool_calls = traj.get("tool_calls", [])
    tools_md = "\n".join(
        f"  {i + 1}. `{tc['name']}` → {str(tc.get('result', ''))[:120]}"
        for i, tc in enumerate(tool_calls)
    )
    judge = result.get("judge_result") or {}
    return (
        f"**Task:** `{result['task_id']}` ({result['difficulty']})\n\n"
        f"**Prompt:** {result['prompt']}\n\n"
        f"**Tool calls ({len(tool_calls)}):**\n{tools_md or '  _(none)_'}\n\n"
        f"**Final response (excerpt):** {traj.get('final_response', '')[:300]}\n\n"
        f"**Judge:** success={judge.get('success')} — {judge.get('reasoning', '')}"
    )


def generate_report(results_dir: str | Path, adapter_name: str = "unknown") -> str:
    results = _load_results(results_dir)
    if not results:
        return "# agent-mark Report\n\nNo results found."

    by_toolkit = _aggregate(results, "toolkit")
    by_difficulty = _aggregate(results, "difficulty")

    # Pick one success and one failure for example trajectories
    successes = [r for r in results if r.get("judge_result", {}).get("success") == 1]
    failures = [r for r in results if r.get("judge_result", {}).get("success") == 0]
    examples: list[dict] = []
    if successes:
        examples.append(successes[0])
    if failures:
        examples.append(failures[0])

    parts = [
        f"# agent-mark Evaluation Report",
        f"\nAdapter: **{adapter_name}** | Tasks run: **{len(results)}**\n",
        "## Results by Toolkit\n",
        _table(by_toolkit, "Toolkit"),
        "\n## Results by Difficulty\n",
        _table(by_difficulty, "Difficulty"),
        "\n## Example Trajectories\n",
    ]

    for ex in examples:
        label = "Success" if ex.get("judge_result", {}).get("success") == 1 else "Failure"
        parts.append(f"\n<details>\n<summary>Example {label}: {ex['task_id']}</summary>\n")
        parts.append(_example_trajectory(ex))
        parts.append("\n</details>\n")

    parts.append("\n## What I Learned\n")
    parts.append("_Fill this section after reviewing results._\n")
    parts.append("1. \n2. \n3. \n")

    return "\n".join(parts)


def write_report(results_dir: str | Path, output: str | Path, adapter_name: str = "unknown") -> None:
    md = generate_report(results_dir, adapter_name=adapter_name)
    with open(output, "w", encoding="utf-8") as f:
        f.write(md)
