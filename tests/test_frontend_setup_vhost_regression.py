"""Production frontend vhost must have one fail-closed setup route."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_first_install_setup_has_one_fail_closed_exact_location():
    source = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    blocks = re.findall(r"(?ms)^\s*location\s+=\s+/setup\s*\{(.*?)^    \}", source)
    assert len(blocks) == 1
    setup = blocks[0]
    assert "try_files /setup.html /setup/index.html =404;" in setup
    assert 'add_header Cache-Control "no-store" always;' in setup
    assert 'add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;' in setup
