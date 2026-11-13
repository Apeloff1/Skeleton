"""Real SQLite telemetry receipt validation with synthetic native generation.

This covers principal, hashing, custody, cold restart, replay and bounded
metrics. The token generator is deliberately synthetic and does NOT witness
physical GGUF, hardware pressure, real accuracy or product release status.
"""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity,SpineLimits
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.jeeves.native_fabric.telemetry_store import (
    NativeTelemetryHold,NativeObservation,NativeTelemetryStore,
)
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL,TOKENIZER,SyntheticallyGenerated,
)


@unittest.skipUnless(os.name=="posix" and Path("/proc/self/fd").is_dir(),
                     "canonical SQLite requires Linux /proc")
class TestNativeTelemetryCustody(unittest.TestCase):
    SESSION="telemetry_session"
    REQUEST="telemetry_request"
    PROMPT="Secret operator task: native inference only."

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=None
        self.gate=None
        self._open()
        self.addCleanup(self._close)
        self.clock=[1700000000000000000]
        self.store=self._store()

    def _close(self):
        if self.gate is not None:
            self.gate.close()
            self.gate=None
        if self.db is not None:
            self.db.close()
            self.db=None

    def _open(self,*,subject="operator"):
        self.db=SpineDatabase(self.tmp.name)
        self.gate=SessionGate(self.tmp.name)
        self.backend=SyntheticallyGenerated()
        self.spine=ExecutionSpine(
            db=self.db,session_gate=self.gate,
            identity=Identity("local",subject,MODEL,TOKENIZER),
            backend=self.backend,
            limits=SpineLimits(
                input_bytes=32768,response_bytes=131072,
                max_output_tokens=128,context_tokens=4096,
            ),
        )
        self.worker=SupervisedAI(self.spine)

    def _cold(self,*,subject="operator"):
        self._close()
        self._open(subject=subject)
        self.store=self._store()

    def _store(self,*,maximum=10000):
        return NativeTelemetryStore(
            self.worker,maximum_observations=maximum,
            clock_ns=lambda:self.clock[0] if hasattr(self,"clock") else 1700000000000000000,
        )

    def _committed(self,*,session=None,request=None,prompt=None):
        ss=session or self.SESSION
        rr=request or self.REQUEST
        pp=prompt or self.PROMPT
        self.spine.create(ss)
        self.worker.turn(ss,rr,pp,seed=0,temperature=0.8)
        return ss,rr,pp

    def _record(self,*,observation="observe_one",duration=250,
                session=None,request=None,prompt=None):
        return self.store.record_committed(
            observation_id=observation,
            session_id=session or self.SESSION,
            request_id=request or self.REQUEST,
            prompt=prompt or self.PROMPT,
            seed=0,temperature=0.8,duration_ms=duration,
        )

    def test_only_committed_native_receipt_becomes_metric(self):
        self._committed()
        item=self._record()
        self.assertEqual(item.generated_tokens,16)
        self.assertEqual(item.prompt_tokens,48)
        self.assertEqual(item.duration_ms,250)
        self.assertEqual(self.store.inspect(item.observation_id),item)
        self.assertEqual(self.backend.calls,1)

    def test_public_sample_never_discloses_private_prompt(self):
        self._committed()
        item=self._record()
        self.assertNotIn(self.PROMPT,str(item.to_public_record()))
        self.assertFalse(item.to_public_record()["release_certified"])
        self.assertFalse(item.to_public_record()["actual_device_pressure_qualified"])

    def test_cold_reopen_preserves_exact_sample(self):
        self._committed()
        item=self._record()
        self._cold()
        restored=self.store.inspect(item.observation_id)
        self.assertEqual(restored,item)
        self.assertEqual(self.backend.calls,0)

    def test_uncommitted_request_cannot_be_observed(self):
        self.spine.create(self.SESSION)
        with self.assertRaises(NativeTelemetryHold):
            self._record()
        self.assertEqual(self.backend.calls,0)

    def test_missing_session_cannot_be_observed(self):
        with self.assertRaises(Exception):
            self._record()

    def test_failed_native_generation_cannot_be_counted(self):
        self.backend.fail=True
        self.spine.create(self.SESSION)
        with self.assertRaises(RuntimeError):
            self.worker.turn(self.SESSION,self.REQUEST,self.PROMPT)
        with self.assertRaises(NativeTelemetryHold):
            self._record()
        self.assertEqual(self.backend.calls,1)

    def test_prompt_mutation_under_same_request_denied(self):
        self._committed()
        with self.assertRaises(Exception):
            self._record(prompt="Different private prompt")
        self.assertEqual(self.backend.calls,1)

    def test_wrong_seed_or_sampling_denied(self):
        self._committed()
        with self.assertRaises(Exception):
            self.store.record_committed(
                observation_id="badseed",session_id=self.SESSION,
                request_id=self.REQUEST,prompt=self.PROMPT,
                seed=17,temperature=0.8,duration_ms=250,
            )

    def test_wrong_model_owner_cannot_read_or_append_samples(self):
        self._committed()
        self._record()
        self._cold(subject="foreign")
        with self.assertRaises(NativeTelemetryHold):
            self.store.inspect("observe_one")
        with self.assertRaises(Exception):
            self._record()
        self.assertEqual(self.backend.calls,0)

    def test_aggregate_quality_reports_are_observational(self):
        self._committed()
        self._record()
        summary=self.store.summarize()
        self.assertEqual(summary["observations"],1)
        self.assertEqual(summary["generated_tokens"],16)
        self.assertEqual(summary["prompt_tokens"],48)
        self.assertAlmostEqual(summary["derived_generated_tokens_per_second"],64)
        self.assertFalse(summary["measurement_independently_attested"])
        self.assertFalse(summary["actual_device_pressure_qualified"])

    def test_empty_aggregate_is_held_as_unqualified(self):
        summary=self.store.summarize()
        self.assertEqual(summary["observations"],0)
        self.assertIsNone(summary["derived_generated_tokens_per_second"])
        self.assertFalse(summary["release_certified"])

    def test_multiple_sessions_have_bounded_latency_distribution(self):
        for i,duration in enumerate((100,200,300),start=1):
            s=f"session_{i}"
            r=f"request_{i}"
            self._committed(session=s,request=r)
            self._record(observation=f"obs_{i}",session=s,request=r,duration=duration)
            self.clock[0]+=10
        result=self.store.summarize()
        self.assertEqual(result["observations"],3)
        self.assertEqual(result["generated_tokens"],48)
        self.assertEqual(result["latency_ms_quantiles"]["p5000"],200)

    def test_checksum_tamper_refuses_telemetry_record(self):
        self._committed()
        self._record()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_observations SET sample_sha256=?",
                ("f"*64,),
            )
        with self.assertRaises(NativeTelemetryHold):
            self.store.inspect("observe_one")

    def test_token_count_tamper_refuses_telemetry_record(self):
        self._committed()
        self._record()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_observations SET generated_tokens=123",
            )
        with self.assertRaises(NativeTelemetryHold):
            self.store.inspect("observe_one")

    def test_transcript_tamper_denies_new_observation(self):
        self._committed()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE turns SET response=?",(b"tampered!",),
            )
        with self.assertRaises(Exception):
            self._record()

    def test_duplicate_observation_id_cannot_change_duration(self):
        self._committed()
        self._record(duration=250)
        with self.assertRaises(NativeTelemetryHold):
            self._record(duration=251)
        self.assertEqual(len(self.store.list_observations()),1)

    def test_duplicate_observation_id_same_receipt_is_idempotent_same_clock(self):
        self._committed()
        first=self._record()
        again=self._record()
        self.assertEqual(first,again)
        self.assertEqual(len(self.store.list_observations()),1)

    def test_reusing_request_identity_cannot_double_count(self):
        self._committed()
        self._record()
        with self.assertRaises(Exception):
            self._record(observation="second_id")
        self.assertEqual(len(self.store.list_observations()),1)

    def test_inventory_ceiling_refuses_extra_telemetry(self):
        self.store=self._store(maximum=1)
        self._committed()
        self._record()
        self._committed(session="another",request="another_request")
        with self.assertRaises(NativeTelemetryHold):
            self._record(
                observation="second",session="another",request="another_request",
            )

    def test_empty_or_boolean_metric_amount_refused(self):
        self._committed()
        for value in (-1,True,600001,1.5):
            with self.subTest(value=value),self.assertRaises(Exception):
                self._record(observation="invalid_obs",duration=value)

    def test_foreign_scope_does_not_see_sample_in_inventory(self):
        self._committed()
        self._record()
        self._cold(subject="foreign")
        self.assertEqual(self.store.list_observations(),())

    def test_no_prompt_text_stored_in_telemetry_table(self):
        self._committed()
        self._record()
        with self.db.snapshot() as conn:
            table=conn.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE name='jeeves_native_observations'",
            ).fetchone()[0]
        self.assertNotIn("prompt_text",table)
        self.assertNotIn(self.PROMPT,str(self.store.summarize()))


if __name__=="__main__":
    unittest.main()
