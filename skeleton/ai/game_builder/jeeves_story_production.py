"""Canonical full-game story source authoring through Jeeves and GameWorkspace.

Works with the existing 100-chapter/1000-act/9999-scene canon, not a
competing dialogue generator. An external authored signed story document
is required for the writing; this bridge supplies precise original source
ownership, historical binding, append-only sequencing, and real proposals.
"""
from __future__ import annotations

from hashlib import sha256
import re

from .contracts import canonical_json
from .game_project_workspace import GameWorkspace
from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest
from .story_canon_fabric import (
    story_bible_template, scene_path,
)
from .story_workspace import (
    load_story_workspace, load_continuity_contract,
    next_story_scene_template, validate_story_workspace_source,
)

SCHEMA = "skeleton.ai.jeeves_story_source_wave.v1"
PHASES = frozenset({"bible", "contract", "scene"})
SHA = re.compile(r"[0-9a-f]{64}\Z")
EMPTY_SHA = sha256(b"").hexdigest()
MAX_STORY = 240_000


class JeevesStorySourceWave:
    """Full-source, human-reviewed authored story canon with immutable history."""

    def __init__(self, inventory: AppwideInventory, workspace: GameWorkspace):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("canonical scanned source inventory required")
        inventory._require_scanned()
        if not isinstance(workspace, GameWorkspace):
            raise JeevesAppwideError("canonical original GameWorkspace required")
        self.inv = inventory
        self.ws = workspace

    def _prepare(self, *, project, phase, chapter=None, act=None,
                 scene=None, expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot != self.inv._digest:
            raise JeevesAppwideError("stale application source inventory")
        if type(project) is not str or project != self.ws.active():
            raise JeevesAppwideError("selected current original project required")
        if type(phase) is not str or phase not in PHASES:
            raise JeevesAppwideError("story source phase must be bible/contract/scene")
        if phase != "scene" and any(x is not None for x in (chapter, act, scene)):
            raise JeevesAppwideError("scene coordinates only apply to authored scenes")
        ws = self.ws
        bible, scenes, history = load_story_workspace(ws, project)
        current_contract = load_continuity_contract(ws, project)
        if phase == "bible":
            path = "game/story_bible.json"
            template = bible if bible is not None else story_bible_template(project)
        elif phase == "contract":
            if bible is None or bible["phase"] != "design":
                raise JeevesAppwideError("approved design phase needed for voice/face continuity")
            if scenes and current_contract is None:
                raise JeevesAppwideError("cannot add immutable voice canon after scene one")
            from .story_continuity_assurance import contract_template
            path = "game/continuity_contract.json"
            template = (current_contract if current_contract is not None
                        else contract_template(bible))
        else:
            if type(act) is not int or type(scene) is not int:
                raise JeevesAppwideError("original authored scene coordinates required")
            if chapter is not None and (
                    type(chapter) is not int or not 1 <= chapter <= 100):
                raise JeevesAppwideError("story chapter must be in 1..100")
            if not 1 <= act <= 1000 or not 1 <= scene <= 9999:
                raise JeevesAppwideError("bounded 1000-act/9999-scene context required")
            source = next_story_scene_template(
                ws, project, act, scene, chapter=chapter)
            path, template = source["path"], source["document"]
        stored = {entry.path: entry for entry in ws.files("current", project)}
        current = stored.get(path)
        expected_sha = current.sha256 if current is not None else EMPTY_SHA
        snapshot = canonical_json(template)
        if len(snapshot.encode("utf-8")) > MAX_STORY:
            raise JeevesAppwideError("source template exceeds bounded context")
        body = {
            "schema": SCHEMA + ".plan",
            "project": project,
            "source_phase": phase,
            "path": path,
            "expected_source_sha256": expected_sha,
            "current_source_exists": current is not None,
            "source_template": template,
            "template_sha256": sha256(snapshot.encode("utf-8")).hexdigest(),
            "app_inventory_snapshot": self.inv._digest,
            "workspace_revision": ws.tree()["revision"],
            "historical_story_scenes": len(scenes),
            "historical_index_digest": (
                history["digest"] if history is not None else None),
            "approved_bible_digest": bible["digest"] if bible is not None else None,
            "approved_continuity_digest": (
                current_contract["digest"] if current_contract is not None else None),
            "next_authoring_position": ({
                "chapter": chapter, "act": act, "scene": scene
            } if phase == "scene" else None),
            "story_target_chapters": 100,
            "story_target_acts": 1000,
            "story_target_scenes": 9999,
            "template_is_not_a_completed_original_story": True,
            "requires_independently_authored_and_signed_document": True,
            "human_source_review_required": True,
            "source_file_committed": False,
        }
        return {**body, "digest": digest(body)}

    def plan(self, *, project, phase, chapter=None, act=None,
             scene=None, expected_snapshot=None):
        return self._prepare(
            project=project, phase=phase, chapter=chapter,
            act=act, scene=scene, expected_snapshot=expected_snapshot)

    def stage(self, *, project, phase, authored_document,
              expected_plan_digest, reason, chapter=None,
              act=None, scene=None, expected_snapshot=None,
              operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("source authoring requires explicit designer approval")
        if type(expected_plan_digest) is not str or not SHA.fullmatch(expected_plan_digest):
            raise JeevesAppwideError("exact reviewed story plan digest required")
        if (type(reason) is not str or not 12 <= len(reason) <= 1000):
            raise JeevesAppwideError("specific story authoring review reason required")
        if type(authored_document) is not dict:
            raise JeevesAppwideError("fully typed signed original story document required")
        plan = self._prepare(
            project=project, phase=phase, chapter=chapter,
            act=act, scene=scene, expected_snapshot=expected_snapshot)
        if plan["digest"] != expected_plan_digest:
            raise JeevesAppwideError("story history, source or selected authoring context changed")
        path = plan["path"]
        if phase == "scene":
            if scene_path(authored_document) != path:
                raise JeevesAppwideError("authored scene belongs to different chapter/act")
            if authored_document.get("bible_digest") != plan["approved_bible_digest"]:
                raise JeevesAppwideError("original scene not bound to approved story bible")
            if authored_document.get("sequence") != plan["historical_story_scenes"]+1:
                raise JeevesAppwideError("original story scene cannot skip historical sequence")
        elif phase == "bible":
            if authored_document.get("project") != project:
                raise JeevesAppwideError("authored canon belongs to different game")
        elif authored_document.get("project") != project:
            raise JeevesAppwideError("continuity contract belongs to another project")
        from .story_canon_fabric import BIBLE, SCENE
        from .story_continuity_assurance import CONTRACT
        expected_schema = {"bible": BIBLE, "scene": SCENE, "contract": CONTRACT}[phase]
        if (authored_document.get("schema") != expected_schema
                or type(authored_document.get("digest")) is not str
                or not SHA.fullmatch(authored_document["digest"])):
            raise JeevesAppwideError("original story source must carry canonical signature")
        # This is the actual canonical full-history quality and continuity
        # validation already used at proposal and commit boundaries.
        preflight = validate_story_workspace_source(
            self.ws, project, path, authored_document)
        content = canonical_json(authored_document) + "\n"
        if len(content.encode("utf-8")) > MAX_STORY:
            raise JeevesAppwideError("full signed story source exceeds proposal budget")
        proposed = self.ws.propose(
            project, path, content,
            expected_sha256=plan["expected_source_sha256"],
            reason=reason, authorized=True)
        body = {
            "schema": SCHEMA + ".stage",
            "project": project, "phase": phase,
            "source_path": path,
            "exact_source_plan_digest": plan["digest"],
            "candidate_document_digest": authored_document["digest"],
            "prior_source_sha256": plan["expected_source_sha256"],
            "proposed_source_sha256": proposed["after"],
            "proposal_id": proposed["proposal_id"],
            "canonical_story_validator_receipt": preflight,
            "historical_story_scenes_before_proposal": plan["historical_story_scenes"],
            "canonical_full_history_checked": True,
            "source_published": False,
            "human_commit_required": True,
            "model_story_writing_not_fabricated": True,
        }
        return {**body, "digest": digest(body)}
