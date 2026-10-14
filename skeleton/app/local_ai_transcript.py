"""Explicit, bounded, offline export/import of local AI conversation snapshots.

This is a user-controlled portable projection, NOT the canonical durable
assistant/operation ledger. It grants no model or tool authority. Transcripts
are plain text on disk; their digest detects accidental changes, not forgery.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Sequence


SNAPSHOT_SCHEMA = "skeleton.app.local_ai.transcript.v1"
MAX_TRANSCRIPT_BYTES = 192 * 1024
MAX_MESSAGES = 16
MAX_USER_CHARS = 4096
MAX_ASSISTANT_CHARS = 16384


class LocalTranscriptError(ValueError):
    """A transcript is unsafe, corrupt, too large, or belongs to another model."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (UnicodeError, TypeError, ValueError) as exc:
        raise LocalTranscriptError("transcript contains nonportable JSON data") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _pairs(rows: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
    if not isinstance(rows, (tuple, list)) or len(rows) > MAX_MESSAGES or len(rows) % 2:
        raise LocalTranscriptError("transcript must contain at most 8 complete turns")
    messages: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        expected = "user" if index % 2 == 0 else "assistant"
        if not isinstance(row, (tuple, list)) or len(row) != 2 or row[0] != expected:
            raise LocalTranscriptError("transcript roles must alternate as complete user/assistant turns")
        text = row[1]
        limit = MAX_USER_CHARS if expected == "user" else MAX_ASSISTANT_CHARS
        if not isinstance(text, str) or not text.strip() or len(text) > limit:
            raise LocalTranscriptError("transcript message is empty or exceeds its text budget")
        messages.append({"role": expected, "text": text})
    return messages


def _assert_digest(value: str, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise LocalTranscriptError("invalid " + label + " identity")


def encode_transcript(
    *, model_digest: str, tokenizer_digest: str, history: Sequence[tuple[str, str]],
) -> bytes:
    """Serialize a model-bound, digest-checked snapshot (no credentials/tools)."""
    _assert_digest(model_digest, "model")
    _assert_digest(tokenizer_digest, "tokenizer")
    body: dict[str, Any] = {
        "schema": SNAPSHOT_SCHEMA,
        "model_digest": model_digest,
        "tokenizer_digest": tokenizer_digest,
        "messages": _pairs(history),
    }
    result = {**body, "digest": _digest(body)}
    data = _canonical(result) + b"\n"
    if len(data) > MAX_TRANSCRIPT_BYTES:
        raise LocalTranscriptError("transcript exceeds byte budget")
    return data


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LocalTranscriptError("duplicate transcript field")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise LocalTranscriptError("non-finite transcript number")


def decode_transcript(
    raw: bytes, *, model_digest: str, tokenizer_digest: str,
) -> tuple[tuple[str, str], ...]:
    _assert_digest(model_digest, "model")
    _assert_digest(tokenizer_digest, "tokenizer")
    if not isinstance(raw, bytes) or len(raw) > MAX_TRANSCRIPT_BYTES:
        raise LocalTranscriptError("transcript exceeds byte budget")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise LocalTranscriptError("transcript is invalid UTF-8 JSON") from exc
    if not isinstance(obj, dict) or set(obj) != {"schema", "model_digest", "tokenizer_digest", "messages", "digest"}:
        raise LocalTranscriptError("invalid transcript envelope fields")
    if obj["schema"] != SNAPSHOT_SCHEMA:
        raise LocalTranscriptError("unsupported transcript schema")
    if obj["model_digest"] != model_digest or obj["tokenizer_digest"] != tokenizer_digest:
        raise LocalTranscriptError("transcript belongs to a different model/tokenizer")
    _assert_digest(obj["digest"], "transcript")
    body = {key: value for key, value in obj.items() if key != "digest"}
    if _digest(body) != obj["digest"]:
        raise LocalTranscriptError("transcript content digest mismatch")
    rows = obj["messages"]
    if not isinstance(rows, list):
        raise LocalTranscriptError("transcript messages must be an array")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"role", "text"}:
            raise LocalTranscriptError("invalid transcript message fields")
    history = tuple((row["role"], row["text"]) for row in rows)
    _pairs(history)
    return history


def load_transcript(
    path: str | Path, *, model_digest: str, tokenizer_digest: str,
) -> tuple[tuple[str, str], ...]:
    """Reject symlinks/devices and check file size before bounded IO."""
    target = Path(path)
    try:
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_TRANSCRIPT_BYTES:
            raise LocalTranscriptError("transcript must be a bounded regular file")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(target, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_size > MAX_TRANSCRIPT_BYTES
                or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)
            ):
                raise LocalTranscriptError("transcript changed during secure open")
            raw = stream.read(MAX_TRANSCRIPT_BYTES + 1)
            if (
                len(raw) != opened.st_size
                or os.fstat(stream.fileno()).st_size != opened.st_size
            ):
                raise LocalTranscriptError("transcript changed while reading")
    except OSError as exc:
        raise LocalTranscriptError("cannot read local transcript") from exc
    return decode_transcript(raw, model_digest=model_digest, tokenizer_digest=tokenizer_digest)


def save_transcript(
    path: str | Path, *, model_digest: str, tokenizer_digest: str,
    history: Sequence[tuple[str, str]],
) -> str:
    """Atomically write a private file and return its content digest."""
    raw = encode_transcript(model_digest=model_digest, tokenizer_digest=tokenizer_digest, history=history)
    target = Path(path)
    temporary: str | None = None
    try:
        # Refuse existing symlink/other nonregular paths. os.replace is atomic
        # within one directory and never resolves a symlink destination.
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise LocalTranscriptError("transcript destination must be a regular file")
        if target.exists():
            # Never overwrite a checkpoint, unrelated JSON, or another model's
            # chat merely because the operator selected the wrong filename.
            load_transcript(
                target, model_digest=model_digest, tokenizer_digest=tokenizer_digest,
            )
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".skeleton-local-chat-", suffix=".tmp",
            dir=target.parent, delete=False,
        ) as out:
            temporary = out.name
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, target)
        temporary = None
    except OSError as exc:
        raise LocalTranscriptError("cannot save local transcript") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return hashlib.sha256(raw).hexdigest()
