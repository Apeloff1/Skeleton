"""Recorded gameplay, graphics, audio and story probe execution controls."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import unittest

from skeleton.ai.game_builder.competitive_probe_runner import (
    RecordedProbeTrial,score_recorded_probe_batch,
)
from skeleton.ai.game_builder.competitive_title_radar import ThreatRadarError
from tests.test_game_builder_competitive_deep import DeepEnemyCases,T0


class MeasuredGameProbeCases(DeepEnemyCases):
    def observations(self,script,*,person="original_world",judge=None,
                     normal_score=9000,adversarial_score=5000):
        judge=judge or self.judges[0]
        trials=[]
        for condition,score in (("normal",normal_score),
                                ("adversarial",adversarial_score)):
            for seq in range(10):
                tag=f"{script.digest}|{person}|{judge.judge_id}|{condition}|{seq}"
                trials.append(RecordedProbeTrial(
                    person,script.digest,judge.judge_id,
                    sha256(("session:"+tag).encode()).hexdigest(),
                    "a"*64,sha256(("participant:"+tag).encode()).hexdigest(),
                    condition,score,T0,
                    sha256(("original_telemetry:"+tag).encode()).hexdigest()))
        return tuple(trials)

    def test_real_replay_aggregator_does_not_hide_adversarial_failure(self):
        script=next(s for s in self.scripts() if s.facet=="npc_agency")
        receipt=score_recorded_probe_batch(
            script,self.observations(script),self.judges[0],
            subject_id="original_world",as_of=T0,
            authorized=True,source_capture_consent=True,
            independent_telemetry_reviewed=True)
        self.assertEqual(receipt.outcome.score_bp,5000)
        self.assertEqual(receipt.outcome.lower_bp,5000)
        self.assertEqual(receipt.outcome.upper_bp,9000)
        self.assertEqual(receipt.condition_counts,
                         (("adversarial",10),("normal",10)))
        self.assertEqual(receipt.payload()["automated_real_world_capture_performed"],
                         False)
        self.assertEqual(receipt.outcome.participant_count,20)
        self.assertEqual(receipt.raw_trial_evidence_root,receipt.outcome.replay_receipt_digest)
        self.assertFalse(receipt.payload()["actual_game_assets_reproduced"])
        self.assertEqual(receipt.payload(),score_recorded_probe_batch(
            script,self.observations(script),self.judges[0],
            subject_id="original_world",as_of=T0,authorized=True,
            source_capture_consent=True,
            independent_telemetry_reviewed=True).payload())

    def test_duplicate_player_or_game_build_invalidates_evidence(self):
        script=self.scripts()[0]
        rows=list(self.observations(script))
        rows[-1]=replace(rows[-1],participant_token_digest=rows[0].participant_token_digest)
        with self.assertRaisesRegex(ThreatRadarError,"repeated"):
            score_recorded_probe_batch(
                script,tuple(rows),self.judges[0],
                subject_id="original_world",as_of=T0,authorized=True,
                source_capture_consent=True,
                independent_telemetry_reviewed=True)
        rows=list(self.observations(script))
        rows[-1]=replace(rows[-1],build_digest="b"*64)
        with self.assertRaisesRegex(ThreatRadarError,"mixing"):
            score_recorded_probe_batch(
                script,tuple(rows),self.judges[0],
                subject_id="original_world",as_of=T0,authorized=True,
                source_capture_consent=True,
                independent_telemetry_reviewed=True)

    def test_minimum_adversarial_trials_and_permission_veto(self):
        script=self.scripts()[0]
        rows=self.observations(script)
        for consent,independent in ((False,True),(True,False)):
            with self.assertRaises(PermissionError):
                score_recorded_probe_batch(
                    script,rows,self.judges[0],subject_id="original_world",
                    as_of=T0,authorized=True,source_capture_consent=consent,
                    independent_telemetry_reviewed=independent)
        with self.assertRaises(ThreatRadarError):
            score_recorded_probe_batch(
                script,rows[:14],self.judges[0],subject_id="original_world",
                as_of=T0,authorized=True,source_capture_consent=True,
                independent_telemetry_reviewed=True,min_trials=10)

    def test_cross_title_trace_and_altered_score_rejected(self):
        script=self.scripts()[0]
        rows=list(self.observations(script))
        rows[0]=replace(rows[0],subject_id="other_atlas")
        with self.assertRaisesRegex(ThreatRadarError,"unexpected title"):
            score_recorded_probe_batch(
                script,tuple(rows),self.judges[0],subject_id="original_world",
                as_of=T0,authorized=True,source_capture_consent=True,
                independent_telemetry_reviewed=True)
        rows=list(self.observations(script))
        rows[0]=replace(rows[0],observed_at="2030-01-01T00:00:00Z")
        with self.assertRaisesRegex(ThreatRadarError,"future"):
            score_recorded_probe_batch(
                script,tuple(rows),self.judges[0],subject_id="original_world",
                as_of=T0,authorized=True,source_capture_consent=True,
                independent_telemetry_reviewed=True)


if __name__=="__main__":
    unittest.main()
