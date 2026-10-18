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

import json
import math
import re
from hashlib import sha256
from pathlib import Path

from .contracts import canonical_digest
from .game_project_workspace import GameWorkspace
from .game_prompt_router import route_game_prompt
from .jeeves_production_director import work_order
from .studio_execution_plane import EXECUTABLE_TOOLS
from .studio_tool_fabric import Actor, Phase, ToolFabric, ToolRequest
from .system_editor_assembly import assemble_workspace_systems
from .system_editors import catalog as system_catalog
from .system_editors import editor_path, editor_source, editor_spec, preview_editor

ATLAS_SCHEMA = "skeleton.game_builder.jeeves_app_atlas.v1"
ACTION_SCHEMA = "skeleton.game_builder.jeeves_capability_action.v1"
REQUEST_SCHEMA = "skeleton.game_builder.jeeves_app_request.v1"
ROOT = Path(__file__).resolve().parents[3] / "skeleton"
REPO_ROOT = ROOT.parent
MAX_MODULES = 30000
MAX_VISIBLE = 120
MAX_RESULTS = 100
EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SHA = re.compile(r"^[a-f0-9]{64}$")
IDENT = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
FILTER = re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")
PROTECTED = re.compile(
    r"(^|[_.-])(secret|credential|password|api.?key|token|private|vault|"
    r"ssh|oauth|session|cookie|auth|license.?key)([_.-]|$)",re.IGNORECASE)
WRITE_ROOTS = ("systems/", "story/", "scenes/", "game/", "missions/",
               "world/", "npc/", "npcs/", "assets/", "design/",
               "dialogue/", "cinematics/", "engine/", "almanacs/", "notes/")
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

# GitHub root scan confirmed that the actual product also owns these parallel
# frontend/backend, app, packaging, accelerator and machine planes.
# They are metadata-only: not magically importable or writable Python modules.
EXTERNAL_SURFACES = {
    "frontend": ("frontend","React / React Native app, presentation and navigation"),
    "frontend_features": ("frontend/src/features","user-visible UI feature implementations"),
    "frontend_components": ("frontend/src/components","shared visual/editor components"),
    "frontend_services": ("frontend/src/services","typed client app services"),
    "frontend_state": ("frontend/src/state","app state and user/session interactions"),
    "backend": ("backend","API, model services and native gameforge"),
    "backend_routes": ("backend/routes","app-facing API route implementations"),
    "backend_services": ("backend/services","backend service orchestration"),
    "backend_gameforge": ("backend/gameforge","backend gameforge adapters"),
    "jeeves_app": ("apps/jeeves","standalone Jeeves application entry point"),
    "windows_packaging": ("packaging/windows","native Windows packaging and installer"),
    "java_accelerators": ("java-accelerators","native Java physics, observability and vector"),
    "satellite_gameforge": ("satellites","Rust/gameforge middleware and satellite components"),
    "machine_index": ("machine","internal machine-readable app feature and milestone catalogs"),
    "volume_forge": ("volume_forge","existing volume and milestone compiler"),
    "test_suites": ("tests","engineering and regression test suites"),
    "core_services": ("core","global supervisor and activation security"),
}
SURFACES.update(EXTERNAL_SURFACES)


def _family_root(family):
    """Fixed installed package root, never an actor-supplied filesystem path."""
    if family not in SURFACES:
        raise JeevesAppCapabilityError("unknown installed app capability family")
    relative=SURFACES[family][0]
    root=(REPO_ROOT if family in EXTERNAL_SURFACES else ROOT)
    return root/relative


def _family_display(family):
    relative=SURFACES[family][0]
    return (relative if family in EXTERNAL_SURFACES
            else "skeleton/"+relative).rstrip("/")


