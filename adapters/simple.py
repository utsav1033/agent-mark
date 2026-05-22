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

from adapters.base import Agent, Trajectory, ToolCall

log = logging.getLogger(__name__)

_TOOLKIT_APPS: dict[str, list[str]] = {
    "gmail": ["gmail"],
    "github": ["github"],
    "linear": ["linear"],
    "slack": ["slack"],
}


def _import_composio():
    """Lazy import so the harness doesn't crash when using --adapter trustclaw."""
    try:
        from composio import Composio
        from composio_anthropic import AnthropicProvider
        return Composio, AnthropicProvider
    except ImportError as exc:
        raise ImportError(
            "composio and composio-anthropic are required for the simple adapter. "
            "Install them with: pip install composio composio-anthropic"
        ) from exc


class SimpleAgent:
    """Agentic loop: Anthropic model + Composio tool execution (new SDK)."""

    def __init__(
        self,
        model: str = "anthropic/claude-haiku-4-5-20251001",
        max_iter: int = 10,
        toolkit: str | None = None,
    ) -> None:
        Composio, AnthropicProvider = _import_composio()
        self.client = anthropic.Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            base_url=os.environ.get("ANTHROPIC_BASE_URL"),
        )
        self._provider = AnthropicProvider()
        self._composio = Composio(provider=self._provider)
        self._apps = _TOOLKIT_APPS.get(toolkit, []) if toolkit else list(_TOOLKIT_APPS.keys())
        self.model = model
        self.max_iter = max_iter

    def _load_tools(self) -> list:
        try:
            return self._composio.tools.get(apps=self._apps)
        except Exception as exc:
            log.warning("Failed to load tools: %s", exc)
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

            text_blocks = [b for b in response.content if hasattr(b, "text")]
            if text_blocks:
                final_response = text_blocks[-1].text

            if response.stop_reason == "end_turn":
                break

            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_use_blocks:
                break

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tu in tool_use_blocks:
                tc_start = time.time()
                try:
                    execution = self._provider.execute_tool_call(
                        user_id="default",
                        tool_call=tu,
                    )
                    result_dict: dict | None = (
                        execution.data if isinstance(execution.data, dict)
                        else {"output": str(execution.data)}
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
