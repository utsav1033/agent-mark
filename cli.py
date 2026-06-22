"""
agent-mark CLI.

Usage:
    agent-mark --adapter trustclaw --task gmail_001
    agent-mark --adapter trustclaw --toolkit gmail
    agent-mark --adapter simple --all
    agent-mark --report --adapter trustclaw
    agent-mark --adapter trustclaw --toolkit gmail --verbose
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path


def _load_dotenv() -> None:
    """Load .env from the project root into os.environ (skip already-set vars)."""
    env_file = Path(__file__).parent / ".env"
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

TASKS_DIR = Path(__file__).parent / "tasks"
RESULTS_DIR = Path(__file__).parent / "results"

_LBLUE = "\033[96m"
_RESET = "\033[0m"

BANNER = _LBLUE + r"""
  __ _  __ _  ___ _ __ | |_      _ __ ___   __ _ _ __| | __
 / _` |/ _` |/ _ \ '_ \| __|____| '_ ` _ \ / _` | '__| |/ /
| (_| | (_| |  __/ | | | ||_____| | | | | | (_| | |  |   <
 \__,_|\__, |\___|_| |_|\__|    |_| |_| |_|\__,_|_|  |_|\_\
        |___/

  > test your agent with ease
  > tested on trustclaw and mvp agents powered by composio
""" + _RESET


def _discover_tasks(toolkit: str | None = None) -> list[Path]:
    if toolkit:
        return sorted((TASKS_DIR / toolkit).glob("*.yaml"))
    return sorted(TASKS_DIR.rglob("*.yaml"))


def _discover_suite(name: str) -> list[Path]:
    """
    Resolve --suite <name> to a list of task files.

    Resolution order:
      1. tasks/<name>/ directory exists  -> all YAMLs in that directory
      2. Otherwise                       -> all YAMLs whose difficulty field matches <name>
    """
    toolkit_dir = TASKS_DIR / name
    if toolkit_dir.is_dir():
        files = sorted(toolkit_dir.glob("*.yaml"))
        if files:
            return files

    # Fall back to filtering by difficulty across all tasks
    import yaml
    matched = []
    for path in sorted(TASKS_DIR.rglob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if data.get("difficulty") == name:
                matched.append(path)
        except Exception:
            pass
    return matched


def _build_agent(adapter: str, toolkit: str | None):
    if adapter == "simple":
        from adapters.simple import SimpleAgent
        return SimpleAgent(toolkit=toolkit)
    elif adapter == "trustclaw":
        from adapters.trustclaw import TrustClawAgent
        return TrustClawAgent()
    raise ValueError(f"Unknown adapter: {adapter!r}. Choose 'simple' or 'trustclaw'.")


def cmd_run(args: argparse.Namespace) -> None:
    from harness.runner import load_task, run_task

    auto_report = False

    if args.task:
        matches = list(TASKS_DIR.rglob(f"{args.task}.yaml"))
        if not matches:
            print(f"ERROR: Task '{args.task}' not found under {TASKS_DIR}", file=sys.stderr)
            sys.exit(1)
        task_files = matches[:1]
    elif args.suite:
        task_files = _discover_suite(args.suite)
        if not task_files:
            print(f"ERROR: No tasks found for suite '{args.suite}'", file=sys.stderr)
            sys.exit(1)
        auto_report = True
    elif args.all:
        task_files = _discover_tasks()
        auto_report = True
    elif args.toolkit:
        task_files = _discover_tasks(toolkit=args.toolkit)
    else:
        print("ERROR: Specify --task TASK_ID, --toolkit TOOLKIT, --suite NAME, or --all", file=sys.stderr)
        sys.exit(1)

    if not task_files:
        print("No task files found.", file=sys.stderr)
        sys.exit(1)

    agent = _build_agent(args.adapter, toolkit=args.toolkit if not (args.all or args.suite) else None)

    passed = failed = errored = 0

    for task_file in task_files:
        task = load_task(task_file)
        result = run_task(task, agent, results_dir=RESULTS_DIR)

        jr = result.get("judge_result") or {}
        success = jr.get("success")
        if result.get("error"):
            errored += 1
            status = "ERROR"
        elif success == 1:
            passed += 1
            status = "PASS"
        elif success == 0:
            failed += 1
            status = "FAIL"
        else:
            status = "JUDGE-FAIL"

        print(f"[{status:10}] {result['task_id']} — {jr.get('reasoning', result.get('error', ''))}")

    print(f"\nDone: {passed} passed, {failed} failed, {errored} errored out of {len(task_files)} tasks.")

    if args.report:
        cmd_report(args)


def cmd_report(args: argparse.Namespace) -> None:
    from harness.report import write_report

    out = RESULTS_DIR / f"report_{args.adapter}.md"
    write_report(RESULTS_DIR, out, adapter_name=args.adapter)
    print(f"Report written to {out}")


def main() -> None:
    print(BANNER)
    parser = argparse.ArgumentParser(
        prog="agent-mark",
        description="Evaluation harness for tool-using AI agents",
    )
    parser.add_argument(
        "--adapter",
        choices=["simple", "trustclaw"],
        default="simple",
        help="Which agent adapter to use (default: simple)",
    )
    parser.add_argument("--task", metavar="TASK_ID", help="Run a single task by ID (e.g. gmail_001)")
    parser.add_argument(
        "--toolkit",
        choices=["gmail", "github", "notion"],
        help="Run all tasks for one toolkit",
    )
    parser.add_argument("--all", action="store_true", help="Run all tasks")
    parser.add_argument("--report", action="store_true", help="Generate markdown report after running (or standalone)")
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.report and not (args.task or args.all or args.toolkit):
        cmd_report(args)
        return

    cmd_run(args)


if __name__ == "__main__":
    main()
