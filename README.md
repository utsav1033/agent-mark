# agent-mark

**Benchmark any tool-using AI agent: did it solve the task, how did it get there, how
long did it take, and what did it cost in real dollars.**

agent-mark runs an agent against a suite of tasks and scores the *outcome* and the
*path* separately. A coding agent that fixes the bug in 3 tool calls for $0.004 and one
that fixes it in 19 calls for $0.12 both "pass". agent-mark tells them apart.

- **Deterministic coding suite.** 10 small repos with real bugs and feature requests,
  graded by **hidden tests** the agent never sees. No LLM judge, so grading costs nothing
  and isn't subjective.
- **Bring any agent.** Use a built-in adapter (pi, Claude+Composio, TrustClaw), wrap any
  CLI agent with one flag, or write a 30-line Python adapter.
- **Real cost accounting, with hard spend limits.** Per-task $ and token caps are
  enforced *while the agent runs*. There's a suite-wide budget, `--dry-run`, a
  confirmation prompt before anything paid, and finished tasks are never re-run.
- **$0 self-checks.** Every task is validated against its reference solution. The whole
  pipeline is tested end-to-end against a scripted fake LLM.

---

## Install

```bash
pipx install git+https://github.com/utsav1033/agent-mark      # or: uv tool install git+...
agent-mark list        # show the bundled task suites
agent-mark validate    # prove every coding task is sound ($0)
agent-mark demo        # mock end-to-end run with a report ($0)
```

The core install depends only on `pyyaml` and `httpx`. The LLM-judged Composio suites
need `pipx install "agent-mark[composio] @ git+https://github.com/utsav1033/agent-mark"`.

---

## Benchmark pi (Rust coding agent)

