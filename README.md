# agent-mark

A framework-agnostic evaluation harness for tool-using AI agents. The primary target is
[TrustClaw](https://github.com/ComposioHQ/composio), Composio's open-source personal agent
(Next.js, Vercel AI SDK, Composio tool integrations). A minimal fallback adapter using the
Anthropic API + Composio Python SDK is also included.

---

## What it does

- Runs structured tasks against a tool-using agent via HTTP
- Scores each run on 5 dimensions: task success, tool correctness, efficiency, latency, cost
- Judges task success using Gemini 2.5 Flash with a per-task rubric
- Outputs per-task JSON results and an aggregated markdown report

---

## Architecture

```
agent-mark/
├── run.py                 # CLI entrypoint
├── adapters/
│   ├── base.py            # Trajectory + ToolCall dataclasses, Agent protocol
│   ├── trustclaw.py       # HTTP/SSE adapter for local TrustClaw instance
│   └── simple.py          # Fallback: Anthropic + Composio Python SDK
├── harness/
│   ├── runner.py          # Loads task YAML, runs agent, saves result JSON
│   ├── judge.py           # Gemini 2.5 Flash rubric judge
│   ├── scorer.py          # Programmatic scores on trajectory
│   └── report.py          # Aggregates results into markdown
├── tasks/
│   ├── gmail/             # 5 tasks (easy x2, medium x2, hard x1)
│   ├── github/            # 5 tasks
│   ├── linear/            # 5 tasks
│   └── slack/             # 5 tasks
└── results/               # Per-task JSON, generated reports
```

### Core contract

Every adapter returns a `Trajectory`:

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
    tool_calls: list[ToolCall]
    final_response: str
    total_latency_ms: float
    input_tokens: int
    output_tokens: int
```

The runner, scorer, and judge only ever see `Trajectory` — adapters are fully interchangeable.

---

## Setup

### Requirements

- Python 3.11+
- A running TrustClaw instance at `localhost:3000` (for the trustclaw adapter)
- API keys: Anthropic (via Vercel AI Gateway), Google AI Studio (for judge), Composio

### Install

```bash
pip install -e .
```

### Environment

Copy `.env.example` to `.env` and fill in your values:

```
ANTHROPIC_API_KEY=<Vercel AI Gateway key>
ANTHROPIC_BASE_URL=https://ai-gateway.vercel.sh
GOOGLE_API_KEY=<Google AI Studio key>
COMPOSIO_API_KEY=<Composio key>

TRUSTCLAW_URL=http://localhost:3000
TRUSTCLAW_AGENT_PATH=/api/chat
TRUSTCLAW_SESSION_COOKIE=<copy Cookie header from a logged-in browser session>
```

The session cookie is required because TrustClaw uses better-auth session-based auth.
To get it: open TrustClaw in a browser, send any message, then copy the `Cookie:` request
header value from DevTools -> Network -> the `/api/chat` request.

---

## Usage

```bash
# Run a single task
python run.py --adapter trustclaw --task gmail_001

# Run all Gmail tasks
python run.py --adapter trustclaw --toolkit gmail

# Run all 20 tasks
python run.py --adapter trustclaw --all

# Generate markdown report
python run.py --report --adapter trustclaw

# Verbose (shows SSE stream debug lines)
python run.py --adapter trustclaw --task gmail_001 --verbose

# Use the fallback simple adapter (no TrustClaw needed)
python run.py --adapter simple --toolkit gmail
```

---

## Results

Only Gmail tasks were fully evaluated. GitHub tasks were skipped to avoid API usage costs.
Linear and Slack tasks were not run because those integrations were not connected in the
test TrustClaw instance.

### Gmail (TrustClaw adapter)

| Task | Difficulty | Result | Latency |
|------|------------|--------|---------|
| gmail_001 — List email labels | easy | PASS | 37.0s |
| gmail_002 — Fetch 5 recent inbox emails | easy | PASS | 30.8s |
| gmail_003 — Search for invoice emails | medium | PASS | 27.6s |
| gmail_004 — Find and count unread emails | medium | PASS | 40.8s |
| gmail_005 — Find emails with attachments (last 7 days) | hard | FAIL | 41.5s |

**Gmail: 4 / 5 (80%)**

The one failure (gmail_005) was a partial response: the agent found 13 emails with
attachments but only listed 2 of them fully, summarizing the rest. The rubric required
listing all of them.

---

## Adapter notes

### TrustClaw adapter

TrustClaw runs as a Next.js app. Key integration details discovered during development:

- Endpoint: `POST /api/chat` (not `/api/agent` as initially assumed)
- Request body: `{ messages: [{ role, content, parts: [{ type: "text", text }] }] }`
  The `parts` array is required — `content` alone returns an empty message error.
- Response: SSE stream using Vercel AI SDK UI Message Stream v1 (`x-vercel-ai-ui-message-stream: v1`)
  JSON-based format: `data: {"type":"text-delta","id":"0","delta":"..."}` per line
- Auth: better-auth session cookie in the `Cookie` header

**Known limitations of the TrustClaw adapter:**

- Tool calls are always empty. TrustClaw executes its full Composio tool loop server-side
  before streaming the text response. No `tool-input-start` or `tool-result` events appear
  in the SSE stream. Tool correctness and efficiency scores are 0 for all TrustClaw runs.
- Token counts are always 0. TrustClaw stores token counts in its database but does not
  expose them in the stream's finish event.

### simple.py adapter

Uses the Anthropic API (via Vercel AI Gateway) and Composio Python SDK (`composio-anthropic`
0.13+). Exposes real token counts and captures tool calls. Serves as a baseline when
TrustClaw is unavailable.

Model: `anthropic/claude-haiku-4-5-20251001` (via Vercel AI Gateway prefix convention).

---

## Scoring

| Dimension | Method |
|-----------|--------|
| Task success | Gemini 2.5 Flash judge, 0 or 1 |
| Tool correctness | 1 if any expected tool was called, else 0 |
| Efficiency | min_tool_calls / actual_tool_calls, capped at 1.0 |
| Latency | total_latency_ms |
| Cost | input_tokens + output_tokens (proxy; not priced) |

The judge retries once on parse failure. If it cannot parse a response after two attempts,
the task is marked `judge-failed` and excluded from aggregate stats rather than defaulting
to pass or fail.

---

## What I learned

**TrustClaw's API is not what the docs suggest.** The actual chat endpoint (`/api/chat`),
the required request shape (Vercel AI SDK `UIMessage` format with `parts`), and the SSE
protocol (JSON-based UI message stream v1, not the older prefix-based data stream) all had
to be discovered by reading the Next.js route source and watching network traffic. Any
harness targeting TrustClaw needs to handle this directly.

**Tool call visibility is an architectural choice.** TrustClaw runs its Composio tool loop
server-side and only streams the final text response. This makes sense for a user-facing
chat product but makes external evaluation harder — you cannot observe which tools were
called or what they returned without database access. The simple.py adapter has full tool
visibility because it owns the loop.

**Gmail performs well on read tasks at medium difficulty.** Four of five tasks passed,
including both medium-difficulty tasks. The one failure was a hard task where the agent
truncated its output — it found the right data but did not present all of it, which the
judge correctly penalized.

**Session-cookie auth is a real integration burden.** better-auth issues HTTP-only cookies
tied to a browser session. Copying a cookie header manually works but expires. A production
harness would need a machine-to-machine auth path (API key or service account) to avoid
this maintenance overhead.

**Latency is dominated by the tool loop, not the model.** All Gmail tasks took 27-41 seconds.
The model response itself streamed quickly once started; the bulk of the time was the
Composio tool execution on TrustClaw's server before the stream began.
