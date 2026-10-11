"""Minimal CSV reader for our export format (the csv module is not available
on the embedded target this runs on)."""


def parse_line(line: str) -> list[str]:
    """Split one CSV line (without its trailing newline) into fields."""
    return line.split(",")
