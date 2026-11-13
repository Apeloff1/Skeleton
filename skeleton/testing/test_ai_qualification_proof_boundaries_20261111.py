"""Adversarial first-boot receipt preflight, independent of a native GGUF."""
import hashlib
import json
from pathlib import Path
from unittest import mock

import pytest

from skeleton.ai.runtime.operational_ai.deployment.qualification.contracts import (
    QualificationError,
)
from skeleton.ai.runtime.operational_ai.deployment.qualification import paths, proof, verification
from skeleton.ai.runtime.operational_ai.deployment.qualification.verification import verify


def _inputs():
    answer = "bounded fixture reply"
    digest = hashlib.sha256(answer.encode("utf8")).hexdigest()
    first = {
        "replayed": False,
        "revision": 1,
        "output_sha256": digest,
        "request_sha256": "a" * 64,
        "context_sha256": "b" * 64,
        "generated_tokens": 2,
        "prompt_tokens": 4,
    }
    return (
        first,
        dict(first, replayed=True),
        ({"role": "user", "content": "hi"},
         {"role": "assistant", "content": answer}),
        {"turns": 1},
    )


def _issue(*, session="session", request="request", history=None):
    first, replayed, baseline, diagnostics = _inputs()
    return proof.construct(
        "c" * 64, "d" * 64, session, request,
        first, replayed, baseline if history is None else history,
        diagnostics, exact_native=False,
    )


def test_valid_bounded_fixture_remains_structurally_verifiable():
    receipt = _issue()
    result = verify(receipt, require_real=False)
    assert result["real_model_executed"] is False
    assert result["status"] == "structurally-valid-receipt-no-external-attestation"


@pytest.mark.parametrize("field,value", [
    ("session", ""), ("request", "bad name"),
    ("session", "a" * 129), ("request", "x\ud800"),
    ("session", 123), ("request", b"bytes"),
    ("session", "x/../y"), ("request", " x "),
])
def test_malformed_identity_rejected_before_canonicalization(field, value):
    with mock.patch.object(
        proof, "canonical", side_effect=AssertionError("canonical called"),
    ):
        with pytest.raises(QualificationError, match="invalid qualification identity"):
            _issue(**{field: value})


@pytest.mark.parametrize("history", [
    [],
    ({"role": "user", "content": "hi"},),
    [{"role": "user", "content": "hi"},
     {"role": "assistant", "content": "bounded fixture reply"}],
    (None, {"role": "assistant", "content": "bounded fixture reply"}),
    ({"role": "user", "content": "hi", "extra": "untrusted"},
     {"role": "assistant", "content": "bounded fixture reply"}),
    ({"role": "user", "content": "hi"},
     {"role": "user", "content": "bounded fixture reply"}),
    ({"role": "user", "content": "hi"},
     {"role": "assistant", "content": 42}),
    ({"role": "user", "content": "hi"},
     {"role": "assistant", "content": "\ud800"}),
    ({"role": "user", "content": "x" * 1_048_577},
     {"role": "assistant", "content": "bounded fixture reply"}),
    ({"role": "user", "content": "x" * 700_000},
     {"role": "assistant", "content": "y" * 400_000}),
])
def test_malformed_history_rejected_before_canonicalization(history):
    with mock.patch.object(
        proof, "canonical", side_effect=AssertionError("canonical called"),
    ):
        with pytest.raises(QualificationError):
            _issue(history=history)


def test_valid_history_with_forged_output_still_fails_digest_binding():
    first, replayed, history, doctor = _inputs()
    history = (history[0], {"role": "assistant", "content": "forged"})
    with pytest.raises(QualificationError, match="durable output"):
        proof.construct(
            "c" * 64, "d" * 64, "session", "request",
            first, replayed, history, doctor, exact_native=False,
        )


def test_ascii_json_preflight_counts_del_and_control_escapes_exactly():
    value = "".join(chr(n) for n in range(128)) + "\u2028\U0001f600"
    assert paths._bounded_ascii_json_string_size(value, 16_384) == len(
        json.dumps(value, ensure_ascii=True)
    )
    assert paths._bounded_ascii_json_string_size("\x7f" * 100, 16_384) == 602


def test_oversized_del_escapes_rejected_before_json_encoder_or_filesystem():
    # DEL is ASCII but ensure_ascii escapes it to six bytes. A raw character
    # count underestimates the 18 KiB encoded string and defeats preflight.
    with mock.patch.object(
        paths.json, "JSONEncoder", side_effect=AssertionError("encoder called"),
    ):
        with pytest.raises(QualificationError, match="oversized"):
            paths.publish_private_report(
                Path("/does-not-need-to-exist"), "report.json",
                {"payload": "\x7f" * 3_000},
            )


