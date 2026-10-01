from __future__ import annotations

from skeleton.persistence.spine_manifest import SpineManifest


def test_manifest_lists_seams_without_signoff() -> None:
    card = SpineManifest().card()
    assert card["count"] == 22
    assert card["apply_landed"] is False
    assert card["poison_apply_landed"] is True
    assert card["hit"] is False
    assert card["completion_checkbox"] is False
    names = [row["name"] for row in card["seams"]]
    assert "hold" in names
    assert "replay" in names
    assert "poison-apply" in names
