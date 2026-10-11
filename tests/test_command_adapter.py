"""The generic command adapter, driven by a tiny scripted 'agent' ($0)."""

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from agent_mark.adapters.command import CommandAgent
from agent_mark.harness.runner import load_task, run_task

TASK = Path(__file__).resolve().parent.parent / "agent_mark" / "tasks" / "coding" / "coding_001.yaml"

FIXER = textwrap.dedent('''
    import json, pathlib
    p = pathlib.Path("pager.py")
    src = p.read_text()
    print(json.dumps({"type": "tool_call", "name": "read", "args": {"path": "pager.py"}, "result": {"text": src[:20]}, "latency_ms": 1}))
    src = src.replace("start = page * per_page", "start = (page - 1) * per_page")
    src = src.replace("return n_items // per_page", "return -(-n_items // per_page)")
    p.write_text(src)
    print(json.dumps({"type": "tool_call", "name": "edit", "args": {"path": "pager.py"}, "result": {"text": "ok"}, "latency_ms": 1}))
    print(json.dumps({"type": "usage", "input_tokens": 500, "output_tokens": 50, "cost_usd": 0.001}))
    print(json.dumps({"type": "final", "text": "fixed"}))
''')


class TestCommandAdapter(unittest.TestCase):
    def test_event_protocol_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp, "fixer.py")
            script.write_text(FIXER)
            agent = CommandAgent(f"{sys.executable} {script} {{prompt}}")
            result = run_task(load_task(TASK), agent, results_dir=Path(tmp, "out"))
        self.assertIsNone(result["error"])
        self.assertEqual(result["judge_result"]["success"], 1, result["judge_result"])
        self.assertEqual([tc["name"] for tc in result["trajectory"]["tool_calls"]], ["read", "edit"])
        self.assertEqual(result["scores"]["tool_correctness"], 1.0)
        self.assertAlmostEqual(result["cost_usd"], 0.001)

    def test_black_box_stdout(self):
        agent = CommandAgent(f"{sys.executable} -c \"print('hello')\" {{prompt}}")
        t = agent.run("anything")
        self.assertEqual((t.final_response, t.tool_calls), ("hello", []))

    def test_noop_agent_fails_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = CommandAgent(f"{sys.executable} -c pass {{prompt}}")
            result = run_task(load_task(TASK), agent, results_dir=tmp)
        self.assertEqual(result["judge_result"]["success"], 0)


if __name__ == "__main__":
    unittest.main()
