"""AI shell type and protocol regressions."""

from __future__ import annotations

import json

import pytest

from skeleton.shells.ai.protocol import (
    AI_MODEL_PROTOCOL_VERSION,
    AIModelRequest,
    AIModelResponse,
    ModelProtocolError,
    parse_model_response,
)
from skeleton.shells.ai.types import (
    AIAction,
    AIIntent,
    AIPlanProposal,
    IntentConstraint,
    IntentKind,
    VerificationCriterion,
)


def action(action_id="a", command="python", **changes):
    values = dict(
        action_id=action_id,
        command=command,
        args=("-V",),
        purpose="inspect runtime",
    )
    values.update(changes)
    return AIAction(**values)


def intent(intent_id="i", **changes):
    values = dict(
        intent_id=intent_id,
        goal="Inspect the runtime without changing anything.",
        kind=IntentKind.INSPECT,
    )
    values.update(changes)
    return AIIntent(**values)


def proposal(proposal_id="p", intent_id="i", actions=None, **changes):
    values = dict(
        proposal_id=proposal_id,
        intent_id=intent_id,
        actions=tuple(actions or (action(),)),
        confidence=0.9,
        uncertainty=0.1,
        model_id="model",
    )
    values.update(changes)
    return AIPlanProposal(**values)


def response_dict(**changes):
    data = {
        "protocol_version": AI_MODEL_PROTOCOL_VERSION,
        "request_id": "r",
        "proposal": proposal().to_dict(),
        "warnings": [],
        "metadata": {},
    }
    data.update(changes)
    return data


def test_constraint_default_denies_network_write_destroy():
    item = IntentConstraint()
    assert not item.allow_network
    assert not item.allow_writes
    assert not item.allow_destructive


def test_constraint_allowlist():
    item = IntentConstraint(allowed_commands=frozenset({"python"}))
    assert item.allows_command("python")
    assert not item.allows_command("git")


def test_constraint_denylist_precedes_open_allowlist():
    item = IntentConstraint(denied_commands=frozenset({"git"}))
    assert item.allows_command("python")
    assert not item.allows_command("git")


def test_constraint_overlap_rejected():
    with pytest.raises(ValueError):
        IntentConstraint(
            allowed_commands=frozenset({"python"}),
            denied_commands=frozenset({"python"}),
        )


@pytest.mark.parametrize("steps", [0, -1, 1025])
def test_constraint_step_bounds(steps):
    with pytest.raises(ValueError):
        IntentConstraint(max_steps=steps)


def test_verification_criterion_shape():
    item = VerificationCriterion(
        "pytest",
        "tests pass",
        command="python",
        expected_returncodes=frozenset({0, 5}),
    )
    assert item.to_dict()["expected_returncodes"] == [0, 5]


def test_verification_rejects_empty_codes():
    with pytest.raises(ValueError):
        VerificationCriterion("x", "x", expected_returncodes=frozenset())


def test_intent_requires_goal():
    with pytest.raises(ValueError):
        AIIntent("i", "")


def test_intent_context_is_copied():
    context = {"repo": "skeleton"}
    item = intent(context=context)
    context["repo"] = "changed"
    assert item.context["repo"] == "skeleton"


def test_intent_duplicate_criteria_rejected():
    criterion = VerificationCriterion("x", "x")
    with pytest.raises(ValueError):
        intent(success_criteria=(criterion, criterion))


def test_intent_fingerprint_stable():
    assert intent().fingerprint == intent().fingerprint


def test_intent_fingerprint_changes_with_goal():
    assert intent().fingerprint != intent(goal="Another goal").fingerprint


def test_action_copies_args_and_environment_refs():
    refs = {"TOKEN": "secret/token"}
    item = action(args=["x"], environment_refs=refs)
    refs["TOKEN"] = "changed"
    assert item.args == ("x",)
    assert item.environment_refs["TOKEN"] == "secret/token"


def test_action_rejects_nul():
    with pytest.raises(ValueError):
        action(args=("a\x00b",))


def test_action_rejects_self_dependency():
    with pytest.raises(ValueError):
        action(depends_on=frozenset({"a"}))


def test_action_rejects_nonpositive_timeout():
    with pytest.raises(ValueError):
        action(timeout_seconds=0)


def test_action_to_shell_command_without_refs():
    item = action(args=("x",))
    command = item.to_shell_command()
    assert command.command == "python"
    assert command.args == ("x",)


