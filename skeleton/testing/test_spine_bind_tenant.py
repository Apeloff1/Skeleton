from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.persistence.spine_bind_card import SpineBindCard
from skeleton.persistence.spine_bind_gap import SpineBindGap, SpineBindGapError
from skeleton.persistence.spine_bind_journal import SpineBindJournal
from skeleton.persistence.spine_bind_replay import SpineBindReplay, SpineBindReplayError
from skeleton.persistence.spine_bind_surface import SpineBindSurface, SpineBindSurfaceError
from skeleton.persistence.spine_bind_tenant import SpineBindTenant, SpineBindTenantError
from skeleton.persistence.spine_dark import SpineDark
from skeleton.persistence.spine_epoch_witness import SpineEpochWitness
from skeleton.persistence.spine_quiet import SpineQuiet
from skeleton.persistence.spine_quiet_witness import SpineQuietWitness


def _bind(tmp_path: Path, tenant: str = "house-a") -> dict:
    dark = SpineDark().card(
        {"live_motor": False, "driver_imports": 0},
        {"called": False, "dispatcher_running": False},
        {"merged": False, "ci_green": False},
    )
    quiet_path = tmp_path / "quiet.sqlite"
    quiet = SpineQuiet(quiet_path)
    quiet.append(tenant, dark)
    quiet.close()
    witness = SpineQuietWitness(quiet_path)
    quiet_card = witness.card(tenant)
    witness.close()
    epoch = SpineEpochWitness().card(epoch_before=3, epoch_after=3, side=dark)
    return SpineBindCard().card(tenant_id=tenant, quiet=quiet_card, dark=dark, epoch=epoch)


def test_tenant_hides_foreign_and_refuses_same_id(tmp_path: Path) -> None:
    card = _bind(tmp_path)
    path = tmp_path / "bind.sqlite"
    journal = SpineBindJournal(path)
    journal.append("house-a", card)
    journal.close()
    tenant = SpineBindTenant(path)
    read = tenant.card("house-a", "house-b")
    assert read["seen"] is True
    assert read["foreign_seen"] is False
    assert read["live_motor"] is False
    empty = tenant.card("house-b", "house-c")
    assert empty["seen"] is False
    with pytest.raises(SpineBindTenantError):
        tenant.card("house-a", "house-a")
    tenant.close()


def test_replay_does_not_insert_and_refuses_a_mismatch(tmp_path: Path) -> None:
    card = _bind(tmp_path)
    path = tmp_path / "bind.sqlite"
    journal = SpineBindJournal(path)
    journal.append("house-a", card)
    journal.close()
    replay = SpineBindReplay(path)
    sealed = replay.replay("house-a", card)
    assert sealed["inserted"] is False
    assert sealed["rows_before"] == 1
    assert sealed["rows_after"] == 1
    assert sealed["moved"] is False
    other = dict(card)
    other["digest"] = "a" * 64
    with pytest.raises(SpineBindReplayError):
        replay.replay("house-a", other)
    replay.close()


def test_surface_strips_green_and_refuses_a_claim() -> None:
    bind = {
        "kind": "spine_bind_card",
        "hit": False,
        "tenant_id": "house-a",
        "digest": "b" * 64,
        "moved": False,
        "apply_landed": False,
    }
    provider = {"kind": "spine_provider_probe", "tenant_id": "house-a", "claimed": 0, "green": False}
    pr = {"kind": "spine_pr_probe", "tenant_id": "house-a", "claimed": 0, "green": False}
    card = SpineBindSurface().card(bind=bind, provider=provider, pr=pr)
    assert card["provider_claimed"] == 0
    assert card["pr_claimed"] == 0
    assert card["green"] is False
    assert card["hit"] is False
    claimed = dict(provider)
    claimed["claimed"] = 1
    with pytest.raises(SpineBindSurfaceError):
        SpineBindSurface().card(bind=bind, provider=claimed, pr=pr)


def test_gap_stays_unfilled_and_refuses_a_foreign_tenant() -> None:
    bind = {
        "kind": "spine_bind_card",
        "tenant_id": "house-a",
        "epoch_before": 4,
        "epoch_after": 4,
        "moved": False,
    }
    gap = {
        "kind": "spine_unread_gap",
        "tenant_id": "house-a",
        "table": "spine_provider_probe",
        "seen": [1, 3],
        "missing": [2],
        "green": False,
    }
    card = SpineBindGap().card(bind=bind, gap=gap)
    assert card["filled"] is False
    assert card["missing"] == [2]
    assert card["epoch_before"] == card["epoch_after"] == 4
    foreign = dict(gap)
    foreign["tenant_id"] = "house-b"
    with pytest.raises(SpineBindGapError):
        SpineBindGap().card(bind=bind, gap=foreign)
