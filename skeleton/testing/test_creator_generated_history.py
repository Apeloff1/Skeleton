"""Regression coverage for generated-state undo/redo history (#807 B018)."""

from __future__ import annotations

from dataclasses import replace
import ast
import json
from pathlib import Path

import pytest

from skeleton.forge.creator.design_graph import (
    DesignGraphEdge,
    DesignGraphNode,
    build_design_graph,
)
from skeleton.forge.creator.generated_history import (
    HISTORY_SCHEMA,
    HISTORY_VERSION,
    GeneratedHistoryError,
    GeneratedStateHistory,
    StateTransition,
    StoredSnapshot,
    create_generated_history,
    current_generated_snapshot,
    parse_generated_history,
    record_generated_transition,
    redo_generated_state,
    serialize_generated_history,
    undo_generated_state,
    validate_generated_history,
)
from skeleton.forge.creator.semantic_diff import semantic_diff


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "forge"
    / "creator"
    / "generated_history.py"
)


def _graph(
    *,
    revision: int,
    scene_label: str,
    cooldown: int,
    source_path: str = "nodes.scene_harbor",
    project_id: str = "project_demo",
):
    return build_design_graph(
        project_id=project_id,
        revision=revision,
        nodes=(
            DesignGraphNode(
                "asset_boat",
                "asset",
                "Patrol Boat",
                (("uri", "asset://boat"),),
            ),
            DesignGraphNode(
                "mechanic_stealth",
                "mechanic",
                "Stealth Loop",
                (("cooldown", cooldown),),
            ),
            DesignGraphNode(
                "scene_harbor",
                "scene",
                scene_label,
                (
                    ("lighting", "night"),
                    ("source_path", source_path),
                ),
            ),
        ),
        edges=(
            DesignGraphEdge(
                "depends:mechanic_stealth:scene_harbor",
                "depends_on",
                "mechanic_stealth",
                "scene_harbor",
            ),
            DesignGraphEdge(
                "references:scene_harbor:asset_boat",
                "references",
                "scene_harbor",
                "asset_boat",
            ),
        ),
    )


def _a():
    return _graph(
        revision=1,
        scene_label="Harbor",
        cooldown=2,
    )


def _b():
    return _graph(
        revision=2,
        scene_label="Harbor Night Raid",
        cooldown=2,
    )


def _c():
    return _graph(
        revision=3,
        scene_label="Harbor Night Raid",
        cooldown=4,
    )


def _d():
    return _graph(
        revision=4,
        scene_label="Harbor Dawn",
        cooldown=3,
    )


def test_schema_and_version_are_stable() -> None:
    assert HISTORY_SCHEMA == "creator.generated_history.v1"
    assert HISTORY_VERSION == 1


def test_create_history_anchors_exact_initial_snapshot() -> None:
    initial = _a()

    history = create_generated_history(initial)

    assert history.project_id == initial.project_id
    assert history.revision == 0
    assert history.current_digest == initial.digest
    assert history.undo_stack == ()
    assert history.redo_stack == ()
    assert history.can_undo is False
    assert history.can_redo is False
    assert len(history.snapshots) == 1
    assert len(history.transitions) == 0
    assert current_generated_snapshot(history) == initial
    assert len(history.digest) == 64
    validate_generated_history(history)


def test_record_transition_binds_b016_semantic_diff() -> None:
    initial = _a()
    target = _b()
    history = create_generated_history(initial)

    history, transition = record_generated_transition(
        history,
        initial,
        target,
        label="Rename harbor scene",
    )

    expected_diff = semantic_diff(initial, target)
    assert transition.semantic_diff_digest == expected_diff.digest
    assert transition.change_count == len(expected_diff.changes)
    assert transition.summaries == expected_diff.summaries()
    assert transition.before_digest == initial.digest
    assert transition.after_digest == target.digest
    assert history.current_digest == target.digest
    assert history.undo_stack == (transition.transition_id,)
    assert history.redo_stack == ()
    assert history.can_undo is True
    assert history.can_redo is False
    assert current_generated_snapshot(history) == target


def test_undo_restores_exact_canonical_snapshot() -> None:
    initial = _a()
    target = _b()
    history = create_generated_history(initial)
    history, transition = record_generated_transition(
        history,
        initial,
        target,
        label="Rename harbor scene",
    )

    history, restored, undone = undo_generated_state(history, target)

    assert undone == transition
    assert restored == initial
    assert restored.serialize() == initial.serialize()
    assert history.current_digest == initial.digest
    assert history.undo_stack == ()
    assert history.redo_stack == (transition.transition_id,)
    assert history.can_undo is False
    assert history.can_redo is True


