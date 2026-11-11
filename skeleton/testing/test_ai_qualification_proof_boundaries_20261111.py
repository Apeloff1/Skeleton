"""Adversarial first-boot receipt preflight, independent of a native GGUF."""
import hashlib
import json
from pathlib import Path
from unittest import mock

import pytest

from skeleton.ai.runtime.operational_ai.deployment.qualification.contracts import (
    QualificationError,
)
from skeleton.ai.runtime.operational_ai.deployment.qualification import paths, proof
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
