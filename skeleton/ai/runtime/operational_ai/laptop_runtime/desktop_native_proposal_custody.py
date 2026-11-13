"""Owner-private custody of a committed local Jeeves model source proposal.

After real GGUF/SQLite code generation, the native CLI normally reports only
hashes. This module adds an EXPLICIT operator-approved no-clobber artifact
for the already-verified original model source proposal, without disclosing
private code into stdout or letting the model choose the destination.

This is a private source REVIEW object, not a source-write authorization.
The original checkout, Git, installed model and SQLite remain untouched.
No generated code is imported, evaluated, compiled or executed. A cold
read verifies the exact stored bytes without replaying native inference.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from .desktop_patch_export import (
    PatchExportHold, _pinned_private_directory,
    _identical_parent, _read_exact,
)
from .desktop_patch_bundle import (
    PatchBundleHold, PortablePatchPlan, get_reviewed_patch,
    review_patch_bundle, revalidate_live_sources,
)
from .desktop_project_work import (
    SCHEMA as MIXED_SCHEMA, review_mixed_work,
)
from .desktop_workspace import (
    SCHEMA as NEW_SCHEMA, _canonical,
)
from .desktop_existing_edits import SCHEMA as EDIT_SCHEMA
from .desktop_source_qualification import (
    StaticSourceHold, require_parseable_patch,
)
from .desktop_source_graph import (
    SourceGraphHold, analyze_python_source_graph,
)

SCHEMA = "jeeves.desktop.private-native-source-proposal.v1"
RECEIPT_SCHEMA = "jeeves.desktop.private-native-source-proposal-receipt.v1"
MAX_PROPOSAL_BYTES = 16384
MAX_ESCROW_BYTES = 32768
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,98}\.source\.json\Z")
_KEYS = frozenset({
    "schema", "job_sha256", "source_context_sha256",
    "source_manifest_sha256", "source_patch_sha256",
    "model_sha256", "session_id", "attempt_count",
    "proposal_schema", "proposal_sha256", "proposal_bytes",
    "proposal", "static_source_status", "python_graph_sha256",
    "original_checkout_modified", "git_commands_executed",
    "generated_code_executed", "release_certified",
})


class PrivateNativeProposalHold(ValueError):
    """The operator-owned native source handoff is unsafe or not verified."""


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _digest(value: object) -> bool:
    return (
        type(value) is str and len(value) == 64
        and all(x in "0123456789abcdef" for x in value)
    )


def _proposal_schema(raw: str) -> str:
    def pairs(data):
        out = {}
        for k, v in data:
            if k in out:
                raise PrivateNativeProposalHold("duplicate model source JSON field")
            out[k] = v
        return out
    def nonfinite(_):
        raise PrivateNativeProposalHold("nonfinite model source JSON value")
    try:
        value = json.loads(
            raw, object_pairs_hook=pairs, parse_constant=nonfinite,
        )
    except (UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise PrivateNativeProposalHold("untrusted original model source schema") from exc
    schema = value.get("schema") if type(value) is dict else None
    if type(schema) is not str or schema not in (
        NEW_SCHEMA, EDIT_SCHEMA, MIXED_SCHEMA,
    ):
        raise PrivateNativeProposalHold("unknown original source package schema")
    return schema


def _review_proposal(
    project_root: str, *, schema: str, proposal: str,
) -> PortablePatchPlan:
    try:
        if schema == MIXED_SCHEMA:
            _, plan = review_mixed_work(proposal, project_root)
        else:
            plan = review_patch_bundle(
                project_root,
                new_files=proposal if schema == NEW_SCHEMA else None,
                existing_edits=proposal if schema == EDIT_SCHEMA else None,
            )
        get_reviewed_patch(plan)
        require_parseable_patch(plan)
        graph = analyze_python_source_graph(plan)
        if not graph.permits_inert_export:
            raise PrivateNativeProposalHold("model Python imports unreviewable")
        return plan
    except (ValueError, OSError, PatchBundleHold,
            StaticSourceHold, SourceGraphHold) as exc:
        raise PrivateNativeProposalHold(
            "original committed proposal no longer passes real source review",
        ) from exc


def _target(value: str | Path, project_root: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise PrivateNativeProposalHold("explicit owner-private source escrow name required")
    path = Path(value)
    source = Path(project_root)
    if (
        not path.is_absolute() or ".." in path.parts
        or "\x00" in str(path) or not _NAME.fullmatch(path.name)
        or not source.is_absolute() or ".." in source.parts
        or path.is_relative_to(source)
    ):
        raise PrivateNativeProposalHold("private model source escrow destination unsafe")
    return path


def _check_record(record: dict) -> bytes:
    if type(record) is not dict or frozenset(record) != _KEYS:
        raise PrivateNativeProposalHold("unexpected model proposal escrow authority")
    for key in (
        "job_sha256", "source_manifest_sha256",
        "source_patch_sha256", "model_sha256",
        "proposal_sha256", "python_graph_sha256",
    ):
        if not _digest(record[key]):
            raise PrivateNativeProposalHold("incomplete private source SHA custody")
    if (
        record["schema"] != SCHEMA
        or record["proposal_schema"] not in (NEW_SCHEMA, EDIT_SCHEMA, MIXED_SCHEMA)
        or (
            record["source_context_sha256"] is not None
            and not _digest(record["source_context_sha256"])
        )
        or type(record["session_id"]) is not str
        or not record["session_id"]
        or type(record["attempt_count"]) is not int
        or not 1 <= record["attempt_count"] <= 3
        or type(record["proposal"]) is not str
        or type(record["proposal_bytes"]) is not int
        or record["original_checkout_modified"] is not False
        or record["git_commands_executed"] is not False
        or record["generated_code_executed"] is not False
        or record["release_certified"] is not False
        or record["static_source_status"] not in (
            "parse-clean", "mixed-unverified",
        )
    ):
        raise PrivateNativeProposalHold("untrusted original model source escrow receipt")
    try:
        src = record["proposal"].encode("utf-8", "strict")
    except UnicodeError as exc:
        raise PrivateNativeProposalHold("invalid model UTF-8 source") from exc
    if (
        not 1 <= len(src) <= MAX_PROPOSAL_BYTES
        or len(src) != record["proposal_bytes"]
        or _sha(src) != record["proposal_sha256"]
        or _proposal_schema(record["proposal"]) != record["proposal_schema"]
    ):
        raise PrivateNativeProposalHold("stored model proposal differs from approved source")
    raw = _canonical(record)
    if not 1 <= len(raw) <= MAX_ESCROW_BYTES:
        raise PrivateNativeProposalHold("finite original model source escrow exceeded")
    return raw


def _build_record(
    result: dict, *, expected_job_sha256: str,
    project_root: str,
) -> tuple[dict, PortablePatchPlan]:
    if (
        type(result) is not dict
        or result.get("schema") != "jeeves.desktop.headless-native-source-receipt.v1"
        or result.get("status") != "review-required"
        or result.get("job_sha256") != expected_job_sha256
        or not _digest(expected_job_sha256)
        or result.get("private_proposal_emitted") is not True
        or result.get("source_receipt_verified") is not True
        or result.get("source_files_modified") is not False
        or result.get("git_commands_executed") is not False
        or result.get("model_granted_filesystem_tools") is not False
        or result.get("release_certified") is not False
        or result.get("device_qualified") is not False
    ):
        raise PrivateNativeProposalHold("original native result lacks committed source evidence")
    proposal = result.get("private_proposal")
    native = result.get("native_source")
    if type(proposal) is not str or type(native) is not dict:
        raise PrivateNativeProposalHold("native source remains unavailable or held")
    schema = _proposal_schema(proposal)
    plan = _review_proposal(project_root, schema=schema, proposal=proposal)
    if (
        not _digest(result.get("native_model_sha256"))
        or type(result.get("durable_session_id")) is not str
        or native.get("status") != "review-required"
        or native.get("model_sha256") != result["native_model_sha256"]
        or native.get("session_id") != result["durable_session_id"]
        or native.get("source_manifest_sha256") != plan.manifest_sha256
        or native.get("source_patch_sha256") != plan.patch_sha256
        or native.get("operator_source_context_sha256")
        != result.get("source_context_sha256")
        or type(native.get("attempt_count")) is not int
        or not 1 <= native["attempt_count"] <= 3
    ):
        raise PrivateNativeProposalHold("model/SQLite/patch provenance differs from real source")
    graph = analyze_python_source_graph(plan)
    static = require_parseable_patch(plan)
    record = {
        "schema": SCHEMA,
        "job_sha256": result["job_sha256"],
        "source_context_sha256": result.get("source_context_sha256"),
        "source_manifest_sha256": plan.manifest_sha256,
        "source_patch_sha256": plan.patch_sha256,
        "model_sha256": result["native_model_sha256"],
        "session_id": result["durable_session_id"],
        "attempt_count": native["attempt_count"],
        "proposal_schema": schema,
        "proposal_sha256": _sha(proposal.encode("utf-8", "strict")),
        "proposal_bytes": len(proposal.encode("utf-8", "strict")),
        "proposal": proposal,
        "static_source_status": static.status,
        "python_graph_sha256": graph.graph_sha256,
        "original_checkout_modified": False,
        "git_commands_executed": False,
        "generated_code_executed": False,
        "release_certified": False,
    }
    _check_record(record)
    return record, plan


def _public_receipt(record: dict, raw: bytes, *, status: str) -> dict[str, object]:
    return {
        "schema": RECEIPT_SCHEMA,
        "status": status,
        "private_file_sha256": _sha(raw),
        "private_file_bytes": len(raw),
        "job_sha256": record["job_sha256"],
        "source_context_sha256": record["source_context_sha256"],
        "source_manifest_sha256": record["source_manifest_sha256"],
        "source_patch_sha256": record["source_patch_sha256"],
        "model_sha256": record["model_sha256"],
        "session_id": record["session_id"],
        "proposal_sha256": record["proposal_sha256"],
        "proposal_bytes": record["proposal_bytes"],
        "static_source_status": record["static_source_status"],
        "python_graph_sha256": record["python_graph_sha256"],
        "private_source_contents_disclosed": False,
        "generated_code_executed": False,
        "original_checkout_modified": False,
        "git_commands_executed": False,
        "model_granted_file_write": False,
        "release_certified": False,
    }


def publish_private_proposal(
    result: dict, project_root: str, destination: str | Path, *,
    expected_job_sha256: str, approve_private_storage: bool,
) -> dict[str, object]:
    """One no-overwrite private source escrow; never replay native model work."""
    if approve_private_storage is not True:
        raise PrivateNativeProposalHold("explicit private source custody approval required")
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise PrivateNativeProposalHold("source escrow needs POSIX/WSL2 descriptors")
    path = _target(destination, project_root)
    record, plan = _build_record(
        result, expected_job_sha256=expected_job_sha256,
        project_root=project_root,
    )
    payload = _check_record(record)
    try:
        private = _pinned_private_directory(path)
    except PatchExportHold as exc:
        raise PrivateNativeProposalHold("owner-controlled 0700 escrow directory required") from exc
    opened = None
    created = None
    successful = False
    try:
        _identical_parent(path, private)
        opened = os.open(
            path.name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            0o600, dir_fd=private,
        )
        initial = os.fstat(opened)
        created = (initial.st_dev, initial.st_ino)
        if (
            not stat.S_ISREG(initial.st_mode)
            or initial.st_uid != os.getuid()
            or initial.st_mode & 0o077
            or initial.st_nlink != 1
        ):
            raise PrivateNativeProposalHold("escrow source file not owner-private")
        pos = 0
        while pos < len(payload):
            n = os.write(opened, payload[pos:pos + 8192])
            if type(n) is not int or n < 1:
                raise PrivateNativeProposalHold("private source escrow short publication")
            pos += n
        os.fsync(opened)
        try:
            checked = _read_exact(opened, expected_bytes=len(payload))
        except PatchExportHold as exc:
            raise PrivateNativeProposalHold("private source escrow readback failed") from exc
        if checked != payload:
            raise PrivateNativeProposalHold("private source bytes not published exactly")
        on_disk = os.stat(path.name, dir_fd=private, follow_symlinks=False)
        written = os.fstat(opened)
        if (
            (on_disk.st_dev, on_disk.st_ino, on_disk.st_size,
             on_disk.st_mtime_ns)
            != (written.st_dev, written.st_ino, written.st_size,
                written.st_mtime_ns)
        ):
            raise PrivateNativeProposalHold("private source escrow file replaced")
        _identical_parent(path, private)
        revalidate_live_sources(plan)
        os.fsync(private)
        successful = True
        return _public_receipt(
            record, payload, status="private-reviewed-native-source-saved",
        )
    finally:
        if not successful and created is not None:
            # Only remove the exact inode created by this operation.
            # Do not recursively remove directories or unrelated replacements.
            try:
                current = os.stat(
                    path.name, dir_fd=private, follow_symlinks=False,
                )
                if (current.st_dev, current.st_ino) == created:
                    os.unlink(path.name, dir_fd=private)
                    os.fsync(private)
            except OSError:
                pass
        if opened is not None:
            os.close(opened)
        os.close(private)


def _parse_saved(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_ESCROW_BYTES:
        raise PrivateNativeProposalHold("saved private model source bytes unbounded")
    def pairs(items):
        obj = {}
        for k, value in items:
            if k in obj:
                raise PrivateNativeProposalHold("duplicate saved private model source key")
            obj[k] = value
        return obj
    def nonfinite(_):
        raise PrivateNativeProposalHold("nonfinite saved private source value")
    try:
        record = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=pairs, parse_constant=nonfinite,
        )
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise PrivateNativeProposalHold("untrusted cold-reopened source record") from exc
    if _check_record(record) != raw:
        raise PrivateNativeProposalHold("private source escrow is not canonical")
    return record


def verify_private_proposal(
    source: str | Path, *, project_root: str,
    expected_file_sha256: str, expected_file_bytes: int,
    expected_job_sha256: str,
    recheck_original_source: bool = False,
) -> dict[str, object]:
    """Cold-reopen private proposal without starting any native model."""
    if (
        not _digest(expected_file_sha256)
        or not _digest(expected_job_sha256)
        or type(expected_file_bytes) is not int
        or not 1 <= expected_file_bytes <= MAX_ESCROW_BYTES
        or type(recheck_original_source) is not bool
    ):
        raise PrivateNativeProposalHold("exact saved source SHA and length required")
    path = _target(source, project_root)
    try:
        root_fd = _pinned_private_directory(path)
    except PatchExportHold as exc:
        raise PrivateNativeProposalHold("original private owner folder unavailable") from exc
    opened = None
    try:
        _identical_parent(path, root_fd)
        opened = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=root_fd,
        )
        try:
            raw = _read_exact(opened, expected_bytes=expected_file_bytes)
        except PatchExportHold as exc:
            raise PrivateNativeProposalHold("saved source custody mode/size changed") from exc
        info = os.fstat(opened)
        linked = os.stat(path.name, dir_fd=root_fd, follow_symlinks=False)
        if (
            (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            != (linked.st_dev, linked.st_ino, linked.st_size, linked.st_mtime_ns)
            or _sha(raw) != expected_file_sha256
        ):
            raise PrivateNativeProposalHold("saved source path or exact bytes changed")
        _identical_parent(path, root_fd)
        record = _parse_saved(raw)
        if record["job_sha256"] != expected_job_sha256:
            raise PrivateNativeProposalHold("private source job differs from approval")
        if recheck_original_source:
            plan = _review_proposal(
                project_root,
                schema=record["proposal_schema"],
                proposal=record["proposal"],
            )
            graph = analyze_python_source_graph(plan)
            static = require_parseable_patch(plan)
            if (
                plan.manifest_sha256 != record["source_manifest_sha256"]
                or plan.patch_sha256 != record["source_patch_sha256"]
                or graph.graph_sha256 != record["python_graph_sha256"]
                or static.status != record["static_source_status"]
            ):
                raise PrivateNativeProposalHold("original project changed since saved native work")
        return _public_receipt(
            record, raw,
            status=(
                "private-native-source-and-original-reverified"
                if recheck_original_source
                else "private-native-source-cold-verified"
            ),
        )
    finally:
        if opened is not None:
            os.close(opened)
        os.close(root_fd)


__all__ = [
    "SCHEMA", "RECEIPT_SCHEMA", "MAX_ESCROW_BYTES",
    "PrivateNativeProposalHold", "publish_private_proposal",
    "verify_private_proposal",
]
