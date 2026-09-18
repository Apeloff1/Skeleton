"""Behavioral and adversarial tests for the shell-plane public data model."""

from __future__ import annotations

import hashlib
import json

import pytest

from skeleton.shells.model import (
    CommandIdentity,
    CommandIntent,
    ExecutionClass,
    ExecutionSummary,
    ExecutionTiming,
    Outcome,
    ResourceRequest,
    ShellInvocation,
    ShellModelError,
    StreamDisposition,
    canonical_json,
    digest_payload,
    invocation_from_dict,
)


@pytest.mark.parametrize(
    ("value", "namespace", "name", "version"),
    [
        ("core:python@1", "core", "python", "1"),
        ("build:compile_all@2026.09", "build", "compile_all", "2026.09"),
        ("tools:ruff@v1+safe", "tools", "ruff", "v1+safe"),
    ],
)
def test_command_identity_round_trip(value: str, namespace: str, name: str, version: str) -> None:
    identity = CommandIdentity.parse(value)
    assert identity.namespace == namespace
    assert identity.name == name
    assert identity.version == version
    assert identity.key == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "python",
        "a:b",
        "a@1",
        "a:b@",
        ":b@1",
        "a:@1",
        "a:b@1@2",
        "a:b:c@1",
        "a b:c@1",
    ],
)
def test_command_identity_rejects_malformed_values(value: str) -> None:
    with pytest.raises(ShellModelError):
        CommandIdentity.parse(value)


def test_command_identity_is_hashable_and_orderable() -> None:
    first = CommandIdentity("a", "one")
    second = CommandIdentity("a", "two")
    assert first < second
    assert {first, second} == {first, second}


def test_intent_normalizes_execution_class_and_tags() -> None:
    intent = CommandIntent(
        execution_class="test",  # type: ignore[arg-type]
        actor="ci",
        tags=frozenset({"security", "shell:test"}),
    )
    assert intent.execution_class is ExecutionClass.TEST
    assert intent.tags == frozenset({"security", "shell:test"})


@pytest.mark.parametrize("actor", ["", "bad actor", "0starts-with-digit", "a" * 129])
def test_intent_rejects_invalid_actor(actor: str) -> None:
    with pytest.raises(ShellModelError):
        CommandIntent(actor=actor)


@pytest.mark.parametrize("correlation_id", ["bad space", "bad?", "x" * 161])
def test_intent_rejects_invalid_correlation_id(correlation_id: str) -> None:
    with pytest.raises(ShellModelError):
        CommandIntent(correlation_id=correlation_id)


def test_intent_metadata_is_copied_and_immutable() -> None:
    source = {"phase": "compile", "count": 3}
    intent = CommandIntent(actor="ci", metadata=source)
    source["phase"] = "mutated"
    assert intent.metadata["phase"] == "compile"
    with pytest.raises(TypeError):
        intent.metadata["new"] = "value"  # type: ignore[index]


def test_intent_rejects_non_scalar_metadata() -> None:
    with pytest.raises(ShellModelError):
        CommandIntent(actor="ci", metadata={"nested": {"secret": "x"}})


def test_intent_rejects_large_metadata_sequence() -> None:
    with pytest.raises(ShellModelError):
        CommandIntent(actor="ci", metadata={"items": list(range(65))})


def test_intent_metadata_sequences_are_frozen() -> None:
    source = ["one", "two"]
    intent = CommandIntent(actor="ci", metadata={"items": source})
    source.append("mutated")
    assert intent.metadata["items"] == ("one", "two")
    with pytest.raises(AttributeError):
        intent.metadata["items"].append("three")  # type: ignore[union-attr]


def test_intent_to_dict_is_json_serializable() -> None:
    intent = CommandIntent(
        execution_class=ExecutionClass.BUILD,
        correlation_id="build:123",
        actor="builder",
        reason="compile verified sources",
        tags=frozenset({"build"}),
        metadata={"attempt": 1},
    )
    encoded = json.dumps(intent.to_dict(), sort_keys=True)
    assert '"execution_class": "build"' in encoded
    assert '"correlation_id": "build:123"' in encoded


