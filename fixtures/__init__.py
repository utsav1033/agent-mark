"""
Synthetic trajectory fixtures — scorer development and demonstration only.

SYNTHETIC DATA. Not real benchmark results. Never use these numbers in
benchmark tables or comparisons with live adapter runs.

Usage:
    from fixtures import FIXTURES
    from harness.scorer import score

    for fx in FIXTURES:
        s = score(fx["trajectory"], fx["task"])
        print(fx["id"], s)
"""

from fixtures.synthetic_gmail import FIXTURES

__all__ = ["FIXTURES"]
