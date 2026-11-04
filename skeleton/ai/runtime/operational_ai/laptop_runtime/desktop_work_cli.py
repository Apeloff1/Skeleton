"""Headless operator CLI for Jeeves local source review and private delivery.

Uses the identical descriptor-rooted source/patch/overlay reviewers as the
desktop, but never loads a GGUF, opens a SQLite inference session, starts Git,
executes generated code, creates branches or installs dependencies.

Input is one bounded, strict JSON request on stdin. All public receipts
exclude raw original/replacement code and private absolute source roots.
No write action can run unless BOTH the request carries the full original
manifest/patch SHA-256 values AND the operator explicitly supplies the
matching CLI approval flag. There are no retries or silent fallbacks.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import BinaryIO, TextIO

from .desktop_workspace import _canonical
from .desktop_patch_bundle import (
    PortablePatchPlan, get_reviewed_patch, review_patch_bundle,
)
from .desktop_project_work import review_mixed_work
from .desktop_patch_export import export_reviewed_patch, verify_saved_patch
from .desktop_private_overlay import stage_reviewed_overlay, verify_staged_overlay
from .desktop_patch_reconcile import reconcile_reviewed_patch
from .desktop_source_qualification import qualify_patch_sources
from .desktop_source_graph import analyze_python_source_graph

SCHEMA = "jeeves.workspace.local-source-cli.v1"
RESULT_SCHEMA = "jeeves.workspace.local-source-cli-result.v1"
MAX_REQUEST_BYTES = 131072
MAX_PUBLIC_RESPONSE_BYTES = 65536
_ACTIONS = frozenset((
    "review", "stage", "verify-stage",
    "export-patch", "verify-patch", "reconcile",
))
_FIELDS = frozenset((
    "schema", "action", "root", "new_files", "existing_edits",
    "mixed_work", "target", "source_manifest_sha256",
    "patch_sha256", "patch_bytes",
))


class LocalSourceCLIHold(ValueError):
    """An exact source-work request did not satisfy local offline admission."""


def _is_sha(value: object) -> bool:
    return (
        type(value) is str and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _exact_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LocalSourceCLIHold("duplicate source-work CLI record field")
        result[key] = value
    return result


def _bad_constant(_name):
    raise LocalSourceCLIHold("nonfinite source-work CLI quantity")


def parse_request(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST_BYTES:
        raise LocalSourceCLIHold("finite original offline source-work request required")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_exact_pairs,
            parse_constant=_bad_constant,
        )
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise LocalSourceCLIHold("strict source-work CLI input rejected") from exc
    if type(value) is not dict or frozenset(value) != _FIELDS:
        raise LocalSourceCLIHold("unexpected source-work CLI authority or missing field")
    if value["schema"] != SCHEMA or value["action"] not in _ACTIONS:
        raise LocalSourceCLIHold("unsupported original offline source-work operation")
    root = value["root"]
    if (
        type(root) is not str or not root or "\x00" in root
        or not Path(root).is_absolute() or ".." in Path(root).parts
    ):
        raise LocalSourceCLIHold("operator-selected canonical source root required")
    for name in ("new_files", "existing_edits", "mixed_work", "target"):
        data = value[name]
        if data is not None and type(data) is not str:
            raise LocalSourceCLIHold("untyped original source-work parameter")
    for name in ("source_manifest_sha256", "patch_sha256"):
        digest = value[name]
        if digest is not None and not _is_sha(digest):
            raise LocalSourceCLIHold("operator approval requires full 64-character SHA-256")
    count = value["patch_bytes"]
    if count is not None and (
        type(count) is not int or not 1 <= count <= 786432
    ):
        raise LocalSourceCLIHold("untyped or unbounded expected Git patch length")
    plan_fields = (
        value["new_files"], value["existing_edits"], value["mixed_work"],
    )
    has_proposal = any(v is not None and bool(v.strip()) for v in plan_fields)
    action = value["action"]
    if action in ("review", "stage", "export-patch", "reconcile"):
        if not has_proposal:
            raise LocalSourceCLIHold("original model source proposals required")
        if value["mixed_work"] is not None and (
            value["new_files"] is not None or value["existing_edits"] is not None
        ):
            raise LocalSourceCLIHold("mixed source cannot overlap separate proposal input")
    elif any(v is not None for v in plan_fields):
        raise LocalSourceCLIHold("private read-only verification cannot carry source proposals")
    if action in ("stage", "export-patch", "verify-stage"):
        if not (
            _is_sha(value["source_manifest_sha256"])
            and _is_sha(value["patch_sha256"])
        ):
            raise LocalSourceCLIHold("exact original manifest and patch SHA required")
    elif action == "verify-patch" and not (
        _is_sha(value["patch_sha256"])
        and value["patch_bytes"] is not None
    ):
        raise LocalSourceCLIHold("exact saved patch digest/byte count required")
    if action in ("review", "reconcile"):
        if any(
            value[n] is not None
            for n in (
                "target", "source_manifest_sha256",
                "patch_sha256", "patch_bytes",
            )
        ):
            raise LocalSourceCLIHold("review cannot carry hidden private write authorization")
    elif type(value["target"]) is not str or not value["target"]:
        raise LocalSourceCLIHold("private target path required for explicit stage/inspection")
    if action != "verify-patch" and value["patch_bytes"] is not None:
        raise LocalSourceCLIHold("patch byte length only valid during saved-patch verification")
    if action == "verify-patch" and value["source_manifest_sha256"] is not None:
        raise LocalSourceCLIHold("saved Git patch verification is not a model reissue")
    return value


def _review_plan(req: dict[str, object]) -> PortablePatchPlan:
    mixed = req["mixed_work"]
    if mixed is not None:
        _, plan = review_mixed_work(mixed, req["root"])
    else:
        plan = review_patch_bundle(
            req["root"],
            new_files=req["new_files"],
            existing_edits=req["existing_edits"],
        )
    get_reviewed_patch(plan)
    return plan


def _public_receipt(action: str, *,
                    review: dict | None = None,
                    qualification: dict | None = None,
                    source_graph: dict | None = None,
                    operation: dict | None = None) -> dict:
    result = {
        "schema": RESULT_SCHEMA,
        "action": action,
        "status": "original-source-reviewed" if action == "review"
        else "source-reconciliation-reviewed" if action == "reconcile"
        else "explicit-private-source-work-completed",
        "review": review,
        "qualification": qualification,
        "python_source_graph": source_graph,
        "operation": operation,
        "model_inference_started": False,
        "source_code_executed": False,
        "original_checkout_modified": False,
        "git_commands_executed": False,
        "private_output_consent_required": action in ("stage", "export-patch"),
        "release_certified": False,
    }
    data = _canonical(result)
    if len(data) > MAX_PUBLIC_RESPONSE_BYTES:
        raise LocalSourceCLIHold("finite public source-work receipt exceeded")
    return result


def execute(
    request: dict[str, object], *,
    approve_private_stage: bool = False,
    approve_private_patch: bool = False,
) -> dict[str, object]:
    """One fully checked operator command; never retry unknown side effects."""
    if (
        type(request) is not dict
        or approve_private_stage not in (True, False)
        or type(approve_private_stage) is not bool
        or approve_private_patch not in (True, False)
        or type(approve_private_patch) is not bool
    ):
        raise LocalSourceCLIHold("typed original explicit operator action required")
    # Re-encode and parse the entire caller-supplied object. This rules out
    # a caller fabricating an already-verified plan or sneaking booleans
    # through a string dict constructed outside the CLI.
    req = parse_request(_canonical(request))
    action = req["action"]
    if action != "stage" and approve_private_stage:
        raise LocalSourceCLIHold("unrequested private stage grant")
    if action != "export-patch" and approve_private_patch:
        raise LocalSourceCLIHold("unrequested private patch grant")
    if action == "stage" and approve_private_stage is not True:
        raise LocalSourceCLIHold("stage needs explicit matching CLI flag")
    if action == "export-patch" and approve_private_patch is not True:
        raise LocalSourceCLIHold("patch export needs explicit matching CLI flag")

    if action == "verify-stage":
        done = verify_staged_overlay(
            req["target"], workspace_root=req["root"],
            expected_manifest_sha256=req["source_manifest_sha256"],
            expected_patch_sha256=req["patch_sha256"],
        )
        return _public_receipt(action, operation=done)
    if action == "verify-patch":
        done = verify_saved_patch(
            req["target"], workspace_root=req["root"],
            expected_patch_sha256=req["patch_sha256"],
            expected_bytes=req["patch_bytes"],
        )
        return _public_receipt(action, operation=done)

    plan = _review_plan(req)
    static = qualify_patch_sources(plan)
    graph = analyze_python_source_graph(plan)
    if action == "review":
        return _public_receipt(
            action, review=plan.public_review(),
            qualification=static.to_public(),
            source_graph=graph.to_public(),
        )
    if action == "reconcile":
        reconciled = reconcile_reviewed_patch(plan)
        return _public_receipt(
            action, review=plan.public_review(),
            qualification=static.to_public(),
            source_graph=graph.to_public(),
            operation=reconciled.to_public(),
        )
    if (
        plan.manifest_sha256 != req["source_manifest_sha256"]
        or plan.patch_sha256 != req["patch_sha256"]
    ):
        raise LocalSourceCLIHold(
            "operator-approved digests differ from freshly reviewed original source",
        )
    if not static.permits_inert_export or not graph.permits_inert_export:
        raise LocalSourceCLIHold(
            "supported source syntax or Python dependency graph has a blocking error",
        )
    if action == "stage":
        done = stage_reviewed_overlay(
            plan, req["target"],
            expected_manifest_sha256=req["source_manifest_sha256"],
            expected_patch_sha256=req["patch_sha256"],
            approve_staging=True,
        )
    elif action == "export-patch":
        done = export_reviewed_patch(
            plan, req["target"],
            expected_manifest_sha256=req["source_manifest_sha256"],
            expected_patch_sha256=req["patch_sha256"],
            approve_export=True,
        )
    else:
        raise LocalSourceCLIHold("unknown original source action")
    return _public_receipt(
        action, review=plan.public_review(),
        qualification=static.to_public(), source_graph=graph.to_public(),
        operation=done,
    )


def main(
    argv: list[str] | None = None,
    *,
    source: BinaryIO | None = None,
    output: TextIO | None = None,
    errors: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="jeeves-local-source",
        description=(
            "No-execution local source review and SHA-approved private stage "
            "or Git-patch export. Strict stdin JSON only; never runs a model."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--approve-private-stage", action="store_true",
        help="Separate explicit human grant for one NEW private source overlay",
    )
    parser.add_argument(
        "--approve-private-patch", action="store_true",
        help="Separate explicit human grant for one NEW private inert Git patch",
    )
    args = parser.parse_args(argv)
    incoming = sys.stdin.buffer if source is None else source
    out = sys.stdout if output is None else output
    err = sys.stderr if errors is None else errors
    try:
        raw = incoming.read(MAX_REQUEST_BYTES + 1)
        req = parse_request(raw)
        result = execute(
            req,
            approve_private_stage=args.approve_private_stage,
            approve_private_patch=args.approve_private_patch,
        )
        out.write(
            json.dumps(
                result, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ) + "\n",
        )
        return 0
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        # Exception .args may include a private path, original source, or
        # prompt. Never print it or a nested traceback to stdout/stderr.
        err.write(
            "Jeeves local source work held: "
            + type(exc).__name__
            + ". Original source, model state and Git remain unchanged.\n",
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "RESULT_SCHEMA", "MAX_REQUEST_BYTES",
    "LocalSourceCLIHold", "parse_request", "execute", "main",
]
