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


def dispatch(cmd: str, rest: List[str]) -> int | None:
    table = {
        "spec": _cmd_spec, "emit": _cmd_emit, "doctor": _cmd_doctor, "turn": _cmd_turn,
        "compose": _cmd_compose, "nexus": _cmd_nexus, "packtree": _cmd_packtree,
        "bundles": _cmd_bundles, "catalog": _cmd_catalog, "sim": _cmd_sim,
        "lab": _cmd_lab, "campus": _cmd_campus, "flesh": _cmd_flesh,
        "world": _cmd_world, "warena": _cmd_warena, "monte": _cmd_monte,
        "bundle": _cmd_bundle, "laws": _cmd_laws, "hunt": _cmd_hunt,
        "wave4": _cmd_wave4, "backlog": _cmd_backlog, "wave5": _cmd_wave5,
        "wave6": _cmd_wave6, "wave7": _cmd_wave7, "wave8": _cmd_wave8,
        "wave9": _cmd_wave9, "wave10": _cmd_wave10, "wave11": _cmd_wave11,
        "wave12": _cmd_wave12, "wave13": _cmd_wave13, "wave14": _cmd_wave14,
    }
    fn = table.get(cmd)
    return None if fn is None else fn(rest)


def _cmd_spec(rest: List[str]) -> int:
    from skeleton.game.spec import compile_spec
    vision = " ".join(part for part in rest if part != "--seed" and not str(part).isdigit())
    vision = vision.strip() or "NEXUS-EXTRACT heat extract #807"
    try:
        payload = compile_spec(vision)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "fields": payload["fields"], "conflicts": payload["conflicts"], "era": payload["reference"]["era"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_emit(_rest: List[str]) -> int:
    from skeleton.game.emit_pack import default_tree, validate_emit
    try:
        payload = validate_emit(default_tree())
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "valid": payload["valid"], "missing": payload["missing"], "godot_binary": payload["godot_binary"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_doctor(rest: List[str]) -> int:
    from skeleton.game.doctor import doctor
    try:
        payload = doctor({"fun": 0.4, "clarity": 0.7, "feasibility": 0.6, "originality": 0.65}, seed=_seed(rest))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "axis": payload["axis"], "retune": payload["retune"], "after_min": payload["after"]["min"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_turn(rest: List[str]) -> int:
    from skeleton.game.turn_engine import play
    try:
        payload = play(seed=_seed(rest), ticks=20)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "ticks": payload["ticks"], "tokens": payload["tokens"], "extract_count": payload["extract_count"], "warp_count": payload["warp_count"], "passed": payload["passed"], "sota_ready": False, "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_compose(rest: List[str]) -> int:
    from skeleton.game.compose import compose
    try:
        payload = compose(seed=_seed(rest))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": payload["digest"], "era": payload["era"], "turn_passed": payload["turn_passed"], "arena_evidence": payload["arena_evidence"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_nexus(rest: List[str]) -> int:
    from skeleton.game.nexus_sim import simulate
    try:
        payload = simulate(seed=_seed(rest), ticks=32)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": payload["digest"], "extracted": payload["extracted"], "tokens": payload["tokens"], "passed": payload["passed"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
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
    print(json.dumps({"ok": True, "n": payload["n"], "spec": payload["spec"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_catalog(_rest: List[str]) -> int:
    from skeleton.game.catalog_index import census
    try:
        payload = census()
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "modules": payload["modules"], "n": payload["n"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_sim(rest: List[str]) -> int:
    from skeleton.game.sim_loop import play
    try:
        payload = play(seed=_seed(rest))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": payload["digest"], "route": payload["route"], "quests_done": payload["quests_done"], "combat_winner": payload["combat_winner"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_lab(rest: List[str]) -> int:
    from skeleton.game.lab_sim import play
    try:
        payload = play(seed=_seed(rest), rooms=8)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": payload["digest"], "cycles": payload["cycles"], "opened": payload["opened"], "alert": payload["alert"], "extract_count": payload["extract_count"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_campus(rest: List[str]) -> int:
    from skeleton.game.campus_index import run_campus
    try:
        payload = run_campus(_seed(rest))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "rooms": payload.get("rooms"), "alerts": payload.get("alerts"), "sota_ready": payload.get("sota_ready", False), "stored_prose": payload.get("stored_prose", 0)}, indent=2))
    return 0


def _cmd_flesh(rest: List[str]) -> int:
    from skeleton.game.flesh_sim import play
    try:
        payload = play(seed=_seed(rest))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": payload["digest"], "floors": payload["floors"], "extract_count": payload["extract_count"], "saved": payload["saved"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_world(rest: List[str]) -> int:
    from skeleton.game.world_tick import play
    try:
        payload = play(seed=_seed(rest), ticks=16)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": payload["digest"], "floors": payload["floors"], "contacts": payload["contacts"], "extract_count": payload["extract_count"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_warena(rest: List[str]) -> int:
    from skeleton.game.world_arena import compare
    seed = _seed(rest)
    try:
        payload = compare(seed_a=seed, seed_b=seed, ticks=16)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "match": payload["match"], "digest_a": payload["digest_a"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_monte(rest: List[str]) -> int:
    from skeleton.game.world_arena import monte
    try:
        payload = monte(seed=_seed(rest), n=4, ticks=16)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "unique_digests": payload["unique_digests"], "extracts": payload["extracts"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_bundle(rest: List[str]) -> int:
    from skeleton.game.world_bundle import bundle
    try:
        payload = bundle(seed=_seed(rest))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": payload["digest"], "path_len": payload["path_len"], "monte": payload["monte"], "extract_count": payload["extract_count"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_laws(rest: List[str]) -> int:
    from skeleton.game.law_composer import play
    try:
        payload = play(seed=_seed(rest))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": payload["digest"], "enc_done": payload["enc_done"], "ledger": payload["ledger"], "extract_count": payload["extract_count"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_hunt(rest: List[str]) -> int:
    from skeleton.game.hunt_field import play
    try:
        payload = play(seed=_seed(rest), ticks=16)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": payload["digest"], "hunters": payload["hunters"], "contacts": payload["contacts"], "extract_count": payload["extract_count"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_wave4(rest: List[str]) -> int:
    from skeleton.game.wave4_play import play
    try:
        payload = play(seed=_seed(rest))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": payload["digest"], "packs": payload["packs"], "extract_count": payload["extract_count"], "sota_ready": payload["sota_ready"], "stored_prose": payload["stored_prose"]}, indent=2))
    return 0


def _cmd_backlog(rest: List[str]) -> int:
    from skeleton.game.backlog_more import play as more
    from skeleton.game.backlog_play import play
    seed = _seed(rest)
    try:
        first = play(seed=seed)
        second = more(seed=seed, digest=str(first.get("digest") or ""))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": first["digest"], "more": second["digest"], "extract_count": first["extract_count"], "saved": second["saved"], "sota_ready": False, "stored_prose": 0}, indent=2))
    return 0


def _cmd_wave5(rest: List[str]) -> int:
    from skeleton.game.wave5_more import play as more
    from skeleton.game.wave5_play import play
    seed = _seed(rest)
    try:
        first = play(seed=seed)
        second = more(seed=seed)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": first["digest"], "more": second["digest"], "packs": first["packs"], "extract_count": first["extract_count"], "sota_ready": False, "stored_prose": 0}, indent=2))
    return 0


def _cmd_wave6(rest: List[str]) -> int:
    from skeleton.game.wave6_more import play as more
    from skeleton.game.wave6_play import play
    seed = _seed(rest)
    try:
        first = play(seed=seed)
        second = more(seed=seed)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": first["digest"], "more": second["digest"], "packs": first["packs"], "sota_ready": False, "stored_prose": 0}, indent=2))
    return 0


def _cmd_wave7(rest: List[str]) -> int:
    from skeleton.game.wave7_more import play as more
    from skeleton.game.wave7_play import play
    seed = _seed(rest)
    try:
        first = play(seed=seed)
        second = more(seed=seed, digest=str(first.get("digest") or "d"))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": first["digest"], "more": second["digest"], "packs": first["packs"], "sota_ready": False, "stored_prose": 0}, indent=2))
    return 0


def _cmd_wave8(rest: List[str]) -> int:
    from skeleton.game.wave8_more import play as more
    from skeleton.game.wave8_play import play
    seed = _seed(rest)
    try:
        first = play(seed=seed)
        second = more(seed=seed)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": first["digest"], "more": second["digest"], "packs": first["packs"], "sota_ready": False, "stored_prose": 0}, indent=2))
    return 0


def _cmd_wave9(rest: List[str]) -> int:
    from skeleton.game.wave9_more import play as more
    from skeleton.game.wave9_play import play
    seed = _seed(rest)
    try:
        first = play(seed=seed)
        second = more(seed=seed, digest=str(first.get("digest") or "d"))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": first["digest"], "more": second["digest"], "packs": first["packs"], "sota_ready": False, "stored_prose": 0}, indent=2))
    return 0


def _cmd_wave10(rest: List[str]) -> int:
    from skeleton.game.wave10_more import play as more
    from skeleton.game.wave10_play import play
    seed = _seed(rest)
    try:
        first = play(seed=seed)
        second = more(seed=seed)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": first["digest"], "more": second["digest"], "packs": first["packs"], "sota_ready": False, "stored_prose": 0}, indent=2))
    return 0


def _cmd_wave11(rest: List[str]) -> int:
    from skeleton.game.wave11_more import play as more
    from skeleton.game.wave11_play import play
    seed = _seed(rest)
    try:
        first = play(seed=seed)
        second = more(seed=seed, digest=str(first.get("digest") or "d"))
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": first["digest"], "more": second["digest"], "packs": first["packs"], "sota_ready": False, "stored_prose": 0}, indent=2))
    return 0


def _cmd_wave12(rest: List[str]) -> int:
    from skeleton.game.wave12_more import play as more
    from skeleton.game.wave12_play import play
    seed = _seed(rest)
    try:
        first = play(seed=seed)
        second = more(seed=seed)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": first["digest"], "more": second["digest"], "packs": first["packs"], "sota_ready": False, "stored_prose": 0}, indent=2))
    return 0


def _cmd_wave13(rest: List[str]) -> int:
    from skeleton.game.wave13_more import play as more
    from skeleton.game.wave13_play import play
    seed = _seed(rest)
    try:
        first = play(seed=seed)
        second = more(seed=seed)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": first["digest"], "more": second["digest"], "packs": first["packs"], "sota_ready": False, "stored_prose": 0}, indent=2))
    return 0


def _cmd_wave14(rest: List[str]) -> int:
    from skeleton.game.wave14_more import play as more
    from skeleton.game.wave14_play import play
    seed = _seed(rest)
    try:
        first = play(seed=seed)
        second = more(seed=seed)
    except Exception as exc:
        return _fail(exc)
    print(json.dumps({"ok": True, "digest": first["digest"], "more": second["digest"], "packs": first["packs"], "sota_ready": False, "stored_prose": 0}, indent=2))
    return 0
