"""
Synthetic Gmail trajectory fixtures — scorer development and demo only.

SYNTHETIC DATA. These trajectories are hand-authored to exercise specific
scorer behaviours. They are NOT real agent runs and must never appear in
benchmark tables or results/ output.

Each fixture dict contains:
  id          — unique identifier
  synthetic   — always True (self-identifying marker, survives out-of-context reads)
  description — what behaviour this fixture exercises and what scores to expect
  task        — task dict matching the shape the scorer reads (expected_tools,
                min_tool_calls, etc.)
  trajectory  — Trajectory object ready to pass directly to score()

Cases covered:
  (a) clean success          — right tool, one call, correct answer
  (b) wasteful success       — correct answer, 3 calls when 1 was enough
  (c) wrong-tool failure     — unexpected tool called, task failed
  (d) right-tool-wrong-scope — correct tool, programmatic scores look fine,
                               but constraint misread; only the judge catches this
  (e) multi-step             — two sequential tool calls, both required
"""

from __future__ import annotations

from adapters.base import Trajectory, ToolCall

FIXTURES: list[dict] = [

    # -------------------------------------------------------------------------
    # (a) Clean success
    # Right tool, single call, correct answer.
    # Expected: tool_correctness=1.0, efficiency=1.0
    # -------------------------------------------------------------------------
    {
        "id": "syn_gmail_a_clean_success",
        "synthetic": True,
        "description": (
            "Clean success: agent calls the expected tool exactly once and "
            "returns a correct, complete answer. "
            "Expected — tool_correctness: 1.0, efficiency: 1.0."
        ),
        "task": {
            "id": "syn_gmail_a_clean_success",
            "toolkit": "gmail",
            "difficulty": "easy",
            "prompt": "List my email labels and tell me how many I have.",
            "expected_tools": ["GMAIL_LIST_LABELS"],
            "min_tool_calls": 1,
            "max_tool_calls": 2,
            "success_rubric": (
                "Response lists the email labels and states the correct total count."
            ),
        },
        "trajectory": Trajectory(
            prompt="List my email labels and tell me how many I have.",
            tool_calls=[
                ToolCall(
                    name="GMAIL_LIST_LABELS",
                    args={},
                    result={
                        "labels": [
                            "INBOX", "SENT", "DRAFT", "SPAM", "TRASH",
                            "STARRED", "IMPORTANT", "UNREAD",
                            "CATEGORY_UPDATES", "CATEGORY_PROMOTIONS",
                        ]
                    },
                    latency_ms=430.2,
                )
            ],
            final_response=(
                "You have 10 email labels: INBOX, SENT, DRAFT, SPAM, TRASH, "
                "STARRED, IMPORTANT, UNREAD, CATEGORY_UPDATES, and CATEGORY_PROMOTIONS."
            ),
            total_latency_ms=1850.7,
            input_tokens=1240,
            output_tokens=188,
        ),
    },

    # -------------------------------------------------------------------------
    # (b) Wasteful success
    # Correct tool and correct final answer, but called 3 times when once was
    # enough — simulated unnecessary retries with progressively looser queries.
    # Expected: tool_correctness=1.0, efficiency=0.33  (min 1 / actual 3)
    # -------------------------------------------------------------------------
    {
        "id": "syn_gmail_b_wasteful_success",
        "synthetic": True,
        "description": (
            "Wasteful success: agent reaches the correct answer but makes 3 "
            "tool calls when the minimum is 1 (unnecessary retries with "
            "progressively looser queries). "
            "Expected — tool_correctness: 1.0, efficiency: 0.33."
        ),
        "task": {
            "id": "syn_gmail_b_wasteful_success",
            "toolkit": "gmail",
            "difficulty": "medium",
            "prompt": (
                "Fetch the 5 most recent emails in my inbox and list their "
                "subjects and senders."
            ),
            "expected_tools": ["GMAIL_FETCH_EMAILS"],
            "min_tool_calls": 1,
            "max_tool_calls": 2,
            "success_rubric": (
                "Response lists 5 emails with subject and sender for each."
            ),
        },
        "trajectory": Trajectory(
            prompt=(
                "Fetch the 5 most recent emails in my inbox and list their "
                "subjects and senders."
            ),
            tool_calls=[
                ToolCall(
                    name="GMAIL_FETCH_EMAILS",
                    args={"maxResults": 5, "labelIds": ["INBOX"], "q": "is:unread"},
                    result={"emails": [], "resultSizeEstimate": 0},
                    latency_ms=610.4,
                ),
                ToolCall(
                    name="GMAIL_FETCH_EMAILS",
                    args={"maxResults": 5, "labelIds": ["INBOX"]},
                    result={"emails": [], "resultSizeEstimate": 0},
                    latency_ms=580.1,
                ),
                ToolCall(
                    name="GMAIL_FETCH_EMAILS",
                    args={"maxResults": 5},
                    result={
                        "emails": [
                            {"subject": "Your AWS invoice is ready", "from": "billing@amazon.com"},
                            {"subject": "Job alert: AI Engineer", "from": "alerts@linkedin.com"},
                            {"subject": "Payment confirmed", "from": "noreply@razorpay.com"},
                            {"subject": "Weekly digest", "from": "digest@substack.com"},
                            {"subject": "Re: Interview scheduling", "from": "hr@company.com"},
                        ]
                    },
                    latency_ms=720.9,
                ),
            ],
            final_response=(
                "Here are your 5 most recent emails:\n"
                "1. Your AWS invoice is ready — billing@amazon.com\n"
                "2. Job alert: AI Engineer — alerts@linkedin.com\n"
                "3. Payment confirmed — noreply@razorpay.com\n"
                "4. Weekly digest — digest@substack.com\n"
                "5. Re: Interview scheduling — hr@company.com"
            ),
            total_latency_ms=4380.2,
            input_tokens=2860,
            output_tokens=241,
        ),
    },

    # -------------------------------------------------------------------------
    # (c) Wrong-tool failure
    # Agent calls GMAIL_LIST_LABELS instead of GMAIL_FETCH_EMAILS. The response
    # is wrong. Efficiency appears fine (1 call, min 1) but the task failed.
    # Expected: tool_correctness=0.0, efficiency=1.0
    # -------------------------------------------------------------------------
    {
        "id": "syn_gmail_c_wrong_tool",
        "synthetic": True,
        "description": (
            "Wrong-tool failure: agent calls GMAIL_LIST_LABELS when "
            "GMAIL_FETCH_EMAILS was required. tool_correctness is 0 because "
            "the expected tool was never called. Efficiency looks fine (1 call, "
            "min 1) but the task failed entirely. "
            "Expected — tool_correctness: 0.0, efficiency: 1.0."
        ),
        "task": {
            "id": "syn_gmail_c_wrong_tool",
            "toolkit": "gmail",
            "difficulty": "easy",
            "prompt": (
                "Search for emails with the word 'invoice' in the subject "
                "and summarize what you find."
            ),
            "expected_tools": ["GMAIL_FETCH_EMAILS"],
            "min_tool_calls": 1,
            "max_tool_calls": 3,
            "success_rubric": (
                "Response lists emails with 'invoice' in the subject, "
                "with sender and date."
            ),
        },
        "trajectory": Trajectory(
            prompt=(
                "Search for emails with the word 'invoice' in the subject "
                "and summarize what you find."
            ),
            tool_calls=[
                ToolCall(
                    name="GMAIL_LIST_LABELS",
                    args={},
                    result={"labels": ["INBOX", "SENT", "DRAFT", "SPAM", "TRASH"]},
                    latency_ms=395.6,
                )
            ],
            final_response=(
                "I found these email categories: INBOX, SENT, DRAFT, SPAM, and TRASH. "
                "I was unable to locate any invoice emails specifically."
            ),
            total_latency_ms=1620.3,
            input_tokens=1180,
            output_tokens=144,
        ),
    },

    # -------------------------------------------------------------------------
    # (d) Right tool, wrong scope
    # Agent calls GMAIL_FETCH_EMAILS (correct) but omits "in:inbox", so results
    # include sent emails alongside received ones. Programmatic scores are both
    # 1.0 — this fixture exists to demonstrate that tool_correctness and
    # efficiency cannot catch constraint misreads. The judge is required.
    # Expected: tool_correctness=1.0, efficiency=1.0  (scores mislead here)
    # -------------------------------------------------------------------------
    {
        "id": "syn_gmail_d_right_tool_wrong_scope",
        "synthetic": True,
        "description": (
            "Right tool, wrong scope: agent calls GMAIL_FETCH_EMAILS correctly "
            "but without the 'in:inbox' / received-only filter, so results "
            "include emails the user sent. Programmatic scores are both 1.0 — "
            "this is intentional. It shows tool_correctness and efficiency "
            "cannot catch constraint misreads; the Gemini judge is required. "
            "Expected — tool_correctness: 1.0, efficiency: 1.0."
        ),
        "task": {
            "id": "syn_gmail_d_right_tool_wrong_scope",
            "toolkit": "gmail",
            "difficulty": "hard",
            "prompt": (
                "Find emails received in the last 7 days that have attachments. "
                "List each email's subject, sender, and attachment name if visible."
            ),
            "expected_tools": ["GMAIL_FETCH_EMAILS"],
            "min_tool_calls": 1,
            "max_tool_calls": 5,
            "success_rubric": (
                "Response lists only received (not sent) emails from the past 7 days "
                "that have attachments, with subject and sender. Must not include "
                "emails the user sent themselves."
            ),
        },
        "trajectory": Trajectory(
            prompt=(
                "Find emails received in the last 7 days that have attachments. "
                "List each email's subject, sender, and attachment name if visible."
            ),
            tool_calls=[
                ToolCall(
                    name="GMAIL_FETCH_EMAILS",
                    args={"q": "has:attachment newer_than:7d"},  # missing in:inbox
                    result={
                        "emails": [
                            {"subject": "Offer letter", "from": "hr@company.com", "attachment": "offer_letter.pdf"},
                            {"subject": "SIP confirmation", "from": "kfintech.com", "attachment": "statement.pdf"},
                            {"subject": "Resume for review", "from": "me@gmail.com", "attachment": "resume_v2.pdf"},
                            {"subject": "Project proposal", "from": "me@gmail.com", "attachment": "proposal.docx"},
                        ]
                    },
                    latency_ms=1140.7,
                )
            ],
            final_response=(
                "Found 4 emails with attachments in the last 7 days:\n"
                "1. Offer letter — hr@company.com (offer_letter.pdf)\n"
                "2. SIP confirmation — kfintech.com (statement.pdf)\n"
                "3. Resume for review — me@gmail.com (resume_v2.pdf)\n"
                "4. Project proposal — me@gmail.com (proposal.docx)"
            ),
            total_latency_ms=3210.4,
            input_tokens=2190,
            output_tokens=207,
        ),
    },

    # -------------------------------------------------------------------------
    # (e) Multi-step task
    # Two GMAIL_FETCH_EMAILS calls in sequence: first fetches all unread GitHub
    # notification emails, second narrows to pull-request subjects only.
    # min_tool_calls=2, actual=2 → efficiency=1.0
    # Expected: tool_correctness=1.0, efficiency=1.0
    # -------------------------------------------------------------------------
    {
        "id": "syn_gmail_e_multi_step",
        "synthetic": True,
        "description": (
            "Multi-step task: two sequential GMAIL_FETCH_EMAILS calls — first "
            "fetches all unread GitHub notification emails, second narrows to "
            "pull-request subjects. Agent synthesises both into a summary. "
            "min_tool_calls=2, actual=2. "
            "Expected — tool_correctness: 1.0, efficiency: 1.0."
        ),
        "task": {
            "id": "syn_gmail_e_multi_step",
            "toolkit": "gmail",
            "difficulty": "medium",
            "prompt": (
                "Find unread emails from GitHub notifications in the last 7 days "
                "and summarise any pull requests mentioned."
            ),
            "expected_tools": ["GMAIL_FETCH_EMAILS"],
            "min_tool_calls": 2,
            "max_tool_calls": 4,
            "success_rubric": (
                "Response lists pull requests from GitHub notification emails, "
                "with PR title or number and repository name where available."
            ),
        },
        "trajectory": Trajectory(
            prompt=(
                "Find unread emails from GitHub notifications in the last 7 days "
                "and summarise any pull requests mentioned."
            ),
            tool_calls=[
                ToolCall(
                    name="GMAIL_FETCH_EMAILS",
                    args={
                        "q": "from:notifications@github.com is:unread newer_than:7d",
                        "maxResults": 20,
                    },
                    result={
                        "emails": [
                            {"subject": "[org/repo] PR #42: Add rate limiting", "from": "notifications@github.com"},
                            {"subject": "[org/repo] PR #43: Fix auth token expiry", "from": "notifications@github.com"},
                            {"subject": "[org/api] Issue #88: 500 on /search", "from": "notifications@github.com"},
                            {"subject": "[org/repo] PR #44: Update dependencies", "from": "notifications@github.com"},
                        ]
                    },
                    latency_ms=880.3,
                ),
                ToolCall(
                    name="GMAIL_FETCH_EMAILS",
                    args={
                        "q": "from:notifications@github.com subject:PR is:unread newer_than:7d",
                        "maxResults": 20,
                    },
                    result={
                        "emails": [
                            {"subject": "[org/repo] PR #42: Add rate limiting", "from": "notifications@github.com"},
                            {"subject": "[org/repo] PR #43: Fix auth token expiry", "from": "notifications@github.com"},
                            {"subject": "[org/repo] PR #44: Update dependencies", "from": "notifications@github.com"},
                        ]
                    },
                    latency_ms=760.1,
                ),
            ],
            final_response=(
                "Found 3 open pull requests in GitHub notification emails from the last 7 days "
                "(repository: org/repo):\n"
                "- PR #42: Add rate limiting\n"
                "- PR #43: Fix auth token expiry\n"
                "- PR #44: Update dependencies\n\n"
                "Also in your notifications: Issue #88 (500 on /search) in org/api."
            ),
            total_latency_ms=5640.8,
            input_tokens=3420,
            output_tokens=312,
        ),
    },
]
