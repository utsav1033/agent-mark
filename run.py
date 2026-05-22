"""
agent-mark CLI entrypoint.

Usage examples:
    # Run all 20 tasks with the simple adapter
    python run.py --adapter simple --all

    # Run a single task
    python run.py --adapter simple --task gmail_001

    # Run all tasks for one toolkit
    python run.py --adapter simple --toolkit gmail

    # Run with TrustClaw adapter
    python run.py --adapter trustclaw --all

    # Generate a markdown report from existing results
    python run.py --report --adapter simple

    # Verbose logging
    python run.py --adapter simple --all --verbose
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


def _discover_tasks(toolkit: str | None = None) -> list[Path]:
    """Return all task YAML paths, optionally filtered by toolkit."""
    if toolkit:
        return sorted((TASKS_DIR / toolkit).glob("*.yaml"))
    return sorted(TASKS_DIR.rglob("*.yaml"))


def _build_agent(adapter: str, toolkit: str | None):
    if adapter == "simple":
        from adapters.simple import SimpleAgent
        return SimpleAgent(toolkit=toolkit)
    elif adapter == "trustclaw":
        from adapters.trustclaw import TrustClawAgent
        return TrustClawAgent()
    else:
        raise ValueError(f"Unknown adapter: {adapter!r}. Choose 'simple' or 'trustclaw'.")


def cmd_run(args: argparse.Namespace) -> None:
    from harness.runner import load_task, run_task

    # Determine which task files to run
    if args.task:
        # Search for the task YAML by ID
        matches = list(TASKS_DIR.rglob(f"{args.task}.yaml"))
        if not matches:
            print(f"ERROR: Task '{args.task}' not found under {TASKS_DIR}", file=sys.stderr)
            sys.exit(1)
        task_files = matches[:1]
    elif args.all or args.toolkit:
        task_files = _discover_tasks(toolkit=args.toolkit if not args.all else None)
    else:
        print("ERROR: Specify --task TASK_ID, --toolkit TOOLKIT, or --all", file=sys.stderr)
        sys.exit(1)

    if not task_files:
        print("No task files found.", file=sys.stderr)
        sys.exit(1)

    agent = _build_agent(args.adapter, toolkit=args.toolkit if not args.all else None)
    log = logging.getLogger(__name__)

    passed = 0
    failed = 0
    errored = 0

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
    parser.add_argument("--toolkit", choices=["gmail", "github", "linear", "slack"], help="Run all tasks for one toolkit")
    parser.add_argument("--all", action="store_true", help="Run all 20 tasks")
    parser.add_argument("--report", action="store_true", help="Generate markdown report after running (or standalone)")
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    # Standalone --report (no task run)
    if args.report and not (args.task or args.all or args.toolkit):
        cmd_report(args)
        return

    cmd_run(args)


if __name__ == "__main__":
    main()
