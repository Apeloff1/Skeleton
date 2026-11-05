"""No-source-stdout handoff from real local GGUF to private reviewed source.

One bounded strict JSON request drives either:
- generate-save: operator-approved fresh native SQLite source work followed
  by a separately approved no-clobber 0600 private proposal escrow; or
- verify: cold read-only verification (optionally recheck original files)
  without loading GGUF or recreating a native request.

The caller must FIRST inspect the original job through desktop_native_code_cli.
There are no hidden tools, project write grants, automatic pending-state
restarts, source execution, Git operations or stdout source disclosures.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import BinaryIO, Callable, TextIO

from .desktop_client import DesktopBridge
from .desktop_native_code_cli import (
    SCHEMA as NATIVE_REQUEST_SCHEMA,
    parse_native_request,
    execute_native_request,
)
from .desktop_native_proposal_custody import (
    _target, publish_private_proposal, verify_private_proposal,
)
from .desktop_patch_export import (
    PatchExportHold, _pinned_private_directory, _identical_parent,
)
from .desktop_workspace import _canonical

SCHEMA = "jeeves.desktop.native-source-escrow-cli.v1"
RESULT_SCHEMA = "jeeves.desktop.native-source-escrow-cli-result.v1"
MAX_INPUT_BYTES = 24576
MAX_OUTPUT_BYTES = 32768
_FIELDS = frozenset({
    "schema", "action", "project_root", "target",
    "native_request", "expected_job_sha256",
    "expected_file_sha256", "expected_file_bytes",
    "recheck_original_source",
})
_ACTIONS = frozenset({"generate-save", "verify"})


class NativeProposalEscrowCLIHold(ValueError):
    """Explicit source model-to-private custody operation is unsafe."""


def _digest(v: object) -> bool:
    return (
        type(v) is str and len(v) == 64
        and all(ch in "0123456789abcdef" for ch in v)
    )


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise NativeProposalEscrowCLIHold("duplicate private native escrow JSON key")
        result[key] = value
    return result


def _nonfinite(_):
    raise NativeProposalEscrowCLIHold("nonfinite native model escrow JSON")


def _absolute(value: object) -> str:
    if (
        type(value) is not str or not value or "\x00" in value
        or not Path(value).is_absolute() or ".." in Path(value).parts
    ):
        raise NativeProposalEscrowCLIHold("private absolute approved source path required")
    return value


def parse_escrow_request(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_INPUT_BYTES:
        raise NativeProposalEscrowCLIHold("bounded strict private escrow input required")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs, parse_constant=_nonfinite,
        )
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise NativeProposalEscrowCLIHold("untrusted model escrow command rejected") from exc
    if type(value) is not dict or frozenset(value) != _FIELDS:
        raise NativeProposalEscrowCLIHold("missing or unknown private model escrow authority")
    if (
        value["schema"] != SCHEMA
        or type(value["action"]) is not str
        or value["action"] not in _ACTIONS
        or type(value["recheck_original_source"]) is not bool
    ):
        raise NativeProposalEscrowCLIHold("invalid explicit private escrow action")
    _absolute(value["project_root"])
    # Validate the same exact canonical private output filename constraints
    # at strict JSON admission, not only after a model has been requested.
    # A syntactically absolute path is not necessarily an approved owner
    # directory; descriptor/ownership checks happen separately pre-start.
    _target(value["target"], value["project_root"])
    if not _digest(value["expected_job_sha256"]):
        raise NativeProposalEscrowCLIHold("full inspected native job SHA-256 required")
    action = value["action"]
    if action == "generate-save":
        if (
            type(value["native_request"]) is not dict
            or value["expected_file_sha256"] is not None
            or value["expected_file_bytes"] is not None
            or value["recheck_original_source"] is not False
        ):
            raise NativeProposalEscrowCLIHold(
                "native generation cannot impersonate cold verification",
            )
        native = parse_native_request(_canonical(value["native_request"]))
        if (
            native["schema"] != NATIVE_REQUEST_SCHEMA
            or native["action"] != "generate"
            or native["project_root"] != value["project_root"]
            or native["job_sha256"] != value["expected_job_sha256"]
        ):
            raise NativeProposalEscrowCLIHold(
                "source escrow does not bind exact approved native task and project",
            )
    else:
        if (
            value["native_request"] is not None
            or not _digest(value["expected_file_sha256"])
            or type(value["expected_file_bytes"]) is not int
            or not 1 <= value["expected_file_bytes"] <= 32768
        ):
            raise NativeProposalEscrowCLIHold(
                "cold source verification cannot carry a model request",
            )
    return value


def _preflight_empty_destination(req: dict) -> None:
    """Verify private directory and absence without invoking a GGUF yet."""
    source = req["native_request"]
    project_root = req["project_root"]
    target = _target(req["target"], project_root)
    if any(
        target.is_relative_to(Path(source[scope]))
        for scope in ("model_root", "state_dir")
    ):
        raise NativeProposalEscrowCLIHold(
            "private escrow must not be inside model or SQLite state",
        )
    try:
        parent = _pinned_private_directory(target)
    except PatchExportHold as exc:
        raise NativeProposalEscrowCLIHold("owner-private escrow parent unavailable") from exc
    try:
        _identical_parent(target, parent)
        try:
            os.stat(target.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise NativeProposalEscrowCLIHold(
            "private proposal destination already exists; cannot start model",
        )
    finally:
        os.close(parent)


def _result(
    action: str, *, status: str,
    job_sha256: str,
    saved: dict | None = None,
    native: dict | None = None,
) -> dict:
    output = {
        "schema": RESULT_SCHEMA,
        "action": action,
        "status": status,
        "job_sha256": job_sha256,
        "private_source": saved,
        "native_source": native,
        "source_contents_in_stdout": False,
        "original_source_modified": False,
        "git_commands_executed": False,
        "generated_code_executed": False,
        "model_filesystem_write_grant": False,
        "automatic_uncertain_native_retry": False,
        "release_certified": False,
    }
    if len(_canonical(output)) > MAX_OUTPUT_BYTES:
        raise NativeProposalEscrowCLIHold("finite non-secret native escrow receipt exceeded")
    return output


def execute_escrow_request(
    req: dict, *, approve_native: bool = False,
    approve_private_storage: bool = False,
    bridge_factory: Callable[..., DesktopBridge] = DesktopBridge,
) -> dict:
    if (
        type(req) is not dict
        or type(approve_native) is not bool
        or type(approve_private_storage) is not bool
        or not callable(bridge_factory)
    ):
        raise NativeProposalEscrowCLIHold("typed operator model/storage consent required")
    selected = parse_escrow_request(_canonical(req))
    action = selected["action"]
    if action == "verify":
        if approve_native or approve_private_storage:
            raise NativeProposalEscrowCLIHold(
                "read-only cold verification cannot carry native write/model grants",
            )
        checked = verify_private_proposal(
            selected["target"], project_root=selected["project_root"],
            expected_job_sha256=selected["expected_job_sha256"],
            expected_file_sha256=selected["expected_file_sha256"],
            expected_file_bytes=selected["expected_file_bytes"],
            recheck_original_source=selected["recheck_original_source"],
        )
        return _result(
            action, status="saved-native-proposal-verified-no-inference",
            job_sha256=selected["expected_job_sha256"], saved=checked,
        )
    if approve_native is not True or approve_private_storage is not True:
        raise NativeProposalEscrowCLIHold(
            "both separate native generation and private storage grants required",
        )
    # No model child or SQLite session can start before the operator's
    # selected source, target and existing owner-private directory pass.
    _preflight_empty_destination(selected)
    native = execute_native_request(
        selected["native_request"],
        approve_native=True,
        emit_private_proposal=True,
        bridge_factory=bridge_factory,
    )
    if native.get("status") != "review-required":
        # Failure was a model-side result. Preserve the exact native/SQLite
        # identities, never silently retry, and do not save unapproved code.
        public = {k: v for k, v in native.items() if k != "private_proposal"}
        return _result(
            action, status="native-source-held-no-private-file",
            job_sha256=selected["expected_job_sha256"], native=public,
        )
    # The private source is intentionally held in process memory only.
    # Subsequent storage errors MUST preserve the authoritative committed
    # SQLite request IDs for manual investigation, not reissue inference.
    try:
        stored = publish_private_proposal(
            native, selected["project_root"], selected["target"],
            expected_job_sha256=selected["expected_job_sha256"],
            approve_private_storage=True,
        )
    except (ValueError, OSError, RuntimeError) as exc:
        public = {k: v for k, v in native.items() if k != "private_proposal"}
        return _result(
            action, status="native-committed-private-publication-held",
            job_sha256=selected["expected_job_sha256"], native={
                **public,
                "escrow_failure_type": type(exc).__name__,
                "manual_sqlite_inspection_required": True,
                "native_effect_must_not_be_reissued": True,
            },
        )
    # Never serialize the private proposal through stdout; the exact
    # proposal is exclusively available in its new owner-private file.
    public = {k: v for k, v in native.items() if k != "private_proposal"}
    return _result(
        action, status="native-proposal-saved-owner-private-no-source-stdout",
        job_sha256=selected["expected_job_sha256"],
        saved=stored, native=public,
    )


class _PrivateParser(argparse.ArgumentParser):
    def error(self, _message):
        raise NativeProposalEscrowCLIHold("invalid private source CLI argument")


def main(
    argv: list[str] | None = None, *,
    source: BinaryIO | None = None,
    output: TextIO | None = None,
    errors: TextIO | None = None,
    bridge_factory: Callable[..., DesktopBridge] = DesktopBridge,
) -> int:
    parser = _PrivateParser(
        prog="jeeves-native-source-escrow",
        description=(
            "Operator-approved original GGUF source generation into one "
            "new private no-clobber source package; or read-only cold verify."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--approve-native-generation", action="store_true",
        help="Permit one real model generation against inspected job SHA",
    )
    parser.add_argument(
        "--approve-private-storage", action="store_true",
        help="Permit one new owner-private source escrow, never overwrite",
    )
    incoming = sys.stdin.buffer if source is None else source
    out = sys.stdout if output is None else output
    err = sys.stderr if errors is None else errors
    try:
        args = parser.parse_args(argv)
        req = parse_escrow_request(incoming.read(MAX_INPUT_BYTES + 1))
        result = execute_escrow_request(
            req,
            approve_native=args.approve_native_generation,
            approve_private_storage=args.approve_private_storage,
            bridge_factory=bridge_factory,
        )
        out.write(_canonical(result).decode("utf-8", "strict") + "\n")
        return 0 if result["status"] in (
            "native-proposal-saved-owner-private-no-source-stdout",
            "saved-native-proposal-verified-no-inference",
        ) else 3
    except (ValueError, OSError, RuntimeError, TypeError, UnicodeError) as exc:
        # Never log model code, original source or private paths.
        err.write(
            "Jeeves private native source held: "
            + type(exc).__name__
            + "; examine original SQLite before attempting another run.\n",
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "RESULT_SCHEMA",
    "NativeProposalEscrowCLIHold",
    "parse_escrow_request", "execute_escrow_request", "main",
]