# All actions are explicitly available to Jeeves through a local, token-gated
# dispatch route. Privileged actions *prepare* changes; none commits them.
ACTION_DEFS = (
    ("atlas.summary", "Discover installed app families and executable adapters", "read", False),
    ("atlas.family", "Page verified module names in an app family", "read", False),
    ("atlas.search", "Search installed capability names and source-tree taxonomy", "read", False),
    ("atlas.deep", "Inventory nested real modules in a bounded app subsystem", "read", False),
    ("atlas.editor", "Inspect an actual typed system editor and its full knobs", "read", False),
    ("studio.tree", "Inspect the current/previous/demo workspace tree", "read", False),
    ("studio.source", "Read bounded reviewed current-project source", "read", False),
    ("studio.editor.catalog", "Discover all typed game system editors", "read", False),
    ("studio.editor.preview", "Validate editor configuration and run existing deterministic preview", "simulate", False),
    ("studio.editor.stage", "Prepare a single exact-source system edit requiring human commit", "propose", True),
    ("studio.source.propose", "Stage any project-scoped editor/director/forge file under exact-SHA human review", "propose", True),
    ("studio.assembly", "Compile reviewed game systems with explicit missing runtime gates", "simulate", False),
    ("studio.route", "Map creative request to exact module/source targets", "plan", False),
    ("jeeves.director", "Plan a phase-correct original Jeeves game production task", "plan", False),
    ("jeeves.chapter_chat", "Recall approved chapter history and prepare one governed chat turn", "plan", False),
    ("forge.kinds", "Inspect the real registered universal forge component kinds", "read", False),
    ("forge.graph", "Compose and structurally verify an original universal forge graph", "simulate", False),
    ("game.compile.original", "Actually compile a small original playable browser game with winning replay", "simulate", True),
    ("game.compile.native", "Actually compile original browser plus Godot source with bounded replay proof", "simulate", True),
    ("game.console.catalog", "List real console native source and sprite integration targets", "read", False),
    ("game.console.source.stage", "Generate authentic console assembly/C and stage one exact source for human approval", "propose", True),
    ("game.console.source.stage.artwork", "Compile six exact original 8x8 sprite tile arrays into reviewed native console source", "propose", True),
    ("game.mirror.review", "Run original game browser/native replay plus the independent adversarial mirror", "simulate", True),
    ("system.triad", "Exercise bounded gameplay, assets, music and reference integrity through deterministic role adapters", "simulate", True),
    ("tool.fabric", "Inspect actual game tool contracts versus executable handlers", "read", False),
    ("tool.plan", "Validate a finite typed Jeeves tool plan without executing it", "plan", True),
    ("companion.simulate", "Rehearse consent-bound Dragon growth and idle state transitions", "simulate", False),
    ("crawler.catalog", "Inspect installed acquisition/research workers and their adapter status", "read", False),
    ("model.improvement", "Prepare an evidence-bound shadow/model enhancement review, never promote weights", "propose", False),
)
ACTIONS = {item[0]: item for item in ACTION_DEFS}
_ACTION_PARAMETERS = {
    "atlas.summary": ((), ()),
    "atlas.family": (("family", "offset", "limit"), ()),
    "atlas.search": (("family", "query", "offset", "limit"), ()),
    "atlas.deep": (("family", "query", "offset", "limit", "max_depth"), ()),
    "atlas.editor": (("editor",), ()),
    "studio.tree": ((), ()),
    "studio.source": (("path",), ()),
    "studio.editor.catalog": ((), ()),
    "studio.editor.preview": (("editor", "settings"), ()),
    "studio.editor.stage": (("editor", "settings", "reason"), ()),
    "studio.source.propose": (("path", "content", "expected_sha256", "reason"), ()),
    "studio.assembly": ((), ()),
    "studio.route": (("prompt",), ()),
    "jeeves.director": (("prompt", "cast", "region", "act", "scene"), ()),
    "jeeves.chapter_chat": (("prompt", "session", "cast", "region"), ()),
    "forge.kinds": ((), ()),
    "forge.graph": (("name", "components", "wires"), ()),
    "game.compile.original": (("intent",), ()),
    "game.compile.native": (("intent",), ()),
    "game.mirror.review": (("intent",), ()),
    "game.console.catalog": ((), ()),
    "system.triad": (("seed", "mirror_attempts"), ()),
    "tool.fabric": ((), ()),
    "tool.plan": (("phase", "tools", "input_digest", "rationale"), ()),
    "companion.simulate": (("owner", "events"), ()),
    "crawler.catalog": (("offset", "limit"), ()),
    "model.improvement": (("target_family", "baseline_sha256", "candidate_sha256",
                           "hypothesis", "metrics", "rollback_plan"), ()),
}
_CONSOLE_FIELDS = (
    "intent", "target", "source_platform", "rights_evidence_sha256",
    "creative_identity", "style", "contrast", "animation_frames",
    "source_file", "expected_sha256", "reason",
)
_ACTION_PARAMETERS["game.console.source.stage"] = (
    _CONSOLE_FIELDS, ("animation_fps", "music_density"))
_ACTION_PARAMETERS["game.console.source.stage.artwork"] = (
    (*_CONSOLE_FIELDS, "artist_tiles"), ("animation_fps", "music_density"))