def test_redo_restores_exact_forward_snapshot() -> None:
    initial = _a()
    target = _b()
    history = create_generated_history(initial)
    history, transition = record_generated_transition(
        history,
        initial,
        target,
        label="Rename harbor scene",
    )
    history, restored, _ = undo_generated_state(history, target)

    history, redone, redone_transition = redo_generated_state(
        history,
        restored,
    )

    assert redone_transition == transition
    assert redone == target
    assert redone.serialize() == target.serialize()
    assert history.current_digest == target.digest
    assert history.undo_stack == (transition.transition_id,)
    assert history.redo_stack == ()


def test_multiple_undo_redo_operations_preserve_chain_order() -> None:
    a = _a()
    b = _b()
    c = _c()
    history = create_generated_history(a)
    history, first = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )
    history, second = record_generated_transition(
        history,
        b,
        c,
        label="Tune stealth cooldown",
    )

    history, state, undone_second = undo_generated_state(history, c)
    assert state == b
    assert undone_second == second
    assert history.redo_stack == (second.transition_id,)

    history, state, undone_first = undo_generated_state(history, state)
    assert state == a
    assert undone_first == first
    assert history.undo_stack == ()
    assert history.redo_stack == (
        second.transition_id,
        first.transition_id,
    )

    history, state, redone_first = redo_generated_state(history, state)
    assert state == b
    assert redone_first == first

    history, state, redone_second = redo_generated_state(history, state)
    assert state == c
    assert redone_second == second
    assert history.redo_stack == ()


def test_new_transition_after_undo_discards_redo_branch() -> None:
    a = _a()
    b = _b()
    c = _c()
    d = _d()
    history = create_generated_history(a)
    history, first = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )
    history, abandoned = record_generated_transition(
        history,
        b,
        c,
        label="Tune cooldown",
    )
    history, current, _ = undo_generated_state(history, c)
    assert current == b
    assert history.can_redo is True

    history, replacement = record_generated_transition(
        history,
        current,
        d,
        label="Try dawn variant",
    )

    assert history.redo_stack == ()
    assert history.undo_stack == (
        first.transition_id,
        replacement.transition_id,
    )
    assert abandoned.transition_id not in {
        transition.transition_id for transition in history.transitions
    }
    assert c.digest not in {
        snapshot.graph_digest for snapshot in history.snapshots
    }
    assert {
        snapshot.graph_digest for snapshot in history.snapshots
    } == {a.digest, b.digest, d.digest}


def test_repeating_same_transition_later_gets_distinct_transition_id() -> None:
    a = _a()
    b = _b()
    history = create_generated_history(a)
    history, first = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )
    history, restored, _ = undo_generated_state(history, b)

    history, second = record_generated_transition(
        history,
        restored,
        b,
        label="Rename scene",
    )

    assert first.before_digest == second.before_digest
    assert first.after_digest == second.after_digest
    assert first.semantic_diff_digest == second.semantic_diff_digest
    assert first.ordinal != second.ordinal
    assert first.transition_id != second.transition_id


def test_source_path_only_transition_is_reversible_semantic_noop() -> None:
    a = _a()
    target = _graph(
        revision=2,
        scene_label="Harbor",
        cooldown=2,
        source_path="generated/scene_harbor",
    )
    diff = semantic_diff(a, target)
    assert diff.is_noop is True
    assert diff.ignored_change_count == 1

    history = create_generated_history(a)
    history, transition = record_generated_transition(
        history,
        a,
        target,
        label="Refresh provenance",
    )

    assert transition.change_count == 0
    assert transition.semantic_diff_digest == diff.digest
    history, restored, _ = undo_generated_state(history, target)
    assert restored == a


def test_exact_same_target_is_rejected() -> None:
    a = _a()
    history = create_generated_history(a)

    with pytest.raises(GeneratedHistoryError) as caught:
        record_generated_transition(
            history,
            a,
            a,
            label="No-op",
        )
    assert caught.value.context["reason"] == "no_change"


def test_current_snapshot_must_match_history_cursor() -> None:
    a = _a()
    b = _b()
    history = create_generated_history(a)

    with pytest.raises(GeneratedHistoryError) as caught:
        record_generated_transition(
            history,
            b,
            _c(),
            label="Invalid cursor",
        )
    assert caught.value.context["reason"] == "current_mismatch"


def test_cross_project_transition_fails_closed() -> None:
    a = _a()
    other = _graph(
        revision=2,
        scene_label="Other",
        cooldown=2,
        project_id="other_project",
    )
    history = create_generated_history(a)

    with pytest.raises(GeneratedHistoryError) as caught:
        record_generated_transition(
            history,
            a,
            other,
            label="Cross project",
        )
    assert caught.value.context["reason"] == "project_mismatch"


