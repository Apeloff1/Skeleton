"""Jeeves multi-engine game production: actual source staging in the canonical Studio.

This is not another game engine or a second persistence owner. Jeeves creates
real validated original system and authored scene sources, reads the exact
active workspace versions, and stages reviewed multi-file proposals through
GameWorkspace.propose. Human commit remains the sole publication boundary.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import re
from typing import Any

from .jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, digest, canonical,
)
from .game_project_workspace import GameWorkspace
from .system_editors import (
    make_editor_document, validate_editor_document, editor_source, editor_path,
    editor_spec, ADVANCED_ENGINE_IDS,
)

SCHEMA = "skeleton.ai.jeeves_production_wave.v1"
MAX_ITEMS = 24
MAX_BYTES = 155_000
MAX_SCENES = 12
MAX_EDITOR_ID = 64
MAX_PROJECT_ID = 64
EMPTY_SHA = sha256(b"").hexdigest()
SCENE_ID = re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
NAME = re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")


def _exact_dict(value: Any, keys: set[str], *, name: str):
    if type(value) is not dict or set(value) != keys:
        raise JeevesAppwideError(name + " has unrecognized or missing fields")
    return value


def _raw_text(value: Any, name: str, ceiling=MAX_BYTES) -> str:
    if type(value) is not str or len(value.encode("utf-8")) > ceiling:
        raise JeevesAppwideError(name + " must be bounded UTF-8")
    if "\x00" in value:
        raise JeevesAppwideError(name + " contains NUL")
    return value


def _check_plan_items(phase: str, items: Any):
    if type(phase) is not str or phase not in ("systems", "scenes"):
        raise JeevesAppwideError("production phase must be systems or scenes")
    if type(items) is not list or not 1 <= len(items) <= MAX_ITEMS:
        raise JeevesAppwideError("production wave requires 1–24 actual editor items")
    normalized = []
    unique = set()
    for item in items:
        if type(item) is not dict:
            raise JeevesAppwideError("typed production item required")
        allowed = {"editor", "settings"} if phase == "systems" else {
            "editor", "scene_id", "seed", "layout"
        }
        if set(item) - allowed:
            raise JeevesAppwideError("unreviewed production item key")
        editor = item.get("editor")
        if type(editor) is not str or not 1 <= len(editor) <= MAX_EDITOR_ID:
            raise JeevesAppwideError("safe editor ID required")
        editor_spec(editor)
        if phase == "systems":
            settings = item.get("settings", {})
            if type(settings) is not dict:
                raise JeevesAppwideError("typed editor configuration expected")
            identity = editor
            normalized.append({"editor": editor, "settings": settings})
        else:
            if editor not in ADVANCED_ENGINE_IDS:
                raise JeevesAppwideError("authored scenes require an advanced engine")
            scene_id = item.get("scene_id", "scene_01")
            if type(scene_id) is not str or not SCENE_ID.fullmatch(scene_id):
                raise JeevesAppwideError("safe original scene name required")
            seed = item.get("seed", 0)
            if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
                raise JeevesAppwideError("bounded scene seed required")
            layout = item.get("layout")
            if layout is not None and type(layout) is not dict:
                raise JeevesAppwideError("typed scene layout required")
            identity = editor + ":" + scene_id
            normalized.append({
                "editor": editor, "scene_id": scene_id, "seed": seed,
                "layout": layout,
            })
        if identity in unique:
            raise JeevesAppwideError("duplicate original production identity")
        unique.add(identity)
    if len(canonical(normalized).encode("utf-8")) > MAX_BYTES:
        raise JeevesAppwideError("production source input exceeds budget")
    return normalized


class JeevesProductionWave:
    """System and scene source creation using *existing* GameWorkspace controls."""

    def __init__(self, inventory: AppwideInventory, workspace: GameWorkspace):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("canonical repo inventory required")
        inventory._require_scanned()
        if not isinstance(workspace, GameWorkspace):
            raise JeevesAppwideError("active original Game Studio workspace required")
        self.inventory = inventory
        self.workspace = workspace

    def _prepare(self, *, project, phase, items, expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot != self.inventory._digest:
            raise JeevesAppwideError("stale Jeeves repository inventory")
        if type(project) is not str or not NAME.fullmatch(project):
            raise JeevesAppwideError("safe selected project identity required")
        if self.workspace.active() != project:
            raise JeevesAppwideError("production requires selected active project")
        items = _check_plan_items(phase, items)
        ws = self.workspace
        stored = {f.path: f for f in ws.files("current", project)}
        results, staged_sources = [], []
        total_bytes = 0
        for item in items:
            editor = item["editor"]
            if phase == "systems":
                document = make_editor_document(editor, item["settings"])
                document = validate_editor_document(document)
                path = editor_path(editor)
                source = editor_source(editor, document["settings"])
            else:
                from .advanced_level_scenes import (
                    make_advanced_scene, validate_advanced_scene, scene_path,
                )
                system_path = editor_path(editor)
                if system_path not in stored:
                    raise JeevesAppwideError(
                        "approve original system before generating its scene: " + editor
                    )
                approved = ws.read("current", project, system_path)
                config = json.loads(approved["content"])
                validated = validate_editor_document(config)
                if validated["editor"] != editor:
                    raise JeevesAppwideError("source editor owner drift")
                document = make_advanced_scene(
                    editor, validated["settings"], seed=item["seed"],
                    layout=item["layout"], scene_id=item["scene_id"],
                )
                document = validate_advanced_scene(
                    document, validated["settings"])
                path = scene_path(document)
                # Existing validation enforces editor ownership and checks
                # the *actually approved* system rather than this request.
                ws._validate_advanced_scene_source(project, path, document)
                source = canonical(document) + "\n"
            encoded = source.encode("utf-8")
            total_bytes += len(encoded)
            if total_bytes > MAX_BYTES:
                raise JeevesAppwideError("combined original production source over budget")
            existing = ws.read("current", project, path) if path in stored else None
            expected = (existing["version"]["sha256"]
                        if existing is not None else EMPTY_SHA)
            proposal_digest = sha256(encoded).hexdigest()
            unchanged = (existing is not None and
                         existing["version"]["sha256"] == proposal_digest)
            record = {
                "path": path,
                "editor": editor,
                "kind": phase[:-1],
                "source_bytes": len(encoded),
                "previous_sha256": expected,
                "candidate_sha256": proposal_digest,
                "canonical_document_digest": document["digest"],
                "prior_file_exists": existing is not None,
                "already_current": unchanged,
                "publication_requires_human_review": True,
            }
            if phase == "scenes":
                record["scene_id"] = item["scene_id"]
                record["approved_system_sha256"] = approved["version"]["sha256"]
            results.append(record)
            staged_sources.append((record, source))
        evidence = {
            "schema": SCHEMA + ".plan",
            "project": project,
            "phase": phase,
            "repo_inventory_snapshot": self.inventory._digest,
            "workspace_revision": ws.tree()["revision"],
            "requested_items": len(items),
            "candidate_source_bytes": total_bytes,
            "changed_items": sum(not x["already_current"] for x in results),
            "already_current_items": sum(x["already_current"] for x in results),
            "families": dict(sorted(Counter(x["editor"] for x in results).items())),
            "items": results,
            "all_sources_generated_by_existing_canonical_game_editors": True,
            "system_scenes_bound_to_actual_approved_workspace_settings": True,
            "source_changes_not_yet_staged": True,
            "source_files_committed": False,
            "requires_explicit_human_commit_after_staging": True,
        }
        return {**evidence, "digest": digest(evidence)}, staged_sources

    def plan(self, *, project, phase, items, expected_snapshot=None):
        """Construct *real* source and version receipts without writing anything."""
        receipt, _ = self._prepare(
            project=project, phase=phase, items=items,
            expected_snapshot=expected_snapshot)
        return receipt

    def stage(self, *, project, phase, items, expected_plan_digest,
              reason, expected_snapshot=None, operator_authorized=False):
        """Stage actual source proposals, never accept/commit them implicitly.

        All proposed files and exact previous identities are checked first.
        A failed source stage cannot publish an incomplete production world.
        """
        if operator_authorized is not True:
            raise PermissionError("designer authorization required to stage proposals")
        if type(expected_plan_digest) is not str or len(expected_plan_digest) != 64:
            raise JeevesAppwideError("exact production plan digest required")
        reason = _raw_text(reason, "production review reason", 1000)
        if not 12 <= len(reason):
            raise JeevesAppwideError("nonempty specific designer justification required")
        plan, sources = self._prepare(
            project=project, phase=phase, items=items,
            expected_snapshot=expected_snapshot)
        if plan["digest"] != expected_plan_digest:
            raise JeevesAppwideError("production sources changed after reviewed plan")
        if plan["changed_items"] == 0:
            raise JeevesAppwideError("all requested original game sources are current")
        # Preflight also preserves all original checksums as a stable CAS
        # receipt. Workspace.propose is the canonical sole write authority.
        created = []
        for record, source in sources:
            if record["already_current"]:
                continue
            proposal = self.workspace.propose(
                project, record["path"], source,
                expected_sha256=record["previous_sha256"],
                reason=reason, authorized=True,
            )
            created.append({
                "path": record["path"],
                "proposal_id": proposal["proposal_id"],
                "previous_sha256": record["previous_sha256"],
                "proposed_sha256": record["candidate_sha256"],
                "review_approval_required": True,
                "source_file_committed": False,
            })
        body = {
            "schema": SCHEMA + ".stage",
            "plan_digest": plan["digest"],
            "repo_inventory_snapshot": self.inventory._digest,
            "workspace_project": project,
            "phase": phase,
            "proposals": created,
            "proposal_count": len(created),
            "preflighted_source_count": len(sources),
            "source_files_committed": 0,
            "pending_review": len(created),
            "human_commit_required_for_every_proposal": True,
            "no_game_source_automatically_published": True,
            "no_provider_model_used": True,
        }
        return {**body, "digest": digest(body)}
