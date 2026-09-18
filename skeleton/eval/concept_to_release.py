"""Concept-to-release benchmark arena and evidence scoreboard.

Measurement infrastructure for ``eval.concept_to_release``. The arena scores
end-to-end runs from creator/game/world/quality/release evidence only. It does
not mutate those subsystems, does not guess missing metrics, and refuses
self-certified model claims.

Evidence contracts consumed (read-only shapes, not rewritten here):
- quality: ``skeleton.organism.quality_state`` rows (``accepted``, ``score``)
- game: ``skeleton.game.mechanics`` bounded generation timings
- world: replay/live digest pair for determinism
- creator: iteration latency, edit success, explicit approval
- release: ``scripts/release_provenance.py`` payload shape (schema, commit,
  artifacts, sbom refs)

Raw evidence is retained separately from the run summary. The summary digest
covers the raw evidence refs, so a summary cannot be produced without them.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from skeleton.kernel.errors import KernelError

BENCHMARK_ID: Final = "eval.concept_to_release"
BENCHMARK_SCHEMA_VERSION: Final = 1
METRIC_CATALOG_VERSION: Final = 1
KIND_RUN: Final = "concept-to-release-run"
KIND_SUMMARY: Final = "concept-to-release-summary"
KIND_RAW: Final = "concept-to-release-raw-evidence"

SCORE_DIMENSIONS: Final[tuple[str, ...]] = (
    "correctness",
    "iteration_latency",
    "editability",
    "determinism_replay",
    "security",
    "provenance",
    "performance",
    "creator_control",
    "release_completeness",
)

ALLOWED_SOURCES: Final[tuple[str, ...]] = (
    "creator",
    "game",
    "world",
    "quality",
    "release",
)

# Matches scripts/release_provenance.py commit validation.
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_RELEASE_SCHEMA_VERSION: Final = 1

MAX_EVIDENCE_BYTES: Final = 16_384
MAX_EVIDENCE_ITEMS: Final = 16
MAX_FRESHNESS_SECONDS: Final = 7 * 24 * 60 * 60
DEFAULT_FRESHNESS_SECONDS: Final = 24 * 60 * 60

_FORBIDDEN_CLAIM_KEYS: Final[frozenset[str]] = frozenset(
    {
        "self_certified",
        "self_score",
        "model_claim",
        "model_self_score",
        "llm_self_grade",
        "self_grade",
    }
)


class ConceptToReleaseError(KernelError):
    """Fail-closed evaluation error. Never coerced into a guessed score."""

    code = "EVAL.CONCEPT_TO_RELEASE"
    http_status = 400


@dataclass(frozen=True, slots=True)
class MetricSpec:
    dimension: str
    version: int
    sources: tuple[str, ...]
    required_inputs: tuple[str, ...]
    description: str


METRIC_SPECS: Final[Mapping[str, MetricSpec]] = MappingProxyType(
    {
        "correctness": MetricSpec(
            dimension="correctness",
            version=1,
            sources=("quality", "game"),
            required_inputs=("accepted", "score"),
            description="Quality-or-game acceptance plus finite unit-interval score.",
        ),
        "iteration_latency": MetricSpec(
            dimension="iteration_latency",
            version=1,
            sources=("creator",),
            required_inputs=("latency_ms", "budget_ms"),
            description="Creator iteration latency versus an explicit budget.",
        ),
        "editability": MetricSpec(
            dimension="editability",
            version=1,
            sources=("creator",),
            required_inputs=("attempted_edits", "successful_edits"),
            description="Successful creator edits over attempted edits.",
        ),
        "determinism_replay": MetricSpec(
            dimension="determinism_replay",
            version=1,
            sources=("world",),
            required_inputs=("replay_digest", "live_digest"),
            description="World live digest must equal the replay digest.",
        ),
        "security": MetricSpec(
            dimension="security",
            version=1,
            sources=("quality", "release"),
            required_inputs=("blocking_findings",),
            description="Zero blocking security findings from quality or release evidence.",
        ),
        "provenance": MetricSpec(
            dimension="provenance",
            version=1,
            sources=("release",),
            required_inputs=("schema_version", "source", "artifacts"),
            description="Release provenance schema, source commit, and artifact digests.",
        ),
        "performance": MetricSpec(
            dimension="performance",
            version=1,
            sources=("game", "quality"),
            required_inputs=("elapsed_ms", "budget_ms"),
            description="Game or quality elapsed time versus an explicit budget.",
        ),
        "creator_control": MetricSpec(
            dimension="creator_control",
            version=1,
            sources=("creator",),
            required_inputs=("explicit_approval", "unapproved_overrides"),
            description="Creator explicit approval with no unapproved overrides.",
        ),
        "release_completeness": MetricSpec(
            dimension="release_completeness",
            version=1,
            sources=("release",),
            required_inputs=("source", "artifacts", "sbom_refs"),
            description="Release commit, artifacts, and SBOM refs from provenance shape.",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    source: str
    dimension: str
    observed_at: int
    payload: Mapping[str, Any]
    digest: str


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    schema_version: int
    source_commit: str
    evaluated_at: int
    items: tuple[EvidenceItem, ...]
    freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS
    metric_versions: Mapping[str, int] | None = None


def canonical_dumps(value: Any) -> str:
    """Return canonical JSON. Non-finite numbers and non-JSON types fail closed."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ConceptToReleaseError(
            "evidence is not canonical JSON",
            context={"reason": "non_canonical_json"},
        ) from exc


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_dumps(value).encode("utf-8")).hexdigest()


