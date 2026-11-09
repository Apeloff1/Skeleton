"""Regression coverage for the canonical creator command surface (#807 B014)."""

from __future__ import annotations

from dataclasses import replace
import json
import math

import pytest

from skeleton.forge.creator.command_surface import (
    COMMAND_SCHEMA,
    COMMAND_VERSION,
    OPERATIONS,
    SURFACES,
    CreatorCommand,
    CreatorCommandError,
    CreatorCommandReceipt,
    all_surface_manifests,
    build_creator_command,
    command_from_api,
    command_from_cli,
    command_from_ui,
    dispatch_creator_command,
    operation_spec,
    operation_specs,
    serialize_creator_command,
    surface_manifest,
    validate_creator_command,
    validate_creator_receipt,
    verify_surface_parity,
)


def _payload(operation: str) -> dict[str, object]:
    if operation == "create":
        return {
            "intent": {
                "brief": "Small deterministic puzzle room",
                "constraints": ["offline", "single-player"],
            }
        }
    if operation == "edit":
        return {
            "target_id": "scene.root",
            "expected_revision": 2,
            "patch": {
                "position": {"x": 4, "y": 2},
                "label": "entry",
            },
        }
    if operation == "test":
        return {
            "scopes": ["mechanic.jump", "scene.root"],
            "profile": "focused",
        }
    if operation == "preview":
        return {
            "scopes": ["scene.root"],
            "mode": "runtime",
        }
    if operation == "export":
        return {
            "format": "godot",
            "artifact_name": "demo-build",
        }
    raise AssertionError(operation)


def _api_payload(operation: str) -> dict[str, object]:
    return {
        "schema": COMMAND_SCHEMA,
        "schema_version": COMMAND_VERSION,
        "operation": operation,
        "project_id": "project-alpha",
        "payload": _payload(operation),
    }


def test_operation_catalog_matches_b014_exactly() -> None:
    assert OPERATIONS == ("create", "edit", "test", "preview", "export")
    assert tuple(spec.name for spec in operation_specs()) == OPERATIONS
    assert SURFACES == ("cli", "api", "ui")


@pytest.mark.parametrize("operation", OPERATIONS)
def test_every_operation_builds_and_revalidates(operation: str) -> None:
    command = build_creator_command(
        operation,
        project_id="project-alpha",
        payload=_payload(operation),
    )

    assert command.operation == operation
    assert command.project_id == "project-alpha"
    assert len(command.digest) == 64
    validate_creator_command(command)


@pytest.mark.parametrize("surface", SURFACES)
def test_each_surface_exposes_the_same_operation_catalog(surface: str) -> None:
    manifest = surface_manifest(surface)

    assert manifest.surface == surface
    assert tuple(spec.name for spec in manifest.operations) == OPERATIONS
    assert len(manifest.digest) == 64


def test_cli_api_ui_surface_parity_is_digest_verified() -> None:
    manifests = all_surface_manifests()

    assert tuple(item.surface for item in manifests) == SURFACES
    catalog_digest = verify_surface_parity(manifests)
    assert len(catalog_digest) == 64
    assert catalog_digest == verify_surface_parity(tuple(reversed(manifests)))


def test_same_create_submission_is_identical_across_cli_api_and_ui() -> None:
    payload = _payload("create")
    cli = command_from_cli(
        (
            "create",
            "project-alpha",
            json.dumps(payload),
        )
    )
    api = command_from_api(
        {
            "schema": COMMAND_SCHEMA,
            "schema_version": COMMAND_VERSION,
            "operation": "create",
            "project_id": "project-alpha",
            "payload": payload,
        }
    )
    ui = command_from_ui(
        operation="create",
        project_id="project-alpha",
        payload=payload,
    )

    assert cli == api == ui


def test_input_object_order_does_not_change_command_identity() -> None:
    left = build_creator_command(
        "create",
        project_id="project-alpha",
        payload={
            "intent": {
                "z": {"two": 2, "one": 1},
                "a": ["x", "y"],
            }
        },
    )
    right = build_creator_command(
        "create",
        project_id="project-alpha",
        payload={
            "intent": {
                "a": ["x", "y"],
                "z": {"one": 1, "two": 2},
            }
        },
    )

    assert left == right


