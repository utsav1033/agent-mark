"""
agent-mark CLI.

Usage:
    agent-mark demo
    agent-mark run --adapter trustclaw --task gmail_001
    agent-mark run --adapter trustclaw --toolkit gmail
    agent-mark run --adapter simple --all
    agent-mark run --report --adapter trustclaw
    agent-mark run --adapter trustclaw --toolkit gmail --verbose
    agent-mark run --adapter mock --all --output /tmp/myresults
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Package directory — tasks are bundled here so this path is valid whether
# running from source or from a pip-installed wheel.
_PKG_DIR = Path(__file__).parent

# Project root — only used to load .env when running from source.
# When installed, there is no project root .env; callers must set env vars
# in their shell. _load_dotenv() silently skips if the file doesn't exist.
_ROOT = _PKG_DIR.parent

# tasks/ is bundled inside the package so it survives pip install.
TASKS_DIR = _PKG_DIR / "tasks"


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
    elif adapter == "mock":
        from adapters.mock import MockAgent
        return MockAgent()
    raise ValueError(f"Unknown adapter: {adapter!r}. Choose 'simple', 'trustclaw', or 'mock'.")


def cmd_demo(results_dir: Path) -> None:
    """Run the mock adapter against all Gmail tasks and print a report. No API keys needed."""
    from harness.runner import load_task, run_task
    from harness.report import write_report
    from adapters.mock import MockAgent

    print("\nRunning demo against Gmail tasks (no API keys required)...\n")

    agent = MockAgent()
    task_files = sorted((TASKS_DIR / "gmail").glob("*.yaml"))

    if not task_files:
        print(f"ERROR: No Gmail task files found under {TASKS_DIR / 'gmail'}", file=sys.stderr)
        sys.exit(1)

    passed = failed = 0

    for task_file in task_files:
        task = load_task(task_file)
        result = run_task(task, agent, results_dir=results_dir)
        jr = result.get("judge_result") or {}
        success = jr.get("success")
        status = "PASS" if success == 1 else "FAIL"
        if success == 1:
            passed += 1
        else:
            failed += 1
        print(f"[{status:4}] {result['task_id']} — {jr.get('reasoning', '')}")

    print(f"\nDone: {passed} passed, {failed} failed out of {len(task_files)} tasks.")

    out = results_dir / "report_mock.md"
    write_report(results_dir, out, adapter_name="mock")
    print(f"Report written to {out}")


def cmd_run(args: argparse.Namespace, results_dir: Path) -> None:
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

    repeat = getattr(args, "repeat", 1)
    if repeat > 1:
        print(f"Repeating each task {repeat}x — will compute pass^k curve in report.\n")

    for task_file in task_files:
        task = load_task(task_file)
        result = run_task(task, agent, results_dir=results_dir, repeat=repeat)

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

    if args.report or auto_report:
        cmd_report(args, results_dir)


def cmd_report(args: argparse.Namespace, results_dir: Path) -> None:
    from harness.report import write_report

    out = results_dir / f"report_{args.adapter}.md"
    write_report(results_dir, out, adapter_name=args.adapter)
    print(f"Report written to {out}")


def _add_run_args(p: argparse.ArgumentParser) -> None:
    """Attach the shared run/report flags to a parser."""
    p.add_argument(
        "--adapter",
        choices=["simple", "trustclaw", "mock"],
        default="simple",
        help="Which agent adapter to use (default: simple)",
    )
    p.add_argument("--task", metavar="TASK_ID", help="Run a single task by ID (e.g. gmail_001)")
    p.add_argument(
        "--toolkit",
        choices=["gmail", "github", "notion"],
        help="Run all tasks for one toolkit",
    )
    p.add_argument(
        "--suite",
        metavar="NAME",
        help="Run a named suite: toolkit name or difficulty (easy, medium, hard)",
    )
    p.add_argument("--all", action="store_true", help="Run all tasks and generate report")
    p.add_argument("--report", action="store_true", help="Generate markdown report after running (or standalone)")
    p.add_argument("--repeat", type=int, default=1, metavar="K", help="Run each task K times and compute pass^k (default: 1)")
    p.add_argument("--output", metavar="DIR", default=None, help="Directory for results and report (default: ./results)")
    p.add_argument("--verbose", action="store_true", help="Enable DEBUG logging")


def main() -> None:
    print(BANNER)
    parser = argparse.ArgumentParser(
        prog="agent-mark",
        description="Evaluation harness for tool-using AI agents",
    )
    subparsers = parser.add_subparsers(dest="command")

    # demo subcommand — no API keys needed
    demo_parser = subparsers.add_parser("demo", help="Run mock Gmail suite end-to-end (no API keys needed)")
    demo_parser.add_argument("--output", metavar="DIR", default=None, help="Directory for results and report (default: ./results)")
    demo_parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging")

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Run tasks against a real adapter")
    _add_run_args(run_parser)

    # Support legacy flat usage: agent-mark --adapter trustclaw --task gmail_001
    _add_run_args(parser)

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    # Resolve output directory — always CWD-relative by default, never inside
    # the package installation directory.
    results_dir = Path(args.output) if args.output else Path.cwd() / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "demo":
        cmd_demo(results_dir)
        return

    if args.report and not (args.task or args.all or args.toolkit or args.suite):
        cmd_report(args, results_dir)
        return

    cmd_run(args, results_dir)


if __name__ == "__main__":
    main()
