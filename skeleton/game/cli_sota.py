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


def _cmd_turn(rest: List[str]) -> int:
    from skeleton.game.turn_engine import play

    try:
        payload = play(seed=_seed(rest), ticks=20)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({
        "ok": True,
        "ticks": payload["ticks"],
        "tokens": payload["tokens"],
        "extract_count": payload["extract_count"],
        "warp_count": payload["warp_count"],
        "passed": payload["passed"],
        "sota_ready": False,
        "stored_prose": payload["stored_prose"],
    }, indent=2))
    return 0


def _cmd_compose(rest: List[str]) -> int:
    from skeleton.game.compose import compose

    try:
        payload = compose(seed=_seed(rest))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({
        "ok": True,
        "digest": payload["digest"],
        "era": payload["era"],
        "turn_passed": payload["turn_passed"],
        "arena_evidence": payload["arena_evidence"],
        "sota_ready": payload["sota_ready"],
        "stored_prose": payload["stored_prose"],
    }, indent=2))
    return 0


def _cmd_nexus(rest: List[str]) -> int:
    from skeleton.game.nexus_sim import simulate

    try:
        payload = simulate(seed=_seed(rest), ticks=32)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({
        "ok": True,
        "digest": payload["digest"],
        "extracted": payload["extracted"],
        "tokens": payload["tokens"],
        "passed": payload["passed"],
        "sota_ready": payload["sota_ready"],
        "stored_prose": payload["stored_prose"],
    }, indent=2))
    return 0


def _cmd_packtree(rest: List[str]) -> int:
    from skeleton.game.emit_tree import build, public_card

    try:
        payload = public_card(build(seed=_seed(rest)))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_bundles(rest: List[str]) -> int:
    from skeleton.game.zip_bundle import bundles

    try:
        payload = bundles(seed=_seed(rest))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({
        "ok": True,
        "n": payload["n"],
        "spec": payload["spec"],
        "sota_ready": payload["sota_ready"],
        "stored_prose": payload["stored_prose"],
    }, indent=2))
    return 0


def _cmd_catalog(_rest: List[str]) -> int:
    from skeleton.game.catalog_index import census

    try:
        payload = census()
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({
        "ok": True,
        "modules": payload["modules"],
        "n": payload["n"],
        "sota_ready": payload["sota_ready"],
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
    if cmd == "turn":
        return _cmd_turn(rest)
    if cmd == "compose":
        return _cmd_compose(rest)
    if cmd == "nexus":
        return _cmd_nexus(rest)
    if cmd == "packtree":
        return _cmd_packtree(rest)
    if cmd == "bundles":
        return _cmd_bundles(rest)
    if cmd == "catalog":
        return _cmd_catalog(rest)
    return None
