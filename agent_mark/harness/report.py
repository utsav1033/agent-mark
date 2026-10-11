"""
Aggregates JSON result files from results/ into a markdown report.

Usage:
    from agent_mark.harness.report import generate_report
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
        if f.name.startswith("_"):  # run metadata, not a task result
            continue
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
        costs = [float(r.get("cost_usd") or 0.0) for r in items]
        err_rate = [r["scores"]["tool_error_rate"] for r in items if r.get("scores", {}).get("tool_error_rate") is not None]
        calls = [len(r["trajectory"]["tool_calls"]) for r in items if r.get("trajectory")]
        out[key] = {
            "total": total,
            "errored": errored,
            "success_rate": success_rate,
            "tool_correctness": _avg(tool_corr),
            "efficiency": _avg(efficiency),
            "avg_latency_ms": _avg(latencies),
            "avg_tokens": _avg(tokens),
            "avg_tool_calls": _avg(calls),
            "tool_error_rate": _avg(err_rate),
            "total_cost": sum(costs),
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


def _usd(val: float | None) -> str:
    return "—" if val is None else f"${val:.4f}"


def _table(agg: dict[str, dict], label: str) -> str:
    lines = [
        f"| {label} | Tasks | Errors | Success | Tool Correct | Efficiency | Tool Err Rate"
        " | Avg Calls | Avg Latency (s) | Avg Tokens | Cost |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    order = {"easy": 0, "medium": 1, "hard": 2}
    for key, s in sorted(agg.items(), key=lambda kv: (order.get(kv[0], 9), kv[0])):
        lat = s["avg_latency_ms"] / 1000 if s["avg_latency_ms"] is not None else None
        lines.append(
            f"| {key} | {s['total']} | {s['errored']} | {_fmt(s['success_rate'], pct=True)}"
            f" | {_fmt(s['tool_correctness'], pct=True)} | {_fmt(s['efficiency'], pct=True)}"
            f" | {_fmt(s['tool_error_rate'], pct=True)} | {_fmt(s['avg_tool_calls'])}"
            f" | {_fmt(lat)} | {_fmt(s['avg_tokens'])} | {_usd(s['total_cost'])} |"
        )
    return "\n".join(lines)


def _summary(results: list[dict]) -> str:
    judged = [r for r in results if (r.get("judge_result") or {}).get("success") is not None]
    solved = sum(1 for r in judged if r["judge_result"]["success"] == 1)
    total_cost = sum(float(r.get("cost_usd") or 0.0) for r in results)
    lat = sorted(r["trajectory"]["total_latency_ms"] / 1000 for r in results if r.get("trajectory"))
    stops: dict[str, int] = {}
    for r in results:
        reason = (r.get("trajectory") or {}).get("stop_reason") or ("error" if r.get("error") else "")
        if reason:
            stops[reason] = stops.get(reason, 0) + 1
    rate = f"{solved / len(judged):.0%}" if judged else "—"
    per_solved = _usd(total_cost / solved) if solved else "—"
    median = f"{lat[len(lat) // 2]:.1f}s" if lat else "—"
    lines = [
        f"**Solved {solved}/{len(judged)} ({rate})** · total cost **{_usd(total_cost)}**"
        f" · cost per solved task **{per_solved}** · median latency **{median}**",
    ]
    if stops:
        lines.append("\nStop reasons: " + ", ".join(f"`{k}` × {v}" for k, v in sorted(stops.items())))
    return "\n".join(lines)


def _example_trajectory(result: dict) -> str:
    traj = result.get("trajectory") or {}
    tool_calls = traj.get("tool_calls", [])
    tools_md = "\n".join(
        f"  {i + 1}. `{tc['name']}({json.dumps(tc.get('args', {}))[:100]})` → "
        f"{str((tc.get('result') or {}).get('text', tc.get('result', '')))[:120]!r}"
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


def _pass_k_table(results: list[dict]) -> str | None:
    """
    Build a pass^k curve table from results that have a pass_k field.
    Returns None if no results were run with --repeat > 1.
    """
    repeat_results = [r for r in results if r.get("pass_k")]
    if not repeat_results:
        return None

    max_k = max(int(k) for r in repeat_results for k in r["pass_k"])

    lines = [
        "| k | Tasks with pass_k data | pass^k rate |",
        "|---|---|---|",
    ]
    for k in range(1, max_k + 1):
        sk = str(k)
        eligible = [r for r in repeat_results if sk in r.get("pass_k", {})]
        if not eligible:
            continue
        passed = sum(1 for r in eligible if r["pass_k"][sk] == 1)
        rate = passed / len(eligible)
        lines.append(f"| {k} | {len(eligible)} | {rate:.0%} |")

    note = (
        "\n_pass^k = fraction of tasks where all k independent runs succeeded. "
        "A steep drop from k=1 to k=2 indicates the agent is non-deterministic on borderline tasks._"
    )
    return "\n".join(lines) + note


def _load_meta(results_dir: str | Path) -> dict:
    f = Path(results_dir) / "_run.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def generate_report(results_dir: str | Path, adapter_name: str = "unknown") -> str:
    results = _load_results(results_dir)
    if not results:
        return "# agent-mark Report\n\nNo results found."
    meta = _load_meta(results_dir)
    adapter_name = meta.get("adapter", adapter_name)
    model = meta.get("model")

    by_toolkit = _aggregate(results, "toolkit")
    by_difficulty = _aggregate(results, "difficulty")

    successes = [r for r in results if (r.get("judge_result") or {}).get("success") == 1]
    failures = [r for r in results if (r.get("judge_result") or {}).get("success") == 0]
    examples: list[dict] = []
    if successes:
        examples.append(successes[0])
    if failures:
        examples.append(failures[0])

    parts = [
        "# agent-mark Evaluation Report",
        f"\nAdapter: **{adapter_name}**" + (f" | Model: **{model}**" if model else "")
        + f" | Tasks run: **{len(results)}**\n",
        _summary(results) + "\n",
        "## Results by Toolkit\n",
        _table(by_toolkit, "Toolkit"),
        "\n## Results by Difficulty\n",
        _table(by_difficulty, "Difficulty"),
    ]

    pass_k_md = _pass_k_table(results)
    if pass_k_md:
        parts.append("\n## pass^k Reliability Curve\n")
        parts.append(pass_k_md)

    parts.append("\n## Example Trajectories\n")
    for ex in examples:
        label = "Success" if (ex.get("judge_result") or {}).get("success") == 1 else "Failure"
        parts.append(f"\n<details>\n<summary>Example {label}: {ex['task_id']}</summary>\n")
        parts.append(_example_trajectory(ex))
        parts.append("\n</details>\n")

    parts.append("\n## Per-task results\n")
    parts.append("| Task | Difficulty | Result | Calls | Tool errors | Latency (s) | Cost | Why |")
    parts.append("|---|---|---|---|---|---|---|---|")
    for r in sorted(results, key=lambda r: r["task_id"]):
        jr, traj = r.get("judge_result") or {}, r.get("trajectory") or {}
        res = "ERROR" if r.get("error") else {1: "PASS", 0: "FAIL"}.get(jr.get("success"), "JUDGE-FAIL")
        why = (r.get("error") or jr.get("reasoning") or "").replace("|", "\\|")[:90]
        n_calls = len(traj.get("tool_calls", []))
        errs = (r.get("scores") or {}).get("tool_error_rate")
        parts.append(
            f"| {r['task_id']} | {r.get('difficulty', '')} | {res} | {n_calls}"
            f" | {_fmt(errs, pct=True)} | {_fmt(traj.get('total_latency_ms', 0) / 1000)}"
            f" | {_usd(float(r.get('cost_usd') or 0.0))} | {why} |"
        )

    return "\n".join(parts)


def write_report(results_dir: str | Path, output: str | Path, adapter_name: str = "unknown") -> None:
    md = generate_report(results_dir, adapter_name=adapter_name)
    with open(output, "w", encoding="utf-8") as f:
        f.write(md)
