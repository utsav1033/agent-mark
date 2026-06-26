# agent-mark

An evaluation harness for tool-using AI agents. It runs an agent against a set of
tasks and scores not just whether the task succeeded, but *how* the agent got there —
the tools it called, the path it took, the latency and token cost — for any agent
whose tool calls are observable.

> **Status — honest version.** This is an early harness. The architecture, scoring,
> and pipeline are built and validated end-to-end. **One adapter has been run against
> a live agent (TrustClaw on real Gmail); the trajectory-level examples below are
> synthetic fixtures used to build and test the scorer, not observed agent runs.**
> Live simple-adapter benchmarks are the next step. Everything is labelled real vs
> synthetic so there's no ambiguity.

---

<img width="896" height="404" alt="agent-mark running the TrustClaw adapter against live Gmail" src="https://github.com/user-attachments/assets/a6284cbf-413d-42d5-864c-49fbba320472" />

*TrustClaw adapter running against a live Gmail inbox.*

---

## Two adapters, two kinds of visibility

agent-mark ships two adapters, and they expose very different information. This gap is
the central idea of the project.

**simple** runs a Claude model directly with Composio tools. Every tool call passes
through your code, so the harness captures the full trajectory — which tools were
called, with what arguments, what came back, how long each step took. You can score
task success, tool correctness, efficiency, latency, and token cost.

