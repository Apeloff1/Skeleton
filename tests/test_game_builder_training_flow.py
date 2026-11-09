"""Fault tolerant original-game training, heldout worlds, and corruption repair."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.competitive_mirror_training import (
    TrainingCandidate,split_project,
)
from skeleton.ai.game_builder.game_training_flow import (
    TrainingFlowError,CandidateBatch,plan_training_flow,
    materialize_training_flow,train_isolated_review_ranker,
)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_learning_almanac import (
    Curriculum,quarantine_curriculum,
)
from skeleton.ai.game_builder.game_training_flow import load_quarantined_batches
from skeleton.ai.game_builder.game_workspace_cli import main as studio_cli


def make_batches():
    pools={"train":[],"validation":[],"test":[]}
    n=0
    while min(len(v) for v in pools.values())<3 or len(pools["train"])<5:
        project=sha256(f"original_fresh_project_{n}".encode()).hexdigest()
        split=split_project(project)
        if len(pools[split])>=6:
            n+=1;continue
        cases=[]
        for j in range(12):
            hostile=(j%2==0)
            kind=("state_forgery","chronology","witness_origin",
                  "source_identity")[j%4]
            input_={"attack_family":kind,
                    "source_campaign_digest":project} if hostile else {
                    "canonical_witness":{"event":"witnessed_gameplay",
                                         "source_world":project}}
            cases.append(TrainingCandidate(
                project_digest=project,split=split,
                example_id=canonical_digest({"source":project,"j":j}),
                instruction="Scrutinize original gameplay evidence.",
                input=input_,
                expected={"decision":"reject" if hostile else
                          "accept_witnessed_incident_only"},
                evidence={"severity":8 if hostile else 2,
                          "verified_control":not hostile},
            ))
        pools[split].append(CandidateBatch(project,canonical_digest({
            "almanac":project}),tuple(cases)))
        n+=1
        if n>1000:
            raise RuntimeError("unable to build grouped split corpus")
    return tuple(batch for split in ("train","validation","test")
                 for batch in pools[split])


class FaultTolerantTrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batches=make_batches()
        cls.plan=plan_training_flow(cls.batches,authorized=True)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace=GameWorkspace.create(
            Path(self.temp.name)/"original_game_studio",authorized=True)

    def test_project_grouping_and_high_gain_curriculum(self):
        plan=self.plan
        self.assertGreater(len(plan.selected),100)
        self.assertEqual(len(set(plan.source_projects)),len(plan.source_projects))
        self.assertEqual({s for s,_ in plan.split_projects},
                         {"train","validation","test"})
        for split,projects in plan.split_projects:
            self.assertTrue(all(split_project(p)==split for p in projects))
        self.assertEqual(len({x.example_id for x in plan.selected}),len(plan.selected))
        self.assertEqual(plan.rejected_duplicates,0)
        self.assertEqual(plan.run_id,plan_training_flow(self.batches,authorized=True).run_id)
        self.assertTrue(all(0<importance<=1000 for _,importance in plan.priority))
        self.assertFalse(plan.payload()["weights_automatically_deployed"])

    def test_resume_after_interruption_and_verify_exact_immutable_shards(self):
        with self.assertRaises(InterruptedError):
            materialize_training_flow(
                self.plan,self.workspace.root,authorized=True,
                shard_size=8,interrupt_after=2,
            )
        stage=self.workspace.root/"training"/"runs"/(self.plan.run_id+".staging")
        self.assertTrue(stage.is_dir())
        self.assertTrue((stage/"train_0000.jsonl").is_file())
        complete=materialize_training_flow(
            self.plan,self.workspace.root,authorized=True,shard_size=8,
        )
        self.assertFalse(complete["recovered"])
        self.assertEqual(complete["total_examples"],len(self.plan.selected))
        self.assertEqual(complete["project_groups"],len(self.plan.source_projects))
        resumed=materialize_training_flow(
            self.plan,self.workspace.root,authorized=True,shard_size=8,
        )
        self.assertTrue(resumed["recovered"])
        self.assertEqual(resumed["run_id"],complete["run_id"])
        self.assertFalse(resumed["deployment_approved"])
        self.assertFalse(stage.exists())
        self.assertTrue((self.workspace.root/"training"/"runs"/
                         self.plan.run_id/"manifest.json").is_file())

    def test_altered_or_hidden_source_shards_rejected_not_silently_regenerated(self):
        with self.assertRaises(InterruptedError):
            materialize_training_flow(
                self.plan,self.workspace.root,authorized=True,
                shard_size=8,interrupt_after=1)
        stage=self.workspace.root/"training"/"runs"/(self.plan.run_id+".staging")
        (stage/"train_0000.jsonl").write_bytes(b"tampered\n")
        with self.assertRaises(TrainingFlowError):
            materialize_training_flow(
                self.plan,self.workspace.root,authorized=True,shard_size=8)
        self.assertFalse((self.workspace.root/"training"/"runs"/self.plan.run_id).exists())

    def test_train_real_isolated_reviewer_policy_and_evaluate_unseen_projects(self):
        fit=train_isolated_review_ranker(self.plan,authorized=True)
        self.assertEqual(fit["status"],"experimental_fit_only")
        self.assertTrue(fit["training_performed"])
        self.assertGreaterEqual(fit["validation"]["balanced_accuracy"],0.9)
        self.assertGreaterEqual(fit["test"]["balanced_accuracy"],0.9)
        self.assertTrue(fit["train"]["n"]>0)
        self.assertTrue(fit["test"]["n"]>0)
        self.assertFalse(fit["training_artifact_approved_for_deployment"])
        self.assertFalse(fit["production_dragon_or_jeeves_weights_changed"])
        self.assertEqual(fit["fitted_policy_digest"],
                         train_isolated_review_ranker(self.plan,authorized=True)[
                             "fitted_policy_digest"])
        small=plan_training_flow(self.batches[:1],authorized=True)
        blocked=train_isolated_review_ranker(small,authorized=True)
        self.assertEqual(blocked["status"],"blocked")
        self.assertFalse(blocked["training_performed"])

    def test_source_receipt_verification_and_train_dataset_cli(self):
        import io
        from contextlib import redirect_stdout
        source=self.batches[0]
        curriculum=Curriculum(
            source.source_project,split_project(source.source_project),
            source.original_almanac,source.examples,6,6,
        )
        receipt=quarantine_curriculum(curriculum,self.workspace.root,
                                      authorized=True)
        self.assertTrue(Path(receipt["path"]).is_file())
        self.assertTrue(Path(receipt["path"]).with_suffix(".receipt.json").is_file())
        self.assertEqual(load_quarantined_batches(
            self.workspace.root,authorized=True)[0].source_project,
            source.source_project)
        out=io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(studio_cli([
                "train-dataset","--root",str(self.workspace.root),
                "--trusted-local-operator","--shard-size","8",
            ]),0)
        result=__import__("json").loads(out.getvalue())
        self.assertEqual(result["source_project_count"],1)
        self.assertEqual(result["training_experiment"]["status"],"blocked")
        self.assertFalse(result["permanent_core_AI_weights_changed"])
        self.assertTrue(result["immutable_shards"])
        with Path(receipt["path"]).open("ab") as file:
            file.write(b"\n")
        with self.assertRaises(TrainingFlowError):
            load_quarantined_batches(self.workspace.root,authorized=True)

    def test_foreign_cross_split_or_per_project_repetition_is_rejected(self):
        first=self.batches[0]
        with self.assertRaises(TrainingFlowError):
            CandidateBatch(first.source_project,first.original_almanac,
                           tuple(replace(c,split="test") for c in first.examples))
        with self.assertRaises(TrainingFlowError):
            plan_training_flow((first,first),authorized=True)
        with self.assertRaises(PermissionError):
            materialize_training_flow(self.plan,self.workspace.root,authorized=False)
        with self.assertRaises(TrainingFlowError):
            plan_training_flow(self.batches,authorized=True,per_project_cap=900)
        with self.assertRaises(TrainingFlowError):
            train_isolated_review_ranker(self.plan,authorized=True,
                                         learning_rate=float("nan"))


if __name__=="__main__":
    unittest.main()
