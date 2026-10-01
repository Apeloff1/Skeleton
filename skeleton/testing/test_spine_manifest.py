from __future__ import annotations

from skeleton.persistence.spine_manifest import SpineManifest


def test_manifest_lists_seams_without_signoff() -> None:
    card = SpineManifest().card()
    assert card["count"] == 57
    assert card["apply_landed"] is False
    assert card["poison_apply_landed"] is True
    assert card["hit"] is False
    assert card["completion_checkbox"] is False
    names = [row["name"] for row in card["seams"]]
    assert "hold" in names
    assert "replay" in names
    assert "poison-apply" in names
    assert "poison-chain" in names
    assert "dispatch-guard" in names
    assert "index-bind" in names
    assert "cut-gate" in names
    assert "provider-probe" in names
    assert "pr-probe" in names
    assert "unread-gap" in names
    assert "surface-seal" in names
    assert "ci-witness" in names
    assert "merge-gate" in names
    assert "motor-witness" in names
    assert "dispatch-witness" in names
    assert "dark" in names
    assert "epoch-witness" in names
    assert "quiet" in names
    assert "quiet-witness" in names
    assert "bind-card" in names
    assert "bind-journal" in names
    assert "bind-read" in names
    assert "bind-chain" in names
    assert "bind-tenant" in names
    assert "bind-replay" in names
    assert "bind-surface" in names
    assert "bind-gap" in names
    assert "bind-snapshot" in names
    assert "bind-recovery" in names
    assert "bind-checkpoint" in names
    assert "bind-checkpoint-replay" in names
    assert "bind-checkpoint-tenant" in names
    assert "bind-checkpoint-chain" in names
    assert "bind-bundle" in names
    assert "bind-bundle-verify" in names
