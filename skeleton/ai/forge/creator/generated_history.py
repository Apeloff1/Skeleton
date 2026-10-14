"""Content-addressed undo/redo history for generated creator state (#807 B018).

B018 records exact B012 design-graph snapshots and binds every logical
transition to the recomputed B016 semantic diff. Undo and redo restore canonical
snapshots rather than replaying raw file edits. A new transition after undo
clears the abandoned redo branch and prunes unreachable stored snapshots.

This module owns data/history integrity only. It performs no filesystem,
engine, process, network, or deployment mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Final, Mapping, NoReturn

from skeleton.forge.creator.design_graph import (
    DesignGraphSnapshot,
    parse_design_graph,
)
from skeleton.forge.creator.semantic_diff import (
    MAX_CHANGES as MAX_SEMANTIC_CHANGES,
    SemanticDiff,
    semantic_diff,
)
from skeleton.kernel.errors import SkeletonError


HISTORY_SCHEMA: Final = "creator.generated_history.v1"
HISTORY_VERSION: Final = 1
MAX_HISTORY_ENTRIES: Final = 64
MAX_SNAPSHOTS: Final = MAX_HISTORY_ENTRIES + 1
MAX_LABEL_CHARS: Final = 256
MAX_SUMMARIES: Final = 64
MAX_SERIALIZED_BYTES: Final = 32 * 1024 * 1024

_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_TRANSITION_ID_RE: Final = re.compile(r"^tr_[0-9a-f]{24}$")


class GeneratedHistoryError(SkeletonError):
    """Generated-state history violates ordering or content integrity."""

    code = "CRE.GENERATED_HISTORY"
    http_status = 409


@dataclass(frozen=True, slots=True)
class StoredSnapshot:
    graph_digest: str
    serialized: str

    def to_dict(self) -> dict[str, object]:
        return {
            "graph_digest": self.graph_digest,
            "serialized": self.serialized,
        }


@dataclass(frozen=True, slots=True)
class StateTransition:
    transition_id: str
    ordinal: int
    label: str
    before_digest: str
    after_digest: str
    semantic_diff_digest: str
    change_count: int
    summaries: tuple[str, ...]
    summaries_truncated: bool
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "transition_id": self.transition_id,
            "ordinal": self.ordinal,
            "label": self.label,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
            "semantic_diff_digest": self.semantic_diff_digest,
            "change_count": self.change_count,
            "summaries": list(self.summaries),
            "summaries_truncated": self.summaries_truncated,
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class GeneratedStateHistory:
    schema: str
    schema_version: int
    project_id: str
    revision: int
    current_digest: str
    snapshots: tuple[StoredSnapshot, ...]
    transitions: tuple[StateTransition, ...]
    undo_stack: tuple[str, ...]
    redo_stack: tuple[str, ...]
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "revision": self.revision,
            "current_digest": self.current_digest,
            "snapshots": [snapshot.to_dict() for snapshot in self.snapshots],
            "transitions": [transition.to_dict() for transition in self.transitions],
            "undo_stack": list(self.undo_stack),
            "redo_stack": list(self.redo_stack),
            "digest": self.digest,
        }

    @property
    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self.redo_stack)


def _fail(message: str, *, reason: str, **context: object) -> NoReturn:
    raise GeneratedHistoryError(message, context={"reason": reason, **context})


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
        _fail("generated history is not canonical JSON", reason="json_type")
        raise AssertionError("unreachable") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate JSON field in generated history", reason="duplicate_field", field=key)
        result[key] = value
    return result


def _sha256(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(
            f"{field} must be a lowercase sha256 digest",
            reason="malformed",
            field=field,
        )
    return value


def _transition_id(value: object) -> str:
    if not isinstance(value, str) or _TRANSITION_ID_RE.fullmatch(value) is None:
        _fail(
            "transition_id is not canonical",
            reason="transition_integrity",
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
        _fail(f"{field} is outside accepted integer range", reason="malformed", field=field)
    return value


def _label(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_LABEL_CHARS
        or any(ord(character) < 32 and character not in "\t" for character in value)
    ):
        _fail("history transition label is malformed", reason="malformed", field="label")
    return value


def _validated_snapshot(
    value: DesignGraphSnapshot,
    *,
    field: str,
) -> DesignGraphSnapshot:
    if not isinstance(value, DesignGraphSnapshot):
        _fail(f"{field} must be DesignGraphSnapshot", reason="malformed", field=field)
    try:
        parsed = parse_design_graph(value.serialize())
    except Exception as exc:
        raise GeneratedHistoryError(
            f"{field} failed design-graph validation",
            context={
                "reason": "snapshot_integrity",
                "field": field,
                "exception": type(exc).__name__,
            },
        ) from exc
    if parsed != value:
        _fail(f"{field} does not round-trip canonically", reason="snapshot_integrity", field=field)
    return parsed


def _snapshot_record(snapshot: DesignGraphSnapshot) -> StoredSnapshot:
    checked = _validated_snapshot(snapshot, field="snapshot")
    serialized = checked.serialize()
    return StoredSnapshot(
        graph_digest=checked.digest,
        serialized=serialized,
    )


def _snapshot_from_record(record: StoredSnapshot) -> DesignGraphSnapshot:
    if not isinstance(record, StoredSnapshot):
        _fail("snapshot record has invalid type", reason="snapshot_integrity")
    if not isinstance(record.graph_digest, str) or len(record.graph_digest) != 64:
        _fail("snapshot record digest is malformed", reason="snapshot_integrity")
    if not isinstance(record.serialized, str) or not record.serialized:
        _fail("snapshot record serialization is malformed", reason="snapshot_integrity")
    try:
        snapshot = parse_design_graph(record.serialized)
    except Exception as exc:
        raise GeneratedHistoryError(
            "stored snapshot cannot be parsed",
            context={
                "reason": "snapshot_integrity",
                "exception": type(exc).__name__,
            },
        ) from exc
    if snapshot.digest != record.graph_digest:
        _fail("stored snapshot digest mismatch", reason="snapshot_integrity")
    if snapshot.serialize() != record.serialized:
        _fail("stored snapshot is not canonical", reason="snapshot_integrity")
    return snapshot


def _transition_payload(
    *,
    ordinal: int,
    label: str,
    before_digest: str,
    after_digest: str,
    diff: SemanticDiff,
) -> dict[str, object]:
    summaries = diff.summaries()[:MAX_SUMMARIES]
    return {
        "ordinal": ordinal,
        "label": label,
        "before_digest": before_digest,
        "after_digest": after_digest,
        "semantic_diff_digest": diff.digest,
        "change_count": len(diff.changes),
        "summaries": list(summaries),
        "summaries_truncated": len(diff.changes) > MAX_SUMMARIES,
    }


def _make_transition(
    *,
    ordinal: int,
    label: str,
    before: DesignGraphSnapshot,
    after: DesignGraphSnapshot,
) -> StateTransition:
    checked_label = _label(label)
    checked_ordinal = _strict_int(
        ordinal,
        field="ordinal",
        minimum=1,
        maximum=(1 << 63) - 1,
    )
    diff = semantic_diff(before, after)
    payload = _transition_payload(
        ordinal=checked_ordinal,
        label=checked_label,
        before_digest=before.digest,
        after_digest=after.digest,
        diff=diff,
    )
    transition_id = f"tr_{_digest(payload)[:24]}"
    with_id = {
        "transition_id": transition_id,
        **payload,
    }
    return StateTransition(
        transition_id=transition_id,
        ordinal=checked_ordinal,
        label=checked_label,
        before_digest=before.digest,
        after_digest=after.digest,
        semantic_diff_digest=diff.digest,
        change_count=len(diff.changes),
        summaries=tuple(diff.summaries()[:MAX_SUMMARIES]),
        summaries_truncated=len(diff.changes) > MAX_SUMMARIES,
        digest=_digest(with_id),
    )


def _transition_map(
    transitions: tuple[StateTransition, ...],
) -> dict[str, StateTransition]:
    result: dict[str, StateTransition] = {}
    for transition in transitions:
        if not isinstance(transition, StateTransition):
            _fail("history transition has invalid type", reason="transition_integrity")
        transition_id = _transition_id(transition.transition_id)
        if transition_id in result:
            _fail(
                "duplicate transition id",
                reason="transition_integrity",
                transition_id=transition_id,
            )
        result[transition_id] = transition
    return result


def _snapshot_map(
    snapshots: tuple[StoredSnapshot, ...],
) -> dict[str, StoredSnapshot]:
    result: dict[str, StoredSnapshot] = {}
    for record in snapshots:
        if not isinstance(record, StoredSnapshot):
            _fail("snapshot record has invalid type", reason="snapshot_integrity")
        graph_digest = _sha256(
            record.graph_digest,
            field="snapshot.graph_digest",
        )
        if not isinstance(record.serialized, str) or not record.serialized:
            _fail(
                "snapshot serialization is malformed",
                reason="snapshot_integrity",
            )
        if graph_digest in result:
            _fail(
                "duplicate stored snapshot digest",
                reason="snapshot_integrity",
                graph_digest=graph_digest,
            )
        result[graph_digest] = record
    return result


def _history_payload(
    *,
    project_id: str,
    revision: int,
    current_digest: str,
    snapshots: tuple[StoredSnapshot, ...],
    transitions: tuple[StateTransition, ...],
    undo_stack: tuple[str, ...],
    redo_stack: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema": HISTORY_SCHEMA,
        "schema_version": HISTORY_VERSION,
        "project_id": project_id,
        "revision": revision,
        "current_digest": current_digest,
        "snapshots": [snapshot.to_dict() for snapshot in snapshots],
        "transitions": [transition.to_dict() for transition in transitions],
        "undo_stack": list(undo_stack),
        "redo_stack": list(redo_stack),
    }


def _build_history(
    *,
    project_id: str,
    revision: int,
    current_digest: str,
    snapshots: tuple[StoredSnapshot, ...],
    transitions: tuple[StateTransition, ...],
    undo_stack: tuple[str, ...],
    redo_stack: tuple[str, ...],
) -> GeneratedStateHistory:
    if len(transitions) > MAX_HISTORY_ENTRIES:
        _fail("history exceeds transition bound", reason="bound", maximum=MAX_HISTORY_ENTRIES)
    if len(snapshots) > MAX_SNAPSHOTS:
        _fail("history exceeds snapshot bound", reason="bound", maximum=MAX_SNAPSHOTS)
    canonical_snapshots = tuple(sorted(snapshots, key=lambda row: row.graph_digest))
    canonical_transitions = tuple(sorted(transitions, key=lambda row: row.transition_id))
    payload = _history_payload(
        project_id=project_id,
        revision=revision,
        current_digest=current_digest,
        snapshots=canonical_snapshots,
        transitions=canonical_transitions,
        undo_stack=undo_stack,
        redo_stack=redo_stack,
    )
    encoded = _canonical_json_bytes(payload)
    if len(encoded) > MAX_SERIALIZED_BYTES:
        _fail(
            "generated history exceeds serialized byte bound",
            reason="bound",
            maximum=MAX_SERIALIZED_BYTES,
        )
    history = GeneratedStateHistory(
        schema=HISTORY_SCHEMA,
        schema_version=HISTORY_VERSION,
        project_id=project_id,
        revision=revision,
        current_digest=current_digest,
        snapshots=canonical_snapshots,
        transitions=canonical_transitions,
        undo_stack=undo_stack,
        redo_stack=redo_stack,
        digest=hashlib.sha256(encoded).hexdigest(),
    )
    validate_generated_history(history)
    return history


def create_generated_history(
    initial: DesignGraphSnapshot,
) -> GeneratedStateHistory:
    """Create an empty undo/redo history anchored to one exact B012 snapshot."""

    checked = _validated_snapshot(initial, field="initial")
    record = _snapshot_record(checked)
    return _build_history(
        project_id=checked.project_id,
        revision=0,
        current_digest=checked.digest,
        snapshots=(record,),
        transitions=(),
        undo_stack=(),
        redo_stack=(),
    )


def _load_snapshot(
    history: GeneratedStateHistory,
    graph_digest: str,
) -> DesignGraphSnapshot:
    records = _snapshot_map(history.snapshots)
    record = records.get(graph_digest)
    if record is None:
        _fail(
            "history references missing snapshot",
            reason="snapshot_integrity",
            graph_digest=graph_digest,
        )
    return _snapshot_from_record(record)


def current_generated_snapshot(
    history: GeneratedStateHistory,
) -> DesignGraphSnapshot:
    validate_generated_history(history)
    return _load_snapshot(history, history.current_digest)


def _required_snapshot_digests(
    transitions: tuple[StateTransition, ...],
    *,
    current_digest: str,
) -> set[str]:
    required = {current_digest}
    for transition in transitions:
        required.add(transition.before_digest)
        required.add(transition.after_digest)
    return required


def _pruned_snapshots(
    records: Mapping[str, StoredSnapshot],
    transitions: tuple[StateTransition, ...],
    *,
    current_digest: str,
) -> tuple[StoredSnapshot, ...]:
    required = _required_snapshot_digests(
        transitions,
        current_digest=current_digest,
    )
    missing = sorted(required - set(records))
    if missing:
        _fail(
            "cannot prune history with missing snapshots",
            reason="snapshot_integrity",
            missing=missing,
        )
    return tuple(records[digest] for digest in sorted(required))


def record_generated_transition(
    history: GeneratedStateHistory,
    current: DesignGraphSnapshot,
    target: DesignGraphSnapshot,
    *,
    label: str,
) -> tuple[GeneratedStateHistory, StateTransition]:
    """Record one logical generated-state transition and clear redo history."""

    validate_generated_history(history)
    checked_current = _validated_snapshot(current, field="current")
    checked_target = _validated_snapshot(target, field="target")
    if checked_current.project_id != history.project_id:
        _fail("current snapshot project does not match history", reason="project_mismatch")
    if checked_target.project_id != history.project_id:
        _fail("target snapshot project does not match history", reason="project_mismatch")
    if checked_current.digest != history.current_digest:
        _fail(
            "current snapshot does not match history cursor",
            reason="current_mismatch",
            expected=history.current_digest,
            actual=checked_current.digest,
        )
    if checked_target.digest == checked_current.digest:
        _fail("target snapshot does not change generated state", reason="no_change")
    if len(history.undo_stack) >= MAX_HISTORY_ENTRIES:
        _fail("history transition bound is exhausted", reason="bound")

    next_revision = history.revision + 1
    transition = _make_transition(
        ordinal=next_revision,
        label=label,
        before=checked_current,
        after=checked_target,
    )

    transition_by_id = _transition_map(history.transitions)
    retained_transitions = [
        transition_by_id[transition_id]
        for transition_id in history.undo_stack
    ]
    retained_transitions.append(transition)
    transitions = tuple(retained_transitions)

    records = _snapshot_map(history.snapshots)
    records[checked_current.digest] = _snapshot_record(checked_current)
    records[checked_target.digest] = _snapshot_record(checked_target)
    snapshots = _pruned_snapshots(
        records,
        transitions,
        current_digest=checked_target.digest,
    )

    next_history = _build_history(
        project_id=history.project_id,
        revision=next_revision,
        current_digest=checked_target.digest,
        snapshots=snapshots,
        transitions=transitions,
        undo_stack=(*history.undo_stack, transition.transition_id),
        redo_stack=(),
    )
    return next_history, transition


def undo_generated_state(
    history: GeneratedStateHistory,
    current: DesignGraphSnapshot,
) -> tuple[GeneratedStateHistory, DesignGraphSnapshot, StateTransition]:
    """Move the cursor to the exact snapshot before the latest transition."""

    validate_generated_history(history)
    checked_current = _validated_snapshot(current, field="current")
    if checked_current.digest != history.current_digest:
        _fail("current snapshot does not match history cursor", reason="current_mismatch")
    if not history.undo_stack:
        _fail("no generated-state transition is available to undo", reason="undo_empty")

    transition_id = history.undo_stack[-1]
    transition = _transition_map(history.transitions)[transition_id]
    if transition.after_digest != checked_current.digest:
        _fail("undo transition is not attached to current state", reason="stack_integrity")
    restored = _load_snapshot(history, transition.before_digest)

    next_history = _build_history(
        project_id=history.project_id,
        revision=history.revision + 1,
        current_digest=restored.digest,
        snapshots=history.snapshots,
        transitions=history.transitions,
        undo_stack=history.undo_stack[:-1],
        redo_stack=(*history.redo_stack, transition_id),
    )
    return next_history, restored, transition


def redo_generated_state(
    history: GeneratedStateHistory,
    current: DesignGraphSnapshot,
) -> tuple[GeneratedStateHistory, DesignGraphSnapshot, StateTransition]:
    """Move the cursor to the exact snapshot after the next redo transition."""

    validate_generated_history(history)
    checked_current = _validated_snapshot(current, field="current")
    if checked_current.digest != history.current_digest:
        _fail("current snapshot does not match history cursor", reason="current_mismatch")
    if not history.redo_stack:
        _fail("no generated-state transition is available to redo", reason="redo_empty")

    transition_id = history.redo_stack[-1]
    transition = _transition_map(history.transitions)[transition_id]
    if transition.before_digest != checked_current.digest:
        _fail("redo transition is not attached to current state", reason="stack_integrity")
    restored = _load_snapshot(history, transition.after_digest)

    next_history = _build_history(
        project_id=history.project_id,
        revision=history.revision + 1,
        current_digest=restored.digest,
        snapshots=history.snapshots,
        transitions=history.transitions,
        undo_stack=(*history.undo_stack, transition_id),
        redo_stack=history.redo_stack[:-1],
    )
    return next_history, restored, transition


def _validate_transition(
    transition: StateTransition,
    *,
    ordinal_ceiling: int,
    snapshots: Mapping[str, DesignGraphSnapshot],
) -> None:
    if not isinstance(transition, StateTransition):
        _fail("history transition has invalid type", reason="transition_integrity")
    ordinal = _strict_int(
        transition.ordinal,
        field="transition.ordinal",
        minimum=1,
        maximum=max(1, ordinal_ceiling),
    )
    checked_label = _label(transition.label)
    before = snapshots.get(transition.before_digest)
    after = snapshots.get(transition.after_digest)
    if before is None or after is None:
        _fail(
            "transition references missing snapshot",
            reason="transition_integrity",
            transition_id=transition.transition_id,
        )
    if before.project_id != after.project_id:
        _fail("transition crosses projects", reason="transition_integrity")
    if before.digest == after.digest:
        _fail("transition does not change state", reason="transition_integrity")

    diff = semantic_diff(before, after)
    payload = _transition_payload(
        ordinal=ordinal,
        label=checked_label,
        before_digest=before.digest,
        after_digest=after.digest,
        diff=diff,
    )
    expected_id = f"tr_{_digest(payload)[:24]}"
    expected_digest = _digest({"transition_id": expected_id, **payload})

    if transition.transition_id != expected_id:
        _fail("transition id mismatch", reason="transition_integrity")
    if transition.semantic_diff_digest != diff.digest:
        _fail("transition semantic diff mismatch", reason="transition_integrity")
    change_count = _strict_int(
        transition.change_count,
        field="transition.change_count",
        minimum=0,
        maximum=MAX_SEMANTIC_CHANGES,
    )
    if change_count != len(diff.changes):
        _fail("transition change count mismatch", reason="transition_integrity")
    if transition.summaries != tuple(diff.summaries()[:MAX_SUMMARIES]):
        _fail("transition semantic summaries mismatch", reason="transition_integrity")
    if not isinstance(transition.summaries_truncated, bool):
        _fail(
            "transition summary truncation flag must be boolean",
            reason="transition_integrity",
        )
    if transition.summaries_truncated != (len(diff.changes) > MAX_SUMMARIES):
        _fail("transition summary truncation flag mismatch", reason="transition_integrity")
    if transition.digest != expected_digest:
        _fail("transition digest mismatch", reason="transition_integrity")


def _validate_stack_chain(
    *,
    current_digest: str,
    undo_stack: tuple[str, ...],
    redo_stack: tuple[str, ...],
    transitions: Mapping[str, StateTransition],
) -> None:
    if undo_stack:
        first = transitions[undo_stack[0]]
        cursor = first.before_digest
        for transition_id in undo_stack:
            transition = transitions[transition_id]
            if transition.before_digest != cursor:
                _fail("undo stack transition chain is broken", reason="stack_integrity")
            cursor = transition.after_digest
        if cursor != current_digest:
            _fail("undo stack does not terminate at current state", reason="stack_integrity")

    cursor = current_digest
    for transition_id in reversed(redo_stack):
        transition = transitions[transition_id]
        if transition.before_digest != cursor:
            _fail("redo stack transition chain is broken", reason="stack_integrity")
        cursor = transition.after_digest


def validate_generated_history(history: GeneratedStateHistory) -> None:
    """Fully validate snapshots, semantic transitions, stacks, and root digest."""

    if not isinstance(history, GeneratedStateHistory):
        _fail("history must be GeneratedStateHistory", reason="malformed")
    if history.schema != HISTORY_SCHEMA:
        _fail("unsupported generated history schema", reason="schema")
    _strict_int(
        history.schema_version,
        field="history.schema_version",
        minimum=HISTORY_VERSION,
        maximum=HISTORY_VERSION,
    )
    revision = _strict_int(
        history.revision,
        field="history.revision",
        minimum=0,
        maximum=(1 << 63) - 1,
    )
    if not isinstance(history.project_id, str) or not history.project_id:
        _fail("history project_id is malformed", reason="malformed")
    _sha256(history.current_digest, field="history.current_digest")
    _sha256(history.digest, field="history.digest")
    if len(history.snapshots) > MAX_SNAPSHOTS:
        _fail("history exceeds snapshot bound", reason="bound")
    if len(history.transitions) > MAX_HISTORY_ENTRIES:
        _fail("history exceeds transition bound", reason="bound")

    records = _snapshot_map(history.snapshots)
    parsed_snapshots: dict[str, DesignGraphSnapshot] = {}
    for graph_digest, record in records.items():
        snapshot = _snapshot_from_record(record)
        if snapshot.project_id != history.project_id:
            _fail("stored snapshot belongs to another project", reason="project_mismatch")
        parsed_snapshots[graph_digest] = snapshot

    if history.current_digest not in parsed_snapshots:
        _fail("history current snapshot is missing", reason="snapshot_integrity")

    if history.snapshots != tuple(
        sorted(history.snapshots, key=lambda row: row.graph_digest)
    ):
        _fail(
            "history snapshot inventory is not canonically ordered",
            reason="snapshot_integrity",
        )
    if history.transitions != tuple(
        sorted(history.transitions, key=lambda row: row.transition_id)
    ):
        _fail(
            "history transition inventory is not canonically ordered",
            reason="transition_integrity",
        )

    transition_by_id = _transition_map(history.transitions)
    for transition in history.transitions:
        _transition_id(transition.transition_id)
        _sha256(transition.before_digest, field="transition.before_digest")
        _sha256(transition.after_digest, field="transition.after_digest")
        _sha256(
            transition.semantic_diff_digest,
            field="transition.semantic_diff_digest",
        )
        _sha256(transition.digest, field="transition.digest")
        _validate_transition(
            transition,
            ordinal_ceiling=max(1, revision),
            snapshots=parsed_snapshots,
        )

    checked_undo = tuple(_transition_id(item) for item in history.undo_stack)
    checked_redo = tuple(_transition_id(item) for item in history.redo_stack)
    if checked_undo != history.undo_stack or checked_redo != history.redo_stack:
        _fail("history stacks are not canonical", reason="stack_integrity")
    if len(set(checked_undo)) != len(checked_undo):
        _fail("undo stack contains duplicate transition ids", reason="stack_integrity")
    if len(set(checked_redo)) != len(checked_redo):
        _fail("redo stack contains duplicate transition ids", reason="stack_integrity")
    if set(history.undo_stack) & set(history.redo_stack):
        _fail("transition appears in both undo and redo stacks", reason="stack_integrity")
    stacked = set(history.undo_stack) | set(history.redo_stack)
    missing_stack_ids = stacked - set(transition_by_id)
    if missing_stack_ids:
        _fail(
            "history stack references unknown transition",
            reason="stack_integrity",
            missing=sorted(missing_stack_ids),
        )
    unstacked_ids = set(transition_by_id) - stacked
    if unstacked_ids:
        _fail(
            "history transition inventory contains unreachable entries",
            reason="stack_integrity",
            unstacked=sorted(unstacked_ids),
        )

    _validate_stack_chain(
        current_digest=history.current_digest,
        undo_stack=history.undo_stack,
        redo_stack=history.redo_stack,
        transitions=transition_by_id,
    )

    required_snapshots = _required_snapshot_digests(
        history.transitions,
        current_digest=history.current_digest,
    )
    if required_snapshots != set(records):
        _fail(
            "history snapshot store is not canonically pruned",
            reason="snapshot_integrity",
            missing=sorted(required_snapshots - set(records)),
            extra=sorted(set(records) - required_snapshots),
        )

    payload = _history_payload(
        project_id=history.project_id,
        revision=revision,
        current_digest=history.current_digest,
        snapshots=history.snapshots,
        transitions=history.transitions,
        undo_stack=history.undo_stack,
        redo_stack=history.redo_stack,
    )
    encoded = _canonical_json_bytes(payload)
    if len(encoded) > MAX_SERIALIZED_BYTES:
        _fail("generated history exceeds serialized byte bound", reason="bound")
    expected = hashlib.sha256(encoded).hexdigest()
    if history.digest != expected:
        _fail("generated history digest mismatch", reason="digest_mismatch")


def serialize_generated_history(history: GeneratedStateHistory) -> str:
    validate_generated_history(history)
    raw = _canonical_json_bytes(history.to_dict())
    if len(raw) > MAX_SERIALIZED_BYTES:
        _fail("serialized generated history exceeds byte bound", reason="bound")
    return raw.decode("ascii")


def _parse_snapshot_record(value: object) -> StoredSnapshot:
    if not isinstance(value, Mapping):
        _fail("snapshot record must be an object", reason="malformed")
    if set(value) != {"graph_digest", "serialized"}:
        _fail("snapshot record has invalid field set", reason="malformed")
    return StoredSnapshot(
        graph_digest=value["graph_digest"],
        serialized=value["serialized"],
    )


def _parse_transition(value: object) -> StateTransition:
    if not isinstance(value, Mapping):
        _fail("transition record must be an object", reason="malformed")
    expected = {
        "transition_id",
        "ordinal",
        "label",
        "before_digest",
        "after_digest",
        "semantic_diff_digest",
        "change_count",
        "summaries",
        "summaries_truncated",
        "digest",
    }
    if set(value) != expected:
        _fail("transition record has invalid field set", reason="malformed")
    summaries = value["summaries"]
    if not isinstance(summaries, list) or not all(isinstance(item, str) for item in summaries):
        _fail("transition summaries must be text list", reason="malformed")
    return StateTransition(
        transition_id=value["transition_id"],
        ordinal=value["ordinal"],
        label=value["label"],
        before_digest=value["before_digest"],
        after_digest=value["after_digest"],
        semantic_diff_digest=value["semantic_diff_digest"],
        change_count=value["change_count"],
        summaries=tuple(summaries),
        summaries_truncated=value["summaries_truncated"],
        digest=value["digest"],
    )


def parse_generated_history(
    raw: str | bytes | Mapping[str, object],
) -> GeneratedStateHistory:
    """Parse and fully revalidate durable undo/redo state."""

    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GeneratedHistoryError(
                "generated history must be UTF-8",
                context={"reason": "encoding"},
            ) from exc
    if isinstance(raw, str):
        if not raw or len(raw.encode("utf-8")) > MAX_SERIALIZED_BYTES:
            _fail("generated history byte size is invalid", reason="bound")
        try:
            payload = json.loads(raw, object_pairs_hook=_unique_object)
        except GeneratedHistoryError:
            raise
        except json.JSONDecodeError as exc:
            raise GeneratedHistoryError(
                "generated history is not valid JSON",
                context={"reason": "json"},
            ) from exc
    elif isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        _fail("generated history must be JSON text/bytes or object", reason="malformed")

    expected = {
        "schema",
        "schema_version",
        "project_id",
        "revision",
        "current_digest",
        "snapshots",
        "transitions",
        "undo_stack",
        "redo_stack",
        "digest",
    }
    if not isinstance(payload, dict) or set(payload) != expected:
        _fail("generated history root has invalid field set", reason="malformed")
    if not isinstance(payload["snapshots"], list):
        _fail("generated history snapshots must be a list", reason="malformed")
    if not isinstance(payload["transitions"], list):
        _fail("generated history transitions must be a list", reason="malformed")
    if not isinstance(payload["undo_stack"], list) or not all(
        isinstance(item, str) for item in payload["undo_stack"]
    ):
        _fail("generated history undo_stack must be text list", reason="malformed")
    if not isinstance(payload["redo_stack"], list) or not all(
        isinstance(item, str) for item in payload["redo_stack"]
    ):
        _fail("generated history redo_stack must be text list", reason="malformed")

    history = GeneratedStateHistory(
        schema=payload["schema"],
        schema_version=payload["schema_version"],
        project_id=payload["project_id"],
        revision=payload["revision"],
        current_digest=payload["current_digest"],
        snapshots=tuple(_parse_snapshot_record(item) for item in payload["snapshots"]),
        transitions=tuple(_parse_transition(item) for item in payload["transitions"]),
        undo_stack=tuple(payload["undo_stack"]),
        redo_stack=tuple(payload["redo_stack"]),
        digest=payload["digest"],
    )
    validate_generated_history(history)
    return history


__all__ = [
    "HISTORY_SCHEMA",
    "HISTORY_VERSION",
    "GeneratedHistoryError",
    "GeneratedStateHistory",
    "MAX_HISTORY_ENTRIES",
    "MAX_SERIALIZED_BYTES",
    "MAX_SNAPSHOTS",
    "StateTransition",
    "StoredSnapshot",
    "create_generated_history",
    "current_generated_snapshot",
    "parse_generated_history",
    "record_generated_transition",
    "redo_generated_state",
    "serialize_generated_history",
    "undo_generated_state",
    "validate_generated_history",
]
