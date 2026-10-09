"""Read-only deterministic replay of local model-improvement evidence.

The operator provides the original and candidate content-addressed native
checkpoints, explicit train/eval text, and the previously printed JSON
receipt. This verifier performs REAL retraining into a disposable scratch
directory, then compares the full authenticated model/artifact identities and
training statistics. It never rewrites either user checkpoint or self-promotes
a model. A matching receipt is a narrow reproducibility statement, not an
independent review or general-purpose model quality certification.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
from typing import Any

from skeleton.ai.runtime.inference.artifact import load_local_model_artifact
from skeleton.app.local_ai import load_native_checkpoint
from skeleton.app.local_ai_improvement import (
    OfflineImprovementReceipt,
    improve_local_model,
)

MAX_RECEIPT_BYTES = 24 * 1024
DIGEST_FIELDS = (
    "parent_model_digest", "candidate_model_digest", "tokenizer_digest",
    "train_source_sha256", "validation_source_sha256",
    "input_checkpoint_sha256", "checkpoint_sha256",
)


class OfflineReplayError(ValueError):
    """Native model improvement cannot be reproduced from supplied evidence."""


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    item: dict[str, Any] = {}
    for key, value in pairs:
        if key in item:
            raise OfflineReplayError("duplicate improvement receipt field")
        item[key] = value
    return item


def _reject_constant(_: str) -> None:
    raise OfflineReplayError("nonfinite improvement receipt value")


def _read_receipt(path: str | Path) -> tuple[bytes, dict[str, Any]]:
    candidate = Path(path)
    try:
        info = candidate.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_RECEIPT_BYTES:
            raise OfflineReplayError("receipt must be a bounded regular JSON file")
        descriptor = os.open(
            candidate,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
        )
        with os.fdopen(descriptor, "rb") as stream:
            current = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(current.st_mode)
                or current.st_size > MAX_RECEIPT_BYTES
                or (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino)
            ):
                raise OfflineReplayError("receipt identity changed during open")
            raw = stream.read(MAX_RECEIPT_BYTES + 1)
            if len(raw) != current.st_size or os.fstat(stream.fileno()).st_size != current.st_size:
                raise OfflineReplayError("receipt changed during reading")
    except OSError as exc:
        raise OfflineReplayError("cannot read bounded improvement receipt") from exc
    try:
        item = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise OfflineReplayError("invalid UTF-8 JSON improvement receipt") from exc
    if not isinstance(item, dict) or item.get("schema_version") != 1:
        raise OfflineReplayError("unsupported improvement receipt schema")
    mandatory = {
        "schema_version", "parent_model_digest", "candidate_model_digest",
        "tokenizer_digest", "train_source_sha256", "validation_source_sha256",
        "input_checkpoint_sha256", "checkpoint_sha256", "baseline_perplexity",
        "accepted_perplexity", "heldout_perplexity_reduction",
        "heldout_improvement_percent", "best_epoch", "attempted_epochs",
        "training_steps", "validation_tokens", "new_checkpoint_only",
        "rollback_checkpoint_retained", "hosted_provider_used",
        "independent_quality_certification", "protected_suite_digest",
        "protected_suite_passed", "protected_suite_cases",
    }
    if set(item) != mandatory:
        raise OfflineReplayError("improvement receipt has missing or unknown fields")
    for field in DIGEST_FIELDS:
        digest = item[field]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise OfflineReplayError("malformed content digest in improvement receipt")
    for field in ("attempted_epochs", "best_epoch", "training_steps", "validation_tokens"):
        if type(item[field]) is not int or item[field] < 1:
            raise OfflineReplayError("invalid improvement receipt integer")
    if item["attempted_epochs"] > 4 or item["best_epoch"] > item["attempted_epochs"]:
        raise OfflineReplayError("receipt training epochs out of bounded range")
    for key in (
        "baseline_perplexity", "accepted_perplexity",
        "heldout_perplexity_reduction", "heldout_improvement_percent",
    ):
        value = item[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise OfflineReplayError("non-finite or nonnumeric receipt metric")
    if any(item[k] is not expected for k, expected in (
        ("new_checkpoint_only", True),
        ("rollback_checkpoint_retained", True),
        ("hosted_provider_used", False),
        ("independent_quality_certification", False),
    )):
        raise OfflineReplayError("invalid claimed model publication authority")
    if type(item["protected_suite_passed"]) is not bool:
        raise OfflineReplayError("protected benchmark boolean invalid")
    if type(item["protected_suite_cases"]) is not int or item["protected_suite_cases"] < 0:
        raise OfflineReplayError("protected benchmark count invalid")
    protected_hash = item["protected_suite_digest"]
    if protected_hash is not None and (
        not isinstance(protected_hash, str)
        or len(protected_hash) != 64
        or any(ch not in "0123456789abcdef" for ch in protected_hash)
    ):
        raise OfflineReplayError("protected suite digest invalid")
    if bool(protected_hash) != item["protected_suite_passed"]:
        raise OfflineReplayError("protected benchmark claim inconsistent")
    return raw, item


def replay_local_improvement(
    receipt_path: str | Path,
    parent_path: str | Path,
    candidate_path: str | Path,
    training_text: str | Path,
    validation_text: str | Path,
    *,
    protected_suite: str | Path | None = None,
) -> dict[str, Any]:
    """Replay an accepted improvement to fresh native weights and verify all facts."""
    raw, expected = _read_receipt(receipt_path)
    if expected["protected_suite_passed"] != (protected_suite is not None):
        raise OfflineReplayError("protected benchmark source required exactly when receipt declares it")
    parent = load_local_model_artifact(parent_path)
    contender = load_local_model_artifact(candidate_path)
    base_model = load_native_checkpoint(parent_path)
    candidate_model = load_native_checkpoint(candidate_path)
    if (
        base_model.model_digest != expected["parent_model_digest"]
        or parent.receipt.artifact_sha256 != expected["input_checkpoint_sha256"]
        or candidate_model.model_digest != expected["candidate_model_digest"]
        or contender.receipt.artifact_sha256 != expected["checkpoint_sha256"]
        or base_model.tokenizer_digest != expected["tokenizer_digest"]
        or candidate_model.tokenizer_digest != expected["tokenizer_digest"]
    ):
        raise OfflineReplayError("checkpoint identity does not match signed-in-data receipt")
    with tempfile.TemporaryDirectory(prefix="skeleton-native-replay-") as directory:
        scratch = Path(directory) / "reproduced-native.json"
        try:
            replayed: OfflineImprovementReceipt = improve_local_model(
                parent_path, training_text, validation_text, scratch,
                epochs=expected["attempted_epochs"],
                protected_suite=protected_suite,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            raise OfflineReplayError("independent checkpoint regeneration failed") from exc
        if replayed.to_dict() != expected:
            raise OfflineReplayError("deterministic native training replay evidence mismatch")
        reread = load_local_model_artifact(scratch)
        if (
            reread.receipt.artifact_sha256 != contender.receipt.artifact_sha256
            or reread.receipt.model_digest != candidate_model.model_digest
        ):
            raise OfflineReplayError("replayed native weights differ from accepted checkpoint")
    return {
        "schema": "skeleton.ai.local_improvement.replay.v1",
        "reproducible": True,
        "receipt_sha256": hashlib.sha256(raw).hexdigest(),
        "parent_model_digest": base_model.model_digest,
        "candidate_model_digest": candidate_model.model_digest,
        "replayed_artifact_sha256": contender.receipt.artifact_sha256,
        "protected_suite_digest": replayed.protected_suite_digest,
        "verification": "local deterministic CPU replay; no independent release certification",
        "model_promoted": False,
        "model_quality_certified": False,
    }