_CATALOG_OWNERS = (
    "jeeves_app_runtime.py", "jeeves_appwide_fabric.py", "studio_tool_fabric.py",
    "studio_execution_plane.py", "studio_role_triad.py", "system_editors.py",
    "game_workspace_server.py", "game_workspace_ui.py",
    "contracts.py", "game_project_workspace.py", "game_prompt_router.py",
    "system_editor_assembly.py", "jeeves_production_director.py", "jeeves_chapter_chat.py",
    "jeeves_capability_intelligence.py", "jeeves_completion_census.py",
    "advanced_rpg_planner.py", "advanced_world_planner.py", "playable_compiler.py",
    "playable_simulation.py", "playable_world.py", "playable_export.py", "tile_editor_export.py",
    "dual_runtime_export.py", "advanced_gameplay_runtime.py",
    "mirror_room_runtime.py", "companion_curriculum.py", "studio_asset_pipeline.py",
    "studio_sprite_authoring.py", "studio_native_psg.py", "game_boy_native_export.py",
    "game_boy_color_native_export.py", "nes_native_export.py", "sms_native_export.py",
    "sega_8bit_native_export.py", "port_planner.py", "platform_registry.py",
)
_CATALOG_DEPENDENCIES = (
    "skeleton/ai/forge/universal.py",
    "skeleton/ai/webcrawler/dragon_companion_runtime.py",
    "skeleton/ai/webcrawler/dragon_visual_state.py",
    "skeleton/ai/webcrawler/active_research.py",
    "skeleton/ai/webcrawler/dragon_chip_music.py",
    "skeleton/ai/webcrawler/dragon_game_blueprints.py",
    "skeleton/ai/webcrawler/game_scale_assets.py",
    "skeleton/developer/jeeves_game_upscale.py",
    "skeleton/jeeves/game_console_assets.py",
)


def capability_catalog():
    """Bind explicit adapter contracts to installed owner bytes.

    This catalog is suitable for composing a subsequent typed request. It is
    neither model readiness nor permission to execute a discovered source file.
    """
    sources = []
    paths = ["skeleton/ai/game_builder/" + name for name in _CATALOG_OWNERS]
    paths.extend(_CATALOG_DEPENDENCIES)
    for relative in paths:
        target = REPO_ROOT / relative
        if target.is_symlink() or not target.is_file():
            raise JeevesAppCapabilityError("installed capability owner unavailable")
        with target.open("rb") as handle:
            raw = handle.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise JeevesAppCapabilityError("capability owner exceeds source identity budget")
        sources.append({"path": relative,
                        "sha256": sha256(raw).hexdigest(), "bytes": len(raw)})
    body = {
        "schema": "skeleton.game_builder.jeeves_capability_catalog.v1",
        "actions": _action_index(),
        "tools": _tool_contracts(),
        "editors_digest": canonical_digest(system_catalog()),
        "source_owners": sources,
        "source_identity_kind": "installed_owner_bytes_not_model_readiness",
        "source_identity_scope": "listed adapters and explicit domain dependencies",
        "arbitrary_transitive_dependency_closure_attested": False,
        "loaded_runtime_or_standard_library_attested": False,
        "argument_limits": {"top_level_fields": 16, "depth": 16,
                            "nodes": 16_384, "canonical_json_bytes": 256_000},
        "surfaces": {key: _family_display(key) for key in sorted(SURFACES)},
        "source_discovery_grants_execution": False,
        "model_readiness_attested": False,
    }
    return {**body, "digest": canonical_digest(body)}


def _catalog_match(expected):
    catalog = capability_catalog()
    if expected is not None:
        _sha(expected, "capability catalog")
        if expected != catalog["digest"]:
            raise JeevesAppCapabilityError("capability catalog changed; refresh before execution")
    return catalog


def _bounded_arguments(value):
    """Reject deeply nested or oversized model/tool data before any adapter."""
    if type(value) is not dict or len(value) > 16:
        raise JeevesAppCapabilityError("bounded typed Jeeves action arguments required")
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if depth > 16 or nodes > 16_384:
            raise JeevesAppCapabilityError("action data exceeds structural limits")
        if type(item) is dict:
            if len(item) > 128 or any(type(key) is not str or len(key) > 160
                                       for key in item):
                raise JeevesAppCapabilityError("bounded string action keys required")
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            if len(item) > 8192:
                raise JeevesAppCapabilityError("action list exceeds item budget")
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            if len(item) > 128_000:
                raise JeevesAppCapabilityError("action text exceeds source budget")
        elif item is None or type(item) in (bool, int):
            if type(item) is int and item.bit_length() > 64:
                raise JeevesAppCapabilityError("action integer exceeds numeric budget")
        elif type(item) is float and math.isfinite(item):
            pass
        else:
            raise JeevesAppCapabilityError("finite JSON action data required")
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True,
                         separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > 256_000:
        raise JeevesAppCapabilityError("action data exceeds context byte budget")
    return json.loads(encoded)


