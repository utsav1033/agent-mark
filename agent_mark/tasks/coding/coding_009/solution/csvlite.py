"""Minimal CSV reader for our export format."""


def parse_line(line: str) -> list[str]:
    """Split one CSV line (without its trailing newline) into fields."""
    fields: list[str] = []
    buf: list[str] = []
    i, n = 0, len(line)
    in_quotes = False
    while i < n:
        ch = line[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < n and line[i + 1] == '"':
                    buf.append('"')
                    i += 1
                else:
                    in_quotes = False
            else:
                buf.append(ch)
        elif ch == '"' and not buf:
            in_quotes = True
        elif ch == ",":
            fields.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    if in_quotes:
        raise ValueError("unterminated quoted field")
    fields.append("".join(buf))
    return fields
