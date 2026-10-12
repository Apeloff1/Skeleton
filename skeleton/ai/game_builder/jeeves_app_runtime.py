"""Jeeves application-wide capability atlas and constrained action dispatcher.

The inventory reflects real installed modules and Studio editor metadata.
A module's existence does NOT confer execution rights: only audited, explicit
adapters below can run. All project edits are review proposals, not commits.
No import-by-name, eval, subprocess, arbitrary source-tree file reads, URL
fetches, AI-weight mutation, device controls or provider-secret access.

This is a local capability bridge usable by Jeeves, chat and the existing
Studio; unsupported source modules are visible as *unwired*, not hallucinated
as functioning runtime adapters.
"""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import re

from .contracts import canonical_digest
from .game_project_workspace import GameWorkspace, WorkspaceError
from .system_editors import (
    catalog as system_catalog, editor_spec, editor_source,
    editor_path, preview_editor)
from .system_editor_assembly import assemble_workspace_systems
from .game_prompt_router import route_game_prompt
from .studio_tool_fabric import (
    ToolFabric, ToolRequest, Actor, Phase)
from .studio_execution_plane import EXECUTABLE_TOOLS
from .jeeves_production_director import work_order

ATLAS_SCHEMA = "skeleton.game_builder.jeeves_app_atlas.v1"
ACTION_SCHEMA = "skeleton.game_builder.jeeves_capability_action.v1"
REQUEST_SCHEMA = "skeleton.game_builder.jeeves_app_request.v1"
ROOT = Path(__file__).resolve().parents[3] / "skeleton"
MAX_MODULES = 30000
MAX_VISIBLE = 120
MAX_RESULTS = 100
EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SHA = re.compile(r"^[a-f0-9]{64}$")
IDENT = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
FILTER = re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")
PROTECTED = re.compile(
    r"(^|[_.-])(secret|credential|password|api.?key|token|private|vault|"
    r"ssh|oauth|session|cookie|auth|license.?key)([_.-]|$)",re.I)
WRITE_ROOTS = ("systems/", "story/", "scenes/", "game/", "missions/",
               "world/", "npc/", "assets/", "design/")
HIGH_RISK = frozenset(("process","filesystem","network","training",
                      "publication","secrets","provider","hardware"))


class JeevesAppCapabilityError(ValueError):
    """Invalid or unproven application capability request."""


# Canonical surfaces: traced to actual installed repo package families.
# 'runtime' only means one of the *explicit* dispatcher adapters below.
# Everything else is discoverable and documented, but remains unexecutable.
SURFACES = {
    "studio": ("ai/game_builder", "system editor families and reviewed game sources"),
    "forge": ("ai/forge", "original game forges, composers, planners and verifiers"),
    "legacy_forge": ("forge", "engine-neutral forge and blueprint components"),
    "crawler": ("ai/webcrawler", "research sources and Dragon acquisition planes"),
    "companion": ("ai/webcrawler", "idle companion and consent-bound Dragon planning"),
    "jeeves": ("jeeves", "existing Jeeves runtime, knowledge, evidence and planners"),
    "assistant": ("ai/assistant", "product chat, tooling and continuity"),
    "model_runtime": ("ai/model_runtime", "native model chat, serving and weights"),
    "training": ("ai/training", "adapters, evaluation, controlled promotion"),
    "learning": ("ai/learning", "holdouts, candidate review and promotion"),
    "ai_agents": ("ai/agents", "typed AI agents and orchestration"),
    "internal_runtime": ("ai/runtime", "AI runtime, context, contracts and plugins"),
    "game": ("game", "native game systems"),
    "engines": ("jeeves", "engine and era-specific code under Jeeves"),
    "knowledge": ("knowledge", "knowledge index and retrieval"),
    "hoag": ("hoag", "Jeeves knowledge display, cards and verification"),
    "creator": ("creator", "original creator graph, proposals and approvals"),
    "organism": ("organism", "scheduler, app governance and idle maintenance"),
    "automation": ("automation", "background supervision and builders"),
    "app": ("app", "application entry points and UI"),
    "assets": ("assets", "local original assets"),
    "audio": ("audio", "sound and voice stack"),
    "video": ("video", "movie/visual analysis stack"),
    "vision": ("vision", "render and vision stack"),
    "security": ("security", "security gates and authority"),
    "shells": ("shells", "policy-governed execution (not granted to Jeeves)"),
    "research": ("research", "independent research"),
    "providers": ("providers", "provider runtime and credentials (not exposed)"),
    "release": ("release", "shipping/signing tools (not granted)"),
    "masterplan": ("masterplan", "signed milestone and volume registers"),
    "project_files": ("ai/game_builder", "active human-reviewed workspace files"),
    "root": ("", "the installed Skeleton application source taxonomy"),
}

