"""Fail-closed regressions for the engine-neutral creator intent compiler (#942)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from skeleton.creator.intent_compiler import (
    DESIGN_PLAN_SCHEMA,
    EDIT_SCHEMA,
    INTENT_SCHEMA,
    INTENT_VERSION,
    MAX_EDIT_LOG,
    MAX_NODES,
    DesignEdit,
    IntentCompiler,
    IntentCompilerError,
    IntentVersionError,
    apply_edit,
    compile_intent,
    revert_edit,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "intent_compiler"
COMPILER_PATH = Path(__file__).resolve().parents[1] / "creator" / "intent_compiler.py"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _request(**overrides: object) -> dict:
    payload = _load_fixture("harbor_heist_v1.json")
    payload.update(overrides)
    return payload


def _reason(exc: pytest.ExceptionInfo[IntentCompilerError]) -> str:
    return str(exc.value.context["reason"])


def test_schema_and_version_are_explicit_and_stable() -> None:
    compiler = IntentCompiler()
    assert compiler.schema == INTENT_SCHEMA == "creator.intent.v1"
    assert compiler.schema_version == INTENT_VERSION == 1
    plan = compiler.compile(_request())
    assert plan.schema == DESIGN_PLAN_SCHEMA == "creator.design_plan.v1"
    assert plan.schema_version == 1
    assert '"schema":"creator.design_plan.v1"' in plan.canonical_json()


def test_foreign_compiler_version_fails_closed() -> None:
    with pytest.raises(IntentVersionError, match="not this boundary"):
        IntentCompiler(schema="creator.intent.v0")
    with pytest.raises(IntentVersionError, match="not this boundary"):
        IntentCompiler(schema_version=True)  # type: ignore[arg-type]


def test_schema_version_true_does_not_equal_one() -> None:
    with pytest.raises(IntentVersionError):
        compile_intent(_request(schema_version=True))


def test_unknown_request_fields_are_schema_drift() -> None:
    with pytest.raises(IntentCompilerError) as caught:
        compile_intent(_request(preview={"live": True}))
    assert _reason(caught) == "schema_drift"
    assert "preview" in caught.value.context["fields"]


def test_unknown_schema_version_fails_closed() -> None:
    with pytest.raises(IntentVersionError) as caught:
        compile_intent(_request(schema_version=2))
    assert caught.value.context["reason"] == "schema_drift"


def test_compile_is_deterministic_across_input_order() -> None:
    first = compile_intent(_request())
    shuffled = _request()
    shuffled["nodes"] = list(reversed(shuffled["nodes"]))
    shuffled["assumptions"] = list(reversed(shuffled["assumptions"]))
    second = compile_intent(shuffled)
    assert first.canonical_json() == second.canonical_json()
    assert first.digest() == second.digest()
    assert first.waves == (("n_world",), ("n_stealth",))


def test_canonical_json_is_byte_stable_across_calls() -> None:
    request = _request()
    first = compile_intent(request)
    second = IntentCompiler().compile(request)
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_json() == first.canonical_json()


def test_missing_and_blank_required_fields_fail_closed() -> None:
    with pytest.raises(IntentCompilerError) as missing:
        compile_intent(_request(title=None))
    assert _reason(missing) == "malformed"

    with pytest.raises(IntentCompilerError) as blank:
        compile_intent(_request(goal="   "))
    assert _reason(blank) == "malformed"

    payload = _request()
    del payload["nodes"][0]["editable"]
    with pytest.raises(IntentCompilerError) as editable:
        compile_intent(payload)
    assert _reason(editable) == "malformed"


def test_bool_editable_flag_does_not_coerce_from_int() -> None:
    payload = _request()
    payload["nodes"][0]["editable"] = 1
    with pytest.raises(IntentCompilerError, match="must be a boolean"):
        compile_intent(payload)


def test_duplicate_ids_and_titles_are_ambiguous() -> None:
    payload = _request()
    payload["nodes"].append(dict(payload["nodes"][0], title="Other harbor"))
    with pytest.raises(IntentCompilerError) as duplicate:
        compile_intent(payload)
    assert _reason(duplicate) == "ambiguous"

    payload = _request()
    payload["nodes"][1]["kind"] = "world"
    payload["nodes"][1]["title"] = payload["nodes"][0]["title"]
    with pytest.raises(IntentCompilerError) as titles:
        compile_intent(payload)
    assert _reason(titles) == "ambiguous"


def test_conflicting_constraints_fail_closed() -> None:
    payload = _request(
        constraints=[
            {"id": "c_min", "field": "players", "op": "min", "value": 4},
            {"id": "c_max", "field": "players", "op": "max", "value": 2},
        ]
    )
    with pytest.raises(IntentCompilerError) as caught:
        compile_intent(payload)
    assert _reason(caught) == "ambiguous"


def test_require_and_forbid_same_value_is_ambiguous() -> None:
    payload = _request(
        constraints=[
            {"id": "c_need", "field": "networking", "op": "require", "value": "realtime"},
            {"id": "c_no", "field": "networking", "op": "forbid", "value": "realtime"},
        ]
    )
    with pytest.raises(IntentCompilerError) as caught:
        compile_intent(payload)
    assert _reason(caught) == "ambiguous"


def test_cycles_fail_closed_without_a_partial_graph() -> None:
    payload = _request()
    payload["nodes"][0]["depends_on"] = ["n_stealth"]
    with pytest.raises(IntentCompilerError) as caught:
        compile_intent(payload)
    assert _reason(caught) == "cycle"


def test_self_cycle_fails_closed() -> None:
    payload = _request()
    payload["nodes"][0]["depends_on"] = ["n_world"]
    with pytest.raises(IntentCompilerError) as caught:
        compile_intent(payload)
    assert _reason(caught) == "cycle"


def test_unknown_dependency_and_validation_target_fail_closed() -> None:
    payload = _request()
    payload["nodes"][1]["depends_on"] = ["n_missing"]
    with pytest.raises(IntentCompilerError) as dep:
        compile_intent(payload)
    assert _reason(dep) == "malformed"

    payload = _request()
    payload["validations"][0]["applies_to"] = ["n_missing"]
    with pytest.raises(IntentCompilerError) as validation:
        compile_intent(payload)
    assert _reason(validation) == "malformed"


def test_code_execution_and_engine_mutation_keys_fail_closed() -> None:
    with pytest.raises(IntentCompilerError) as code:
        compile_intent(_request(code="print('nope')"))
    assert _reason(code) == "execution"

    with pytest.raises(IntentCompilerError) as engine:
        compile_intent(_request(godot={"main_scene": "res://cheat.tscn"}))
    assert _reason(engine) == "engine_mutation"


def test_compiler_source_has_no_execution_or_network_surface() -> None:
    tree = ast.parse(COMPILER_PATH.read_text(encoding="utf-8"))
    forbidden_names = {"eval", "exec", "compile", "system"}
    forbidden_modules = {"subprocess", "socket", "http", "urllib", "requests", "godot"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_names
        if isinstance(node, ast.Import):
            assert {alias.name.split(".")[0] for alias in node.names}.isdisjoint(forbidden_modules)
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden_modules
            assert not node.module.startswith("skeleton.forge")
            assert not node.module.startswith("skeleton.platform")


def test_provenance_binds_request_fields_to_graph_nodes() -> None:
    plan = compile_intent(_request())
    by_path = {link.source_path: link for link in plan.provenance}
    assert by_path["nodes.n_stealth.title"].request_field == "title"
    assert by_path["nodes.n_stealth.title"].request_id == "req_harbor_heist"
    assert by_path["nodes.n_stealth.depends_on.n_world"].target_id == "n_stealth"
    assert by_path["assumptions.a_presentation_2d.statement"].target_kind == "assumption"
    assert by_path["validations.v_extract_path.requirement"].target_id == "v_extract_path"
    world = plan.node_map()["n_world"]
    assert world.source_path == "nodes.n_world"
    assert world.validation_ids == ("v_extract_path",)
    assert world.assumption_ids == ("a_presentation_2d",)


def test_reversible_title_edit_restores_graph_digest() -> None:
    original = compile_intent(_request())
    edited, recorded = apply_edit(
        original,
        {
            "schema": EDIT_SCHEMA,
            "schema_version": 1,
            "edit_id": "e_rename",
            "op": "set_field",
            "node_id": "n_stealth",
            "field": "title",
            "value": "Detection loop",
        },
    )
    assert edited.revision == 1
    assert edited.node_map()["n_stealth"].title == "Detection loop"
    assert edited.digest() != original.digest()
    assert recorded.inverse is not None

    restored = revert_edit(edited)
    assert restored.digest() == original.digest()
    assert restored.node_map()["n_stealth"].title == "Stealth loop"
    assert restored.edit_log == ()
    assert restored.revision == 2


def test_invalid_edits_fail_closed() -> None:
    plan = compile_intent(_request())
    with pytest.raises(IntentCompilerError) as unknown:
        apply_edit(
            plan,
            {
                "schema": EDIT_SCHEMA,
                "schema_version": 1,
                "edit_id": "e_missing",
                "op": "set_field",
                "node_id": "n_missing",
                "field": "title",
                "value": "Nope",
            },
        )
    assert _reason(unknown) == "invalid_edit"

    payload = _request()
    payload["nodes"][1]["editable"] = False
    locked = compile_intent(payload)
    with pytest.raises(IntentCompilerError) as not_editable:
        apply_edit(
            locked,
            {
                "schema": EDIT_SCHEMA,
                "schema_version": 1,
                "edit_id": "e_locked",
                "op": "set_field",
                "node_id": "n_stealth",
                "field": "title",
                "value": "Nope",
            },
        )
    assert _reason(not_editable) == "invalid_edit"
    assert locked.digest() == compile_intent(payload).digest()


def test_edit_that_creates_a_cycle_fails_closed() -> None:
    plan = compile_intent(_request())
    with pytest.raises(IntentCompilerError) as caught:
        apply_edit(
            plan,
            {
                "schema": EDIT_SCHEMA,
                "schema_version": 1,
                "edit_id": "e_cycle",
                "op": "add_dependency",
                "node_id": "n_world",
                "value": "n_stealth",
            },
        )
    assert _reason(caught) == "cycle"
    assert plan.canonical_json() == compile_intent(_request()).canonical_json()


def test_dependency_edit_is_reversible() -> None:
    payload = _request()
    payload["nodes"].append(
        {
            "id": "n_heat",
            "kind": "mechanic",
            "title": "Heat meter",
            "summary": "Tracks detection pressure.",
            "depends_on": [],
            "editable": True,
        }
    )
    original = compile_intent(payload)
    edited, recorded = apply_edit(
        original,
        DesignEdit(
            edit_id="e_link",
            op="add_dependency",
            node_id="n_heat",
            field="depends_on",
            value="n_stealth",
        ),
    )
    assert "n_stealth" in edited.node_map()["n_heat"].depends_on
    assert edited.waves[-1] == ("n_heat",)
    restored = revert_edit(edited, recorded.inverse)
    assert restored.digest() == original.digest()


def test_mismatched_inverse_fails_closed() -> None:
    plan, recorded = apply_edit(
        compile_intent(_request()),
        {
            "schema": EDIT_SCHEMA,
            "schema_version": 1,
            "edit_id": "e_rename",
            "op": "set_field",
            "node_id": "n_stealth",
            "field": "title",
            "value": "Detection loop",
        },
    )
    assert recorded.inverse is not None
    with pytest.raises(IntentCompilerError) as caught:
        revert_edit(
            plan,
            {
                "schema": EDIT_SCHEMA,
                "schema_version": 1,
                "edit_id": "e_wrong",
                "op": "set_field",
                "node_id": "n_stealth",
                "field": "title",
                "value": "Unrelated",
            },
        )
    assert _reason(caught) == "invalid_edit"


def test_bounded_node_count_fails_closed() -> None:
    payload = {
        "schema": INTENT_SCHEMA,
        "schema_version": 1,
        "request_id": "req_bound",
        "title": "Bound",
        "goal": "Prove the node cap.",
        "nodes": [
            {
                "id": f"n_{index}",
                "kind": "content",
                "title": f"Prop {index}",
                "editable": True,
            }
            for index in range(MAX_NODES + 1)
        ],
    }
    with pytest.raises(IntentCompilerError) as caught:
        compile_intent(payload)
    assert _reason(caught) == "bound"


def test_bounded_edit_log_fails_closed() -> None:
    plan = compile_intent(_request())
    for index in range(MAX_EDIT_LOG):
        plan, _recorded = apply_edit(
            plan,
            {
                "schema": EDIT_SCHEMA,
                "schema_version": 1,
                "edit_id": f"e_{index}",
                "op": "set_field",
                "node_id": "n_stealth",
                "field": "summary",
                "value": f"Revision {index}",
            },
        )
    with pytest.raises(IntentCompilerError) as caught:
        apply_edit(
            plan,
            {
                "schema": EDIT_SCHEMA,
                "schema_version": 1,
                "edit_id": "e_overflow",
                "op": "set_field",
                "node_id": "n_stealth",
                "field": "summary",
                "value": "one too many",
            },
        )
    assert _reason(caught) == "bound"
    restored = revert_edit(plan)
    assert restored.revision == MAX_EDIT_LOG + 1
    assert len(restored.edit_log) == MAX_EDIT_LOG - 1


def test_kind_mismatch_is_schema_drift() -> None:
    with pytest.raises(IntentCompilerError) as caught:
        compile_intent(_request(kind="game-spec"))
    assert _reason(caught) == "schema_drift"
