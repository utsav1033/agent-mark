"""
Generic adapter: benchmark ANY agent that can be launched as a shell command.

    agent-mark run --adapter command --agent-cmd "my-agent --prompt {prompt}" --suite coding

`{prompt}` is replaced by the task prompt (as a single argument). The command runs
inside the task workspace (for coding tasks) and its stdout is read.

Two levels of observability:

1. Black box (zero integration): stdout is taken as the final response. Task
   success, latency are scored; tools/tokens/cost are reported as 0.

2. agent-mark event protocol (a few print statements in your agent): emit JSON
   lines on stdout and the full trajectory is scored:

     {"type": "tool_call", "name": "read", "args": {...}, "result": {...}, "latency_ms": 12.5}
     {"type": "usage", "input_tokens": 1200, "output_tokens": 80, "cost_usd": 0.0004}
     {"type": "final", "text": "Fixed the bug in pager.py"}

   `usage` lines are summed. Non-JSON lines are ignored once any event is seen.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time
from pathlib import Path

from agent_mark.adapters.base import ToolCall, Trajectory


class CommandAgent:
    def __init__(self, command: str, timeout_s: float = 300.0) -> None:
        if "{prompt}" not in command:
            raise ValueError("--agent-cmd must contain the {prompt} placeholder")
        self.command = command
        self.timeout_s = timeout_s

    def _argv(self, prompt: str) -> list[str]:
        return [part.replace("{prompt}", prompt) for part in shlex.split(self.command)]

    def run(self, prompt: str, *, workdir: Path | None = None) -> Trajectory:
        start = time.time()
        stop_reason = ""
        try:
            proc = subprocess.run(
                self._argv(prompt), cwd=workdir, capture_output=True, text=True, timeout=self.timeout_s,
                stdin=subprocess.DEVNULL,
            )
            stdout, code = proc.stdout, proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            code, stop_reason = None, "timeout"
        total_ms = (time.time() - start) * 1000

        traj = Trajectory(prompt=prompt, total_latency_ms=total_ms, stop_reason=stop_reason)
        saw_event = False
        final_parts: list[str] = []
        for line in stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                final_parts.append(line)
                continue
            if not isinstance(ev, dict) or ev.get("type") not in {"tool_call", "usage", "final"}:
                final_parts.append(line)
                continue
            saw_event = True
            if ev["type"] == "tool_call":
                traj.tool_calls.append(ToolCall(
                    name=str(ev.get("name", "?")), args=ev.get("args") or {},
                    result=ev.get("result"), latency_ms=float(ev.get("latency_ms", 0.0)),
                ))
            elif ev["type"] == "usage":
                traj.input_tokens += int(ev.get("input_tokens", 0))
                traj.output_tokens += int(ev.get("output_tokens", 0))
                traj.cost_usd += float(ev.get("cost_usd", 0.0))
            else:
                traj.final_response = str(ev.get("text", ""))

        if not saw_event:
            traj.final_response = stdout.strip()
        elif not traj.final_response:
            traj.final_response = "\n".join(final_parts).strip()
        if code not in (0, None) and not stop_reason:
            traj.stop_reason = f"exit_{code}"
        return traj
