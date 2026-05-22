# agent-mark

A framework-agnostic evaluation harness for tool-using AI agents. The first target is
TrustClaw (Composio's open-source personal agent), but the harness must work for any
agent that takes a prompt and returns a trajectory of tool calls.

This file is the source of truth for Claude Code working on this repo. Read it fully
before making changes.

## Project goal

Produce a small, sharp evaluation harness that:
- Runs ~20 real tasks against a tool-using agent
- Scores each run on 5 dimensions (task success, tool correctness, efficiency, latency, cost)
- Outputs a markdown report with aggregates and example trajectories
- Includes at least 2 working adapters (TrustClaw, plus one fallback)

This is a weekend project (~15 hours total budget). Optimize for shipping a clean,
runnable artifact with real results, not for completeness.

## What this is NOT

- Not a TrustClaw fork. TrustClaw is one adapter target, not the subject.
- Not a generic LLM eval (no HumanEval, MMLU, etc). This is specifically about
  tool-using agents.
- Not a red-team / injection harness. Just standard capability evaluation.
- Not a leaderboard service. Single-run, local-first, markdown output.

## Architecture

```
agent-mark/
├── CLAUDE.md              # this file
├── README.md              # user-facing, written last
├── pyproject.toml         # uv or poetry, Python 3.11+
├── run.py                 # CLI entrypoint
├── adapters/
│   ├── base.py            # Agent protocol + Trajectory/ToolCall dataclasses
│   ├── trustclaw.py       # HTTP client for local TrustClaw instance
│   └── simple.py          # fallback: minimal LangGraph+Composio agent
├── harness/
│   ├── runner.py          # runs one task end-to-end against an adapter
│   ├── judge.py           # Gemini-based rubric judge for task success
│   ├── scorer.py          # programmatic checks on trajectory
│   └── report.py          # aggregates results → markdown
├── tasks/
│   ├── gmail/
│   ├── github/
│   ├── linear/
│   └── slack/
└── results/               # generated markdown reports (gitignored except .gitkeep)
```

## Core contract: the Trajectory dataclass

Every adapter MUST return this shape. The runner, scorer, and judge only ever see
`Trajectory`. This is what makes the harness framework-agnostic.

```python
@dataclass
class ToolCall:
    name: str           # e.g. "GMAIL_FETCH_EMAILS"
    args: dict          # arguments passed to the tool
    result: dict | None # tool response, if available
    latency_ms: float

@dataclass
class Trajectory:
    prompt: str
    tool_calls: list[ToolCall]
    final_response: str
    total_latency_ms: float
    input_tokens: int
    output_tokens: int
```

If an adapter can't fill a field (e.g. token counts not exposed), use 0 and document
it in the adapter's docstring. Do not silently fabricate values.

## Task YAML format

```yaml
id: gmail_001
toolkit: gmail
difficulty: easy        # easy | medium | hard
prompt: "Find emails from notifications@github.com in the last 7 days"
expected_tools:
  - GMAIL_FETCH_EMAILS
min_tool_calls: 1
max_tool_calls: 3
success_rubric: |
  Response should list GitHub notification emails with sender, subject, and date.
```

Use exact Composio action names in `expected_tools`. Check Composio docs; don't
guess. If unsure, leave the list empty and rely on the judge.

## Scoring dimensions

1. **Task success** — 0 or 1, from Gemini judge using the rubric
2. **Tool correctness** — 1 if any tool in `expected_tools` was called, else 0
3. **Efficiency** — `min_tool_calls / actual_tool_calls`, capped at 1.0
4. **Latency** — `total_latency_ms`
5. **Cost** — `input_tokens + output_tokens` (treat as proxy; we're not pricing here)

Aggregate per toolkit and per difficulty in the report.

## Judge

Gemini 2.5 Flash. Force JSON output. Retry once on parse failure, then mark as
judge-failed (do NOT default to success or failure — log it).

```
JUDGE_PROMPT = """Evaluate this agent response.

Task: {prompt}
Rubric: {rubric}
Agent's final response: {response}

Respond with JSON only:
{{"success": 0 or 1, "reasoning": "one sentence"}}
"""
```

Before trusting the judge, hand-label 5 trajectories and confirm agreement >= 4/5.
If lower, iterate on the rubric prompt before running the full suite.

## Adapters

### trustclaw.py
TrustClaw runs as a Next.js app on localhost:3000. The agent endpoint is a tRPC
or REST route — inspect the TrustClaw repo to find it. Adapter:
- Takes a `prompt: str`, returns `Trajectory`
- Captures tool calls from the response (TrustClaw exposes a ToolLoopAgent loop;
  find where it logs/yields tool invocations)
- Measures wall-clock latency around the HTTP call
- If TrustClaw doesn't expose token counts, set to 0 and note this in docstring

### simple.py
A ~50-line LangGraph or plain-loop agent using Composio's Python SDK directly.
This is the fallback if TrustClaw setup blows the time budget. It also serves as
a baseline for comparison in the final report.

## Tasks (20 total)

5 per toolkit × 4 toolkits = 20 tasks.

Difficulty distribution per toolkit:
- 2 easy (single tool call, one toolkit)
- 2 medium (2-3 tool calls, one toolkit)
- 1 hard (cross-toolkit OR multi-step reasoning)

Toolkits: gmail, github, linear, slack. Pick actions TrustClaw supports — check
its Composio integrations before writing tasks.

When writing tasks, the prompt must be answerable with READ-ONLY operations
where possible. Avoid tasks that send emails / create issues during eval runs
unless using dedicated test accounts. Mutation tasks are valuable but require
sandbox setup; flag them in the YAML with `mutates: true` and document the
test account in README.

## Build order (do not deviate)

1. **base.py** — Trajectory + ToolCall + Agent protocol. ~30 lines.
2. **simple.py** — minimal Composio agent, returns a real Trajectory.
   Test with one hardcoded prompt before moving on.
3. **runner.py** — load task YAML, invoke adapter, return raw trajectory.
4. **scorer.py** — programmatic scores on a Trajectory.
5. **judge.py** — Gemini rubric judge. Validate against 5 hand-labels.
6. **One real end-to-end run** with one task and simple.py. Must work before
   writing more tasks.
7. **Write 20 task YAMLs.**
8. **trustclaw.py adapter.** Reuses runner/scorer/judge unchanged.
9. **report.py** — aggregate runs into markdown.
10. **Run full suite against simple.py, then TrustClaw.** Compare.
11. **README** with results table, methodology, and a "what I learned" section.

If TrustClaw setup fails or takes more than 3 hours, ship the harness with
simple.py results only and note TrustClaw integration as future work. The
harness is the artifact.

## Style conventions

- Python 3.11+, type hints everywhere, dataclasses over dicts for structured data.
- Pydantic only if validating external input (task YAML loading). Otherwise plain dataclasses.
- No async unless an adapter needs it. The runner is sequential — we're running 20 tasks, not 20,000.
- Logging via stdlib `logging`, INFO by default, DEBUG with `--verbose` flag.
- Errors during a task run must NOT crash the suite. Catch, log, mark task as
  errored in the report, continue.
- One file per concern. Don't pre-factor. ~200 lines per file is fine.

## What NOT to build

- No web UI, no dashboard, no FastAPI server. CLI + markdown only.
- No database. Results are JSON files in `results/`, aggregated into markdown.
- No retry logic on agent calls beyond the judge. If the agent fails, that's a data point.
- No multi-model judging or ensemble judging. One judge, validated by hand.
- No CI/CD. This is a weekend project.

## Submission plan (out of scope for code, but informs design)

When done, the README's "Results" section is the headline. It must include:
- Aggregate scores per toolkit
- Aggregate scores per difficulty
- A "what I learned" section with 3-5 concrete observations (e.g.
  "agent over-calls search tools by 2x on Gmail", "fails 60% of cross-toolkit tasks")
- 2-3 example trajectories (one success, one failure) in collapsible details blocks

The README is the marketing surface. Treat it accordingly.

## Things Claude Code should ask before doing

- Adding any dependency beyond: `pyyaml`, `pydantic`, `google-generativeai`, `httpx`, `composio-core`, `langgraph` (only for simple.py)
- Changing the Trajectory contract once it exists
- Adding more than the 4 listed toolkits
- Implementing anything in the "What NOT to build" section
- Writing more than 20 tasks (more tasks = more time spent, not better signal)

## Things Claude Code should do without asking

- Add type hints
- Fix obvious bugs as encountered
- Improve docstrings on functions being edited
- Add `__init__.py` files where missing
- Add `.gitignore` entries for results, .env, venv, __pycache__
