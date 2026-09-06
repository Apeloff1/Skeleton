"""P0 spine — questionnaire → spec → Godot slice → walk score → report.

Day verb calls forge(). Cards stay lean. Files live under root/game.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


SCHEMA = "2026.09.06-gamespec"


def spec_from_answers(answers: Optional[Dict[str, Any]] = None, *, cue: str = "") -> Dict[str, Any]:
    from skeleton.context.questionnaire import intake
    raw = dict(answers or {})
    if cue and "vision" not in raw:
        raw.setdefault("theme", "sci-fi")
    result = intake(raw)
    spec = {
        "kind": "game-spec",
        "schema": SCHEMA,
        "vision": result.vision,
        "era": result.era,
        "genre": result.genre,
        "platform": result.target_platform or "godot",
        "pillars": [
            raw.get("combat") or "tactical",
            raw.get("progression") or "skill-tree",
            raw.get("perspective") or "third-person",
        ],
        "cue": str(cue or "")[:240],
        "conflicts": [],
        "stored_prose": 0,
    }
    if spec["platform"] not in {"godot", "web", "data"}:
        spec["conflicts"].append("platform")
        spec["platform"] = "godot"
    return spec


def write_spec(spec: Dict[str, Any], root: Optional[Path] = None) -> Path:
    base = Path(root) if root else Path(".")
    path = base / "game" / "data" / "spec.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return path


def slice_godot(spec: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    from skeleton.forge.eras import compile_era
    from skeleton.forge.godot_emit import emit_godot
    from skeleton.forge.projector import write_project
    from skeleton.forge.world import generate_rooms

    pack = compile_era(str(spec.get("era") or "extraction_now"))
    graph = generate_rooms(pack, seed=str(spec.get("cue") or spec.get("era") or "day"))
    files = emit_godot(pack, title=str(spec.get("genre") or "FORGE")[:32])
    files["data/spec.json"] = json.dumps(spec, indent=2)
    files["data/cockpit.json"] = json.dumps(
        {"kind": "cockpit", "era": spec.get("era"), "stored_prose": 0}, indent=2
    )
    files["data/world.json"] = json.dumps(
        {"kind": "world", "rooms": graph.get("rooms") if isinstance(graph, dict) else graph, "stored_prose": 0},
        indent=2, default=str,
    )
    game_root = (Path(root) if root else Path(".")) / "game"
    manifest = write_project(game_root, files, overwrite=True, meta={"schema": SCHEMA, "era": spec.get("era")})
    return {"kind": "godot-slice", "root": str(game_root), "n": manifest.get("count"), "pack": pack, "graph": graph, "stored_prose": 0}


def score(pack: Dict[str, Any], graph: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.forge.walk import walk_graph
    report = walk_graph(pack, graph)
    card = report.to_dict() if hasattr(report, "to_dict") else dict(report)
    card["kind"] = "headless-score"
    card["time_to_fun"] = card.get("t") or 0
    card["stored_prose"] = 0
    return card


def report(spec: Dict[str, Any], slice_card: Dict[str, Any], score_card: Dict[str, Any],
           *, root: Optional[Path] = None, cue: str = "", mass: float = 0.0,
           field_pct: float = 0.0) -> Path:
    base = Path(root) if root else Path(".")
    path = base / "game" / "reports" / "build_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# build_report",
        "",
        f"- schema: {SCHEMA}",
        f"- era: {spec.get('era')}",
        f"- genre: {spec.get('genre')}",
        f"- vision: {spec.get('vision')}",
        f"- cue: {cue or spec.get('cue') or ''}",
        f"- files: {slice_card.get('n')}",
        f"- passed: {score_card.get('passed')}",
        f"- t: {score_card.get('t')}",
        f"- hops: {score_card.get('hops')}",
        f"- fights: {score_card.get('fights')}",
        f"- mass: {mass}",
        f"- field_pct: {field_pct}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def forge(org=None, *, answers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    root = Path(getattr(org, "root", None) or ".")
    cue = ""
    try:
        from skeleton.organism.rotors import card as rotor_card
        cue = str(rotor_card(root).get("cue") or "")
    except Exception:
        cue = ""
    spec = spec_from_answers(answers, cue=cue)
    spec_path = write_spec(spec, root)
    sl = slice_godot(spec, root)
    pack = sl.pop("pack", {})
    graph = sl.pop("graph", {})
    sc = {"kind": "headless-score", "passed": 0, "stored_prose": 0}
    try:
        sc = score(pack, graph)
    except Exception as exc:
        sc["err"] = type(exc).__name__
    field_pct = 0.0
    try:
        from skeleton.organism.runloop import bound_card
        field_pct = float(bound_card(root).get("field_pct") or 0)
    except Exception:
        field_pct = 0.0
    rep = report(spec, sl, sc, root=root, cue=cue, field_pct=field_pct)
    return {
        "kind": "game-forge-day",
        "spec": str(spec_path),
        "game": sl.get("root"),
        "files": sl.get("n"),
        "passed": int(bool(sc.get("passed"))),
        "report": str(rep),
        "era": spec.get("era"),
        "stored_prose": 0,
    }
