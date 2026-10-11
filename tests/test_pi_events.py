"""Unit tests for parsing pi's JSON event stream (no binary, no network)."""

import unittest

from agent_mark.adapters.pi import _RunState, apply_event


def assistant_end(text="", inp=100, out=10, cost=0.0, stop="stop"):
    return {"type": "message_end", "message": {
        "role": "assistant", "content": [{"type": "text", "text": text}] if text else [],
        "usage": {"input": inp, "output": out, "cacheRead": 0, "cacheWrite": 0, "cost": {"total": cost}},
        "stopReason": stop}}


class TestApplyEvent(unittest.TestCase):
    def setUp(self):
        self.s = _RunState(pending={}, tool_calls=[])

    def test_tool_call_roundtrip(self):
        apply_event(self.s, {"type": "tool_execution_start", "toolCallId": "1", "toolName": "read",
                             "args": {"path": "a.py"}}, now=10.0)
        apply_event(self.s, {"type": "tool_execution_end", "toolCallId": "1", "toolName": "read",
                             "result": {"content": [{"type": "text", "text": "x = 1"}]}, "isError": False},
                    now=10.25)
        tc = self.s.tool_calls[0]
        self.assertEqual((tc.name, tc.args, tc.result["text"], tc.result["is_error"]), ("read", {"path": "a.py"}, "x = 1", False))
        self.assertAlmostEqual(tc.latency_ms, 250.0)

    def test_tool_error_flag(self):
        apply_event(self.s, {"type": "tool_execution_start", "toolCallId": "1", "toolName": "bash", "args": {}}, 0)
        apply_event(self.s, {"type": "tool_execution_end", "toolCallId": "1", "toolName": "bash",
                             "result": {"content": []}, "isError": True}, 1)
        self.assertTrue(self.s.tool_calls[0].result["is_error"])

    def test_usage_and_cost_accumulate(self):
        apply_event(self.s, assistant_end(inp=100, out=10, cost=0.01, stop="toolUse"), 0)
        apply_event(self.s, assistant_end("done", inp=200, out=20, cost=0.02), 0)
        self.assertEqual((self.s.input_tokens, self.s.output_tokens), (300, 30))
        self.assertAlmostEqual(self.s.cost_usd, 0.03)
        self.assertEqual(self.s.final_response, "done")
        self.assertEqual(self.s.stop_reason, "stop")

    def test_fallback_pricing_when_unpriced(self):
        apply_event(self.s, assistant_end(inp=1_000_000, out=1_000_000, cost=0.0), 0, prices=(0.1, 0.5))
        self.assertAlmostEqual(self.s.cost_usd, 0.6)

    def test_user_messages_ignored(self):
        apply_event(self.s, {"type": "message_end", "message": {"role": "user", "content": "hi"}}, 0)
        self.assertEqual(self.s.input_tokens, 0)

    def test_fatal_error(self):
        apply_event(self.s, {"type": "error", "code": "auth.missing_api_key", "message": "no key"}, 0)
        self.assertIn("auth.missing_api_key", self.s.fatal_error)


if __name__ == "__main__":
    unittest.main()
