"""Seal a 20-minute SOTA compose. Every plane, one digest. sota_ready stays false."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.game.approval import stamp
from skeleton.game.arena import run_arena
from skeleton.game.build_report import report
from skeleton.game.conductor import execute
from skeleton.game.cut import cut, plan_sees
from skeleton.game.doctor import doctor
from skeleton.game.encounters import pack_tables
from skeleton.game.handoff import offer, resolve, session as handoff_session
from skeleton.game.provenance import meta
from skeleton.game.questionnaire import fill
from skeleton.game.release_graph import graph
from skeleton.game.turn_engine import play


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compose(*, seed: int = 8847291, vision: str = "NEXUS-EXTRACT heat extract #807") -> dict[str, Any]:
    overlay = cut("extraction_now")
    planned = plan_sees(overlay)
    sheet = fill(vision)
    approved = stamp(vision, actor="operator", approve=not sheet["conflicts"])
    run = execute(seed=int(seed), vision=vision, forges=4)
    turns = play(seed=int(seed), ticks=20)
    tables = pack_tables(int(seed))
    treated = doctor(
        {"fun": 0.55, "clarity": 0.61, "feasibility": 0.48, "originality": 0.7},
        seed=int(seed),
    )
    offered = offer(from_agent="extract", to_agent="heat", verb="offer")
    accepted = resolve(offered, "accept")
    mesh = handoff_session([offered, accepted])
    marks = [
        meta(path="data/spec.json", seed=int(seed), step="export", rotor="spec"),
        meta(path="reports/build_report.md", seed=int(seed), step="export", rotor="report"),
    ]
    tree = graph(
        [
            {"name": "spec", "body": {"fields": sheet["filled"]}},
            {"name": "turns", "body": {"ticks": turns["ticks"]}},
            {"name": "tables", "body": {"n": tables["n"]}},
        ]
    )
    exported = report(vision=vision, seed=int(seed), forges=4)
    arena = run_arena((int(seed), int(seed) + 1))
    body = {
        "kind": "sota_compose",
        "seed": int(seed),
        "era": planned["era"],
        "fields": sheet["filled"],
        "conflicts": sheet["conflicts"],
        "approval": approved["state"],
        "conductor_ok": bool(run.get("ok")),
        "turn_passed": bool(turns.get("passed")),
        "extract_count": turns["extract_count"],
        "warp_count": turns["warp_count"],
        "tokens": turns["tokens"],
        "tables": tables["n"],
        "doctor_axis": treated["axis"],
        "retune": treated["retune"],
        "handoff_accepted": mesh["accepted"],
        "provenance": len(marks),
        "release_root": tree["root"],
        "report_digest": exported["digest"],
        "arena_evidence": arena["evidence"],
        "sota_ready": False,
        "law": "batch_complete_is_not_sota",
        "stored_prose": 0,
    }
    body["digest"] = hashlib.sha256(_dumps(body).encode("utf-8")).hexdigest()
    body["ok"] = True
    return body
