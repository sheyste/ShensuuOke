"""Pure helpers for turning timed syllables into display lines and finding the current one."""
from __future__ import annotations
from bisect import bisect_right
from dataclasses import dataclass

MAX_LINE_CHARS = 48


@dataclass
class LyricEvent:
    time: float
    text: str
    new_line: bool = False   # starts a new display line


def build_lines(events) -> list[list]:
    lines, cur, chars = [], [], 0
    for e in events:
        if e.new_line and cur:
            lines.append(cur); cur, chars = [], 0
        cur.append(e)
        chars += len(e.text)
        if chars >= MAX_LINE_CHARS and e.text.endswith(" "):   # files without line markers
            lines.append(cur); cur, chars = [], 0
    if cur:
        lines.append(cur)
    return lines


def locate(lines, t: float):
    """Return (line_index, syllable_index) of the last syllable with time <= t, or (-1, -1)."""
    if not lines:
        return -1, -1
    starts = [ln[0].time for ln in lines]
    li = bisect_right(starts, t) - 1
    if li < 0:
        return -1, -1
    times = [e.time for e in lines[li]]
    return li, bisect_right(times, t) - 1
