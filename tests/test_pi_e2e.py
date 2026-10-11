"""
End-to-end: the real pi binary, driven by the scripted fake LLM, through the full
harness. Costs $0. Skipped unless a pi binary is available (PI_BINARY or on PATH).
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from agent_mark.adapters.pi import PiAgent, PiConfig
from agent_mark.harness.runner import load_task, run_task
from tests.fake_llm import FakeLLM

PI = os.environ.get("PI_BINARY") or shutil.which("pi")
TASK = Path(__file__).resolve().parent.parent / "agent_mark" / "tasks" / "coding" / "coding_001.yaml"

FIX_PAGER = [
    {"tool_calls": [{"name": "read", "arguments": {"path": "pager.py"}}]},
    {"tool_calls": [{"name": "edit", "arguments": {
        "path": "pager.py", "oldText": "start = page * per_page", "newText": "start = (page - 1) * per_page"}}]},
    {"tool_calls": [{"name": "edit", "arguments": {
        "path": "pager.py", "oldText": "return n_items // per_page", "newText": "return -(-n_items // per_page)"}}]},
    {"content": "Fixed both pagination bugs."},
]


def agent(url, **kw):
    os.environ["FAKE_LLM_KEY"] = "sk-fake"
    return PiAgent(PiConfig(model="fake-model", provider="litellm", base_url=url, api_key_env="FAKE_LLM_KEY",
                            binary=PI, price_in_per_mtok=1.0, price_out_per_mtok=5.0, timeout_s=60, **kw))


@unittest.skipUnless(PI, "pi binary not available (set PI_BINARY)")
class TestPiEndToEnd(unittest.TestCase):
    def test_solves_task_and_tracks_cost(self):
        with FakeLLM(FIX_PAGER, prompt_tokens=1000, completion_tokens=50) as url, tempfile.TemporaryDirectory() as out:
            result = run_task(load_task(TASK), agent(url), results_dir=out)
        self.assertIsNone(result["error"])
        self.assertEqual(result["judge_result"]["success"], 1, result["judge_result"])
        self.assertEqual([t["name"] for t in result["trajectory"]["tool_calls"]], ["read", "edit", "edit"])
        self.assertEqual(result["judge_result"]["changed_files"], ["pager.py"])
        # 4 model turns x (1000 in @ $1/M + 50 out @ $5/M)
        self.assertAlmostEqual(result["cost_usd"], 4 * (0.001 + 0.00025), places=6)
        self.assertEqual(result["trajectory"]["input_tokens"], 4000)

    def test_budget_guard_kills_runaway_agent(self):
        loop = [{"tool_calls": [{"name": "bash", "arguments": {"command": "echo again"}}]}]
        # each turn: 100k tokens @ $1/M = $0.10 -> must be killed shortly after $0.25
        with FakeLLM(loop, prompt_tokens=100_000, completion_tokens=0) as url:
            t = agent(url, max_cost_usd=0.25).run("loop forever", workdir=Path(tempfile.mkdtemp()))
        self.assertEqual(t.stop_reason, "budget_exceeded")
        self.assertLessEqual(t.cost_usd, 0.35)

    def test_token_guard(self):
        loop = [{"tool_calls": [{"name": "bash", "arguments": {"command": "echo again"}}]}]
        with FakeLLM(loop, prompt_tokens=50_000, completion_tokens=0) as url:
            t = agent(url, max_cost_usd=None, max_tokens=120_000).run("loop", workdir=Path(tempfile.mkdtemp()))
        self.assertEqual(t.stop_reason, "token_limit")

    def test_task_failure_is_scored_not_crashed(self):
        give_up = [{"content": "I could not find the bug."}]
        with FakeLLM(give_up) as url, tempfile.TemporaryDirectory() as out:
            result = run_task(load_task(TASK), agent(url), results_dir=out)
        self.assertIsNone(result["error"])
        self.assertEqual(result["judge_result"]["success"], 0)


if __name__ == "__main__":
    unittest.main()
