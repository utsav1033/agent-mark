"""
Synthetic trajectory fixtures — scorer development and demonstration only.

SYNTHETIC DATA. Not real benchmark results. Never use these numbers in
benchmark tables or comparisons with live adapter runs.

Usage:
    from agent_mark.fixtures import FIXTURES
    from agent_mark.harness.scorer import score

    for fx in FIXTURES:
        s = score(fx["trajectory"], fx["task"])
        print(fx["id"], s)
"""

from agent_mark.fixtures.synthetic_gmail import FIXTURES

__all__ = ["FIXTURES"]