def test_action_requires_declared_environment_resolution():
    item = action(environment_refs={"TOKEN": "secret/token"})
    with pytest.raises(ValueError):
        item.to_shell_command()


def test_action_rejects_undeclared_environment_value():
    item = action()
    with pytest.raises(ValueError):
        item.to_shell_command(environment={"TOKEN": "value"})


def test_action_environment_resolution():
    item = action(environment_refs={"TOKEN": "secret/token"})
    command = item.to_shell_command(environment={"TOKEN": "value"})
    assert command.env == {"TOKEN": "value"}


def test_proposal_requires_actions():
    with pytest.raises(ValueError):
        proposal(actions=())


def test_proposal_duplicate_action_ids():
    with pytest.raises(ValueError):
        proposal(actions=(action("a"), action("a")))


def test_proposal_unknown_dependency():
    with pytest.raises(ValueError):
        proposal(actions=(action("a", depends_on=frozenset({"missing"})),))


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_proposal_confidence_bounds(value):
    with pytest.raises(ValueError):
        proposal(confidence=value)


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_proposal_uncertainty_bounds(value):
    with pytest.raises(ValueError):
        proposal(uncertainty=value)


def test_proposal_fingerprint_stable():
    assert proposal().fingerprint == proposal().fingerprint


def test_proposal_fingerprint_changes_with_args():
    first = proposal(actions=(action(args=("a",)),))
    second = proposal(actions=(action(args=("b",)),))
    assert first.fingerprint != second.fingerprint


def test_model_request_copies_cards():
    cards = ({"name": "python"},)
    request = AIModelRequest(
        "r",
        intent(),
        "a" * 64,
        "b" * 64,
        cards,
    )
    cards[0]["name"] = "changed"
    assert request.tool_cards[0]["name"] == "python"


def test_model_request_digest_lengths():
    with pytest.raises(ValueError):
        AIModelRequest("r", intent(), "short", "b" * 64, ())


def test_model_request_protocol_version():
    with pytest.raises(ValueError):
        AIModelRequest("r", intent(), "a" * 64, "b" * 64, (), protocol_version=2)


def test_model_response_metadata_copied():
    metadata = {"provider": "x"}
    item = AIModelResponse("r", proposal(), metadata=metadata)
    metadata["provider"] = "y"
    assert item.metadata["provider"] == "x"


def test_parse_model_response_mapping():
    parsed = parse_model_response(response_dict())
    assert parsed.request_id == "r"
    assert parsed.proposal.proposal_id == "p"


def test_parse_model_response_json_string():
    parsed = parse_model_response(json.dumps(response_dict()))
    assert parsed.proposal.actions[0].command == "python"


def test_parse_model_response_bytes():
    parsed = parse_model_response(json.dumps(response_dict()).encode())
    assert parsed.proposal.intent_id == "i"


def test_parse_response_rejects_unknown_top_field():
    data = response_dict(extra=True)
    with pytest.raises(ModelProtocolError):
        parse_model_response(data)


def test_parse_response_rejects_protocol_mismatch():
    data = response_dict(protocol_version=999)
    with pytest.raises(ModelProtocolError):
        parse_model_response(data)


def test_parse_response_rejects_unknown_proposal_field():
    data = response_dict()
    data["proposal"]["unexpected"] = True
    with pytest.raises(ModelProtocolError):
        parse_model_response(data)


def test_parse_response_rejects_unknown_action_field():
    data = response_dict()
    data["proposal"]["actions"][0]["raw_command"] = "rm -rf /"
    with pytest.raises(ModelProtocolError):
        parse_model_response(data)


def test_parse_response_rejects_nonlist_args():
    data = response_dict()
    data["proposal"]["actions"][0]["args"] = "not-a-list"
    with pytest.raises(ModelProtocolError):
        parse_model_response(data)


def test_parse_response_rejects_freeform_invalid_json():
    with pytest.raises(ModelProtocolError):
        parse_model_response("{not-json")


def test_parse_response_preserves_dependencies():
    data = response_dict()
    data["proposal"]["actions"] = [
        action("a").to_dict(),
        action("b", depends_on=frozenset({"a"})).to_dict(),
    ]
    parsed = parse_model_response(data)
    assert parsed.proposal.actions[1].depends_on == frozenset({"a"})