# All actions are explicitly available to Jeeves through a local, token-gated
# dispatch route. Privileged actions *prepare* changes; none commits them.
ACTION_DEFS = (
    ("atlas.summary", "Discover installed app families and executable adapters", "read", False),
    ("atlas.family", "Page verified module names in an app family", "read", False),
    ("atlas.search", "Search installed capability names and source-tree taxonomy", "read", False),
    ("atlas.editor", "Inspect an actual typed system editor and its full knobs", "read", False),
    ("studio.tree", "Inspect the current/previous/demo workspace tree", "read", False),
    ("studio.source", "Read bounded reviewed current-project source", "read", False),
    ("studio.editor.catalog", "Discover all typed game system editors", "read", False),
    ("studio.editor.preview", "Validate editor configuration and run existing deterministic preview", "simulate", False),
    ("studio.editor.stage", "Prepare a single exact-source system edit requiring human commit", "propose", True),
    ("studio.assembly", "Compile reviewed game systems with explicit missing runtime gates", "simulate", False),
    ("studio.route", "Map creative request to exact module/source targets", "plan", False),
    ("jeeves.director", "Plan a phase-correct original Jeeves game production task", "plan", False),
    ("jeeves.chapter_chat", "Recall approved chapter history and prepare one governed chat turn", "plan", False),
    ("forge.kinds", "Inspect the real registered universal forge component kinds", "read", False),
    ("tool.fabric", "Inspect actual game tool contracts versus executable handlers", "read", False),
    ("tool.plan", "Validate a finite typed Jeeves tool plan without executing it", "plan", True),
    ("companion.simulate", "Rehearse consent-bound Dragon growth and idle state transitions", "simulate", False),
    ("crawler.catalog", "Inspect installed acquisition/research workers and their adapter status", "read", False),
    ("model.improvement", "Prepare an evidence-bound shadow/model enhancement review, never promote weights", "propose", False),
)
ACTIONS = {item[0]: item for item in ACTION_DEFS}


def _exact(value, fields, name):
    if type(value) is not dict or set(value) != set(fields):
        raise JeevesAppCapabilityError("exact " + name + " keys required")
    return value


def _bounds(value, lo, hi, name):
    if type(value) is not int or not lo <= value <= hi:
        raise JeevesAppCapabilityError("bounded integer required for " + name)
    return value


def _name(value, name):
    if type(value) is not str or not IDENT.fullmatch(value):
        raise JeevesAppCapabilityError("invalid " + name + " identifier")
    return value


def _plain(value, name, maximum=8000):
    if type(value) is not str or not 1 <= len(value) <= maximum:
        raise JeevesAppCapabilityError("bounded " + name + " text required")
    return value


def _sha(value, name):
    if type(value) is not str or not SHA.fullmatch(value):
        raise JeevesAppCapabilityError("content-addressed " + name + " required")
    return value


def _safe_dir(root):
    if not root.is_dir() or root.is_symlink():
        raise JeevesAppCapabilityError("installed feature directory unavailable")
    return root


def _entries(family, *, offset=0, limit=80, prefix=None):
    """One-level source taxonomy; no recursive secrets or raw source imports."""
    if family not in SURFACES:
        raise JeevesAppCapabilityError("unknown installed app capability family")
    offset=_bounds(offset,0,MAX_MODULES,"source page offset")
    limit=_bounds(limit,1,MAX_VISIBLE,"source page limit")
    if prefix is not None:
        _plain(prefix,"source module filter",64)
        if not FILTER.fullmatch(prefix):
            raise JeevesAppCapabilityError("unsafe source module filter")
    relative=SURFACES[family][0]
    root=_safe_dir(ROOT/relative)
    entries=[]
    # os.scandir/Path.iterdir are bounded by per-directory maximum. Only
    # metadata of Python/source directories is visible, not raw code.
    for candidate in root.iterdir():
        if candidate.is_symlink() or candidate.name.startswith("."):
            continue
        if (candidate.is_dir() or candidate.suffix in (".py",".json",".md",
                ".ts",".js",".tsx",".jsx",".css",".html",".gd",".yml",".yaml")):
            if prefix is None or prefix.lower() in candidate.name.lower():
                entries.append({
                    "name":candidate.name,
                    "type":"family" if candidate.is_dir() else "module",
                    "relative_path":(relative + "/" if relative else "")+
                                    candidate.name,
                    "execution_adapter":False,
                    "access":"discoverable_only",
                })
        if len(entries)>MAX_MODULES:
            raise JeevesAppCapabilityError("inventory too large: request a narrower family")
    entries.sort(key=lambda x:(x["type"],x["name"]))
    return {"family":family,"description":SURFACES[family][1],
            "total_entries":len(entries),"offset":offset,"limit":limit,
            "entries":entries[offset:offset+limit],
            "next_offset":offset+limit if offset+limit<len(entries) else None,
            "no_implicit_execute_authority":True}


