"""Shadow-clone run-until-plateau contracts: real forks, dry ten cycles, receipts."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.jeeves.game_studio_environment import make_studio_source
from skeleton.jeeves.game_studio_shadow_saturation import (
    DRY_CYCLES_REQUIRED, ShadowSaturationError,
    run_shadow_saturation, verify_shadow_receipts,
)
from skeleton.jeeves.game_studio_shadow_cli import (
    execute_shadow_room, verify_shadow_certificate,
)


class ShadowSaturationTests(unittest.TestCase):
    def setUp(self):
        # A deliberately narrow engine state allows a reproducible bounded
        # zero-novelty plateau without relying on arbitrary randomness.
        self.source=make_studio_source(
            "economy",{"market_nodes":2,"goods":10},actions=("inspect",),
        )

    def test_ten_is_dry_consecutive_cycles_after_real_learning_not_run_limit(self):
        rows=[]
        report=run_shadow_saturation(
            self.source,angles=("explore",),seed=7,
            steps=1,max_cycles_per_sim=12,
            dry_cycles=DRY_CYCLES_REQUIRED,workers=1,
            max_replay_work_per_sim=1000,
            on_receipt=rows.append,
        )
        sim=report["simulations"][0]
        self.assertEqual(len(rows),sim["cycles_executed"])
        self.assertGreaterEqual(sim["cycles_executed"],11)
        self.assertEqual(sim["observed_zero_novelty_streak"],10)
        self.assertTrue(sim["saturation_within_tested_bounds"])
        self.assertTrue(report["all_saturated_within_bounds"])
        self.assertEqual(sim["total_primary_and_shadow_runs"],
                         sim["cycles_executed"]*2)
        self.assertFalse(sim["universal_learning_exhaustion_proven"])
        self.assertEqual(len(sim["receipts"]),sim["cycles_executed"])
        self.assertEqual(sim["receipts"][0]["base_audits_passed"],20)
        self.assertEqual(sim["receipts"][0]["additional_checks_passed"],1)
        self.assertEqual(sim["receipts"][7]["additional_checks_passed"],8)
        self.assertEqual(sim["peak_additional_scrutiny_checks"],8)
        self.assertTrue(all(x["fork"]["same_source_same_checkpoint_verified"]
                            for x in sim["receipts"]))
        self.assertTrue(verify_shadow_receipts(report))

    def test_budget_is_inconclusive_not_false_saturation(self):
        report=run_shadow_saturation(
            self.source,angles=("explore",),seed=7,
            steps=2,max_cycles_per_sim=12,
            workers=1,max_replay_work_per_sim=100,
        )
        sim=report["simulations"][0]
        self.assertFalse(sim["saturation_within_tested_bounds"])
        self.assertFalse(report["all_saturated_within_bounds"])
        self.assertEqual(sim["stop_reason"],"compute_budget_exhausted_unproven")
        self.assertFalse(report["universal_game_knowledge_exhaustion_claimed"])
        self.assertTrue(verify_shadow_receipts(report))

    def test_source_bound_cycle_tampering_changes_chain(self):
        doc=run_shadow_saturation(
            self.source,angles=("explore",),seed=8,
            steps=1,max_cycles_per_sim=11,workers=1,
            max_replay_work_per_sim=1000,
        )
        bad=deepcopy(doc)
        bad["simulations"][0]["receipts"][0]["fork"]["parent_snapshot_digest"]="0"*64
        with self.assertRaises(ShadowSaturationError):
            verify_shadow_receipts(bad)
        bad=deepcopy(doc)
        bad["simulations"][0]["receipts"][-1]["zero_novelty_streak"]=9
        with self.assertRaises(ShadowSaturationError):
            verify_shadow_receipts(bad)

    def test_real_q_candidate_requires_rights_and_cannot_fake_plateau(self):
        with self.assertRaises(PermissionError):
            run_shadow_saturation(
                self.source,angles=("explore",),steps=1,
                max_cycles_per_sim=11,
                train_policy=True,
            )
        doc=run_shadow_saturation(
            self.source,angles=("explore",),seed=2,steps=1,
            max_cycles_per_sim=11,workers=1,
            max_replay_work_per_sim=1000,
            train_policy=True,authorized=True,rights_cleared=True,
        )
        sim=doc["simulations"][0]
        self.assertTrue(sim["candidate_q_training_enabled"])
        self.assertEqual(doc["candidate_q_policy_count"],1)
        self.assertIsNotNone(sim["candidate_q_policy_snapshot"])
        self.assertFalse(doc["production_neural_weights_modified"])
        self.assertTrue(all(
            receipt["actual_game_q_updates"]>=1
            and len(receipt["policy_snapshot_digest"])==64
            for receipt in sim["receipts"]
        ))
        if not sim["saturation_within_tested_bounds"]:
            self.assertTrue(sim["stop_reason"].endswith("_unproven"))
        self.assertTrue(verify_shadow_receipts(doc))

    def test_persistent_append_only_logs_and_final_certificate(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            target=root/"certificate.json"
            journal=root/"evidence.ndjson"
            outcome=execute_shadow_room(
                source=self.source,output=target,ledger_path=journal,
                authorized=True,rights_cleared=True,
                train_policy=False,angles=("explore",),
                seed=9,steps=1,max_cycles_per_sim=12,
                max_replay_work_per_sim=1000,workers=1,
            )
            self.assertTrue(target.exists())
            self.assertTrue(journal.exists())
            self.assertTrue(outcome["all_saturated_within_bounds"])
            envelope=json.loads(target.read_text())
            self.assertTrue(verify_shadow_receipts(envelope["laboratory"]))
            audited=verify_shadow_certificate(target,journal,self.source)
            self.assertTrue(audited["independently_verified"])
            self.assertEqual(audited["log_receipts_reexecuted"],
                             outcome["ledger_event_count"])
            changed=make_studio_source(
                "economy",{"market_nodes":2,"goods":10,"trade_tax":11},
                actions=("inspect",),
            )
            with self.assertRaises(ShadowSaturationError):
                verify_shadow_certificate(target,journal,changed)
            self.assertEqual(
                len(journal.read_text().splitlines()),
                outcome["ledger_event_count"],
            )
            self.assertFalse(envelope["production_neural_weights_modified"])
            with self.assertRaises(FileExistsError):
                execute_shadow_room(
                    source=self.source,output=target,ledger_path=journal,
                    authorized=True,rights_cleared=True,
                    train_policy=False,angles=("explore",),
                    steps=1,max_cycles_per_sim=12,
                )


if __name__=="__main__":
    unittest.main()
