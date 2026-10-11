"""
Adapter for pi (https://github.com/Dicklesworthstone/pi_agent_rust), the Rust port
of Mario Zechner's pi coding agent.

Runs `pi -p --mode json` as a subprocess inside the task workspace and parses its
JSON event stream into a Trajectory:

  tool_execution_start / tool_execution_end  -> ToolCall (name, args, result, latency)
  message_end (role=assistant)               -> usage (tokens + $ cost), final text

Everything is observable: full tool trajectory, per-tool latency, exact token
counts, and dollar cost as computed by pi from its pricing catalog (or from the
prices passed in for a custom OpenAI-compatible endpoint such as a LiteLLM proxy).

Spend guards (enforced live, while the agent is running):
  max_cost_usd     — kill the run once pi-reported cost for this task exceeds it
  max_tokens       — kill the run once input+output tokens exceed it (works even
                     when the provider is unpriced)
  timeout_s        — kill the run after this many wall-clock seconds
A killed run is still returned as a Trajectory with stop_reason set, so it is
scored as a failure, never silently dropped.

Isolation: each run gets a throwaway PI_CODING_AGENT_DIR, so your personal
~/.pi config, skills, extensions and AGENTS.md never leak into benchmark runs.
Extensions, skills, prompt templates and session persistence are disabled.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from agent_mark.adapters.base import ToolCall, Trajectory

log = logging.getLogger(__name__)

DEFAULT_TOOLS = "read,bash,edit,write,grep,find,ls"
_RESULT_TEXT_LIMIT = 2000  # chars of tool output kept per call in result JSON


@dataclass
class PiConfig:
    model: str
    provider: str | None = None
    binary: str = "pi"
    tools: str = DEFAULT_TOOLS
    thinking: str | None = None
    # Custom OpenAI-compatible endpoint (e.g. a LiteLLM proxy). When set, a
    # provider named `provider` is registered in an isolated models.json.
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    price_in_per_mtok: float = 0.0
    price_out_per_mtok: float = 0.0
    # Spend guards
    max_cost_usd: float | None = 0.25
    max_tokens: int | None = 300_000
    timeout_s: float = 300.0


@dataclass
class _RunState:
    """Mutable accumulator for one pi run, fed one JSON event at a time."""

    pending: dict[str, tuple[str, dict, float]]
    tool_calls: list[ToolCall]
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    final_response: str = ""
    stop_reason: str = ""
    fatal_error: str | None = None


def _text_of(blocks: list | None) -> str:
    if not blocks:
        return ""
    return "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")


def apply_event(state: _RunState, event: dict, now: float, prices: tuple[float, float] = (0.0, 0.0)) -> None:
    """Fold one pi JSON event into the run state. Pure apart from `state`; unit-tested."""
    etype = event.get("type")

    if etype == "tool_execution_start":
        state.pending[event["toolCallId"]] = (event.get("toolName", "?"), event.get("args") or {}, now)

    elif etype == "tool_execution_end":
        name, args, started = state.pending.pop(
            event["toolCallId"], (event.get("toolName", "?"), {}, now)
        )
        result = event.get("result") or {}
        is_error = bool(event.get("isError") or result.get("isError"))
        state.tool_calls.append(
            ToolCall(
                name=name,
                args=args if isinstance(args, dict) else {"args": args},
                result={"is_error": is_error, "text": _text_of(result.get("content"))[:_RESULT_TEXT_LIMIT]},
                latency_ms=(now - started) * 1000,
            )
        )

    elif etype == "message_end":
        msg = event.get("message") or {}
        if msg.get("role") != "assistant":
            return
        usage = msg.get("usage") or {}
        tin = int(usage.get("input", 0)) + int(usage.get("cacheRead", 0)) + int(usage.get("cacheWrite", 0))
        tout = int(usage.get("output", 0))
        state.input_tokens += tin
        state.output_tokens += tout
        cost = float((usage.get("cost") or {}).get("total", 0.0))
        if cost == 0.0 and any(prices):
            # Unpriced in pi's catalog: fall back to the caller's per-Mtok prices.
            cost = (tin * prices[0] + tout * prices[1]) / 1_000_000
        state.cost_usd += cost
        text = _text_of(msg.get("content"))
        if text.strip():
            state.final_response = text
        state.stop_reason = msg.get("stopReason", state.stop_reason)
        if msg.get("errorMessage"):
            state.fatal_error = msg["errorMessage"]

    elif etype == "agent_end":
        if event.get("error"):
            state.fatal_error = event["error"]

    elif etype == "error":
        state.fatal_error = f"{event.get('code', 'error')}: {event.get('message', '')}"


class PiAgent:
    """Runs the pi coding agent in a task workspace. See module docstring."""

    def __init__(self, config: PiConfig) -> None:
        if shutil.which(config.binary) is None and not Path(config.binary).is_file():
            raise FileNotFoundError(
                f"pi binary not found: {config.binary!r}. Install pi or pass --pi-binary /path/to/pi"
            )
        self.config = config

    def _agent_dir(self) -> str:
        """Create an isolated pi config dir; register the custom provider if any."""
        d = tempfile.mkdtemp(prefix="agent-mark-pi-")
        c = self.config
        if c.base_url:
            models = {
                "providers": {
                    c.provider or "custom": {
                        "baseUrl": c.base_url,
                        "api": "openai-completions",
                        "apiKey": c.api_key_env,
                        "models": [
                            {
                                "id": c.model,
                                "name": c.model,
                                "contextWindow": 128_000,
                                "maxTokens": 8192,
                                "reasoning": False,
                                "input": ["text"],
                                "cost": {
                                    "input": c.price_in_per_mtok,
                                    "output": c.price_out_per_mtok,
                                    "cacheRead": c.price_in_per_mtok,
                                    "cacheWrite": c.price_in_per_mtok,
                                },
                            }
                        ],
                    }
                }
            }
            Path(d, "models.json").write_text(json.dumps(models, indent=2), encoding="utf-8")
        return d

    def _command(self, prompt: str) -> list[str]:
        c = self.config
        cmd = [
            c.binary, "-p", "--mode", "json",
            "--no-session", "--yolo",
            "--no-extensions", "--no-skills", "--no-prompt-templates",
            "--tools", c.tools,
            "--model", c.model,
        ]
        if c.provider or c.base_url:
            cmd += ["--provider", c.provider or "custom"]
        if c.thinking:
            cmd += ["--thinking", c.thinking]
        cmd.append(prompt)
        return cmd

    def run(self, prompt: str, *, workdir: Path | None = None) -> Trajectory:
        c = self.config
        agent_dir = self._agent_dir()
        env = {**os.environ, "PI_CODING_AGENT_DIR": agent_dir}
        state = _RunState(pending={}, tool_calls=[])
        prices = (c.price_in_per_mtok, c.price_out_per_mtok)
        stderr_file = tempfile.TemporaryFile()
        start = time.time()

        proc = subprocess.Popen(
            self._command(prompt),
            cwd=str(workdir) if workdir else None,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        lines: queue.Queue[str | None] = queue.Queue()

        def _pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.put(line)
            lines.put(None)

        pump = threading.Thread(target=_pump, daemon=True)
        pump.start()

        killed: str | None = None
        while True:
            try:
                line = lines.get(timeout=0.5)
            except queue.Empty:
                line = ""
            if line is None:
                break
            if line.strip():
                try:
                    apply_event(state, json.loads(line), time.time(), prices)
                except json.JSONDecodeError:
                    log.debug("pi non-JSON line: %s", line.rstrip()[:200])

            if c.max_cost_usd is not None and state.cost_usd > c.max_cost_usd:
                killed = "budget_exceeded"
            elif c.max_tokens is not None and state.input_tokens + state.output_tokens > c.max_tokens:
                killed = "token_limit"
            elif time.time() - start > c.timeout_s:
                killed = "timeout"
            if killed:
                log.warning("Stopping pi run: %s (cost $%.4f, %d tokens)", killed, state.cost_usd,
                            state.input_tokens + state.output_tokens)
                proc.kill()
                break

        proc.wait()
        pump.join(timeout=5)
        if proc.stdout:
            proc.stdout.close()
        total_ms = (time.time() - start) * 1000
        stderr_file.seek(0)
        stderr = stderr_file.read().decode("utf-8", "replace")
        stderr_file.close()
        shutil.rmtree(agent_dir, ignore_errors=True)

        # Startup / auth failures are harness errors, not agent behaviour.
        if not killed and proc.returncode != 0 and not state.tool_calls and not state.final_response:
            raise RuntimeError(
                f"pi exited {proc.returncode}: {state.fatal_error or stderr.strip()[-500:] or 'no output'}"
            )

        return Trajectory(
            prompt=prompt,
            tool_calls=state.tool_calls,
            final_response=state.final_response,
            total_latency_ms=total_ms,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            cost_usd=state.cost_usd,
            stop_reason=killed or state.stop_reason or ("error" if state.fatal_error else ""),
        )