def compose_app_request(workspace, project, action, args, *,
                        expected_catalog_digest=None):
    """Freeze a selected-project request without granting or using authority."""
    _project(workspace, project)
    if type(action) is not str or action not in ACTIONS:
        raise JeevesAppCapabilityError("unregistered Jeeves app action")
    arguments = _bounded_arguments(args)
    required, optional = _ACTION_PARAMETERS[action]
    if not set(required) <= set(arguments) or set(arguments) - set(required) - set(optional):
        raise JeevesAppCapabilityError("missing or unsupported parameters for " + action)
    catalog = _catalog_match(expected_catalog_digest)
    body = {
        "schema": REQUEST_SCHEMA, "project": project, "action": action,
        "args": arguments, "arguments_digest": canonical_digest(arguments),
        "catalog_digest": catalog["digest"], "effect": ACTIONS[action][2],
        "operator_authorization_required": ACTIONS[action][3],
        "authority_granted": False, "execution_performed": False,
    }
    return {**body, "digest": canonical_digest(body)}


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
    root=_safe_dir(_family_root(family))
    entries=[]
    # os.scandir/Path.iterdir are bounded by per-directory maximum. Only
    # metadata of Python/source directories is visible, not raw code.
    for inspected, candidate in enumerate(root.iterdir(), start=1):
        if inspected > MAX_MODULES:
            raise JeevesAppCapabilityError("directory exceeds bounded capability scan")
        if candidate.is_symlink() or candidate.name.startswith(".") or \
           PROTECTED.search(candidate.name):
            continue
        if ((candidate.is_dir() or candidate.suffix in (".py",".json",".md",
                ".ts",".js",".tsx",".jsx",".css",".html",".gd",".yml",".yaml"))
                and (prefix is None or prefix.lower() in candidate.name.lower())):
            entries.append({
                "name":candidate.name,
                "type":"family" if candidate.is_dir() else "module",
                "relative_path":_family_display(family)+"/"+candidate.name,
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


def _deep_entries(family, *, query=None, offset=0, limit=80, max_depth=8):
    """Recursive bounded walk; path metadata only, no imports or file contents.

    Unlike a static list, it finds newly installed modules and children.
    Scanning is bounded to the named installed family and does not follow
    symlinks, hidden trees, credential filenames or excluded build caches.
    """
    if family not in SURFACES:
        raise JeevesAppCapabilityError("unknown app family")
    offset=_bounds(offset,0,MAX_MODULES,"feature-page offset")
    limit=_bounds(limit,1,MAX_VISIBLE,"feature-page length")
    max_depth=_bounds(max_depth,1,10,"nested source scan depth")
    if query is not None:
        _plain(query,"nested feature search",64)
        if not FILTER.fullmatch(query):
            raise JeevesAppCapabilityError("unsafe nested feature query")
    start=_safe_dir(_family_root(family))
    stack=[(start,0)]
    entries=[]
    visited=0
    examined=depth_truncated=0
    while stack:
        directory,depth=stack.pop()
        visited+=1
        if visited>MAX_MODULES:
            raise JeevesAppCapabilityError("feature walk exceeded bounded directory budget")
        for candidate in directory.iterdir():
            examined += 1
            if examined > MAX_MODULES * 4:
                raise JeevesAppCapabilityError("nested capability entry budget exceeded")
            if candidate.is_symlink() or candidate.name.startswith(".") or \
               PROTECTED.search(candidate.name) or \
               candidate.name in ("__pycache__","node_modules","venv",".venv",
                                  "dist","build","target"):
                continue
            if candidate.is_dir():
                if depth<max_depth:
                    stack.append((candidate,depth+1))
                else:
                    depth_truncated += 1
                typ="directory"
            elif candidate.suffix in (".py",".json",".md",".ts",".js",
                                       ".tsx",".jsx",".css",".html",".gd",".yml",".yaml"):
                typ="module"
            else:
                continue
            installed=candidate.relative_to(REPO_ROOT).as_posix()
            if query is None or query.casefold() in installed.casefold():
                entries.append({
                    "path":installed,"kind":typ,
                    "discovered_from_installed_source":True,
                    "local_execution_adapter_granted":False,
                })
            if len(entries)>MAX_MODULES:
                raise JeevesAppCapabilityError("too many matching installed features")
    entries.sort(key=lambda x:x["path"])
    body={
        "schema":"skeleton.game_builder.jeeves_feature_deep_index.v1",
        "family":family,"path":_family_display(family),
        "matching_entries":len(entries),
        "source_directories_visited":visited,
        "source_entries_examined":examined,
        "depth_truncated_directories":depth_truncated,
        "scanned_to_depth":max_depth,
        "offset":offset,"limit":limit,
        "entries":entries[offset:offset+limit],
        "next_offset":offset+limit if offset+limit<len(entries) else None,
        "model_cannot_execute_arbitrary_discovered_modules":True,
        "no_unreviewed_code_loaded":True,
    }
    return {**body,"digest":canonical_digest(body)}


def _action_index():
    if set(_ACTION_PARAMETERS) != set(ACTIONS):
        raise JeevesAppCapabilityError("capability parameter catalog drifted from adapters")
    return [{
        "id":key,"description":description,"effect":effect,
        "operator_authorization_required":requires,
        "executable_local_adapter":True,
        "human_source_commit_delegated":False,
        "network_or_provider_access":False,
        "model_invocation_by_adapter":False,
        "required_parameters":list(_ACTION_PARAMETERS[key][0]),
        "optional_parameters":list(_ACTION_PARAMETERS[key][1]),
        "runtime_dependencies": ([{
            "kind":"optional_installed_reference_pack",
            "available_by_metadata":all((REPO_ROOT/path).is_file()
                                        and not (REPO_ROOT/path).is_symlink()
                                        for path in (
                "data/game_building/manifest.json",
                "data/game_building/pareto/game_design_pareto_corpus.txt.gz",
                "data/game_building/math_physics/game_math_physics_corpus.txt.gz")),
            "content_verified_at_execution":True,
        }] if key == "system.triad" else []),
    } for key,description,effect,requires in ACTION_DEFS]


def app_atlas(*, family=None, offset=0, limit=80, query=None,
              expected_catalog_digest=None):
    """Live feature taxonomy with truthful adapter coverage and source pages."""
    catalog = _catalog_match(expected_catalog_digest)
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
                "id":key,"path":_family_display(key),
                "description":SURFACES[key][1],
                "present":_family_root(key).is_dir() and not _family_root(key).is_symlink(),
                "source_executable_by_name":False,
            } for key in names],
            "family_count":len(names),"operator_adapters":_action_index(),
            "typed_game_editor_count":len(system_catalog()),
            "local_executable_game_tools":sorted(EXECUTABLE_TOOLS),
            "all_source_modules_executable":False,
            "coverage_interpretation":"cataloged != wired != tested != publishable",
            "catalog_source_owners":catalog["source_owners"],
        }
    body={"schema":ATLAS_SCHEMA,"catalog_digest":catalog["digest"],**payload}
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


