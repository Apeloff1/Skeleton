"""Headless, source-bound Jeeves native code generation using the REAL GGUF.

This is the missing operational bridge between the headless source-work
reviewer and the existing local offline native SQLite model. The request is
a bounded strict JSON record on stdin (never prompts, source or paths on argv).
Inspection is read-only and emits an exact job SHA. A separate explicitly
approved invocation re-reads all selected source files, matches that job SHA,
starts ONE independently installed model via the SAME DesktopBridge/host,
opens ONE native SQLite session, and runs the existing finite verified source
repair executor. Every native effect is a unique committed request. There is
no second provider, automatic startup repair, hidden tool, Git write, project
source mutation, remote fallback, or uncertain replay.

Private original source and the model's generated code never appear in
public receipts. An *extra* explicit flag is required to print generated
source JSON to stdout; use a private destination if capturing that output.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import BinaryIO, Callable, TextIO

from .contracts import identifier
from .desktop_client import DesktopBridge, DesktopConfig
from .desktop_project_context import (
    ProjectSourceContext, snapshot_project_context, parse_context_selection,
    revalidate_project_context,
)
from .desktop_source_repair import (
    FORMATS, SourceRepairRequest, NativeSourceRepairRunner,
    MAX_NATIVE_ATTEMPTS, MAX_GOAL_BYTES,
)
from .desktop_workspace import _canonical

SCHEMA = "jeeves.desktop.headless-native-source-work.v1"
RESULT_SCHEMA = "jeeves.desktop.headless-native-source-receipt.v1"
MAX_REQUEST_BYTES = 16384
MAX_RESPONSE_BYTES = 65536
_MAX_SOURCE_SELECTION_BYTES = 1024
_REQUIRED = frozenset({
    "schema", "action", "project_root", "model_root", "state_dir",
    "tenant", "subject", "goal", "format", "maximum_attempts",
    "source_paths", "source_context_sha256", "job_sha256",
    "context_tokens", "max_output_tokens", "threads", "gpu_layers",
    "inference_ms", "capacity_budget_bytes",
})
_ACTIONS = frozenset({"inspect", "generate"})


class HeadlessNativeSourceHold(ValueError):
    """The operator-selected native source action was not admitted."""


def _is_sha(value: object) -> bool:
    return (
        type(value) is str and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise HeadlessNativeSourceHold("duplicate operator request field")
        result[key] = value
    return result


def _nonfinite(_value):
    raise HeadlessNativeSourceHold("nonfinite operator native request")


def _canonical_path(value: object) -> str:
    if (
        type(value) is not str or not value or "\x00" in value
        or not Path(value).is_absolute() or ".." in Path(value).parts
    ):
        raise HeadlessNativeSourceHold("absolute original model/source/state path required")
    return value


def parse_native_request(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST_BYTES:
        raise HeadlessNativeSourceHold("bounded private headless source request required")
    try:
        req = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs, parse_constant=_nonfinite,
        )
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise HeadlessNativeSourceHold("strict original model-source request rejected") from exc
    if type(req) is not dict or frozenset(req) != _REQUIRED:
        raise HeadlessNativeSourceHold("headless request missing field or carries new authority")
    if (
        req["schema"] != SCHEMA
        or type(req["action"]) is not str
        or req["action"] not in _ACTIONS
    ):
        raise HeadlessNativeSourceHold("unknown local GGUF source operation")
    for field in ("project_root", "model_root", "state_dir"):
        _canonical_path(req[field])
    identifier(req["tenant"], "tenant")
    identifier(req["subject"], "subject")
    if (
        type(req["goal"]) is not str or not req["goal"].strip()
        or not 1 <= len(req["goal"].encode("utf-8", "strict")) <= MAX_GOAL_BYTES
    ):
        raise HeadlessNativeSourceHold("original task must have finite UTF-8 goal")
    if type(req["format"]) is not str or req["format"] not in FORMATS:
        raise HeadlessNativeSourceHold("invalid original GGUF source schema")
    if (
        type(req["maximum_attempts"]) is not int
        or not 1 <= req["maximum_attempts"] <= MAX_NATIVE_ATTEMPTS
    ):
        raise HeadlessNativeSourceHold("no explicit finite source-repair turn count")
    names = req["source_paths"]
    if type(names) is not list or len(names) > 4 or any(type(x) is not str for x in names):
        raise HeadlessNativeSourceHold("exact selected source paths must be a finite list")
    if names:
        selected = parse_context_selection("\n".join(names))
        if list(selected) != names:
            raise HeadlessNativeSourceHold("source selection changed during strict normalization")
    if (
        not names and req["source_context_sha256"] is not None
        or req["source_context_sha256"] is not None
        and not _is_sha(req["source_context_sha256"])
    ):
        raise HeadlessNativeSourceHold("unbound source snapshot digest")
    job = req["job_sha256"]
    if req["action"] == "inspect":
        if job is not None:
            raise HeadlessNativeSourceHold("read-only task inspection cannot carry native approval")
    elif not _is_sha(job):
        raise HeadlessNativeSourceHold("generation needs exact inspected original job SHA")
    fields = {
        "context_tokens": (128, 131072),
        "max_output_tokens": (1, 8192),
        "threads": (1, 64),
        "gpu_layers": (0, 128),
        "inference_ms": (100, 600000),
        "capacity_budget_bytes": (1, 20000000000),
    }
    for name, (low, high) in fields.items():
        value = req[name]
        if type(value) is not int or not low <= value <= high:
            raise HeadlessNativeSourceHold("explicit hardware/token budget must be finite")
    if req["max_output_tokens"] >= req["context_tokens"]:
        raise HeadlessNativeSourceHold("native model output tokens exceed context")
    # The real model configuration must stay CPU-only by default unless the
    # operator separately provides a verified CUDA/Metal installation.
    # This API does not guess VRAM or silently change GPU settings.
    if req["gpu_layers"] != 0:
        raise HeadlessNativeSourceHold("GPU model-device qualification is not established")
    return req


def _snapshot(req: dict) -> ProjectSourceContext | None:
    names = req["source_paths"]
    if not names:
        return None
    source = snapshot_project_context(
        req["project_root"], "\n".join(names),
    )
    if (
        req["source_context_sha256"] is not None
        and req["source_context_sha256"] != source.manifest_sha256
    ):
        raise HeadlessNativeSourceHold(
            "operator-selected original file contents changed since inspection",
        )
    return source


def _job_digest(req: dict, selected: ProjectSourceContext | None) -> str:
    body = {
        "schema": SCHEMA,
        "operator_goal": req["goal"],
        "project_root": req["project_root"],
        "model_root": req["model_root"],
        "state_dir": req["state_dir"],
        "tenant": req["tenant"],
        "subject": req["subject"],
        "format": req["format"],
        "maximum_attempts": req["maximum_attempts"],
        "source_paths": req["source_paths"],
        "source_context_sha256": (
            selected.manifest_sha256 if selected is not None else None
        ),
        "context_tokens": req["context_tokens"],
        "max_output_tokens": req["max_output_tokens"],
        "threads": req["threads"],
        "gpu_layers": req["gpu_layers"],
        "inference_ms": req["inference_ms"],
        "capacity_budget_bytes": req["capacity_budget_bytes"],
    }
    return sha256(_canonical(body)).hexdigest()


def _public_review(req: dict, selected: ProjectSourceContext | None) -> dict:
    return {
        "schema": RESULT_SCHEMA,
        "action": "inspect",
        "status": "operator-review-required-before-native-model",
        "job_sha256": _job_digest(req, selected),
        "goal_sha256": sha256(req["goal"].encode("utf-8", "strict")).hexdigest(),
        "format": req["format"],
        "maximum_attempts": req["maximum_attempts"],
        "source_context_sha256": (
            selected.manifest_sha256 if selected is not None else None
        ),
        "selected_source_file_count": len(selected.files) if selected else 0,
        "source_files": (
            [x.to_public() for x in selected.files] if selected else []
        ),
        "local_cpu_threads": req["threads"],
        "local_context_tokens": req["context_tokens"],
        "max_output_tokens": req["max_output_tokens"],
        "gpu_layers": 0,
        "native_gguf_started": False,
        "source_files_modified": False,
        "git_commands_executed": False,
        "model_granted_filesystem_tools": False,
        "device_qualified": False,
        "release_certified": False,
    }


def execute_native_request(
    request: dict,
    *, approve_native: bool = False,
    emit_private_proposal: bool = False,
    bridge_factory: Callable[..., DesktopBridge] = DesktopBridge,
) -> dict:
    """One operator-approved real SQLite native inference, no implicit retry."""
    if (
        type(request) is not dict
        or type(approve_native) is not bool
        or type(emit_private_proposal) is not bool
        or not callable(bridge_factory)
    ):
        raise HeadlessNativeSourceHold("explicit typed original operator request required")
    req = parse_native_request(_canonical(request))
    selected = _snapshot(req)
    inspected = _public_review(req, selected)
    if req["action"] == "inspect":
        if approve_native or emit_private_proposal:
            raise HeadlessNativeSourceHold("read-only review cannot start a real model")
        return inspected
    if (
        approve_native is not True
        or req["job_sha256"] != inspected["job_sha256"]
        or (
            selected is not None
            and req["source_context_sha256"] != selected.manifest_sha256
        )
    ):
        raise HeadlessNativeSourceHold(
            "full original reviewed job/source digests and native consent required",
        )
    if emit_private_proposal and not approve_native:
        raise HeadlessNativeSourceHold("private generated source needs distinct native approval")

    cfg = DesktopConfig(
        model_root=req["model_root"], state_dir=req["state_dir"],
        tenant=req["tenant"], subject=req["subject"],
        context=req["context_tokens"],
        max_output_tokens=req["max_output_tokens"],
        threads=req["threads"], gpu_layers=0,
        inference_ms=req["inference_ms"],
        capacity_budget_bytes=req["capacity_budget_bytes"],
        enable_signed_source_tool=False,
        enable_pressure_guard=True,
    )
    order = SourceRepairRequest(
        root=req["project_root"], goal=req["goal"],
        format=req["format"],
        maximum_attempts=req["maximum_attempts"],
        source_context=selected,
    )
    if selected is not None:
        revalidate_project_context(selected)

    bridge = bridge_factory(cfg)
    try:
        ready = bridge.open()
        if (
            type(ready) is not dict
            or ready.get("status") != "native-gguf-ready"
            or ready.get("source_bound") is not True
            or ready.get("physical_device_qualified") is not False
            or ready.get("release_certified") is not False
            or bridge.model_sha256 is None
            or bridge.session_id is not None
            or not bridge.connected
        ):
            raise HeadlessNativeSourceHold("native host not ready without a private session")
        opened = bridge.request("new")
        if (
            type(opened) is not dict
            or opened.get("status") != "new-durable-session"
            or not bridge.session_id
        ):
            raise HeadlessNativeSourceHold("new private SQLite session was not committed")
        if selected is not None:
            revalidate_project_context(selected)
        runner = NativeSourceRepairRunner(
            bridge, order, approved=True,
        )
        outcome = runner.execute()
        receipt = outcome.public_receipt()
        if (
            receipt["model_sha256"] != bridge.model_sha256
            or receipt["session_id"] != bridge.session_id
            or receipt["goal_sha256"] != inspected["goal_sha256"]
        ):
            raise HeadlessNativeSourceHold("source result crossed original native worker")
        result = {
            "schema": RESULT_SCHEMA,
            "action": "generate",
            "status": receipt["status"],
            "job_sha256": inspected["job_sha256"],
            "source_context_sha256": inspected["source_context_sha256"],
            "native_model_sha256": bridge.model_sha256,
            "durable_session_id": bridge.session_id,
            "native_source": receipt,
            "source_receipt_verified": True,
            "operator_patch_review_required": True,
            "private_proposal_emitted": emit_private_proposal
                and outcome.proposal is not None,
            "source_files_modified": False,
            "git_commands_executed": False,
            "model_granted_filesystem_tools": False,
            "device_qualified": False,
            "release_certified": False,
        }
        if emit_private_proposal and outcome.proposal is not None:
            # This is sensitive private code: stdout capture must be
            # explicitly approved. The next local-source CLI will STRICTLY
            # revalidate it against actual original source before staging.
            result["private_proposal"] = outcome.proposal
        if len(_canonical(result)) > MAX_RESPONSE_BYTES:
            raise HeadlessNativeSourceHold(
                "generated private proposal exceeds bounded output disclosure",
            )
        return result
    finally:
        # A failed or cancelled model operation may already have committed.
        # Preserve its SQLite ledger; never automatically replay/reissue work.
        bridge.close()


class _PrivateParser(argparse.ArgumentParser):
    def error(self, _message):
        raise HeadlessNativeSourceHold("invalid headless native CLI arguments")


def main(
    argv: list[str] | None = None,
    *,
    source: BinaryIO | None = None,
    output: TextIO | None = None,
    errors: TextIO | None = None,
    bridge_factory: Callable[..., DesktopBridge] = DesktopBridge,
) -> int:
    parser = _PrivateParser(
        prog="jeeves-native-code",
        description=(
            "Source-bound local GGUF native SQLite code generation. "
            "Private task and paths are read from bounded strict JSON stdin."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--approve-native-generation", action="store_true",
        help="Explicitly allow one inspected finite native GGUF/SQLite source run",
    )
    parser.add_argument(
        "--emit-private-proposal", action="store_true",
        help="Explicitly allow sensitive generated source JSON to stdout",
    )
    incoming = sys.stdin.buffer if source is None else source
    out = sys.stdout if output is None else output
    err = sys.stderr if errors is None else errors
    try:
        args = parser.parse_args(argv)
        raw = incoming.read(MAX_REQUEST_BYTES + 1)
        request = parse_native_request(raw)
        result = execute_native_request(
            request,
            approve_native=args.approve_native_generation,
            emit_private_proposal=args.emit_private_proposal,
            bridge_factory=bridge_factory,
        )
        data = _canonical(result)
        if len(data) > MAX_RESPONSE_BYTES:
            raise HeadlessNativeSourceHold("bounded native source disclosure exceeded")
        out.write(data.decode("utf-8", "strict") + "\n")
        return 0 if (
            result.get("status") not in ("held-exhausted", "operator-stopped")
        ) else 3
    except (ValueError, OSError, RuntimeError, TypeError, UnicodeError) as exc:
        # No source contents, model paths, prompts or nested private
        # exception args in user-visible stderr.
        err.write(
            "Jeeves headless native source held: "
            + type(exc).__name__
            + ". Check original SQLite custody; no automatic retry.\n",
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "RESULT_SCHEMA", "MAX_REQUEST_BYTES",
    "HeadlessNativeSourceHold", "parse_native_request",
    "execute_native_request", "main",
]
