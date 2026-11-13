"""Review a private real-GGUF proposal and deliver its exact source without a model.

This final independent operator gate closes the offline Jeeves coding loop:

    real local GGUF + canonical SQLite commit
      -> immutable private owner-only model proposal
      -> COLD descriptor-verified original source/patch review
      -> explicit NEW private source overlay or inert Git patch

It intentionally NEVER regenerates, replays or imports model output,
modifies the original checkout, invokes Git, executes generated source or
grants native tools. Stored private source is loaded through pinned
O_NOFOLLOW descriptors and stays in trusted process memory, not stdout.
Every source is rechecked before and after separate private publication.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path

from .desktop_native_proposal_custody import (
    MAX_ESCROW_BYTES, _parse_saved, _target, _review_proposal,
)
from .desktop_patch_export import (
    PatchExportHold, _pinned_private_directory,
    _identical_parent, _read_exact, export_reviewed_patch,
)
from .desktop_patch_bundle import (
    PortablePatchPlan, revalidate_live_sources,
)
from .desktop_private_overlay import (
    stage_reviewed_overlay,
)
from .desktop_source_qualification import require_parseable_patch
from .desktop_source_graph import analyze_python_source_graph

SCHEMA = "jeeves.workspace.private-native-escrow-delivery.v1"
MAX_FINAL_FILES = 24


class NativeSourceDeliveryHold(ValueError):
    """Private original source is untrusted, stale or not independently approved."""


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _digest(value: object) -> bool:
    return (
        type(value) is str and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


@dataclass(frozen=True, slots=True)
class ReviewedNativeDelivery:
    job_sha256: str
    private_file_sha256: str
    source_manifest_sha256: str
    patch_sha256: str
    model_sha256: str
    python_graph_sha256: str
    private_file_bytes: int
    source_plan: PortablePatchPlan
    static_status: str

    def __post_init__(self):
        for name in (
            "job_sha256", "private_file_sha256",
            "source_manifest_sha256", "patch_sha256",
            "model_sha256", "python_graph_sha256",
        ):
            if not _digest(getattr(self, name)):
                raise NativeSourceDeliveryHold("exact saved source or model SHA missing")
        if (
            type(self.private_file_bytes) is not int
            or not 1 <= self.private_file_bytes <= MAX_ESCROW_BYTES
            or type(self.source_plan) is not PortablePatchPlan
            or not 1 <= len(self.source_plan.entries) <= MAX_FINAL_FILES
            or self.source_plan.manifest_sha256 != self.source_manifest_sha256
            or self.source_plan.patch_sha256 != self.patch_sha256
            or self.static_status not in ("parse-clean", "mixed-unverified")
        ):
            raise NativeSourceDeliveryHold("stale original operator source review")
        self.source_plan.__post_init__()

    def public_review(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "status": "cold-saved-native-source-reviewed-not-applied",
            "job_sha256": self.job_sha256,
            "saved_source_file_sha256": self.private_file_sha256,
            "saved_source_file_bytes": self.private_file_bytes,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_patch_sha256": self.patch_sha256,
            "original_native_model_sha256": self.model_sha256,
            "python_graph_sha256": self.python_graph_sha256,
            "static_source_status": self.static_status,
            "source_files": [item.public() for item in self.source_plan.entries],
            "source_file_count": len(self.source_plan.entries),
            "new_file_count": sum(
                item.kind == "new" for item in self.source_plan.entries
            ),
            "existing_edit_count": sum(
                item.kind == "edit" for item in self.source_plan.entries
            ),
            "operator_must_review_private_source_and_full_diffs": True,
            "additional_native_inference_executed": False,
            "source_contents_in_stdout": False,
            "original_project_modified": False,
            "git_commands_executed": False,
            "model_file_write_grants": False,
            "release_certified": False,
        }


def inspect_saved_native_source(
    source: str | Path, *, project_root: str,
    expected_job_sha256: str,
    expected_file_sha256: str,
    expected_file_bytes: int,
) -> ReviewedNativeDelivery:
    """Read real original source+escrow; no model session/side effects."""
    if (
        type(project_root) is not str
        or not Path(project_root).is_absolute()
        or ".." in Path(project_root).parts
        or not _digest(expected_job_sha256)
        or not _digest(expected_file_sha256)
        or type(expected_file_bytes) is not int
        or not 1 <= expected_file_bytes <= MAX_ESCROW_BYTES
    ):
        raise NativeSourceDeliveryHold("complete original source/escrow identity required")
    path = _target(source, project_root)
    try:
        parent = _pinned_private_directory(path)
    except PatchExportHold as exc:
        raise NativeSourceDeliveryHold("private saved native source root unavailable") from exc
    opened = None
    try:
        _identical_parent(path, parent)
        opened = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
        try:
            raw = _read_exact(opened, expected_bytes=expected_file_bytes)
        except PatchExportHold as exc:
            raise NativeSourceDeliveryHold("owner-private source file mode/length changed") from exc
        source_info = os.fstat(opened)
        linked = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (
            (source_info.st_dev, source_info.st_ino, source_info.st_size,
             source_info.st_mtime_ns)
            != (linked.st_dev, linked.st_ino, linked.st_size, linked.st_mtime_ns)
            or _sha(raw) != expected_file_sha256
        ):
            raise NativeSourceDeliveryHold("source escrow inode/bytes differ from review")
        _identical_parent(path, parent)
        record = _parse_saved(raw)
        if record["job_sha256"] != expected_job_sha256:
            raise NativeSourceDeliveryHold("escrow belongs to another original model task")
        # The original model source remains private and is NEVER returned in
        # the public typed review; the module reconstructs a fresh checked
        # PortablePatchPlan from the actual source workspace.
        plan = _review_proposal(
            project_root, schema=record["proposal_schema"],
            proposal=record["proposal"],
        )
        static = require_parseable_patch(plan)
        graph = analyze_python_source_graph(plan)
        if (
            plan.manifest_sha256 != record["source_manifest_sha256"]
            or plan.patch_sha256 != record["source_patch_sha256"]
            or static.status != record["static_source_status"]
            or not static.permits_inert_export
            or graph.graph_sha256 != record["python_graph_sha256"]
            or not graph.permits_inert_export
        ):
            raise NativeSourceDeliveryHold(
                "fresh original source, parser or graph differs from saved GGUF work",
            )
        revalidate_live_sources(plan)
        # Verify private file path/inode again after original project reads.
        newest = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (
            newest.st_dev != linked.st_dev
            or newest.st_ino != linked.st_ino
            or newest.st_size != linked.st_size
            or newest.st_mtime_ns != linked.st_mtime_ns
        ):
            raise NativeSourceDeliveryHold(
                "private source file changed during original project review",
            )
        return ReviewedNativeDelivery(
            job_sha256=record["job_sha256"],
            private_file_sha256=expected_file_sha256,
            source_manifest_sha256=plan.manifest_sha256,
            patch_sha256=plan.patch_sha256,
            model_sha256=record["model_sha256"],
            python_graph_sha256=graph.graph_sha256,
            private_file_bytes=len(raw),
            source_plan=plan,
            static_status=static.status,
        )
    finally:
        if opened is not None:
            os.close(opened)
        os.close(parent)


def deliver_saved_native_source(
    reviewed: ReviewedNativeDelivery,
    destination: str | Path, *,
    action: str,
    expected_manifest_sha256: str,
    expected_patch_sha256: str,
    approve_private_stage: bool = False,
    approve_private_patch: bool = False,
) -> dict[str, object]:
    """Explicit source review to private artifact without any new inference."""
    if type(reviewed) is not ReviewedNativeDelivery:
        raise NativeSourceDeliveryHold("original typed source review required")
    reviewed.__post_init__()
    if (
        not _digest(expected_manifest_sha256)
        or not _digest(expected_patch_sha256)
        or expected_manifest_sha256 != reviewed.source_manifest_sha256
        or expected_patch_sha256 != reviewed.patch_sha256
        or type(action) is not str or action not in ("stage", "export-patch")
        or type(approve_private_stage) is not bool
        or type(approve_private_patch) is not bool
    ):
        raise NativeSourceDeliveryHold("full current source/patch digests required")
    if action == "stage":
        if approve_private_stage is not True or approve_private_patch is True:
            raise NativeSourceDeliveryHold("separate single private-stage approval required")
        receipt = stage_reviewed_overlay(
            reviewed.source_plan, destination,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_patch_sha256=expected_patch_sha256,
            approve_staging=True,
        )
    else:
        if approve_private_patch is not True or approve_private_stage is True:
            raise NativeSourceDeliveryHold("separate inert Git-patch approval required")
        receipt = export_reviewed_patch(
            reviewed.source_plan, destination,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_patch_sha256=expected_patch_sha256,
            approve_export=True,
        )
    if (
        receipt.get("manifest_sha256") != reviewed.source_manifest_sha256
        or receipt.get("patch_sha256") != reviewed.patch_sha256
        or receipt.get("release_certified") is not False
    ):
        raise NativeSourceDeliveryHold("private source publication lacks exact review identity")
    return {
        "schema": "jeeves.workspace.private-native-escrow-delivery-result.v1",
        "action": action,
        "status": (
            "new-private-source-stage-completed"
            if action == "stage" else "new-private-source-patch-completed"
        ),
        "original_job_sha256": reviewed.job_sha256,
        "original_model_sha256": reviewed.model_sha256,
        "saved_proposal_sha256": reviewed.private_file_sha256,
        "source_manifest_sha256": reviewed.source_manifest_sha256,
        "source_patch_sha256": reviewed.patch_sha256,
        "python_graph_sha256": reviewed.python_graph_sha256,
        "publication": receipt,
        "additional_model_inference_executed": False,
        "source_contents_in_stdout": False,
        "original_project_modified": False,
        "git_commands_executed": False,
        "source_code_executed": False,
        "release_certified": False,
    }


__all__ = [
    "SCHEMA", "NativeSourceDeliveryHold", "ReviewedNativeDelivery",
    "inspect_saved_native_source", "deliver_saved_native_source",
]