def _compile_original_game(project,args,mode):
    """Concrete original game builder, audited and bounded, no filesystem writes.

    Uses the existing canonical game compiler and native source renderer, not
    a second engine. An original playable browser game is actually compiled,
    solved and replayed. Native mode emits Godot source in memory, NOT a
    certified executable installer or a completed commercial game.
    """
    _exact(args,("intent",),"one original game compiler request")
    values=args["intent"]
    if type(values) is not dict:
        raise JeevesAppCapabilityError("typed game intent must be a bounded object")
    allowed=("title","subtitle","seed","width","height","levels",
             "collectibles_per_level","hazards_per_level","theme",
             "starting_health")
    if set(values)-set(allowed) or not {"title","subtitle","seed"}<=set(values):
        raise JeevesAppCapabilityError("unrecognized/absent original game parameters")
    from .dual_runtime_export import render_dual_runtime_package
    from .playable_compiler import compile_original_game
    from .playable_world import GameBuildIntent
    intent=GameBuildIntent(project_id=project,**values)
    # Additional app/Jeeves request budget: the game compiler itself supports
    # larger bounded worlds; the app agent is deliberately constrained.
    if intent.levels>3 or intent.width>25 or intent.height>25 or \
       intent.hazards_per_level>10:
        raise JeevesAppCapabilityError(
            "Jeeves synchronous preview budget: <=3 levels, <=25 tiles/axis, <=10 hazards")
    compiled=compile_original_game(intent,authorized=True)
    record=compiled.receipt()
    package=None
    mirror=None
    if mode in ("native","mirror"):
        package=render_dual_runtime_package(compiled,authorized=True)
    if mode=="mirror":
        from .mirror_room_runtime import review_playable_project
        # The existing mirror reviewer has a bounded attempt count.
        mirror=review_playable_project(
            compiled,package,authorized=True,attempts=64)
        if not mirror.passed:
            raise JeevesAppCapabilityError(
                "independent original game replay/mirror rejected the candidate")
    body={
        "schema":"skeleton.game_builder.jeeves_original_runtime_result.v1",
        "project":project,"mode":mode,"intent":intent.to_payload(),
        "compiled_source_receipt":record,
        "browser_html_sha256":compiled.playable.html_sha256,
        "original_world_sha256":compiled.world.digest,
        "winning_replay_sha256":compiled.proof.digest,
        "native_source_manifest_digest":
            package.manifest["manifest_digest"] if package else None,
        "mirror_receipt_digest":mirror.digest if mirror else None,
        "gameplay_proof_executed":True,
        "native_godot_executable_executed":False,
        "source_exported_to_disk":False,"consumer_release_certified":False,
        "external_model_or_network_used":False,
    }
    return {**body,"digest":canonical_digest(body)}