def test_empty_undo_and_redo_fail_closed() -> None:
    a = _a()
    history = create_generated_history(a)

    with pytest.raises(GeneratedHistoryError) as caught:
        undo_generated_state(history, a)
    assert caught.value.context["reason"] == "undo_empty"

    with pytest.raises(GeneratedHistoryError) as caught:
        redo_generated_state(history, a)
    assert caught.value.context["reason"] == "redo_empty"


def test_history_round_trip_is_canonical_and_byte_stable() -> None:
    a = _a()
    b = _b()
    history = create_generated_history(a)
    history, _ = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )

    raw = serialize_generated_history(history)
    parsed = parse_generated_history(raw)

    assert parsed == history
    assert serialize_generated_history(parsed) == raw
    assert raw == json.dumps(
        json.loads(raw),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def test_duplicate_json_root_field_fails_closed() -> None:
    raw = serialize_generated_history(create_generated_history(_a()))
    duplicate = raw.replace(
        '"schema":"creator.generated_history.v1"',
        '"schema":"creator.generated_history.v1","schema":"creator.generated_history.v1"',
        1,
    )

    with pytest.raises(GeneratedHistoryError) as caught:
        parse_generated_history(duplicate)
    assert caught.value.context["reason"] == "duplicate_field"


def test_unknown_or_missing_root_fields_fail_closed() -> None:
    payload = json.loads(
        serialize_generated_history(create_generated_history(_a()))
    )
    payload["unexpected"] = True

    with pytest.raises(GeneratedHistoryError):
        parse_generated_history(payload)

    payload = json.loads(
        serialize_generated_history(create_generated_history(_a()))
    )
    del payload["current_digest"]

    with pytest.raises(GeneratedHistoryError):
        parse_generated_history(payload)


def test_root_digest_tampering_fails_closed() -> None:
    history = create_generated_history(_a())

    with pytest.raises(GeneratedHistoryError) as caught:
        validate_generated_history(
            replace(history, digest="0" * 64)
        )
    assert caught.value.context["reason"] == "digest_mismatch"


def test_bool_schema_version_cannot_coerce_to_one() -> None:
    history = create_generated_history(_a())

    with pytest.raises(GeneratedHistoryError):
        validate_generated_history(
            replace(history, schema_version=True)
        )


def test_snapshot_serialization_tamper_fails_closed() -> None:
    history = create_generated_history(_a())
    record = history.snapshots[0]
    forged = replace(
        record,
        serialized=record.serialized.replace("Harbor", "HarborX", 1),
    )

    with pytest.raises(GeneratedHistoryError) as caught:
        validate_generated_history(
            replace(history, snapshots=(forged,))
        )
    assert caught.value.context["reason"] == "snapshot_integrity"


def test_snapshot_digest_type_tamper_fails_as_contract_error() -> None:
    history = create_generated_history(_a())
    forged = replace(
        history.snapshots[0],
        graph_digest="not-a-sha",
    )

    with pytest.raises(GeneratedHistoryError):
        validate_generated_history(
            replace(history, snapshots=(forged,))
        )


def test_transition_digest_tampering_fails_closed() -> None:
    a = _a()
    b = _b()
    history = create_generated_history(a)
    history, transition = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )
    forged = replace(transition, digest="0" * 64)

    with pytest.raises(GeneratedHistoryError):
        validate_generated_history(
            replace(history, transitions=(forged,))
        )


def test_semantic_diff_digest_tampering_fails_closed() -> None:
    a = _a()
    b = _b()
    history = create_generated_history(a)
    history, transition = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )
    forged = replace(
        transition,
        semantic_diff_digest="0" * 64,
    )

    with pytest.raises(GeneratedHistoryError) as caught:
        validate_generated_history(
            replace(history, transitions=(forged,))
        )
    assert caught.value.context["reason"] == "transition_integrity"


def test_bool_change_count_cannot_coerce_to_one() -> None:
    a = _a()
    b = _b()
    diff = semantic_diff(a, b)
    assert len(diff.changes) == 1
    history = create_generated_history(a)
    history, transition = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )
    forged = replace(transition, change_count=True)

    with pytest.raises(GeneratedHistoryError):
        validate_generated_history(
            replace(history, transitions=(forged,))
        )


def test_bool_summary_truncation_flag_is_rejected() -> None:
    a = _a()
    b = _b()
    history = create_generated_history(a)
    history, transition = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )
    forged = replace(
        transition,
        summaries_truncated=1,  # type: ignore[arg-type]
    )

    with pytest.raises(GeneratedHistoryError):
        validate_generated_history(
            replace(history, transitions=(forged,))
        )


