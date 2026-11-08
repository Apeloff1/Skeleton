"""Static pinned-backend Docker compatibility gate, not actual runtime qualification."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_all_backend_python_image_stages_compatible_and_same_digest():
    source = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    bases = re.findall(
        r"^FROM python:(3\.\d+)-alpine@sha256:([0-9a-f]{64}) AS (builder|runtime-source|production)$",
        source, re.MULTILINE,
    )
    assert len(bases) == 3
    assert {stage for _, _, stage in bases} == {"builder", "runtime-source", "production"}
    assert len({(version, digest) for version, digest, _ in bases}) == 1
    version = tuple(map(int, bases[0][0].split(".")))
    assert (3, 10) <= version < (3, 15)
    assert "backend dependencies require supported Python <3.15" in source


def test_production_pip_cleanup_rejects_unknown_python_layout():
    source = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    assert 'sysconfig.get_path("purelib")' in source
    assert 'unexpected Python site-packages path; refusing runtime pip cleanup' in source
    assert "ENVIRONMENT=production" in source
