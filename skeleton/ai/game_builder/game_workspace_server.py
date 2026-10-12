"""A strictly loopback-only visual original game file-tree studio.

A local HTTP adapter makes previous/current/demo file lists, targeted edits,
immutable versions and project autoload usable in a real browser. All mutation
APIs enforce same-origin, a high-entropy session token, explicit approval,
source revision checks and restrictive path handling. No shell or model tool
is exposed over HTTP, and no external listener is permitted.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import json
import secrets
from base64 import b64encode

from .game_project_workspace import GameWorkspace, WorkspaceError
from .game_workspace_ui import render_workspace_html
from .game_prompt_router import route_game_prompt,ingest_ai_draft
from .system_editors import catalog as system_editor_catalog, editor_source, editor_path, preview_editor, make_editor_document
from .system_editor_assembly import assemble_workspace_systems
from .advanced_gameplay_runtime import (
    run_advanced_session, verify_advanced_session, ACTION_HELP,
)
from .advanced_level_scenes import make_advanced_scene, scene_path, validate_advanced_scene
from .advanced_puzzle_solver import solve_advanced_puzzle
from .advanced_fighting_rollback import (run_peer_fight,verify_peer_fight,
    reconcile_peer_prediction,verify_peer_reconciliation)
from .advanced_rhythm_longrun import (run_long_rhythm,verify_long_rhythm,continue_long_rhythm)
from .advanced_rhythm_runtime import default_layout as rhythm_default_layout
from .advanced_rhythm_audio import render_original_beat_wav,original_audio_receipt
from .advanced_roguelike_longrun import (replay_long_roguelike,
    continue_long_roguelike,verify_long_roguelike)
from .advanced_world_planner import plan_original_world
from .advanced_stealth_planner import plan_stealth_route
from .advanced_parkour_planner import plan_parkour_route, verify_parkour_plan
from .advanced_sports_coach import plan_original_sports_match, verify_original_sports_plan
from .advanced_maze_planner import plan_original_maze, verify_original_maze_plan
from .advanced_rpg_planner import plan_original_rpg_chapter, verify_original_rpg_plan
from .advanced_npc_society_planner import (
    plan_original_civic_milestone, verify_original_civic_plan,
)
from .advanced_ecosystem_planner import (
    plan_original_ecology, verify_original_ecology_plan,
)
from .advanced_procedural_world_planner import (
    plan_original_frontier,verify_original_frontier_plan,
)
from .advanced_godot_export import (
    render_advanced_godot_package, archive_advanced_godot_package,
)
from .advanced_platformer_godot import render_platformer_godot_package
from .advanced_deck_godot import render_deck_godot_package
from .advanced_shooter_godot import render_shooter_godot_package
from .advanced_tactics_godot import render_tactics_godot_package
from .advanced_defense_godot import render_defense_godot_package
from .advanced_racing_godot import render_racing_godot_package
from .advanced_survival_godot import render_survival_godot_package
from .advanced_farming_godot import render_farming_godot_package
from .advanced_factory_godot import render_factory_godot_package
from .advanced_colony_godot import render_colony_godot_package
from .advanced_gameplay_save import (
    export_advanced_savegame, import_advanced_savegame, continue_advanced_savegame,
)


class StudioServerError(ValueError):
    """Studio was asked to bind outside the local operator's loopback."""


class _LocalStudioServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=False

    def __init__(self,address,workspace,secret):
        super().__init__(address,_StudioHandler)
        self.workspace=workspace
        self.secret=secret


