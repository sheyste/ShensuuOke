from app.utils.lyrics import LyricEvent
from app.utils.lyrics import build_lines, locate

def ev(t, s, nl=False): return LyricEvent(t, s, nl)

def test_lines_and_locate():
    evs = [ev(1, "Hel"), ev(2, "lo "), ev(3, "World", True), ev(4, "!")]
    lines = build_lines(evs); assert [len(l) for l in lines] == [2, 2]
    assert locate(lines, 0.5) == (-1, -1) and locate(lines, 1.5) == (0, 0)
    assert locate(lines, 3.0) == (1, 0) and locate(lines, 99) == (1, 1)

def test_long_line_without_markers_is_wrapped():
    evs = [ev(i, "word ") for i in range(30)]; assert len(build_lines(evs)) > 2