def _action_index():
    return [{
        "id":key,"description":description,"effect":effect,
        "operator_authorization_required":requires,
        "executable_local_adapter":True,
        "human_source_commit_delegated":False,
        "network_or_provider_access":False,
    } for key,description,effect,requires in ACTION_DEFS]


def app_atlas(*, family=None, offset=0, limit=80, query=None):
    """Live feature taxonomy with truthful adapter coverage and source pages."""
    names=sorted(SURFACES)
    if family is not None:
        payload=_entries(family,offset=offset,limit=limit,prefix=query)
    else:
        if query is not None:
            _plain(query,"search query",64)
            names=[key for key in names if query.casefold() in key.casefold()
                   or query.casefold() in SURFACES[key][1].casefold()]
        payload={
            "families":[{
                "id":key,"path":"skeleton/"+SURFACES[key][0],
                "description":SURFACES[key][1],
                "present":(ROOT/SURFACES[key][0]).is_dir(),
                "source_executable_by_name":False,
            } for key in names],
            "family_count":len(names),"operator_adapters":_action_index(),
            "typed_game_editor_count":len(system_catalog()),
            "local_executable_game_tools":sorted(EXECUTABLE_TOOLS),
            "all_source_modules_executable":False,
            "coverage_interpretation":"cataloged != wired != tested != publishable",
        }
    body={"schema":ATLAS_SCHEMA,**payload}
    return {**body,"digest":canonical_digest(body)}


def _project(workspace, project):
    if not isinstance(workspace,GameWorkspace):
        raise JeevesAppCapabilityError("bound original game workspace required")
    if type(project) is not str or project!=workspace.active():
        raise JeevesAppCapabilityError("Jeeves actions require the active selected project")


def _source_read(workspace,project,args):
    _exact(args,("path",),"source read request")
    path=args["path"]
    if type(path) is not str or not any(path.startswith(x) for x in WRITE_ROOTS):
        raise PermissionError("Jeeves source reads must stay inside reviewed game directories")
    if PROTECTED.search(path):
        raise PermissionError("source path contains credential or identity material")
    record=workspace.read("current",project,path)
    if len(record["content"].encode("utf-8"))>32000:
        raise JeevesAppCapabilityError("full source too large for a single Jeeves context turn")
    return {"path":path,"sha256":record["version"]["sha256"],
            "content":record["content"],"source_read_only":True}


def _stage_editor(workspace,project,args,authorized):
    if not authorized:
        raise PermissionError("operator authorization required to stage Jeeves editor changes")
    _exact(args,("editor","settings","reason"),"editor staging proposal")
    editor=_name(args["editor"],"editor")
    source=editor_source(editor,args["settings"])
    reason=_plain(args["reason"],"review rationale",1000)
    if len(reason)<10:
        raise JeevesAppCapabilityError("review must explain the intended original change")
    path=editor_path(editor)
    files={row.path:row for row in workspace.files("current",project)}
    sha=files[path].sha256 if path in files else EMPTY_SHA
    result=workspace.propose(project,path,source,expected_sha256=sha,
                             reason=reason,authorized=True)
    return {**result,"editor":editor,"editor_spec_digest":
            canonical_digest(editor_spec(editor)),
            "no_unreviewed_commit":True,"source_was_committed":False}


