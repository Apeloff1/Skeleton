"""Fail-closed AI golden-journey evidence collection for release readiness.

This module does not run tests. It consumes explicit test-result artifacts,
verifies that the canonical Stage-7 AI journeys actually passed, binds every
record to the exact report bytes, and emits the existing release TestEvidence
contract. Missing, skipped, xfailed, failed, malformed, or merely planned
journeys are never promoted into release evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping
import xml.etree.ElementTree as ET

from skeleton.release.evidence import EvidenceSchemaError, TestEvidence


_EVIDENCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_LANES = frozenset({"test", "eval"})
_PASS = frozenset({"passed", "pass", "ok", "success"})
_FAIL = frozenset({"failed", "fail", "error", "errors"})
_SKIP = frozenset({"skipped", "skip", "xfailed", "xfail", "xpassed", "xpass"})


@dataclass(frozen=True, slots=True)
class AIJourneyRequirement:
    evidence_id: str
    nodeid: str
    lane: str = "test"

    def __post_init__(self) -> None:
        evidence_id = str(self.evidence_id).strip()
        nodeid = str(self.nodeid).strip()
        lane = str(self.lane).strip().lower()
        if not evidence_id or _EVIDENCE_ID_RE.fullmatch(evidence_id) is None:
            raise EvidenceSchemaError(
                "AI journey evidence_id must be a canonical token"
            )
        if not nodeid or "::" not in nodeid:
            raise EvidenceSchemaError(
                "AI journey nodeid must identify one concrete test"
            )
        if lane not in _LANES:
            raise EvidenceSchemaError("AI journey lane must be test or eval")
        object.__setattr__(self, "evidence_id", evidence_id)
        object.__setattr__(self, "nodeid", nodeid)
        object.__setattr__(self, "lane", lane)


@dataclass(frozen=True, slots=True)
class AIJourneyEvidenceBundle:
    test_evidence: tuple[TestEvidence, ...]
    eval_evidence: tuple[TestEvidence, ...]
    observed_cases: tuple[str, ...]

    def release_kwargs(self) -> dict[str, tuple[TestEvidence, ...]]:
        return {
            "test_evidence": self.test_evidence,
            "eval_evidence": self.eval_evidence,
        }


def requirements_from_manifest(
    payload: Mapping[str, Any],
) -> tuple[AIJourneyRequirement, ...]:
    """Convert the machine Stage-7 journey contract into typed requirements."""

    if not isinstance(payload, Mapping):
        raise EvidenceSchemaError(
            "AI journey manifest must be an object"
        )
    if payload.get("schema_id") != "skeleton.ai.release-journeys":
        raise EvidenceSchemaError(
            "AI journey manifest schema_id is invalid"
        )
    if payload.get("schema_version") != 1:
        raise EvidenceSchemaError(
            "AI journey manifest schema_version is unsupported"
        )
    raw = payload.get("required")
    if not isinstance(raw, list) or not raw:
        raise EvidenceSchemaError(
            "AI journey manifest required must be a non-empty list"
        )

    requirements: list[AIJourneyRequirement] = []
    seen_ids: set[str] = set()
    seen_nodes: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise EvidenceSchemaError(
                f"AI journey manifest required[{index}] must be an object"
            )
        category = str(item.get("category") or "").strip().lower()
        lane = {
            "golden": "test",
            "fault": "eval",
        }.get(category)
        if lane is None:
            raise EvidenceSchemaError(
                "AI journey category must be golden or fault"
            )
        requirement = AIJourneyRequirement(
            evidence_id=str(item.get("evidence_id") or ""),
            nodeid=str(item.get("nodeid") or ""),
            lane=lane,
        )
        if requirement.evidence_id in seen_ids:
            raise EvidenceSchemaError(
                "AI journey evidence ids must be unique"
            )
        if requirement.nodeid in seen_nodes:
            raise EvidenceSchemaError(
                "AI journey nodeids must be unique"
            )
        seen_ids.add(requirement.evidence_id)
        seen_nodes.add(requirement.nodeid)
        requirements.append(requirement)
    return tuple(requirements)


# Fallback typed matrix retained for library callers that do not have the
# repository machine manifest available. The release CLI loads the machine
# manifest and passes it explicitly, preventing workflow drift.
MANDATORY_AI_JOURNEYS: tuple[AIJourneyRequirement, ...] = (
    AIJourneyRequirement(
        "ai-journey.simple-chat",
        "skeleton/testing/test_execution_runtime.py::test_direct_provider_completion_is_verified_and_atomically_finalized",
        lane="test",
    ),
    AIJourneyRequirement(
        "ai-journey.retrieval-tool-approval",
        "backend/tests/test_ai_golden_journey.py::test_deterministic_retrieval_tool_approval_golden_journey",
        lane="test",
    ),
    AIJourneyRequirement(
        "ai-journey.conversation-retry",
        "backend/tests/test_ai_chat_conversation_authority.py::test_chat_retry_reuses_same_engine_operation_and_execution_identity",
        lane="test",
    ),
    AIJourneyRequirement(
        "ai-journey.artifact-result",
        "backend/tests/test_ai_artifact_result_journey.py::test_deterministic_artifact_is_bound_to_durable_execution_result",
        lane="test",
    ),
    AIJourneyRequirement(
        "ai-journey.stream-resync",
        "backend/tests/test_operation_stream_route.py::test_authoritative_resync_returns_compaction_floor_and_retained_events",
        lane="test",
    ),
    AIJourneyRequirement(
        "ai-fault.cross-tenant-retrieval",
        "backend/tests/test_ai_golden_journey.py::test_retrieval_tenant_ambiguity_fails_before_compilation",
        lane="eval",
    ),
    AIJourneyRequirement(
        "ai-fault.provider-outage",
        "skeleton/testing/test_engine_execution_coordinator.py::test_coordinator_provider_unavailable_becomes_durable_failure",
        lane="eval",
    ),
    AIJourneyRequirement(
        "ai-fault.provider-checkpoint-crash",
        "skeleton/testing/test_execution_runtime.py::test_crash_after_provider_checkpoint_resumes_without_second_provider_call",
        lane="eval",
    ),
    AIJourneyRequirement(
        "ai-fault.tool-effect-crash",
        "skeleton/testing/test_execution_runtime.py::test_crash_after_tool_effect_resumes_without_duplicate_tool_effect",
        lane="eval",
    ),
    AIJourneyRequirement(
        "ai-fault.tool-outage",
        "skeleton/testing/test_execution_runtime.py::test_tool_handler_outage_becomes_durable_execution_failure",
        lane="eval",
    ),
    AIJourneyRequirement(
        "ai-fault.approval-expiry",
        "skeleton/testing/test_engine_execution_service.py::test_expired_persisted_approval_is_not_replayed_into_resume",
        lane="eval",
    ),
    AIJourneyRequirement(
        "ai-fault.slow-client-backpressure",
        "backend/tests/test_operation_stream_transport.py::test_slow_consumer_backpressure_preserves_pending_outbox_until_ack",
        lane="eval",
    ),
    AIJourneyRequirement(
        "ai-fault.complete-wins-cancel-race",
        "backend/tests/test_operation_stream_transport.py::test_completion_wins_cancel_race_and_terminal_stream_remains_final",
        lane="eval",
    ),
    AIJourneyRequirement(
        "ai-fault.cancel-wins-complete-race",
        "backend/tests/test_operation_stream_transport.py::test_cancel_wins_completion_race_and_completion_cannot_reopen_operation",
        lane="eval",
    ),
    AIJourneyRequirement(
        "ai-fault.durable-approval-restart",
        "skeleton/testing/test_engine_execution_coordinator.py::test_coordinator_durable_approval_resumes_effect_once_after_restart",
        lane="eval",
    ),
)


def collect_ai_journey_evidence(
    *,
    report_name: str,
    report_bytes: bytes,
    report_format: str,
    requirements: Iterable[AIJourneyRequirement] = MANDATORY_AI_JOURNEYS,
) -> AIJourneyEvidenceBundle:
    """Validate a concrete result artifact and emit canonical release evidence."""

    name = _canonical_report_name(report_name)
    if not isinstance(report_bytes, (bytes, bytearray)) or not report_bytes:
        raise EvidenceSchemaError("AI journey report bytes must be non-empty")
    raw = bytes(report_bytes)
    format_key = str(report_format).strip().lower()
    if format_key in {"pytest-json", "pytest_json", "json"}:
        outcomes = _parse_pytest_json(raw)
    elif format_key in {"junit", "junit-xml", "xml"}:
        outcomes = _parse_junit(raw)
    else:
        raise EvidenceSchemaError(
            "AI journey report_format must be pytest-json or junit"
        )

    required = tuple(requirements)
    if not required:
        raise EvidenceSchemaError("AI journey requirements must not be empty")
    evidence_ids: set[str] = set()
    nodeids: set[str] = set()
    for requirement in required:
        if not isinstance(requirement, AIJourneyRequirement):
            raise EvidenceSchemaError(
                "AI journey requirements must be AIJourneyRequirement values"
            )
        if requirement.evidence_id in evidence_ids:
            raise EvidenceSchemaError(
                "AI journey evidence ids must be unique"
            )
        if requirement.nodeid in nodeids:
            raise EvidenceSchemaError(
                "AI journey nodeids must be unique"
            )
        evidence_ids.add(requirement.evidence_id)
        nodeids.add(requirement.nodeid)

    digest = hashlib.sha256(raw).hexdigest()
    tests: list[TestEvidence] = []
    evals: list[TestEvidence] = []
    missing: list[str] = []
    nonpassing: list[str] = []

    for requirement in required:
        outcome = _resolve_required_outcome(
            outcomes,
            requirement.nodeid,
        )
        if outcome is None:
            missing.append(requirement.nodeid)
            continue
        if outcome != "passed":
            nonpassing.append(
                f"{requirement.nodeid}={outcome}"
            )
            continue
        evidence = TestEvidence(
            evidence_id=requirement.evidence_id,
            name=name,
            sha256=digest,
            result="pass",
        )
        (tests if requirement.lane == "test" else evals).append(evidence)

    if missing or nonpassing:
        parts: list[str] = []
        if missing:
            parts.append(
                "missing required AI journeys: " + ", ".join(sorted(missing))
            )
        if nonpassing:
            parts.append(
                "non-passing required AI journeys: "
                + ", ".join(sorted(nonpassing))
            )
        raise EvidenceSchemaError("; ".join(parts))

    if not tests:
        raise EvidenceSchemaError(
            "AI journey matrix must produce release test evidence"
        )
    if not evals:
        raise EvidenceSchemaError(
            "AI journey matrix must produce release eval evidence"
        )

    return AIJourneyEvidenceBundle(
        test_evidence=tuple(sorted(tests, key=lambda item: item.evidence_id)),
        eval_evidence=tuple(sorted(evals, key=lambda item: item.evidence_id)),
        observed_cases=tuple(sorted(outcomes)),
    )


def _resolve_required_outcome(
    outcomes: Mapping[str, str],
    nodeid: str,
) -> str | None:
    direct = outcomes.get(nodeid)
    if direct is not None:
        return direct

    suffix = "/" + nodeid
    matches = {
        outcome
        for candidate, outcome in outcomes.items()
        if candidate.endswith(suffix)
    }
    if not matches:
        return None
    if len(matches) != 1:
        raise EvidenceSchemaError(
            f"AI journey report has ambiguous prefixed results for {nodeid}"
        )
    return next(iter(matches))


def _canonical_report_name(value: object) -> str:
    if not isinstance(value, str):
        raise EvidenceSchemaError("AI journey report_name must be text")
    name = value.strip()
    if not name or name != value:
        raise EvidenceSchemaError(
            "AI journey report_name must be normalized"
        )
    if (
        name.startswith("/")
        or "\\" in name
        or "//" in name
        or "/./" in name
        or "/../" in name
        or name.startswith("../")
        or name.endswith("/..")
    ):
        raise EvidenceSchemaError(
            "AI journey report_name must be a canonical relative path"
        )
    return name


def _normalize_outcome(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    if normalized in _PASS:
        return "passed"
    if normalized in _FAIL:
        return "failed"
    if normalized in _SKIP:
        return "skipped"
    return normalized or "unknown"


def _record_case(
    outcomes: dict[str, str],
    nodeid: str,
    outcome: str,
) -> None:
    key = str(nodeid).strip()
    if not key:
        raise EvidenceSchemaError(
            "test result contains an empty test identity"
        )
    normalized = _normalize_outcome(outcome)
    existing = outcomes.get(key)
    if existing is not None and existing != normalized:
        raise EvidenceSchemaError(
            f"test result contains conflicting outcomes for {key}"
        )
    outcomes[key] = normalized


def _parse_pytest_json(raw: bytes) -> dict[str, str]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceSchemaError(
            "pytest JSON report is malformed"
        ) from exc
    if not isinstance(payload, Mapping):
        raise EvidenceSchemaError(
            "pytest JSON report root must be an object"
        )
    tests = payload.get("tests")
    if not isinstance(tests, list) or not tests:
        raise EvidenceSchemaError(
            "pytest JSON report contains no test cases"
        )
    outcomes: dict[str, str] = {}
    for item in tests:
        if not isinstance(item, Mapping):
            raise EvidenceSchemaError(
                "pytest JSON report has malformed test case"
            )
        nodeid = item.get("nodeid")
        outcome = item.get("outcome")
        if not isinstance(nodeid, str):
            raise EvidenceSchemaError(
                "pytest JSON test case is missing nodeid"
            )
        _record_case(outcomes, nodeid, str(outcome or "unknown"))
    return outcomes


def _parse_junit(raw: bytes) -> dict[str, str]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise EvidenceSchemaError("JUnit report is malformed") from exc

    cases = tuple(root.iter("testcase"))
    if not cases:
        raise EvidenceSchemaError("JUnit report contains no test cases")

    outcomes: dict[str, str] = {}
    for case in cases:
        name = str(case.attrib.get("name") or "").strip()
        file_name = str(case.attrib.get("file") or "").strip()
        classname = str(case.attrib.get("classname") or "").strip()
        if not name:
            raise EvidenceSchemaError(
                "JUnit test case is missing name"
            )
        if case.find("failure") is not None or case.find("error") is not None:
            outcome = "failed"
        elif case.find("skipped") is not None:
            outcome = "skipped"
        else:
            outcome = "passed"

        candidates: set[str] = {name}
        if file_name:
            candidates.add(f"{file_name}::{name}")
        if classname:
            candidates.add(f"{classname}::{name}")
            module_path = classname.replace(".", "/")
            if not module_path.endswith(".py"):
                module_path += ".py"
            candidates.add(f"{module_path}::{name}")
        for candidate in candidates:
            _record_case(outcomes, candidate, outcome)
    return outcomes


__all__ = [
    "AIJourneyEvidenceBundle",
    "AIJourneyRequirement",
    "MANDATORY_AI_JOURNEYS",
    "collect_ai_journey_evidence",
    "requirements_from_manifest",
]
