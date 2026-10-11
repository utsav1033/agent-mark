"""
agent-mark CLI.

Usage:
    agent-mark demo                                   # mock run, no API keys, $0
    agent-mark list                                   # show bundled task suites
    agent-mark validate                               # check every coding task, $0
    agent-mark run --adapter pi --model claude-haiku-5-5 \\
        --base-url "$LITELLM_BASE_URL" --api-key-env LITELLM_API_KEY \\
        --suite coding --budget-usd 1 --dry-run
    agent-mark run --adapter command --agent-cmd "my-agent -p {prompt}" --suite coding
    agent-mark run --adapter mypkg.agent:MyAgent --suite coding
    agent-mark report results/pi-claude-haiku-5-5
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Package directory — tasks are bundled here so this path is valid whether
# running from source or from a pip-installed wheel.
_PKG_DIR = Path(__file__).parent

# Project root — only used to load .env when running from source.
_ROOT = _PKG_DIR.parent

TASKS_DIR = _PKG_DIR / "tasks"

# Adapters that never call a paid API.
_FREE_ADAPTERS = {"mock"}


def _load_dotenv() -> None:
    """Load .env from the project root into os.environ (skip already-set vars)."""
    env_file = _ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


_load_dotenv()

_LBLUE = "\033[96m"
_RESET = "\033[0m"

BANNER = _LBLUE + """
 █████╗  ██████╗ ███████╗███╗   ██╗████████╗   ███╗   ███╗ █████╗ ██████╗ ██╗  ██╗
██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝   ████╗ ████║██╔══██╗██╔══██╗██║ ██╔╝
███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║█████╗██╔████╔██║███████║██████╔╝█████╔╝
██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║╚════╝██║╚██╔╝██║██╔══██║██╔══██╗██╔═██╗
██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║      ██║ ╚═╝ ██║██║  ██║██║  ██║██║  ██╗
╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝      ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝

  > benchmark any tool-using agent: success, path, latency, cost
""" + _RESET


# --------------------------------------------------------------------------- tasks

def _discover_tasks(root: Path, suite: str | None = None) -> list[Path]:
    """Task YAMLs live at <root>/<suite>/<id>.yaml. `suite` may also be a difficulty."""
    import yaml

    if suite and (root / suite).is_dir():
        return sorted((root / suite).glob("*.yaml"))
    files = sorted(root.glob("*/*.yaml"))
    if suite:
        files = [f for f in files if (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("difficulty") == suite]
    return files


def _select_tasks(args: argparse.Namespace) -> list[Path]:
    root = Path(args.tasks) if args.tasks else TASKS_DIR
    if args.task:
        matches = sorted(root.glob(f"*/{args.task}.yaml"))
        if not matches:
            sys.exit(f"ERROR: task '{args.task}' not found under {root}")
        return matches[:1]
    if args.suite:
        files = _discover_tasks(root, args.suite)
    elif args.all:
        files = _discover_tasks(root)
    else:
        sys.exit("ERROR: specify --task TASK_ID, --suite NAME, or --all")
    if not files:
        sys.exit(f"ERROR: no tasks found (root={root}, suite={args.suite})")
    return files


# --------------------------------------------------------------------------- pricing

def _litellm_prices(base_url: str, model: str, api_key: str | None) -> tuple[float, float] | None:
    """Look up $/Mtok for `model` from a LiteLLM proxy's /model/info. Free metadata call."""
    import httpx

    root = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    for url in (f"{root}/model/info", re.sub(r"/v1$", "", root) + "/model/info"):
        try:
            resp = httpx.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue
            for m in resp.json().get("data", []):
                info = m.get("model_info") or {}
                if m.get("model_name") == model and info.get("input_cost_per_token"):
                    return (info["input_cost_per_token"] * 1e6, (info.get("output_cost_per_token") or 0) * 1e6)
        except Exception as exc:  # pricing lookup is best-effort
            logging.getLogger(__name__).debug("price lookup %s failed: %s", url, exc)
    return None


# --------------------------------------------------------------------------- adapters

