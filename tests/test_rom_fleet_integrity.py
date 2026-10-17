"""Fleet qualification must reconstruct actual synthetic Q-policy evidence.

The simulator implements real state transitions, snapshots, reversal/replay,
and measured Q updates. It is NOT native game hardware or production Jeeves.
"""
from __future__ import annotations

import hashlib
import json

from skeleton.ai.training import rom_fleet_audit as fleet
from skeleton.ai.training import rom_study as rom
from skeleton.ai.training.rom_inventory_snapshot import freeze_rom_inventory, load_frozen_inventory
from skeleton.jeeves import game_emulator_training_lab as lab
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
from skeleton.testing.test_game_emulator_training_lab import ControlledNativeFixture

from tests.test_rom_study import _approvals, _fake_training, _roms


def _legitimate_fleet(tmp_path, monkeypatch):
    root, source, _ = _roms(tmp_path)
    approvals, _ = _approvals(tmp_path, source)
    out = tmp_path / "receipts"
    out.mkdir(mode=0o700)
    original_trainer = lab.run_emulator_training_lab
    _fake_training(tmp_path, monkeypatch, updates=4)
    # The legacy paging fixture intentionally fakes report metadata; replace
    # it with the ACTUAL synthetic lab and restore strict proof validation.
    monkeypatch.setattr(lab, "run_emulator_training_lab", original_trainer)
    monkeypatch.setattr(fleet, "_verify_existing_q_receipt", rom._verify_existing_q_receipt)
    monkeypatch.setattr(
        GameEnvironmentRequest, "build",
        lambda self: ControlledNativeFixture(),
    )
    frozen = freeze_rom_inventory(root, out)
    snapshot = load_frozen_inventory(
        __import__("pathlib").Path(frozen["manifest_path"]), root=root,
    )
    execution = rom.train_page(
        root, approvals, out, inventory_snapshot=snapshot,
        limit=2, runs=1, steps=4, seed=18,
    )
    trained = next(row for row in execution["page_results"]
                   if row["relative_path"] == "a.gb")
    assert trained["state"] == "q_policy_updated_with_receipt", trained
    assert trained["actual_q_table_updates"] == 4
    return root, approvals, out, frozen, trained


def test_real_synthetic_policy_and_replay_qualifies_one_fleet_source(tmp_path, monkeypatch):
    root, approvals, out, frozen, trained = _legitimate_fleet(tmp_path, monkeypatch)
    audit = fleet.audit_fleet_page(
        root, __import__("pathlib").Path(frozen["manifest_path"]),
        approvals, out, limit=2,
    )
    assert audit["page_counts"]["verified_q_policy_sources"] == 1
    source = next(row for row in audit["rows"]
                  if row["relative_path"] == "a.gb")
    assert source["status"] == "verified_q_policy_updated"
    assert trained["receipt_sha256"] in source["receipt_sha256"]
    # The same frozen source and exact rights ledger must permit read-only reuse.
    prior = rom.train_page(
        root, approvals, out,
        inventory_snapshot=load_frozen_inventory(
            __import__("pathlib").Path(frozen["manifest_path"]), root=root,
        ),
        runs=1, steps=4, seed=18, limit=2,
    )
    state = next(row for row in prior["page_results"]
                 if row["relative_path"] == "a.gb")
    assert state["state"] == "previous_verified_receipt_no_reexecution", state


def test_fleet_rejects_policy_forgery_even_with_recomputed_report_checksum(
    tmp_path, monkeypatch,
):
    from skeleton.jeeves.game_learning import _digest
    root, approvals, out, frozen, trained = _legitimate_fleet(tmp_path, monkeypatch)
    receipt_path = out / trained["receipt_name"]
    record = json.loads(receipt_path.read_text())
    report = record["candidate_evidence"]
    report["audited_run_receipts"][0]["actual_steps"] = 3
    report["report_digest"] = _digest({
        k: v for k, v in report.items() if k != "report_digest"
    })
    receipt_path.write_bytes(rom._canonical(record) + b"\n")
    audit = fleet.audit_fleet_page(
        root, __import__("pathlib").Path(frozen["manifest_path"]),
        approvals, out, limit=2,
    )
    assert audit["page_counts"]["verified_q_policy_sources"] == 0
    assert audit["page_counts"]["invalid_or_stale_receipt_sources"] == 1
    assert next(row for row in audit["rows"]
                if row["relative_path"] == "a.gb")["status"] == "invalid_or_stale_receipt_only"


def test_fleet_rejects_missing_active_core_identity(tmp_path, monkeypatch):
    from skeleton.jeeves import game_emulator_catalog as catalog
    root, approvals, out, frozen, trained = _legitimate_fleet(tmp_path, monkeypatch)
    class WrongRegistry:
        registry_digest = hashlib.sha256(b"changed cores").hexdigest()
        def resolve_core(self, name):
            raise LookupError("approved core withdrawn")
    monkeypatch.setattr(
        catalog.GameEmulatorRegistry, "from_environment",
        classmethod(lambda cls: WrongRegistry()),
    )
    audit = fleet.audit_fleet_page(
        root, __import__("pathlib").Path(frozen["manifest_path"]),
        approvals, out, limit=2,
    )
    assert audit["page_counts"]["verified_q_policy_sources"] == 0
    assert audit["page_counts"]["invalid_or_stale_receipt_sources"] == 1
