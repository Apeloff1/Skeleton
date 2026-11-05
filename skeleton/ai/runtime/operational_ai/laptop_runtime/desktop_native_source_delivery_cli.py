"""No-model terminal delivery of a cold-verified private Jeeves GGUF proposal.

This provides the last explicit source handoff: an operator selects ONE
previously saved owner-private original model proposal, confirms the full
source and patch SHA values, then writes either ONE new private source
overlay or ONE inert patch. Code is never passed through stdout or executed.

No native GGUF or SQLite worker is started or reissued, no model tools or
filesystem write rights are granted, and original project/Git is unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import BinaryIO, TextIO

from .desktop_native_source_delivery import (
    inspect_saved_native_source, deliver_saved_native_source,
)
from .desktop_workspace import _canonical

SCHEMA = "jeeves.workspace.native-escrow-delivery-cli.v1"
RESULT_SCHEMA = "jeeves.workspace.native-escrow-delivery-cli-result.v1"
MAX_REQUEST_BYTES = 8192
MAX_PUBLIC_BYTES = 65536
_ALLOWED = frozenset(("review", "stage", "export-patch"))
_FIELDS = frozenset({
    "schema", "action", "project_root", "saved_proposal_file",
    "expected_saved_file_sha256", "expected_saved_file_bytes",
    "expected_job_sha256", "target",
    "source_manifest_sha256", "source_patch_sha256",
})


class NativeSourceDeliveryCLIHold(ValueError):
    """The operator's private saved source was not safely approved."""


def _digest(x: object) -> bool:
    return (
        type(x) is str and len(x) == 64
        and all(c in "0123456789abcdef" for c in x)
    )


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise NativeSourceDeliveryCLIHold("duplicate private source request")
        out[key] = value
    return out


def _nonfinite(_):
    raise NativeSourceDeliveryCLIHold("nonfinite source-delivery request value")


def _abs(value: object) -> str:
    if (
        type(value) is not str or not value or "\x00" in value
        or not Path(value).is_absolute() or ".." in Path(value).parts
    ):
        raise NativeSourceDeliveryCLIHold("canonical selected private source path required")
    return value


def parse_delivery_request(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST_BYTES:
        raise NativeSourceDeliveryCLIHold("bounded private source delivery JSON required")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs, parse_constant=_nonfinite,
        )
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise NativeSourceDeliveryCLIHold(
            "untrusted model proposal delivery JSON",
        ) from exc
    if type(value) is not dict or frozenset(value) != _FIELDS:
        raise NativeSourceDeliveryCLIHold(
            "incomplete or unexpected model source-delivery authority",
        )
    if (
        value["schema"] != SCHEMA
        or type(value["action"]) is not str
        or value["action"] not in _ALLOWED
    ):
        raise NativeSourceDeliveryCLIHold("unsupported source-delivery action")
    _abs(value["project_root"])
    _abs(value["saved_proposal_file"])
    if (
        not _digest(value["expected_saved_file_sha256"])
        or not _digest(value["expected_job_sha256"])
        or type(value["expected_saved_file_bytes"]) is not int
        or not 1 <= value["expected_saved_file_bytes"] <= 32768
    ):
        raise NativeSourceDeliveryCLIHold("saved private source lacks exact original digest")
    if value["action"] == "review":
        if any(
            value[k] is not None
            for k in ("target", "source_manifest_sha256", "source_patch_sha256")
        ):
            raise NativeSourceDeliveryCLIHold("read-only review cannot carry private write grant")
    else:
        _abs(value["target"])
        if (
            not _digest(value["source_manifest_sha256"])
            or not _digest(value["source_patch_sha256"])
        ):
            raise NativeSourceDeliveryCLIHold(
                "full SHA-256 source AND Git patch approval required",
            )
    return value