def _build_agent(args: argparse.Namespace):
    a = args.adapter
    if a == "pi":
        from agent_mark.adapters.pi import PiAgent, PiConfig

        if not args.model:
            sys.exit("ERROR: --adapter pi needs --model")
        price_in, price_out = args.price_in, args.price_out
        if args.base_url and price_in is None and price_out is None:
            found = _litellm_prices(args.base_url, args.model, os.environ.get(args.api_key_env))
            if found:
                price_in, price_out = found
                print(f"Prices from gateway for {args.model}: ${price_in:.2f}/M in, ${price_out:.2f}/M out")
        if args.base_url and not (price_in or price_out):
            print("WARNING: no prices known for this model — the $ budget cannot be enforced, "
                  "only --max-tokens-per-task. Pass --price-in/--price-out.", file=sys.stderr)
        return PiAgent(PiConfig(
            model=args.model,
            provider=args.provider or ("litellm" if args.base_url else None),
            binary=args.pi_binary,
            tools=args.pi_tools,
            thinking=args.thinking,
            base_url=args.base_url,
            api_key_env=args.api_key_env,
            price_in_per_mtok=price_in or 0.0,
            price_out_per_mtok=price_out or 0.0,
            max_cost_usd=args.max_cost_per_task,
            max_tokens=args.max_tokens_per_task,
            timeout_s=args.timeout,
        ))
    if a == "command":
        from agent_mark.adapters.command import CommandAgent

        if not args.agent_cmd:
            sys.exit('ERROR: --adapter command needs --agent-cmd "your-agent ... {prompt}"')
        return CommandAgent(args.agent_cmd, timeout_s=args.timeout)
    if a == "simple":
        from agent_mark.adapters.simple import SimpleAgent

        return SimpleAgent(**({"model": args.model} if args.model else {}))
    if a == "trustclaw":
        from agent_mark.adapters.trustclaw import TrustClawAgent

        return TrustClawAgent()
    if a == "mock":
        from agent_mark.adapters.mock import MockAgent

        return MockAgent()
    if ":" in a:  # bring-your-own adapter: "package.module:ClassName"
        import importlib

        sys.path.insert(0, os.getcwd())
        module, _, cls = a.partition(":")
        return getattr(importlib.import_module(module), cls)()
    sys.exit(f"ERROR: unknown adapter {a!r}. Use pi, command, simple, trustclaw, mock, or module:Class")


def _agent_version(args: argparse.Namespace) -> str | None:
    if args.adapter != "pi":
        return None
    try:
        out = subprocess.run([args.pi_binary, "--version"], capture_output=True, text=True, timeout=15)
        return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else None
    except Exception:
        return None


def _default_results_dir(args: argparse.Namespace) -> Path:
    name = args.adapter.replace(":", "_").replace(".", "_")
    if args.model:
        name += "-" + re.sub(r"[^A-Za-z0-9._-]+", "_", args.model)
    return Path.cwd() / "results" / name


# --------------------------------------------------------------------------- commands

def cmd_demo(args: argparse.Namespace) -> None:
    """Run the mock adapter against all Gmail tasks and print a report. No API keys needed."""
    from agent_mark.adapters.mock import MockAgent
    from agent_mark.harness.report import write_report
    from agent_mark.harness.runner import load_task, run_task

    results_dir = Path(args.output) if args.output else Path.cwd() / "results" / "mock"
    print("\nRunning demo against Gmail tasks (no API keys required)...\n")
    agent = MockAgent()
    passed = 0
    files = sorted((TASKS_DIR / "gmail").glob("*.yaml"))
    for task_file in files:
        result = run_task(load_task(task_file), agent, results_dir=results_dir)
        jr = result.get("judge_result") or {}
        passed += jr.get("success") == 1
        print(f"[{'PASS' if jr.get('success') == 1 else 'FAIL':4}] {result['task_id']} — {jr.get('reasoning', '')}")
    print(f"\nDone: {passed}/{len(files)} passed.")
    out = results_dir / "report.md"
    write_report(results_dir, out, adapter_name="mock")
    print(f"Report written to {out}")


def cmd_list(args: argparse.Namespace) -> None:
    import yaml

    root = Path(args.tasks) if args.tasks else TASKS_DIR
    for suite in sorted(p for p in root.iterdir() if p.is_dir()):
        files = sorted(suite.glob("*.yaml"))
        if not files:
            continue
        print(f"\n{suite.name} ({len(files)} tasks)")
        for f in files:
            t = yaml.safe_load(f.read_text(encoding="utf-8"))
            kind = "workspace" if t.get("workspace") else "judge"
            prompt = " ".join(str(t.get("prompt", "")).split())
            print(f"  {t['id']:12} {t.get('difficulty', ''):7} {kind:9} {prompt[:70]}")


