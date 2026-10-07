"""Transactional live-preview coordination for #807 B015.

This module stages B011 design edits immutably, then coordinates an explicit
preview backend through begin, apply, compile, runtime, commit, or rollback.
The creator core never imports an engine and provides no default backend.

A failed or raised backend phase returns the original DesignPlan only after a
successful rollback receipt. If rollback cannot be proven, execution fails
closed with PreviewRollbackError rather than pretending the preview is clean.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Final, NoReturn, Protocol

from skeleton.forge.creator.intent_compiler import (
    DESIGN_PLAN_SCHEMA,
    INTENT_VERSION,
    DesignEdit,
    DesignPlan,
    apply_edit,
)
from skeleton.kernel.errors import SkeletonError


PREVIEW_SCHEMA: Final = "creator.preview_transaction.v1"
PREVIEW_VERSION: Final = 1

PREVIEW_PHASES: Final = (
    "begin",
    "apply",
    "compile",
    "runtime",
    "commit",
    "rollback",
)
EXECUTION_PHASES: Final = PREVIEW_PHASES[:-1]

MAX_TRANSACTION_ID_CHARS: Final = 128
MAX_EDITS: Final = 32
MAX_DIAGNOSTICS: Final = 128
MAX_DIAGNOSTIC_CHARS: Final = 2_048
MAX_EVIDENCE_FIELDS: Final = 256
MAX_EVIDENCE_DEPTH: Final = 12
MAX_EVIDENCE_NODES: Final = 4_096
MAX_SERIALIZED_BYTES: Final = 512 * 1_024

_TX_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$")
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")


class PreviewTransactionError(SkeletonError):
    """Preview transaction data or backend behavior is invalid."""

    code = "CRE.PREVIEW_TRANSACTION"
    http_status = 409


class PreviewRollbackError(PreviewTransactionError):
    """The preview backend could not prove rollback to its prior state."""

    code = "CRE.PREVIEW_ROLLBACK"
    http_status = 500


@dataclass(frozen=True, slots=True)
class PreviewStepResult:
    phase: str
    ok: bool
    evidence_digest: str
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "ok": self.ok,
            "evidence_digest": self.evidence_digest,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True, slots=True)
class PreviewTransaction:
    transaction_id: str
    base_graph_digest: str
    base_state_digest: str
    base_revision: int
    staged_graph_digest: str
    staged_state_digest: str
    staged_revision: int
    edit_ids: tuple[str, ...]
    edit_digests: tuple[str, ...]
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": PREVIEW_SCHEMA,
            "schema_version": PREVIEW_VERSION,
            "transaction_id": self.transaction_id,
            "base_graph_digest": self.base_graph_digest,
            "base_state_digest": self.base_state_digest,
            "base_revision": self.base_revision,
            "staged_graph_digest": self.staged_graph_digest,
            "staged_state_digest": self.staged_state_digest,
            "staged_revision": self.staged_revision,
            "edit_ids": list(self.edit_ids),
            "edit_digests": list(self.edit_digests),
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class PreparedPreview:
    transaction: PreviewTransaction
    base_plan: DesignPlan
    staged_plan: DesignPlan
    edits: tuple[DesignEdit, ...]


@dataclass(frozen=True, slots=True)
class PreviewOutcome:
    transaction_digest: str
    status: str
    resulting_state_digest: str
    failure_phase: str | None
    failure_reason: str | None
    steps: tuple[PreviewStepResult, ...]
    rollback: PreviewStepResult | None
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": PREVIEW_SCHEMA,
            "schema_version": PREVIEW_VERSION,
            "transaction_digest": self.transaction_digest,
            "status": self.status,
            "resulting_state_digest": self.resulting_state_digest,
            "failure_phase": self.failure_phase,
            "failure_reason": self.failure_reason,
            "steps": [step.to_dict() for step in self.steps],
            "rollback": None if self.rollback is None else self.rollback.to_dict(),
            "digest": self.digest,
        }


class PreviewBackend(Protocol):
    """Explicit preview adapter required by execute_preview_transaction."""

    def begin(self, transaction: PreviewTransaction) -> PreviewStepResult:
        ...

    def apply(
        self,
        transaction: PreviewTransaction,
        staged_plan: DesignPlan,
    ) -> PreviewStepResult:
        ...

    def compile(self, transaction: PreviewTransaction) -> PreviewStepResult:
        ...

    def runtime(self, transaction: PreviewTransaction) -> PreviewStepResult:
        ...

    def commit(self, transaction: PreviewTransaction) -> PreviewStepResult:
        ...

    def rollback(
        self,
        transaction: PreviewTransaction,
        *,
        failed_phase: str,
        reason: str,
    ) -> PreviewStepResult:
        ...


def _fail(message: str, *, reason: str, **context: object) -> NoReturn:
    raise PreviewTransactionError(message, context={"reason": reason, **context})


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("preview data is not canonical JSON", reason="json_type")
        raise AssertionError("unreachable") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(
            f"{field} must be a lowercase sha256 digest",
            reason="malformed",
            field=field,
        )
    return value


def _strict_int(
    value: object,
    *,
    field: str,
    minimum: int,
    maximum: int,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        _fail(
            f"{field} is outside the accepted integer range",
            reason="malformed",
            field=field,
        )
    return value


def _transaction_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > MAX_TRANSACTION_ID_CHARS
        or _TX_RE.fullmatch(value) is None
    ):
        _fail(
            "transaction_id is not canonical",
            reason="malformed",
            field="transaction_id",
        )
    return value


def _diagnostics(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        _fail("diagnostics must be a sequence of strings", reason="malformed")
    result: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values, start=1):
        if index > MAX_DIAGNOSTICS:
            _fail(
                "diagnostics exceed item bound",
                reason="bound",
                maximum=MAX_DIAGNOSTICS,
            )
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > MAX_DIAGNOSTIC_CHARS
            or any(ord(character) < 32 and character not in "\t" for character in value)
        ):
            _fail("diagnostic text is malformed", reason="malformed")
        if value in seen:
            _fail(
                "diagnostics contain duplicate text",
                reason="duplicate",
                diagnostic=value,
            )
        seen.add(value)
        result.append(value)
    return tuple(sorted(result))


def _bounded_evidence(value: object) -> object:
    nodes = 0

    def visit(current: object, depth: int) -> object:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_EVIDENCE_NODES:
            _fail("preview evidence exceeds node bound", reason="bound")
        if depth > MAX_EVIDENCE_DEPTH:
            _fail("preview evidence exceeds depth bound", reason="bound")
        if current is None or isinstance(current, bool):
            return current
        if isinstance(current, int):
            if abs(current) > 2**63 - 1:
                _fail("preview evidence integer exceeds bound", reason="bound")
            return current
        if isinstance(current, float):
            if current != current or current in (float("inf"), float("-inf")):
                _fail("preview evidence contains non-finite number", reason="malformed")
            return current
        if isinstance(current, str):
            if len(current) > MAX_DIAGNOSTIC_CHARS:
                _fail("preview evidence text exceeds bound", reason="bound")
            return current
        if isinstance(current, list):
            if len(current) > MAX_EVIDENCE_FIELDS:
                _fail("preview evidence list exceeds bound", reason="bound")
            return [visit(item, depth + 1) for item in current]
        if isinstance(current, Mapping):
            if len(current) > MAX_EVIDENCE_FIELDS:
                _fail("preview evidence object exceeds bound", reason="bound")
            checked: list[tuple[str, object]] = []
            for key, item in current.items():
                if (
                    not isinstance(key, str)
                    or not key
                    or key != key.strip()
                    or len(key) > MAX_DIAGNOSTIC_CHARS
                ):
                    _fail("preview evidence key is malformed", reason="malformed")
                checked.append((key, item))
            return {
                key: visit(item, depth + 1)
                for key, item in sorted(checked, key=lambda pair: pair[0])
            }
        _fail("preview evidence contains unsupported type", reason="json_type")

    normalized = visit(value, 0)
    if len(_canonical_json_bytes(normalized)) > MAX_SERIALIZED_BYTES:
        _fail("preview evidence exceeds serialized byte bound", reason="bound")
    return normalized


def make_preview_step_result(
    phase: str,
    *,
    ok: bool,
    evidence: Mapping[str, object],
    diagnostics: Iterable[str] = (),
) -> PreviewStepResult:
    """Build one canonical backend step receipt."""

    if phase not in PREVIEW_PHASES:
        _fail("unknown preview phase", reason="phase", phase=phase)
    if not isinstance(ok, bool):
        _fail("preview step ok must be boolean", reason="malformed", phase=phase)
    if not isinstance(evidence, Mapping):
        _fail("preview step evidence must be an object", reason="malformed", phase=phase)
    normalized = _bounded_evidence(dict(evidence))
    return PreviewStepResult(
        phase=phase,
        ok=ok,
        evidence_digest=_digest(
            {
                "schema": PREVIEW_SCHEMA,
                "schema_version": PREVIEW_VERSION,
                "phase": phase,
                "ok": ok,
                "evidence": normalized,
            }
        ),
        diagnostics=_diagnostics(diagnostics),
    )


def validate_preview_step_result(
    result: PreviewStepResult,
    *,
    expected_phase: str,
) -> None:
    if not isinstance(result, PreviewStepResult):
        _fail(
            "preview backend returned invalid step type",
            reason="backend_contract",
            expected_phase=expected_phase,
        )
    if expected_phase not in PREVIEW_PHASES:
        _fail("unknown expected preview phase", reason="phase", phase=expected_phase)
    if result.phase != expected_phase:
        _fail(
            "preview backend returned wrong phase",
            reason="backend_contract",
            expected_phase=expected_phase,
            actual_phase=result.phase,
        )
    if not isinstance(result.ok, bool):
        _fail(
            "preview backend returned non-boolean status",
            reason="backend_contract",
            phase=expected_phase,
        )
    _sha256(result.evidence_digest, field="evidence_digest")
    normalized_diagnostics = _diagnostics(result.diagnostics)
    if normalized_diagnostics != result.diagnostics:
        _fail(
            "preview diagnostics are not canonical",
            reason="backend_contract",
            phase=expected_phase,
        )


def _validate_plan(plan: DesignPlan, *, label: str) -> None:
    if not isinstance(plan, DesignPlan):
        _fail(f"{label} must be a DesignPlan", reason="malformed", field=label)
    if plan.schema != DESIGN_PLAN_SCHEMA or plan.schema_version != INTENT_VERSION:
        _fail(
            f"{label} schema is unsupported",
            reason="schema",
            field=label,
        )
    _strict_int(
        plan.revision,
        field=f"{label}.revision",
        minimum=0,
        maximum=2**63 - 1,
    )
    try:
        canonical = plan.canonical_json()
        graph_digest = plan.digest()
    except Exception as exc:
        _fail(
            f"{label} cannot be canonically serialized",
            reason="plan_integrity",
            field=label,
            exception=type(exc).__name__,
        )
    if len(canonical.encode("utf-8")) > MAX_SERIALIZED_BYTES:
        _fail(f"{label} exceeds preview size bound", reason="bound", field=label)
    _sha256(graph_digest, field=f"{label}.graph_digest")


def _plan_state_digest(plan: DesignPlan) -> str:
    _validate_plan(plan, label="plan")
    return hashlib.sha256(plan.canonical_json().encode("utf-8")).hexdigest()


def _edit_digest(edit: DesignEdit) -> str:
    if not isinstance(edit, DesignEdit):
        _fail("prepared edit must be DesignEdit", reason="plan_integrity")
    return _digest(edit.to_payload())


def _transaction_payload(
    *,
    transaction_id: str,
    base_plan: DesignPlan,
    staged_plan: DesignPlan,
    edits: tuple[DesignEdit, ...],
) -> dict[str, object]:
    return {
        "schema": PREVIEW_SCHEMA,
        "schema_version": PREVIEW_VERSION,
        "transaction_id": transaction_id,
        "base_graph_digest": base_plan.digest(),
        "base_state_digest": _plan_state_digest(base_plan),
        "base_revision": base_plan.revision,
        "staged_graph_digest": staged_plan.digest(),
        "staged_state_digest": _plan_state_digest(staged_plan),
        "staged_revision": staged_plan.revision,
        "edit_ids": [edit.edit_id for edit in edits],
        "edit_digests": [_edit_digest(edit) for edit in edits],
    }


def stage_preview_transaction(
    base_plan: DesignPlan,
    edits: Sequence[Mapping[str, object] | DesignEdit],
    *,
    transaction_id: str,
) -> PreparedPreview:
    """Apply B011 edits immutably and prepare one preview transaction."""

    _validate_plan(base_plan, label="base_plan")
    canonical_id = _transaction_id(transaction_id)
    if isinstance(edits, (str, bytes, bytearray, Mapping)) or not isinstance(
        edits,
        Sequence,
    ):
        _fail("preview edits must be a sequence", reason="malformed")
    if not edits:
        _fail("preview transaction requires at least one edit", reason="empty_edits")
    if len(edits) > MAX_EDITS:
        _fail("preview transaction exceeds edit bound", reason="bound", maximum=MAX_EDITS)

    staged = base_plan
    recorded: list[DesignEdit] = []
    for index, edit in enumerate(edits):
        try:
            staged, applied = apply_edit(staged, edit)
        except Exception as exc:
            raise PreviewTransactionError(
                "preview edit staging failed",
                context={
                    "reason": "staging_failure",
                    "index": index,
                    "exception": type(exc).__name__,
                },
            ) from exc
        recorded.append(applied)

    recorded_tuple = tuple(recorded)
    payload = _transaction_payload(
        transaction_id=canonical_id,
        base_plan=base_plan,
        staged_plan=staged,
        edits=recorded_tuple,
    )
    transaction = PreviewTransaction(
        transaction_id=canonical_id,
        base_graph_digest=str(payload["base_graph_digest"]),
        base_state_digest=str(payload["base_state_digest"]),
        base_revision=int(payload["base_revision"]),
        staged_graph_digest=str(payload["staged_graph_digest"]),
        staged_state_digest=str(payload["staged_state_digest"]),
        staged_revision=int(payload["staged_revision"]),
        edit_ids=tuple(str(item) for item in payload["edit_ids"]),
        edit_digests=tuple(str(item) for item in payload["edit_digests"]),
        digest=_digest(payload),
    )
    prepared = PreparedPreview(
        transaction=transaction,
        base_plan=base_plan,
        staged_plan=staged,
        edits=recorded_tuple,
    )
    validate_prepared_preview(prepared)
    return prepared


def validate_prepared_preview(prepared: PreparedPreview) -> None:
    """Reapply prepared edits and verify every transaction identity."""

    if not isinstance(prepared, PreparedPreview):
        _fail("prepared preview has invalid type", reason="malformed")
    _validate_plan(prepared.base_plan, label="base_plan")
    _validate_plan(prepared.staged_plan, label="staged_plan")
    transaction = prepared.transaction
    if not isinstance(transaction, PreviewTransaction):
        _fail("prepared preview transaction has invalid type", reason="malformed")
    _transaction_id(transaction.transaction_id)
    if not prepared.edits or len(prepared.edits) > MAX_EDITS:
        _fail("prepared preview edit set is invalid", reason="plan_integrity")

    replayed = prepared.base_plan
    replayed_edits: list[DesignEdit] = []
    for edit in prepared.edits:
        try:
            replayed, applied = apply_edit(replayed, edit)
        except Exception as exc:
            _fail(
                "prepared preview edits cannot be replayed",
                reason="plan_integrity",
                exception=type(exc).__name__,
            )
        replayed_edits.append(applied)

    if replayed.canonical_json() != prepared.staged_plan.canonical_json():
        _fail("staged preview plan does not match edit replay", reason="plan_integrity")

    replayed_tuple = tuple(replayed_edits)
    payload = _transaction_payload(
        transaction_id=transaction.transaction_id,
        base_plan=prepared.base_plan,
        staged_plan=prepared.staged_plan,
        edits=replayed_tuple,
    )
    expected = PreviewTransaction(
        transaction_id=transaction.transaction_id,
        base_graph_digest=str(payload["base_graph_digest"]),
        base_state_digest=str(payload["base_state_digest"]),
        base_revision=int(payload["base_revision"]),
        staged_graph_digest=str(payload["staged_graph_digest"]),
        staged_state_digest=str(payload["staged_state_digest"]),
        staged_revision=int(payload["staged_revision"]),
        edit_ids=tuple(str(item) for item in payload["edit_ids"]),
        edit_digests=tuple(str(item) for item in payload["edit_digests"]),
        digest=_digest(payload),
    )
    if transaction != expected:
        _fail("preview transaction identity mismatch", reason="digest_mismatch")


def serialize_preview_transaction(prepared: PreparedPreview) -> str:
    validate_prepared_preview(prepared)
    raw = _canonical_json_bytes(prepared.transaction.to_dict())
    if len(raw) > MAX_SERIALIZED_BYTES:
        _fail("serialized preview transaction exceeds byte bound", reason="bound")
    return raw.decode("ascii")


def _outcome_payload(
    *,
    transaction: PreviewTransaction,
    status: str,
    resulting_state_digest: str,
    failure_phase: str | None,
    failure_reason: str | None,
    steps: tuple[PreviewStepResult, ...],
    rollback: PreviewStepResult | None,
) -> dict[str, object]:
    return {
        "schema": PREVIEW_SCHEMA,
        "schema_version": PREVIEW_VERSION,
        "transaction_digest": transaction.digest,
        "status": status,
        "resulting_state_digest": resulting_state_digest,
        "failure_phase": failure_phase,
        "failure_reason": failure_reason,
        "steps": [step.to_dict() for step in steps],
        "rollback": None if rollback is None else rollback.to_dict(),
    }


def _build_outcome(
    prepared: PreparedPreview,
    *,
    status: str,
    resulting_state_digest: str,
    failure_phase: str | None,
    failure_reason: str | None,
    steps: tuple[PreviewStepResult, ...],
    rollback: PreviewStepResult | None,
) -> PreviewOutcome:
    payload = _outcome_payload(
        transaction=prepared.transaction,
        status=status,
        resulting_state_digest=resulting_state_digest,
        failure_phase=failure_phase,
        failure_reason=failure_reason,
        steps=steps,
        rollback=rollback,
    )
    return PreviewOutcome(
        transaction_digest=prepared.transaction.digest,
        status=status,
        resulting_state_digest=resulting_state_digest,
        failure_phase=failure_phase,
        failure_reason=failure_reason,
        steps=steps,
        rollback=rollback,
        digest=_digest(payload),
    )


def _invoke_phase(
    backend: PreviewBackend,
    prepared: PreparedPreview,
    phase: str,
) -> PreviewStepResult:
    transaction = prepared.transaction
    if phase == "begin":
        result = backend.begin(transaction)
    elif phase == "apply":
        result = backend.apply(transaction, prepared.staged_plan)
    elif phase == "compile":
        result = backend.compile(transaction)
    elif phase == "runtime":
        result = backend.runtime(transaction)
    elif phase == "commit":
        result = backend.commit(transaction)
    else:
        _fail("unsupported execution phase", reason="phase", phase=phase)
    validate_preview_step_result(result, expected_phase=phase)
    return result


def _rollback(
    prepared: PreparedPreview,
    backend: PreviewBackend,
    *,
    failed_phase: str,
    reason: str,
    steps: tuple[PreviewStepResult, ...],
) -> tuple[DesignPlan, PreviewOutcome]:
    try:
        result = backend.rollback(
            prepared.transaction,
            failed_phase=failed_phase,
            reason=reason,
        )
    except Exception as exc:
        raise PreviewRollbackError(
            "preview backend raised during rollback",
            context={
                "reason": "rollback_exception",
                "failed_phase": failed_phase,
                "exception": type(exc).__name__,
            },
        ) from exc

    try:
        validate_preview_step_result(result, expected_phase="rollback")
    except PreviewTransactionError as exc:
        raise PreviewRollbackError(
            "preview backend returned invalid rollback evidence",
            context={
                "reason": "rollback_contract",
                "failed_phase": failed_phase,
            },
        ) from exc
    if not result.ok:
        raise PreviewRollbackError(
            "preview backend reported rollback failure",
            context={
                "reason": "rollback_failed",
                "failed_phase": failed_phase,
            },
        )

    outcome = _build_outcome(
        prepared,
        status="rolled_back",
        resulting_state_digest=prepared.transaction.base_state_digest,
        failure_phase=failed_phase,
        failure_reason=reason,
        steps=steps,
        rollback=result,
    )
    validate_preview_outcome(
        outcome,
        prepared,
        resulting_plan=prepared.base_plan,
    )
    return prepared.base_plan, outcome


def execute_preview_transaction(
    prepared: PreparedPreview,
    backend: PreviewBackend,
) -> tuple[DesignPlan, PreviewOutcome]:
    """Execute a prepared preview, rolling back on any failed backend phase."""

    validate_prepared_preview(prepared)
    steps: list[PreviewStepResult] = []

    for phase in EXECUTION_PHASES:
        try:
            result = _invoke_phase(backend, prepared, phase)
        except PreviewTransactionError:
            return _rollback(
                prepared,
                backend,
                failed_phase=phase,
                reason="backend_contract",
                steps=tuple(steps),
            )
        except Exception as exc:
            return _rollback(
                prepared,
                backend,
                failed_phase=phase,
                reason=f"backend_exception:{type(exc).__name__}",
                steps=tuple(steps),
            )
        steps.append(result)
        if not result.ok:
            return _rollback(
                prepared,
                backend,
                failed_phase=phase,
                reason="step_failed",
                steps=tuple(steps),
            )

    outcome = _build_outcome(
        prepared,
        status="committed",
        resulting_state_digest=prepared.transaction.staged_state_digest,
        failure_phase=None,
        failure_reason=None,
        steps=tuple(steps),
        rollback=None,
    )
    validate_preview_outcome(
        outcome,
        prepared,
        resulting_plan=prepared.staged_plan,
    )
    return prepared.staged_plan, outcome


def validate_preview_outcome(
    outcome: PreviewOutcome,
    prepared: PreparedPreview,
    *,
    resulting_plan: DesignPlan,
) -> None:
    """Independently revalidate committed or rolled-back transaction evidence."""

    validate_prepared_preview(prepared)
    _validate_plan(resulting_plan, label="resulting_plan")
    if not isinstance(outcome, PreviewOutcome):
        _fail("preview outcome has invalid type", reason="malformed")
    if outcome.transaction_digest != prepared.transaction.digest:
        _fail("preview outcome belongs to another transaction", reason="transaction_mismatch")
    if outcome.status not in {"committed", "rolled_back"}:
        _fail("preview outcome has invalid status", reason="outcome_status")
    if not outcome.steps or len(outcome.steps) > len(EXECUTION_PHASES):
        _fail("preview outcome has invalid execution evidence", reason="outcome_evidence")

    expected_phases = EXECUTION_PHASES[: len(outcome.steps)]
    for step, expected_phase in zip(outcome.steps, expected_phases, strict=True):
        validate_preview_step_result(step, expected_phase=expected_phase)

    actual_state_digest = _plan_state_digest(resulting_plan)
    if outcome.resulting_state_digest != actual_state_digest:
        _fail("preview outcome state digest mismatch", reason="digest_mismatch")

    if outcome.status == "committed":
        if len(outcome.steps) != len(EXECUTION_PHASES):
            _fail("committed preview is missing phase evidence", reason="outcome_evidence")
        if any(not step.ok for step in outcome.steps):
            _fail("committed preview contains failed phase", reason="outcome_evidence")
        if outcome.rollback is not None:
            _fail("committed preview must not contain rollback evidence", reason="outcome_evidence")
        if outcome.failure_phase is not None or outcome.failure_reason is not None:
            _fail("committed preview must not contain failure metadata", reason="outcome_evidence")
        if actual_state_digest != prepared.transaction.staged_state_digest:
            _fail("committed preview did not produce staged plan", reason="digest_mismatch")
    else:
        if outcome.failure_phase not in EXECUTION_PHASES:
            _fail("rolled-back preview has invalid failure phase", reason="outcome_evidence")
        failure_index = EXECUTION_PHASES.index(outcome.failure_phase)
        if len(outcome.steps) not in {failure_index, failure_index + 1}:
            _fail("rolled-back preview has inconsistent phase evidence", reason="outcome_evidence")
        if outcome.failure_reason is None:
            _fail("rolled-back preview is missing failure reason", reason="outcome_evidence")
        if outcome.rollback is None:
            _fail("rolled-back preview lacks rollback evidence", reason="outcome_evidence")
        validate_preview_step_result(outcome.rollback, expected_phase="rollback")
        if not outcome.rollback.ok:
            _fail("rolled-back preview records failed rollback", reason="outcome_evidence")
        if actual_state_digest != prepared.transaction.base_state_digest:
            _fail("rolled-back preview did not restore base plan", reason="digest_mismatch")

    for digest in (
        outcome.transaction_digest,
        outcome.resulting_state_digest,
        outcome.digest,
    ):
        _sha256(digest, field="outcome_digest")

    payload = _outcome_payload(
        transaction=prepared.transaction,
        status=outcome.status,
        resulting_state_digest=outcome.resulting_state_digest,
        failure_phase=outcome.failure_phase,
        failure_reason=outcome.failure_reason,
        steps=outcome.steps,
        rollback=outcome.rollback,
    )
    if outcome.digest != _digest(payload):
        _fail("preview outcome digest mismatch", reason="digest_mismatch")


def serialize_preview_outcome(
    outcome: PreviewOutcome,
    prepared: PreparedPreview,
    *,
    resulting_plan: DesignPlan,
) -> str:
    validate_preview_outcome(
        outcome,
        prepared,
        resulting_plan=resulting_plan,
    )
    raw = _canonical_json_bytes(outcome.to_dict())
    if len(raw) > MAX_SERIALIZED_BYTES:
        _fail("serialized preview outcome exceeds byte bound", reason="bound")
    return raw.decode("ascii")


__all__ = [
    "EXECUTION_PHASES",
    "MAX_DIAGNOSTICS",
    "MAX_EDITS",
    "MAX_SERIALIZED_BYTES",
    "PREVIEW_PHASES",
    "PREVIEW_SCHEMA",
    "PREVIEW_VERSION",
    "PreparedPreview",
    "PreviewBackend",
    "PreviewOutcome",
    "PreviewRollbackError",
    "PreviewStepResult",
    "PreviewTransaction",
    "PreviewTransactionError",
    "execute_preview_transaction",
    "make_preview_step_result",
    "serialize_preview_outcome",
    "serialize_preview_transaction",
    "stage_preview_transaction",
    "validate_prepared_preview",
    "validate_preview_outcome",
    "validate_preview_step_result",
]
