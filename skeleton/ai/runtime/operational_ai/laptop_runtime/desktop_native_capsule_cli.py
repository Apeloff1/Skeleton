"""Strict headless cold GGUF escrow -> selected-source capsule CLI.

Input is a finite, duplicate-rejecting JSON request. "inspect" is read-only;
"publish" additionally needs a full capsule SHA, complete original source
and patch SHA, and a separate terminal --approve-private-capsule flag.
Normal stdout never contains generated source or absolute private paths.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import BinaryIO, TextIO

from .desktop_native_source_delivery import inspect_saved_native_source
from .desktop_private_capsule import (
    prepare_private_capsule, publish_private_capsule,
)
from .desktop_workspace import _canonical

SCHEMA = "jeeves.workspace.native-private-source-capsule-cli.v1"
RESULT_SCHEMA = "jeeves.workspace.native-private-source-capsule-result.v1"
MAX_REQUEST_BYTES = 16384
MAX_PUBLIC_BYTES = 65536
_FIELDS = frozenset({
    "schema", "action", "project_root", "saved_proposal_file",
    "expected_saved_file_sha256", "expected_saved_file_bytes",
    "expected_job_sha256", "selected_sources", "target",
    "source_manifest_sha256", "source_patch_sha256",
    "capsule_sha256",
})


class PrivateCapsuleCLIHold(ValueError):
    """Requested operator authority is malformed, stale or missing."""


def _digest(raw: object) -> bool:
    return type(raw) is str and len(raw) == 64 and all(
        ch in "0123456789abcdef" for ch in raw
    )


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PrivateCapsuleCLIHold("duplicate source capsule authority")
        result[key] = value
    return result


def _nonfinite(_):
    raise PrivateCapsuleCLIHold("nonfinite source capsule request")


def _absolute(value: object) -> str:
    if (
        type(value) is not str or not value or "\x00" in value
        or not Path(value).is_absolute() or ".." in Path(value).parts
    ):
        raise PrivateCapsuleCLIHold("selected source capsule path must be canonical")
    return value


def parse_capsule_request(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST_BYTES:
        raise PrivateCapsuleCLIHold("bounded source capsule JSON request required")
    try:
        obj = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=_pairs,
            parse_constant=_nonfinite,
        )
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise PrivateCapsuleCLIHold("invalid source capsule request") from exc
    if type(obj) is not dict or frozenset(obj) != _FIELDS:
        raise PrivateCapsuleCLIHold("unrecognized or incomplete capsule authority")
    if obj["schema"] != SCHEMA or obj["action"] not in ("inspect", "publish"):
        raise PrivateCapsuleCLIHold("unsupported source capsule action")
    _absolute(obj["project_root"])
    _absolute(obj["saved_proposal_file"])
    if (
        not _digest(obj["expected_saved_file_sha256"])
        or not _digest(obj["expected_job_sha256"])
        or type(obj["expected_saved_file_bytes"]) is not int
        or not 1 <= obj["expected_saved_file_bytes"] <= 32768
        or type(obj["selected_sources"]) is not str
        or not 1 <= len(obj["selected_sources"].encode("utf-8", "strict")) <= 4096
    ):
        raise PrivateCapsuleCLIHold("original native escrow/selection identity missing")
    if obj["action"] == "inspect":
        if any(
            obj[k] is not None for k in (
                "target", "source_manifest_sha256",
                "source_patch_sha256", "capsule_sha256",
            )
        ):
            raise PrivateCapsuleCLIHold("read-only capsule inspection has no write grant")
    else:
        _absolute(obj["target"])
        if any(not _digest(obj[k]) for k in (
            "source_manifest_sha256", "source_patch_sha256", "capsule_sha256",
        )):
            raise PrivateCapsuleCLIHold("all three full SHA-256 approvals required")
    return obj


def execute_capsule_request(request: dict, *,
                            approve_private_capsule: bool = False) -> dict[str, object]:
    if type(request) is not dict or type(approve_private_capsule) is not bool:
        raise PrivateCapsuleCLIHold("strict original capsule request and approval needed")
    req = parse_capsule_request(_canonical(request))
    if (req["action"] == "inspect" and approve_private_capsule) or (
        req["action"] == "publish" and not approve_private_capsule
    ):
        raise PrivateCapsuleCLIHold("separate action-specific capsule consent required")
    # Every invocation COLD-verifies original encrypted/private escrow and
    # rereads the current project source. No native GGUF/SQLite is restarted.
    reviewed = inspect_saved_native_source(
        req["saved_proposal_file"],
        project_root=req["project_root"],
        expected_file_sha256=req["expected_saved_file_sha256"],
        expected_file_bytes=req["expected_saved_file_bytes"],
        expected_job_sha256=req["expected_job_sha256"],
    )
    capsule = prepare_private_capsule(
        reviewed.source_plan, req["selected_sources"],
    )
    receipt = None
    if req["action"] == "publish":
        if (
            reviewed.source_manifest_sha256 != req["source_manifest_sha256"]
            or reviewed.patch_sha256 != req["source_patch_sha256"]
            or capsule.capsule_sha256 != req["capsule_sha256"]
        ):
            raise PrivateCapsuleCLIHold("original capsule and patch digests changed")
        receipt = publish_private_capsule(
            capsule, req["target"],
            expected_capsule_sha256=req["capsule_sha256"],
            expected_manifest_sha256=req["source_manifest_sha256"],
            expected_patch_sha256=req["source_patch_sha256"],
            approve_private_capsule=True,
        )
    return {
        "schema": RESULT_SCHEMA,
        "action": req["action"],
        "status": (
            "read-only-selected-source-capsule-reviewed"
            if req["action"] == "inspect"
            else "owner-private-selected-source-capsule-sealed"
        ),
        "saved_proposal_sha256": reviewed.private_file_sha256,
        "original_job_sha256": reviewed.job_sha256,
        "original_model_sha256": reviewed.model_sha256,
        "review": capsule.public_review(),
        "publication": receipt,
        "native_inference_executed": False,
        "new_model_request_issued": False,
        "source_code_executed": False,
        "original_project_modified": False,
        "generated_source_in_stdout": False,
        "release_certified": False,
    }


def main(
    argv: list[str] | None = None, *,
    stdin: BinaryIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Cold verify private GGUF source and prepare a sealed selected-source capsule",
    )
    parser.add_argument("--approve-private-capsule", action="store_true")
    args = parser.parse_args(argv)
    source = stdin if stdin is not None else sys.stdin.buffer
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    try:
        raw = source.read(MAX_REQUEST_BYTES + 1)
        request = parse_capsule_request(raw)
        receipt = execute_capsule_request(
            request, approve_private_capsule=args.approve_private_capsule,
        )
        encoded = _canonical(receipt)
        if len(encoded) > MAX_PUBLIC_BYTES:
            raise PrivateCapsuleCLIHold("private capsule public receipt too large")
        out.write(encoded.decode("utf-8", "strict") + "\n")
        return 0
    except (Exception, KeyboardInterrupt):
        # Do not leak private model tokens, source text, original paths or
        # confidential proposal data in a terminal exception traceback.
        err.write("JEEVES_PRIVATE_SOURCE_CAPSULE_HELD\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "RESULT_SCHEMA", "PrivateCapsuleCLIHold",
    "parse_capsule_request", "execute_capsule_request", "main",
]