def test_role_equality_spoof_rejected_before_canonicalization():
    class SpoofRole:
        def __eq__(self, other):
            return True

    _, _, history, _ = _inputs()
    forged = ({"role": SpoofRole(), "content": "hi"}, history[1])
    with mock.patch.object(
        proof, "canonical", side_effect=AssertionError("canonical called"),
    ):
        with pytest.raises(QualificationError, match="committed transcript"):
            _issue(history=forged)


def test_subclassed_receipts_cannot_override_lookup_before_preflight():
    class HostileReceipt(dict):
        def get(self, *args, **kwargs):
            raise AssertionError("hostile mapping getter invoked")

    first, replayed, history, diagnostics = _inputs()
    for forged_first, forged_replay in (
        (HostileReceipt(first), replayed),
        (first, HostileReceipt(replayed)),
    ):
        with pytest.raises(QualificationError, match="missing inference receipts"):
            proof.construct(
                "c" * 64, "d" * 64, "session", "request",
                forged_first, forged_replay, history, diagnostics,
                exact_native=False,
            )


@pytest.mark.parametrize("field,invalid", [
    ("context_sha256", "f" * 64),
    ("generated_tokens", 3),
    ("prompt_tokens", 5),
    ("generated_tokens", True),
    ("prompt_tokens", 4.0),
    ("request_sha256", object()),
    ("output_sha256", 17),
    ("context_sha256", None),
])
def test_replay_durable_evidence_mismatch_rejected_before_canonical(field, invalid):
    first, replayed, history, doctor = _inputs()
    replayed[field] = invalid
    with mock.patch.object(
        proof, "canonical", side_effect=AssertionError("forged replay serialized"),
    ):
        with pytest.raises(QualificationError):
            proof.construct(
                "c" * 64, "d" * 64, "session", "request",
                first, replayed, history, doctor, exact_native=False,
            )


def test_replay_receipt_rejects_provenance_and_finish_reason_forgery():
    first, replayed, history, doctor = _inputs()
    first.update(model_sha256="c" * 64, tokenizer_sha256="d" * 64,
                 finish_reason="stop")
    replayed.update(model_sha256="c" * 64, tokenizer_sha256="d" * 64,
                    finish_reason="stop")
    valid = proof.construct(
        "c" * 64, "d" * 64, "session", "request",
        first, replayed, history, doctor, exact_native=False,
    )
    assert verify(valid, require_real=False)["real_model_executed"] is False
    for key, invalid in (
        ("model_sha256", "e" * 64),
        ("tokenizer_sha256", "f" * 64),
        ("finish_reason", "length"),
    ):
        forged = dict(replayed, **{key: invalid})
        with mock.patch.object(
            proof, "canonical", side_effect=AssertionError("forged provenance serialized"),
        ):
            with pytest.raises(QualificationError, match="changed across restart"):
                proof.construct(
                    "c" * 64, "d" * 64, "session", "request",
                    first, forged, history, doctor, exact_native=False,
                )


def test_replay_digest_subclass_cannot_override_equality():
    class EqualitySpoof(str):
        def __eq__(self, other):
            raise AssertionError("untrusted equality invoked")

    first, replayed, history, doctor = _inputs()
    replayed["request_sha256"] = EqualitySpoof(first["request_sha256"])
    with mock.patch.object(
        proof, "canonical", side_effect=AssertionError("forged digest serialized"),
    ):
        with pytest.raises(QualificationError, match="invalid qualification digest"):
            proof.construct(
                "c" * 64, "d" * 64, "session", "request",
                first, replayed, history, doctor, exact_native=False,
            )


class _UntrustedText(str):
    """A str subclass must not control authoritative receipt comparisons."""

    def __eq__(self, other):
        raise AssertionError("hostile equality invoked")

    def __ne__(self, other):
        raise AssertionError("hostile inequality invoked")

    __hash__ = str.__hash__


@pytest.mark.parametrize("field", [
    "schema", "model_sha256", "tokenizer_sha256", "session_sha256",
    "request_id_sha256", "request_sha256", "output_sha256",
    "transcript_sha256", "context_sha256", "proof_sha256",
    "checkpoint_execution_mode", "status",
])
def test_verifier_rejects_subclassed_receipt_text_without_equality(field):
    receipt = _issue()
    receipt[field] = _UntrustedText(receipt[field])
    with pytest.raises(QualificationError):
        verify(receipt, require_real=False)