def test_identifier_lists_are_canonicalized() -> None:
    command = build_creator_command(
        "test",
        project_id="project-alpha",
        payload={
            "scopes": ["scene.z", "scene.a"],
            "profile": "smoke",
        },
    )

    assert command.payload["scopes"] == ["scene.a", "scene.z"]


def test_duplicate_identifier_list_entries_fail_closed() -> None:
    with pytest.raises(CreatorCommandError) as caught:
        build_creator_command(
            "test",
            project_id="project-alpha",
            payload={
                "scopes": ["scene.root", "scene.root"],
                "profile": "smoke",
            },
        )

    assert caught.value.context["reason"] == "duplicate"


def test_unknown_operation_fails_closed_on_every_adapter() -> None:
    with pytest.raises(CreatorCommandError) as caught:
        build_creator_command(
            "delete-everything",
            project_id="project-alpha",
            payload={},
        )
    assert caught.value.context["reason"] == "unknown_operation"

    with pytest.raises(CreatorCommandError):
        command_from_cli(("delete-everything", "project-alpha", "{}"))

    with pytest.raises(CreatorCommandError):
        command_from_api(
            {
                "schema": COMMAND_SCHEMA,
                "schema_version": COMMAND_VERSION,
                "operation": "delete-everything",
                "project_id": "project-alpha",
                "payload": {},
            }
        )


@pytest.mark.parametrize(
    ("operation", "payload"),
    [
        ("create", {}),
        ("create", {"intent": {}, "extra": True}),
        (
            "edit",
            {
                "target_id": "scene.root",
                "expected_revision": 1,
            },
        ),
        ("test", {"scopes": ["scene.root"], "profile": "unknown"}),
        ("preview", {"scopes": [], "mode": "static"}),
        ("export", {"format": "godot", "artifact_name": "../escape"}),
    ],
)
def test_operation_specific_payload_contracts_fail_closed(
    operation: str,
    payload: dict[str, object],
) -> None:
    with pytest.raises(CreatorCommandError):
        build_creator_command(
            operation,
            project_id="project-alpha",
            payload=payload,
        )


def test_bool_is_not_accepted_as_edit_revision() -> None:
    with pytest.raises(CreatorCommandError) as caught:
        build_creator_command(
            "edit",
            project_id="project-alpha",
            payload={
                "target_id": "scene.root",
                "expected_revision": True,
                "patch": {},
            },
        )

    assert caught.value.context["reason"] == "field_type"


@pytest.mark.parametrize(
    "project_id",
    ["", " project", "project ", "../project", "project/name", "bad project"],
)
def test_project_ids_are_canonical_and_not_paths(project_id: str) -> None:
    with pytest.raises(CreatorCommandError):
        build_creator_command(
            "create",
            project_id=project_id,
            payload=_payload("create"),
        )


def test_api_schema_version_and_field_set_are_strict() -> None:
    payload = _api_payload("create")

    with pytest.raises(CreatorCommandError) as caught:
        command_from_api({**payload, "schema": "creator.command.v999"})
    assert caught.value.context["reason"] == "schema"

    with pytest.raises(CreatorCommandError) as caught:
        command_from_api({**payload, "schema_version": True})
    assert caught.value.context["reason"] == "version"

    with pytest.raises(CreatorCommandError) as caught:
        command_from_api({**payload, "unexpected": 1})
    assert caught.value.context["reason"] == "field_set"


def test_duplicate_json_fields_fail_closed_for_cli_and_api() -> None:
    with pytest.raises(CreatorCommandError) as caught:
        command_from_cli(
            (
                "create",
                "project-alpha",
                '{"intent":{},"intent":{"brief":"duplicate"}}',
            )
        )
    assert caught.value.context["reason"] == "duplicate_field"

    with pytest.raises(CreatorCommandError) as caught:
        command_from_api(
            '{"schema":"creator.command.v1","schema":"creator.command.v1",'
            '"schema_version":1,"operation":"create","project_id":"project-alpha",'
            '"payload":{"intent":{}}}'
        )
    assert caught.value.context["reason"] == "duplicate_field"


