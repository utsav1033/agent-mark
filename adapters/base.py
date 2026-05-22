from __future__ import annotations

from dataclasses import dataclass, field
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


@runtime_checkable
class Agent(Protocol):
    """Every adapter must implement this single method."""

    def run(self, prompt: str) -> Trajectory:
        ...
