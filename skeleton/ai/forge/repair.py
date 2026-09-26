"""Bounded forge repair scaffold.

Now wired to policy_enforcement for dynamic threshold/repair gating.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

# Bound at import time on purpose: the canonical scaffold used for closure
# repair must be the real emitter even when a caller swaps the module-level
# ``godot_emit.emit_godot`` (tests, alternative emitters).
from skeleton.forge.eras import compile_era as _compile_era
from skeleton.forge.godot_emit import emit_godot as _canonical_emit
from skeleton.organism.policy_enforcement import repair_class_enabled, repair_enabled_for, threshold_for
from skeleton.organism.quality_state import append_repair, latest_failure, repair_candidates


def latest_repair_plan(*, root=None) -> Dict[str, Any]:
    failure = latest_failure(root=root, surface="forge")
    if not failure:
        return {"kind": "forge-repair-plan", "ok": 0, "reason": "no-failure", "targets": [], "stored_prose": 0}
    reason = failure.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return {"kind": "forge-repair-plan", "ok": 0, "reason": "missing-reason", "targets": [], "stored_prose": 0}
    return {"kind": "forge-repair-plan", "ok": 1, "reason": reason, "surface": "forge", "weakest_path": failure.get("weakest_path") or "", "targets": _targets(failure), "stored_prose": 0}


def candidate_failures(*, root=None, limit: int = 5) -> Dict[str, Any]:
    rows = repair_candidates(root=root, surface="forge")[:max(1, limit)]
    return {"kind": "forge-repair-candidates", "n": len(rows), "items": rows, "stored_prose": 0}


REPAIR_MODES = ("apply", "suggest")

# Canonical autoload singletons emitted by ``godot_emit``; closure repair keeps
# ``[autoload]`` in step with the scripts that exist so the build boots.
_CANONICAL_AUTOLOADS = (
    ("EventBus", "scripts/autoloads/event_bus.gd"),
    ("HeatSystem", "scripts/autoloads/heat_system.gd"),
    ("ForgeManager", "scripts/autoloads/forge_manager.gd"),
    ("GameState", "scripts/autoloads/game_state.gd"),
    ("Jeeves", "scripts/autoloads/jeeves.gd"),
    ("InputBind", "scripts/autoloads/input_bind.gd"),
)
_MAIN_SCENE = "scenes/levels/run_level.tscn"
# Content checks in ``gdscript_check`` that are fixed by restoring the
# canonical file wholesale (the scaffold owns these contracts).
_CANONICAL_CONTENT_FIXES = {
    "player never calls move_and_slide": "scripts/player/player_controller.gd",
    "player never talks to HeatSystem": "scripts/player/player_controller.gd",
    "GameState has no enter_room": "scripts/autoloads/game_state.gd",
    "InputBind never binds KEY_A": "scripts/autoloads/input_bind.gd",
    "player.tscn has no Camera2D": "scenes/player.tscn",
}
_LEVEL_REFS = (
    ("run_level.tscn never instances the player PackedScene", "res://scenes/player.tscn", "3", "Player"),
    ("run_level.tscn never instances Door packed scenes", "res://scenes/door.tscn", "7", "Door"),
)
_MAX_CLOSURE_PASSES = 6


def attempt_repair(
    files: Mapping[str, str],
    *,
    request: str = "",
    root=None,
    evidence: Dict[str, Any] | None = None,
    mode: str = "apply",
    pack: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """One bounded, policy-gated repair pass over an emitted Godot project.

    ``mode="apply"`` (default) applies deterministic repairs and re-verifies:
    targeted script patching (extends / entry point / unsafe calls), project
    closure (main scene, ``[autoload]`` registration) and restoration of
    missing or contract-breaking files from the canonical era scaffold.

    ``mode="suggest"`` plans exactly the same repairs but applies none: files
    come back unchanged, ``changed`` is 0 and every action carries
    ``applied: 0`` (the #2006 suggest-only contract, now an explicit opt-in).
    """
    if mode not in REPAIR_MODES:
        raise ValueError(f"repair mode must be one of {REPAIR_MODES}, got {mode!r}")
    if not isinstance(files, Mapping) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in files.items()):
        raise ValueError("files must map paths to source")
    gate = repair_enabled_for("forge", root=root)
    if not gate:
        return {"kind": "forge-repair-attempt", "ok": 0, "surface": "forge", "mode": mode, "reason": "repair-disabled", "actions": [], "changed": 0, "stored_prose": 0, "files": dict(files)}
    
    # Lazy: forge_verifier imports skeleton.forge.gdscript_check, whose package
    # __init__ imports this module — a top-level import is circular.
    from skeleton.intelligence.forge_verifier import ForgeVerifier

    threshold = threshold_for("forge", root=root, fallback=0.7)
    verifier = ForgeVerifier(accept_at=threshold, gd_accept_at=threshold, root=root)
    before = verifier.verify(files, request=request)
    report = before.to_dict()
    if before.accepted:
        planned, actions, weakest = dict(files), [], ""
    else:
        weakest = _select_target(report, evidence or {}) or before.weakest_path or ""
        planned, actions = _plan_repairs(files, report, weakest=weakest, root=root, pack=pack)
    changed_paths = sorted(p for p in set(planned) | set(files) if planned.get(p) != files.get(p))
    if mode == "suggest":
        result = {
            "kind": "forge-repair-attempt",
            "mode": "suggest",
            "ok": int(before.accepted),
            "surface": "forge",
            "reason": str(before.reason),
            "weakest_path": str(before.weakest_path or ""),
            "before": report,
            "after": report,
            "actions": [dict(a, applied=0) for a in actions],
            "proposed_paths": changed_paths,
            "changed": 0,
            "targeted_path": weakest,
            "stored_prose": 0,
            "files": dict(files),
        }
    else:
        after = verifier.verify(planned, request=request) if actions else before
        result = {
            "kind": "forge-repair-attempt",
            "mode": "apply",
            "ok": int(after.accepted),
            "surface": "forge",
            "reason": str(after.reason),
            "weakest_path": str(after.weakest_path or before.weakest_path or ""),
            "before": report,
            "after": after.to_dict(),
            "actions": [dict(a, applied=1) for a in actions],
            "changed_paths": changed_paths,
            "changed": int(bool(actions)),
            "targeted_path": weakest,
            "stored_prose": 0,
            "files": planned,
        }
    record = {k: v for k, v in result.items() if k != "files"}
    record["attempt_kind"] = record.pop("kind")
    record["kind"] = "repair"
    record["metadata"] = {
        "repair": 1,
        "mode": mode,
        "changed": int(bool(result["changed"])),
        "before_reason": str(report.get("reason") or ""),
        "after_reason": str((result.get("after") or {}).get("reason") or ""),
        "actions": len(result["actions"]),
    }
    append_repair(record, root=root)
    return result


def _plan_repairs(
    files: Mapping[str, str],
    report: Dict[str, Any],
    *,
    weakest: str,
    root=None,
    pack: Mapping[str, Any] | None = None,
) -> tuple[Dict[str, str], List[Dict[str, Any]]]:
    fixed = dict(files)
    actions: List[Dict[str, Any]] = []
    if weakest.endswith(".gd") and weakest in fixed and repair_class_enabled("script_patch", root=root):
        patched, notes = _patch_script(fixed[weakest])
        if patched != fixed[weakest]:
            fixed[weakest] = patched
            actions.append({"path": weakest, "class": "script_patch", "action": "patched targeted script once", "notes": notes})
    if report.get("project_issues") and repair_class_enabled("project_closure", root=root):
        _close_project(fixed, actions, root=root, pack=pack)
    return fixed, actions


def _patch_script(src: str) -> tuple[str, List[str]]:
    from skeleton.intelligence.forge_verifier import _UNSAFE

    notes: List[str] = []
    lines = src.split("\n")
    out: List[str] = []
    for line in lines:
        if _UNSAFE.search(line) and not line.lstrip().startswith("#"):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}# {line.lstrip()}")
            out.append(f"{indent}pass  # forge-repair: unsafe call neutralised")
            notes.append("neutralised unsafe call")
        else:
            out.append(line)
    text = "\n".join(out)
    if "extends " not in "\n".join(text.split("\n")[:5]):
        text = "extends Node\n" + text
        notes.append("added extends Node")
    if "func " not in text:
        text = text.rstrip("\n") + "\n\nfunc _ready() -> void:\n    pass  # forge-repair: seeded entry point\n"
        notes.append("seeded _ready entry point")
    return text, notes


def _canonical_files(files: Mapping[str, str], pack: Mapping[str, Any] | None) -> Dict[str, str]:
    import re

    title = "FORGE-RUN"
    match = re.search(r'config/name="([^"]*)"', files.get("project.godot", ""))
    if match and match.group(1).strip():
        title = match.group(1).strip()
    return _canonical_emit(dict(pack) if pack else _compile_era("extraction_now"), title=title)


def _ensure_section_line(project: str, section: str, line: str) -> str:
    header = f"[{section}]"
    if header in project:
        head, _, tail = project.partition(header)
        return f"{head}{header}\n{line}{tail}" if tail.startswith("\n") else f"{head}{header}\n{line}\n{tail}"
    return project.rstrip("\n") + f"\n\n{header}\n{line}\n"


def _close_project(fixed: Dict[str, str], actions: List[Dict[str, Any]], *, root=None, pack=None) -> None:
    from skeleton.forge.gdscript_check import check_files

    canonical: Dict[str, str] | None = None

    def canon() -> Dict[str, str]:
        nonlocal canonical
        if canonical is None:
            canonical = _canonical_files(fixed, pack)
        return canonical

    stub_ok = repair_class_enabled("scene_stub", root=root)
    project = fixed.get("project.godot")
    if project is None:
        if not stub_ok:
            return
        fixed["project.godot"] = canon()["project.godot"]
        actions.append({"path": "project.godot", "class": "scene_stub", "action": "restored missing project.godot from canonical scaffold"})
    else:
        if "config_version=5" not in project:
            project = "config_version=5\n" + project
            actions.append({"path": "project.godot", "class": "project_closure", "action": "declared Godot 4 config_version=5"})
        if "run/main_scene=" not in project:
            project = _ensure_section_line(project, "application", f'run/main_scene="res://{_MAIN_SCENE}"')
            actions.append({"path": "project.godot", "class": "project_closure", "action": "restored main scene entry"})
        if 'EventBus="*res://scripts/autoloads/event_bus.gd"' not in project:
            project = _ensure_section_line(project, "autoload", 'EventBus="*res://scripts/autoloads/event_bus.gd"')
            actions.append({"path": "project.godot", "class": "project_closure", "action": "restored EventBus autoload"})
        fixed["project.godot"] = project
    if not stub_ok:
        return

    for _ in range(_MAX_CLOSURE_PASSES):
        progressed = False
        for issue in check_files(fixed):
            path = _missing_path(issue)
            if path and path not in fixed and path in canon():
                fixed[path] = canon()[path]
                actions.append({"path": path, "class": "scene_stub", "action": "restored missing file from canonical scaffold", "issue": issue})
                progressed = True
                continue
            fix_path = _CANONICAL_CONTENT_FIXES.get(issue)
            if fix_path and fix_path in canon() and fixed.get(fix_path) != canon()[fix_path]:
                fixed[fix_path] = canon()[fix_path]
                actions.append({"path": fix_path, "class": "scene_stub", "action": "replaced contract-breaking file with canonical scaffold", "issue": issue})
                progressed = True
                continue
            if issue.startswith("run_level.tscn") and _MAIN_SCENE in fixed:
                if _patch_level(fixed, issue, canon()):
                    actions.append({"path": _MAIN_SCENE, "class": "scene_stub", "action": "restored level instance", "issue": issue})
                    progressed = True
        # Register canonical autoload singletons whose scripts now exist.
        project = fixed.get("project.godot", "")
        for name, script in _CANONICAL_AUTOLOADS:
            entry = f'{name}="*res://{script}"'
            if script in fixed and entry not in project:
                project = _ensure_section_line(project, "autoload", entry)
                actions.append({"path": "project.godot", "class": "project_closure", "action": f"registered {name} autoload"})
                progressed = True
        fixed["project.godot"] = project
        if not progressed:
            break


def _missing_path(issue: str) -> str:
    for prefix in ("required ", "main scene missing: "):
        if issue.startswith(prefix):
            return issue[len(prefix):].replace(" missing", "").strip()
    if issue.startswith("autoload ") and " missing file " in issue:
        return issue.split(" missing file ", 1)[1].strip()
    if " references missing " in issue:
        return issue.split(" references missing ", 1)[1].strip()
    return ""


def _patch_level(fixed: Dict[str, str], issue: str, canonical: Mapping[str, str]) -> bool:
    level = fixed[_MAIN_SCENE]
    if issue == "run_level.tscn does not instance Room_r00":
        if "Room_r00" in level:
            return False
        fixed[_MAIN_SCENE] = level.rstrip("\n") + '\n[node name="Room_r00" type="Node2D" parent="."]\n'
        return True
    for check, res_path, rid, node in _LEVEL_REFS:
        if issue != check:
            continue
        if f'id="{rid}"' in level and res_path not in level:
            # Resource id already taken by something else: the scaffold's
            # level is the only coherent fix.
            fixed[_MAIN_SCENE] = canonical[_MAIN_SCENE]
            return True
        lines = level.rstrip("\n").split("\n")
        ext = f'[ext_resource type="PackedScene" path="{res_path}" id="{rid}"]'
        if res_path not in level:
            # ext_resources must precede the first node: insert after header
            # and any existing ext_resource lines.
            at = 1 if lines and lines[0].startswith("[gd_scene") else 0
            while at < len(lines) and lines[at].startswith("[ext_resource"):
                at += 1
            lines.insert(at, ext)
        parent = "Room_r00" if "Room_r00" in level else "."
        lines.append(f'[node name="{node}" parent="{parent}" instance=ExtResource("{rid}")]')
        fixed[_MAIN_SCENE] = "\n".join(lines) + "\n"
        return True
    return False


def _select_target(before: Dict[str, Any], evidence: Dict[str, Any]) -> str:
    top = list(evidence.get("top_file_reports") or [])
    for item in top:
        if item.get("hard_issues") and item.get("path"):
            return str(item["path"])
    for item in top:
        if item.get("path"):
            return str(item["path"])
    return str(before.get("weakest_path") or "")


def _targets(failure: Dict[str, Any]) -> List[Dict[str, Any]]:
    reason = failure.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return []
    weakest = failure.get("weakest_path") if isinstance(failure.get("weakest_path"), str) else ""
    summary = dict(failure.get("summary") or {})
    evidence = dict(failure.get("evidence") or {})
    top = list(evidence.get("top_file_reports") or [])
    targets: List[Dict[str, Any]] = []
    for item in top:
        if item.get("hard_issues") and isinstance(item.get("path"), str) and item["path"]:
            targets.append({"target": item["path"], "action": "clear hard verification failures first"})
    if reason == "project_closure":
        targets.append({"target": "project graph", "action": "restore missing required files or references"})
    if reason in {"unsafe_code", "low_score"} and weakest:
        targets.append({"target": weakest, "action": "repair weakest emitted file first"})
    blocking = summary.get("blocking_issues")
    if isinstance(blocking, int) and not isinstance(blocking, bool) and blocking > 0:
        targets.append({"target": "blocking issues", "action": "clear hard verification failures before soft tuning"})
    return targets


def polish_artefact(
    item: Mapping[str, Any],
    *,
    root=None,
    max_rounds: int = 3,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages=(),
    regions=(),
    era: str | None = None,
    artefact_id: str = "",
    use_file_repair: bool = True,
) -> Dict[str, Any]:
    """Bounded forge quality polish loop (Prood forge_quality / polish surface).

    Composes ``forge_quality.polish_loop`` with optional ``attempt_repair`` on
    embedded file maps. Does not rewrite VerificationLoop.
    """
    from skeleton.forge.forge_quality import polish_loop

    repair_fn = attempt_repair if use_file_repair else None
    return polish_loop(
        item,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
        max_rounds=max_rounds,
        persist=True,
        artefact_id=artefact_id,
        root=root,
        repair_files=repair_fn,
    )
