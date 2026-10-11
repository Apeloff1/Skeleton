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

from .game_project_workspace import GameWorkspace, WorkspaceError
from .game_workspace_ui import render_workspace_html
from .game_prompt_router import route_game_prompt,ingest_ai_draft
from .system_editors import catalog as system_editor_catalog, editor_source, editor_path, preview_editor
from .system_editor_assembly import assemble_workspace_systems
from .advanced_gameplay_runtime import (
    run_advanced_session, verify_advanced_session, ACTION_HELP,
)
from .advanced_level_scenes import make_advanced_scene, scene_path


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
