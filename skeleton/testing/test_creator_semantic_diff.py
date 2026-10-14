"""Regression coverage for semantic creator graph diffs (#807 B016)."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from skeleton.forge.creator.design_graph import (
    DesignGraphEdge,
    DesignGraphNode,
    build_design_graph,
)
from skeleton.forge.creator.semantic_diff import (
    CHANGE_ACTIONS,
    IGNORED_ATTRIBUTES,
    SEMANTIC_DIFF_SCHEMA,
    SEMANTIC_DIFF_VERSION,
    SemanticDiffError,
    render_semantic_summary,
    semantic_diff,
    serialize_semantic_diff,
    validate_semantic_diff,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _nodes(
    *,
    scene_label: str = "Harbor",
    mechanic_label: str = "Stealth Loop",
    scene_attributes: dict[str, object] | None = None,
    mechanic_attributes: dict[str, object] | None = None,
) -> tuple[DesignGraphNode, ...]:
    return (
        DesignGraphNode(
            "asset_boat",
            "asset",
            "Patrol Boat",
            tuple(sorted({"uri": "asset://boat"}.items())),
        ),
        DesignGraphNode(
            "mechanic_stealth",
            "mechanic",
            mechanic_label,
            tuple(
                sorted(
                    (
                        mechanic_attributes
                        or {
                            "cooldown": 2,
                            "source_path": "nodes.mechanic_stealth",
                        }
                    ).items()
                )
            ),
        ),
        DesignGraphNode(
            "narrative_escape",
            "narrative",
            "Escape Route",
        ),
        DesignGraphNode(
            "scene_harbor",
            "scene",
            scene_label,
            tuple(
                sorted(
                    (
                        scene_attributes
                        or {
                            "lighting": "night",
                            "source_path": "nodes.scene_harbor",
                        }
                    ).items()
                )
            ),
        ),
    )


def _edges(
    *,
    dependency_id: str = "depends:mechanic_stealth:scene_harbor",
    dependency_attributes: dict[str, object] | None = None,
    include_asset_reference: bool = True,
) -> tuple[DesignGraphEdge, ...]:
    rows = [
        DesignGraphEdge(
            dependency_id,
            "depends_on",
            "mechanic_stealth",
            "scene_harbor",
            tuple(sorted((dependency_attributes or {}).items())),
        ),
    ]
    if include_asset_reference:
        rows.append(
            DesignGraphEdge(
                "references:narrative_escape:asset_boat",
                "references",
                "narrative_escape",
                "asset_boat",
            )
        )
    return tuple(rows)


def _graph(
    *,
    revision: int = 1,
    nodes: tuple[DesignGraphNode, ...] | None = None,
    edges: tuple[DesignGraphEdge, ...] | None = None,
    source_plan_digest: str | None = None,
):
    return build_design_graph(
        project_id="project_demo",
        revision=revision,
        nodes=_nodes() if nodes is None else nodes,
        edges=_edges() if edges is None else edges,
        source_plan_digest=source_plan_digest,
    )


def test_schema_and_action_contract_are_stable() -> None:
    assert SEMANTIC_DIFF_SCHEMA == "creator.semantic_diff.v1"
    assert SEMANTIC_DIFF_VERSION == 1
    assert CHANGE_ACTIONS == (
        "node_removed",
        "node_added",
        "node_kind_changed",
        "node_renamed",
        "node_attributes_changed",
        "relationship_removed",
        "relationship_added",
        "relationship_attributes_changed",
    )
    assert IGNORED_ATTRIBUTES == frozenset({"source_path"})


def test_identical_graph_is_semantic_noop() -> None:
    graph = _graph()

    diff = semantic_diff(graph, graph)

    assert diff.is_noop is True
    assert diff.changes == ()
    assert diff.counts_by_domain == ()
    assert diff.counts_by_action == ()
    assert diff.ignored_change_count == 0
    assert diff.base_digest == diff.target_digest
    assert len(diff.digest) == 64


def test_revision_only_change_is_semantic_noop() -> None:
    base = _graph(revision=1)
    target = _graph(revision=2)

    diff = semantic_diff(base, target)

    assert diff.is_noop is True
    assert diff.base_digest != diff.target_digest
    assert diff.base_revision == 1
    assert diff.target_revision == 2


def test_source_plan_digest_change_is_ignored_metadata() -> None:
    base = _graph(source_plan_digest=_sha("plan-a"))
    target = _graph(source_plan_digest=_sha("plan-b"))

    diff = semantic_diff(base, target)

    assert diff.is_noop is True
    assert diff.ignored_change_count == 1


def test_source_path_only_change_is_not_user_facing() -> None:
    base = _graph()
    target = _graph(
        revision=2,
        nodes=_nodes(
            scene_attributes={
                "lighting": "night",
                "source_path": "new/internal/path.py",
            }
        ),
    )

    diff = semantic_diff(base, target)

    assert diff.is_noop is True
    assert diff.ignored_change_count == 1
    raw = serialize_semantic_diff(diff, base, target)
    assert "new/internal/path.py" not in raw
    assert "nodes.scene_harbor" not in raw


def test_edge_id_churn_does_not_create_fake_relationship_change() -> None:
    base = _graph()
    target = _graph(
        revision=2,
        edges=_edges(dependency_id="depends:replacement-id"),
    )

    diff = semantic_diff(base, target)

    assert diff.is_noop is True
    assert diff.ignored_change_count == 1
    assert "replacement-id" not in serialize_semantic_diff(diff, base, target)


def test_scene_rename_is_meaningful_and_preserves_label_case() -> None:
    base = _graph()
    target = _graph(
        revision=2,
        nodes=_nodes(scene_label="Harbor Night Raid"),
    )

    diff = semantic_diff(base, target)
    changes = diff.changes_for_domain("scene")

    assert len(changes) == 1
    change = changes[0]
    assert change.action == "node_renamed"
    assert change.subject_id == "scene_harbor"
    assert change.summary == 'Renamed scene "Harbor" to "Harbor Night Raid".'
    assert change.deltas[0].before == "Harbor"
    assert change.deltas[0].after == "Harbor Night Raid"


def test_mechanic_attribute_change_reports_semantic_field() -> None:
    base = _graph()
    target = _graph(
        revision=2,
        nodes=_nodes(
            mechanic_attributes={
                "cooldown": 4,
                "source_path": "nodes.mechanic_stealth",
            }
        ),
    )

    diff = semantic_diff(base, target)
    changes = diff.changes_for_domain("mechanic")

    assert len(changes) == 1
    change = changes[0]
    assert change.action == "node_attributes_changed"
    assert change.summary == 'Updated mechanic "Stealth Loop": cooldown.'
    assert len(change.deltas) == 1
    delta = change.deltas[0]
    assert delta.field == "attribute.cooldown"
    assert delta.before == 2
    assert delta.after == 4


def test_added_asset_is_reported_as_game_entity_not_file() -> None:
    base = _graph()
    extra = DesignGraphNode(
        "asset_keycard",
        "asset",
        "Security Keycard",
        (("uri", "asset://keycard"),),
    )
    target = _graph(
        revision=2,
        nodes=(*_nodes(), extra),
    )

    diff = semantic_diff(base, target)
    changes = diff.changes_for_domain("asset")

    assert len(changes) == 1
    assert changes[0].action == "node_added"
    assert changes[0].summary == 'Added asset "Security Keycard".'
    assert changes[0].subject_id == "asset_keycard"
    assert "file" not in changes[0].summary.lower()


def test_removed_mechanic_is_explicit() -> None:
    base = _graph()
    target_nodes = tuple(
        node for node in _nodes() if node.node_id != "mechanic_stealth"
    )
    target_edges = tuple(
        edge for edge in _edges() if edge.source != "mechanic_stealth"
    )
    target = _graph(
        revision=2,
        nodes=target_nodes,
        edges=target_edges,
    )

    diff = semantic_diff(base, target)
    mechanic = diff.changes_for_domain("mechanic")

    assert any(change.action == "node_removed" for change in mechanic)
    assert any(
        change.summary == 'Removed mechanic "Stealth Loop".'
        for change in mechanic
    )


def test_kind_change_is_reported_without_losing_identity() -> None:
    base = _graph()
    changed = tuple(
        DesignGraphNode(
            node.node_id,
            "system" if node.node_id == "mechanic_stealth" else node.kind,
            node.label,
            node.attributes,
        )
        for node in _nodes()
    )
    target = _graph(revision=2, nodes=changed)

    diff = semantic_diff(base, target)
    change = next(
        item for item in diff.changes
        if item.action == "node_kind_changed"
    )

    assert change.subject_id == "mechanic_stealth"
    assert change.domain == "system"
    assert change.summary == 'Changed "Stealth Loop" from mechanic to system.'


def test_relationship_addition_uses_domain_language() -> None:
    base = _graph(
        edges=_edges(include_asset_reference=False),
    )
    target = _graph(
        revision=2,
        edges=_edges(include_asset_reference=True),
    )

    diff = semantic_diff(base, target)
    relationship = next(
        change for change in diff.changes
        if change.action == "relationship_added"
    )

    assert relationship.domain == "narrative"
    assert relationship.source_id == "narrative_escape"
    assert relationship.target_id == "asset_boat"
    assert relationship.summary == (
        'Narrative "Escape Route" now references asset "Patrol Boat".'
    )


def test_relationship_removal_is_meaningful() -> None:
    base = _graph()
    target = _graph(
        revision=2,
        edges=_edges(include_asset_reference=False),
    )

    diff = semantic_diff(base, target)
    relationship = next(
        change for change in diff.changes
        if change.action == "relationship_removed"
    )

    assert relationship.summary == (
        'Narrative "Escape Route" no longer references asset "Patrol Boat".'
    )


def test_relationship_attribute_change_is_reported() -> None:
    base = _graph(
        edges=_edges(dependency_attributes={"weight": 1}),
    )
    target = _graph(
        revision=2,
        edges=_edges(dependency_attributes={"weight": 3}),
    )

    diff = semantic_diff(base, target)
    relationship = next(
        change for change in diff.changes
        if change.action == "relationship_attributes_changed"
    )

    assert relationship.domain == "mechanic"
    assert relationship.summary == (
        'Updated depends_on relationship from mechanic "Stealth Loop" '
        'to scene "Harbor": weight.'
    )
    assert relationship.deltas[0].before == 1
    assert relationship.deltas[0].after == 3


def test_relationship_source_path_attribute_is_ignored() -> None:
    base = _graph(
        edges=_edges(
            dependency_attributes={"source_path": "graph/old"}
        ),
    )
    target = _graph(
        revision=2,
        edges=_edges(
            dependency_attributes={"source_path": "graph/new"}
        ),
    )

    diff = semantic_diff(base, target)

    assert diff.is_noop is True
    assert diff.ignored_change_count == 1


def test_duplicate_semantic_relationship_is_ambiguous() -> None:
    duplicate_edges = (
        *_edges(include_asset_reference=False),
        DesignGraphEdge(
            "depends:second-id",
            "depends_on",
            "mechanic_stealth",
            "scene_harbor",
        ),
    )
    graph = _graph(edges=duplicate_edges)

    with pytest.raises(SemanticDiffError) as caught:
        semantic_diff(graph, graph)

    assert caught.value.context["reason"] == "ambiguous_relationship"


def test_different_projects_cannot_be_diffed() -> None:
    base = _graph()
    target = build_design_graph(
        project_id="other_project",
        revision=2,
        nodes=_nodes(),
        edges=_edges(),
    )

    with pytest.raises(SemanticDiffError) as caught:
        semantic_diff(base, target)

    assert caught.value.context["reason"] == "project_mismatch"


def test_declaration_order_does_not_change_semantic_diff() -> None:
    base = _graph()
    target = _graph(
        revision=2,
        nodes=_nodes(scene_label="Harbor Night Raid"),
    )
    reordered_base = build_design_graph(
        project_id=base.project_id,
        revision=base.revision,
        nodes=reversed(base.nodes),
        edges=reversed(base.edges),
    )
    reordered_target = build_design_graph(
        project_id=target.project_id,
        revision=target.revision,
        nodes=reversed(target.nodes),
        edges=reversed(target.edges),
    )

    first = semantic_diff(base, target)
    second = semantic_diff(reordered_base, reordered_target)

    assert first == second


def test_counts_group_changes_by_domain_and_action() -> None:
    base = _graph()
    extra = DesignGraphNode(
        "asset_keycard",
        "asset",
        "Security Keycard",
    )
    target = _graph(
        revision=2,
        nodes=(*_nodes(scene_label="Harbor Night Raid"), extra),
        edges=_edges(include_asset_reference=False),
    )

    diff = semantic_diff(base, target)

    domains = dict(diff.counts_by_domain)
    actions = dict(diff.counts_by_action)
    assert domains["scene"] == 1
    assert domains["asset"] == 1
    assert domains["narrative"] == 1
    assert actions["node_renamed"] == 1
    assert actions["node_added"] == 1
    assert actions["relationship_removed"] == 1


def test_subject_query_includes_relationships_touching_node() -> None:
    base = _graph(edges=_edges(include_asset_reference=False))
    target = _graph(revision=2, edges=_edges())

    diff = semantic_diff(base, target)
    touched = diff.changes_for_subject("asset_boat")

    assert len(touched) == 1
    assert touched[0].action == "relationship_added"
    assert touched[0].target_id == "asset_boat"


def test_invalid_domain_and_subject_queries_fail_closed() -> None:
    diff = semantic_diff(_graph(), _graph())

    with pytest.raises(SemanticDiffError):
        diff.changes_for_domain("filesystem")

    with pytest.raises(SemanticDiffError):
        diff.changes_for_subject("")


def test_render_summary_obeys_canonical_order_and_limit() -> None:
    base = _graph()
    target = _graph(
        revision=2,
        nodes=_nodes(scene_label="Harbor Night Raid"),
        edges=_edges(include_asset_reference=False),
    )
    diff = semantic_diff(base, target)

    assert render_semantic_summary(diff) == diff.summaries()
    assert render_semantic_summary(diff, limit=1) == diff.summaries()[:1]
    assert render_semantic_summary(diff, limit=0) == ()

    with pytest.raises(SemanticDiffError):
        render_semantic_summary(diff, limit=True)


def test_diff_serialization_is_canonical_and_digest_bound() -> None:
    base = _graph()
    target = _graph(
        revision=2,
        nodes=_nodes(scene_label="Harbor Night Raid"),
    )
    diff = semantic_diff(base, target)

    raw = serialize_semantic_diff(diff, base, target)

    assert raw == json.dumps(
        json.loads(raw),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert json.loads(raw)["digest"] == diff.digest
    assert len(diff.digest) == 64


def test_tampered_summary_or_digest_fails_revalidation() -> None:
    base = _graph()
    target = _graph(
        revision=2,
        nodes=_nodes(scene_label="Harbor Night Raid"),
    )
    diff = semantic_diff(base, target)
    changed = replace(
        diff.changes[0],
        summary="Raw file changed.",
    )

    with pytest.raises(SemanticDiffError) as caught:
        validate_semantic_diff(
            replace(diff, changes=(changed,)),
            base,
            target,
        )
    assert caught.value.context["reason"] == "digest_mismatch"

    with pytest.raises(SemanticDiffError):
        validate_semantic_diff(
            replace(diff, digest="0" * 64),
            base,
            target,
        )


def test_attribute_addition_and_removal_preserve_presence_information() -> None:
    base = _graph(
        nodes=_nodes(
            scene_attributes={
                "lighting": "night",
                "weather": "rain",
                "source_path": "nodes.scene_harbor",
            }
        )
    )
    target = _graph(
        revision=2,
        nodes=_nodes(
            scene_attributes={
                "lighting": "dawn",
                "difficulty": 3,
                "source_path": "nodes.scene_harbor",
            }
        ),
    )

    diff = semantic_diff(base, target)
    change = next(
        item for item in diff.changes
        if item.action == "node_attributes_changed"
    )
    by_field = {delta.field: delta for delta in change.deltas}

    assert by_field["attribute.weather"].before_present is True
    assert by_field["attribute.weather"].after_present is False
    assert by_field["attribute.difficulty"].before_present is False
    assert by_field["attribute.difficulty"].after_present is True
    assert by_field["attribute.lighting"].before == "night"
    assert by_field["attribute.lighting"].after == "dawn"


def test_semantic_change_ids_are_stable_across_edge_id_churn() -> None:
    base = _graph(edges=_edges(include_asset_reference=False))
    target_a = _graph(revision=2, edges=_edges())
    target_b = _graph(
        revision=2,
        edges=(
            DesignGraphEdge(
                "depends:different",
                "depends_on",
                "mechanic_stealth",
                "scene_harbor",
            ),
            DesignGraphEdge(
                "references:different",
                "references",
                "narrative_escape",
                "asset_boat",
            ),
        ),
    )

    first = semantic_diff(base, target_a)
    second = semantic_diff(base, target_b)

    first_added = next(
        change for change in first.changes
        if change.action == "relationship_added"
    )
    second_added = next(
        change for change in second.changes
        if change.action == "relationship_added"
    )
    assert first_added.change_id == second_added.change_id
    assert first_added.subject_id == second_added.subject_id
