"""Every unsigned volume organ must admit a canonical card and reject adversaries."""
from __future__ import annotations

import pytest

from skeleton.volumes.wave4.catalog import BIND, FAMILIES, contract
from skeleton.volumes.wave4.engine import VolumeReject, admit, volume_ids


def _card(volume: str) -> dict:
    spec = contract(volume)
    family = spec["family"]
    card = {"volume": volume}
    for field in spec["required"]:
        card[field] = {
            "signed": True,
            "bytecode_sha256": "a" * 64,
            "cycle_free": True,
            "decision": "deny",
            "erasure_proof": True,
            "objective": 10,
            "burn": 1,
            "cardinality": 2,
            "budget": 8,
            "units": 1,
            "cap": 4,
            "contaminated": False,
            "score": 1,
            "bound": 1,
            "maturity": 1,
            "idempotency_key": "k",
            "steps": ["a"],
            "digest": "b" * 64,
            "bytes": 8,
            "bound": True if family == "cache" else 1,
            "quota": 1,
            "allowed": True,
            "deprecated": False,
            "stage": "hold",
            "isolated": True,
            "terminal": False,
            "approval": "denied",
            "expires": "2026-10-09T00:00:00Z",
            "fresh": True,
            "static_ok": True,
            "simulated": True,
            "health": "ok",
            "trust": "low",
            "compensation": "undo",
            "risk": "low",
            "plan": "hold",
            "critical": False,
            "deadline": "t",
            "evictable": True,
            "hit": False,
            "prefix": "p",
            "node": "n",
            "tier": "hot",
            "queue": "q",
            "job": "j",
            "license": "mit",
            "usage": "internal",
            "model": "m",
            "flag": "off",
            "branch": "exp",
            "selected": False,
            "strategy": "s",
            "cost": 1,
            "tool": "t",
            "saga_id": "s",
            "step": "1",
            "device": "cpu",
            "class_name": "a.B",
            "path": "p",
            "owner": "o",
            "boundary": "b",
            "module": "m",
            "allowed": True,
            "req_id": "r",
            "acceptance": "a",
            "metric": "m",
            "unit": "u",
            "cap_id": "c",
            "parent": "p",
            "spec_id": "s",
            "pre": "p",
            "post": "q",
            "machine": "m",
            "state": "s",
            "name": "n",
            "version": "1",
            "errors": "e",
            "message_id": "m",
            "inbox": "i",
            "principal": "p",
            "action": "a",
            "resource": "r",
            "subject": "s",
            "purpose": "p",
            "component": "c",
            "license": "mit",
            "service": "s",
            "signal": "s",
            "meter": "m",
            "source_id": "s",
            "citation": "c",
            "harness": "h",
            "case_id": "c",
            "card_id": "c",
            "policy_id": "p",
            "deny_default": True,
            "objective": "o" if family != "slo" else 10,
            "constraint": "c",
            "wf_id": "w",
            "task": "t",
            "actor": "a",
            "intent": "i",
            "ns": "n",
            "resolved": True,
            "artifact": "a",
            "deps": ["d"],
            "change_id": "c",
            "surface": "s",
            "contract": "c",
            "schema_sha": "s",
            "claim_id": "c",
            "scope": "s",
            "plan_id": "p",
        }.get(field, "x")
    if family == "slo":
        card["objective"] = 10
        card["burn"] = 1
    if family == "cache":
        card["bound"] = True
    if family == "nfr":
        card["bound"] = 1
    return card


def test_catalog_covers_every_bound_volume() -> None:
    assert len(volume_ids()) == 141
    assert set(volume_ids()) == set(BIND)


@pytest.mark.parametrize("volume", volume_ids())
def test_volume_admits_canonical_and_rejects_empty(volume: str) -> None:
    receipt = admit(volume, _card(volume))
    assert receipt["admitted"] is True
    assert receipt["stored_prose"] == 0
    assert receipt["family"] == contract(volume)["family"]
    with pytest.raises(VolumeReject):
        admit(volume, {"volume": volume})
    with pytest.raises(VolumeReject):
        admit(volume, {**_card(volume), "volume": "VOL-000"})


def test_unknown_volume_rejected() -> None:
    with pytest.raises(VolumeReject):
        admit("VOL-999", {"volume": "VOL-999"})


def test_families_are_bounded() -> None:
    assert set(FAMILIES) >= {contract(v)["family"] for v in volume_ids()}
