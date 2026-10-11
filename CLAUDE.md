# agent-mark

A framework-agnostic evaluation harness for tool-using AI agents, shipped as an
installable CLI (`agent-mark`) so anyone can benchmark their own agent. v2's primary
target is **pi** (pi_agent_rust, the Rust port of the pi coding agent) on a
deterministic coding suite; v1's Composio suites (gmail/github/notion) and
TrustClaw/simple adapters remain supported.

This file is the source of truth for Claude Code working on this repo. Read it fully
before making changes.

## Money rule (most important)

The owner pays for model calls through a LiteLLM proxy with limited credits.
**Never run anything that calls a paid model without asking first.** That includes
`agent-mark run` with any adapter except `mock`, the Gemini judge, and the `simple`
adapter. Free things you may run freely: `agent-mark list|validate|demo|run --dry-run`,
the unit tests (they use `tests/fake_llm.py`), and metadata calls like `/v1/models` or
`/model/info`. When proposing a paid run, state the model, task count, and caps.

## Project goal

- Score agents on: task success, tool correctness, efficiency, tool error rate,
  latency, real $ cost, cost per solved task, and pass^k with `--repeat`.
- Deterministic coding suite graded by hidden tests (no LLM judge).
- Plug in any agent: built-in adapters, `--adapter command` for any CLI agent, or
  `--adapter module:Class` for a Python adapter.
- Markdown report per run in `results/<adapter>-<model>/report.md`.

## Architecture

```
agent-mark/
├── CLAUDE.md
├── README.md                   # user-facing; the "marketing surface"
├── pyproject.toml              # hatchling; core deps: pyyaml, httpx; extra: [composio]
├── run.py                      # shim → agent_mark.cli:main
├── agent_mark/
│   ├── cli.py                  # demo | list | validate | run | report
│   ├── adapters/
│   │   ├── base.py             # Trajectory / ToolCall / Agent protocol
│   │   ├── pi.py               # pi_agent_rust via `pi -p --mode json`
│   │   ├── command.py          # any CLI agent; optional JSON-lines event protocol
│   │   ├── simple.py           # Claude + Composio reference agent
│   │   ├── trustclaw.py        # HTTP/SSE client for a local TrustClaw
│   │   └── mock.py             # canned Gmail trajectories for the $0 demo
│   ├── harness/
│   │   ├── runner.py           # load task → run adapter → score → decide success
│   │   ├── workspace.py        # temp repo copy, hidden-test verify, task validation
│   │   ├── scorer.py           # programmatic path metrics
│   │   ├── judge.py            # Gemini rubric judge (non-workspace tasks only)
│   │   └── report.py           # JSON results → markdown
│   ├── fixtures/               # synthetic trajectories (scorer dev only, never results)
│   └── tasks/<suite>/<id>.yaml (+ <id>/repo, hidden_tests, solution for workspace tasks)
├── tests/                      # unittest; fake_llm.py = scripted OpenAI-compatible server
└── results/                    # gitignored except .gitkeep
```

## Core contract: Trajectory

```python
@dataclass
class ToolCall:
    name: str
    args: dict
    result: dict | None
    latency_ms: float

@dataclass
class Trajectory:
    prompt: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    final_response: str = ""
    total_latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    stop_reason: str = ""   # e.g. "stop", "budget_exceeded", "token_limit", "timeout"
```

Adapters implement `run(prompt, *, workdir: Path | None = None) -> Trajectory`.
`workdir` is passed only for workspace tasks. If an adapter can't fill a field, use the
default and document it in the adapter docstring. Never fabricate values.

## Task YAML

```yaml
id: coding_001
toolkit: coding            # = suite directory name
difficulty: easy           # easy | medium | hard
prompt: "..."
workspace: coding_001      # optional → workspace task (dir next to the YAML)
expected_tools: [edit, write, hashline_edit]   # any-of; exact tool names
min_tool_calls: 2
max_tool_calls: 8
# workspace-only, optional:
expected_answer: 'ANSWER:\s*20'   # regex on final response
must_not_modify: true              # any file change fails
oracle_answer: "ANSWER: 20"        # used by `agent-mark validate`
verify: "{python} -m unittest ..." # default runs hidden_tests with unittest
# non-workspace:
success_rubric: |
  ...
```

Every workspace task needs `repo/`, and `hidden_tests/` and/or `expected_answer`, plus
`solution/` (or `oracle_answer`). `agent-mark validate` must pass: the untouched repo
fails and the reference solution passes. Hidden tests use stdlib `unittest` only.

## Judge (non-workspace tasks)

Gemini 2.5 Flash, forced JSON, one retry, then `judge-failed` (never defaulted).
Imported lazily so coding runs don't need google-genai.

## Style conventions

- Python 3.11+, type hints everywhere, dataclasses over dicts for structured data.
- No async unless an adapter needs it. The runner is sequential.
- Logging via stdlib `logging`; WARNING by default, DEBUG with `--verbose`.
- Errors during a task run must NOT crash the suite. Catch, log, mark errored, continue.
- Harness failures (missing key, binary not found) are errors; agent failures are FAILs.
- One file per concern. ~200–400 lines per file is fine.
- Tests: `PI_BINARY=/path/to/pi python -m unittest discover -s tests -t .` must pass.

## What NOT to build

- No web UI, dashboard, server, or database. CLI + JSON + markdown only.
- No retry logic on agent calls. If the agent fails, that's a data point.
- No multi-model or ensemble judging.

## Things Claude Code should ask before doing

- Anything that spends money (see Money rule)
- Adding a runtime dependency beyond `pyyaml`, `httpx` (core) or the `[composio]` extra
- Changing the Trajectory contract or the adapter protocol
- Publishing to PyPI or any other public registry
- Implementing anything in "What NOT to build"

## Things Claude Code should do without asking

- Add type hints, fix obvious bugs, improve docstrings on edited functions
- Add `__init__.py` files where missing
- Add `.gitignore` entries for results, .env, venv, __pycache__
- Add or fix tests that run at $0
