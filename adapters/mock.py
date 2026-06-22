"""
Mock adapter for demo and CI use. Returns hardcoded Trajectory objects for all
Gmail tasks. Requires no API keys.

Also implements get_mock_judge(prompt) -> dict so the runner can skip the
Gemini judge entirely — the mock result is pre-set per task.

Usage:
    agent-mark demo
    python cli.py --adapter mock --toolkit gmail
"""

from __future__ import annotations

from adapters.base import Trajectory, ToolCall

# Pre-built Trajectory + judge result for each Gmail task prompt.
# Mirrors realistic output from a Composio-powered agent.
_MOCK_DATA: dict[str, dict] = {
    "List my email labels and tell me how many I have.": {
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
                            "CATEGORY_PERSONAL", "CATEGORY_SOCIAL",
                            "CATEGORY_FORUMS", "CHAT", "YELLOW_STAR",
                        ]
                    },
                    latency_ms=820.4,
                )
            ],
            final_response=(
                "You have 15 email labels in total.\n\n"
                "System labels: INBOX, SENT, DRAFT, SPAM, TRASH, STARRED, IMPORTANT, UNREAD\n"
                "Category labels: CATEGORY_UPDATES, CATEGORY_PROMOTIONS, CATEGORY_PERSONAL, "
                "CATEGORY_SOCIAL, CATEGORY_FORUMS\n"
                "Other: CHAT, YELLOW_STAR"
            ),
            total_latency_ms=1240.1,
            input_tokens=1843,
            output_tokens=312,
        ),
        "judge": {"success": 1, "reasoning": "Agent listed all 15 labels and stated the correct total count."},
    },

    "Fetch the 5 most recent emails in my inbox and list their subjects and senders.": {
        "trajectory": Trajectory(
            prompt="Fetch the 5 most recent emails in my inbox and list their subjects and senders.",
            tool_calls=[
                ToolCall(
                    name="GMAIL_FETCH_EMAILS",
                    args={"maxResults": 5, "labelIds": ["INBOX"]},
                    result={
                        "emails": [
                            {"subject": "Your AWS invoice is ready", "from": "billing@amazon.com"},
                            {"subject": "Job alert: AI Engineer at Startup", "from": "alerts@linkedin.com"},
                            {"subject": "Payment confirmed", "from": "noreply@razorpay.com"},
                            {"subject": "Weekly digest", "from": "digest@substack.com"},
                            {"subject": "Re: Interview scheduling", "from": "hr@company.com"},
                        ]
                    },
                    latency_ms=1103.7,
                )
            ],
            final_response=(
                "Here are your 5 most recent inbox emails:\n\n"
                "1. **Your AWS invoice is ready** — billing@amazon.com\n"
                "2. **Job alert: AI Engineer at Startup** — alerts@linkedin.com\n"
                "3. **Payment confirmed** — noreply@razorpay.com\n"
                "4. **Weekly digest** — digest@substack.com\n"
                "5. **Re: Interview scheduling** — hr@company.com"
            ),
            total_latency_ms=1580.2,
            input_tokens=2104,
            output_tokens=287,
        ),
        "judge": {"success": 1, "reasoning": "Agent listed 5 emails with subjects and senders as requested."},
    },

    "Search for emails with the word 'invoice' in the subject and summarize what you find.": {
        "trajectory": Trajectory(
            prompt="Search for emails with the word 'invoice' in the subject and summarize what you find.",
            tool_calls=[
                ToolCall(
                    name="GMAIL_FETCH_EMAILS",
                    args={"q": "subject:invoice"},
                    result={
                        "emails": [
                            {"subject": "Your AWS invoice is ready", "from": "billing@amazon.com", "date": "2026-05-20"},
                            {"subject": "Invoice #1042 from Razorpay", "from": "noreply@razorpay.com", "date": "2026-05-15"},
                            {"subject": "GST Invoice Available", "from": "invoicing@aws.com", "date": "2026-05-01"},
                        ]
                    },
                    latency_ms=980.5,
                )
            ],
            final_response=(
                "Found 3 emails with 'invoice' in the subject:\n\n"
                "1. **Your AWS invoice is ready** — billing@amazon.com (May 20)\n"
                "2. **Invoice #1042 from Razorpay** — noreply@razorpay.com (May 15)\n"
                "3. **GST Invoice Available** — invoicing@aws.com (May 1)\n\n"
                "All three are transactional billing emails from AWS and Razorpay."
            ),
            total_latency_ms=1450.8,
            input_tokens=2356,
            output_tokens=341,
        ),
        "judge": {"success": 1, "reasoning": "Agent found and summarized all invoice emails with senders and dates."},
    },

    "Find unread emails in my inbox. How many are there and who are they from?": {
        "trajectory": Trajectory(
            prompt="Find unread emails in my inbox. How many are there and who are they from?",
            tool_calls=[
                ToolCall(
                    name="GMAIL_FETCH_EMAILS",
                    args={"q": "is:unread in:inbox", "maxResults": 50},
                    result={"resultSizeEstimate": 214, "emails": [
                        {"from": "alerts@linkedin.com"},
                        {"from": "noreply@github.com"},
                        {"from": "newsletter@substack.com"},
                    ]},
                    latency_ms=1230.0,
                )
            ],
            final_response=(
                "You have approximately 214 unread emails in your inbox.\n\n"
                "Top senders:\n"
                "- LinkedIn job alerts\n"
                "- GitHub notifications\n"
                "- Substack newsletters\n\n"
                "Most are automated notifications."
            ),
            total_latency_ms=1890.3,
            input_tokens=2671,
            output_tokens=298,
        ),
        "judge": {"success": 1, "reasoning": "Agent stated unread count and listed senders from actual fetched data."},
    },

    "Find emails received in the last 7 days that have attachments. List each email's subject, sender, and the name of the attachment if visible. If there are none, say so explicitly.": {
        "trajectory": Trajectory(
            prompt="Find emails received in the last 7 days that have attachments. List each email's subject, sender, and the name of the attachment if visible. If there are none, say so explicitly.",
            tool_calls=[
                ToolCall(
                    name="GMAIL_FETCH_EMAILS",
                    args={"q": "has:attachment newer_than:7d in:inbox"},
                    result={"emails": [
                        {"subject": "Offer letter", "from": "hr@company.com", "attachment": "offer_letter.pdf"},
                        {"subject": "SIP confirmation", "from": "kfintech.com", "attachment": "statement.pdf"},
                    ]},
                    latency_ms=1410.2,
                )
            ],
            final_response=(
                "Found 2 received emails with attachments in the last 7 days:\n\n"
                "1. **Offer letter** — hr@company.com\n   Attachment: offer_letter.pdf\n\n"
                "2. **SIP confirmation** — kfintech.com\n   Attachment: statement.pdf"
            ),
            total_latency_ms=2100.6,
            input_tokens=2890,
            output_tokens=334,
        ),
        "judge": {"success": 1, "reasoning": "Agent listed received emails with attachments, subjects, senders, and filenames."},
    },
}

# Normalise keys so the lookup is whitespace-insensitive
_INDEX: dict[str, dict] = {k.strip(): v for k, v in _MOCK_DATA.items()}


class MockAgent:
    """Returns hardcoded trajectories. No network calls, no API keys."""

    def run(self, prompt: str) -> Trajectory:
        entry = _INDEX.get(prompt.strip())
        if entry is None:
            # Unknown prompt — return an empty trajectory so the harness doesn't crash
            return Trajectory(
                prompt=prompt,
                tool_calls=[],
                final_response="[mock] No hardcoded response for this prompt.",
                total_latency_ms=50.0,
                input_tokens=0,
                output_tokens=0,
            )
        return entry["trajectory"]

    def get_mock_judge(self, prompt: str) -> dict | None:
        entry = _INDEX.get(prompt.strip())
        return entry["judge"] if entry else None
