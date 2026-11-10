"""Exact-owner AI-tree retained roots and host-portable native acceptance fixture."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def test_retained_non_ai_roots_have_explicit_canonical_owner():
    metadata = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    rows = metadata["retained_outside_ai_tree"]
    for path in ("skeleton/mass_build", "skeleton/perf_profiler"):
        matches = [entry for entry in rows if entry.get("path") == path]
        assert len(matches) == 1
        assert matches[0]["owner"] and matches[0]["reason"]
        assert (ROOT / path).is_dir()


def test_native_http_fixture_has_no_runner_specific_absolute_directory():
    source = (ROOT / "skeleton/testing/test_ai_flight_http.py").read_text(encoding="utf-8")
    assert "tempfile.TemporaryDirectory(prefix='ai-flight-http-'" in source
    assert "dir='/home/oai'" not in source
