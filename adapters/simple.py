"""
Minimal Anthropic + Composio agent. Serves as the baseline adapter and fallback
when TrustClaw setup is unavailable.

Token counts are captured from Anthropic API responses (input + output).
Tool latencies are wall-clock time around each Composio execute_action call.

Required env vars: ANTHROPIC_API_KEY, COMPOSIO_API_KEY
Optional env vars: ANTHROPIC_BASE_URL (set to route through a gateway, e.g. Vercel AI Gateway)
"""

from __future__ import annotations

import logging
import os
import time

import anthropic
from composio_anthropic import Action, ComposioToolSet

from adapters.base import Agent, Trajectory, ToolCall

log = logging.getLogger(__name__)

# Curated read-only actions for the 4 supported toolkits.
# Exact Composio action names — verified against composio-core action registry.
_GMAIL_ACTIONS = [
    Action.GMAIL_FETCH_EMAILS,
    Action.GMAIL_LIST_LABELS,
    Action.GMAIL_GET_ATTACHMENT,
]

_GITHUB_ACTIONS = [
    Action.GITHUB_LIST_REPOS_FOR_AUTHENTICATED_USER,
    Action.GITHUB_LIST_REPOSITORY_ISSUES,
    Action.GITHUB_GET_AN_ISSUE,
    Action.GITHUB_LIST_PULL_REQUESTS,
    Action.GITHUB_GET_A_REPOSITORY,
]

_LINEAR_ACTIONS = [
    Action.LINEAR_GET_TEAMS,
    Action.LINEAR_LIST_ISSUES,
    Action.LINEAR_GET_ISSUE,
]

_SLACK_ACTIONS = [
    Action.SLACK_LIST_ALL_SLACK_CHANNEL,
    Action.SLACK_FETCH_CONVERSATION_HISTORY,
    Action.SLACK_SEARCH_MESSAGES,
]

_TOOLKIT_ACTIONS: dict[str, list] = {
    "gmail": _GMAIL_ACTIONS,
    "github": _GITHUB_ACTIONS,
    "linear": _LINEAR_ACTIONS,
    "slack": _SLACK_ACTIONS,
}

_ALL_ACTIONS = _GMAIL_ACTIONS + _GITHUB_ACTIONS + _LINEAR_ACTIONS + _SLACK_ACTIONS


class SimpleAgent:
    """Agentic loop: Anthropic model + Composio tool execution."""

    def __init__(
        self,
        model: str = "anthropic/claude-haiku-4-5-20251001",
        max_iter: int = 10,
        toolkit: str | None = None,
    ) -> None:
        self.client = anthropic.Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            base_url=os.environ.get("ANTHROPIC_BASE_URL"),
        )
        self.toolset = ComposioToolSet()
        self.model = model
        self.max_iter = max_iter
        self._actions = (
            _TOOLKIT_ACTIONS.get(toolkit, _ALL_ACTIONS) if toolkit else _ALL_ACTIONS
        )

    def _load_tools(self) -> list:
        try:
            return self.toolset.get_tools(actions=self._actions)
        except Exception as exc:
            log.warning("Failed to load some tools: %s", exc)
            return []

    def run(self, prompt: str) -> Trajectory:
        tools = self._load_tools()
        messages: list[dict] = [{"role": "user", "content": prompt}]

        tool_calls: list[ToolCall] = []
        input_tokens = 0
        output_tokens = 0
        final_response = ""
        run_start = time.time()

        for iteration in range(self.max_iter):
            log.debug("Iteration %d", iteration)
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                tools=tools,
                messages=messages,
            )

            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens

            # Extract text from response
            text_blocks = [b for b in response.content if hasattr(b, "text")]
            if text_blocks:
                final_response = text_blocks[-1].text

            if response.stop_reason == "end_turn":
                break

            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_use_blocks:
                break

            # Append assistant turn
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tu in tool_use_blocks:
                tc_start = time.time()
                try:
                    raw = self.toolset.execute_action(
                        action=tu.name,
                        params=tu.input,
                    )
                    result_dict: dict | None = (
                        raw if isinstance(raw, dict) else {"output": str(raw)}
                    )
                except Exception as exc:
                    log.warning("Tool %s failed: %s", tu.name, exc)
                    result_dict = {"error": str(exc)}

                tc_latency = (time.time() - tc_start) * 1000
                tool_calls.append(
                    ToolCall(
                        name=tu.name,
                        args=tu.input,
                        result=result_dict,
                        latency_ms=tc_latency,
                    )
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": str(result_dict),
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        total_ms = (time.time() - run_start) * 1000
        return Trajectory(
            prompt=prompt,
            tool_calls=tool_calls,
            final_response=final_response,
            total_latency_ms=total_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
