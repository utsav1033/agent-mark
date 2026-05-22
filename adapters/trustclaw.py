"""
HTTP adapter for a local TrustClaw instance (Next.js on localhost:3000).

TrustClaw exposes a tool-loop agent via an HTTP endpoint. This adapter:
- Sends the prompt to the agent endpoint
- Parses tool calls from the response
- Returns a Trajectory

Token counts: TrustClaw does not currently expose token counts via its
public HTTP API; both fields are set to 0 and noted here.

Required env vars: TRUSTCLAW_URL (default: http://localhost:3000)

Endpoint discovery: Inspect the TrustClaw repo for the agent route.
The adapter targets POST /api/agent or the tRPC equivalent — update
TRUSTCLAW_AGENT_PATH if the route differs in your build.
"""

from __future__ import annotations

import logging
import os
import time

import httpx

from adapters.base import Agent, Trajectory, ToolCall

log = logging.getLogger(__name__)

TRUSTCLAW_AGENT_PATH = "/api/agent"
DEFAULT_TIMEOUT = 120.0  # seconds; agent loops can be slow


class TrustClawAgent:
    """
    Wraps the TrustClaw HTTP endpoint as an Agent.

    Expected response shape (adjust _parse_response if TrustClaw differs):
    {
      "response": "final text response",
      "toolCalls": [
        {"name": "TOOL_NAME", "args": {...}, "result": {...}, "latencyMs": 123}
      ]
    }
    """

    def __init__(self, base_url: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = (base_url or os.getenv("TRUSTCLAW_URL", "http://localhost:3000")).rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=self.timeout)

    def run(self, prompt: str) -> Trajectory:
        url = self.base_url + TRUSTCLAW_AGENT_PATH
        payload = {"prompt": prompt}

        start = time.time()
        try:
            resp = self._client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Cannot reach TrustClaw at {url}. Is the Next.js app running? ({exc})"
            ) from exc

        total_ms = (time.time() - start) * 1000

        tool_calls = self._parse_tool_calls(data.get("toolCalls", []))
        final_response = data.get("response", "")

        return Trajectory(
            prompt=prompt,
            tool_calls=tool_calls,
            final_response=final_response,
            total_latency_ms=total_ms,
            input_tokens=0,   # not exposed by TrustClaw HTTP API
            output_tokens=0,  # not exposed by TrustClaw HTTP API
        )

    @staticmethod
    def _parse_tool_calls(raw: list[dict]) -> list[ToolCall]:
        calls = []
        for item in raw:
            calls.append(
                ToolCall(
                    name=item.get("name", "unknown"),
                    args=item.get("args", {}),
                    result=item.get("result"),
                    latency_ms=float(item.get("latencyMs", 0)),
                )
            )
        return calls

    def close(self) -> None:
        self._client.close()