@pytest.mark.parametrize(
    "argv",
    [
        (),
        ("create",),
        ("create", "project-alpha"),
        ("create", "project-alpha", "{}", "extra"),
    ],
)
def test_cli_arity_is_exact(argv: tuple[str, ...]) -> None:
    with pytest.raises(CreatorCommandError) as caught:
        command_from_cli(argv)
    assert caught.value.context["reason"] == "cli_arity"


def test_cli_payload_must_be_json_object() -> None:
    with pytest.raises(CreatorCommandError):
        command_from_cli(("create", "project-alpha", "[]"))

    with pytest.raises(CreatorCommandError):
        command_from_cli(("create", "project-alpha", "{not-json}"))


def test_nested_json_key_types_fail_closed_for_ui_direct_calls() -> None:
    with pytest.raises(CreatorCommandError) as caught:
        command_from_ui(
            operation="create",
            project_id="project-alpha",
            payload={"intent": {1: "not-a-json-object-key"}},
        )
    assert caught.value.context["reason"] == "field_type"


def test_non_finite_numbers_fail_closed() -> None:
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(CreatorCommandError):
            build_creator_command(
                "create",
                project_id="project-alpha",
                payload={"intent": {"weight": value}},
            )


def test_json_depth_bound_fails_closed() -> None:
    nested: dict[str, object] = {}
    cursor = nested
    for index in range(20):
        child: dict[str, object] = {}
        cursor[f"n{index}"] = child
        cursor = child

    with pytest.raises(CreatorCommandError) as caught:
        build_creator_command(
            "create",
            project_id="project-alpha",
            payload={"intent": nested},
        )
    assert caught.value.context["reason"] == "bound"


def test_json_list_item_bound_fails_closed() -> None:
    with pytest.raises(CreatorCommandError) as caught:
        build_creator_command(
            "create",
            project_id="project-alpha",
            payload={"intent": {"items": list(range(300))}},
        )
    assert caught.value.context["reason"] == "bound"