def cmd_validate(args: argparse.Namespace) -> None:
    """Check every workspace task: untouched repo must fail, reference solution must pass."""
    from agent_mark.harness.runner import load_task
    from agent_mark.harness.workspace import validate

    root = Path(args.tasks) if args.tasks else TASKS_DIR
    bad = 0
    for f in _discover_tasks(root, args.suite):
        task = load_task(f)
        if not task.get("workspace"):
            continue
        ok, msg = validate(task)
        bad += not ok
        print(f"[{'OK' if ok else 'BAD':3}] {task['id']} — {msg}")
    print(f"\n{'All tasks valid.' if not bad else f'{bad} invalid task(s).'}")
    sys.exit(1 if bad else 0)


def cmd_run(args: argparse.Namespace) -> None:
    from agent_mark.harness.report import write_report
    from agent_mark.harness.runner import load_task, run_cost, run_task

    task_files = _select_tasks(args)
    results_dir = Path(args.output) if args.output else _default_results_dir(args)

    # Skip tasks that already have a clean result, so re-runs never pay twice.
    todo, skipped = [], []
    for f in task_files:
        existing = results_dir / f"{f.stem}.json"
        if existing.exists() and not args.force:
            try:
                if not json.loads(existing.read_text(encoding="utf-8")).get("error"):
                    skipped.append(f.stem)
                    continue
            except Exception:
                pass
        todo.append(f)

    paid = args.adapter not in _FREE_ADAPTERS
    n_runs = len(todo) * args.repeat
    ceiling = min(args.budget_usd, n_runs * args.max_cost_per_task) if args.max_cost_per_task else args.budget_usd

    print(f"Plan: adapter={args.adapter}" + (f" model={args.model}" if args.model else ""))
    print(f"      {len(todo)} task(s) × {args.repeat} run(s) = {n_runs} agent run(s); "
          f"results → {results_dir}")
    if skipped:
        print(f"      skipping {len(skipped)} task(s) with existing results (use --force to re-run): "
              + ", ".join(skipped))
    if paid:
        print(f"      spend guards: suite budget ${args.budget_usd:.2f}, per task ${args.max_cost_per_task:.2f}, "
              f"{args.max_tokens_per_task:,} tokens/task, {args.timeout:.0f}s timeout")
        print(f"      worst-case spend: ${ceiling:.2f} (+ at most one task's cap if the last run overshoots)")

    if args.dry_run or not todo:
        print("\nDry run — nothing executed." if args.dry_run else "\nNothing to do.")
        return
    if paid and not args.yes:
        if not sys.stdin.isatty():
            sys.exit("Refusing to spend money non-interactively. Re-run with --yes to confirm.")
        if input("\nThis calls a paid model API. Proceed? [y/N] ").strip().lower() not in {"y", "yes"}:
            sys.exit("Aborted.")

    agent = _build_agent(args)
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "_run.json").write_text(json.dumps({
        "adapter": args.adapter, "model": args.model, "provider": args.provider,
        "agent_version": _agent_version(args), "tools": args.pi_tools if args.adapter == "pi" else None,
        "thinking": args.thinking, "repeat": args.repeat,
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, indent=2), encoding="utf-8")

    spent = 0.0
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "JUDGE-FAIL": 0}
    for task_file in todo:
        if spent >= args.budget_usd:
            print(f"\nBudget of ${args.budget_usd:.2f} reached (spent ${spent:.4f}) — stopping suite.")
            break
        result = run_task(
            load_task(task_file), agent, results_dir=results_dir, repeat=args.repeat,
            budget_left_usd=args.budget_usd - spent, keep_workspace=args.keep_workspaces,
        )
        spent += sum(run_cost(r) for r in result.get("runs", [result]))
        jr = result.get("judge_result") or {}
        status = "ERROR" if result.get("error") else {1: "PASS", 0: "FAIL"}.get(jr.get("success"), "JUDGE-FAIL")
        counts[status] += 1
        traj = result.get("trajectory") or {}
        print(f"[{status:10}] {result['task_id']} ${float(result.get('cost_usd') or 0):.4f} "
              f"{len(traj.get('tool_calls', []))} calls — {jr.get('reasoning', result.get('error', ''))}")

    print(f"\nDone: {counts['PASS']} passed, {counts['FAIL']} failed, {counts['ERROR']} errored. "
          f"Spent ${spent:.4f} this invocation.")
    out = results_dir / "report.md"
    write_report(results_dir, out, adapter_name=args.adapter)
    print(f"Report written to {out}")


