"""Conservation, replay custody and user-facing CLI for market receipts."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    _advance, cli, new_market, original_market, simulate_market,
)
from skeleton.game.gameplay.scene_market_ledger import (
    audit_market_ledger, export_market_ledger, import_market_ledger,
    verify_market_ledger,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _finished():
    source, actions = original_market()
    return simulate_market(source, actions)


def test_market_ledger_earned_spent_and_inventory_conserved():
    report = audit_market_ledger(_finished())
    assert report["credits_earned"] == 3
    assert report["credits_spent"] == 2
    assert report["credits_remaining"] == 1
    assert report["goods_remaining"] == {}
    assert report["reputation_earned"] == 5
    assert report["delivered"] == ["sanctuary_seal"]
    assert report["phase"] == "won"
    assert sum(x["credit_delta"] for x in report["entries"]) == 1
    assert sum(x["reputation_delta"] for x in report["entries"]) == 5
    assert report["checksum"] == dig({
        k: v for k, v in report.items() if k != "checksum"
    })


@pytest.mark.parametrize("split", [0, 1, 3, 5, 6, 7, 8, 9, 10])
def test_market_ledger_prefixes_are_deterministic(split):
    source, actions = original_market()
    session = simulate_market(source, actions[:split])
    report = audit_market_ledger(session)
    assert report["journal_length"] == split
    assert report["credits_remaining"] == session["state"]["credits"]
    assert report["goods_remaining"] == session["state"]["goods"]
    assert report["last_receipt"] == (
        session["journal"][-1]["receipt"] if split else None
    )
    assert verify_market_ledger(session, json.loads(json.dumps(report))) == report


def test_portable_market_ledger_roundtrip_and_replay():
    session = _finished()
    bundle = export_market_ledger(session)
    assert import_market_ledger(json.loads(json.dumps(bundle))) == session
    assert bundle["ledger"] == audit_market_ledger(session)


@pytest.mark.parametrize("field", [
    "credits_earned", "credits_spent", "credits_remaining",
    "reputation_earned", "goods_remaining", "source_digest",
    "state_digest", "journal_length", "last_receipt", "phase",
])
def test_recomputed_checksum_cannot_authorize_forged_witness(field):
    session = _finished()
    report = audit_market_ledger(session)
    bad = copy.deepcopy(report)
    bad[field] = "forged"
    bad["checksum"] = dig({k: v for k, v in bad.items() if k != "checksum"})
    with pytest.raises(SceneTravelError, match="witness mismatch"):
        verify_market_ledger(session, bad)


def test_modified_entry_rejected_even_with_recomputed_checksums():
    session = _finished()
    bundle = export_market_ledger(session)
    bad = copy.deepcopy(bundle)
    bad["ledger"]["entries"][5]["credit_delta"] = 1000
    bad["ledger"]["checksum"] = dig({
        k: v for k, v in bad["ledger"].items() if k != "checksum"
    })
    bad["checksum"] = dig({k: v for k, v in bad.items() if k != "checksum"})
    with pytest.raises(SceneTravelError, match="witness mismatch"):
        import_market_ledger(bad)


def test_market_ledger_rejects_forged_session_even_if_witness_recomputed():
    session = _finished()
    session["state"]["credits"] += 100
    with pytest.raises(SceneTravelError):
        audit_market_ledger(session)


def test_market_ledger_failed_purchase_does_not_mint_or_mutate():
    source, actions = original_market()
    session = simulate_market(source, actions[:6])
    before = copy.deepcopy(session)
    with pytest.raises(SceneTravelError):
        _advance(session, {"kind": "buy", "offer_id": "copper_badge"})
    assert session == before
    assert audit_market_ledger(session)["credits_remaining"] == 1


def test_market_ledger_cli_and_portable_cli_roundtrip(capsys):
    from skeleton.__main__ import main
    session = _finished()
    serialized = json.dumps(session)
    assert main(["scene-market", "ledger", "--session-json", serialized]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["credits_remaining"] == 1
    assert cli(["ledger-export", "--session-json", serialized]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["ledger-import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == session
    bundle["ledger"]["credits_remaining"] = 999
    assert cli(["ledger-import", "--bundle-json", json.dumps(bundle)]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
