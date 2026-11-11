"""Privacy-preserving, bounded qualification evidence; never a model quality claim."""
from __future__ import annotations

import hashlib

from ...orchestration.execution_spine.contracts import (
    SpineError, canonical, hexdigest, identifier,
)
from .contracts import QualificationError

# The canonical execution-spine serializer has a 1 MiB output ceiling.
# Validate transcript text before encoding/hashing it, including direct calls
# that bypass the production runner's SpineLimits.
_MAX_TRANSCRIPT_BYTES = 1_048_576


def _validated_transcript(history: tuple[dict, ...]) -> bytes:
    """Return the assistant's bounded bytes after checking both durable turns."""
    if type(history) is not tuple or len(history) != 2:
        raise QualificationError("committed transcript did not replay exactly")
    total = 0
    assistant_bytes = b""
    for expected_role, entry in zip(("user", "assistant"), history):
        if (type(entry) is not dict or len(entry) != 2
                or "role" not in entry or "content" not in entry
                or type(entry["role"]) is not str
                or entry["role"] != expected_role):
            raise QualificationError("committed transcript did not replay exactly")
        content = entry["content"]
        if type(content) is not str or len(content) > _MAX_TRANSCRIPT_BYTES:
            raise QualificationError("invalid bounded qualification transcript")
        try:
            encoded = content.encode("utf8")
        except UnicodeError:
            raise QualificationError("invalid bounded qualification transcript") from None
        total += len(encoded)
        if total > _MAX_TRANSCRIPT_BYTES:
            raise QualificationError("invalid bounded qualification transcript")
        if expected_role == "assistant":
            assistant_bytes = encoded
    return assistant_bytes


def construct(
    model: str,
    tokenizer: str,
    session: str,
    request: str,
    first: dict,
    replayed: dict,
    history: tuple[dict, ...],
    diagnostics: dict,
    *,
    exact_native: bool,
) -> dict:
    # Bound all caller-controlled identities before encode() or canonical().
    if type(model) is not str or type(tokenizer) is not str:
        raise QualificationError("invalid qualification digest")
    try:
        hexdigest(model, "model digest")
        hexdigest(tokenizer, "tokenizer digest")
    except SpineError:
        raise QualificationError("invalid qualification digest") from None
    if type(session) is not str or type(request) is not str:
        raise QualificationError("invalid qualification identity")
    try:
        identifier(session, "session")
        identifier(request, "request")
    except SpineError:
        raise QualificationError("invalid qualification identity") from None
    if type(exact_native) is not bool:
        raise QualificationError("qualification backend proof missing")
    if type(first) is not dict or type(replayed) is not dict:
        raise QualificationError("missing inference receipts")
    if first.get("replayed") is not False or replayed.get("replayed") is not True:
        raise QualificationError("restarted invocation did not prove replay")
    if (type(first.get("revision")) is not int or first["revision"] != 1
            or type(replayed.get("revision")) is not int
            or replayed["revision"] != 1):
        raise QualificationError("replay changed conversation revision")
    for key, ceiling in (("generated_tokens", 8192), ("prompt_tokens", 131072)):
        value = first.get(key)
        if type(value) is not int or not 0 <= value <= ceiling:
            raise QualificationError("invalid numeric qualification evidence")
    try:
        for key in ("request_sha256", "output_sha256", "context_sha256"):
            hexdigest(first.get(key), key)
    except SpineError:
        raise QualificationError("invalid qualification digest") from None
    if first.get("output_sha256") != replayed.get("output_sha256"):
        raise QualificationError("inference output changed across restart")
    if first.get("request_sha256") != replayed.get("request_sha256"):
        raise QualificationError("request identity changed across restart")

    assistant_bytes = _validated_transcript(history)
    if hashlib.sha256(assistant_bytes).hexdigest() != first["output_sha256"]:
        raise QualificationError("durable output does not match generation receipt")
    if (type(diagnostics) is not dict or type(diagnostics.get("turns")) is not int
            or diagnostics["turns"] != 1):
        raise QualificationError("database integrity doctor did not prove the turn")
    try:
        transcript_digest = hashlib.sha256(canonical(history)).hexdigest()
    except SpineError:
        raise QualificationError("invalid bounded qualification transcript") from None

    proof = {
        "schema": "skeleton.ai.first-boot-qualification.v1",
        "model_sha256": model,
        "tokenizer_sha256": tokenizer,
        "session_sha256": hashlib.sha256(session.encode("ascii")).hexdigest(),
        "request_id_sha256": hashlib.sha256(request.encode("ascii")).hexdigest(),
        "request_sha256": first["request_sha256"],
        "output_sha256": first["output_sha256"],
        "transcript_sha256": transcript_digest,
        "revision": first["revision"],
        "generated_tokens": first["generated_tokens"],
        "prompt_tokens": first["prompt_tokens"],
        "context_sha256": first["context_sha256"],
        "replay_without_regeneration": True,
        "database_turns": diagnostics["turns"],
        "checkpoint_execution_mode": (
            "actual-gguf-llama-cpp" if exact_native else "injected-test-double"
        ),
        "status": (
            "real-first-boot-replay-probe-not-release-certified"
            if exact_native else "fixture-only-not-production-certified"
        ),
    }
    try:
        proof["proof_sha256"] = hashlib.sha256(canonical(proof)).hexdigest()
    except SpineError:
        raise QualificationError("invalid qualification proof") from None
    return proof
