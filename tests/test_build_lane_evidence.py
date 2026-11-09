"""#807 B001-B010 build-lane structural evidence audit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skeleton.repo_intelligence import build_lane_evidence as ble

ROOT = Path(__file__).resolve().parents[1]


def test_current_main_build_lane_evidence_is_complete() -> None:
    report = ble.audit()
    rec = report.to_record()
    assert [b["batch_id"] for b in rec["batches"]] == list(ble.BUILD_LANE)
    assert report.ok, [b for b in rec["batches"] if not b["ok"]]
    assert all(b["title"] for b in rec["batches"])


def test_priority_batches_are_covered() -> None:
    assert set(ble.PRIORITY) <= {e.batch_id for e in ble.DEFAULT_EVIDENCE}
    assert ble.audit(batches=ble.PRIORITY).ok


def test_report_digest_is_canonical_and_deterministic() -> None:
    a, b = ble.audit().to_record(), ble.audit().to_record()
    assert a == b
    body = {k: v for k, v in a.items() if k != "digest"}
    assert a["digest"] == hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_mirror_is_byte_identical() -> None:
    src = ROOT / "skeleton/repo_intelligence/build_lane_evidence.py"
    dst = ROOT / "skeleton/ai/build/repo_intelligence/build_lane_evidence.py"
    assert src.read_bytes() == dst.read_bytes()


def test_missing_symbol_and_file_fail_closed(tmp_path: Path) -> None:
    spec = ble.BatchEvidence("B005", {"skeleton.build.parallel_scheduler": ("NoSuchThing",)}, tests=("nope/test_x.py",))
    res = ble.audit_batch(spec, root=tmp_path)
    assert not res.ok
    assert any("NoSuchThing" in p for p in res.problems) and any("nope/test_x.py" in p for p in res.problems)


def test_import_failure_fails_closed(tmp_path: Path) -> None:
    res = ble.audit_batch(ble.BatchEvidence("B009", {"skeleton.build.does_not_exist": ()}), root=tmp_path)
    assert not res.ok and "ModuleNotFoundError" in res.problems[0]


def test_mirror_drift_detected(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("x = 2\n")
    res = ble.audit_batch(ble.BatchEvidence("B007", {}, mirrors=(("a.py", "b.py"),)), root=tmp_path)
    assert res.problems == ["mirror drift a.py != b.py"]
    (tmp_path / "b.py").write_text("x = 1\n")
    assert ble.audit_batch(ble.BatchEvidence("B007", {}, mirrors=(("a.py", "b.py"),)), root=tmp_path).ok


def test_empty_spec_is_not_ok(tmp_path: Path) -> None:
    assert not ble.audit_batch(ble.BatchEvidence("B004", {}), root=tmp_path).ok


def test_missing_specification_is_reported() -> None:
    report = ble.audit(evidence=(), batches=("B004",))
    assert not report.ok and report.results[0].problems == ["no evidence specification"]


@pytest.mark.parametrize("bad", ["/etc/passwd", "../x.py", ""])
def test_paths_must_be_repo_relative(bad: str) -> None:
    with pytest.raises(ble.BuildLaneEvidenceError):
        ble.BatchEvidence("B001", {}, tests=(bad,))


def test_non_build_lane_ids_rejected() -> None:
    with pytest.raises(ble.BuildLaneEvidenceError):
        ble.BatchEvidence("B011", {})
    with pytest.raises(ble.BuildLaneEvidenceError):
        ble.audit(batches=("B042",))


def test_cli(capsys) -> None:
    assert ble.main(["B004", "B009"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [b["batch_id"] for b in out["batches"]] == ["B004", "B009"]