def cmd_report(args: argparse.Namespace) -> None:
    from agent_mark.harness.report import write_report

    results_dir = Path(args.results_dir)
    out = results_dir / "report.md"
    write_report(results_dir, out)
    print(f"Report written to {out}")


# --------------------------------------------------------------------------- parser

def _add_selection_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--task", metavar="TASK_ID", help="Run a single task by ID (e.g. coding_001)")
    p.add_argument("--suite", metavar="NAME", help="Task suite (coding, gmail, github, notion) or difficulty")
    p.add_argument("--all", action="store_true", help="Run every task")
    p.add_argument("--tasks", metavar="DIR", help="Use your own task directory instead of the bundled tasks")


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent-mark", description="Evaluation harness for tool-using AI agents")
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="Mock run end-to-end (no API keys, $0)")
    demo.add_argument("--output", metavar="DIR")

    lst = sub.add_parser("list", help="List task suites")
    lst.add_argument("--tasks", metavar="DIR")

    val = sub.add_parser("validate", help="Check workspace tasks with reference solutions ($0)")
    val.add_argument("--tasks", metavar="DIR")
    val.add_argument("--suite", metavar="NAME")

    run = sub.add_parser("run", help="Run tasks against an agent")
    run.add_argument("--adapter", default="pi",
                     help="pi | command | simple | trustclaw | mock | module.path:ClassName (default: pi)")
    _add_selection_args(run)
    g = run.add_argument_group("model")
    g.add_argument("--model", help="Model id, e.g. claude-haiku-5-5")
    g.add_argument("--provider", help="Provider name (pi built-ins: anthropic, openai, openrouter, ...)")
    g.add_argument("--base-url", default=os.environ.get("AGENT_MARK_BASE_URL"),
                   help="OpenAI-compatible endpoint, e.g. a LiteLLM proxy (env: AGENT_MARK_BASE_URL)")
    g.add_argument("--api-key-env", default="OPENAI_API_KEY",
                   help="Name of the env var holding the key for --base-url (default: OPENAI_API_KEY)")
    g.add_argument("--price-in", type=float, help="$ per 1M input tokens (auto-detected from LiteLLM)")
    g.add_argument("--price-out", type=float, help="$ per 1M output tokens (auto-detected from LiteLLM)")
    g.add_argument("--thinking", choices=["off", "minimal", "low", "medium", "high", "xhigh", "max"])
    g = run.add_argument_group("agent")
    g.add_argument("--pi-binary", default=os.environ.get("PI_BINARY", "pi"), help="Path to pi (env: PI_BINARY)")
    g.add_argument("--pi-tools", default="read,bash,edit,write,grep,find,ls", help="Tools exposed to pi")
    g.add_argument("--agent-cmd", help='For --adapter command: e.g. "my-agent -p {prompt}"')
    g = run.add_argument_group("spend guards")
    g.add_argument("--budget-usd", type=float, default=1.0, help="Stop the suite once this much is spent (default 1.0)")
    g.add_argument("--max-cost-per-task", type=float, default=0.25, help="Kill a run above this $ (default 0.25)")
    g.add_argument("--max-tokens-per-task", type=int, default=300_000, help="Kill a run above this many tokens")
    g.add_argument("--timeout", type=float, default=300.0, help="Kill a run after this many seconds")
    g.add_argument("--dry-run", action="store_true", help="Show the plan and worst-case spend, run nothing")
    g.add_argument("--yes", "-y", action="store_true", help="Skip the confirmation prompt before paid runs")
    g = run.add_argument_group("output")
    g.add_argument("--repeat", type=int, default=1, metavar="K", help="Run each task K times → pass^k")
    g.add_argument("--output", metavar="DIR", help="Results dir (default: results/<adapter>-<model>)")
    g.add_argument("--force", action="store_true", help="Re-run tasks that already have results")
    g.add_argument("--keep-workspaces", action="store_true", help="Keep agent workspaces for inspection")

    rep = sub.add_parser("report", help="Regenerate report.md for a results directory")
    rep.add_argument("results_dir")

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    if args.command in {"demo", "run"} and sys.stdout.isatty():
        print(BANNER)
    {"demo": cmd_demo, "list": cmd_list, "validate": cmd_validate, "run": cmd_run, "report": cmd_report}[
        args.command
    ](args)


if __name__ == "__main__":
    main()
