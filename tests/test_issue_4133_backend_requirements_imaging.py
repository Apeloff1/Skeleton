"""backend/requirements.txt pins imageio and scipy exactly once, no conflicting specs."""
import re
from pathlib import Path

REQ = Path(__file__).resolve().parents[1] / "backend" / "requirements.txt"


def _pins():
    out = {}
    for line in REQ.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        m = re.match(r"^([A-Za-z0-9_.\-]+)(\[.*\])?\s*(==|>=|~=)\s*(\S+)$", line)
        if m:
            out.setdefault(m.group(1).lower().replace("_", "-"), []).append(m.group(4))
    return out


def test_imageio_and_scipy_pinned_once():
    pins = _pins()
    for name in ("imageio", "scipy"):
        assert len(pins.get(name, [])) == 1, (name, pins.get(name))
    assert "==" in REQ.read_text().split("imageio", 1)[1].splitlines()[0]
