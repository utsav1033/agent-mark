"""Find free meeting slots. Times are minutes since midnight; intervals are
half-open [start, end)."""


def free_slots(
    busy: list[tuple[int, int]],
    day_start: int,
    day_end: int,
    min_minutes: int = 30,
) -> list[tuple[int, int]]:
    slots = []
    cursor = day_start
    for start, end in busy:
        if start - cursor >= min_minutes:
            slots.append((cursor, start))
        cursor = end
    if day_end - cursor >= min_minutes:
        slots.append((cursor, day_end))
    return slots
