"""Replay-driven quality evidence harness.

Consumes the landed deterministic replay interfaces — cognitive tapes,
foundation journals, and school snapshots — and emits a credential-free
pass/fail evidence document. No model, network, or CI policy is consulted.

This module must not grow a second replay core. Loading, integrity, and
divergence all go through the existing replay APIs.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from skeleton.foundation.journal import EventJournal, ReplayEngine
from skeleton.school.replay import JeevesReplay, ReplaySnapshot


def _load_cognition_replay() -> Any:
    """Load the cognition replay module without the package barrel export."""
    name = "_skeleton_quality_cognition_replay"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = Path(__file__).resolve().parents[1] / "cognition" / "replay.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("unable to load cognition replay interface")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ReplayTape = _load_cognition_replay().ReplayTape

SCHEMA_ID = "quality.replay_evidence.v1"
MAX_RUNS = 16
MAX_TIME_BUDGET_MS = 60_000.0
MAX_EVENTS = 10_000
MAX_SCENARIO_ID = 128
_SCENARIO_ID_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
)
_ALLOWED_SOURCES = frozenset({"cognition.tape", "foundation.journal", "school.snapshot"})
_ALLOWED_KINDS = frozenset({"correctness", "regression", "performance", "divergence"})
_MANIFEST_FIELDS = {
    "schema",
    "scenario_id",
    "kind",
    "source",
    "seed",
    "max_runs",
    "time_budget_ms",
    "trace",
    "candidate",
    "baseline_digest",
    "expect_divergence_at",
    "expected_duration_ms",
    "tolerances",
    "observed_duration_ms",
}
_CANONICAL_EVIDENCE_KEYS = (
    "schema",
    "scenario_id",
    "kind",
    "verdict",
    "passed",
    "reasons",
    "runs",
    "max_runs",
    "time_budget_ms",
    "trace_digests",
    "baseline_digest",
    "divergence",
    "tolerances",
    "envelope",
    "quarantine",
    "source",
    "seed",
)


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    QUARANTINE = "quarantine"
    TIMEOUT = "timeout"
    CORRUPT = "corrupt"


class QualityEvidenceError(ValueError):
    """Manifest or evidence document is not a usable quality record."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise QualityEvidenceError("value is not canonically serializable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise QualityEvidenceError(f"{name} must be an object")
    return value


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str], name: str) -> None:
    extra = sorted(set(payload) - allowed)
    if extra:
        raise QualityEvidenceError(f"{name} has unknown fields: {', '.join(extra)}")


