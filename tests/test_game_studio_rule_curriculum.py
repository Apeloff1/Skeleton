"""Real AI-authored rules: bounded source mutation, measured learning and replay."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.jeeves.game_studio_environment import make_studio_source
from skeleton.jeeves.game_learning import GameLearningError
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
from skeleton.jeeves.game_studio_rule_curriculum import (
    PLAN_SCHEMA, PROPOSAL_SCHEMA, RuleCurriculumEnvironment,
    RuleCurriculumError, apply_rule_proposal, make_rule_curriculum,
    verify_rule_curriculum,
)
from skeleton.jeeves.game_studio_rule_training_cli import train_rule_curriculum


def source_hash(source):
    raw = json.dumps(source, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def change(source, proposal_id, changes, scene_seed=None):
    return {
        "schema_version": PROPOSAL_SCHEMA,
        "proposal_id": proposal_id,
        "base_digest": source_hash(source),
        "reason": "Change the original mechanic to measure distinct world conditions.",
        "scene_seed": scene_seed,
        "operations": changes,
    }


def setting(field, op, value):
    return {"scope": "settings", "path": field,
            "op": op, "value": value}


def layout(path, op, value):
    return {"scope": "layout", "path": path,
            "op": op, "value": value}


class TestModelProposedEngineRules(unittest.TestCase):
    def setUp(self):
        self.base = make_studio_source(
            "economy", {"market_nodes": 3, "goods": 10},
            actions=("inspect", "wait", "survey", "buy:1", "sell:1"),
        )
        self.tax = change(
            self.base, "scarcity-tax",
            [setting("trade_tax", "add", 9),
             setting("finite_inventory", "toggle", None)],
        )
        self.market = change(
            self.base, "distant-market",
            [layout("nodes/0/price", "add", 7)], scene_seed=2,
        )

    def test_ai_can_discover_real_schema_but_not_ownership_controls(self):
        from skeleton.jeeves.game_studio_rule_curriculum import rule_authoring_contract
        contract=rule_authoring_contract(self.base)
        self.assertEqual(contract["editor"],"economy")
        self.assertEqual(contract["base_digest"],source_hash(self.base))
        fields={row["path"]:row for row in contract["editable_settings"]}
        self.assertIn("trade_tax",fields)
        self.assertEqual(fields["trade_tax"]["minimum"],0)
        self.assertEqual(fields["trade_tax"]["maximum"],100)
        self.assertIn("add",fields["trade_tax"]["operators"])
        sample=contract["sample_operation"]
        self.assertIsNotNone(sample)
        self.assertEqual(sample["scope"],"settings")
        self.assertNotEqual(sample["value"],self.base["settings"][sample["path"]])
        protected=make_studio_source("platform_profile")
        gates=rule_authoring_contract(protected)
        self.assertNotIn("homebrew_only",{
            row["path"] for row in gates["editable_settings"]
        })

    def test_ai_rules_change_real_playable_engine_source(self):
        original = deepcopy(self.base)
        candidate = apply_rule_proposal(self.base, self.tax)
        self.assertEqual(self.base, original)
        self.assertEqual(candidate["settings"]["trade_tax"],
                         original["settings"]["trade_tax"] + 9)
        self.assertIs(candidate["settings"]["finite_inventory"], False)
        self.assertEqual(candidate["actions"], original["actions"])
        self.assertNotEqual(source_hash(original),source_hash(candidate))
        # The changed rules must actually be executable by the authoritative
        # source interpreter and replay verified, not just a new label.
        from skeleton.ai.game_builder.advanced_gameplay_runtime import (
            run_advanced_session, verify_advanced_session,
        )
        receipt=run_advanced_session("economy",candidate["settings"],
                                     ["inspect"], seed=4)
        self.assertTrue(verify_advanced_session(receipt,candidate["settings"]))

    def test_scene_edit_is_applied_to_source_and_replay_authority(self):
        candidate = apply_rule_proposal(self.base,self.market)
        self.assertEqual(candidate["scene"]["layout"]["nodes"][0]["price"],
                         make_rule_curriculum(self.base,[self.market])[
                             "scenarios"][1]["source"]["scene"]["layout"]["nodes"][0]["price"])
        self.assertEqual(candidate["scene"]["seed"],2)
        from skeleton.ai.game_builder.advanced_gameplay_runtime import (
            run_advanced_session, verify_advanced_session,
        )
        evidence=run_advanced_session(
            "economy",candidate["settings"],["inspect"],seed=2,
            scene=candidate["scene"],
        )
        self.assertTrue(verify_advanced_session(evidence,candidate["settings"]))

    def test_tampered_and_out_of_range_ai_requests_rejected(self):
        with self.assertRaises(RuleCurriculumError):
            apply_rule_proposal(self.base,{**self.tax,"base_digest":"0"*64})
        with self.assertRaises(RuleCurriculumError):
            apply_rule_proposal(self.base,change(self.base,"unsafe-eval",[
                {"scope":"python","path":"code","op":"set","value":"__import__('os')"}
            ]))
        with self.assertRaises(RuleCurriculumError):
            apply_rule_proposal(self.base,change(self.base,"off-limits",[
                setting("goods","set",9999999),
            ]))
        with self.assertRaises(RuleCurriculumError):
            apply_rule_proposal(self.base,change(self.base,"duplicate-ops",[
                setting("trade_tax","add",1), setting("trade_tax","add",2),
            ]))
        with self.assertRaises(RuleCurriculumError):
            apply_rule_proposal(self.base,change(self.base,"layout-injection",[
                layout("nodes/0/id","set",7),
            ],scene_seed=2))
        with self.assertRaises(RuleCurriculumError):
            apply_rule_proposal(self.base,change(self.base,"layout-range",[
                layout("nodes/0/price","set",50000000),
            ],scene_seed=2))
        protected=make_studio_source("platform_profile")
        with self.assertRaises(RuleCurriculumError):
            apply_rule_proposal(protected,change(protected,"license-bypass",[
                setting("homebrew_only","toggle",None),
            ]))

    def test_baseline_and_adversarial_rules_are_shared_policy_states(self):
        plan = make_rule_curriculum(self.base,[self.tax,self.market],max_steps=4)
        self.assertEqual(plan["schema_version"],PLAN_SCHEMA)
        self.assertEqual(len(plan["scenarios"]),3)
        self.assertEqual(verify_rule_curriculum(plan),plan)
        self.assertNotEqual(
            plan["scenarios"][1]["source"],
            plan["scenarios"][2]["source"],
        )
        env=RuleCurriculumEnvironment(plan)
        observations=[]
        try:
            for seed in (0,1,2):
                observation=env.reset(seed)
                observations.append(observation["circumstance"])
                result=env.step("inspect")
                self.assertTrue(result.info["evidence"]["accepted"])
                self.assertEqual(result.info["scenario_index"],seed)
                snap=env.snapshot()
                other=RuleCurriculumEnvironment(plan)
                try:
                    restored=other.restore(snap)
                    self.assertEqual(snap,other.snapshot())
                    self.assertEqual(restored,dict(result.observation))
                finally:
                    other.close()
            self.assertEqual(observations,[0.0,0.5,1.0])
            self.assertIn("circumstance",env.spec.observation_bins)
        finally:
            env.close()

    def test_plan_tampering_or_future_scene_promotion_fails_closed(self):
        plan=make_rule_curriculum(self.base,[self.tax],max_steps=4)
        forged=deepcopy(plan)
        forged["scenarios"][1]["source"]["settings"]["trade_tax"]=99
        with self.assertRaises(RuleCurriculumError):
            verify_rule_curriculum(forged)
        with self.assertRaises(RuleCurriculumError):
            make_rule_curriculum(self.base,[self.tax,self.tax])

    def test_isolated_rollout_request_replays_same_rule_spec(self):
        plan=make_rule_curriculum(self.base,[self.tax,self.market],max_steps=5)
        source=json.dumps(plan,sort_keys=True,separators=(",", ":"),ensure_ascii=True)
        request=GameEnvironmentRequest(
            "studio-rules:economy",kind="studio_rules",
            tree={"game/studio/rule_curriculum.json":source},
            max_steps=5,
        )
        imported=GameEnvironmentRequest.from_dict(request.as_dict())
        self.assertEqual(imported.digest,request.digest)
        env=imported.build()
        baseline=RuleCurriculumEnvironment(plan)
        try:
            self.assertEqual(env.spec.as_dict(),baseline.spec.as_dict())
            self.assertEqual(env.reset(2),baseline.reset(2))
            self.assertEqual(env.step("inspect").transition_digest,
                             baseline.step("inspect").transition_digest)
        finally:
            env.close()
            baseline.close()
        with self.assertRaises(GameLearningError):
            GameEnvironmentRequest(
                "studio-rules:foreign",kind="studio_rules",
                tree={"game/studio/session.json":source},max_steps=5,
            )
        bad=GameEnvironmentRequest(
            "studio-rules:economy",kind="studio_rules",
            tree={"game/studio/rule_curriculum.json":source},max_steps=4,
        )
        with self.assertRaises(GameLearningError):
            bad.build()

    def test_actual_q_updates_and_disjoint_scenario_evaluation(self):
        with TemporaryDirectory() as folder:
            target=Path(folder)/"trained-rules.json"
            with self.assertRaises(PermissionError):
                train_rule_curriculum(
                    base_source=self.base, proposals=[self.tax,self.market],
                    output=target, authorized=False, rights_cleared=True,
                    episodes_per_scenario=1, max_steps=3,
                )
            report=train_rule_curriculum(
                base_source=self.base, proposals=[self.tax,self.market],
                output=target, authorized=True,rights_cleared=True,
                episodes_per_scenario=2,max_steps=3,seed=4,
            )
            record=json.loads(target.read_text())
            self.assertEqual(report["circumstances"],3)
            self.assertEqual(report["episodes"],6)
            self.assertGreater(report["actual_q_updates"],0)
            self.assertEqual(len(record["evaluation_by_circumstance"]),3)
            self.assertFalse(record["production_neural_weights_modified"])
            self.assertFalse(record["automatic_policy_promotion"])
            self.assertFalse(record["candidate_improvement_claimed"])
            self.assertEqual(record["evaluation"]["heldout_seeds"],
                             [entry["heldout_seed"] for entry in
                              record["evaluation_by_circumstance"]])
            self.assertTrue(
                set(record["evaluation"]["heldout_seeds"]).isdisjoint(
                    entry["seed"] for entry in record["training_episode_evidence"]
                )
            )
            with self.assertRaises(FileExistsError):
                train_rule_curriculum(
                    base_source=self.base,proposals=[self.tax,self.market],
                    output=target,authorized=True,rights_cleared=True,
                    episodes_per_scenario=1,max_steps=3,
                )


if __name__=="__main__":
    unittest.main()