@pytest.mark.parametrize("value", [0, -1, -0.5, True, float("nan"), float("inf"), float("-inf")])
def test_resource_request_rejects_nonpositive_or_boolean_timeout(value: object) -> None:
    with pytest.raises(ShellModelError):
        ResourceRequest(timeout_seconds=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [0, -1, True])
def test_resource_request_rejects_bad_output_bound(value: object) -> None:
    with pytest.raises(ShellModelError):
        ResourceRequest(max_output_bytes=value)  # type: ignore[arg-type]


def test_resource_request_allows_zero_input_budget() -> None:
    request = ResourceRequest(max_input_bytes=0)
    assert request.max_input_bytes == 0


@pytest.mark.parametrize("value", [0, -1, 1025, True])
def test_resource_request_rejects_bad_concurrency_weight(value: int) -> None:
    with pytest.raises(ShellModelError):
        ResourceRequest(concurrency_weight=value)


def test_invocation_normalizes_arguments_environment_and_returncodes() -> None:
    invocation = ShellInvocation(
        CommandIdentity("core", "python"),
        arguments=["-V"],  # type: ignore[arg-type]
        environment={"LANG": "C"},
        allowed_returncodes={0, 2},
    )
    assert invocation.arguments == ("-V",)
    assert invocation.environment == {"LANG": "C"}
    assert invocation.allowed_returncodes == frozenset({0, 2})


def test_invocation_allows_conventional_underscore_environment_key() -> None:
    invocation = ShellInvocation(CommandIdentity("core", "python"), environment={"_PRIVATE": "x"})
    assert invocation.environment["_PRIVATE"] == "x"


def test_invocation_environment_is_defensively_copied() -> None:
    env = {"LANG": "C"}
    invocation = ShellInvocation(CommandIdentity("core", "python"), environment=env)
    env["LANG"] = "mutated"
    assert invocation.environment["LANG"] == "C"
    with pytest.raises(TypeError):
        invocation.environment["X"] = "Y"  # type: ignore[index]


def test_invocation_rejects_nul_in_argument() -> None:
    with pytest.raises(ShellModelError):
        ShellInvocation(CommandIdentity("core", "python"), arguments=("x\x00y",))


def test_invocation_rejects_nul_in_environment_value() -> None:
    with pytest.raises(ShellModelError):
        ShellInvocation(
            CommandIdentity("core", "python"),
            environment={"TOKEN": "a\x00b"},
        )


def test_invocation_rejects_raw_text_stdin() -> None:
    with pytest.raises(ShellModelError):
        ShellInvocation(CommandIdentity("core", "python"), stdin="secret")  # type: ignore[arg-type]


def test_invocation_rejects_empty_allowed_returncodes() -> None:
    with pytest.raises(ShellModelError):
        ShellInvocation(CommandIdentity("core", "python"), allowed_returncodes=frozenset())


@pytest.mark.parametrize("code", [-256, 256, 9999])
def test_invocation_rejects_extreme_returncodes(code: int) -> None:
    with pytest.raises(ShellModelError):
        ShellInvocation(CommandIdentity("core", "python"), allowed_returncodes={code})


def test_invocation_normalizes_stream_dispositions() -> None:
    invocation = ShellInvocation(
        CommandIdentity("core", "python"),
        stdout="discard",  # type: ignore[arg-type]
        stderr="capture",  # type: ignore[arg-type]
    )
    assert invocation.stdout is StreamDisposition.DISCARD
    assert invocation.stderr is StreamDisposition.CAPTURE


def test_public_shape_hashes_argument_values() -> None:
    secret = "--token=this-must-not-be-persisted"
    invocation = ShellInvocation(
        CommandIdentity("core", "python"),
        arguments=(secret,),
    )
    shape = invocation.public_shape()
    rendered = canonical_json(shape)

    assert secret not in rendered
    assert shape["argument_count"] == 1
    assert shape["arguments"][0]["bytes"] == len(secret.encode())
    assert shape["arguments"][0]["sha256"] == hashlib.sha256(secret.encode()).hexdigest()