def _require_int(name: str, value: Any, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConceptToReleaseError(
            f"{name} must be an integer",
            context={"field": name},
        )
    if minimum is not None and value < minimum:
        raise ConceptToReleaseError(
            f"{name} is out of bounds",
            context={"field": name, "minimum": minimum},
        )
    return value


def _validate_commit(value: Any) -> str:
    if not isinstance(value, str) or not _COMMIT_RE.fullmatch(value):
        raise ConceptToReleaseError(
            "source commit must be a 40-64 character hexadecimal Git object ID",
            context={"reason": "invalid_source_commit"},
        )
    return value.lower()


def _validate_digest(value: Any, *, field: str = "digest") -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ConceptToReleaseError(
            f"{field} must be a 64-character lowercase hex SHA-256 digest",
            context={"field": field},
        )
    return value


def _digests_match(actual: str, expected: str) -> bool:
    return hmac.compare_digest(actual.encode("ascii"), expected.encode("ascii"))


def _claim_keys(payload: Mapping[str, Any]) -> tuple[str, ...]:
    found: list[str] = []
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            for key, nested in current.items():
                if key in _FORBIDDEN_CLAIM_KEYS:
                    found.append(str(key))
                else:
                    stack.append(nested)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)
    return tuple(sorted(set(found)))


def _freeze_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or isinstance(payload, (str, bytes)):
        raise ConceptToReleaseError(
            "evidence payload must be a mapping",
            context={"reason": "payload_not_mapping"},
        )
    encoded = canonical_dumps(dict(payload)).encode("utf-8")
    if len(encoded) > MAX_EVIDENCE_BYTES:
        raise ConceptToReleaseError(
            "evidence payload exceeds bound",
            context={"max_bytes": MAX_EVIDENCE_BYTES, "size": len(encoded)},
        )
    copied = json.loads(encoded.decode("utf-8"))
    if not isinstance(copied, dict):
        raise ConceptToReleaseError(
            "evidence payload must be a JSON object",
            context={"reason": "payload_not_object"},
        )
    forbidden = _claim_keys(copied)
    if forbidden:
        raise ConceptToReleaseError(
            "self-certified model claims are refused",
            context={"reason": "self_certified_claim", "keys": list(forbidden)},
        )
    return copied


