"""Meaningful design-graph diffs for #807 B016.

B016 compares persistent B012 design graphs and reports game-domain changes
instead of raw repository/file deltas. Stable node IDs and semantic
relationship triples are authoritative. Edge-ID churn and provenance-only
source_path changes are intentionally suppressed from user-facing changes.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Final, Mapping, NoReturn

from skeleton.forge.creator.design_graph import (
    EDGE_KINDS,
    NODE_KINDS,
    DesignGraphEdge,
    DesignGraphNode,
    DesignGraphSnapshot,
    parse_design_graph,
)
from skeleton.kernel.errors import SkeletonError


SEMANTIC_DIFF_SCHEMA: Final = "creator.semantic_diff.v1"
SEMANTIC_DIFF_VERSION: Final = 1
MAX_CHANGES: Final = 65_536
MAX_SUMMARY_CHARS: Final = 2_048
MAX_SERIALIZED_BYTES: Final = 8 * 1024 * 1024

IGNORED_ATTRIBUTES: Final = frozenset({"source_path"})
CHANGE_ACTIONS: Final = (
    "node_removed",
    "node_added",
    "node_kind_changed",
    "node_renamed",
    "node_attributes_changed",
    "relationship_removed",
    "relationship_added",
    "relationship_attributes_changed",
)
_ACTION_ORDER: Final = {name: index for index, name in enumerate(CHANGE_ACTIONS)}
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")

_EDGE_VERBS: Final = {
    "assumes": ("now assumes", "no longer assumes"),
    "constrained_by": ("is now constrained by", "is no longer constrained by"),
    "contains": ("now contains", "no longer contains"),
    "depends_on": ("now depends on", "no longer depends on"),
    "produces": ("now produces", "no longer produces"),
    "references": ("now references", "no longer references"),
    "validated_by": ("is now validated by", "is no longer validated by"),
    "validates": ("now validates", "no longer validates"),
}


class SemanticDiffError(SkeletonError):
    """Semantic graph comparison is invalid or ambiguous."""

    code = "CRE.SEMANTIC_DIFF"
    http_status = 400


@dataclass(frozen=True, slots=True)
class SemanticValueDelta:
    field: str
    before_present: bool
    before: object
    after_present: bool
    after: object

    def to_dict(self) -> dict[str, object]:
        return {
            "field": self.field,
            "before_present": self.before_present,
            "before": self.before,
            "after_present": self.after_present,
            "after": self.after,
        }


@dataclass(frozen=True, slots=True)
class SemanticChange:
    change_id: str
    entity: str
    domain: str
    action: str
    subject_id: str
    summary: str
    source_id: str | None
    target_id: str | None
    deltas: tuple[SemanticValueDelta, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "change_id": self.change_id,
            "entity": self.entity,
            "domain": self.domain,
            "action": self.action,
            "subject_id": self.subject_id,
            "summary": self.summary,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "deltas": [delta.to_dict() for delta in self.deltas],
        }


@dataclass(frozen=True, slots=True)
class SemanticDiff:
    project_id: str
    base_revision: int
    target_revision: int
    base_digest: str
    target_digest: str
    changes: tuple[SemanticChange, ...]
    counts_by_domain: tuple[tuple[str, int], ...]
    counts_by_action: tuple[tuple[str, int], ...]
    ignored_change_count: int
    digest: str

    @property
    def is_noop(self) -> bool:
        return not self.changes

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SEMANTIC_DIFF_SCHEMA,
            "schema_version": SEMANTIC_DIFF_VERSION,
            "project_id": self.project_id,
            "base_revision": self.base_revision,
            "target_revision": self.target_revision,
            "base_digest": self.base_digest,
            "target_digest": self.target_digest,
            "changes": [change.to_dict() for change in self.changes],
            "counts_by_domain": [
                {"domain": domain, "count": count}
                for domain, count in self.counts_by_domain
            ],
            "counts_by_action": [
                {"action": action, "count": count}
                for action, count in self.counts_by_action
            ],
            "ignored_change_count": self.ignored_change_count,
            "digest": self.digest,
        }

    def changes_for_domain(self, domain: str) -> tuple[SemanticChange, ...]:
        if not isinstance(domain, str) or domain not in NODE_KINDS:
            _fail("unknown semantic domain", reason="domain", domain=domain)
        return tuple(change for change in self.changes if change.domain == domain)

    def changes_for_subject(self, subject_id: str) -> tuple[SemanticChange, ...]:
        if not isinstance(subject_id, str) or not subject_id:
            _fail("subject_id must be non-empty text", reason="subject")
        return tuple(
            change
            for change in self.changes
            if change.subject_id == subject_id
            or change.source_id == subject_id
            or change.target_id == subject_id
        )

    def summaries(self) -> tuple[str, ...]:
        return tuple(change.summary for change in self.changes)


def _fail(message: str, *, reason: str, **context: object) -> NoReturn:
    raise SemanticDiffError(message, context={"reason": reason, **context})


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
        _fail("semantic diff contains non-canonical JSON data", reason="json_type")
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


def _scalar(value: object, *, field: str) -> object:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            _fail(f"{field} must be finite", reason="malformed", field=field)
        return value
    _fail(f"{field} must be a JSON scalar", reason="malformed", field=field)


def _validated_snapshot(value: DesignGraphSnapshot, *, field: str) -> DesignGraphSnapshot:
    if not isinstance(value, DesignGraphSnapshot):
        _fail(f"{field} must be DesignGraphSnapshot", reason="malformed", field=field)
    try:
        parsed = parse_design_graph(value.serialize())
    except Exception as exc:
        raise SemanticDiffError(
            f"{field} failed design-graph validation",
            context={
                "reason": "graph_integrity",
                "field": field,
                "exception": type(exc).__name__,
            },
        ) from exc
    if parsed != value:
        _fail(
            f"{field} canonical graph does not round-trip",
            reason="graph_integrity",
            field=field,
        )
    return parsed


def _visible_attributes(
    attributes: Mapping[str, object],
) -> dict[str, object]:
    return {
        key: value
        for key, value in attributes.items()
        if key not in IGNORED_ATTRIBUTES
    }


def _attribute_deltas(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> tuple[SemanticValueDelta, ...]:
    fields = sorted(set(before) | set(after))
    result: list[SemanticValueDelta] = []
    for field in fields:
        before_present = field in before
        after_present = field in after
        before_value = before.get(field)
        after_value = after.get(field)
        if before_present == after_present and before_value == after_value:
            continue
        result.append(
            SemanticValueDelta(
                field=f"attribute.{field}",
                before_present=before_present,
                before=_scalar(before_value, field=field) if before_present else None,
                after_present=after_present,
                after=_scalar(after_value, field=field) if after_present else None,
            )
        )
    return tuple(result)


def _node_presence_deltas(
    node: DesignGraphNode,
    *,
    before_present: bool,
) -> tuple[SemanticValueDelta, ...]:
    deltas = [
        SemanticValueDelta(
            field="kind",
            before_present=before_present,
            before=node.kind if before_present else None,
            after_present=not before_present,
            after=None if before_present else node.kind,
        ),
        SemanticValueDelta(
            field="label",
            before_present=before_present,
            before=node.label if before_present else None,
            after_present=not before_present,
            after=None if before_present else node.label,
        ),
    ]
    for key, value in sorted(_visible_attributes(node.attribute_map()).items()):
        deltas.append(
            SemanticValueDelta(
                field=f"attribute.{key}",
                before_present=before_present,
                before=value if before_present else None,
                after_present=not before_present,
                after=None if before_present else value,
            )
        )
    return tuple(deltas)


def _entity_phrase(kind: str, label: str) -> str:
    return f'{kind} "{label}"'


def _clean_summary(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_SUMMARY_CHARS:
        _fail("semantic summary exceeds contract", reason="summary")
    if any(ord(character) < 32 and character not in "\t" for character in value):
        _fail("semantic summary contains control character", reason="summary")
    return value


def _change(
    *,
    entity: str,
    domain: str,
    action: str,
    subject_id: str,
    summary: str,
    source_id: str | None = None,
    target_id: str | None = None,
    deltas: tuple[SemanticValueDelta, ...] = (),
) -> SemanticChange:
    if entity not in {"node", "relationship"}:
        _fail("unsupported semantic entity", reason="contract", entity=entity)
    if domain not in NODE_KINDS:
        _fail("unsupported semantic domain", reason="domain", domain=domain)
    if action not in CHANGE_ACTIONS:
        _fail("unsupported semantic action", reason="contract", action=action)
    if not isinstance(subject_id, str) or not subject_id:
        _fail("semantic subject_id is invalid", reason="contract")
    for delta in deltas:
        if not isinstance(delta, SemanticValueDelta):
            _fail("semantic delta has invalid type", reason="contract")
    payload = {
        "entity": entity,
        "domain": domain,
        "action": action,
        "subject_id": subject_id,
        "summary": _clean_summary(summary),
        "source_id": source_id,
        "target_id": target_id,
        "deltas": [delta.to_dict() for delta in deltas],
    }
    return SemanticChange(
        change_id=f"chg_{_digest(payload)[:24]}",
        entity=entity,
        domain=domain,
        action=action,
        subject_id=subject_id,
        summary=str(payload["summary"]),
        source_id=source_id,
        target_id=target_id,
        deltas=deltas,
    )


def _node_changes(
    base: DesignGraphSnapshot,
    target: DesignGraphSnapshot,
) -> tuple[list[SemanticChange], int]:
    changes: list[SemanticChange] = []
    ignored = 0
    before = base.node_map()
    after = target.node_map()

    for node_id in sorted(set(before) - set(after)):
        node = before[node_id]
        changes.append(
            _change(
                entity="node",
                domain=node.kind,
                action="node_removed",
                subject_id=node.node_id,
                summary=f"Removed {_entity_phrase(node.kind, node.label)}.",
                deltas=_node_presence_deltas(node, before_present=True),
            )
        )

    for node_id in sorted(set(after) - set(before)):
        node = after[node_id]
        changes.append(
            _change(
                entity="node",
                domain=node.kind,
                action="node_added",
                subject_id=node.node_id,
                summary=f"Added {_entity_phrase(node.kind, node.label)}.",
                deltas=_node_presence_deltas(node, before_present=False),
            )
        )

    for node_id in sorted(set(before) & set(after)):
        old = before[node_id]
        new = after[node_id]

        if old.kind != new.kind:
            changes.append(
                _change(
                    entity="node",
                    domain=new.kind,
                    action="node_kind_changed",
                    subject_id=node_id,
                    summary=(
                        f'Changed "{new.label}" from {old.kind} to {new.kind}.'
                    ),
                    deltas=(
                        SemanticValueDelta(
                            field="kind",
                            before_present=True,
                            before=old.kind,
                            after_present=True,
                            after=new.kind,
                        ),
                    ),
                )
            )

        if old.label != new.label:
            changes.append(
                _change(
                    entity="node",
                    domain=new.kind,
                    action="node_renamed",
                    subject_id=node_id,
                    summary=(
                        f'Renamed {new.kind} "{old.label}" to "{new.label}".'
                    ),
                    deltas=(
                        SemanticValueDelta(
                            field="label",
                            before_present=True,
                            before=old.label,
                            after_present=True,
                            after=new.label,
                        ),
                    ),
                )
            )

        old_attrs = old.attribute_map()
        new_attrs = new.attribute_map()
        for ignored_key in IGNORED_ATTRIBUTES:
            if old_attrs.get(ignored_key) != new_attrs.get(ignored_key):
                if ignored_key in old_attrs or ignored_key in new_attrs:
                    ignored += 1
        visible_old = _visible_attributes(old_attrs)
        visible_new = _visible_attributes(new_attrs)
        deltas = _attribute_deltas(visible_old, visible_new)
        if deltas:
            fields = ", ".join(
                delta.field.removeprefix("attribute.").replace("_", " ")
                for delta in deltas
            )
            changes.append(
                _change(
                    entity="node",
                    domain=new.kind,
                    action="node_attributes_changed",
                    subject_id=node_id,
                    summary=(
                        f'Updated {new.kind} "{new.label}": {fields}.'
                    ),
                    deltas=deltas,
                )
            )

    return changes, ignored


def _relationship_key(edge: DesignGraphEdge) -> tuple[str, str, str]:
    return (edge.kind, edge.source, edge.target)


def _semantic_edges(
    graph: DesignGraphSnapshot,
) -> dict[tuple[str, str, str], DesignGraphEdge]:
    result: dict[tuple[str, str, str], DesignGraphEdge] = {}
    for edge in graph.edges:
        key = _relationship_key(edge)
        if key in result:
            _fail(
                "design graph contains duplicate semantic relationship",
                reason="ambiguous_relationship",
                kind=edge.kind,
                source=edge.source,
                target=edge.target,
            )
        result[key] = edge
    return result


def _relationship_subject(key: tuple[str, str, str]) -> str:
    return f"rel_{_digest(list(key))[:24]}"


def _relationship_summary(
    *,
    edge: DesignGraphEdge,
    nodes: Mapping[str, DesignGraphNode],
    added: bool,
) -> str:
    source = nodes[edge.source]
    target = nodes[edge.target]
    positive, negative = _EDGE_VERBS[edge.kind]
    verb = positive if added else negative
    source_phrase = _entity_phrase(source.kind, source.label)
    source_phrase = source_phrase[:1].upper() + source_phrase[1:]
    return (
        f'{source_phrase} '
        f'{verb} {_entity_phrase(target.kind, target.label)}.'
    )


def _relationship_changes(
    base: DesignGraphSnapshot,
    target: DesignGraphSnapshot,
) -> tuple[list[SemanticChange], int]:
    changes: list[SemanticChange] = []
    ignored = 0
    before = _semantic_edges(base)
    after = _semantic_edges(target)
    base_nodes = base.node_map()
    target_nodes = target.node_map()

    for key in sorted(set(before) - set(after)):
        edge = before[key]
        source = base_nodes[edge.source]
        changes.append(
            _change(
                entity="relationship",
                domain=source.kind,
                action="relationship_removed",
                subject_id=_relationship_subject(key),
                source_id=edge.source,
                target_id=edge.target,
                summary=_relationship_summary(
                    edge=edge,
                    nodes=base_nodes,
                    added=False,
                ),
            )
        )

    for key in sorted(set(after) - set(before)):
        edge = after[key]
        source = target_nodes[edge.source]
        changes.append(
            _change(
                entity="relationship",
                domain=source.kind,
                action="relationship_added",
                subject_id=_relationship_subject(key),
                source_id=edge.source,
                target_id=edge.target,
                summary=_relationship_summary(
                    edge=edge,
                    nodes=target_nodes,
                    added=True,
                ),
            )
        )

    for key in sorted(set(before) & set(after)):
        old = before[key]
        new = after[key]
        if old.edge_id != new.edge_id:
            ignored += 1

        old_attrs = old.attribute_map()
        new_attrs = new.attribute_map()
        for ignored_key in IGNORED_ATTRIBUTES:
            if old_attrs.get(ignored_key) != new_attrs.get(ignored_key):
                if ignored_key in old_attrs or ignored_key in new_attrs:
                    ignored += 1
        deltas = _attribute_deltas(
            _visible_attributes(old_attrs),
            _visible_attributes(new_attrs),
        )
        if deltas:
            source = target_nodes[new.source]
            target_node = target_nodes[new.target]
            fields = ", ".join(
                delta.field.removeprefix("attribute.").replace("_", " ")
                for delta in deltas
            )
            changes.append(
                _change(
                    entity="relationship",
                    domain=source.kind,
                    action="relationship_attributes_changed",
                    subject_id=_relationship_subject(key),
                    source_id=new.source,
                    target_id=new.target,
                    summary=(
                        f'Updated {new.kind} relationship from '
                        f'{_entity_phrase(source.kind, source.label)} to '
                        f'{_entity_phrase(target_node.kind, target_node.label)}: '
                        f'{fields}.'
                    ),
                    deltas=deltas,
                )
            )

    return changes, ignored


def _counts(
    changes: tuple[SemanticChange, ...],
    *,
    field: str,
) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for change in changes:
        key = getattr(change, field)
        counts[key] = counts.get(key, 0) + 1
    return tuple(sorted(counts.items()))


def _diff_payload(
    *,
    project_id: str,
    base_revision: int,
    target_revision: int,
    base_digest: str,
    target_digest: str,
    changes: tuple[SemanticChange, ...],
    counts_by_domain: tuple[tuple[str, int], ...],
    counts_by_action: tuple[tuple[str, int], ...],
    ignored_change_count: int,
) -> dict[str, object]:
    return {
        "schema": SEMANTIC_DIFF_SCHEMA,
        "schema_version": SEMANTIC_DIFF_VERSION,
        "project_id": project_id,
        "base_revision": base_revision,
        "target_revision": target_revision,
        "base_digest": base_digest,
        "target_digest": target_digest,
        "changes": [change.to_dict() for change in changes],
        "counts_by_domain": [
            {"domain": domain, "count": count}
            for domain, count in counts_by_domain
        ],
        "counts_by_action": [
            {"action": action, "count": count}
            for action, count in counts_by_action
        ],
        "ignored_change_count": ignored_change_count,
    }


def semantic_diff(
    base: DesignGraphSnapshot,
    target: DesignGraphSnapshot,
) -> SemanticDiff:
    """Return deterministic user-meaningful graph changes from base to target."""

    checked_base = _validated_snapshot(base, field="base")
    checked_target = _validated_snapshot(target, field="target")
    if checked_base.project_id != checked_target.project_id:
        _fail(
            "cannot diff design graphs from different projects",
            reason="project_mismatch",
            base_project=checked_base.project_id,
            target_project=checked_target.project_id,
        )

    node_changes, node_ignored = _node_changes(checked_base, checked_target)
    relationship_changes, relation_ignored = _relationship_changes(
        checked_base,
        checked_target,
    )
    all_changes = node_changes + relationship_changes
    if len(all_changes) > MAX_CHANGES:
        _fail(
            "semantic change count exceeds configured bound",
            reason="bound",
            maximum=MAX_CHANGES,
        )
    changes = tuple(
        sorted(
            all_changes,
            key=lambda change: (
                change.domain,
                _ACTION_ORDER[change.action],
                change.subject_id,
                change.change_id,
            ),
        )
    )
    ignored = node_ignored + relation_ignored
    if checked_base.source_plan_digest != checked_target.source_plan_digest:
        ignored += 1

    counts_by_domain = _counts(changes, field="domain")
    counts_by_action = _counts(changes, field="action")
    payload = _diff_payload(
        project_id=checked_base.project_id,
        base_revision=checked_base.revision,
        target_revision=checked_target.revision,
        base_digest=checked_base.digest,
        target_digest=checked_target.digest,
        changes=changes,
        counts_by_domain=counts_by_domain,
        counts_by_action=counts_by_action,
        ignored_change_count=ignored,
    )
    encoded = _canonical_json_bytes(payload)
    if len(encoded) > MAX_SERIALIZED_BYTES:
        _fail("semantic diff exceeds serialized byte bound", reason="bound")
    return SemanticDiff(
        project_id=checked_base.project_id,
        base_revision=checked_base.revision,
        target_revision=checked_target.revision,
        base_digest=checked_base.digest,
        target_digest=checked_target.digest,
        changes=changes,
        counts_by_domain=counts_by_domain,
        counts_by_action=counts_by_action,
        ignored_change_count=ignored,
        digest=hashlib.sha256(encoded).hexdigest(),
    )


def validate_semantic_diff(
    diff: SemanticDiff,
    base: DesignGraphSnapshot,
    target: DesignGraphSnapshot,
) -> None:
    """Recompute the entire semantic diff and reject forged summaries/evidence."""

    if not isinstance(diff, SemanticDiff):
        _fail("diff must be SemanticDiff", reason="malformed")
    expected = semantic_diff(base, target)
    if diff != expected:
        _fail("semantic diff derived identity mismatch", reason="digest_mismatch")


def serialize_semantic_diff(
    diff: SemanticDiff,
    base: DesignGraphSnapshot,
    target: DesignGraphSnapshot,
) -> str:
    validate_semantic_diff(diff, base, target)
    raw = _canonical_json_bytes(diff.to_dict())
    if len(raw) > MAX_SERIALIZED_BYTES:
        _fail("serialized semantic diff exceeds byte bound", reason="bound")
    return raw.decode("ascii")


def render_semantic_summary(
    diff: SemanticDiff,
    *,
    limit: int | None = None,
) -> tuple[str, ...]:
    """Return bounded human-readable summaries in canonical change order."""

    if not isinstance(diff, SemanticDiff):
        _fail("diff must be SemanticDiff", reason="malformed")
    if limit is None:
        selected = diff.changes
    else:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            _fail("summary limit must be a non-negative integer", reason="malformed")
        selected = diff.changes[:limit]
    return tuple(change.summary for change in selected)


__all__ = [
    "CHANGE_ACTIONS",
    "IGNORED_ATTRIBUTES",
    "MAX_CHANGES",
    "MAX_SERIALIZED_BYTES",
    "SEMANTIC_DIFF_SCHEMA",
    "SEMANTIC_DIFF_VERSION",
    "SemanticChange",
    "SemanticDiff",
    "SemanticDiffError",
    "SemanticValueDelta",
    "render_semantic_summary",
    "semantic_diff",
    "serialize_semantic_diff",
    "validate_semantic_diff",
]
