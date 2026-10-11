from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class ToolCall:
    name: str
    args: dict
    result: dict | None
    latency_ms: float


@dataclass
class Trajectory:
    prompt: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    final_response: str = ""
    total_latency_ms: float = 0.0
    input_tokens: int = 0   # 0 if adapter cannot expose this
    output_tokens: int = 0  # 0 if adapter cannot expose this
    cost_usd: float = 0.0   # 0.0 if adapter cannot price the run
    stop_reason: str = ""   # adapter-specific, e.g. "end_turn", "budget_exceeded", "timeout"


@runtime_checkable
class Agent(Protocol):
    """Every adapter must implement this single method.

    Adapters that operate on files (coding agents) also accept a keyword-only
    ``workdir``: the runner passes a fresh scratch copy of the task's workspace
    and the agent must do all its work inside it. Adapters without file access
    may ignore workspace tasks; the runner records a clear error for them.
    """

    def run(self, prompt: str, *, workdir: Path | None = None) -> Trajectory:
        ...
