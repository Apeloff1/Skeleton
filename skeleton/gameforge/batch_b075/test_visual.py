import pytest

from skeleton.gameforge.batch_b071 import SimContext
from skeleton.gameforge.batch_b075 import Capture, CaptureError, VisualSuite, render_scene


def _draw(ctx, x, y):
    v = (x * 30 + y * 20 + ctx.clock.tick) % 256
    return (v, v, 255 - v)


def _cap(tick=5, draw=_draw):
    ctx = SimContext(seed=1)
    ctx.clock.advance(tick)
    return render_scene(ctx, 4, 3, draw)


def test_deterministic_capture():
    assert _cap().digest == _cap().digest


def test_detects_change_with_bbox():
    s = VisualSuite()
    s.approve("hud", _cap())
    bug = lambda ctx, x, y: (0, 0, 0) if (x, y) == (2, 1) else _draw(ctx, x, y)
    d = s.compare("hud", _cap(draw=bug))
    assert not d.passed and d.bbox == (2, 1, 2, 1)


def test_tolerance_and_fraction():
    s = VisualSuite(tolerance=2, max_changed_fraction=0.1)
    s.approve("a", _cap())
    nudge = lambda ctx, x, y: tuple(min(255, c + 1) for c in _draw(ctx, x, y))
    assert s.compare("a", _cap(draw=nudge)).passed


def test_tick_and_missing_golden():
    s = VisualSuite()
    s.approve("a", _cap(5))
    assert "tick" in s.compare("a", _cap(6)).reason
    assert s.compare("b", _cap()).reason == "no golden"


def test_bad_capture():
    with pytest.raises(CaptureError):
        Capture(2, 2, ((0, 0, 0),), 0)
    with pytest.raises(CaptureError):
        _cap(draw=lambda c, x, y: (300, 0, 0))
