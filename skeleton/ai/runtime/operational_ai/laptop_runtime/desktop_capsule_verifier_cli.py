"""Read-only cold verification of a completed owner-private Jeeves capsule.

No original GGUF, project, SQLite session, or Git call is needed. Operator
supplies exact full final seal and capsule SHA-256 from the previous stage.
Malformed JSON, unknown authority and duplicate keys hold without disclosure.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import BinaryIO, TextIO

from .desktop_private_capsule import verify_private_capsule
from .desktop_workspace import _canonical

SCHEMA = "jeeves.workspace.cold-capsule-verification-cli.v1"
RESULT_SCHEMA = "jeeves.workspace.cold-capsule-verification-result.v1"
MAX_REQUEST_BYTES = 4096
_FIELDS = frozenset({
    "schema", "capsule_directory", "original_project_root",
    "expected_capsule_sha256", "expected_seal_sha256",
})


class CapsuleVerificationHold(ValueError):
    """Private capsule cannot be independently verified."""


def _pairs(pairs):
    observed = {}
    for key, value in pairs:
        if key in observed:
            raise CapsuleVerificationHold("duplicate cold capsule verifier field")
        observed[key] = value
    return observed


def _constant(_):
    raise CapsuleVerificationHold("nonfinite cold capsule verifier field")


def _sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def _absolute(value: object) -> str:
    if (
        type(value) is not str or "\x00" in value
        or not Path(value).is_absolute() or ".." in Path(value).parts
    ):
        raise CapsuleVerificationHold("canonical absolute capsule path required")
    return value


def parse_verification(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST_BYTES:
        raise CapsuleVerificationHold("bounded original source capsule verification needed")
    try:
        obj = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs, parse_constant=_constant,
        )
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise CapsuleVerificationHold("invalid cold capsule verifier request") from exc
    if type(obj) is not dict or set(obj) != _FIELDS or obj["schema"] != SCHEMA:
        raise CapsuleVerificationHold("incomplete source capsule verifier authority")
    _absolute(obj["capsule_directory"])
    _absolute(obj["original_project_root"])
    if not _sha(obj["expected_capsule_sha256"]) or not _sha(
        obj["expected_seal_sha256"]
    ):
        raise CapsuleVerificationHold("both full original SHA-256 values are required")
    return obj


def execute_verification(request: dict) -> dict[str, object]:
    if type(request) is not dict:
        raise CapsuleVerificationHold("typed exact capsule verifier request required")
    req = parse_verification(_canonical(request))
    receipt = verify_private_capsule(
        req["capsule_directory"],
        original_project_root=req["original_project_root"],
        expected_capsule_sha256=req["expected_capsule_sha256"],
        expected_seal_sha256=req["expected_seal_sha256"],
    )
    return {
        "schema": RESULT_SCHEMA,
        "status": "sealed-private-source-capsule-cold-verified",
        "verification": receipt,
        "source_contents_in_stdout": False,
        "source_code_executed": False,
        "model_or_git_invoked": False,
        "release_certified": False,
    }


def main(
    argv: list[str] | None = None, *,
    stdin: BinaryIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Verify all inert private source capsule bytes and SHA-256 seal",
    )
    parser.parse_args(argv)
    source = stdin if stdin is not None else sys.stdin.buffer
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    try:
        request = parse_verification(source.read(MAX_REQUEST_BYTES + 1))
        result = execute_verification(request)
        public = _canonical(result)
        if len(public) > 8192:
            raise CapsuleVerificationHold("oversize cold verifier receipt")
        out.write(public.decode("utf-8", "strict") + "\n")
        return 0
    except (Exception, KeyboardInterrupt):
        err.write("JEEVES_PRIVATE_CAPSULE_VERIFICATION_HELD\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "RESULT_SCHEMA", "CapsuleVerificationHold",
    "parse_verification", "execute_verification", "main",
]
