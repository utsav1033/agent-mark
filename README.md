# agent-mark

A benchmark harness for tool-using AI agents. Point it at any agent, give it tasks, get
scored results — task success, tool usage, latency, and cost. No framework assumptions.

---

## Tested against TrustClaw

[TrustClaw](https://github.com/ComposioHQ/trustclaw) is Composio's open-source personal
agent (Next.js, Vercel AI SDK, Composio integrations). It was the first agent evaluated
with this harness.

**Gmail benchmark — 5 tasks, TrustClaw adapter:**

| Task | Difficulty | Result | Latency |
|------|------------|--------|---------|
| List email labels | easy | PASS | 37.0s |
| Fetch 5 most recent inbox emails | easy | PASS | 30.8s |
| Search for invoice emails and summarize | medium | PASS | 27.6s |
| Find and count unread emails | medium | PASS | 40.8s |
| Find emails with attachments (last 7 days) | hard | FAIL | 41.5s |

**4 / 5 (80%).** The hard task failed because the agent found the right data but truncated
its output — the judge penalized an incomplete list.

> Don't have TrustClaw running? See [Quickstart](#quickstart-composio-tools-via-simplepy)
> to run the same tasks against Composio tools directly — no local server needed.

---

## Works for any agent

Plug in a new agent by implementing one method:

```python
class YourAgent:
    def run(self, prompt: str) -> Trajectory:
        # Trajectory = prompt + tool calls made + final response + latency + token counts
        ...
```

Pass it to the runner and the scoring, judging, and reporting pipeline works unchanged.
Two adapters ship out of the box:

- **trustclaw.py** — HTTP/SSE client for a local TrustClaw instance
- **simple.py** — Minimal Anthropic + Composio loop; baseline and reference implementation

---

## Quickstart (Composio tools via simple.py)

The simple adapter runs without TrustClaw. You need an Anthropic API key and a Composio
account with at least one integration connected.

```bash
git clone https://github.com/utsav1033/agent-mark.git
cd agent-mark
pip install -e .
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and COMPOSIO_API_KEY in .env
# I used Vercel AI Gaateway Key as Anthropic API and free tier Composio
```

Run a single task:

```bash
python run.py --adapter simple --task gmail_001
```

Run all Gmail tasks:

```bash
python run.py --adapter simple --toolkit gmail
```

Generate a markdown report:

```bash
python run.py --adapter simple --toolkit gmail --report
```

---

## Running against TrustClaw

Requires TrustClaw running locally on port 3000 and a session cookie for auth.

```bash
# Add to .env:
# TRUSTCLAW_URL=http://localhost:3000
# TRUSTCLAW_AGENT_PATH=/api/chat
# TRUSTCLAW_SESSION_COOKIE=<Cookie header from a logged-in browser session>

python run.py --adapter trustclaw --toolkit gmail
```

To get the session cookie: open TrustClaw in a browser, send any message, then copy the
`Cookie:` request header value from DevTools -> Network -> the `/api/chat` request.

---

## How it works

```
tasks/gmail/gmail_001.yaml
        |
        v
harness/runner.py  -->  adapter.run(prompt)  -->  Trajectory
        |
        v
harness/scorer.py  (tool correctness, efficiency)
harness/judge.py   (Gemini 2.5 Flash rubric judge)
        |
        v
results/gmail_001.json
harness/report.py  -->  results/report_trustclaw.md
```

### Scoring dimensions

| Dimension | Method |
|-----------|--------|
| Task success | Gemini 2.5 Flash judge with per-task rubric, 0 or 1 |
| Tool correctness | 1 if any expected tool was called, else 0 |
| Efficiency | min\_tool\_calls / actual\_tool\_calls, capped at 1.0 |
| Latency | total\_latency\_ms |
| Cost | input\_tokens + output\_tokens (proxy; not priced) |

### Task format

```yaml
id: gmail_001
toolkit: gmail
difficulty: easy
prompt: "List my email labels and tell me how many I have."
expected_tools:
  - GMAIL_LIST_LABELS
min_tool_calls: 1
max_tool_calls: 2
success_rubric: |
  Response should list the email labels and state the total count.
```

---

## Known limitations

**TrustClaw adapter:** Tool calls and token counts are always 0. TrustClaw runs its
Composio tool loop server-side before streaming — no tool events appear in the SSE output.
Task success (the primary metric) is unaffected.

**simple.py adapter:** Requires Composio to be available and the relevant integrations
connected on your account.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic or Vercel AI Gateway key |
| `ANTHROPIC_BASE_URL` | No | Set to `https://ai-gateway.vercel.sh` for Vercel gateway |
| `GOOGLE_API_KEY` | Yes | Google AI Studio key (Gemini judge) |
| `COMPOSIO_API_KEY` | simple adapter | Composio account key |
| `TRUSTCLAW_URL` | trustclaw adapter | Default: `http://localhost:3000` |
| `TRUSTCLAW_AGENT_PATH` | trustclaw adapter | Default: `/api/chat` |
| `TRUSTCLAW_SESSION_COOKIE` | trustclaw adapter | Full Cookie header value from browser |
