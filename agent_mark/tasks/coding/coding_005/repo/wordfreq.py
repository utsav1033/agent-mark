"""Count word frequencies in a text file."""

import argparse
import re
import sys
from collections import Counter


def count_words(text: str) -> Counter:
    return Counter(re.findall(r"[a-z']+", text.lower()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="text file to analyse")
    args = parser.parse_args(argv)

    with open(args.path, encoding="utf-8") as f:
        counts = count_words(f.read())

    for word, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"{word} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