def evidence_digest(
    *,
    source: str,
    dimension: str,
    observed_at: int,
    payload: Mapping[str, Any],
) -> str:
    return canonical_digest(
        {
            "dimension": dimension,
            "observed_at": observed_at,
            "payload": dict(payload),
            "source": source,
        }
    )


def retain_evidence(
    *,
    source: str,
    dimension: str,
    observed_at: int,
    payload: Mapping[str, Any],
    digest: str | None = None,
) -> EvidenceItem:
    """Validate and freeze one raw evidence item. Tampered digests fail closed."""

    if source not in ALLOWED_SOURCES:
        raise ConceptToReleaseError(
            "evidence source is not a stabilized contract",
            context={"source": source, "allowed": list(ALLOWED_SOURCES)},
        )
    if dimension not in METRIC_SPECS:
        raise ConceptToReleaseError(
            "unknown score dimension",
            context={"dimension": dimension},
        )
    spec = METRIC_SPECS[dimension]
    if source not in spec.sources:
        raise ConceptToReleaseError(
            "evidence source is incompatible with dimension",
            context={"dimension": dimension, "source": source, "allowed": list(spec.sources)},
        )
    observed = _require_int("observed_at", observed_at, minimum=0)
    frozen = _freeze_payload(payload)
    computed = evidence_digest(
        source=source,
        dimension=dimension,
        observed_at=observed,
        payload=frozen,
    )
    if digest is not None:
        supplied = _validate_digest(digest)
        if not _digests_match(computed, supplied):
            raise ConceptToReleaseError(
                "tampered evidence reference",
                context={"dimension": dimension, "reason": "digest_mismatch"},
            )
    return EvidenceItem(
        source=source,
        dimension=dimension,
        observed_at=observed,
        payload=MappingProxyType(frozen),
        digest=computed,
    )


def _optional_finite_number(payload: Mapping[str, Any], key: str) -> float | None:
    if key not in payload:
        return None
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConceptToReleaseError(
            f"{key} must be a finite number",
            context={"field": key},
        )
    number = float(value)
    if not math.isfinite(number):
        raise ConceptToReleaseError(
            f"{key} must be a finite number",
            context={"field": key},
        )
    return number


def _optional_bool(payload: Mapping[str, Any], key: str) -> bool | None:
    if key not in payload:
        return None
    value = payload[key]
    if not isinstance(value, bool):
        raise ConceptToReleaseError(
            f"{key} must be a boolean",
            context={"field": key},
        )
    return value


def _optional_int(payload: Mapping[str, Any], key: str, *, minimum: int = 0) -> int | None:
    if key not in payload:
        return None
    return _require_int(key, payload[key], minimum=minimum)