def _simulate_companion(args):
    _exact(args,("owner","events"),"Dragon companion rehearsal")
    from skeleton.ai.webcrawler.dragon_companion_runtime import (
        new_companion, transition, DragonEvent, animation_frame)
    owner=_plain(args["owner"],"companion owner",128)
    events=args["events"]
    if type(events) is not list or len(events)>16:
        raise JeevesAppCapabilityError("finite Dragon rehearsal event list required")
    state=new_companion(owner)
    trajectory=[]
    for event in events:
        if type(event) is not dict or set(event)-{"event","topic","consent",
                                                 "progress"} or "event" not in event:
            raise JeevesAppCapabilityError("typed Dragon event and optional parameters required")
        if event["event"] == "approved":
            raise PermissionError("Jeeves cannot impersonate human approval of Dragon memory")
        try:
            choice=DragonEvent(event["event"])
        except (ValueError,TypeError) as exc:
            raise JeevesAppCapabilityError("unrecognized Dragon companion event") from exc
        consent=event.get("consent",False)
        if type(consent) is not bool:
            raise JeevesAppCapabilityError("explicit boolean companion consent required")
        state=transition(state,choice,topic=event.get("topic",""),
                         consent=consent,progress=event.get("progress"),
                         human_approved=False)
        trajectory.append({"event":choice.value,"phase":state.phase.value,
                           "fingerprint":state.fingerprint})
    return {"schema":"skeleton.game_builder.jeeves_dragon_rehearsal.v1",
            "phases":trajectory,"final_frame":animation_frame(state),
            "real_network_crawl_performed":False,
            "memory_or_weights_promoted":False,
            "persistent_companion_state_changed":False}


def _tool_contracts():
    fabric=ToolFabric()
    plans=[]
    for phase in Phase:
        for spec in fabric.discover(actor=Actor.JEEVES,phase=phase):
            if spec.tool_id not in {x["id"] for x in plans}:
                plans.append({**spec.to_payload(),
                              "local_executor_present":spec.tool_id in EXECUTABLE_TOOLS,
                              "model_may_execute_without_operator":False})
    return sorted(plans,key=lambda x:x["tool_id"])


def _plan_tool(args,authorized):
    if not authorized:
        raise PermissionError("typed tool work planning requires operator approval")
    _exact(args,("phase","tools","input_digest","rationale"),
           "tool plan request")
    phase=Phase(args["phase"])
    tools=args["tools"]
    _sha(args["input_digest"],"tool input")
    rationale=_plain(args["rationale"],"tool plan rationale",300)
    if len(rationale)<3 or type(tools) is not list or len(tools)>16:
        raise JeevesAppCapabilityError("finite tool list and adequate rationale required")
    requests=tuple(ToolRequest(actor=Actor.JEEVES,phase=phase,tool_id=k,
                               input_digest=args["input_digest"],rationale=rationale)
                   for k in tools)
    plan=ToolFabric().plan(requests,authorized=True,
                           max_resource_units=500,allow_filesystem_write=False)
    return {**plan.to_payload(),
            "locally_executable_tools":
                [key for key in tools if key in EXECUTABLE_TOOLS],
            "unwired_tools":[key for key in tools if key not in EXECUTABLE_TOOLS],
            "execution_performed":False,
            "operator_signoff_on_execution_still_required":True}


def _improvement_proposal(project,args):
    _exact(args,("target_family","baseline_sha256","candidate_sha256",
                 "hypothesis","metrics","rollback_plan"),
           "Jeeves improvement plan")
    family=args["target_family"]
    if family not in SURFACES:
        raise JeevesAppCapabilityError("unknown original app feature family")
    baseline=_sha(args["baseline_sha256"],"baseline")
    candidate=_sha(args["candidate_sha256"],"candidate")
    if baseline==candidate:
        raise JeevesAppCapabilityError("self-improvement proposal has no content delta")
    hypothesis=_plain(args["hypothesis"],"testable quality hypothesis",2000)
    rollback=_plain(args["rollback_plan"],"reversible rollback plan",1000)
    metrics=args["metrics"]
    if type(metrics) is not list or not 1<=len(metrics)<=32:
        raise JeevesAppCapabilityError("reproducible quality metrics needed")
    for m in metrics:
        if type(m) is not str or not 5<=len(m)<=160:
            raise JeevesAppCapabilityError("ambiguous improvement measurement")
    require_names=("frozen_holdout","adversarial_mirror","performance_budget",
                   "security_rights","rollback_replay","operator_review")
    body={
        "schema":"skeleton.game_builder.jeeves_improvement_candidate.v1",
        "project":project,"family":family,"baseline_sha256":baseline,
        "candidate_sha256":candidate,"hypothesis":hypothesis,
        "metrics":metrics,"rollback_plan":rollback,
        "required_independent_gates":list(require_names),
        "workflow":["shadow_weights_candidate","verification_sandbox",
                    "heldout_game_quality","reviewed_model_or_code_patch",
                    "separate_operator_promotion_and_rollback"],
        "frozen_holdout_report_provided":False,
        "weight_promotion_performed":False,
        "runtime_self_modification_performed":False,
        "promotion_authority_delegated":False,
    }
    return {**body,"digest":canonical_digest(body)}


