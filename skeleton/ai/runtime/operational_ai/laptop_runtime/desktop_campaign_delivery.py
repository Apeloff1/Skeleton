"""Cold merge of independently saved real native Jeeves coding tasks.

The campaign is authoritative ONLY for what was explicitly recorded in
canonical native SQLite and privately escrowed. This adapter binds all the
completed campaign's original GGUF source work into ONE reviewed finite
Git-compatible patch or private staged source overlay, using the existing
owner's parser, path leases and source graph. A merged patch is never
automatically applied to Git or the original project.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .desktop_campaign_journal import inspect_campaign_journal
from .desktop_native_campaign import (
    SourceCampaignPlan, verify_campaign,
)
from .desktop_native_source_delivery import inspect_saved_native_source
from .desktop_patch_bundle import (
    MAX_ENTRIES, PortablePatchPlan, PatchEntry, _manifest_digest,
    _patch_bytes, get_reviewed_patch, revalidate_live_sources,
)
from .desktop_patch_export import (
    export_reviewed_patch, verify_saved_patch,
)
from .desktop_private_overlay import (
    stage_reviewed_overlay, verify_staged_overlay,
)
from .desktop_source_graph import analyze_python_source_graph
from .desktop_source_qualification import require_parseable_patch
from .desktop_workspace import _canonical

SCHEMA = "jeeves.desktop.native-campaign-source-assembly.v1"
RESULT_SCHEMA = "jeeves.desktop.native-campaign-source-assembly-receipt.v1"
MAX_SOURCE_BYTES = 1048576
MAX_PRIVATE_PATCH_BYTES = 786432


class CampaignAssemblyHold(ValueError):
    """One or more committed source tasks cannot form a reviewed source set."""


def _digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def _sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(
        ch in "0123456789abcdef" for ch in value
    )


@dataclass(frozen=True, slots=True)
class CampaignSourceAssembly:
    campaign_manifest_sha256: str
    campaign_audit_sha256: str
    combined_source_manifest_sha256: str
    combined_patch_sha256: str
    combined_python_graph_sha256: str
    assembly_sha256: str
    patch: PortablePatchPlan
    completed_native_tasks: int
    model_sha256: str
    total_replacement_bytes: int

    def __post_init__(self):
        if any(not _sha(x) for x in (
            self.campaign_manifest_sha256,
            self.campaign_audit_sha256,
            self.combined_source_manifest_sha256,
            self.combined_patch_sha256,
            self.combined_python_graph_sha256,
            self.assembly_sha256,
            self.model_sha256,
        )):
            raise CampaignAssemblyHold("exact cold model/source proof missing")
        if (
            type(self.patch) is not PortablePatchPlan
            or type(self.completed_native_tasks) is not int
            or not 1 <= self.completed_native_tasks <= 12
            or type(self.total_replacement_bytes) is not int
            or not 1 <= self.total_replacement_bytes <= MAX_SOURCE_BYTES
            or self.patch.manifest_sha256 != self.combined_source_manifest_sha256
            or self.patch.patch_sha256 != self.combined_patch_sha256
            or self.total_replacement_bytes != sum(
                e.replacement_bytes for e in self.patch.entries
            )
        ):
            raise CampaignAssemblyHold("assembled source files changed since review")
        self.patch.__post_init__()
        if (
            analyze_python_source_graph(self.patch).graph_sha256
            != self.combined_python_graph_sha256
            or self.assembly_sha256 != _assembly_sha(self)
        ):
            raise CampaignAssemblyHold("source import graph or campaign binding changed")

    def public_review(self) -> dict[str, object]:
        return {
            "schema": RESULT_SCHEMA,
            "status": "combined-native-source-reviewed-no-write",
            "campaign_manifest_sha256": self.campaign_manifest_sha256,
            "campaign_audit_sha256": self.campaign_audit_sha256,
            "combined_source_manifest_sha256": self.combined_source_manifest_sha256,
            "combined_patch_sha256": self.combined_patch_sha256,
            "combined_python_graph_sha256": self.combined_python_graph_sha256,
            "assembly_sha256": self.assembly_sha256,
            "original_native_model_sha256": self.model_sha256,
            "native_task_count": self.completed_native_tasks,
            "merged_source_count": len(self.patch.entries),
            "new_source_files": sum(x.kind == "new" for x in self.patch.entries),
            "existing_source_edits": sum(x.kind == "edit" for x in self.patch.entries),
            "total_replacement_bytes": self.total_replacement_bytes,
            "generated_source_in_stdout": False,
            "original_checkout_modified": False,
            "native_code_executed": False,
            "git_commands_executed": False,
            "release_certified": False,
        }


def _assembly_sha(plan: CampaignSourceAssembly) -> str:
    return _digest(_canonical({
        "schema": SCHEMA,
        "campaign_manifest_sha256": plan.campaign_manifest_sha256,
        "campaign_audit_sha256": plan.campaign_audit_sha256,
        "combined_source_manifest_sha256": plan.combined_source_manifest_sha256,
        "combined_patch_sha256": plan.combined_patch_sha256,
        "combined_python_graph_sha256": plan.combined_python_graph_sha256,
        "native_model_sha256": plan.model_sha256,
        "native_task_count": plan.completed_native_tasks,
        "source_bytes": plan.total_replacement_bytes,
    }))


def inspect_campaign_assembly(plan: SourceCampaignPlan) -> CampaignSourceAssembly:
    """Fresh cold read of ALL previously committed, escrowed real model code."""
    plan.__post_init__()
    cold = verify_campaign(plan, recheck_original_source=True)
    if cold["all_source_escrows_cold_verified"] is not True:
        raise CampaignAssemblyHold("not all original native jobs have saved source")
    audit = inspect_campaign_journal(
        plan.journal_file, project_root=plan.project_root,
        manifest_sha256=plan.manifest_sha256,
        task_ids=tuple(t.task_id for t in plan.tasks),
    )
    if audit["all_tasks_completed"] is not True:
        raise CampaignAssemblyHold("cannot combine uncertain native model effects")
    all_entries: list[PatchEntry] = []
    used: set[str] = set()
    original_identity = None
    model_identity = None
    amount = 0
    for task in plan.tasks:
        saved = audit["saved_receipts"].get(task.task_id)
        if type(saved) is not dict or saved.get("job_sha256") != task.expected_job_sha256:
            raise CampaignAssemblyHold("saved source task lacks exact SQLite identity")
        reviewed = inspect_saved_native_source(
            task.target,
            project_root=plan.project_root,
            expected_job_sha256=task.expected_job_sha256,
            expected_file_sha256=saved["private_file_sha256"],
            expected_file_bytes=saved["private_file_bytes"],
        )
        if any(
            getattr(reviewed, key) != saved[declared]
            for key, declared in (
                ("job_sha256", "job_sha256"),
                ("private_file_sha256", "private_file_sha256"),
                ("source_manifest_sha256", "source_manifest_sha256"),
                ("patch_sha256", "source_patch_sha256"),
                ("model_sha256", "model_sha256"),
            )
        ):
            raise CampaignAssemblyHold("cold reviewed source does not match campaign receipt")
        source_plan = reviewed.source_plan
        source_plan.__post_init__()
        identity = (source_plan.root_device, source_plan.root_inode, source_plan.root)
        if original_identity is None:
            original_identity = identity
        if original_identity != identity:
            raise CampaignAssemblyHold("source tasks changed original project root inode")
        if model_identity is None:
            model_identity = reviewed.model_sha256
        if model_identity != reviewed.model_sha256:
            raise CampaignAssemblyHold("campaign crossed pinned original GGUF model")
        for entry in source_plan.entries:
            entry.__post_init__()
            if entry.path.casefold() in used:
                # No "last model wins": separate tasks cannot overwrite
                # each other's proposed new or existing file changes.
                raise CampaignAssemblyHold("independent model tasks wrote same source path")
            used.add(entry.path.casefold())
            all_entries.append(entry)
            amount += entry.replacement_bytes
            if len(all_entries) > MAX_ENTRIES or amount > MAX_SOURCE_BYTES:
                raise CampaignAssemblyHold("aggregate original coding output over budget")
    entries = tuple(sorted(all_entries, key=lambda e: (e.path.casefold(), e.path)))
    patch = _patch_bytes(entries)
    combined = PortablePatchPlan(
        root=plan.project_root,
        root_device=original_identity[0],
        root_inode=original_identity[1],
        entries=entries,
        manifest_sha256=_manifest_digest(entries),
        patch_sha256=_digest(patch),
        patch_bytes=len(patch),
    )
    # The COMBINED source may have imports that were not resolvable in each
    # individual native task. Re-run actual static qualification and source
    # graph against the whole original set, not individual model verdicts.
    static = require_parseable_patch(combined)
    graph = analyze_python_source_graph(combined)
    if not static.permits_inert_export or not graph.permits_inert_export:
        raise CampaignAssemblyHold("new cross-task Python source graph invalid")
    revalidate_live_sources(combined)
    get_reviewed_patch(combined)
    core = {
        "schema": SCHEMA,
        "campaign_manifest_sha256": plan.manifest_sha256,
        "campaign_audit_sha256": audit["last_event_sha256"],
        "combined_source_manifest_sha256": combined.manifest_sha256,
        "combined_patch_sha256": combined.patch_sha256,
        "combined_python_graph_sha256": graph.graph_sha256,
        "native_model_sha256": model_identity,
        "native_task_count": len(plan.tasks),
        "source_bytes": amount,
    }
    assembly = CampaignSourceAssembly(
        campaign_manifest_sha256=plan.manifest_sha256,
        campaign_audit_sha256=audit["last_event_sha256"],
        combined_source_manifest_sha256=combined.manifest_sha256,
        combined_patch_sha256=combined.patch_sha256,
        combined_python_graph_sha256=graph.graph_sha256,
        assembly_sha256=_digest(_canonical(core)),
        patch=combined,
        completed_native_tasks=len(plan.tasks),
        model_sha256=model_identity,
        total_replacement_bytes=amount,
    )
    return assembly


def publish_campaign_assembly(
    plan: SourceCampaignPlan, destination: str, *,
    output_kind: str, expected_assembly_sha256: str,
    expected_manifest_sha256: str, expected_patch_sha256: str,
    approve_delivery: bool,
) -> dict[str, object]:
    """Exact fresh model-source review; separate manual private delivery only."""
    if (
        approve_delivery is not True
        or output_kind not in ("private-stage", "git-patch")
        or any(not _sha(x) for x in (
            expected_assembly_sha256, expected_manifest_sha256,
            expected_patch_sha256,
        ))
    ):
        raise CampaignAssemblyHold("explicit complete source bundle authority required")
    assembly = inspect_campaign_assembly(plan)
    if any((
        assembly.assembly_sha256 != expected_assembly_sha256,
        assembly.combined_source_manifest_sha256 != expected_manifest_sha256,
        assembly.combined_patch_sha256 != expected_patch_sha256,
    )):
        raise CampaignAssemblyHold("reviewed source bundle/model receipts changed")
    if output_kind == "git-patch":
        published = export_reviewed_patch(
            assembly.patch, destination,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_patch_sha256=expected_patch_sha256,
            approve_export=True,
        )
        check = verify_saved_patch(
            destination, expected_patch_sha256=expected_patch_sha256,
            expected_bytes=assembly.patch.patch_bytes,
            workspace_root=plan.project_root,
        )
    else:
        published = stage_reviewed_overlay(
            assembly.patch, destination,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_patch_sha256=expected_patch_sha256,
            approve_staging=True,
        )
        check = verify_staged_overlay(
            destination, expected_manifest_sha256=expected_manifest_sha256,
            expected_patch_sha256=expected_patch_sha256,
            workspace_root=plan.project_root,
        )
    # Publication is terminal before this cold proof; a failed proof never
    # grants a rerun or deletes a possibly substituted file.
    if (
        type(published) is not dict or type(check) is not dict
        or (
            output_kind == "git-patch" and (
                check.get("status") != "verified-inert-source-patch"
                or check.get("patch_sha256") != expected_patch_sha256
                or check.get("bytes") != assembly.patch.patch_bytes
                or check.get("patch_applied") is not False
            )
        )
        or (
            output_kind == "private-stage" and (
                check.get("status") != "complete-private-source-overlay-snapshot"
                or check.get("manifest_sha256") != expected_manifest_sha256
                or check.get("patch_sha256") != expected_patch_sha256
                or check.get("file_count") != len(assembly.patch.entries)
                or check.get("source_code_executed") is not False
            )
        )
    ):
        raise CampaignAssemblyHold("combined source cold publication is unverified")
    return {
        **assembly.public_review(),
        "status": "new-cold-verified-multi-task-source-delivery",
        "output_kind": output_kind,
        "private_publication": {
            "manifest_sha256": expected_manifest_sha256,
            "patch_sha256": expected_patch_sha256,
            "verified": True,
        },
        "original_checkout_modified": False,
        "source_code_executed": False,
        "release_certified": False,
    }


__all__ = [
    "SCHEMA", "RESULT_SCHEMA", "CampaignAssemblyHold",
    "CampaignSourceAssembly", "inspect_campaign_assembly",
    "publish_campaign_assembly",
]