def _clamp_unit(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return round(value, 4)


def _budget_score(elapsed: float, budget: float) -> float:
    if budget <= 0.0:
        raise ConceptToReleaseError(
            "budget_ms must be positive",
            context={"field": "budget_ms"},
        )
    if elapsed < 0.0:
        raise ConceptToReleaseError(
            "elapsed value cannot be negative",
            context={"field": "elapsed"},
        )
    return _clamp_unit(1.0 - (elapsed / budget))


def _hex_digest64(value: Any) -> str | None:
    if not isinstance(value, str):
        raise ConceptToReleaseError(
            "digest must be a string",
            context={"reason": "digest_not_string"},
        )
    if not _DIGEST_RE.fullmatch(value):
        return None
    return value


def _score_correctness(payload: Mapping[str, Any]) -> float | None:
    accepted = _optional_bool(payload, "accepted")
    score = _optional_finite_number(payload, "score")
    if accepted is None or score is None:
        return None
    if not 0.0 <= score <= 1.0:
        raise ConceptToReleaseError(
            "correctness score must be a unit interval",
            context={"field": "score"},
        )
    if not accepted:
        return 0.0
    return round(score, 4)


def _score_iteration_latency(payload: Mapping[str, Any]) -> float | None:
    latency = _optional_finite_number(payload, "latency_ms")
    budget = _optional_finite_number(payload, "budget_ms")
    if latency is None or budget is None:
        return None
    return _budget_score(latency, budget)


def _score_editability(payload: Mapping[str, Any]) -> float | None:
    attempted = _optional_int(payload, "attempted_edits", minimum=0)
    successful = _optional_int(payload, "successful_edits", minimum=0)
    if attempted is None or successful is None:
        return None
    if successful > attempted:
        raise ConceptToReleaseError(
            "successful_edits cannot exceed attempted_edits",
            context={"attempted_edits": attempted, "successful_edits": successful},
        )
    if attempted == 0:
        return None
    return round(successful / attempted, 4)


def _score_determinism_replay(payload: Mapping[str, Any]) -> float | None:
    if "replay_digest" not in payload or "live_digest" not in payload:
        return None
    replay = _hex_digest64(payload["replay_digest"])
    live = _hex_digest64(payload["live_digest"])
    if replay is None or live is None:
        return 0.0
    return 1.0 if _digests_match(replay, live) else 0.0


def _score_security(payload: Mapping[str, Any]) -> float | None:
    blocking = _optional_int(payload, "blocking_findings", minimum=0)
    if blocking is None:
        return None
    passed = _optional_bool(payload, "passed")
    expected_pass = blocking == 0
    if passed is not None and passed is not expected_pass:
        raise ConceptToReleaseError(
            "security evidence is contradictory",
            context={"blocking_findings": blocking, "passed": passed},
        )
    return 1.0 if expected_pass else 0.0


def _artifact_records_valid(artifacts: Any) -> bool:
    if not isinstance(artifacts, list) or not artifacts:
        return False
    for record in artifacts:
        if not isinstance(record, Mapping):
            return False
        name = record.get("name")
        digest = record.get("sha256")
        size = record.get("size")
        if not isinstance(name, str) or not name.strip():
            return False
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            return False
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            return False
    return True


def _source_commit_from_payload(payload: Mapping[str, Any]) -> str | None:
    source = payload.get("source")
    if source is None:
        return None
    if not isinstance(source, Mapping):
        raise ConceptToReleaseError(
            "release source must be a mapping",
            context={"field": "source"},
        )
    commit = source.get("commit")
    if commit is None:
        return None
    if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
        return ""
    return commit.lower()


def _score_provenance(payload: Mapping[str, Any]) -> float | None:
    has_any = any(key in payload for key in ("schema_version", "source", "artifacts"))
    if not has_any:
        return None
    schema_ok = payload.get("schema_version") == _RELEASE_SCHEMA_VERSION
    commit = _source_commit_from_payload(payload)
    commit_ok = bool(commit)
    artifacts_ok = _artifact_records_valid(payload.get("artifacts"))
    return round((int(schema_ok) + int(commit_ok) + int(artifacts_ok)) / 3.0, 4)


def _score_performance(payload: Mapping[str, Any]) -> float | None:
    elapsed = _optional_finite_number(payload, "elapsed_ms")
    budget = _optional_finite_number(payload, "budget_ms")
    if elapsed is None or budget is None:
        return None
    return _budget_score(elapsed, budget)


def _score_creator_control(payload: Mapping[str, Any]) -> float | None:
    approval = _optional_bool(payload, "explicit_approval")
    overrides = _optional_int(payload, "unapproved_overrides", minimum=0)
    if approval is None or overrides is None:
        return None
    if overrides > 0 or not approval:
        return 0.0
    return 1.0


def _score_release_completeness(payload: Mapping[str, Any]) -> float | None:
    has_any = any(key in payload for key in ("source", "artifacts", "sbom_refs"))
    if not has_any:
        return None
    commit = _source_commit_from_payload(payload)
    commit_ok = bool(commit)
    artifacts_ok = _artifact_records_valid(payload.get("artifacts"))
    sbom = payload.get("sbom_refs")
    sbom_ok = isinstance(sbom, list) and bool(sbom) and _artifact_records_valid(sbom)
    return round((int(commit_ok) + int(artifacts_ok) + int(sbom_ok)) / 3.0, 4)


_SCORERS = {
    "correctness": _score_correctness,
    "iteration_latency": _score_iteration_latency,
    "editability": _score_editability,
    "determinism_replay": _score_determinism_replay,
    "security": _score_security,
    "provenance": _score_provenance,
    "performance": _score_performance,
    "creator_control": _score_creator_control,
    "release_completeness": _score_release_completeness,
}


def build_summary(
    *,
    schema_version: int,
    source_commit: str,
    raw_evidence_refs: Mapping[str, str],
    dimensions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a summary bound to raw evidence refs. Missing refs fail closed."""

    if not isinstance(raw_evidence_refs, Mapping):
        raise ConceptToReleaseError(
            "summary cannot be produced without raw evidence refs",
            context={"reason": "missing_raw_refs"},
        )
    refs = {str(key): _validate_digest(value, field=f"raw_evidence_refs.{key}") for key, value in raw_evidence_refs.items()}
    if set(refs) - set(SCORE_DIMENSIONS):
        raise ConceptToReleaseError(
            "raw evidence refs contain unknown dimensions",
            context={"unknown": sorted(set(refs) - set(SCORE_DIMENSIONS))},
        )
    normalized: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    scored: list[str] = []
    for dimension in SCORE_DIMENSIONS:
        row = dimensions.get(dimension)
        if not isinstance(row, Mapping):
            raise ConceptToReleaseError(
                "summary is missing a required dimension",
                context={"dimension": dimension},
            )
        status = row.get("status")
        value = row.get("value")
        if status == "missing":
            if value is not None:
                raise ConceptToReleaseError(
                    "missing dimensions cannot carry a numeric value",
                    context={"dimension": dimension},
                )
            missing.append(dimension)
        elif status == "scored":
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                raise ConceptToReleaseError(
                    "scored dimensions require a finite numeric value",
                    context={"dimension": dimension},
                )
            if dimension not in refs:
                raise ConceptToReleaseError(
                    "summary cannot be produced without raw evidence refs",
                    context={"dimension": dimension, "reason": "scored_without_ref"},
                )
            scored.append(dimension)
            value = round(float(value), 4)
        else:
            raise ConceptToReleaseError(
                "dimension status must be scored or missing",
                context={"dimension": dimension, "status": status},
            )
        normalized[dimension] = {
            "status": status,
            "value": value,
            "metric_version": METRIC_SPECS[dimension].version,
            "source": row.get("source"),
            "evidence_digest": refs.get(dimension),
        }
    material = {
        "benchmark_id": BENCHMARK_ID,
        "dimensions": normalized,
        "metric_catalog_version": METRIC_CATALOG_VERSION,
        "raw_evidence_refs": {key: refs[key] for key in SCORE_DIMENSIONS if key in refs},
        "schema_version": schema_version,
        "source_commit": source_commit,
    }
    return {
        "complete": not missing,
        "digest": canonical_digest(material),
        "dimensions": normalized,
        "kind": KIND_SUMMARY,
        "metric_catalog_version": METRIC_CATALOG_VERSION,
        "missing": missing,
        "scored": scored,
    }


def _index_items(items: Iterable[EvidenceItem]) -> dict[str, EvidenceItem]:
    indexed: dict[str, EvidenceItem] = {}
    seen_dimensions: set[str] = set()
    for count, item in enumerate(items, start=1):
        if count > MAX_EVIDENCE_ITEMS:
            raise ConceptToReleaseError(
                "evidence bundle exceeds item bound",
                context={"max_items": MAX_EVIDENCE_ITEMS},
            )
        if item.dimension in seen_dimensions:
            raise ConceptToReleaseError(
                "duplicate evidence for dimension",
                context={"dimension": item.dimension},
            )
        seen_dimensions.add(item.dimension)
        computed = evidence_digest(
            source=item.source,
            dimension=item.dimension,
            observed_at=item.observed_at,
            payload=item.payload,
        )
        if not _digests_match(computed, item.digest):
            raise ConceptToReleaseError(
                "tampered evidence reference",
                context={"dimension": item.dimension, "reason": "digest_mismatch"},
            )
        indexed[item.dimension] = item
    return indexed


def _assert_fresh(item: EvidenceItem, *, evaluated_at: int, freshness_seconds: int) -> None:
    if item.observed_at > evaluated_at:
        raise ConceptToReleaseError(
            "evidence timestamp is in the future relative to evaluation",
            context={"dimension": item.dimension, "reason": "future_evidence"},
        )
    age = evaluated_at - item.observed_at
    if age > freshness_seconds:
        raise ConceptToReleaseError(
            "stale evidence",
            context={
                "dimension": item.dimension,
                "age_seconds": age,
                "freshness_seconds": freshness_seconds,
            },
        )


def score_concept_to_release(bundle: EvidenceBundle) -> dict[str, Any]:
    """Score a concept-to-release evidence bundle fail-closed and deterministically."""

    if not isinstance(bundle, EvidenceBundle):
        raise ConceptToReleaseError(
            "bundle must be an EvidenceBundle",
            context={"reason": "invalid_bundle_type"},
        )
    if bundle.schema_version != BENCHMARK_SCHEMA_VERSION:
        raise ConceptToReleaseError(
            "incompatible benchmark version",
            context={
                "expected": BENCHMARK_SCHEMA_VERSION,
                "received": bundle.schema_version,
            },
        )
    source_commit = _validate_commit(bundle.source_commit)
    evaluated_at = _require_int("evaluated_at", bundle.evaluated_at, minimum=0)
    freshness = _require_int("freshness_seconds", bundle.freshness_seconds, minimum=0)
    if freshness > MAX_FRESHNESS_SECONDS:
        raise ConceptToReleaseError(
            "freshness window exceeds bound",
            context={"max_seconds": MAX_FRESHNESS_SECONDS},
        )
    if bundle.metric_versions is not None:
        if not isinstance(bundle.metric_versions, Mapping):
            raise ConceptToReleaseError(
                "metric_versions must be a mapping",
                context={"reason": "invalid_metric_versions"},
            )
        for dimension in SCORE_DIMENSIONS:
            expected = METRIC_SPECS[dimension].version
            if dimension not in bundle.metric_versions:
                raise ConceptToReleaseError(
                    "incompatible benchmark version",
                    context={"dimension": dimension, "reason": "missing_metric_version"},
                )
            received = bundle.metric_versions[dimension]
            if received != expected:
                raise ConceptToReleaseError(
                    "incompatible benchmark version",
                    context={
                        "dimension": dimension,
                        "expected": expected,
                        "received": received,
                    },
                )
        extra = set(bundle.metric_versions) - set(SCORE_DIMENSIONS)
        if extra:
            raise ConceptToReleaseError(
                "incompatible benchmark version",
                context={"unknown_metrics": sorted(extra)},
            )

    indexed = _index_items(bundle.items)
    raw_store: dict[str, dict[str, Any]] = {}
    refs: dict[str, str] = {}
    dimensions: dict[str, dict[str, Any]] = {}

    for dimension in SCORE_DIMENSIONS:
        item = indexed.get(dimension)
        if item is None:
            dimensions[dimension] = {"status": "missing", "value": None, "source": None}
            continue
        _assert_fresh(item, evaluated_at=evaluated_at, freshness_seconds=freshness)
        if item.source == "release" and dimension in {"provenance", "release_completeness"}:
            evidence_commit = _source_commit_from_payload(item.payload)
            if evidence_commit and evidence_commit != source_commit:
                raise ConceptToReleaseError(
                    "release evidence source commit does not match benchmark run",
                    context={
                        "dimension": dimension,
                        "benchmark_commit": source_commit,
                        "evidence_commit": evidence_commit,
                    },
                )
        value = _SCORERS[dimension](item.payload)
        raw_store[item.digest] = {
            "digest": item.digest,
            "dimension": item.dimension,
            "kind": KIND_RAW,
            "observed_at": item.observed_at,
            "payload": dict(item.payload),
            "source": item.source,
        }
        refs[dimension] = item.digest
        if value is None:
            dimensions[dimension] = {
                "status": "missing",
                "value": None,
                "source": item.source,
            }
        else:
            dimensions[dimension] = {
                "status": "scored",
                "value": value,
                "source": item.source,
            }

    summary = build_summary(
        schema_version=bundle.schema_version,
        source_commit=source_commit,
        raw_evidence_refs=refs,
        dimensions=dimensions,
    )
    run = {
        "benchmark_id": BENCHMARK_ID,
        "evaluated_at": evaluated_at,
        "freshness_seconds": freshness,
        "kind": KIND_RUN,
        "raw_evidence_refs": {key: refs[key] for key in SCORE_DIMENSIONS if key in refs},
        "schema_version": bundle.schema_version,
        "source_commit": source_commit,
        "summary": summary,
    }
    return {
        "raw_evidence": MappingProxyType({digest: MappingProxyType(row) for digest, row in raw_store.items()}),
        "run": MappingProxyType(run),
    }


def make_reproducible_fixture(
    *,
    source_commit: str = "a" * 40,
    observed_at: int = 1_000_000,
    evaluated_at: int = 1_000_100,
    omit: Iterable[str] = (),
    overlay: Mapping[str, Mapping[str, Any]] | None = None,
) -> EvidenceBundle:
    """Return a bounded, deterministic evidence bundle for tests and local scoring."""

    omitted = set(omit)
    unknown = omitted - set(SCORE_DIMENSIONS)
    if unknown:
        raise ConceptToReleaseError(
            "unknown omitted dimension",
            context={"unknown": sorted(unknown)},
        )
    overlay = overlay or {}
    digest_a = "b" * 64
    digest_b = "c" * 64
    artifact = {"name": "dist/skeleton-16.0.0.tar.gz", "sha256": digest_a, "size": 128}
    sbom = {"name": "dist/sbom.cdx.json", "sha256": digest_b, "size": 64}
    payloads: dict[str, tuple[str, dict[str, Any]]] = {
        "correctness": (
            "quality",
            {"accepted": True, "score": 0.91, "reason": "accepted", "surface": "forge"},
        ),
        "iteration_latency": ("creator", {"latency_ms": 250, "budget_ms": 1000}),
        "editability": ("creator", {"attempted_edits": 4, "successful_edits": 3}),
        "determinism_replay": (
            "world",
            {"replay_digest": digest_a, "live_digest": digest_a},
        ),
        "security": ("quality", {"blocking_findings": 0, "passed": True}),
        "provenance": (
            "release",
            {
                "artifacts": [artifact],
                "schema_version": _RELEASE_SCHEMA_VERSION,
                "source": {"commit": source_commit.lower(), "source_date_epoch": 1_700_000_000},
            },
        ),
        "performance": ("game", {"elapsed_ms": 40, "budget_ms": 200}),
        "creator_control": ("creator", {"explicit_approval": True, "unapproved_overrides": 0}),
        "release_completeness": (
            "release",
            {
                "artifacts": [artifact],
                "sbom_refs": [sbom],
                "source": {"commit": source_commit.lower()},
            },
        ),
    }
    items: list[EvidenceItem] = []
    for dimension in SCORE_DIMENSIONS:
        if dimension in omitted:
            continue
        source, payload = payloads[dimension]
        if dimension in overlay:
            payload = {**payload, **dict(overlay[dimension])}
        items.append(
            retain_evidence(
                source=source,
                dimension=dimension,
                observed_at=observed_at,
                payload=payload,
            )
        )
    return EvidenceBundle(
        schema_version=BENCHMARK_SCHEMA_VERSION,
        source_commit=source_commit,
        evaluated_at=evaluated_at,
        items=tuple(items),
        freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
        metric_versions={dimension: METRIC_SPECS[dimension].version for dimension in SCORE_DIMENSIONS},
    )