def test_verifier_rejects_subclassed_report_key_before_set_comparison():
    receipt = _issue()
    saved = receipt.pop("status")
    receipt[_UntrustedText("status")] = saved
    with pytest.raises(QualificationError, match="schema mismatch"):
        verify(receipt, require_real=False)


def test_fixture_receipt_cannot_spoof_real_model_provenance():
    receipt = _issue()
    # Without exact builtin strings, a malicious __eq__ may claim that both
    # fixture labels are real-model labels while the canonical bytes stay
    # identical to the valid fixture report and its existing SHA-256.
    class _AlwaysEqualText(str):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    receipt["checkpoint_execution_mode"] = _AlwaysEqualText(
        receipt["checkpoint_execution_mode"]
    )
    receipt["status"] = _AlwaysEqualText(receipt["status"])
    with pytest.raises(QualificationError, match="provenance"):
        verify(receipt, require_real=True)


def test_verifier_normalizes_canonicalization_failure():
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import SpineError

    with mock.patch.object(
        verification, "canonical", side_effect=SpineError("internal encoder detail")
    ):
        with pytest.raises(QualificationError, match="invalid qualification report"):
            verify(_issue(), require_real=False)


def test_native_report_ci_watches_and_compiles_receipt_verifier():
    # A proof-verifier-only repair must always re-run the native custody gate.
    workflow = (
        Path(__file__).resolve().parents[2]
        / ".github/workflows/native-qualification-report-custody.yml"
    ).read_text(encoding="utf-8")
    relative = "skeleton/ai/runtime/operational_ai/deployment/qualification/verification.py"
    watch, run = workflow.split("      - name: Compile and execute actual native report regression suite", 1)
    assert f"      - '{relative}'" in watch
    assert relative in run
    assert "ref: ${{ github.event.pull_request.head.sha }}" in workflow


class _HostileReceiptKey:
    """A foreign key colliding with a trusted lookup must never run equality."""

    def __init__(self, target):
        self.target = target

    def __hash__(self):
        return hash(self.target)

    def __eq__(self, other):
        raise AssertionError("untrusted mapping-key equality invoked")


class _HostileStringKey(str):
    __hash__ = str.__hash__

    def __eq__(self, other):
        raise AssertionError("untrusted string-subclass equality invoked")


@pytest.mark.parametrize("surface,target", [
    ("first", "replayed"),
    ("replayed", "request_sha256"),
    ("user_history", "role"),
    ("assistant_history", "content"),
    ("diagnostics", "turns"),
])
@pytest.mark.parametrize("key_type", [_HostileReceiptKey, _HostileStringKey])
def test_receipt_mapping_keys_are_validated_before_lookup(surface, target, key_type):
    # Exact dict containers can still carry keys whose equality executes
    # arbitrary caller code during .get(), membership, or indexed lookup.
    first, replayed, history, diagnostics = _inputs()

    def poison(mapping):
        altered = dict(mapping)
        original = altered.pop(target)
        altered[key_type(target)] = original
        return altered

    if surface == "first":
        first = poison(first)
    elif surface == "replayed":
        replayed = poison(replayed)
    elif surface == "user_history":
        history = (poison(history[0]), history[1])
    elif surface == "assistant_history":
        history = (history[0], poison(history[1]))
    else:
        diagnostics = poison(diagnostics)

    with mock.patch.object(
        proof, "canonical", side_effect=AssertionError("forged mapping serialized"),
    ):
        with pytest.raises(QualificationError):
            proof.construct(
                "c" * 64, "d" * 64, "session", "request",
                first, replayed, history, diagnostics, exact_native=False,
            )


def test_mapping_key_hardening_preserves_canonical_fixture_receipt():
    receipt = _issue()
    assert verify(receipt, require_real=False)["real_model_executed"] is False

@pytest.mark.parametrize("policy", [None, 0, 1, "", "false", [], {}])
def test_verifier_rejects_ambiguous_real_model_policy(policy):
    # The fixture inspection exception must require literal False, not
    # arbitrary falsey values such as 0, None, or an empty collection.
    with pytest.raises(QualificationError, match="verification policy"):
        verify(_issue(), require_real=policy)


def test_verifier_preserves_explicit_fixture_policy():
    receipt = _issue()
    with pytest.raises(QualificationError, match="fixture"):
        verify(receipt, require_real=True)
    assert verify(receipt, require_real=False)["real_model_executed"] is False
