"""A declaration is not runtime evidence; inventory never imports source."""
from pathlib import Path
from types import SimpleNamespace

from gameforge.coverage_inventory import ScanLimits, scan_source, route_registration


def test_non_executable_inventory_with_exact_digests(tmp_path):
    (tmp_path / "alpha.py").write_text("raise RuntimeError('do not import')\nclass AlphaEngine: pass\n")
    (tmp_path / "notes.py").write_text('"""class PretendEngine: pass"""\n')
    (tmp_path / "invalid.py").write_text("class:")
    first = scan_source(tmp_path)
    assert [row["module"] for row in first["modules"]] == ["gameforge.alpha"]
    assert first["modules"][0]["classes"] == ["AlphaEngine"]
    assert not first["complete"]
    assert first["skipped_count"] == 1
    (tmp_path / "alpha.py").write_text("class AlphaEngine: pass\n")
    second = scan_source(tmp_path)
    assert first["inventory_sha256"] != second["inventory_sha256"]


def test_scan_limits_and_symlinks(tmp_path):
    (tmp_path / "a.py").write_text("class AEngine: pass")
    (tmp_path / "b.py").write_text("class BEngine: pass")
    result = scan_source(tmp_path, ScanLimits(files=1))
    assert not result["complete"]
    assert result["stop_reason"] == "file_or_time_budget"
    assert result["files_examined"] == 1
    result = scan_source(tmp_path, ScanLimits(file_bytes=4))
    assert result["skipped_count"] == 2 and not result["modules"]


def test_registration_uses_path_boundary_not_prefix_spoof():
    routes = [SimpleNamespace(path="/api/foo/bar", methods={"GET"}),
              SimpleNamespace(path="/api/foobar", methods={"GET"}),
              SimpleNamespace(path="/api/no-method", methods=None)]
    results = route_registration(routes, [("yes", "/api/foo"), ("no", "/api/fo"),
                                          ("no-method", "/api/no-method")])
    assert [row["ok"] for row in results] == [True, False, False]
    assert all(not row["runtime_verified"] for row in results)
