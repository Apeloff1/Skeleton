"""Source-bound studio manifest verification and release-hold regression tests."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.dual_runtime_verify import (
    DualRuntimeVerificationError, _canonical_bytes, verify_exported_package,
)
from skeleton.testing.test_app_offline_first_playable_batch import original_games


def _reissue_test_manifest(root: Path, *, remove: str | None = None,
                           replace: dict[str, bytes] | None = None) -> str:
    """Recalculate *all* source hashes so negative tests reach policy validation."""
    manifest_path = root / "release.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if remove is not None:
        (root / remove).unlink()
        del manifest["files"][remove]
    for path, data in (replace or {}).items():
        (root / path).write_bytes(data)
        manifest["files"][path] = sha256(data).hexdigest()
    body = {k: v for k, v in manifest.items() if k != "manifest_digest"}
    manifest["manifest_digest"] = canonical_digest(body)
    release = _canonical_bytes(manifest)
    manifest_path.write_bytes(release)
    return sha256(release).hexdigest()


def test_reviewed_studio_source_replays_without_device_or_release_claims(
    original_games,
) -> None:
    root, pin = original_games[0]
    report = verify_exported_package(
        root, expected_manifest_sha256=pin, authorized=True,
    )
    assert report["offline_gameplay_reexecuted"] is True
    assert report["godot_executed"] is False
    assert report["rights_certified"] is False
    assert report["release_certified"] is False


@pytest.mark.parametrize("missing", [
    "studio/pipeline.json",
    "studio/mirror_room.json",
    "studio/consumer_gate.json",
])
def test_studio_source_missing_governed_receipt_fails_after_repin(
    original_games, tmp_path: Path, missing: str,
) -> None:
    root = tmp_path / "detached-studio"
    shutil.copytree(original_games[0][0], root)
    pin = _reissue_test_manifest(root, remove=missing)
    with pytest.raises(DualRuntimeVerificationError, match="missing required studio source"):
        verify_exported_package(root, expected_manifest_sha256=pin, authorized=True)


def test_studio_claiming_publication_authority_fails_even_with_fresh_digest(
    original_games, tmp_path: Path,
) -> None:
    root = tmp_path / "forged-studio"
    shutil.copytree(original_games[0][0], root)
    gate = root / "studio" / "consumer_gate.json"
    review = json.loads(gate.read_text(encoding="utf-8"))
    review["evidence"]["approved_for_publication"] = True
    pin = _reissue_test_manifest(
        root,
        replace={"studio/consumer_gate.json": _canonical_bytes(review)},
    )
    with pytest.raises(DualRuntimeVerificationError, match="release-blocked studio review"):
        verify_exported_package(root, expected_manifest_sha256=pin, authorized=True)