**trustclaw** sends the prompt to a local [TrustClaw](https://github.com/ComposioHQ/trustclaw)
instance over HTTP and reads a streaming text response. TrustClaw runs its Composio
tool loop server-side before streaming begins, so no tool events appear in the output.
The harness can only observe the final answer and total latency. Tool correctness and
efficiency are N/A — not because TrustClaw performs badly, but because the information
is not observable from outside.

| Metric | simple | trustclaw |
|---|---|---|
| Task success | ✓ | ✓ |
| Tool correctness | ✓ | N/A — server-side |
| Efficiency | ✓ | N/A — server-side |
| Latency | ✓ | ✓ |
| Full trajectory | ✓ | N/A — server-side |
| Token counts | ✓ | N/A — not exposed |

The simple adapter exposes the path, so we can score how the agent got there. TrustClaw
exposes only the end result, so we can confirm what it achieved but not how. This
observable-vs-black-box gap is the central tradeoff when evaluating agents you don't
own: you gain a realistic, unmodified target, but you lose interpretability.

---

## Results

### TrustClaw adapter — real run (live Gmail)

The only live agent run so far. Outcome and latency are real; tool correctness and
efficiency are N/A because TrustClaw's tool loop is not observable.

| Toolkit | Tasks | Success | Tool Correctness | Efficiency | Avg Latency |
|---------|-------|---------|------------------|------------|-------------|
| gmail   | 5     | 60%     | N/A              | N/A        | 24.3s       |

| Difficulty | Tasks | Success | Avg Latency |
|------------|-------|---------|-------------|
| easy       | 2     | 100%    | 18.7s       |
| medium     | 2     | 50%     | 30.8s       |
| hard       | 1     | 0%      | 22.5s       |

### simple adapter — benchmark pending

Not yet run against live credentials. The harness supports it fully; this table is a
placeholder until a clean live run is done.

| Toolkit | Tasks | Success | Tool Correctness | Efficiency | Avg Latency | Avg Tokens |
|---------|-------|---------|------------------|------------|-------------|------------|
| gmail   | —     | —       | —                | —          | —           | —          |

To populate it:

```bash
agent-mark run --adapter simple --toolkit gmail
```

---

## How it works

Every adapter implements one method — `run(prompt) -> Trajectory` — and the rest of
the pipeline works unchanged. A `Trajectory` captures the prompt, every tool call made,
the final response, latency, and token counts. The runner loads a task YAML, invokes
the adapter, then passes the trajectory to the scorer (programmatic checks) and the
judge (Gemini 2.5 Flash with a per-task rubric). Results are saved as JSON and
aggregated into a markdown report.

```python
@dataclass
class Trajectory:
    prompt: str
    tool_calls: list[ToolCall]   # name, args, result, latency_ms
    final_response: str
    total_latency_ms: float
    input_tokens: int
    output_tokens: int
```

### Scoring, in detail

Each run is scored on five dimensions, by two different mechanisms:

- **Task success** (0/1) — decided by the **judge** (Gemini 2.5 Flash) against a
  per-task rubric. Judges the *outcome*.
- **Tool correctness** (0/1) — **programmatic**. Each task declares expected tools;
  the scorer checks the trajectory's actual tool calls. *Current check is coarse: 1 if
  any expected tool was called. A stricter version comparing the full expected
  sequence is planned.*
- **Efficiency** (0–1) — **programmatic**. `min_tool_calls / actual_tool_calls`.
  Catches wasteful or redundant paths.
- **Latency** (ms) and **cost** (input + output tokens) — measured, reported.

The judge grades the outcome; programmatic checks grade the path. Outcome and path are
scored separately — that separation is the point. An agent can succeed at the task
while taking a wrong or wasteful path, and only the path metrics catch that.

For the TrustClaw adapter, tool correctness and efficiency are N/A: its tool calls are
not exposed in the SSE stream, so the path cannot be inspected. This is a visibility
limitation, not a performance failure.

---

## Quick start

```bash
git clone https://github.com/utsav1033/agent-mark && cd agent-mark
pip install -e .
cp .env.example .env        # fill in ANTHROPIC_API_KEY and COMPOSIO_API_KEY
python run.py --adapter simple --task gmail_001
```

---

## Adapters

- **simple** — Anthropic + Composio Python SDK. Reference implementation. Token counts
  and tool calls fully visible.
- **trustclaw** — HTTP/SSE client for a local
  [TrustClaw](https://github.com/ComposioHQ/trustclaw) instance.
- **adding your own** — implement the `Agent` protocol (~30 lines). If it returns a
  `Trajectory`, it works.

```python
class YourAgent:
    def run(self, prompt: str) -> Trajectory:
        ...
```

Because the scorer and report are adapter-agnostic, adding a new agent or a new toolkit
(e.g. GitHub, with its destructive actions and multi-step workflows) is mostly task
authoring, not pipeline changes.

---

## Methodology

**Tasks.** 5 tasks per toolkit across 3 difficulty levels: easy (single tool call,
clear expected output), medium (2–3 tool calls, some reasoning), hard (multi-step or
ambiguous constraints). All tasks are read-only — no mutations to live data during
evaluation.

**Judge.** Gemini 2.5 Flash with a per-task rubric, forced JSON output. Retries once on
parse failure. If it cannot produce a valid result after two attempts the task is
marked `judge-failed` and excluded from aggregates rather than defaulting to pass or
fail. LLM judges have known weaknesses (position and verbosity bias, and for safety
tasks they can be fooled by the same input), so judge output is treated as one signal,
not ground truth.

---

## Illustrative examples (synthetic)

> These are **synthetic trajectories**, hand-authored to design and test the scoring
> pipeline — not observed runs of a live agent. They show the *kind* of behavior the
> harness is built to score and the failure modes it's meant to catch. Real
> simple-adapter trajectories will replace these once a live benchmark is run.

<details>
<summary>Example: a passing task — list labels (easy)</summary>

**Prompt:** List my email labels and tell me how many I have.

A clean single-tool-call task: the agent calls a list-labels tool and reports the
count. The kind of task the harness expects to pass reliably, used to confirm the
scorer marks a correct single-call trajectory as success with full tool correctness.

</details>

<details>
<summary>Example: a constraint-interpretation failure — received vs sent (hard)</summary>

**Prompt:** Find emails received in the last 7 days that have attachments. List each
email's subject, sender, and attachment name.

The failure this example models: an agent returns attachments from *all* mail,
including sent items, when the task said *received*. The data retrieval is correct; the
query scope is wrong. This is a **constraint-interpretation failure, not a tool
failure** — exactly the kind of issue task-success-only metrics miss but that a harness
scoring the full trajectory is designed to surface. Used to verify the scorer
distinguishes "wrong tool" from "right tool, wrong scope."

</details>

---

## Status & roadmap

- **Done:** harness architecture, adapter interface, scoring pipeline, Gemini judge,
  markdown reporting; one live adapter (TrustClaw) benchmarked on real Gmail.
- **Next:** live simple-adapter benchmark; stricter tool-correctness (expected-sequence
  match); a second toolkit (GitHub — destructive, multi-step) to stress trajectory and
  reliability scoring; pass^k reliability (consistency across repeated runs); a
  prompt-injection safety suite scored programmatically on tool calls.