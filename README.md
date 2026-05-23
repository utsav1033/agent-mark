# agent-mark

benchmark harness for tool-using AI agents, built to evaluate composio-powered agents in the real world.

---
<img width="896" height="404" alt="ezgif-5ef3e2e1fb8d80a4" src="https://github.com/user-attachments/assets/a6284cbf-413d-42d5-864c-49fbba320472" />

---

## Results

Tested against [TrustClaw](https://github.com/ComposioHQ/trustclaw) — Composio's open-source personal agent.

### By toolkit

| Toolkit | Tasks | Success | Avg Latency |
|---------|-------|---------|-------------|
| gmail   | 5     | 60%     | 24.3s       |

### By difficulty

| Difficulty | Tasks | Success | Avg Latency |
|------------|-------|---------|-------------|
| easy       | 2     | 100%    | 18.7s       |
| medium     | 2     | 50%     | 30.8s       |
| hard       | 1     | 0%      | 22.5s       |

---

## What I learned

**Easy tasks are solved reliably.** Both easy tasks passed — list labels, fetch recent emails. Single tool call, unambiguous output. The agent nails these.

**Medium tasks fail on output consistency, not tool usage.** gmail_004 (count unread emails) fetched the right data but returned two different counts — 49 then ~201 — in the same response. The agent knew how to get the data, not how to present it.

**Hard tasks fail on query interpretation.** gmail_005 asked for *received* emails with attachments. The agent returned sent emails too. It didn't misuse a tool — it misread the task constraint.

**Difficulty scales latency.** Easy tasks averaged 18.7s, medium 30.8s. The extra time is the tool loop, not the model — TrustClaw handles tool execution server-side before streaming begins.

**Tool calls are a black box from the outside.** TrustClaw runs its Composio tool loop before streaming, so no tool events appear in the SSE output. Task success is fully observable; tool usage is not.

---

## How it works

Every adapter implements one method — `run(prompt) -> Trajectory` — and the rest of the pipeline works unchanged. A `Trajectory` captures the prompt, every tool call made, the final response, latency, and token counts. The runner loads a task YAML, invokes the adapter, then passes the trajectory to the scorer (programmatic checks) and the judge (Gemini 2.5 Flash with a per-task rubric). Results are saved as JSON and aggregated into a markdown report.

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

---

## Quick start

```bash
git clone <repo> && cd agent-mark
pip install -e .
cp .env.example .env        # fill in ANTHROPIC_API_KEY and COMPOSIO_API_KEY
python run.py --adapter simple --task gmail_001
```

---

## Adapters

- **simple** — Anthropic + Composio Python SDK. Reference implementation. Token counts and tool calls fully visible.
- **trustclaw** — HTTP/SSE client for a local [TrustClaw](https://github.com/ComposioHQ/trustclaw) instance.
- **adding your own** — implement the `Agent` protocol (~30 lines). If it returns a `Trajectory`, it works.

```python
class YourAgent:
    def run(self, prompt: str) -> Trajectory:
        ...
```

---

## Methodology

**Tasks.** 5 tasks per toolkit across 3 difficulty levels: easy (single tool call, clear expected output), medium (2–3 tool calls, some reasoning), hard (multi-step or ambiguous constraints). All tasks are read-only — no mutations to live data during evaluation.

**Scoring.** Each run is scored on 5 dimensions: task success (0 or 1, from the judge), tool correctness (1 if any expected tool was called), efficiency (min\_tool\_calls / actual), latency (ms), and cost (input + output tokens as proxy). Tool correctness and efficiency are 0 for the TrustClaw adapter because tool calls are not exposed in its SSE stream — this is a known limitation documented in the adapter.

**Judge.** Gemini 2.5 Flash with a per-task rubric, forced JSON output. Retries once on parse failure. If it cannot produce a valid result after two attempts the task is marked `judge-failed` and excluded from aggregates rather than defaulting to pass or fail. Before running the full suite, 5 trajectories were hand-labelled to confirm judge agreement.

---

## Example trajectories

<details>
<summary>Successful task — gmail_001 (easy)</summary>

**Prompt:** List my email labels and tell me how many I have.

**Final response:**

```
Your Email Labels: 15 Total

System Labels:
1. INBOX — 7,169 messages | 6,277 unread
2. UNREAD — 6,278 messages
3. IMPORTANT — 806 messages | 318 unread
4. SENT — 120 messages
5. STARRED — 28 messages
6. DRAFT — 1 message
7. SPAM — 27 messages
8. TRASH — 13 messages
...
```

**Judge:** success=1 — "The agent successfully listed 15 Gmail labels and accurately stated the total count."

**Latency:** 18.5s

</details>

<details>
<summary>Failed task — gmail_005 (hard)</summary>

**Prompt:** Find emails received in the last 7 days that have attachments. List each email's subject, sender, and attachment name.

**What went wrong:** The agent returned 14 emails with attachments — correct count, full details — but included emails the user *sent*, not just received. The task said "received." The agent interpreted it as "in inbox" which includes sent items in its tool query.

**Judge:** success=0 — "The agent failed to filter for received emails, including many sent emails in the results."

**Pattern:** constraint interpretation failure, not a tool failure. The data retrieval was correct; the query scope was wrong.

</details>