def _stage_console_art_source(workspace, project, args, *, with_artist=False):
    """Generate actual original native ROM source, then stage through CAS review.

    No toolchain, shell, network or unchecked artifact commit. The operator
    supplies an authorship-document digest as a *reference*, not as proof of
    independently adjudicated IP rights. One source file per reviewed edit.
    """
    fields = _CONSOLE_FIELDS
    optional = tuple(
        name for name in ("animation_fps", "music_density") if name in args
    )
    _exact(args, (*fields, *optional, "artist_tiles")
           if with_artist else (*fields, *optional),
           "original native source production")
    from .game_boy_color_native_export import compile_native_game_boy_color
    from .game_boy_native_export import compile_native_game_boy
    from .nes_native_export import compile_native_nes
    from .platform_registry import default_registry
    from .playable_world import GameBuildIntent, generate_playable_world
    from .port_planner import HomebrewSource
    from .sega_8bit_native_export import compile_native_sega_8bit
    from .sms_native_export import compile_native_sms
    from .studio_asset_pipeline import ArtDirection, _palette, render_studio_art
    from .studio_sprite_authoring import typed_artist_tiles

    targets = {
        "nintendo_game_boy": "main.asm",
        "nintendo_game_boy_color": "main.asm",
        "nintendo_famicom": "main.s",
        "sega_master_system": "game.asm",
        "sega_game_gear": "game.c",
    }
    target = args["target"]
    if type(target) is not str or target not in targets:
        raise JeevesAppCapabilityError("no verified ROM-source pixel integration for target")
    if args["source_file"] != targets[target]:
        raise JeevesAppCapabilityError("selected native file is not the target source entrypoint")
    values = args["intent"]
    if type(values) is not dict or not {"title", "subtitle", "seed"} <= set(values):
        raise JeevesAppCapabilityError("typed original game intent required")
    allowed = {"title", "subtitle", "seed", "width", "height", "levels",
               "collectibles_per_level", "hazards_per_level", "theme", "starting_health"}
    if set(values) - allowed:
        raise JeevesAppCapabilityError("unknown game authoring parameter")
    intent = GameBuildIntent(project_id=project, **values)
    if intent.levels > 3 or intent.width > 19 or intent.height > 15:
        raise JeevesAppCapabilityError("synchronous console source staging budget exceeded")
    basis = _name(args["source_platform"], "registered original source platform")
    if basis not in default_registry().profiles:
        raise JeevesAppCapabilityError("design basis absent from canonical platform registry")
    evidence = _sha(args["rights_evidence_sha256"], "authorship evidence reference")
    creative = args["creative_identity"]
    if type(creative) is not list or not 1 <= len(creative) <= 16:
        raise JeevesAppCapabilityError("1..16 original creative identity statements required")
    rights = HomebrewSource(project, basis, "project_owned", evidence, tuple(creative))
    art = ArtDirection(
        style=args["style"], contrast=args["contrast"],
        animation_frames=args["animation_frames"], seed=intent.seed,
        animation_fps=args.get("animation_fps", 4),
        music_density=args.get("music_density", 2),
    )
    world = generate_playable_world(intent, authorized=True)
    artist_atlas = (
        typed_artist_tiles(
            args["artist_tiles"], palette=_palette(intent.theme, art.contrast),
            authorized=True,
        ) if with_artist else None
    )
    pack = render_studio_art(
        world, target=target, direction=art, authorized=True,
        artist_atlas=artist_atlas,
    )
    hero_frames = None
    frame_delay = 12
    psg = None
    if target in ("nintendo_game_boy", "nintendo_game_boy_color",
                  "nintendo_famicom"):
        from skeleton.jeeves.game_console_assets import decode_tiles

        from .studio_native_psg import compose_native_psg
        hero_frames = decode_tiles(
            dict(pack.files)["tiles/hero_animation.bin"], pack.codec,
        )
        if (len(hero_frames) != art.animation_frames
                or hero_frames[0] != pack.runtime_tiles[5]):
            raise JeevesAppCapabilityError("Jeeves generated mismatching native hero frames")
        frame_delay = max(2, min(60, round(60 / art.animation_fps)))
        psg = compose_native_psg(intent.theme, art.seed, art.music_density)
    if target == "nintendo_game_boy":
        native = compile_native_game_boy(
            world, rights, authorized=True, tile_art=pack.runtime_tiles,
            hero_frames=hero_frames, animation_delay=frame_delay,
            psg_score=psg,
        )
        text = native.asm
    elif target == "nintendo_game_boy_color":
        native = compile_native_game_boy_color(
            world, rights, authorized=True, tile_art=pack.runtime_tiles,
            hero_frames=hero_frames, animation_delay=frame_delay,
            psg_score=psg,
        )
        text = native.asm
    elif target == "nintendo_famicom":
        native = compile_native_nes(
            world, rights, authorized=True, tile_art=pack.runtime_tiles,
            hero_frames=hero_frames, animation_delay=frame_delay,
            psg_score=psg,
        )
        text = native.asm
    elif target == "sega_master_system":
        native = compile_native_sms(world, rights, authorized=True, tile_art=pack.runtime_tiles)
        text = native.asm
    else:
        native = compile_native_sega_8bit(
            world, rights, target, authorized=True, tile_art=pack.runtime_tiles)
        text = native.game_c
    import json
    manifest = json.loads(native.manifest_json)
    expected_art = canonical_digest([list(tile) for tile in pack.runtime_tiles])
    if manifest.get("generated_runtime_art_tile_digest") != expected_art:
        raise JeevesAppCapabilityError("native producer omitted or mutated original sprite pixels")
    if (psg is not None
            and (manifest.get("native_hero_animation_frames") != art.animation_frames
                or manifest.get("native_hero_animation_frame_delay") != frame_delay
                or manifest.get("native_psg_score_digest") != psg.digest
                or manifest.get("original_native_psg_integrated")
                != (psg.density > 0))):
        raise JeevesAppCapabilityError("generated native animation/audio content lost")
    if len(text.encode("utf-8")) > 240_000:
        raise JeevesAppCapabilityError("generated native file exceeds reviewed source capacity")
    path = "game/native/" + target + "/" + targets[target]
    revision = _sha(args["expected_sha256"], "exact existing source revision")
    reason = _plain(args["reason"], "native source review rationale", 1000)
    if len(reason) < 10:
        raise JeevesAppCapabilityError("native source proposal requires an explicit designer rationale")
    proposal = workspace.propose(
        project, path, text, expected_sha256=revision, reason=reason,
        authorized=True,
    )
    from hashlib import sha256
    return {
        **proposal,
        "schema": "skeleton.game_builder.jeeves_console_source_stage.v1",
        "target": target,
        "original_world_digest": world.digest,
        "native_source_digest": native.content_digest,
        "generated_source_file": path,
        "generated_source_sha256": sha256(text.encode("utf-8")).hexdigest(),
        "art_pack_digest": pack.digest,
        "artist_sprite_pixel_digest": artist_atlas.digest if artist_atlas else None,
        "native_tile_art_digest": expected_art,
        "sprite_preview_count": len(world.levels),
        "animation_frame_count": art.animation_frames,
        "native_animation_frame_delay": frame_delay if hero_frames else None,
        "native_animation_source_integrated": bool(
            hero_frames and len(hero_frames) > 1
        ),
        "native_psg_score_digest": psg.digest if psg else None,
        "native_psg_audio_source_integrated": bool(psg and psg.density > 0),
        "emulator_audio_executed": False,
        "native_pcm_sound_equivalence_claimed": False,
        "actual_native_source_generated": True,
        "actual_sprite_pixels_embedded": True,
        "binary_compiled": False,
        "emulator_or_hardware_qualified": False,
        "rights_independently_verified": False,
        "source_committed": False,
        "human_review_and_explicit_commit_required": True,
    }


