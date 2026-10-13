"""Actual multi-genre authored-scene reference gameplay and approved replay sources.

Uses current human-committed scenes and systems, canonical 29-engine reference
gameplay interpreter and existing GameWorkspace proposal/commit custody.
It does NOT replace the underlying engines, modify an AI model, or run a
native Godot binary. Every persistent replay is source-version bound and
re-verified at the original workspace source proposal AND commit boundaries.
"""
from __future__ import annotations

from hashlib import sha256
import re
from typing import Any

from .contracts import canonical_json, canonical_digest
from .game_project_workspace import GameWorkspace, _json
from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest
from .advanced_gameplay_runtime import (
    ENGINES, ACTION_HELP, run_advanced_session, verify_advanced_session,
)
from .system_editors import validate_editor_document
from .advanced_level_scenes import validate_advanced_scene

SCHEMA="skeleton.ai.jeeves_advanced_replay.v1"
DOCUMENT="skeleton.game_builder.approved_advanced_replay_source.v1"
IDENT=re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
SHA=re.compile(r"[0-9a-f]{64}\Z")
EMPTY_SHA=sha256(b"").hexdigest()
MAX_SOURCE_BYTES=220_000
MAX_ACTIONS=128


class JeevesAdvancedReplay:
    """A real approved game scene -> executed command transcript -> reviewed file."""

    def __init__(self, inventory: AppwideInventory, workspace: GameWorkspace):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("canonical scanned app source inventory required")
        inventory._require_scanned()
        if not isinstance(workspace, GameWorkspace):
            raise JeevesAppwideError("original human-reviewed GameWorkspace required")
        self.inv=inventory
        self.ws=workspace

    def _loaded(self, *, project, editor, scene_id, expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot!=self.inv._digest:
            raise JeevesAppwideError("stale exact app inventory")
        if (type(project) is not str or self.ws.active()!=project
                or type(editor) is not str or editor not in ENGINES
                or type(scene_id) is not str or not IDENT.fullmatch(scene_id)):
            raise JeevesAppwideError("active original project and installed editor/scene required")
        system=self.ws.read("current",project,"systems/"+editor+".json")
        authored=self.ws.read(
            "current",project,"scenes/advanced_"+editor+"_"+scene_id+".json")
        config=validate_editor_document(_json(system["content"]))
        scene=validate_advanced_scene(
            _json(authored["content"]),config["settings"])
        if config["editor"]!=editor or scene["scene_id"]!=scene_id:
            raise JeevesAppwideError("approved scene editor/identity does not match source")
        path="game/replays/"+editor+"_"+scene_id+".json"
        return config,scene,system["version"]["sha256"],authored["version"]["sha256"],path

    def _prepare(self, *, project, editor, scene_id, actions,
                 expected_snapshot=None):
        config,scene,system_sha,scene_sha,path=self._loaded(
            project=project,editor=editor,scene_id=scene_id,
            expected_snapshot=expected_snapshot)
        if (type(actions) is not list or len(actions)>MAX_ACTIONS
                or any(type(action) is not str or
                       action not in ACTION_HELP[editor] for action in actions)):
            raise JeevesAppwideError("0–128 installed engine command tokens required")
        receipt=run_advanced_session(
            editor,config["settings"],actions,seed=scene["seed"],scene=scene)
        verify_advanced_session(receipt,config["settings"])
        document={
            "schema":DOCUMENT,"project":project,"editor":editor,
            "scene_id":scene_id,"system_sha256":system_sha,
            "scene_sha256":scene_sha,"session":receipt,
        }
        document={**document,"digest":canonical_digest(document)}
        content=canonical_json(document)+"\n"
        if len(content.encode("utf-8"))>MAX_SOURCE_BYTES:
            raise JeevesAppwideError("reviewed advanced gameplay receipt exceeds source size")
        current={f.path:f for f in self.ws.files("current",project)}
        previous=current[path].sha256 if path in current else EMPTY_SHA
        candidate=sha256(content.encode("utf-8")).hexdigest()
        body={
            "schema":SCHEMA+".plan","project":project,"editor":editor,
            "scene_id":scene_id,"source_path":path,
            "inventory_snapshot":self.inv._digest,
            "workspace_revision":self.ws.tree()["revision"],
            "approved_system_sha256":system_sha,
            "approved_scene_sha256":scene_sha,
            "previous_replay_sha256":previous,
            "proposed_replay_sha256":candidate,
            "session_digest":receipt["digest"],
            "session_trace_head_digest":receipt["head_digest"],
            "turn_count":receipt["validated_turn_count"],
            "terminal":receipt["terminal"],
            "final_game_state":receipt["state"],
            "allowed_action_tokens":list(ACTION_HELP[editor]),
            "already_published_identically":previous==candidate,
            "actual_installed_advanced_game_reference_executed":True,
            "exact_original_scene_and_system_used":True,
            "winning_session_or_hardware_execution_not_assumed":True,
            "source_writes_executed":False,
            "independent_human_commit_required":True,
        }
        return {**body,"digest":digest(body)},content

    def plan(self, *, project, editor, scene_id, actions,
             expected_snapshot=None,operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("designer approval required to execute original gameplay")
        report,_=self._prepare(
            project=project,editor=editor,scene_id=scene_id,
            actions=actions,expected_snapshot=expected_snapshot)
        return report

    def stage(self, *, project, editor, scene_id, actions,
              expected_plan_digest,reason,expected_snapshot=None,
              operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("designer approval required for game trace staging")
        if (type(expected_plan_digest) is not str or
                not SHA.fullmatch(expected_plan_digest)):
            raise JeevesAppwideError("exact original replay plan digest required")
        if (type(reason) is not str or not 12<=len(reason)<=1000):
            raise JeevesAppwideError("specific original session review reason required")
        report,source=self._prepare(
            project=project,editor=editor,scene_id=scene_id,
            actions=actions,expected_snapshot=expected_snapshot)
        if report["digest"]!=expected_plan_digest:
            raise JeevesAppwideError("original game or action trace changed after review")
        if report["already_published_identically"]:
            raise JeevesAppwideError("the exact source trace is already committed")
        # The canonical writer independently validates the replay, not only
        # its content hash, before it is staged and again before commit.
        proposal=self.ws.propose(
            project,report["source_path"],source,
            expected_sha256=report["previous_replay_sha256"],
            reason=reason,authorized=True)
        body={
            "schema":SCHEMA+".staged","project":project,
            "editor":editor,"scene_id":scene_id,
            "proposal_id":proposal["proposal_id"],
            "source_path":report["source_path"],
            "source_before_sha256":report["previous_replay_sha256"],
            "source_after_sha256":report["proposed_replay_sha256"],
            "approved_scene_sha256":report["approved_scene_sha256"],
            "session_digest":report["session_digest"],
            "actual_gameplay_executed":True,
            "new_source_files_committed":0,
            "independent_source_diff_review_and_commit_required":True,
        }
        return {**body,"digest":digest(body)}

    def verify(self, *, project, editor, scene_id, expected_snapshot=None):
        config,scene,system_sha,scene_sha,path=self._loaded(
            project=project,editor=editor,scene_id=scene_id,
            expected_snapshot=expected_snapshot)
        stored=self.ws.read("current",project,path)
        document=_json(stored["content"])
        assurance=self.ws._validate_advanced_replay_source(
            project,path,document)
        verify_advanced_session(document["session"],config["settings"])
        body={
            "schema":SCHEMA+".verified","project":project,
            "editor":editor,"scene_id":scene_id,
            "replay_source_path":path,
            "source_sha256":stored["version"]["sha256"],
            "system_sha256":system_sha,"scene_sha256":scene_sha,
            "session_digest":document["session"]["digest"],
            "trace_head_digest":document["session"]["head_digest"],
            "turns_reexecuted":document["session"]["validated_turn_count"],
            "canonical_workspace_source_validation":assurance,
            "actual_reference_gameplay_reexecuted":True,
            "native_playback_executed":False,
            "independent_release_qualification_asserted":False,
            "no_project_sources_mutated":True,
        }
        return {**body,"digest":digest(body)}