[pi_agent_rust](https://github.com/Dicklesworthstone/pi_agent_rust) is a Rust port of
Mario Zechner's pi coding agent. agent-mark runs it headless (`pi -p --mode json`)
inside a scratch copy of each task repo. It reads pi's event stream to capture every
tool call (name, args, output, error flag, latency) plus exact token usage and $ cost.

```bash
# 1. See the plan and the worst-case spend. Runs nothing.
agent-mark run --adapter pi --model claude-haiku-5-5 \
  --base-url "$LITELLM_BASE_URL/v1" --api-key-env LITELLM_API_KEY \
  --suite coding --dry-run

# 2. Smoke-test a single task with a 10-cent ceiling.
agent-mark run --adapter pi --model claude-haiku-5-5 \
  --base-url "$LITELLM_BASE_URL/v1" --api-key-env LITELLM_API_KEY \
  --task coding_001 --budget-usd 0.10

# 3. Run the full suite (tasks already done in step 2 are skipped, not re-paid).
agent-mark run ... --suite coding --budget-usd 1
```

- **`--base-url`** points at any OpenAI-compatible endpoint (a LiteLLM proxy, vLLM, …).
  For a LiteLLM proxy, prices are fetched automatically from its `/model/info`. For
  pi's built-in providers, use `--provider anthropic|openai|openrouter|…` and pi's own
  price catalog.
- **Isolation.** Each run gets a throwaway `PI_CODING_AGENT_DIR`, and extensions,
  skills, prompt templates and sessions are disabled. Your personal `~/.pi` setup
  never leaks into results.
- **Tools.** The default set is `read,bash,edit,write,grep,find,ls` (change it with
  `--pi-tools`), so web search can't silently add cost or leak the answers.

### Spend guards

| Guard | Default | Behaviour |
|---|---|---|
| `--budget-usd` | `$1.00` | Suite stops once this much is spent |
| `--max-cost-per-task` | `$0.25` | Agent is killed mid-run when it crosses this |
| `--max-tokens-per-task` | `300,000` | Agent is killed mid-run (works even if the model is unpriced) |
| `--timeout` | `300s` | Agent is killed mid-run |
| `--dry-run` | – | Prints the plan and worst-case spend, runs nothing |
| confirmation | on | Paid runs ask `Proceed? [y/N]` unless `--yes` |
| resume | on | Tasks with an existing result are skipped unless `--force` |

A killed run is still recorded and scored as a failure, with its `stop_reason`
(`budget_exceeded`, `token_limit`, `timeout`) shown in the report. Guards are checked
after every model turn, so a run can overshoot its cap by at most one turn.

---

## Benchmark your own agent

**Any CLI agent, zero code.** `{prompt}` is replaced with the task prompt. The command
runs inside the task workspace.

```bash
agent-mark run --adapter command --agent-cmd "my-agent --print {prompt}" --suite coding
```

Black-box, this scores task success and latency. To also score the path and cost,
print JSON lines from your agent (the *agent-mark event protocol*):

```json
{"type": "tool_call", "name": "edit", "args": {"path": "pager.py"}, "result": {"text": "ok"}, "latency_ms": 12}
{"type": "usage", "input_tokens": 1200, "output_tokens": 80, "cost_usd": 0.0004}
{"type": "final", "text": "Fixed both pagination bugs."}
```

**Python adapter.** Return a `Trajectory` and the rest of the pipeline just works:

```python
# my_agent.py  →  agent-mark run --adapter my_agent:MyAgent --suite coding
from pathlib import Path
from agent_mark.adapters.base import Trajectory, ToolCall

class MyAgent:
    def run(self, prompt: str, *, workdir: Path | None = None) -> Trajectory:
        ...  # do the work inside workdir
        return Trajectory(prompt=prompt, tool_calls=[...], final_response="...",
                          total_latency_ms=..., input_tokens=..., output_tokens=..., cost_usd=...)
```

---

## What gets measured

| Metric | How | Why it matters |
|---|---|---|
| **Task success** | Hidden tests pass / expected answer matches (coding). Gemini rubric judge (Composio suites) | Did it work? |
| **Tool correctness** | Called one of the task's expected tools | Right kind of action |
| **Efficiency** | `min_tool_calls / actual_tool_calls` | Wasted steps |
| **Tool error rate** | Share of tool calls that errored (bad edit, failing command) | Sloppy tool use |
| **Within max calls** | Stayed under the task's call ceiling | Flailing |
| **Latency** | Wall clock per task and per tool call | UX |
| **Cost** | Real $ and tokens (incl. cache) per task | Money |
| **Cost per solved task** | Total $ ÷ tasks solved | The number that matters for choosing a model |
| **pass^k** | `--repeat k`: did all k independent runs pass? | Reliability, not luck |

Results are aggregated per suite and per difficulty in `results/<adapter>-<model>/report.md`,
with a per-task table and example trajectories.

---

## Task suites

| Suite | Tasks | Graded by | Needs |
|---|---|---|---|
| `coding` | 10 (3 easy, 4 medium, 3 hard) | hidden unit tests / answer regex | nothing (Python 3.11+) |
| `gmail`, `github`, `notion` | 5 each | Gemini 2.5 Flash rubric judge | Composio + live accounts |

**Coding tasks** cover: an off-by-one pagination bug, implementing a function from its
docstring, fixing a failing test, tracing a config value through code while the README
lies (read-only; any edit fails the task), adding a CLI flag, a discount applied twice
that's only described as a customer complaint, a cross-file rename that keeps a
deprecated alias, an LRU cache with expiry, a CSV parser with quoted fields, and a
free-slot finder with overlapping intervals.

Each task is a directory:

```
coding_006.yaml          prompt, difficulty, expected tools, call bounds
coding_006/repo/         copied to a temp dir; the agent works here
coding_006/hidden_tests/ copied in only after the agent finishes, then run
coding_006/solution/     reference fix; `agent-mark validate` checks it passes
```

`agent-mark validate` proves every task is sound in both directions: the untouched
repo **fails** (the task measures something) and the reference solution **passes**
(the task is solvable). Bring your own suite with `--tasks ./my_tasks`.

---

## Results

### pi (Rust) on the coding suite

> **Pending a live run.** The pipeline is verified end-to-end against the real pi
> binary with a scripted fake model (see *Development*). Real numbers go here after the
> first paid run. No synthetic numbers are presented as results.

| Model | Solved | Cost | Cost / solved | Median latency | Tool err rate |
|---|---|---|---|---|---|
| claude-haiku-5-5 | – | – | – | – | – |

### TrustClaw on Gmail (v1, live run)

<img width="896" height="404" alt="agent-mark running the TrustClaw adapter against live Gmail" src="https://github.com/user-attachments/assets/a6284cbf-413d-42d5-864c-49fbba320472" />

| Difficulty | Tasks | Success | Avg Latency |
|---|---|---|---|
| easy | 2 | 100% | 18.7s |
| medium | 2 | 50% | 30.8s |
| hard | 1 | 0% | 22.5s |

TrustClaw runs its tool loop server-side and streams only the final text, so only
outcome and latency are observable. Tool correctness and efficiency are N/A. That's
a visibility limit, not a performance verdict, and it's the reason the event protocol
above exists.

---

## How it works

```
task YAML ──► runner ──► adapter.run(prompt, workdir) ──► Trajectory
                │                                           │
                │   workspace tasks: hidden tests ◄─────────┤
                │   other tasks:     Gemini judge ◄─────────┤
                ▼                                           ▼
           results/<adapter>-<model>/<task>.json  ◄──  scorer (path metrics)
                ▼
           report.md (per suite / difficulty / task, cost, stop reasons)
```

Every adapter returns the same `Trajectory` (prompt, tool calls, final response,
latency, tokens, `cost_usd`, `stop_reason`). The runner, scorer and report never know
which agent produced it.

**Design choices**
- **Hidden tests over LLM judges for code.** They're deterministic, free, and immune
  to judge bias. Because they're copied in *after* the run, the agent can't read them
  or "fix" them.
- **Outcome and path scored separately.** Success alone hides the 19-call, $0.12 run.
- **Errors never crash the suite.** A broken run is recorded as an error and the suite
  continues. Harness failures (bad API key) are kept distinct from agent failures.

---

## Development

```bash
pip install -e .
PI_BINARY=/path/to/pi python -m unittest discover -s tests -t .
```

The test suite costs $0 and includes:
- unit tests for pi's event parsing and the scorer
- `validate` over every bundled task
- the command adapter driven by a scripted agent
- **the real pi binary end-to-end** against `tests/fake_llm.py`, a scripted
  OpenAI-compatible server. It solves a task, checks the exact $ accounting, and checks
  that the budget and token guards kill a runaway agent. Skipped if no pi binary is
  found.

## Limitations

- Ten coding tasks is a smoke-level benchmark, not SWE-bench. The tasks are small by
  design so a full run costs cents.
- Tool correctness is any-of over expected tools; it doesn't check ordering.
- A single run per task shows capability, not reliability. Use `--repeat` for pass^k.
- Composio suites depend on live account contents and an LLM judge, so they aren't
  reproducible across users. The coding suite is.

MIT licensed.
