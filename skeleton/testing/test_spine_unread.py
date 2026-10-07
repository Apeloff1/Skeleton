from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.persistence.spine_provider_probe import SpineProviderProbe, SpineProviderProbeError
from skeleton.persistence.spine_pr_probe import SpinePrProbe, SpinePrProbeError
from skeleton.persistence.spine_surface_seal import SpineSurfaceSeal
from skeleton.persistence.spine_unread_gap import SpineUnreadGap


def test_provider_probe_stays_unclaimed(tmp_path: Path) -> None:
    probe = SpineProviderProbe(tmp_path / "provider.sqlite")
    card = probe.probe(tenant_id="house-a", surface="mongo-live")
    assert card["claimed"] == 0
    assert card["green"] is False
    assert card["seq"] == 1
    claim = probe.claim(tenant_id="house-a", surface="motor-bootstrap")
    assert claim["claimed"] == 0
    assert claim["reason"] == "claim-refused"
    assert claim["green"] is False
    read = probe.read("house-a")
    assert read["seen"] == 2
    assert read["claimed"] == 0
    assert read["green"] is False
    verify = probe.verify("house-a")
    assert verify["gaps"] == []
    assert verify["mismatch"] is False
    probe.close()


def test_provider_foreign_tenant_is_empty(tmp_path: Path) -> None:
    probe = SpineProviderProbe(tmp_path / "provider.sqlite")
    probe.probe(tenant_id="house-a", surface="provider-health")
    foreign = probe.read("house-b")
    assert foreign["seen"] == 0
    assert foreign["surfaces"] == []
    gap = SpineUnreadGap(tmp_path / "provider.sqlite", table="spine_provider_probe")
    assert gap.read("house-b")["missing"] == []
    assert gap.read("house-b")["seen"] == []
    gap.close()
    probe.close()


def test_provider_gap_and_rewrite_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "provider.sqlite"
    probe = SpineProviderProbe(path)
    probe.probe(tenant_id="house-a", surface="mongo-live")
    probe.probe(tenant_id="house-a", surface="runtime-dispatcher")
    probe.probe(tenant_id="house-a", surface="provider-health")
    probe.close()
    import sqlite3

    conn = sqlite3.connect(path)
    conn.execute("DELETE FROM spine_provider_probe WHERE tenant_id = ? AND seq = 2", ("house-a",))
    conn.execute(
        "UPDATE spine_provider_probe SET claimed = 1 WHERE tenant_id = ? AND seq = 1",
        ("house-a",),
    )
    conn.commit()
    conn.close()
    gap = SpineUnreadGap(path, table="spine_provider_probe")
    missing = gap.read("house-a")
    assert missing["missing"] == [2]
    assert missing["green"] is False
    gap.close()
    verify = SpineProviderProbe(path).verify("house-a")
    assert verify["mismatch"] is True
    assert 2 in verify["gaps"]
    assert verify["green"] is False


def test_unknown_surface_and_blank_tenant_refused(tmp_path: Path) -> None:
    probe = SpineProviderProbe(tmp_path / "provider.sqlite")
    with pytest.raises(SpineProviderProbeError):
        probe.probe(tenant_id="house-a", surface="live-green")
    with pytest.raises(SpineProviderProbeError):
        probe.claim(tenant_id="  ", surface="mongo-live")
    probe.close()


def test_pr_probe_stays_unclaimed_and_isolated(tmp_path: Path) -> None:
    probe = SpinePrProbe(tmp_path / "pr.sqlite")
    card = probe.probe(tenant_id="house-a", check_name="import-ci")
    assert card["claimed"] == 0
    claim = probe.claim(tenant_id="house-a", check_name="occupied-pr")
    assert claim["green"] is False
    assert claim["reason"] == "claim-refused"
    assert probe.read("house-b")["seen"] == 0
    assert probe.verify("house-a")["mismatch"] is False
    with pytest.raises(SpinePrProbeError):
        probe.probe(tenant_id="house-a", check_name="merge-green")
    probe.close()


def test_seal_strips_forged_green() -> None:
    card = SpineSurfaceSeal().seal(
        {"kind": "spine_provider_probe", "green": True, "seen": 4},
        {"kind": "spine_pr_probe", "pr_automation_green": True, "seen": 2},
    )
    assert card["provider_surface_green"] is False
    assert card["pr_automation_green"] is False
    assert card["ci_green"] is False
    assert card["live_motor"] is False
    assert card["hit"] is False
    assert "provider-green-stripped" in card["stripped"]
    assert "pr-green-stripped" in card["stripped"]
    assert card["completion_checkbox"] is False


def test_unread_gap_rejects_other_tables(tmp_path: Path) -> None:
    from skeleton.persistence.spine_unread_gap import SpineUnreadGapError

    with pytest.raises(SpineUnreadGapError):
        SpineUnreadGap(tmp_path / "no.sqlite", table="spine_poison_apply")