def dispatch_app_action(workspace,project,action,args,*,authorized=False):
    """One exact typed capability invocation; no free-form model tool execution."""
    _project(workspace,project)
    if type(action) is not str or action not in ACTIONS:
        raise JeevesAppCapabilityError("unregistered Jeeves app action")
    if type(args) is not dict or len(args)>12:
        raise JeevesAppCapabilityError("bounded typed Jeeves action arguments required")
    if type(authorized) is not bool:
        raise JeevesAppCapabilityError("explicit actor authorization required")
    _,_,effect,needs_operator=ACTIONS[action]
    if needs_operator and not authorized:
        raise PermissionError("operator authorization is required for this capability")
    if action=="atlas.summary":
        _exact(args,(),"app summary request")
        result=app_atlas()
    elif action=="atlas.family":
        _exact(args,("family","offset","limit"),"app family page")
        result=app_atlas(family=args["family"],offset=args["offset"],limit=args["limit"])
    elif action=="atlas.search":
        _exact(args,("family","query","offset","limit"),"app source search")
        result=app_atlas(family=args["family"],query=args["query"],
                         offset=args["offset"],limit=args["limit"])
    elif action=="atlas.editor":
        _exact(args,("editor",),"editor schema lookup")
        result=editor_spec(args["editor"])
    elif action=="studio.tree":
        _exact(args,(),"project tree")
        result=workspace.tree()
    elif action=="studio.source":
        result=_source_read(workspace,project,args)
    elif action=="studio.editor.catalog":
        _exact(args,(),"real editor catalog")
        result={"editors":system_catalog()}
    elif action=="studio.editor.preview":
        _exact(args,("editor","settings"),"editor preview")
        result=preview_editor(args["editor"],args["settings"])
    elif action=="studio.editor.stage":
        result=_stage_editor(workspace,project,args,authorized)
    elif action=="studio.assembly":
        _exact(args,(),"approved engine assembly")
        result=assemble_workspace_systems(workspace,project,authorized=True)
    elif action=="studio.route":
        _exact(args,("prompt",),"original game prompt routing")
        result=route_game_prompt(workspace,args["prompt"],project=project,
                                 authorized=True).payload()
    elif action=="jeeves.director":
        _exact(args,("prompt","cast","region","act","scene"),"Jeeves production direction")
        result=work_order(workspace,project,args["prompt"],
                          cast=args["cast"],region=args["region"],
                          act=args["act"],scene=args["scene"])
    elif action=="jeeves.chapter_chat":
        _exact(args,("prompt","session","cast","region"),"Jeeves chapter chat")
        from .jeeves_chapter_chat import chat_turn
        result=chat_turn(workspace,project,args["prompt"],session=args["session"],
                         cast=args["cast"],region=args["region"])
    elif action=="forge.kinds":
        _exact(args,(),"installed forge read")
        from skeleton.ai.forge.universal import Forge
        result={"component_kinds":Forge().available_kinds(),
                "blueprint_materialization_executed":False}
    elif action=="tool.fabric":
        _exact(args,(),"existing typed tool fabric")
        result={"tools":_tool_contracts(),
                "source_discovery_is_not_execution_authority":True}
    elif action=="tool.plan":
        result=_plan_tool(args,authorized)
    elif action=="companion.simulate":
        result=_simulate_companion(args)
    elif action=="crawler.catalog":
        _exact(args,("offset","limit"),"Dragon worker catalog")
        result=app_atlas(family="crawler",offset=args["offset"],limit=args["limit"])
    elif action=="model.improvement":
        result=_improvement_proposal(project,args)
    else:
        raise JeevesAppCapabilityError("no audited adapter installed for action")
    body={
        "schema":ACTION_SCHEMA,"project":project,"action":action,
        "effect":effect,"arguments_digest":canonical_digest(args),
        "result":result,
        "runtime_adapter_executed":True,
        "source_files_committed":False,
        "model_weights_changed":False,
        "network_calls_by_dispatch":False,
        "human_approval_still_required_for_commits":True,
    }
    return {**body,"digest":canonical_digest(body)}
