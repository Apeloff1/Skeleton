"""Durable, payload-free native inference telemetry on canonical SQLite.

This store observes existing committed native inference receipts. It does
not call a model, change capacity admission, touch model private paths, store
prompts/responses, or treat operator-supplied timings as attested device
performance. It refuses noncommitted results and binds each sample to the
active tenant, operator, model and tokenizer. No metrics can create grants.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import time
from typing import Any, Callable, Sequence

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.laptop_runtime.result_protocol import verify_turn_receipt
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase

from .contracts import (
    ContractHold, digest, exact_integer, fingerprint, identifier,
    finite, text,
)
from .health import quantiles


class NativeTelemetryHold(ContractHold):
    """A telemetry sample cannot be linked to a committed native receipt."""


_TELEMETRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS jeeves_native_observations (
  observation_id TEXT NOT NULL,
  tenant TEXT NOT NULL,
  subject TEXT NOT NULL,
  model_sha256 TEXT NOT NULL,
  tokenizer_sha256 TEXT NOT NULL,
  session_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  prompt_sha256 TEXT NOT NULL,
  output_sha256 TEXT NOT NULL,
  generated_tokens INTEGER NOT NULL,
  prompt_tokens INTEGER NOT NULL,
  duration_ms INTEGER NOT NULL,
  sampled_ns INTEGER NOT NULL,
  sample_sha256 TEXT NOT NULL,
  PRIMARY KEY (tenant,subject,model_sha256,tokenizer_sha256,observation_id),
  UNIQUE (tenant,subject,model_sha256,tokenizer_sha256,session_id,request_id)
)
"""


@dataclass(frozen=True, slots=True)
class NativeObservation:
    observation_id: str
    tenant: str
    subject: str
    model_sha256: str
    tokenizer_sha256: str
    session_id: str
    request_id: str
    prompt_sha256: str
    output_sha256: str
    generated_tokens: int
    prompt_tokens: int
    duration_ms: int
    sampled_ns: int

    def __post_init__(self):
        for attr in (
            "observation_id","tenant","subject","session_id","request_id",
        ):
            identifier(getattr(self,attr),attr)
        for attr in (
            "model_sha256","tokenizer_sha256","prompt_sha256","output_sha256",
        ):
            digest(getattr(self,attr))
        exact_integer(self.generated_tokens,maximum=8192)
        exact_integer(self.prompt_tokens,maximum=131072)
        exact_integer(self.duration_ms,maximum=600000)
        exact_integer(self.sampled_ns,maximum=10**30)

    @property
    def fingerprint(self)->str:
        return fingerprint({
          "schema":"jeeves.native_inference_observation.v1",
          "id":self.observation_id,
          "tenant":self.tenant,"subject":self.subject,
          "model":self.model_sha256,"tokenizer":self.tokenizer_sha256,
          "session":self.session_id,"request":self.request_id,
          "prompt":self.prompt_sha256,"output":self.output_sha256,
          "prompt_tokens":self.prompt_tokens,
          "generated_tokens":self.generated_tokens,
          "duration_ms":self.duration_ms,"sampled_ns":self.sampled_ns,
        })

    def to_public_record(self):
        return {
          "schema":"jeeves.native_inference_observation.v1",
          "observation_id":self.observation_id,
          "scope_sha256":fingerprint({
              "tenant":self.tenant,"subject":self.subject,
              "model":self.model_sha256,"tokenizer":self.tokenizer_sha256,
          }),
          "prompt_sha256":self.prompt_sha256,
          "output_sha256":self.output_sha256,
          "prompt_tokens":self.prompt_tokens,
          "generated_tokens":self.generated_tokens,
          "duration_ms":self.duration_ms,
          "sample_sha256":self.fingerprint,
          "timing_sensor_independently_attested":False,
          "actual_device_pressure_qualified":False,
          "release_certified":False,
        }