def _propose_source(workspace,project,args,authorized):
    """The common guarded write gateway for all project-owned editor families.

    Full 3D, character, dialogue, world, cinematic, quest, forge and director
    authoring is possible as source proposals without a generic write primitive.
    Existing Studio validators still run on BOTH proposal and human commit.
    Every source is revision-bound and cannot edit app Python outside the
    active project source tree.
    """
    if not authorized:
        raise PermissionError("operator authorization is needed for project source proposals")
    _exact(args,("path","content","expected_sha256","reason"),
           "Jeeves whole-studio source proposal")
    path=args["path"]
    if type(path) is not str or not any(path.startswith(p) for p in WRITE_ROOTS):
        raise PermissionError("Jeeves project edits must stay inside reviewed editor directories")
    if PROTECTED.search(path):
        raise PermissionError("cannot propose credential material as a game source")
    content=_plain(args["content"],"reviewable UTF-8 original source",128000)
    sha=_sha(args["expected_sha256"],"optimistic source revision")
    reason=_plain(args["reason"],"specific designer review reason",1000)
    if len(reason)<10:
        raise JeevesAppCapabilityError("authored source must have a detailed review reason")
    result=workspace.propose(project,path,content,
                             expected_sha256=sha,
                             reason=reason,
                             authorized=True)
    return {**result,"source_file_compiled":False,
            "human_commit_required":True,
            "no_undocumented_filesystem_write":True}


def _simulate_companion(args):
    _exact(args,("owner","events"),"Dragon companion rehearsal")
    from skeleton.ai.webcrawler.dragon_companion_runtime import (
        DragonEvent,
        animation_frame,
        new_companion,
        transition,
    )
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


def _review_forge_graph(args):
    """Actual Universal Forge component/port/type/cycle checking, no build writes."""
    _exact(args,("name","components","wires"),"original forge blueprint")
    name=_plain(args["name"],"original forge blueprint name",120)
    components=args["components"]
    wires=args["wires"]
    if type(components) is not list or not 1<=len(components)<=64:
        raise JeevesAppCapabilityError("finite original forge components required")
    if type(wires) is not list or len(wires)>128:
        raise JeevesAppCapabilityError("bounded forge port connections required")
    from skeleton.ai.forge.universal import Blueprint, Forge
    forge=Forge()
    # Pure, ephemeral graph; no new on-disk project, no event bus.
    blueprint=Blueprint(blueprint_id="jeeves_ephemeral",name=name,created_at=0.0)
    for item in components:
        _exact(item,("id","kind","config"),"original forge component")
        _name(item["id"],"forge instance")
        if type(item["kind"]) is not str or item["kind"] not in forge.available_kinds():
            raise JeevesAppCapabilityError("forge kind absent from installed component registry")
        if type(item["config"]) is not dict or len(item["config"])>32:
            raise JeevesAppCapabilityError("bounded typed forge configuration needed")
        forge.instantiate(blueprint,item["kind"],item["id"],config=item["config"])
    for wire in wires:
        if type(wire) is not list or len(wire)!=4:
            raise JeevesAppCapabilityError("forge wire needs four exact port endpoints")
        for end in wire:
            _name(end,"forge connection endpoint")
        blueprint.connect((wire[0],wire[1]),(wire[2],wire[3]))
    problems=blueprint.validate()
    report={
        "schema":"skeleton.game_builder.jeeves_forge_graph_review.v1",
        "source_graph_digest":canonical_digest(args),
        "component_count":len(components),"connection_count":len(wires),
        "valid":not problems,"problems":problems,
        "component_ports":{key:[
            {"name":p.name,"port_type":p.port_type,"direction":p.direction}
            for p in component.ports]
            for key,component in sorted(blueprint.components.items())},
        "game_build_executed":False,"source_project_modified":False,
    }
    return {**report,"digest":canonical_digest(report)}