def _bounded_int(value: object, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise QualityEvidenceError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise QualityEvidenceError(f"{name} is outside the accepted range")
    return value


def _bounded_float(value: object, name: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QualityEvidenceError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise QualityEvidenceError(f"{name} must be finite")
    if not minimum <= number <= maximum:
        raise QualityEvidenceError(f"{name} is outside the accepted range")
    return number


def _scenario_id(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_SCENARIO_ID:
        raise QualityEvidenceError("scenario_id must be a 1-128 character identifier")
    if value[0] in "._:-" or any(char not in _SCENARIO_ID_CHARS for char in value):
        raise QualityEvidenceError("scenario_id must be a normalized identifier")
    return value


def _sha256_hex(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise QualityEvidenceError(f"{name} must be a sha256 hex digest")
    if any(char not in "0123456789abcdef" for char in value):
        raise QualityEvidenceError(f"{name} must be a sha256 hex digest")
    return value


def _within(actual: float, expected: float, abs_tol: float, rel_tol: float) -> bool:
    return abs(actual - expected) <= (abs_tol + rel_tol * abs(expected))


def _placeholder_manifest(scenario_id: str = "invalid-manifest") -> ScenarioManifest:
    return ScenarioManifest(
        scenario_id=scenario_id,
        kind="correctness",
        source="cognition.tape",
        seed=0,
        max_runs=1,
        time_budget_ms=1.0,
        trace=(),
    )


@dataclass(frozen=True, slots=True)
class Tolerances:
    duration_ms: float = 0.0
    duration_rel: float = 0.0

    def to_mapping(self) -> dict[str, float]:
        return {"duration_ms": self.duration_ms, "duration_rel": self.duration_rel}

    @classmethod
    def from_mapping(cls, payload: object | None) -> Tolerances:
        if payload is None:
            return cls()
        data = _require_mapping(payload, "tolerances")
        _reject_unknown(data, {"duration_ms", "duration_rel"}, "tolerances")
        return cls(
            duration_ms=_bounded_float(
                data.get("duration_ms", 0.0), "duration_ms", minimum=0.0, maximum=MAX_TIME_BUDGET_MS
            ),
            duration_rel=_bounded_float(
                data.get("duration_rel", 0.0), "duration_rel", minimum=0.0, maximum=1.0
            ),
        )


@dataclass(frozen=True, slots=True)
class ScenarioManifest:
    scenario_id: str
    kind: str
    source: str
    seed: int
    max_runs: int
    time_budget_ms: float
    trace: Any
    candidate: Any = None
    baseline_digest: str = ""
    expect_divergence_at: int | None = None
    expected_duration_ms: float | None = None
    tolerances: Tolerances = Tolerances()
    observed_duration_ms: tuple[float, ...] = ()
    schema: str = SCHEMA_ID

    def to_mapping(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "scenario_id": self.scenario_id,
            "kind": self.kind,
            "source": self.source,
            "seed": self.seed,
            "max_runs": self.max_runs,
            "time_budget_ms": self.time_budget_ms,
            "trace": self.trace,
            "tolerances": self.tolerances.to_mapping(),
        }
        if self.candidate is not None:
            payload["candidate"] = self.candidate
        if self.baseline_digest:
            payload["baseline_digest"] = self.baseline_digest
        if self.expect_divergence_at is not None:
            payload["expect_divergence_at"] = self.expect_divergence_at
        if self.expected_duration_ms is not None:
            payload["expected_duration_ms"] = self.expected_duration_ms
        if self.observed_duration_ms:
            payload["observed_duration_ms"] = list(self.observed_duration_ms)
        return payload

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ScenarioManifest:
        data = _require_mapping(payload, "manifest")
        _reject_unknown(data, _MANIFEST_FIELDS, "manifest")
        if data.get("schema", SCHEMA_ID) != SCHEMA_ID:
            raise QualityEvidenceError("unsupported quality evidence schema")
        kind = data.get("kind")
        source = data.get("source")
        if kind not in _ALLOWED_KINDS:
            raise QualityEvidenceError("unknown scenario kind")
        if source not in _ALLOWED_SOURCES:
            raise QualityEvidenceError("unknown replay source")
        if "trace" not in data:
            raise QualityEvidenceError("manifest trace is required")
        divergence_at = data.get("expect_divergence_at")
        if divergence_at is not None:
            divergence_at = _bounded_int(
                divergence_at, "expect_divergence_at", minimum=0, maximum=MAX_EVENTS
            )
        expected_duration = data.get("expected_duration_ms")
        if expected_duration is not None:
            expected_duration = _bounded_float(
                expected_duration, "expected_duration_ms", minimum=0.0, maximum=MAX_TIME_BUDGET_MS
            )
        durations = data.get("observed_duration_ms", ())
        if isinstance(durations, (int, float, bool, str)) or durations is None:
            raise QualityEvidenceError("observed_duration_ms must be a list")
        observed = tuple(
            _bounded_float(item, "observed_duration_ms", minimum=0.0, maximum=MAX_TIME_BUDGET_MS)
            for item in durations
        )
        baseline_digest = data.get("baseline_digest", "")
        if baseline_digest:
            baseline_digest = _sha256_hex(baseline_digest, "baseline_digest")
        return cls(
            schema=SCHEMA_ID,
            scenario_id=_scenario_id(data.get("scenario_id")),
            kind=str(kind),
            source=str(source),
            seed=_bounded_int(data.get("seed", 0), "seed", minimum=0, maximum=2**32 - 1),
            max_runs=_bounded_int(data.get("max_runs", 1), "max_runs", minimum=1, maximum=MAX_RUNS),
            time_budget_ms=_bounded_float(
                data.get("time_budget_ms", 1_000.0),
                "time_budget_ms",
                minimum=1.0,
                maximum=MAX_TIME_BUDGET_MS,
            ),
            trace=data.get("trace"),
            candidate=data.get("candidate"),
            baseline_digest=str(baseline_digest),
            expect_divergence_at=divergence_at,
            expected_duration_ms=expected_duration,
            tolerances=Tolerances.from_mapping(data.get("tolerances")),
            observed_duration_ms=observed,
        )


load_manifest = ScenarioManifest.from_mapping


@dataclass(frozen=True, slots=True)
class EvidenceReport:
    scenario_id: str
    kind: str
    verdict: Verdict
    reasons: tuple[str, ...]
    runs: int
    max_runs: int
    time_budget_ms: float
    trace_digests: tuple[str, ...]
    baseline_digest: str
    divergence: dict[str, Any] | None
    tolerances: dict[str, float]
    envelope: dict[str, Any] | None
    quarantine: dict[str, str] | None
    source: str
    seed: int
    evidence_digest: str
    schema: str = SCHEMA_ID

    @property
    def passed(self) -> bool:
        return self.verdict is Verdict.PASS

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "scenario_id": self.scenario_id,
            "kind": self.kind,
            "verdict": self.verdict.value,
            "passed": self.passed,
            "reasons": list(self.reasons),
            "runs": self.runs,
            "max_runs": self.max_runs,
            "time_budget_ms": self.time_budget_ms,
            "trace_digests": list(self.trace_digests),
            "baseline_digest": self.baseline_digest,
            "divergence": None if self.divergence is None else dict(self.divergence),
            "tolerances": dict(self.tolerances),
            "envelope": None if self.envelope is None else dict(self.envelope),
            "quarantine": None if self.quarantine is None else dict(self.quarantine),
            "source": self.source,
            "seed": self.seed,
            "evidence_digest": self.evidence_digest,
        }


def _canonical_evidence_body(payload: Mapping[str, Any]) -> dict[str, Any]:
    missing = [key for key in _CANONICAL_EVIDENCE_KEYS if key not in payload]
    if missing:
        raise QualityEvidenceError(f"evidence missing fields: {', '.join(missing)}")
    return {key: payload[key] for key in _CANONICAL_EVIDENCE_KEYS}


def evidence_digest_for(payload: Mapping[str, Any]) -> str:
    return _digest(_canonical_evidence_body(payload))


def _report(
    manifest: ScenarioManifest,
    *,
    verdict: Verdict,
    reasons: Sequence[str],
    runs: int,
    trace_digests: Sequence[str],
    baseline_digest: str,
    divergence: dict[str, Any] | None = None,
    envelope: dict[str, Any] | None = None,
    quarantine: dict[str, str] | None = None,
) -> EvidenceReport:
    unique_reasons = tuple(dict.fromkeys(reason for reason in reasons if reason))
    body = {
        "schema": SCHEMA_ID,
        "scenario_id": manifest.scenario_id,
        "kind": manifest.kind,
        "verdict": verdict.value,
        "passed": verdict is Verdict.PASS,
        "reasons": list(unique_reasons),
        "runs": runs,
        "max_runs": manifest.max_runs,
        "time_budget_ms": manifest.time_budget_ms,
        "trace_digests": list(trace_digests),
        "baseline_digest": baseline_digest,
        "divergence": divergence,
        "tolerances": manifest.tolerances.to_mapping(),
        "envelope": envelope,
        "quarantine": quarantine,
        "source": manifest.source,
        "seed": manifest.seed,
    }
    return EvidenceReport(
        schema=SCHEMA_ID,
        scenario_id=manifest.scenario_id,
        kind=manifest.kind,
        verdict=verdict,
        reasons=unique_reasons,
        runs=runs,
        max_runs=manifest.max_runs,
        time_budget_ms=manifest.time_budget_ms,
        trace_digests=tuple(trace_digests),
        baseline_digest=baseline_digest,
        divergence=divergence,
        tolerances=manifest.tolerances.to_mapping(),
        envelope=envelope,
        quarantine=quarantine,
        source=manifest.source,
        seed=manifest.seed,
        evidence_digest=_digest(body),
    )


def _corrupt_report(reason: str, *, manifest: ScenarioManifest | None = None) -> EvidenceReport:
    return _report(
        manifest or _placeholder_manifest(),
        verdict=Verdict.CORRUPT,
        reasons=(reason,),
        runs=0,
        trace_digests=(),
        baseline_digest="" if manifest is None else manifest.baseline_digest,
    )


def _load_tape(trace: object) -> ReplayTape:
    if not isinstance(trace, (list, tuple)):
        raise QualityEvidenceError("cognition.tape trace must be a list of events")
    if len(trace) > MAX_EVENTS:
        raise QualityEvidenceError("trace exceeds event bound")
    try:
        tape = ReplayTape.from_events(trace)
    except (TypeError, ValueError, KeyError) as exc:
        raise QualityEvidenceError("corrupt cognition replay tape") from exc
    sequences = [event.sequence for event in tape.events]
    if sequences != list(range(len(tape.events))):
        raise QualityEvidenceError("corrupt cognition replay tape")
    return tape


def _tape_digest(tape: ReplayTape) -> str:
    return _digest(tape.export())


def _load_journal(trace: object) -> EventJournal:
    if not isinstance(trace, (list, tuple)):
        raise QualityEvidenceError("foundation.journal trace must be a list of entries")
    if len(trace) > MAX_EVENTS:
        raise QualityEvidenceError("trace exceeds event bound")
    journal = EventJournal()
    for index, raw in enumerate(trace):
        entry = _require_mapping(raw, "journal entry")
        try:
            topic = entry["topic"]
            payload = entry["payload"]
            timestamp = entry["timestamp"]
        except KeyError as exc:
            raise QualityEvidenceError("corrupt foundation journal trace") from exc
        if not isinstance(topic, str) or not topic or not isinstance(payload, Mapping):
            raise QualityEvidenceError("corrupt foundation journal trace")
        recorded = journal.append(
            topic,
            dict(payload),
            str(entry.get("correlation_id", "")),
            _bounded_float(timestamp, "timestamp", minimum=0.0, maximum=2**31),
        )
        expected_hash = entry.get("entry_hash")
        if expected_hash and recorded.entry_hash != expected_hash:
            raise QualityEvidenceError("corrupt foundation journal trace")
        if recorded.index != index:
            raise QualityEvidenceError("corrupt foundation journal trace")
    if not journal.integrity():
        raise QualityEvidenceError("corrupt foundation journal trace")
    return journal


def _journal_state(journal: EventJournal) -> dict[str, Any]:
    engine = ReplayEngine(journal)

    def handler(entry: Any, state: dict[str, Any]) -> None:
        events = state.setdefault("events", [])
        events.append({"index": entry.index, "topic": entry.topic, "payload": dict(entry.payload)})
        state["count"] = len(events)

    engine.on("*", handler)
    state = engine.replay()
    if not engine.verify_determinism():
        raise QualityEvidenceError("foundation journal replay is not deterministic")
    return state


def _journal_digest(journal: EventJournal) -> str:
    return _digest(_journal_state(journal))


def _load_snapshot(trace: object) -> ReplaySnapshot:
    data = _require_mapping(trace, "school.snapshot")
    required = (
        "session_id",
        "decision_ids",
        "predecessors",
        "record_hashes",
        "selected_actions",
        "rejected_actions",
        "evidence_ids",
        "policy_digests",
        "state_digests",
        "dispositions",
    )
    if any(key not in data for key in required):
        raise QualityEvidenceError("corrupt school replay snapshot")
    try:
        return ReplaySnapshot(
            session_id=str(data["session_id"]),
            decision_ids=tuple(data["decision_ids"]),
            predecessors=tuple(tuple(group) for group in data["predecessors"]),
            record_hashes=tuple(data["record_hashes"]),
            selected_actions=tuple(data["selected_actions"]),
            rejected_actions=tuple(data["rejected_actions"]),
            evidence_ids=tuple(data["evidence_ids"]),
            policy_digests=tuple(data["policy_digests"]),
            state_digests=tuple(data["state_digests"]),
            dispositions=tuple(data["dispositions"]),
        )
    except (TypeError, ValueError) as exc:
        raise QualityEvidenceError("corrupt school replay snapshot") from exc


def snapshot_payload(snapshot: ReplaySnapshot) -> dict[str, Any]:
    """Serialize a school ReplaySnapshot for a scenario manifest."""
    return {
        "session_id": snapshot.session_id,
        "decision_ids": list(snapshot.decision_ids),
        "predecessors": [list(group) for group in snapshot.predecessors],
        "record_hashes": list(snapshot.record_hashes),
        "selected_actions": list(snapshot.selected_actions),
        "rejected_actions": list(snapshot.rejected_actions),
        "evidence_ids": list(snapshot.evidence_ids),
        "policy_digests": list(snapshot.policy_digests),
        "state_digests": list(snapshot.state_digests),
        "dispositions": list(snapshot.dispositions),
    }


def _snapshot_digest(snapshot: ReplaySnapshot) -> str:
    return _digest(snapshot_payload(snapshot))


def _load_trace(source: str, trace: object) -> Any:
    if source == "cognition.tape":
        return _load_tape(trace)
    if source == "foundation.journal":
        return _load_journal(trace)
    return _load_snapshot(trace)


def _trace_digest(source: str, loaded: Any) -> str:
    if source == "cognition.tape":
        return _tape_digest(loaded)
    if source == "foundation.journal":
        return _journal_digest(loaded)
    return _snapshot_digest(loaded)


def _diverge(source: str, baseline: Any, candidate: Any) -> dict[str, Any] | None:
    if source == "cognition.tape":
        sequence = baseline.divergence(candidate)
        if sequence is None:
            return None
        return {"sequence": sequence, "reason": "cognition tape divergence"}
    if source == "foundation.journal":
        left_events = _journal_state(baseline).get("events", [])
        right_events = _journal_state(candidate).get("events", [])
        for index, (left, right) in enumerate(zip(left_events, right_events)):
            if left != right:
                return {"sequence": index, "reason": "foundation journal divergence"}
        if len(left_events) != len(right_events):
            return {
                "sequence": min(len(left_events), len(right_events)),
                "reason": "foundation journal divergence",
            }
        return None
    report = JeevesReplay().compare_snapshots(baseline, candidate)
    if report.identical:
        return None
    mismatch = report.mismatches[0]
    return {"sequence": mismatch.sequence, "reason": mismatch.reason}


def _repeat_payload(payload: Any, runs: int) -> tuple[Any, ...]:
    return tuple(payload for _ in range(runs))


def _candidate_payloads(
    manifest: ScenarioManifest,
    candidate: Any,
    candidates: Sequence[Any] | None,
) -> tuple[Any, ...]:
    if candidates is not None:
        if not isinstance(candidates, (list, tuple)) or not candidates:
            raise QualityEvidenceError("candidates must be a non-empty list of traces")
        return tuple(candidates)
    payload = manifest.trace if candidate is None and manifest.candidate is None else (
        candidate if candidate is not None else manifest.candidate
    )
    return _repeat_payload(payload, manifest.max_runs)

def _durations(
    manifest: ScenarioManifest, observed_duration_ms: Sequence[float] | None
) -> tuple[float, ...]:
    values = manifest.observed_duration_ms if observed_duration_ms is None else observed_duration_ms
    return tuple(
        _bounded_float(item, "observed_duration_ms", minimum=0.0, maximum=MAX_TIME_BUDGET_MS)
        for item in values
    )


def _envelope(manifest: ScenarioManifest, observed: Sequence[float]) -> dict[str, Any]:
    expected_ms = float(manifest.expected_duration_ms or 0.0)
    abs_tol = manifest.tolerances.duration_ms
    rel_tol = manifest.tolerances.duration_rel
    within = tuple(_within(value, expected_ms, abs_tol, rel_tol) for value in observed)
    return {
        "expected_ms": expected_ms,
        "abs_ms": abs_tol,
        "rel": rel_tol,
        "limit_ms": abs_tol + rel_tol * abs(expected_ms),
        "observed_ms": list(observed),
        "within": bool(observed) and all(within),
        "run_within": list(within),
    }


def run_harness(
    manifest: ScenarioManifest | Mapping[str, Any],
    *,
    candidate: Any = None,
    candidates: Sequence[Any] | None = None,
    observed_duration_ms: Sequence[float] | None = None,
    clock: Callable[[], float] | None = None,
) -> EvidenceReport:
    """Produce pass/fail quality evidence from a deterministic scenario manifest."""
    if not isinstance(manifest, ScenarioManifest):
        try:
            manifest = ScenarioManifest.from_mapping(manifest)
        except QualityEvidenceError as exc:
            return _corrupt_report(str(exc))

    try:
        baseline = _load_trace(manifest.source, manifest.trace)
        actual_baseline_digest = _trace_digest(manifest.source, baseline)
        if manifest.baseline_digest and manifest.baseline_digest != actual_baseline_digest:
            return _corrupt_report(
                "baseline digest does not match baseline trace",
                manifest=manifest,
            )
        baseline_digest = actual_baseline_digest
        payloads = _candidate_payloads(manifest, candidate, candidates)
        durations = _durations(manifest, observed_duration_ms)
    except QualityEvidenceError as exc:
        return _corrupt_report(str(exc), manifest=manifest)

    now = clock or time.monotonic
    started = now()
    digests: list[str] = []
    reasons: list[str] = []
    divergence: dict[str, Any] | None = None

    def elapsed_ms() -> float:
        return (now() - started) * 1000.0

    for run_index in range(manifest.max_runs):
        if elapsed_ms() > manifest.time_budget_ms:
            return _report(
                manifest,
                verdict=Verdict.TIMEOUT,
                reasons=("time budget exceeded", *reasons),
                runs=run_index,
                trace_digests=digests,
                baseline_digest=baseline_digest,
                divergence=divergence,
            )
        payload = payloads[run_index] if run_index < len(payloads) else payloads[-1]
        try:
            loaded = _load_trace(manifest.source, payload)
            digest = _trace_digest(manifest.source, loaded)
            if run_index == 0:
                divergence = _diverge(manifest.source, baseline, loaded)
        except QualityEvidenceError as exc:
            return _report(
                manifest,
                verdict=Verdict.CORRUPT,
                reasons=(str(exc), *reasons),
                runs=run_index,
                trace_digests=digests,
                baseline_digest=baseline_digest,
                divergence=divergence,
            )
        digests.append(digest)
        if elapsed_ms() > manifest.time_budget_ms:
            return _report(
                manifest,
                verdict=Verdict.TIMEOUT,
                reasons=("time budget exceeded", *reasons),
                runs=run_index + 1,
                trace_digests=digests,
                baseline_digest=baseline_digest,
                divergence=divergence,
            )

    envelope = None
    if manifest.kind == "performance":
        if manifest.expected_duration_ms is None or not durations:
            reasons.append("missing performance observations")
        else:
            envelope = _envelope(manifest, durations)
            if not envelope["within"]:
                reasons.append("performance envelope exceeded")
            if envelope["run_within"] and not all(envelope["run_within"]) and any(envelope["run_within"]):
                reasons.append("non-reproducible performance envelope")

    unique_digests = set(digests)
    if len(unique_digests) > 1:
        reasons.append("non-reproducible digests")
    if (
        len(unique_digests) == 1
        and next(iter(unique_digests)) != baseline_digest
        and manifest.kind != "divergence"
    ):
        reasons.append("baseline digest mismatch")

    expected_at = manifest.expect_divergence_at
    if expected_at is None:
        if divergence is not None and manifest.kind != "divergence":
            reasons.append(str(divergence["reason"]))
        if manifest.kind == "divergence" and divergence is None:
            reasons.append("expected divergence was not observed")
    elif divergence is None:
        reasons.append("expected divergence was not observed")
    elif int(divergence["sequence"]) != expected_at:
        reasons.append("divergence sequence mismatch")

    flaky = "non-reproducible digests" in reasons or "non-reproducible performance envelope" in reasons
    quarantine = {"reason": "non-reproducible results"} if flaky else None
    if flaky:
        verdict = Verdict.QUARANTINE
    elif reasons:
        verdict = Verdict.FAIL
    else:
        verdict = Verdict.PASS
    return _report(
        manifest,
        verdict=verdict,
        reasons=reasons,
        runs=len(digests),
        trace_digests=digests,
        baseline_digest=baseline_digest,
        divergence=divergence,
        envelope=envelope,
        quarantine=quarantine,
    )


def verify_evidence(payload: Mapping[str, Any]) -> EvidenceReport:
    """Fail closed on tampered or incomplete evidence documents."""
    try:
        data = _require_mapping(payload, "evidence")
        _reject_unknown(data, set(_CANONICAL_EVIDENCE_KEYS) | {"evidence_digest"}, "evidence")
        body = _canonical_evidence_body(data)
        digest = _sha256_hex(data.get("evidence_digest"), "evidence_digest")
        verdict = Verdict(str(body["verdict"]))
        expected = _digest(body)
    except (QualityEvidenceError, ValueError, KeyError, TypeError) as exc:
        return _corrupt_report(f"corrupt evidence: {exc}", manifest=_placeholder_manifest("corrupt-evidence"))
    if digest != expected:
        return _corrupt_report(
            "corrupt evidence: digest mismatch",
            manifest=_placeholder_manifest(str(body.get("scenario_id") or "corrupt-evidence")),
        )
    if body["schema"] != SCHEMA_ID:
        return _corrupt_report(
            "corrupt evidence: unsupported schema",
            manifest=_placeholder_manifest(str(body["scenario_id"])),
        )
    if not isinstance(body["passed"], bool) or body["passed"] != (verdict is Verdict.PASS):
        return _corrupt_report(
            "corrupt evidence: passed flag disagrees with verdict",
            manifest=_placeholder_manifest(str(body["scenario_id"])),
        )
    try:
        scenario_id = _scenario_id(body["scenario_id"])
        kind = body["kind"]
        if kind not in _ALLOWED_KINDS:
            raise QualityEvidenceError("unknown scenario kind")
        source = body["source"]
        if source not in _ALLOWED_SOURCES:
            raise QualityEvidenceError("unknown replay source")
        max_runs = _bounded_int(body["max_runs"], "max_runs", minimum=1, maximum=MAX_RUNS)
        runs = _bounded_int(body["runs"], "runs", minimum=0, maximum=MAX_RUNS)
        if runs > max_runs:
            raise QualityEvidenceError("runs exceeds max_runs")
        time_budget_ms = _bounded_float(
            body["time_budget_ms"],
            "time_budget_ms",
            minimum=1.0,
            maximum=MAX_TIME_BUDGET_MS,
        )
        reasons_raw = body["reasons"]
        if not isinstance(reasons_raw, list) or any(
            not isinstance(reason, str) or not reason for reason in reasons_raw
        ):
            raise QualityEvidenceError("reasons must be a list of non-empty strings")
        trace_raw = body["trace_digests"]
        if not isinstance(trace_raw, list) or len(trace_raw) > max_runs:
            raise QualityEvidenceError("trace_digests must be a bounded list")
        trace_digests = tuple(
            _sha256_hex(item, "trace_digest") for item in trace_raw
        )
        if len(trace_digests) != runs:
            raise QualityEvidenceError("trace_digests count must equal runs")
        if (verdict is Verdict.PASS) != (len(reasons_raw) == 0):
            raise QualityEvidenceError("verdict and reasons are inconsistent")
        baseline_raw = body["baseline_digest"]
        if baseline_raw != "":
            baseline_digest = _sha256_hex(baseline_raw, "baseline_digest")
        else:
            baseline_digest = ""
        tolerances = Tolerances.from_mapping(body["tolerances"]).to_mapping()
        for name in ("divergence", "envelope", "quarantine"):
            value = body[name]
            if value is not None and not isinstance(value, Mapping):
                raise QualityEvidenceError(f"{name} must be an object or null")
        if verdict is Verdict.QUARANTINE:
            if body["quarantine"] is None:
                raise QualityEvidenceError("quarantine verdict requires quarantine evidence")
        elif body["quarantine"] is not None:
            raise QualityEvidenceError("quarantine evidence requires quarantine verdict")
        if body["envelope"] is not None and kind != "performance":
            raise QualityEvidenceError("performance envelope requires performance kind")
        seed = _bounded_int(body["seed"], "seed", minimum=0, maximum=2**32 - 1)
    except (QualityEvidenceError, KeyError, TypeError) as exc:
        return _corrupt_report(
            f"corrupt evidence: {exc}",
            manifest=_placeholder_manifest(str(body.get("scenario_id") or "corrupt-evidence")),
        )
    return EvidenceReport(
        schema=SCHEMA_ID,
        scenario_id=scenario_id,
        kind=kind,
        verdict=verdict,
        reasons=tuple(reasons_raw),
        runs=runs,
        max_runs=max_runs,
        time_budget_ms=time_budget_ms,
        trace_digests=trace_digests,
        baseline_digest=baseline_digest,
        divergence=None if body["divergence"] is None else dict(body["divergence"]),
        tolerances=tolerances,
        envelope=None if body["envelope"] is None else dict(body["envelope"]),
        quarantine=None if body["quarantine"] is None else dict(body["quarantine"]),
        source=source,
        seed=seed,
        evidence_digest=digest,
    )


__all__ = [
    "SCHEMA_ID",
    "EvidenceReport",
    "QualityEvidenceError",
    "ReplayTape",
    "ScenarioManifest",
    "Tolerances",
    "Verdict",
    "evidence_digest_for",
    "load_manifest",
    "run_harness",
    "snapshot_payload",
    "verify_evidence",
]
