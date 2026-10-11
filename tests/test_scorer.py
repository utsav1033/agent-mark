import unittest

from agent_mark.adapters.base import ToolCall, Trajectory
from agent_mark.harness.scorer import score


def traj(*names, errors=()):
    return Trajectory(prompt="p", tool_calls=[
        ToolCall(n, {}, {"is_error": i in errors, "text": ""}, 1.0) for i, n in enumerate(names)])


class TestScorer(unittest.TestCase):
    def test_scores(self):
        task = {"expected_tools": ["edit", "write"], "min_tool_calls": 2, "max_tool_calls": 3}
        s = score(traj("read", "edit", "bash", "bash", errors={2}), task)
        self.assertEqual(s["tool_correctness"], 1.0)
        self.assertEqual(s["efficiency"], 0.5)
        self.assertEqual(s["tool_error_rate"], 0.25)
        self.assertEqual(s["within_max_calls"], 0.0)

    def test_wrong_tools_and_no_calls(self):
        s = score(traj(), {"expected_tools": ["edit"]})
        self.assertEqual((s["tool_correctness"], s["efficiency"], s["tool_error_rate"]), (0.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
