"""Source-lease pinning prevents a stale operator handoff from passing recovery."""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.worlds.laptop_recovery_check import inspect_recovery, main
from skeleton.jeeves.worlds.world_canon import CanonError
from skeleton.testing.test_jeeves_world_laptop_flow import ready


def test_exact_digest_accepts_read_only_snapshot(tmp_path):
    _, _, reviewed, _ = ready(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    report = inspect_recovery(tmp_path, "lighthouse", expected_source_digest=reviewed["source_digest"])
    assert report["source_handoff_verified"] is True
    assert report["expected_source_digest"] == reviewed["source_digest"]
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before


def test_stale_digest_fails_closed_without_changing_artifacts(tmp_path):
    ready(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    report = inspect_recovery(tmp_path, "lighthouse", expected_source_digest="0" * 64)
    assert report["source_handoff_verified"] is False
    assert report["checks"]["source_lease"]["error"] == "source_digest_mismatch"
    assert report["next_action"] == "restart_diagnostic_after_source_change"
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before


@pytest.mark.parametrize("invalid", ["", "a" * 63, "A" * 64, "../world", "z" * 64])
def test_malformed_digest_is_rejected_before_store_access(tmp_path, invalid):
    with pytest.raises(CanonError, match="expected_source_digest_invalid"):
        inspect_recovery(tmp_path / "nonexistent", "lighthouse", expected_source_digest=invalid)
    assert not (tmp_path / "nonexistent").exists()


def test_cli_stale_digest_exits_nonzero_with_bounded_json(tmp_path, capsys):
    ready(tmp_path)
    code = main(["--store", str(tmp_path), "--world-id", "lighthouse",
                 "--expect-source-digest", "0" * 64])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_handoff_verified"] is False
    assert payload["checks"]["source_lease"]["ok"] is False
