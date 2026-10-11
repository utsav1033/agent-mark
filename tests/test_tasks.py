"""Every bundled workspace task must fail untouched and pass with its reference solution."""

import unittest
from pathlib import Path

from agent_mark.harness.runner import load_task
from agent_mark.harness.workspace import validate

TASKS = Path(__file__).resolve().parent.parent / "agent_mark" / "tasks"


class TestBundledTasks(unittest.TestCase):
    def test_workspace_tasks_valid(self):
        files = sorted(TASKS.glob("*/*.yaml"))
        checked = 0
        for f in files:
            task = load_task(f)
            if not task.get("workspace"):
                continue
            with self.subTest(task=task["id"]):
                ok, msg = validate(task)
                self.assertTrue(ok, msg)
            checked += 1
        self.assertGreaterEqual(checked, 10)


if __name__ == "__main__":
    unittest.main()
