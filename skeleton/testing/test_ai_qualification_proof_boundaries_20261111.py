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
