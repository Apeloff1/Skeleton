"""Strict stdin-only headless export, inspection, and import of Jeeves capsules.

The operator supplies three complete independent digests for a cold import.
Export requires the existing SHA-approved capsule and a new private archive.
Inspect has no write grant. Neither original prompts nor source bytes, private
paths, or native GGUF material enter the normal terminal response.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import BinaryIO, TextIO

from .desktop_capsule_transport import (
    export_private_transport, import_private_transport,
    inspect_private_transport,
)
from .desktop_workspace import _canonical

SCHEMA = "jeeves.workspace.private-capsule-offline-transport-cli.v1"
RESULT_SCHEMA = "jeeves.workspace.private-capsule-offline-transport-result.v1"
MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 8192
_FIELDS = frozenset({
    "schema", "action", "original_project_root", "capsule_directory",
    "archive_file", "destination", "expected_capsule_sha256",
    "expected_seal_sha256", "expected_archive_sha256",
})


class CapsuleTransportCLIHold(ValueError):
    """Operator did not approve the exact private source transfer."""


def _sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(
        ch in "0123456789abcdef" for ch in value
    )


def _pairs(items):
    parsed = {}
    for key, value in items:
        if key in parsed:
            raise CapsuleTransportCLIHold("duplicate capsule transport authority")
        parsed[key] = value
    return parsed


def _constant(_):
    raise CapsuleTransportCLIHold("nonfinite source transport request")


def _path(value: object) -> str:
    if (
        type(value) is not str or not value or len(value) > 4096
        or "\x00" in value or not Path(value).is_absolute()
        or ".." in Path(value).parts
    ):
        raise CapsuleTransportCLIHold("private source transport requires absolute paths")
    return value


def parse_transport_request(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST_BYTES:
        raise CapsuleTransportCLIHold("finite strict JSON transport request required")
    try:
        req = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise CapsuleTransportCLIHold("invalid source transport request") from exc
    if type(req) is not dict or frozenset(req) != _FIELDS:
        raise CapsuleTransportCLIHold("missing or unexpected transport operation authority")
    if req["schema"] != SCHEMA or req["action"] not in ("inspect", "export", "import"):
        raise CapsuleTransportCLIHold("unsupported private capsule transport action")
    for key in ("original_project_root", "archive_file"):
        _path(req[key])
    for key in ("expected_capsule_sha256", "expected_seal_sha256"):
        if not _sha(req[key]):
            raise CapsuleTransportCLIHold("complete capsule and seal SHA-256 required")
    action = req["action"]
    if action == "export":
        _path(req["capsule_directory"])
        if req["destination"] is not None or req["expected_archive_sha256"] is not None:
            raise CapsuleTransportCLIHold("export cannot carry import or stale digest authority")
    elif action == "import":
        _path(req["destination"])
        if req["capsule_directory"] is not None or not _sha(req["expected_archive_sha256"]):
            raise CapsuleTransportCLIHold("import requires exact approved archive and new target")
    else:
        if (
            req["capsule_directory"] is not None or req["destination"] is not None
            or not _sha(req["expected_archive_sha256"])
        ):
            raise CapsuleTransportCLIHold("read-only archive inspection carries write authority")
    return req


def execute_transport_request(
    req: dict, *, approve_export: bool = False, approve_import: bool = False,
) -> dict[str, object]:
    if (
        type(req) is not dict or type(approve_export) is not bool
        or type(approve_import) is not bool
    ):
        raise CapsuleTransportCLIHold("strict typed transfer approval required")
    req = parse_transport_request(_canonical(req))
    action = req["action"]
    if (
        (action == "inspect" and (approve_export or approve_import))
        or (action == "export" and (not approve_export or approve_import))
        or (action == "import" and (not approve_import or approve_export))
    ):
        raise CapsuleTransportCLIHold("separate action-specific explicit operator consent needed")
    fields = {
        "original_project_root": req["original_project_root"],
        "expected_capsule_sha256": req["expected_capsule_sha256"],
        "expected_seal_sha256": req["expected_seal_sha256"],
    }
    if action == "export":
        result = export_private_transport(
            req["capsule_directory"], req["archive_file"],
            approve_export=True, **fields,
        )
    elif action == "import":
        result = import_private_transport(
            req["archive_file"], req["destination"],
            expected_archive_sha256=req["expected_archive_sha256"],
            approve_import=True, **fields,
        )
    else:
        result = inspect_private_transport(
            req["archive_file"],
            expected_archive_sha256=req["expected_archive_sha256"],
            **fields,
        )
    return {
        "schema": RESULT_SCHEMA,
        "action": action,
        "transport": result,
        "source_contents_in_stdout": False,
        "generated_source_executed": False,
        "native_inference_started": False,
        "original_project_modified": False,
        "release_certified": False,
    }


def main(
    argv: list[str] | None = None, *,
    stdin: BinaryIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Owner-approved sealed Jeeves source transport (offline)",
    )
    parser.add_argument("--approve-export", action="store_true")
    parser.add_argument("--approve-import", action="store_true")
    args = parser.parse_args(argv)
    source = stdin if stdin is not None else sys.stdin.buffer
    output = stdout if stdout is not None else sys.stdout
    errors = stderr if stderr is not None else sys.stderr
    try:
        req = parse_transport_request(source.read(MAX_REQUEST_BYTES + 1))
        result = execute_transport_request(
            req, approve_export=args.approve_export,
            approve_import=args.approve_import,
        )
        serialized = _canonical(result)
        if len(serialized) > MAX_RESPONSE_BYTES:
            raise CapsuleTransportCLIHold("transport receipt exceeds public size budget")
        output.write(serialized.decode("utf-8", "strict") + "\n")
        return 0
    except (Exception, KeyboardInterrupt):
        # Never echo generated model text, private filesystem paths or archive bytes.
        errors.write("JEEVES_PRIVATE_CAPSULE_TRANSPORT_HELD\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "RESULT_SCHEMA", "CapsuleTransportCLIHold",
    "parse_transport_request", "execute_transport_request", "main",
]
