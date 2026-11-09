from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.persistence.spine_ci_witness import SpineCiWitness
from skeleton.persistence.spine_merge_gate import SpineMergeGate
from skeleton.persistence.spine_pr_probe import CHECKS, SpinePrProbe
from skeleton.persistence.spine_probe_replay import SpineProbeReplay, SpineProbeReplayError
from skeleton.persistence.spine_provider_probe import SpineProviderProbe
from skeleton.persistence.spine_surface_seal import SpineSurfaceSeal


def test_complete_catalog_is_still_not_ci_green(tmp_path: Path) -> None:
    probe = SpinePrProbe(tmp_path / "pr.sqlite")
    for name in CHECKS:
        probe.probe(tenant_id="house-a", check_name=name)
    probe.close()
    witness = SpineCiWitness(tmp_path / "pr.sqlite")
    card = witness.card("house-a")
    assert card["catalog_complete"] is True
    assert card["ci_green"] is False
    assert card["missing"] == []
    assert card["hit"] is False
    foreign = witness.card("house-b")
    assert foreign["seen"] == []
    assert foreign["ci_green"] is False
    witness.close()


def test_merge_stays_refused_when_catalog_is_complete() -> None:
    ci = {"catalog_complete": True, "ci_green": False}
    seal = SpineSurfaceSeal().seal({"kind": "spine_provider_probe", "seen": 1}, {"kind": "spine_pr_probe", "seen": 5})
    card = SpineMergeGate().consider(ci, seal)
    assert card["merged"] is False
    assert card["ci_green"] is False
    assert card["reasons"] == ["merge-not-landed"]
    forged = SpineMergeGate().consider({"catalog_complete": True, "ci_green": True}, seal)
    assert forged["merged"] is False
    assert "forged-ci" in forged["reasons"]
    assert "merge-not-landed" in forged["reasons"]


def test_replay_matches_digest_and_does_not_insert(tmp_path: Path) -> None:
    path = tmp_path / "provider.sqlite"
    probe = SpineProviderProbe(path)
    first = probe.probe(tenant_id="house-a", surface="mongo-live")
    probe.close()
    replay = SpineProbeReplay(path, table="spine_provider_probe")
    card = replay.replay(tenant_id="house-a", seq=1, digest=first["digest"])
    assert card["duplicate"] is True
    assert card["inserted"] is False
    assert card["claimed"] == 0
    with pytest.raises(SpineProbeReplayError):
        replay.replay(tenant_id="house-a", seq=1, digest="0" * 64)
    with pytest.raises(SpineProbeReplayError):
        replay.replay(tenant_id="house-a", seq=2, digest=first["digest"])
    replay.close()
    again = SpineProviderProbe(path)
    assert again.read("house-a")["seen"] == 1
    again.close()