def test_invocation_public_shape_hashes_secret_environment_value() -> None:
    secret = "this-must-not-be-in-public-shape"
    invocation = ShellInvocation(
        CommandIdentity("core", "python"),
        environment={"API_TOKEN": secret},
    )
    shape = invocation.public_shape()
    rendered = canonical_json(shape)

    assert secret not in rendered
    assert shape["environment"]["API_TOKEN"]["bytes"] == len(secret)
    assert shape["environment"]["API_TOKEN"]["sha256"] == hashlib.sha256(secret.encode()).hexdigest()


def test_invocation_public_shape_hashes_stdin() -> None:
    payload = b"private stdin bytes"
    invocation = ShellInvocation(CommandIdentity("core", "python"), stdin=payload)
    shape = invocation.public_shape()
    rendered = canonical_json(shape)

    assert "private stdin bytes" not in rendered
    assert shape["stdin"]["bytes"] == len(payload)
    assert shape["stdin"]["sha256"] == hashlib.sha256(payload).hexdigest()


def test_public_shape_hashes_reason_and_metadata_values() -> None:
    reason = "token=super-secret"
    metadata_value = "another-secret"
    invocation = ShellInvocation(
        CommandIdentity("core", "python"),
        intent=CommandIntent(
            actor="builder",
            reason=reason,
            metadata={"note": metadata_value},
        ),
    )
    rendered = canonical_json(invocation.public_shape())

    assert reason not in rendered
    assert metadata_value not in rendered
    assert invocation.public_shape()["intent"]["reason"]["bytes"] == len(reason)


def test_fingerprint_is_deterministic_for_equivalent_invocations() -> None:
    first = ShellInvocation(
        CommandIdentity("core", "python"),
        arguments=("-V",),
        environment={"B": "2", "A": "1"},
    )
    second = ShellInvocation(
        CommandIdentity("core", "python"),
        arguments=("-V",),
        environment={"A": "1", "B": "2"},
    )
    assert first.fingerprint == second.fingerprint


def test_fingerprint_changes_with_secret_value_without_exposing_it() -> None:
    first = ShellInvocation(
        CommandIdentity("core", "python"),
        environment={"TOKEN": "one"},
    )
    second = ShellInvocation(
        CommandIdentity("core", "python"),
        environment={"TOKEN": "two"},
    )
    assert first.fingerprint != second.fingerprint
    assert "one" not in first.fingerprint
    assert "two" not in second.fingerprint


def test_with_intent_preserves_invocation_and_replaces_intent_field() -> None:
    invocation = ShellInvocation(
        CommandIdentity("core", "python"),
        intent=CommandIntent(actor="builder", correlation_id="one"),
    )
    changed = invocation.with_intent(correlation_id="two")
    assert invocation.intent.correlation_id == "one"
    assert changed.intent.correlation_id == "two"
    assert changed.identity == invocation.identity


@pytest.mark.parametrize("value", [-0.001, True, float("nan"), float("inf")])
def test_execution_timing_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ShellModelError):
        ExecutionTiming(runtime_seconds=value)  # type: ignore[arg-type]


def test_execution_summary_normalizes_outcome() -> None:
    summary = ExecutionSummary(
        invocation_fingerprint="sha256:abc",
        command="core:python@1",
        outcome="succeeded",  # type: ignore[arg-type]
        returncode=0,
    )
    assert summary.outcome is Outcome.SUCCEEDED
    assert summary.ok is True


def test_execution_summary_failed_is_not_ok() -> None:
    summary = ExecutionSummary(
        invocation_fingerprint="sha256:abc",
        command="core:python@1",
        outcome=Outcome.FAILED,
        returncode=1,
    )
    assert summary.ok is False


@pytest.mark.parametrize(("field", "value"), [("stdout_bytes", -1), ("stderr_bytes", -1), ("attempt_count", 0)])
def test_execution_summary_rejects_negative_counts(field: str, value: int) -> None:
    kwargs = {
        "invocation_fingerprint": "sha256:abc",
        "command": "core:python@1",
        "outcome": Outcome.FAILED,
        field: value,
    }
    with pytest.raises(ShellModelError):
        ExecutionSummary(**kwargs)


def test_canonical_json_has_stable_key_order() -> None:
    assert canonical_json({"z": 1, "a": 2}) == '{"a":2,"z":1}'


