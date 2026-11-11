"""Read-only structural verification of operator-issued qualification receipts."""
from __future__ import annotations

from hashlib import sha256

from ...orchestration.execution_spine.contracts import SpineError, canonical, hexdigest
from .contracts import QualificationError

FIELDS = frozenset({
    "schema", "model_sha256", "tokenizer_sha256", "session_sha256",
    "request_id_sha256", "request_sha256", "output_sha256",
    "transcript_sha256", "revision", "generated_tokens", "prompt_tokens",
    "context_sha256", "replay_without_regeneration", "database_turns",
    "checkpoint_execution_mode", "status", "proof_sha256",
})

DIGEST_FIELDS = (
    "model_sha256", "tokenizer_sha256", "session_sha256",
    "request_id_sha256", "request_sha256", "output_sha256",
    "transcript_sha256", "context_sha256", "proof_sha256",
)


def verify(record: dict, *, require_real: bool = True) -> dict:
    # A dict with string-subclass keys or values can override equality checks.
    # Only exact built-in types may authorize real-model provenance. Check key
    # types before comparing them to the allowlisted schema names.
    if (type(record) is not dict
            or len(record) != len(FIELDS)
            or any(type(key) is not str for key in record)
            or set(record) != FIELDS):
        raise QualificationError("qualification report schema mismatch")
    if (type(record["schema"]) is not str
            or record["schema"] != "skeleton.ai.first-boot-qualification.v1"):
        raise QualificationError("unknown qualification report schema")

    try:
        for key in DIGEST_FIELDS:
            if type(record[key]) is not str:
                raise QualificationError("invalid qualification digest")
            hexdigest(record[key], key)
    except SpineError:
        raise QualificationError("invalid qualification digest") from None

    # Prove exactly one committed turn at revision one. Bound every integer
    # before canonicalizing, so huge or subclassed numeric values are denied.
    numeric_bounds = {
        "revision": (1, 1),
        "database_turns": (1, 1),
        "generated_tokens": (0, 8192),
        "prompt_tokens": (0, 131072),
    }
    for key, (minimum, maximum) in numeric_bounds.items():
        value = record[key]
        if type(value) is not int or not minimum <= value <= maximum:
            raise QualificationError("invalid numeric qualification evidence")
    if record["replay_without_regeneration"] is not True:
        raise QualificationError("restart replay was not proven")

    mode, status = record["checkpoint_execution_mode"], record["status"]
    if type(mode) is not str or type(status) is not str:
        raise QualificationError("unsupported checkpoint execution provenance")
    is_real = (
        mode == "actual-gguf-llama-cpp"
        and status == "real-first-boot-replay-probe-not-release-certified"
    )
    is_fixture = (
        mode == "injected-test-double"
        and status == "fixture-only-not-production-certified"
    )
    if not (is_real or is_fixture):
        raise QualificationError("unsupported checkpoint execution provenance")
    if require_real and not is_real:
        raise QualificationError("fixture cannot satisfy real-model qualification")

    try:
        expected = sha256(canonical({
            key: value for key, value in record.items()
            if key != "proof_sha256"
        })).hexdigest()
    except SpineError:
        raise QualificationError("invalid qualification report payload") from None
    if expected != record["proof_sha256"]:
        raise QualificationError("qualification proof digest mismatch")

    # Structural verification is never external attestation or release proof.
    return {
        "status": "structurally-valid-receipt-no-external-attestation",
        "real_model_executed": is_real,
        "proof_sha256": expected,
    }