def test_stack_order_tampering_fails_closed() -> None:
    a = _a()
    b = _b()
    c = _c()
    history = create_generated_history(a)
    history, first = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )
    history, second = record_generated_transition(
        history,
        b,
        c,
        label="Tune cooldown",
    )

    forged = replace(
        history,
        undo_stack=(second.transition_id, first.transition_id),
    )

    with pytest.raises(GeneratedHistoryError) as caught:
        validate_generated_history(forged)
    assert caught.value.context["reason"] == "stack_integrity"


def test_stack_unknown_transition_fails_closed_without_key_error() -> None:
    history = create_generated_history(_a())

    with pytest.raises(GeneratedHistoryError) as caught:
        validate_generated_history(
            replace(history, undo_stack=("tr_" + "0" * 24,))
        )
    assert caught.value.context["reason"] == "stack_integrity"


def test_same_transition_cannot_appear_in_both_stacks() -> None:
    a = _a()
    b = _b()
    history = create_generated_history(a)
    history, transition = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )

    forged = replace(
        history,
        redo_stack=(transition.transition_id,),
    )

    with pytest.raises(GeneratedHistoryError) as caught:
        validate_generated_history(forged)
    assert caught.value.context["reason"] == "stack_integrity"


def test_unreachable_transition_inventory_fails_closed() -> None:
    a = _a()
    b = _b()
    history = create_generated_history(a)
    history, transition = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )

    forged = replace(
        history,
        undo_stack=(),
    )

    with pytest.raises(GeneratedHistoryError) as caught:
        validate_generated_history(forged)
    assert caught.value.context["reason"] == "stack_integrity"


def test_extra_snapshot_inventory_fails_closed() -> None:
    a = _a()
    b = _b()
    history = create_generated_history(a)
    extra = StoredSnapshot(
        graph_digest=b.digest,
        serialized=b.serialize(),
    )

    with pytest.raises(GeneratedHistoryError) as caught:
        validate_generated_history(
            replace(
                history,
                snapshots=(*history.snapshots, extra),
            )
        )
    assert caught.value.context["reason"] == "snapshot_integrity"


@pytest.mark.parametrize(
    "label",
    [
        "",
        " leading",
        "trailing ",
        "bad\nlabel",
        "x" * 257,
    ],
)
def test_transition_label_bounds_fail_closed(label: str) -> None:
    a = _a()
    history = create_generated_history(a)

    with pytest.raises(GeneratedHistoryError):
        record_generated_transition(
            history,
            a,
            _b(),
            label=label,
        )


def test_parse_revalidates_forged_transition_payload() -> None:
    a = _a()
    b = _b()
    history = create_generated_history(a)
    history, _ = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )
    payload = json.loads(serialize_generated_history(history))
    payload["transitions"][0]["semantic_diff_digest"] = "0" * 64

    with pytest.raises(GeneratedHistoryError):
        parse_generated_history(payload)


def test_history_module_has_no_filesystem_process_network_or_engine_authority() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden_modules = {
        "os",
        "pathlib",
        "shutil",
        "socket",
        "subprocess",
        "tempfile",
        "urllib",
        "requests",
        "godot",
    }
    forbidden_calls = {
        "eval",
        "exec",
        "compile",
        "open",
        "system",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert {
                alias.name.split(".")[0]
                for alias in node.names
            }.isdisjoint(forbidden_modules)
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden_modules
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls


def test_snapshot_inventory_order_is_canonical() -> None:
    a = _a()
    b = _b()
    history = create_generated_history(a)
    history, _ = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )
    assert len(history.snapshots) == 2

    with pytest.raises(GeneratedHistoryError) as caught:
        validate_generated_history(
            replace(
                history,
                snapshots=tuple(reversed(history.snapshots)),
            )
        )
    assert caught.value.context["reason"] == "snapshot_integrity"


def test_transition_inventory_order_is_canonical() -> None:
    a = _a()
    b = _b()
    c = _c()
    history = create_generated_history(a)
    history, _ = record_generated_transition(
        history,
        a,
        b,
        label="Rename scene",
    )
    history, _ = record_generated_transition(
        history,
        b,
        c,
        label="Tune cooldown",
    )
    assert len(history.transitions) == 2

    with pytest.raises(GeneratedHistoryError) as caught:
        validate_generated_history(
            replace(
                history,
                transitions=tuple(reversed(history.transitions)),
            )
        )
    assert caught.value.context["reason"] == "transition_integrity"