class NativeTelemetryStore:
    """One protected SQLite authority; immutable native receipt observations."""

    def __init__(self,worker:Any,*,maximum_observations:int=10000,
                 clock_ns:Callable[[],int]=time.time_ns):
        if worker is None or not hasattr(worker,"spine") or not isinstance(
            worker.spine.db,SpineDatabase
        ):
            raise NativeTelemetryHold("canonical native SQLite supervisor required")
        exact_integer(maximum_observations,minimum=1,maximum=100000)
        if not callable(clock_ns):
            raise NativeTelemetryHold("host observation clock required")
        self.worker=worker
        self.db=worker.spine.db
        self.identity=ActiveModel.from_supervisor(worker)
        self.maximum_observations=maximum_observations
        self.clock_ns=clock_ns
        self.db.inspect()
        with self.db.transaction() as conn:
            conn.execute(_TELEMETRY_SCHEMA)

    def _live(self):
        if ActiveModel.from_supervisor(self.worker)!=self.identity:
            raise NativeTelemetryHold("model or principal changed after telemetry binding")

    def _scope(self):
        i=self.identity
        return i.tenant,i.subject,i.model_sha256,i.tokenizer_sha256

    def _row(self,raw):
        if raw is None:
            raise NativeTelemetryHold("native observation not found")
        try:
            item=NativeObservation(*raw[:-1])
        except (ValueError,TypeError) as exc:
            raise NativeTelemetryHold("malformed native observation") from exc
        if item.fingerprint!=raw[-1]:
            raise NativeTelemetryHold("persisted observation hash mismatch")
        if (item.tenant,item.subject,item.model_sha256,
            item.tokenizer_sha256)!=self._scope():
            raise NativeTelemetryHold("foreign telemetry principal")
        return item

    def _receipt(self,session_id,request_id,prompt,seed,temperature):
        text(prompt,maximum_bytes=self.worker.spine.limits.input_bytes)
        identifier(session_id,"session")
        identifier(request_id,"request")
        exact_integer(seed,maximum=2**32-1)
        finite(temperature,minimum=0.000000001,maximum=2)
        result=self.worker.spine.replay(
            session_id,request_id,prompt,seed=seed,
            temperature=temperature,
        )
        if result is None:
            raise NativeTelemetryHold("uncommitted request cannot become a telemetry pass")
        proven=verify_turn_receipt(
            result,
            model_sha256=self.identity.model_sha256,
            tokenizer_sha256=self.identity.tokenizer_sha256,
        )
        if proven.get("replayed") is not True:
            raise NativeTelemetryHold("native replay-only telemetry is required")
        return proven

    def record_committed(
        self,*,observation_id:str,session_id:str,request_id:str,prompt:str,
        seed:int=0,temperature:float=0.8,duration_ms:int,
    )->NativeObservation:
        """Require an actual saved and independently re-read inference receipt.

        The duration is a host-measured advisory quantity, not a security
        entitlement or independently attested hardware profiling result.
        """
        self._live()
        identifier(observation_id,"observation")
        exact_integer(duration_ms,maximum=600000)
        proof=self._receipt(session_id,request_id,prompt,seed,temperature)
        sample=NativeObservation(
            observation_id,*self._scope(),session_id,request_id,
            sha256(prompt.encode("utf-8","strict")).hexdigest(),
            proof["output_sha256"],
            proof["generated_tokens"],proof["prompt_tokens"],
            duration_ms,exact_integer(self.clock_ns(),maximum=10**30),
        )
        with self.db.transaction() as conn:
            previous=conn.execute(
              "SELECT observation_id,tenant,subject,model_sha256,tokenizer_sha256,"
              "session_id,request_id,prompt_sha256,output_sha256,generated_tokens,"
              "prompt_tokens,duration_ms,sampled_ns,sample_sha256 "
              "FROM jeeves_native_observations WHERE tenant=? AND subject=? "
              "AND model_sha256=? AND tokenizer_sha256=? AND observation_id=?",
              (*self._scope(),observation_id),
            ).fetchone()
            if previous is not None:
                prior=self._row(previous)
                if prior==sample:
                    return prior
                raise NativeTelemetryHold("observation identity cannot be overwritten")
            count=conn.execute(
              "SELECT COUNT(*) FROM jeeves_native_observations WHERE "
              "tenant=? AND subject=? AND model_sha256=? AND tokenizer_sha256=?",
              self._scope(),
            ).fetchone()[0]
            if count>=self.maximum_observations:
                raise NativeTelemetryHold("telemetry inventory full")
            conn.execute(
              "INSERT INTO jeeves_native_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (sample.observation_id,*self._scope(),session_id,request_id,
               sample.prompt_sha256,sample.output_sha256,
               sample.generated_tokens,sample.prompt_tokens,
               duration_ms,sample.sampled_ns,sample.fingerprint),
            )
            return sample

    def inspect(self,observation_id:str)->NativeObservation:
        self._live()
        identifier(observation_id,"observation")
        with self.db.snapshot() as conn:
            row=conn.execute(
              "SELECT observation_id,tenant,subject,model_sha256,tokenizer_sha256,"
              "session_id,request_id,prompt_sha256,output_sha256,generated_tokens,"
              "prompt_tokens,duration_ms,sampled_ns,sample_sha256 "
              "FROM jeeves_native_observations WHERE tenant=? AND subject=? "
              "AND model_sha256=? AND tokenizer_sha256=? AND observation_id=?",
              (*self._scope(),observation_id),
            ).fetchone()
            return self._row(row)

    def list_observations(self,*,limit:int=256):
        self._live()
        exact_integer(limit,minimum=1,maximum=10000)
        with self.db.snapshot() as conn:
            rows=conn.execute(
              "SELECT observation_id,tenant,subject,model_sha256,tokenizer_sha256,"
              "session_id,request_id,prompt_sha256,output_sha256,generated_tokens,"
              "prompt_tokens,duration_ms,sampled_ns,sample_sha256 "
              "FROM jeeves_native_observations WHERE tenant=? AND subject=? "
              "AND model_sha256=? AND tokenizer_sha256=? "
              "ORDER BY sampled_ns,observation_id LIMIT ?",
              (*self._scope(),limit),
            ).fetchall()
            return tuple(self._row(row) for row in rows)

    def summarize(self,*,maximum_samples:int=10000):
        """Percentiles are observational; unknown hardware remains unqualified."""
        self._live()
        exact_integer(maximum_samples,minimum=1,maximum=10000)
        with self.db.snapshot() as conn:
            rows=conn.execute(
              "SELECT observation_id,tenant,subject,model_sha256,tokenizer_sha256,"
              "session_id,request_id,prompt_sha256,output_sha256,generated_tokens,"
              "prompt_tokens,duration_ms,sampled_ns,sample_sha256 "
              "FROM jeeves_native_observations WHERE tenant=? AND subject=? "
              "AND model_sha256=? AND tokenizer_sha256=? "
              "ORDER BY sampled_ns DESC,observation_id DESC LIMIT ?",
              (*self._scope(),maximum_samples+1),
            ).fetchall()
            if len(rows)>maximum_samples:
                raise NativeTelemetryHold("unbounded telemetry window")
            samples=tuple(self._row(row) for row in rows)
        if not samples:
            return {
              "schema":"jeeves.native_telemetry_summary.v1",
              "observations":0,"latency_ms_quantiles":{},
              "generated_tokens":0,"prompt_tokens":0,
              "derived_generated_tokens_per_second":None,
              "actual_device_pressure_qualified":False,
              "release_certified":False,
            }
        latencies=tuple(float(s.duration_ms) for s in samples)
        total_generated=sum(s.generated_tokens for s in samples)
        time_ms=sum(s.duration_ms for s in samples)
        return {
          "schema":"jeeves.native_telemetry_summary.v1",
          "observations":len(samples),
          "latency_ms_quantiles":quantiles(latencies),
          "generated_tokens":total_generated,
          "prompt_tokens":sum(s.prompt_tokens for s in samples),
          "derived_generated_tokens_per_second":(
              total_generated*1000/time_ms if time_ms else None
          ),
          "model_sha256":self.identity.model_sha256,
          "tokenizer_sha256":self.identity.tokenizer_sha256,
          "measurement_independently_attested":False,
          "actual_device_pressure_qualified":False,
          "release_certified":False,
        }


__all__=["NativeTelemetryHold","NativeObservation","NativeTelemetryStore"]
