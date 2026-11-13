"""Single-owner, finite, explicitly approved real GGUF source-work campaigns.

This composes the EXISTING native GGUF/SQLite source generator and the EXISTING
owner-private proposal escrow for a serial campaign of original source work.
There is no second model owner, simulated inference, implicit provider,
automatic retry, dynamic source execution, Git write or project modification.

Each task is independently inspected against the original live file SHAs.
The campaign manifest binds exact task order, model budgets, dependencies,
project source, job digests and new private output targets. An append-only,
fsynced receipt journal records INTENT before each real model request. A
crash or failed model step is non-retryable without a fresh operator campaign.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Callable

from .desktop_campaign_journal import (
    CampaignJournalWriter, NativeCampaignJournalHold, _path as _journal_path,
    inspect_campaign_journal,
)
from .desktop_client import DesktopBridge
from .desktop_native_code_cli import (
    execute_native_request, parse_native_request,
)
from .desktop_native_proposal_cli import (
    SCHEMA as ESCROW_SCHEMA,
    execute_escrow_request, parse_escrow_request,
    _preflight_empty_destination,
)
from .desktop_native_proposal_custody import (
    _target, verify_private_proposal,
)
from .desktop_patch_export import _pinned_private_directory, _identical_parent
from .desktop_workspace import _canonical

SCHEMA = "jeeves.desktop.native-source-campaign.v1"
RESULT_SCHEMA = "jeeves.desktop.native-source-campaign-receipt.v1"
MAX_REQUEST_BYTES = 131072
MAX_TASKS = 12
MAX_OUTPUT_BYTES = 32768
MAX_TOTAL_ATTEMPTS = 24
MAX_INFERENCE_MS = 1200000
MAX_OUTPUT_TOKENS = 65536
_MAX_GOAL_BYTES = 16384
_TASK_ID = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")
_FIELDS = frozenset((
    "schema", "action", "project_root", "journal_file",
    "manifest_sha256", "recheck_original_source", "tasks",
))
_TASK_FIELDS = frozenset((
    "task_id", "depends_on", "target",
    "expected_job_sha256", "native_request",
))


class NativeCampaignHold(ValueError):
    """Campaign source identity, operator authority, or custody is invalid."""


def _sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(
        char in "0123456789abcdef" for char in value
    )


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise NativeCampaignHold("duplicate private source campaign key")
        result[key] = value
    return result


def _nonfinite(_):
    raise NativeCampaignHold("nonfinite private source campaign budget")


def _absolute(value: object) -> str:
    if (
        type(value) is not str or not value or len(value) > 4096
        or "\x00" in value or not Path(value).is_absolute()
        or ".." in Path(value).parts
    ):
        raise NativeCampaignHold("absolute canonical campaign source root required")
    return value


@dataclass(frozen=True, slots=True)
class SourceCampaignTask:
    task_id: str
    depends_on: tuple[str, ...]
    target: str
    expected_job_sha256: str
    native_request: dict

    def __post_init__(self):
        if (
            type(self.task_id) is not str or not _TASK_ID.fullmatch(self.task_id)
            or type(self.depends_on) is not tuple
            or any(type(x) is not str or not _TASK_ID.fullmatch(x)
                   for x in self.depends_on)
            or len(set(self.depends_on)) != len(self.depends_on)
            or self.task_id in self.depends_on
            or not _sha(self.expected_job_sha256)
            or type(self.native_request) is not dict
        ):
            raise NativeCampaignHold("untrusted model campaign task/dependency")
        checked = parse_native_request(_canonical(self.native_request))
        if (
            checked["action"] != "generate"
            or checked["job_sha256"] != self.expected_job_sha256
        ):
            raise NativeCampaignHold("original exact approved model task is missing")
        _absolute(self.target)

    def document(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "depends_on": list(self.depends_on),
            "target": self.target,
            "expected_job_sha256": self.expected_job_sha256,
            "native_request": self.native_request,
        }


@dataclass(frozen=True, slots=True)
class SourceCampaignPlan:
    project_root: str
    journal_file: str
    manifest_sha256: str
    tasks: tuple[SourceCampaignTask, ...]
    total_attempts: int
    total_output_tokens: int
    total_inference_ms: int

    def __post_init__(self):
        _absolute(self.project_root)
        _journal_path(self.journal_file, self.project_root)
        if (
            not _sha(self.manifest_sha256)
            or type(self.tasks) is not tuple
            or not 1 <= len(self.tasks) <= MAX_TASKS
            or any(type(t) is not SourceCampaignTask for t in self.tasks)
            or type(self.total_attempts) is not int
            or type(self.total_output_tokens) is not int
            or type(self.total_inference_ms) is not int
        ):
            raise NativeCampaignHold("finite typed source work campaign required")
        seen: set[str] = set()
        targets: set[str] = set()
        base = None
        attempts = 0
        output = 0
        wall = 0
        for task in self.tasks:
            task.__post_init__()
            if task.task_id in seen or any(dep not in seen for dep in task.depends_on):
                raise NativeCampaignHold("non-topological or duplicate source task")
            seen.add(task.task_id)
            req = task.native_request
            model_state_owner = (
                req["project_root"], req["model_root"], req["state_dir"],
                req["tenant"], req["subject"],
            )
            if base is None:
                base = model_state_owner
            if model_state_owner != base or req["project_root"] != self.project_root:
                raise NativeCampaignHold("native campaign crossed model/session/source owner")
            destination = _target(task.target, self.project_root)
            audit = Path(self.journal_file)
            if (
                audit.is_relative_to(Path(req["model_root"]))
                or audit.is_relative_to(Path(req["state_dir"]))
                or destination.parent != audit.parent
                or task.target.casefold() in targets
                or destination == audit
                or destination.is_relative_to(Path(req["model_root"]))
                or destination.is_relative_to(Path(req["state_dir"]))
            ):
                raise NativeCampaignHold("private campaign escrow output collides with a source owner")
            targets.add(task.target.casefold())
            attempts += req["maximum_attempts"]
            output += req["max_output_tokens"] * req["maximum_attempts"]
            wall += req["inference_ms"] * req["maximum_attempts"]
        if (
            attempts != self.total_attempts or output != self.total_output_tokens
            or wall != self.total_inference_ms
            or attempts > MAX_TOTAL_ATTEMPTS or output > MAX_OUTPUT_TOKENS
            or wall > MAX_INFERENCE_MS
            or self.manifest_sha256 != _manifest(self.project_root,
                                                 self.journal_file, self.tasks)
        ):
            raise NativeCampaignHold("campaign resource budget or approval digest changed")

    def public(self) -> dict[str, object]:
        return {
            "schema": RESULT_SCHEMA,
            "status": "review-required-before-original-native-campaign",
            "manifest_sha256": self.manifest_sha256,
            "task_count": len(self.tasks),
            "total_maximum_native_attempts": self.total_attempts,
            "total_maximum_output_tokens": self.total_output_tokens,
            "total_maximum_inference_ms": self.total_inference_ms,
            "task_receipts": [
                {
                    "task_id": item.task_id,
                    "depends_on": list(item.depends_on),
                    "job_sha256": item.expected_job_sha256,
                    "goal_sha256": sha256(
                        item.native_request["goal"].encode("utf-8", "strict"),
                    ).hexdigest(),
                    "private_target_disclosed": False,
                }
                for item in self.tasks
            ],
            "model_started": False,
            "private_source_in_stdout": False,
            "original_project_modified": False,
            "release_certified": False,
        }


def _manifest(project_root: str, journal_file: str,
              tasks: tuple[SourceCampaignTask, ...]) -> str:
    payload = {
        "schema": SCHEMA,
        "project_root": project_root,
        "journal_file": journal_file,
        "tasks": [task.document() for task in tasks],
    }
    return sha256(_canonical(payload)).hexdigest()


def parse_campaign(raw: bytes) -> tuple[SourceCampaignPlan, dict]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST_BYTES:
        raise NativeCampaignHold("finite strict private campaign JSON required")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs, parse_constant=_nonfinite,
        )
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise NativeCampaignHold("ambiguous private campaign request") from exc
    if (
        type(value) is not dict or frozenset(value) != _FIELDS
        or value["schema"] != SCHEMA
        or value["action"] not in ("inspect", "run", "verify")
        or type(value["recheck_original_source"]) is not bool
    ):
        raise NativeCampaignHold("source campaign action or strict fields invalid")
    project_root = _absolute(value["project_root"])
    _journal_path(value["journal_file"], project_root)
    task_data = value["tasks"]
    if type(task_data) is not list or not 1 <= len(task_data) <= MAX_TASKS:
        raise NativeCampaignHold("one to twelve explicit native source tasks required")
    tasks = []
    for item in task_data:
        if (
            type(item) is not dict or frozenset(item) != _TASK_FIELDS
            or type(item["depends_on"]) is not list
        ):
            raise NativeCampaignHold("unsupported native source task fields")
        task = SourceCampaignTask(
            task_id=item["task_id"],
            depends_on=tuple(item["depends_on"]),
            target=item["target"],
            expected_job_sha256=item["expected_job_sha256"],
            native_request=item["native_request"],
        )
        tasks.append(task)
    series = tuple(tasks)
    manifest = _manifest(project_root, value["journal_file"], series)
    approved = value["manifest_sha256"]
    if value["action"] == "inspect":
        if approved is not None or value["recheck_original_source"]:
            raise NativeCampaignHold("read-only inspection cannot carry run consent")
    elif approved != manifest:
        raise NativeCampaignHold("original operator reviewed campaign SHA missing or stale")
    plan = SourceCampaignPlan(
        project_root=project_root, journal_file=value["journal_file"],
        manifest_sha256=manifest, tasks=series,
        total_attempts=sum(x.native_request["maximum_attempts"] for x in series),
        total_output_tokens=sum(
            x.native_request["max_output_tokens"]
            * x.native_request["maximum_attempts"] for x in series
        ),
        total_inference_ms=sum(
            x.native_request["inference_ms"]
            * x.native_request["maximum_attempts"] for x in series
        ),
    )
    return plan, value


def _inspect_all(plan: SourceCampaignPlan) -> None:
    for item in plan.tasks:
        native = {
            **item.native_request,
            "action": "inspect",
            "job_sha256": None,
        }
        inspected = execute_native_request(native, approve_native=False)
        if (
            type(inspected) is not dict
            or inspected.get("job_sha256") != item.expected_job_sha256
            or inspected.get("release_certified") is not False
            or inspected.get("native_gguf_started") is not False
        ):
            raise NativeCampaignHold("reviewed original source/model job SHA changed")


def inspect_campaign(plan: SourceCampaignPlan) -> dict[str, object]:
    plan.__post_init__()
    _inspect_all(plan)
    return plan.public()


def _escrow_request(plan: SourceCampaignPlan, task: SourceCampaignTask) -> dict:
    return {
        "schema": ESCROW_SCHEMA, "action": "generate-save",
        "project_root": plan.project_root,
        "target": task.target,
        "native_request": task.native_request,
        "expected_job_sha256": task.expected_job_sha256,
        "expected_file_sha256": None, "expected_file_bytes": None,
        "recheck_original_source": False,
    }


def _preflight_all(plan: SourceCampaignPlan) -> None:
    journal = Path(plan.journal_file)
    private = _pinned_private_directory(journal)
    try:
        _identical_parent(journal, private)
        names = (journal.name,) + tuple(Path(t.target).name for t in plan.tasks)
        for name in names:
            try:
                os.stat(name, dir_fd=private, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise NativeCampaignHold("original private campaign output already exists")
    finally:
        os.close(private)
    for item in plan.tasks:
        _preflight_empty_destination(
            parse_escrow_request(_canonical(_escrow_request(plan, item))),
        )


def _saved_receipt(value: dict, job_sha256: str) -> dict:
    if (
        type(value) is not dict
        or value.get("status") != "native-proposal-saved-owner-private-no-source-stdout"
        or value.get("source_contents_in_stdout") is not False
        or value.get("original_source_modified") is not False
        or value.get("generated_code_executed") is not False
        or value.get("release_certified") is not False
    ):
        raise NativeCampaignHold("model did not yield a separately reviewed private escrow")
    saved = value.get("private_source")
    if (
        type(saved) is not dict
        or saved.get("job_sha256") != job_sha256
        or saved.get("status") != "private-reviewed-native-source-saved"
    ):
        raise NativeCampaignHold("private model source receipt lacks correct job ownership")
    keys = (
        "job_sha256", "private_file_sha256", "private_file_bytes",
        "model_sha256", "session_id", "source_manifest_sha256",
        "source_patch_sha256",
    )
    return {key: saved[key] for key in keys}


def _status(plan: SourceCampaignPlan, *, status: str,
            audit: dict | None = None) -> dict[str, object]:
    return {
        "schema": RESULT_SCHEMA,
        "status": status,
        "manifest_sha256": plan.manifest_sha256,
        "task_count": len(plan.tasks),
        "source_audit": {
            key: value for key, value in (audit or {}).items()
            if key not in ("saved_receipts",)
        } if audit else None,
        "native_sqlite_may_have_committed": status != "all-private-source-escrows-cold-verified",
        "native_call_auto_retry_permitted": False,
        "operator_must_inspect_sqlite_on_uncertain_state": status != "all-private-source-escrows-cold-verified",
        "private_source_in_stdout": False,
        "original_project_modified": False,
        "release_certified": False,
    }


def run_campaign(
    plan: SourceCampaignPlan, *,
    approve_campaign: bool, approve_native: bool,
    approve_private_storage: bool,
    bridge_factory: Callable[..., DesktopBridge] = DesktopBridge,
) -> dict[str, object]:
    """Execute explicitly approved tasks serially; never replay uncertain jobs."""
    if any(
        x is not True for x in (
            approve_campaign, approve_native, approve_private_storage,
        )
    ) or not callable(bridge_factory):
        raise NativeCampaignHold("separate original campaign/native/private approvals required")
    plan.__post_init__()
    _inspect_all(plan)
    _preflight_all(plan)
    seen: set[str] = set()
    with CampaignJournalWriter(
        plan.journal_file, project_root=plan.project_root,
        manifest_sha256=plan.manifest_sha256,
    ) as audit:
        audit.append("begin")
        for task in plan.tasks:
            if any(dependency not in seen for dependency in task.depends_on):
                raise NativeCampaignHold("original native task dependency has not completed")
            # Recheck this original task and exact selected source immediately
            # before writing the native INTENT and starting GGUF/SQLite.
            _inspect_all(plan)
            audit.append("attempt", task_id=task.task_id, evidence={
                "job_sha256": task.expected_job_sha256,
            })
            try:
                value = execute_escrow_request(
                    _escrow_request(plan, task),
                    approve_native=True, approve_private_storage=True,
                    bridge_factory=bridge_factory,
                )
                saved = _saved_receipt(value, task.expected_job_sha256)
                verified = verify_private_proposal(
                    task.target, project_root=plan.project_root,
                    expected_job_sha256=task.expected_job_sha256,
                    expected_file_sha256=saved["private_file_sha256"],
                    expected_file_bytes=saved["private_file_bytes"],
                    recheck_original_source=True,
                )
                if any(verified.get(k) != saved[k] for k in saved):
                    raise NativeCampaignHold("cold native source proof drifted after publication")
                audit.append("saved", task_id=task.task_id, evidence=saved)
                seen.add(task.task_id)
            except (Exception, KeyboardInterrupt):
                # Native SQLite may have committed at ANY point after INTENT.
                # Never issue a second call, even if private source is absent.
                try:
                    audit.append("halt", evidence={"reason": "native-uncertain"})
                except Exception:
                    pass
                return _status(
                    plan, status="native-campaign-held-no-auto-retry",
                    audit=inspect_campaign_journal(
                        plan.journal_file, project_root=plan.project_root,
                        manifest_sha256=plan.manifest_sha256,
                        task_ids=tuple(t.task_id for t in plan.tasks),
                    ),
                )
        audit.append("complete")
    checked = verify_campaign(plan, recheck_original_source=True)
    if not checked["all_source_escrows_cold_verified"]:
        return _status(plan, status="native-campaign-held-no-auto-retry",
                       audit=checked["source_audit"])
    return _status(
        plan, status="all-private-source-escrows-cold-verified",
        audit=checked["source_audit"],
    )


def verify_campaign(
    plan: SourceCampaignPlan, *, recheck_original_source: bool = False,
) -> dict[str, object]:
    """No model startup; independently re-open every completed private escrow."""
    if type(recheck_original_source) is not bool:
        raise NativeCampaignHold("strict cold model review flag required")
    plan.__post_init__()
    journal = inspect_campaign_journal(
        plan.journal_file, project_root=plan.project_root,
        manifest_sha256=plan.manifest_sha256,
        task_ids=tuple(t.task_id for t in plan.tasks),
    )
    receipts = journal["saved_receipts"]
    verified = 0
    for task in plan.tasks:
        saved = receipts.get(task.task_id)
        if saved is None:
            continue
        if saved["job_sha256"] != task.expected_job_sha256:
            raise NativeCampaignHold("saved native result does not match approved task")
        cold = verify_private_proposal(
            task.target, project_root=plan.project_root,
            expected_job_sha256=task.expected_job_sha256,
            expected_file_sha256=saved["private_file_sha256"],
            expected_file_bytes=saved["private_file_bytes"],
            recheck_original_source=recheck_original_source,
        )
        if any(cold.get(key) != value for key, value in saved.items()):
            raise NativeCampaignHold("private source cold inspection differs from audit")
        verified += 1
    complete = journal["all_tasks_completed"] and verified == len(plan.tasks)
    public = {
        key: value for key, value in journal.items()
        if key not in ("saved_receipts",)
    }
    return {
        "schema": RESULT_SCHEMA,
        "status": (
            "all-private-source-escrows-cold-verified"
            if complete else "incomplete-native-campaign-no-auto-retry"
        ),
        "manifest_sha256": plan.manifest_sha256,
        "source_audit": public,
        "cold_verified_private_source_count": verified,
        "all_source_escrows_cold_verified": complete,
        "native_model_started": False,
        "source_code_executed": False,
        "original_project_modified": False,
        "native_call_auto_retry_permitted": False,
        "release_certified": False,
    }


def execute_campaign_request(
    request: dict, *,
    approve_campaign: bool = False,
    approve_native: bool = False,
    approve_private_storage: bool = False,
    bridge_factory: Callable[..., DesktopBridge] = DesktopBridge,
) -> dict[str, object]:
    if type(request) is not dict or any(
        type(x) is not bool for x in (
            approve_campaign, approve_native, approve_private_storage,
        )
    ):
        raise NativeCampaignHold("typed explicit campaign approvals required")
    plan, req = parse_campaign(_canonical(request))
    flags = (approve_campaign, approve_native, approve_private_storage)
    if req["action"] != "run" and any(flags):
        raise NativeCampaignHold("read-only campaign review must not carry native grants")
    if req["action"] == "inspect":
        return inspect_campaign(plan)
    if req["action"] == "verify":
        return verify_campaign(
            plan, recheck_original_source=req["recheck_original_source"],
        )
    return run_campaign(
        plan, approve_campaign=approve_campaign,
        approve_native=approve_native,
        approve_private_storage=approve_private_storage,
        bridge_factory=bridge_factory,
    )


__all__ = [
    "SCHEMA", "RESULT_SCHEMA", "NativeCampaignHold",
    "SourceCampaignTask", "SourceCampaignPlan", "parse_campaign",
    "inspect_campaign", "run_campaign", "verify_campaign",
    "execute_campaign_request",
]
