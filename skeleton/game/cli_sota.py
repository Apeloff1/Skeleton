"""Extra SOTA CLI verbs. Keep __main__ dispatch thin."""

from __future__ import annotations

import json
from typing import List


def _seed(rest: List[str]) -> int:
    seed = 8847291
    i = 0
    while i < len(rest):
        if rest[i] == "--seed" and i + 1 < len(rest) and str(rest[i + 1]).isdigit():
            seed = int(rest[i + 1])
            i += 2
        else:
            i += 1
    return seed


def _fail(exc: Exception) -> int:
    print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
    return 2


def _cmd_spec(rest: List[str]) -> int:
    from skeleton.game.spec import compile_spec

    vision = " ".join(part for part in rest if part != "--seed" and not str(part).isdigit())
    vision = vision.strip() or "NEXUS-EXTRACT heat extract #807"
    try:
        payload = compile_spec(vision)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({
        "ok": True,
        "fields": payload["fields"],
        "conflicts": payload["conflicts"],
        "era": payload["reference"]["era"],
        "stored_prose": payload["stored_prose"],
    }, indent=2))
    return 0


def _cmd_emit(_rest: List[str]) -> int:
    from skeleton.game.emit_pack import default_tree, validate_emit

    try:
        payload = validate_emit(default_tree())
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({
        "ok": True,
        "valid": payload["valid"],
        "missing": payload["missing"],
        "godot_binary": payload["godot_binary"],
        "stored_prose": payload["stored_prose"],
    }, indent=2))
    return 0


def _cmd_doctor(rest: List[str]) -> int:
    from skeleton.game.doctor import doctor

    try:
        payload = doctor(
            {"fun": 0.4, "clarity": 0.7, "feasibility": 0.6, "originality": 0.65},
            seed=_seed(rest),
        )
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({
        "ok": True,
        "axis": payload["axis"],
        "retune": payload["retune"],
        "after_min": payload["after"]["min"],
        "stored_prose": payload["stored_prose"],
    }, indent=2))
    return 0


def dispatch(cmd: str, rest: List[str]) -> int | None:
    if cmd == "spec":
        return _cmd_spec(rest)
    if cmd == "emit":
        return _cmd_emit(rest)
    if cmd == "doctor":
        return _cmd_doctor(rest)
    return None