class _StudioHandler(BaseHTTPRequestHandler):
    server: _LocalStudioServer
    protocol_version="HTTP/1.1"

    def log_message(self,format,*args):
        # Local file contents and random session tokens must never be logged.
        return

    def _send(self,status: int,data: bytes,mime: str="application/json; charset=utf-8"):
        self.send_response(status)
        # A rejected POST must never leave attacker-controlled body bytes on
        # a persistent HTTP connection to be parsed as a subsequent request.
        self.send_header("Connection","close")
        self.close_connection=True
        self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("X-Frame-Options","DENY")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Cross-Origin-Resource-Policy","same-origin")
        self.send_header("Access-Control-Allow-Origin","null") if False else None
        self.end_headers()
        self.wfile.write(data)

    def _json(self,status: int,value):
        data=(json.dumps(value,ensure_ascii=False,sort_keys=True,
                         separators=(",",":"))+"\n").encode("utf-8")
        self._send(status,data)

    def _allowed(self,mutation=False):
        host=self.headers.get("Host","")
        expected=f"127.0.0.1:{self.server.server_port}"
        if host!=expected:
            raise PermissionError("only the exact local server origin is allowed")
        if self.headers.get("X-Game-Studio-Token","")!=self.server.secret:
            raise PermissionError("valid local studio session capability required")
        if mutation:
            origin=self.headers.get("Origin",f"http://{expected}")
            if origin!=f"http://{expected}":
                raise PermissionError("cross-origin editing is blocked")
            if self.headers.get("Content-Type","").split(";")[0]!="application/json":
                raise WorkspaceError("JSON mutation contract required")

    def _params(self):
        result=parse_qs(urlsplit(self.path).query,keep_blank_values=True)
        return {k:v[-1] for k,v in result.items()}

    def _body(self):
        size=self.headers.get("Content-Length")
        if size is None or not size.isascii() or not size.isdecimal():
            raise WorkspaceError("bounded known-size request required")
        count=int(size)
        if not 0<count<=320000:
            raise WorkspaceError("mutation request exceeds bounded input size")
        try:
            body=json.loads(self.rfile.read(count).decode("utf-8","strict"))
        except (UnicodeError,ValueError) as exc:
            raise WorkspaceError("malformed local editor JSON") from exc
        if type(body) is not dict:
            raise WorkspaceError("typed JSON object required")
        return body

    def _handle(self,action):
        try:
            action()
        except PermissionError as exc:
            self._json(403,{"error":str(exc)})
        except (WorkspaceError,ValueError,TypeError,KeyError,OSError) as exc:
            self._json(400,{"error":str(exc)})
        except Exception:
            # Fail closed: no traceback, filesystem path, or secret leaks.
            self._json(500,{"error":"local studio operation failed"})

    def do_GET(self):
        self._handle(self._get)

    def _get(self):
        path=urlsplit(self.path).path
        if path=="/":
            expected=f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host","")!=expected:
                raise PermissionError("workspace UI is bound to one loopback origin")
            return self._send(200,render_workspace_html(self.server.secret),
                              "text/html; charset=utf-8")
        self._allowed()
        params=self._params()
        if path=="/api/model-status":
            # Read-only surface: never exposes private candidate weights or
            # grants authority to promote from a browser status request.
            from .game_reviewer_registry import ReviewerRegistry
            work=self.server.workspace.root
            previous=work/"training"/"review_models"/"state.json"
            if not previous.is_file():
                return self._json(200,{
                    "schema":"skeleton.game_builder.review_ladder_ui.v1",
                    "phase":"unconfigured","revision":0,
                    "active":False,"candidate":False,
                    "usage_checked":False,"idle_checked":False,
                    "signed_roles":[],"model_training_or_deployment_running":False,
                })
            state=ReviewerRegistry(work).read_state()
            return self._json(200,{
                "schema":"skeleton.game_builder.review_ladder_ui.v1",
                "phase":state["phase"],"revision":state["revision"],
                "active":bool(state["active"]),
                "candidate":bool(state["candidate"]),
                "usage_checked":"usage" in state["observations"],
                "idle_checked":"idle" in state["observations"],
                "signed_roles":[row["role"] for row in state["attestations"]],
                "source_project_count":len(state["source_projects"]),
                "last_incident":state["last_incident"]["reason"] if state["last_incident"] else None,
                "model_training_or_deployment_running":False,
                "core_llm_weights_changed":False,
            })
        if path=="/api/story-memory-page":
            from .story_memory import character_memory_page
            return self._json(200,character_memory_page(
                self.server.workspace,params["project"],params["character"],
                partner=params.get("partner") or None,
                offset=int(params.get("offset",0)),
                limit=int(params.get("limit",40))))
        if path=="/api/story-status":
            from .story_workspace import story_workspace_status
            return self._json(200,story_workspace_status(
                self.server.workspace,params["project"]))
        if path=="/api/editors":
            return self._json(200,{"schema":"skeleton.game_builder.system_editor_catalog.v1",
                                   "editors":system_editor_catalog()})
        if path=="/api/editor-assembly":
            result = assemble_workspace_systems(
                self.server.workspace, params["project"], authorized=True)
            return self._json(200, result)
        if path=="/api/tree":
            return self._json(200,self.server.workspace.tree())
        if path=="/api/files":
            rows=self.server.workspace.files(params["tree"],params["project"])
            return self._json(200,{"files":[f.payload() for f in rows]})
        if path=="/api/file":
            return self._json(200,self.server.workspace.read(
                params["tree"],params["project"],params["path"]))
        return self._json(404,{"error":"unknown local studio endpoint"})

    def do_POST(self):
        self._handle(self._post)

    def _post(self):
        self._allowed(mutation=True)
        path=urlsplit(self.path).path
        values=self._body()
        studio=self.server.workspace
        if path=="/api/jeeves-work-order":
            from .jeeves_production_director import work_order
            return self._json(200,work_order(
                studio,values["project"],values["prompt"],
                cast=values.get("cast"),region=values.get("region"),
                act=values.get("act"),scene=values.get("scene")))
        if path=="/api/jeeves-asset-orders":
            from .jeeves_production_director import planned_asset_orders
            return self._json(200,planned_asset_orders(
                studio,values["project"],values["prompt"],
                region=values.get("region"),kinds=values.get("kinds"),
                max_jobs=values.get("max_jobs",128)))
        if path=="/api/story-memory":
            from .story_memory import retrieve_bookmarks
            return self._json(200,retrieve_bookmarks(
                studio,values["project"],values["references"]))
        if path=="/api/story-pixel-proof":
            from .story_asset_pixels import inspect_png_against_canon
            from .story_workspace import load_story_workspace
            from base64 import b64decode
            import binascii
            bible,_,_=load_story_workspace(studio,values["project"])
            if bible is None:
                raise WorkspaceError("approved original world design required")
            data=values["png_base64"]
            if type(data) is not str or len(data)>280000:
                raise WorkspaceError("bounded original image preview only")
            try:
                raw=b64decode(data,validate=True)
            except (ValueError,binascii.Error) as exc:
                raise WorkspaceError("malformed original asset PNG transport") from exc
            proof=inspect_png_against_canon(
                bible,values["asset"],raw,
                max_channel_delta=values.get("max_channel_delta",0))
            return self._json(200,{"pixel_proof":proof,
                                   "preview_size_limited":True,
                                   "game_source_mutated":False,
                                   "model_art_generated":False})
        if path=="/api/story-asset-history":
            from .story_memory import asset_identity_history
            return self._json(200,asset_identity_history(
                studio,values["project"],values["asset"]))
        if path=="/api/story-continuity-template":
            from .story_continuity_assurance import contract_template
            from .story_workspace import load_story_workspace
            bible,scenes,_=load_story_workspace(studio,values["project"])
            if bible is None or scenes:
                raise WorkspaceError("voice/face contract requires approved design before scene one")
            return self._json(200,{
                "path":"game/continuity_contract.json",
                "document":contract_template(bible),
                "model_inference_performed":False,"write_authorized":False})
        if path=="/api/story-stage-confirmation":
            from .story_continuity_assurance import confirm_stage
            return self._json(200,confirm_stage(studio,values["project"]))
        if path=="/api/story-detail-timeline":
            from .story_detail_history import detail_timeline
            return self._json(200,detail_timeline(
                studio,values["project"],character=values.get("character"),
                item=values.get("item"),region=values.get("region"),
                offset=values.get("offset",0),limit=values.get("limit",48)))
        if path=="/api/story-foundation-template":
            from .story_canon_fabric import story_bible_template
            return self._json(200,{"path":"game/story_bible.json",
                                   "document":story_bible_template(values["project"]),
                                   "model_inference_performed":False,
                                   "write_authorized":False})
        if path=="/api/story-scene-template":
            from .story_workspace import next_story_scene_template
            return self._json(200,next_story_scene_template(
                studio,values["project"],values["act"],values["scene"],
                chapter=values.get("chapter")))
        if path=="/api/story-brief":
            from .story_workspace import story_workspace_brief
            return self._json(200,story_workspace_brief(
                studio,values["project"],cast=values["cast"],
                region=values["region"],prompt=values["prompt"],
                max_bookmarks=values.get("max_bookmarks",48)))
        if path=="/api/story-sign":
            from .story_canon_fabric import BIBLE,SCENE,sign
            from .story_workspace import (
                validate_story_workspace_source,load_story_workspace,
                load_continuity_contract)
            from .story_continuity_assurance import CONTRACT,seal_production_scene
            source_path=values["path"]
            schema=(BIBLE if source_path=="game/story_bible.json"
                    else CONTRACT if source_path=="game/continuity_contract.json"
                    else SCENE if source_path.startswith(("story/scenes/","story/chapters/"))
                    else None)
            if schema is None:
                raise WorkspaceError("Jeeves signing only permits exact approved story sources")
            if schema==SCENE and load_continuity_contract(
                    studio,values["project"]) is not None:
                bible,history,_=load_story_workspace(studio,values["project"])
                contract=load_continuity_contract(studio,values["project"])
                document=seal_production_scene(
                    bible,contract,history,values["document"],
                    values["observations"])
            else:
                document=sign(values["document"],schema)
            evidence=validate_story_workspace_source(
                studio,values["project"],source_path,document)
            return self._json(200,{"path":source_path,"document":document,
                                   "evidence":evidence,"write_authorized":False,
                                   "human_commit_required":True})
        if path=="/api/story-verify":
            from .story_workspace import validate_story_workspace_source
            evidence=validate_story_workspace_source(studio,values["project"],
                        values["path"],values["document"])
            return self._json(200,{"evidence":evidence,
                                   "source_project_mutated":False,
                                   "source_commit_requires_human_review":True})
        if path=="/api/advanced-godot-package":
            from base64 import b64encode
            session=values["session"]
            renderer=(render_platformer_godot_package
                      if type(session) is dict and session.get("editor")=="platformer"
                      else render_deck_godot_package
                      if type(session) is dict and session.get("editor")=="deck_battler"
                      else render_shooter_godot_package
                      if type(session) is dict and session.get("editor")=="shooter"
                      else render_tactics_godot_package
                      if type(session) is dict and session.get("editor")=="tactics"
                      else render_defense_godot_package
                      if type(session) is dict and session.get("editor")=="tower_defense"
                      else render_racing_godot_package
                      if type(session) is dict and session.get("editor")=="racing"
                      else render_survival_godot_package
                      if type(session) is dict and session.get("editor")=="survival"
                      else render_farming_godot_package
                      if type(session) is dict and session.get("editor")=="farming"
                      else render_factory_godot_package
                      if type(session) is dict and session.get("editor")=="factory"
                      else render_colony_godot_package
                      if type(session) is dict and session.get("editor")=="colony"
                      else render_advanced_godot_package)
            package=renderer(session,values.get("settings"),authorized=True)
            compressed=archive_advanced_godot_package(package)
            genre=package.manifest["native_editor"]
            return self._json(200,{
                "file_name":"original-godot-"+genre+".zip",
                "zip_base64":b64encode(compressed).decode("ascii"),
                "zip_sha256":__import__("hashlib").sha256(compressed).hexdigest(),
                "source_session_digest":package.manifest["source_session_digest"],
                "engine":genre,
                "gameplay_native_verified_by_this_request":False,
                "source_project_mutated":False,
                "requires_external_hardware_release_review":True,
            })
        if path=="/api/advanced-puzzle-solve":
            proof=solve_advanced_puzzle(
                values["scene"],values.get("settings"),
                max_states=values.get("max_states",20000),
                max_depth=values.get("max_depth",96))
            return self._json(200,{"proof":proof,"source_mutated":False,
                                   "native_release_verified":False})
        if path=="/api/advanced-save":
            result=export_advanced_savegame(values["session"],values.get("settings"))
            return self._json(200,{"savegame":result,
                                    "source_project_mutated":False})
        if path=="/api/advanced-load":
            restored=import_advanced_savegame(values["savegame"])
            return self._json(200,{**restored,
                "available_actions":list(ACTION_HELP[restored["session"]["editor"]])})
        if path=="/api/advanced-continue":
            result=continue_advanced_savegame(
                values["savegame"],values["new_actions"])
            return self._json(200,{"savegame":result,
                                    "source_project_mutated":False})
        if path=="/api/advanced-scene-template":
            scene=make_advanced_scene(
                values["editor"],values.get("settings"),
                seed=values.get("seed",0),
                layout=values.get("layout"),
                scene_id=values.get("scene_id","scene_01"))
            return self._json(200,{
                "scene":scene,"path":scene_path(scene),
                "content":json.dumps(scene,sort_keys=True,ensure_ascii=True,
                                      separators=(",",":"))+"\\n",
                "requires_approved_system":True,
                "automatically_committed":False,
            })
        if path=="/api/fighting-peer-replay":
            report=run_peer_fight(
                values.get("settings"),values.get("blue_actions",[]),
                values.get("red_actions",[]),seed=values.get("seed",0),
                scene=values.get("scene"))
            return self._json(200,{"report":report,
                "independently_verified":verify_peer_fight(
                    report,values.get("settings")),
                "source_code_executed":False,"native_hardware_certified":False,
                "network_transport_certified":False,"game_files_mutated":False})
        if path=="/api/fighting-rollback":
            report=reconcile_peer_prediction(
                values.get("settings"),values.get("blue_actions",[]),
                values.get("predicted_red",[]),
                values.get("authoritative_red",[]),seed=values.get("seed",0),
                scene=values.get("scene"))
            return self._json(200,{"report":report,
                "independently_verified":verify_peer_reconciliation(
                    report,values.get("settings")),
                "source_code_executed":False,"native_hardware_certified":False,
                "network_transport_certified":False,"game_files_mutated":False})
        if path=="/api/rhythm-longrun":
            if values.get("prior") is not None:
                record=continue_long_rhythm(values["prior"],
                    values.get("actions",[]),values.get("settings"))
            else:
                record=run_long_rhythm(
                    values.get("settings"),values.get("actions",[]),
                    seed=values.get("seed",0),scene=values.get("scene"),
                    checkpoint_interval=values.get("checkpoint_interval",64))
            return self._json(200,{"record":record,
                "independently_verified":verify_long_rhythm(
                    record,values.get("settings")),
                "game_files_mutated":False,
                "native_hardware_certified":False})
        if path=="/api/rhythm-audio":
            config=make_editor_document("rhythm",values.get("settings"))["settings"]
            seed=values.get("seed",0)
            if type(seed) is not int or not 0<=seed<=2**31-1:
                raise StudioServerError("original rhythm audio seed must be a bounded integer")
            source=values.get("scene")
            if source is not None:
                source=validate_advanced_scene(source,config)
                if source["editor"]!="rhythm" or source["seed"]!=seed:
                    raise StudioServerError("verified original source/seed mismatch")
                chart=source["layout"]
            else:
                chart=rhythm_default_layout(config,seed)
            from_ms=values.get("from_ms",0)
            duration_ms=values.get("duration_ms",2500)
            if type(duration_ms) is not int or not 100<=duration_ms<=5000:
                raise StudioServerError("studio audio preview must be 100..5000ms")
            sound=render_original_beat_wav(chart,config,from_ms=from_ms,
                                           duration_ms=duration_ms)
            receipt=original_audio_receipt(chart,config,from_ms=from_ms,
                                             duration_ms=duration_ms)
            return self._json(200,{"audio_base64":b64encode(sound).decode("ascii"),
                "receipt":receipt,"original_asset_only":True,
                "native_hardware_certified":False,"game_files_mutated":False})
        if path=="/api/roguelike-marathon":
            if values.get("prior") is not None:
                result=continue_long_roguelike(
                    values["prior"],values.get("actions",[]),values.get("settings"))
            else:
                result=replay_long_roguelike(
                    values.get("settings"),values.get("actions",[]),
                    seed=values.get("seed",0),scene=values.get("scene"),
                    checkpoint_interval=values.get("checkpoint_interval",64))
            return self._json(200,{"record":result,
                "independently_verified":verify_long_roguelike(
                    result,values.get("settings")),
                "game_files_mutated":False,"native_executable_certified":False})
        if path=="/api/world-plan":
            result=plan_original_world(values["scene"],values.get("settings"),
                max_states=values.get("max_states",50000),
                max_actions=values.get("max_actions",128))
            return self._json(200,{"plan":result,
                                  "original_source_mutated":False,
                                  "game_survivability_certified":False})
        if path=="/api/stealth-plan":
            result=plan_stealth_route(
                values["scene"],values.get("settings"),
                max_states=values.get("max_states",30000),
                max_depth=values.get("max_depth",96))
            return self._json(200,{"plan":result,
                                  "original_source_mutated":False,
                                  "live_security_evasion_certified":False})
        if path=="/api/parkour-plan":
            result=plan_parkour_route(
                values["scene"],values.get("settings"),
                max_states=values.get("max_states",12000),
                max_depth=values.get("max_depth",96),
                beam_width=values.get("beam_width",64))
            return self._json(200,{"plan":result,
                                   "original_source_mutated":False,
                                   "native_execution_certified":False})
        if path=="/api/parkour-plan-verify":
            valid=verify_parkour_plan(values["record"],values["scene"],
                                      values.get("settings"))
            return self._json(200,{"verified":valid,"original_source_mutated":False})
        if path=="/api/sports-coach":
            plan=plan_original_sports_match(
                values["scene"],values.get("settings"),
                max_states=values.get("max_states",16000),
                max_depth=values.get("max_depth",64),
                beam_width=values.get("beam_width",48))
            return self._json(200,{"plan":plan,
                                   "original_source_mutated":False,
                                   "native_hardware_certified":False})
        if path=="/api/sports-coach-verify":
            verified=verify_original_sports_plan(
                values["record"],values["scene"],values.get("settings"))
            return self._json(200,{"verified":verified,
                                   "original_source_mutated":False})
        if path=="/api/maze-plan":
            plan=plan_original_maze(
                values["scene"],values.get("settings"),
                max_states=values.get("max_states",12000),
                max_depth=values.get("max_depth",96),
                beam_width=values.get("beam_width",96))
            return self._json(200,{"plan":plan,
                                   "original_source_mutated":False,
                                   "native_hardware_certified":False})
        if path=="/api/maze-plan-verify":
            verified=verify_original_maze_plan(
                values["record"],values["scene"],values.get("settings"))
            return self._json(200,{"verified":verified,
                                   "original_source_mutated":False})
        if path=="/api/rpg-story-plan":
            plan=plan_original_rpg_chapter(
                values["scene"],values.get("settings"),
                max_nodes=values.get("max_nodes",8000),
                max_actions=values.get("max_actions",128),
                social_choice=values.get("social_choice","choose:trust"))
            return self._json(200,{"plan":plan,"original_source_mutated":False,
                                   "native_hardware_verified":False})
        if path=="/api/rpg-story-plan-verify":
            valid=verify_original_rpg_plan(
                values["record"],values["scene"],values.get("settings"))
            return self._json(200,{"verified":valid,"original_source_mutated":False})
        if path=="/api/frontier-expedition-plan":
            plan=plan_original_frontier(
                values["scene"],values.get("settings"),
                max_actions=values.get("max_actions",100),
                retire=values.get("retire",False))
            return self._json(200,{"plan":plan,"original_source_mutated":False,
                                   "native_hardware_verified":False})
        if path=="/api/frontier-expedition-plan-verify":
            valid=verify_original_frontier_plan(
                values["record"],values["scene"],values.get("settings"))
            return self._json(200,{"verified":valid,"original_source_mutated":False})
        if path=="/api/civic-plan":
            plan=plan_original_civic_milestone(
                values["scene"],values.get("settings"),
                max_actions=values.get("max_actions",100),
                retire=values.get("retire",False))
            return self._json(200,{"plan":plan,
                                   "original_source_mutated":False,
                                   "native_hardware_verified":False})
        if path=="/api/civic-plan-verify":
            validated=verify_original_civic_plan(
                values["record"],values["scene"],values.get("settings"))
            return self._json(200,{"verified":validated,
                                   "original_source_mutated":False})
        if path=="/api/ecology-plan":
            plan=plan_original_ecology(
                values["scene"],values.get("settings"),
                max_actions=values.get("max_actions",100),
                retire=values.get("retire",False))
            return self._json(200,{"plan":plan,
                                   "original_source_mutated":False,
                                   "native_hardware_verified":False})
        if path=="/api/ecology-plan-verify":
            validated=verify_original_ecology_plan(
                values["record"],values["scene"],values.get("settings"))
            return self._json(200,{"verified":validated,
                                   "original_source_mutated":False})
        if path=="/api/advanced-play":
            result=run_advanced_session(
                values["editor"], values.get("settings"),
                values.get("actions", []), seed=values.get("seed", 0),
                scene=values.get("scene"))
            return self._json(200, {"session":result,
                                    "available_actions":list(ACTION_HELP[result["editor"]]),
                                    "server_mutated_game_files":False})
        if path=="/api/advanced-verify":
            verified=verify_advanced_session(
                values["session"],values.get("settings"))
            return self._json(200,{"verified":verified,
                                   "publication_certified":False})
        if path=="/api/editor-preview":
            editor=values["editor"]
            config=values.get("settings")
            preview=preview_editor(editor,config,values.get("actions"))
            return self._json(200,{
                "editor":editor,"path":editor_path(editor),
                "content":editor_source(editor,config),
                "preview":preview,
                "write_authorized":False,
                "human_commit_required":True,
            })
        if path=="/api/plan":
            output=route_game_prompt(studio,values["prompt"],
                                     project=values["project"],
                                     authorized=True).payload()
        elif path=="/api/ai-propose":
            plan=route_game_prompt(studio,values["prompt"],
                                   project=values["project"],authorized=True)
            if values["plan_digest"]!=plan.digest:
                raise WorkspaceError("AI source proposal is not bound to this plan")
            output=ingest_ai_draft(studio,plan,values["draft"],authorized=True)
        elif path=="/api/create":
            output=studio.create_project(values["project"],values["genre"],
                                         authorized=True)
        elif path=="/api/select":
            output=studio.select_project(values["project"],authorized=True)
        elif path=="/api/propose":
            output=studio.propose(values["project"],values["path"],
                                  values["content"],
                                  expected_sha256=values["expected_sha256"],
                                  reason=values["reason"],authorized=True)
        elif path=="/api/commit":
            output=studio.commit(values["proposal_id"],
                                 human_approved=values["human_approved"],
                                 authorized=True)
        elif path=="/api/archive":
            output=studio.archive(values["project"],demo=values["demo"],
                                  authorized=True)
        elif path=="/api/autoload":
            output=studio.autoload_previous(values["genre"],values["project"],
                                            authorized=True)
        elif path=="/api/fork-demo":
            output=studio.fork_demo(values["reference"],values["project"],
                                    authorized=True)
        else:
            return self._json(404,{"error":"unrecognized game studio mutation"})
        return self._json(200,output)


def create_workspace_server(workspace: GameWorkspace, *, host: str="127.0.0.1",
                            port: int=0):
    """Bind loopback, no public listener, no cross-origin API and no CORS."""
    if host!="127.0.0.1":
        raise StudioServerError("AI game studio never listens on a public address")
    if not isinstance(workspace,GameWorkspace):
        raise StudioServerError("pre-initialized controlled local game workspace required")
    if type(port) is not int or not 0<=port<=65535:
        raise StudioServerError("invalid bounded local HTTP port")
    secret=secrets.token_urlsafe(32)
    server=_LocalStudioServer((host,port),workspace,secret)
    return server


__all__=["StudioServerError","create_workspace_server"]