def _tool_contracts():
    fabric=ToolFabric()
    plans=[]
    for phase in Phase:
        for spec in fabric.discover(actor=Actor.JEEVES,phase=phase):
            if spec.tool_id not in {x["tool_id"] for x in plans}:
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


def dispatch_app_action(workspace,project,action,args,*,authorized=False,
                        expected_catalog_digest=None):
    """One exact typed capability invocation; no free-form model tool execution."""
    _project(workspace,project)
    if type(action) is not str or action not in ACTIONS:
        raise JeevesAppCapabilityError("unregistered Jeeves app action")
    if type(args) is not dict or len(args)>16:
        raise JeevesAppCapabilityError("bounded typed Jeeves action arguments required")
    if type(authorized) is not bool:
        raise JeevesAppCapabilityError("explicit actor authorization required")
    _,_,effect,needs_operator=ACTIONS[action]
    if needs_operator and not authorized:
        raise PermissionError("operator authorization is required for this capability")
    request = compose_app_request(
        workspace, project, action, args,
        expected_catalog_digest=expected_catalog_digest)
    args = request["args"]
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
    elif action=="atlas.deep":
        _exact(args,("family","query","offset","limit","max_depth"),
               "recursive app family walk")
        result=_deep_entries(args["family"],query=args["query"],
                             offset=args["offset"],limit=args["limit"],
                             max_depth=args["max_depth"])
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
    elif action=="studio.source.propose":
        result=_propose_source(workspace,project,args,authorized)
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
    elif action=="game.compile.original":
        result=_compile_original_game(project,args,"browser")
    elif action=="game.compile.native":
        result=_compile_original_game(project,args,"native")
    elif action=="game.console.catalog":
        _exact(args,(), "native console production catalog")
        result={
            "targets": [
                "nintendo_game_boy", "nintendo_game_boy_color",
                "nintendo_famicom", "sega_master_system", "sega_game_gear",
            ],
            "source_art_embedded": True,
            "source_formats": ["RGBDS", "ca65", "z80asm", "SDCC C"],
            "art": ["indexed sprites", "tile sheets", "animated PNG previews",
                    "per-level rendered scenes", "sprite descriptors"],
            "workbench_stage": "exact-CAS proposal, explicit human commit",
            "native_executable_compiled": False,
            "external_toolchain_invoked": False,
        }
    elif action=="game.console.source.stage":
        result=_stage_console_art_source(workspace,project,args)
    elif action=="game.console.source.stage.artwork":
        result=_stage_console_art_source(workspace,project,args,with_artist=True)
    elif action=="game.mirror.review":
        result=_compile_original_game(project,args,"mirror")
    elif action=="system.triad":
        _exact(args,("seed","mirror_attempts"),"role triad")
        from .studio_role_triad import connect_system_triad
        result=connect_system_triad(
            seed=args["seed"], mirror_attempts=args["mirror_attempts"],
            authorized=authorized)
    elif action=="forge.graph":
        result=_review_forge_graph(args)
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
    _project(workspace, project)
    if canonical_digest(args) != request["arguments_digest"]:
        raise JeevesAppCapabilityError("adapter changed its frozen request arguments")
    if capability_catalog()["digest"] != request["catalog_digest"]:
        raise JeevesAppCapabilityError("capability source changed during dispatch; refresh evidence")
    body={
        "schema":ACTION_SCHEMA,"project":project,"action":action,
        "catalog_digest":request["catalog_digest"],
        "request_digest":request["digest"],
        "catalog_pin_requested":expected_catalog_digest is not None,
        "effect":effect,"arguments_digest":request["arguments_digest"],
        "result":result,
        "runtime_adapter_executed":True,
        "source_files_committed":False,
        "model_weights_changed":False,
        "network_calls_by_dispatch":False,
        "human_approval_still_required_for_commits":True,
    }
    return {**body,"digest":canonical_digest(body)}