def execute_delivery_request(
    request: dict,
    *, approve_private_stage: bool = False,
    approve_private_patch: bool = False,
) -> dict[str, object]:
    if (
        type(request) is not dict
        or type(approve_private_stage) is not bool
        or type(approve_private_patch) is not bool
    ):
        raise NativeSourceDeliveryCLIHold("typed original delivery/approval required")
    req = parse_delivery_request(_canonical(request))
    kind = req["action"]
    if kind != "stage" and approve_private_stage:
        raise NativeSourceDeliveryCLIHold("unrequested private source stage grant")
    if kind != "export-patch" and approve_private_patch:
        raise NativeSourceDeliveryCLIHold("unrequested private patch grant")
    if kind == "stage" and not approve_private_stage:
        raise NativeSourceDeliveryCLIHold("explicit CLI stage consent required")
    if kind == "export-patch" and not approve_private_patch:
        raise NativeSourceDeliveryCLIHold("explicit CLI patch consent required")
    # Parse and reread owner-private source plus real original project through
    # exact SHA, inode/permissions and syntax/import graph checks, every time.
    reviewed = inspect_saved_native_source(
        req["saved_proposal_file"],
        project_root=req["project_root"],
        expected_file_sha256=req["expected_saved_file_sha256"],
        expected_file_bytes=req["expected_saved_file_bytes"],
        expected_job_sha256=req["expected_job_sha256"],
    )
    status = "reviewed-cold-source-no-private-write"
    done = None
    if kind != "review":
        if (
            reviewed.source_manifest_sha256 != req["source_manifest_sha256"]
            or reviewed.patch_sha256 != req["source_patch_sha256"]
        ):
            raise NativeSourceDeliveryCLIHold(
                "separately approved full source and patch SHA changed",
            )
        done = deliver_saved_native_source(
            reviewed, req["target"], action=kind,
            expected_manifest_sha256=req["source_manifest_sha256"],
            expected_patch_sha256=req["source_patch_sha256"],
            approve_private_stage=approve_private_stage,
            approve_private_patch=approve_private_patch,
        )
        status = "private-original-source-delivered-no-model-or-Git"
    result = {
        "schema": RESULT_SCHEMA,
        "action": kind,
        "status": status,
        "review": reviewed.public_review(),
        "delivery": done,
        "generated_source_in_stdout": False,
        "native_inference_executed": False,
        "original_project_modified": False,
        "git_commands_executed": False,
        "source_code_executed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_PUBLIC_BYTES:
        raise NativeSourceDeliveryCLIHold("private source receipt exceeds public byte ceiling")
    return result


class _PrivateParser(argparse.ArgumentParser):
    def error(self, _message):
        raise NativeSourceDeliveryCLIHold("invalid private source-delivery argument")


def main(
    argv: list[str] | None = None, *, source: BinaryIO | None = None,
    output: TextIO | None = None, errors: TextIO | None = None,
) -> int:
    parser = _PrivateParser(
        prog="jeeves-source-delivery",
        description=(
            "No-model owner-private source/patch review and delivery "
            "from a previously committed GGUF source escrow."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--approve-private-stage", action="store_true",
        help="Permit one NEW source overlay outside original checkout",
    )
    parser.add_argument(
        "--approve-private-patch", action="store_true",
        help="Permit one NEW inert Git patch file; never invoke Git",
    )
    stdin = sys.stdin.buffer if source is None else source
    out = sys.stdout if output is None else output
    err = sys.stderr if errors is None else errors
    try:
        args = parser.parse_args(argv)
        req = parse_delivery_request(stdin.read(MAX_REQUEST_BYTES + 1))
        result = execute_delivery_request(
            req,
            approve_private_stage=args.approve_private_stage,
            approve_private_patch=args.approve_private_patch,
        )
        out.write(_canonical(result).decode("utf-8", "strict") + "\n")
        return 0
    except (ValueError, OSError, RuntimeError, TypeError, UnicodeError) as exc:
        err.write(
            "Jeeves saved native source delivery held: "
            + type(exc).__name__
            + "; no model retry, code execution or automatic Git write.\n",
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "RESULT_SCHEMA", "NativeSourceDeliveryCLIHold",
    "parse_delivery_request", "execute_delivery_request", "main",
]