def test_digest_payload_is_deterministic_and_prefixed() -> None:
    first = digest_payload({"b": 2, "a": 1}, prefix="request")
    second = digest_payload({"a": 1, "b": 2}, prefix="request")
    assert first == second
    assert first.startswith("request:")
    assert len(first.split(":", 1)[1]) == 64


def test_invocation_from_dict_builds_typed_request() -> None:
    invocation = invocation_from_dict(
        {
            "command": "core:python@1",
            "arguments": ["-V"],
            "cwd": "/tmp/work",
            "environment": {"LANG": "C"},
            "resources": {
                "timeout_seconds": 5,
                "max_output_bytes": 1000,
                "cpu_weight": 2,
            },
            "intent": {
                "execution_class": "probe",
                "correlation_id": "probe:1",
                "actor": "health",
                "tags": ["startup"],
                "metadata": {"source": "test"},
            },
            "allowed_returncodes": [0],
            "stdout": "capture",
            "stderr": "discard",
        }
    )
    assert invocation.identity.key == "core:python@1"
    assert invocation.arguments == ("-V",)
    assert invocation.resources.timeout_seconds == 5
    assert invocation.intent.execution_class is ExecutionClass.PROBE
    assert invocation.stderr is StreamDisposition.DISCARD


def test_invocation_from_dict_rejects_non_string_command() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": 123})


def test_invocation_from_dict_rejects_non_string_argument_item() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": "core:python@1", "arguments": ["-V", 1]})


def test_invocation_from_dict_rejects_non_string_environment_value() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": "core:python@1", "environment": {"PORT": 8000}})


def test_invocation_from_dict_rejects_unknown_resource_field() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": "core:python@1", "resources": {"unlimited": True}})


def test_invocation_from_dict_rejects_boolean_resource_weight() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": "core:python@1", "resources": {"cpu_weight": True}})


def test_invocation_from_dict_rejects_unknown_intent_field() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": "core:python@1", "intent": {"admin": True}})


def test_invocation_from_dict_rejects_non_string_intent_actor() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": "core:python@1", "intent": {"actor": 42}})


def test_invocation_from_dict_rejects_string_returncode_coercion() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": "core:python@1", "allowed_returncodes": ["0"]})


def test_invocation_from_dict_rejects_boolean_returncode() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": "core:python@1", "allowed_returncodes": [True]})


def test_invocation_from_dict_rejects_non_string_cwd() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": "core:python@1", "cwd": 123})


def test_invocation_from_dict_refuses_raw_stdin() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict(
            {
                "command": "core:python@1",
                "stdin": "secret",
            }
        )


@pytest.mark.parametrize("arguments", ["-V", b"-V", 123, {"arg": "-V"}])
def test_invocation_from_dict_requires_argument_sequence(arguments: object) -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": "core:python@1", "arguments": arguments})


def test_invocation_from_dict_requires_environment_object() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": "core:python@1", "environment": ["LANG=C"]})


def test_invocation_from_dict_requires_resources_object() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": "core:python@1", "resources": "fast"})


def test_invocation_from_dict_requires_intent_object() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict({"command": "core:python@1", "intent": "test"})


def test_model_rejects_executable_path_field() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict(
            {
                "command": "core:python@1",
                "executable": "/bin/sh",
            }
        )


def test_model_rejects_arbitrary_shell_text_field() -> None:
    with pytest.raises(ShellModelError):
        invocation_from_dict(
            {
                "command": "core:python@1",
                "shell": "rm -rf /",
            }
        )


def test_public_shape_is_json_serializable() -> None:
    invocation = ShellInvocation(
        CommandIdentity("core", "python"),
        arguments=("-V",),
        intent=CommandIntent(actor="ci"),
    )
    json.dumps(invocation.public_shape(), sort_keys=True)


def test_execution_summary_to_dict_is_json_serializable() -> None:
    summary = ExecutionSummary(
        invocation_fingerprint="sha256:abc",
        command="core:python@1",
        outcome=Outcome.SUCCEEDED,
        returncode=0,
        stdout_bytes=10,
        timing=ExecutionTiming(runtime_seconds=0.1, total_seconds=0.1),
        receipt_id="receipt-1",
    )
    payload = summary.to_dict()
    assert payload["outcome"] == "succeeded"
    json.dumps(payload, sort_keys=True)