def test_command_serialization_is_canonical_and_digest_bound() -> None:
    command = build_creator_command(
        "preview",
        project_id="project-alpha",
        payload=_payload("preview"),
    )

    raw = serialize_creator_command(command)
    restored = json.loads(raw)

    assert raw == json.dumps(
        restored,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert restored["digest"] == command.digest

    with pytest.raises(CreatorCommandError) as caught:
        validate_creator_command(replace(command, digest="0" * 64))
    assert caught.value.context["reason"] == "digest_mismatch"


def test_operation_lookup_is_strict() -> None:
    assert operation_spec("create").name == "create"

    with pytest.raises(CreatorCommandError):
        operation_spec("destroy")


def test_surface_manifest_tampering_fails_closed() -> None:
    manifests = list(all_surface_manifests())
    manifests[0] = replace(
        manifests[0],
        operations=manifests[0].operations[:-1],
    )

    with pytest.raises(CreatorCommandError) as caught:
        verify_surface_parity(manifests)
    assert caught.value.context["reason"] == "digest_mismatch"


def test_surface_set_must_be_exactly_cli_api_ui() -> None:
    with pytest.raises(CreatorCommandError) as caught:
        verify_surface_parity(all_surface_manifests()[:2])
    assert caught.value.context["reason"] == "surface_parity"

    with pytest.raises(CreatorCommandError):
        surface_manifest("mobile-secret-fourth-contract")


def test_dispatch_requires_explicit_handler() -> None:
    command = build_creator_command(
        "test",
        project_id="project-alpha",
        payload=_payload("test"),
    )

    with pytest.raises(CreatorCommandError) as caught:
        dispatch_creator_command(command, handlers={})
    assert caught.value.context["reason"] == "handler_unavailable"


def test_dispatch_rejects_shadow_operation_handlers() -> None:
    command = build_creator_command(
        "test",
        project_id="project-alpha",
        payload=_payload("test"),
    )

    with pytest.raises(CreatorCommandError) as caught:
        dispatch_creator_command(
            command,
            handlers={
                "test": lambda _: {"ok": True},
                "hidden-admin": lambda _: {"ok": True},
            },
        )
    assert caught.value.context["reason"] == "handler"


def test_dispatch_returns_digest_bound_receipt() -> None:
    command = build_creator_command(
        "test",
        project_id="project-alpha",
        payload=_payload("test"),
    )

    receipt = dispatch_creator_command(
        command,
        handlers={
            "test": lambda cmd: {
                "ok": True,
                "operation": cmd.operation,
                "checked": ["scene.root"],
            }
        },
    )

    assert receipt.command_digest == command.digest
    assert receipt.operation == "test"
    assert receipt.status == "completed"
    assert receipt.output["ok"] is True
    assert len(receipt.digest) == 64
    validate_creator_receipt(receipt, command)


def test_receipt_tampering_and_cross_command_reuse_fail_closed() -> None:
    command = build_creator_command(
        "preview",
        project_id="project-alpha",
        payload=_payload("preview"),
    )
    receipt = dispatch_creator_command(
        command,
        handlers={"preview": lambda _: {"ready": True}},
    )

    with pytest.raises(CreatorCommandError) as caught:
        validate_creator_receipt(
            replace(receipt, digest="0" * 64),
            command,
        )
    assert caught.value.context["reason"] == "digest_mismatch"

    other = build_creator_command(
        "preview",
        project_id="project-beta",
        payload=_payload("preview"),
    )
    with pytest.raises(CreatorCommandError) as caught:
        validate_creator_receipt(receipt, other)
    assert caught.value.context["reason"] == "command_mismatch"


def test_handler_result_must_be_bounded_json_object() -> None:
    command = build_creator_command(
        "create",
        project_id="project-alpha",
        payload=_payload("create"),
    )

    with pytest.raises(CreatorCommandError) as caught:
        dispatch_creator_command(
            command,
            handlers={"create": lambda _: ["not", "an", "object"]},
        )
    assert caught.value.context["reason"] == "handler_result"

    with pytest.raises(CreatorCommandError):
        dispatch_creator_command(
            command,
            handlers={"create": lambda _: {"bad": object()}},
        )


def test_receipt_constructor_cannot_bypass_revalidation() -> None:
    command = build_creator_command(
        "export",
        project_id="project-alpha",
        payload=_payload("export"),
    )
    forged = CreatorCommandReceipt(
        command_digest=command.digest,
        operation=command.operation,
        status="completed",
        output={"artifact": "demo-build"},
        digest="0" * 64,
    )

    with pytest.raises(CreatorCommandError) as caught:
        validate_creator_receipt(forged, command)
    assert caught.value.context["reason"] == "digest_mismatch"


def test_hand_constructed_command_cannot_bypass_payload_contract() -> None:
    forged = CreatorCommand(
        operation="export",
        project_id="project-alpha",
        payload={"format": "godot", "artifact_name": "../escape"},
        digest="0" * 64,
    )

    with pytest.raises(CreatorCommandError):
        validate_creator_command(forged)


def test_top_level_creator_cli_emits_canonical_command(capsys) -> None:
    from skeleton.__main__ import main

    exit_code = main(
        [
            "creator",
            "create",
            "project-alpha",
            json.dumps(_payload("create")),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    output = json.loads(captured.out)
    assert output["schema"] == COMMAND_SCHEMA
    assert output["schema_version"] == COMMAND_VERSION
    assert output["operation"] == "create"
    assert output["project_id"] == "project-alpha"
    assert output["payload"] == _payload("create")
    assert len(output["digest"]) == 64


def test_top_level_creator_cli_fails_closed_on_invalid_operation(capsys) -> None:
    from skeleton.__main__ import main

    exit_code = main(
        [
            "creator",
            "destroy",
            "project-alpha",
            "{}",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    output = json.loads(captured.out)
    assert output["ok"] is False
    assert output["error"] == "CRE.COMMAND_SURFACE"
    assert output["context"]["reason"] == "unknown_operation"
