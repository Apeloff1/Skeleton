"""Read-only exact-source task composer for local Jeeves native coding campaigns.

The composer turns explicit human source-work goals into strict original
GGUF-native request records, with real read-only current project snapshot
digests and full job SHA-256. It never starts a model or writes a project.
Every compiled task still flows through the *existing* canonical campaign,
private journal, SQLite and separate manual operator-approval boundaries.

The returned campaign JSON contains private original goals and paths and
MUST remain inside the owner's local desktop UI or another private channel.
Normal public receipts are SHA/count only.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from .desktop_native_campaign import (
    SCHEMA as CAMPAIGN_SCHEMA, parse_campaign,
    inspect_campaign, _preflight_all,
)
from .desktop_native_code_cli import (
    SCHEMA as NATIVE_SCHEMA, execute_native_request,
)
from .desktop_workspace import _canonical

SCHEMA = "jeeves.desktop.native-source-campaign-composer.v1"
MAX_INPUT_BYTES = 65536
MAX_TASKS = 12
MAX_GOAL_BYTES = 8192
MAX_TOTAL_GOAL_BYTES = 32768
MAX_RESULT_BYTES = 131072
_FIELDS = frozenset((
    "schema", "project_root", "private_dir", "journal_name", "model_root",
    "state_dir", "tenant", "subject", "context_tokens", "max_output_tokens",
    "threads", "gpu_layers", "inference_ms", "capacity_budget_bytes", "tasks",
))
_TASK_FIELDS = frozenset((
    "task_id", "depends_on", "goal", "format", "maximum_attempts",
    "source_paths", "target_name",
))
_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,96}\.source\.json\Z")
_JOURNAL = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,96}\.jeeves-campaign\.jsonl\Z")


class CampaignComposerHold(ValueError):
    """Original source tasks cannot be safely formed into a native campaign."""


def _absolute(value: object) -> Path:
    if (
        type(value) is not str or not 1 <= len(value) <= 4096
        or "\x00" in value or not Path(value).is_absolute()
        or ".." in Path(value).parts
    ):
        raise CampaignComposerHold("explicit owner-selected absolute path required")
    return Path(value)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CampaignComposerHold("duplicate untrusted campaign composer field")
        result[key] = value
    return result


def _nonfinite(_):
    raise CampaignComposerHold("nonfinite campaign resource budget")


def parse_composer_request(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_INPUT_BYTES:
        raise CampaignComposerHold("bounded strict task-composer JSON required")
    try:
        request = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs, parse_constant=_nonfinite,
        )
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise CampaignComposerHold("ambiguous or invalid source-composer JSON") from exc
    if type(request) is not dict or frozenset(request) != _FIELDS:
        raise CampaignComposerHold("composer contains missing or unknown authority")
    if request["schema"] != SCHEMA:
        raise CampaignComposerHold("unsupported native task composer schema")
    for field in ("project_root", "private_dir", "model_root", "state_dir"):
        _absolute(request[field])
    private = Path(request["private_dir"])
    project = Path(request["project_root"])
    model = Path(request["model_root"])
    state = Path(request["state_dir"])
    if any(
        private == owner or private.is_relative_to(owner)
        or owner.is_relative_to(private)
        for owner in (project, model, state)
    ):
        raise CampaignComposerHold("private campaign outputs must not overlap original owners")
    if (
        type(request["journal_name"]) is not str
        or not _JOURNAL.fullmatch(request["journal_name"])
    ):
        raise CampaignComposerHold("canonical private campaign journal name required")
    tasks = request["tasks"]
    if type(tasks) is not list or not 1 <= len(tasks) <= MAX_TASKS:
        raise CampaignComposerHold("finite original native goals required")
    seen_targets = {request["journal_name"].casefold()}
    count = 0
    for task in tasks:
        if type(task) is not dict or frozenset(task) != _TASK_FIELDS:
            raise CampaignComposerHold("unexpected model task planning authority")
        if (
            type(task["goal"]) is not str or not task["goal"].strip()
            or type(task["source_paths"]) is not list
            or type(task["depends_on"]) is not list
            or type(task["target_name"]) is not str
            or not _NAME.fullmatch(task["target_name"])
        ):
            raise CampaignComposerHold("typed original native task goal/source/target required")
        try:
            size = len(task["goal"].encode("utf-8", "strict"))
        except UnicodeError as exc:
            raise CampaignComposerHold("task goal is not valid UTF-8") from exc
        if not 1 <= size <= MAX_GOAL_BYTES:
            raise CampaignComposerHold("individual original task exceeds goal budget")
        count += size
        name = task["target_name"].casefold()
        if name in seen_targets:
            raise CampaignComposerHold("source task destination collides with another task")
        seen_targets.add(name)
    if count > MAX_TOTAL_GOAL_BYTES:
        raise CampaignComposerHold("whole original campaign goal budget exceeded")
    return request


def compose_campaign(raw: bytes) -> tuple[dict, dict]:
    """Build and inspect original job/source hashes without starting GGUF.

    Returns (PRIVATE full campaign JSON dictionary, PUBLIC SHA review).
    The first item is private and must NOT be printed in public logs.
    """
    req = parse_composer_request(raw)
    path = Path(req["private_dir"])
    tasks = []
    for task in req["tasks"]:
        original = {
            "schema": NATIVE_SCHEMA,
            "action": "inspect",
            "project_root": req["project_root"],
            "model_root": req["model_root"],
            "state_dir": req["state_dir"],
            "tenant": req["tenant"],
            "subject": req["subject"],
            "goal": task["goal"],
            "format": task["format"],
            "maximum_attempts": task["maximum_attempts"],
            "source_paths": task["source_paths"],
            "source_context_sha256": None,
            "job_sha256": None,
            "context_tokens": req["context_tokens"],
            "max_output_tokens": req["max_output_tokens"],
            "threads": req["threads"],
            "gpu_layers": req["gpu_layers"],
            "inference_ms": req["inference_ms"],
            "capacity_budget_bytes": req["capacity_budget_bytes"],
        }
        inspected = execute_native_request(original, approve_native=False)
        if (
            inspected.get("status") != "operator-review-required-before-native-model"
            or inspected.get("native_gguf_started") is not False
            or inspected.get("source_files_modified") is not False
            or inspected.get("release_certified") is not False
        ):
            raise CampaignComposerHold("read-only original source/job inspection not trusted")
        # Bind the current original source SHA to the job record itself.
        original["source_context_sha256"] = inspected["source_context_sha256"]
        repeated = execute_native_request(original, approve_native=False)
        if (
            repeated.get("job_sha256") != inspected.get("job_sha256")
            or repeated.get("source_context_sha256") != inspected.get("source_context_sha256")
        ):
            raise CampaignComposerHold("original project source changed while composing")
        original["action"] = "generate"
        original["job_sha256"] = inspected["job_sha256"]
        tasks.append({
            "task_id": task["task_id"],
            "depends_on": task["depends_on"],
            "target": str(path / task["target_name"]),
            "expected_job_sha256": inspected["job_sha256"],
            "native_request": original,
        })
    private = {
        "schema": CAMPAIGN_SCHEMA,
        "action": "inspect",
        "project_root": req["project_root"],
        "journal_file": str(path / req["journal_name"]),
        "manifest_sha256": None,
        "recheck_original_source": False,
        "tasks": tasks,
    }
    if len(_canonical(private)) > MAX_RESULT_BYTES:
        raise CampaignComposerHold("original private task request exceeds finite output budget")
    plan, _ = parse_campaign(_canonical(private))
    result = inspect_campaign(plan)
    # A task planner cannot approve a target already owned by another
    # campaign, even though inspection does not write or run a model.
    _preflight_all(plan)
    if (
        result.get("manifest_sha256") != plan.manifest_sha256
        or result.get("model_started") is not False
        or result.get("private_source_in_stdout") is not False
    ):
        raise CampaignComposerHold("composed task lacks exact safe private campaign review")
    public = {
        "schema": "jeeves.desktop.native-source-campaign-composer-receipt.v1",
        "status": "original-source-campaign-composed-no-model",
        "manifest_sha256": plan.manifest_sha256,
        "task_count": len(tasks),
        "total_maximum_native_attempts": plan.total_attempts,
        "total_maximum_output_tokens": plan.total_output_tokens,
        "total_maximum_inference_ms": plan.total_inference_ms,
        "source_snapshot_count": sum(len(task["source_paths"]) for task in req["tasks"]),
        "private_goals_and_paths_emitted_to_stdout": False,
        "model_started": False,
        "project_files_modified": False,
        "release_certified": False,
    }
    return private, public


__all__ = [
    "SCHEMA", "CampaignComposerHold", "parse_composer_request",
    "compose_campaign",
]
