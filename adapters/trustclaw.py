"""
HTTP adapter for a local TrustClaw instance (Next.js on localhost:3000).

TrustClaw exposes a streaming chat endpoint at POST /api/chat that uses the
Vercel AI SDK data stream protocol (SSE with prefixed lines):
  0:"text delta"      — assistant text chunk
  9:{...}             — tool call start (toolCallId, toolName, args)
  a:{...}             — tool result (toolCallId, result)
  d:{...}             — finish (finishReason, usage with promptTokens/completionTokens)

Token counts: TrustClaw's finish event does not include usage data; both fields are set to 0.

Tool calls: TrustClaw executes its full tool loop server-side before streaming the text
response, so no tool-input-start/tool-result events appear in the SSE. tool_calls will
always be an empty list; tool_correctness and efficiency scores are always 0 for this adapter.

Auth: TrustClaw uses better-auth session cookies. Set TRUSTCLAW_SESSION_COOKIE
to the full cookie header value from a logged-in browser session (e.g. from
DevTools → Application → Cookies → copy "Cookie" header value).

Required env vars: TRUSTCLAW_URL (default: http://localhost:3000)
                   TRUSTCLAW_AGENT_PATH (default: /api/chat)
                   TRUSTCLAW_SESSION_COOKIE (session cookie for auth)
"""

from __future__ import annotations

import json
import logging
import os
import time

import httpx

from adapters.base import Trajectory, ToolCall

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 300.0  # SSE streams can be slow for multi-step tool loops


class TrustClawAgent:
    """Wraps TrustClaw's /api/chat SSE endpoint as an Agent."""

    def __init__(self, base_url: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = (base_url or os.getenv("TRUSTCLAW_URL", "http://localhost:3000")).rstrip("/")
        self.agent_path = os.getenv("TRUSTCLAW_AGENT_PATH", "/api/chat")
        self.timeout = timeout
        self._session_cookie = os.getenv("TRUSTCLAW_SESSION_COOKIE", "")

    def run(self, prompt: str) -> Trajectory:
        url = self.base_url + self.agent_path
        headers = {"Content-Type": "application/json"}
        if self._session_cookie:
            log.debug("Sending Cookie header (%d chars, starts with: %s...)", len(self._session_cookie), self._session_cookie[:40])
            headers["Cookie"] = self._session_cookie
        else:
            log.warning("TRUSTCLAW_SESSION_COOKIE is not set — request will be UNAUTHORIZED")

        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "parts": [{"type": "text", "text": prompt}],
                }
            ]
        }

        start = time.time()
        tool_calls: list[ToolCall] = []
        text_chunks: list[str] = []

        # pending_tool_calls: toolCallId -> {name, args, start_time}
        pending: dict[str, dict] = {}

        # usage is populated by the `d:` finish line inside _process_line
        usage: dict[str, int] = {}

        try:
            with httpx.stream(
                "POST",
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            ) as resp:
                if resp.status_code >= 400:
                    body = resp.read().decode(errors="replace")
                    if resp.status_code == 401:
                        raise RuntimeError(
                            "TrustClaw returned 401. Set TRUSTCLAW_SESSION_COOKIE to a valid session."
                        )
                    raise RuntimeError(f"TrustClaw returned HTTP {resp.status_code}: {body}")
                for raw_line in resp.iter_lines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    log.debug("SSE line: %r", line[:120])
                    self._process_line(line, text_chunks, pending, tool_calls, usage)
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Cannot reach TrustClaw at {url}. Is the Next.js app running? ({exc})"
            ) from exc

        total_ms = (time.time() - start) * 1000
        return Trajectory(
            prompt=prompt,
            tool_calls=tool_calls,
            final_response="".join(text_chunks),
            total_latency_ms=total_ms,
            input_tokens=usage.get("inputTokens") or usage.get("promptTokens", 0),
            output_tokens=usage.get("outputTokens") or usage.get("completionTokens", 0),
        )

    def _process_line(
        self,
        line: str,
        text_chunks: list[str],
        pending: dict[str, dict],
        tool_calls: list[ToolCall],
        usage: dict[str, int],
    ) -> None:
        # Vercel AI SDK UI Message Stream v1 format:
        #   data: {"type": "...", ...}
        #   data: [DONE]
        if not line.startswith("data: "):
            return
        payload = line[6:]
        if payload == "[DONE]":
            return

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            log.debug("Could not parse SSE payload %r: %s", payload[:80], exc)
            return

        event = data.get("type", "")

        if event == "text-delta":
            text_chunks.append(data.get("delta", ""))

        elif event == "tool-input-start":
            call_id = data.get("toolCallId", "")
            pending[call_id] = {
                "name": data.get("toolName", "unknown"),
                "args_str": "",
                "start_time": time.time(),
            }

        elif event == "tool-input-delta":
            call_id = data.get("toolCallId", "")
            if call_id in pending:
                pending[call_id]["args_str"] += data.get("delta", "")

        elif event == "tool-input-end":
            call_id = data.get("toolCallId", "")
            if call_id in pending:
                raw = pending[call_id].get("args_str", "{}")
                try:
                    pending[call_id]["args"] = json.loads(raw)
                except json.JSONDecodeError:
                    pending[call_id]["args"] = {"raw": raw}

        elif event == "tool-result":
            call_id = data.get("toolCallId", "")
            info = pending.pop(call_id, {})
            latency = (time.time() - info.get("start_time", time.time())) * 1000
            result = data.get("result")
            tool_calls.append(
                ToolCall(
                    name=info.get("name", "unknown"),
                    args=info.get("args", {}),
                    result=result if isinstance(result, dict) else {"output": str(result)},
                    latency_ms=latency,
                )
            )

        elif event == "finish":
            u = data.get("usage", {})
            if u:
                usage.update(u)

    def close(self) -> None:
        pass  # httpx.stream() closes the connection after the with-block
