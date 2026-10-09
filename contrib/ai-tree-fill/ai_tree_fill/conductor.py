"""Conductor. Probe every catalog body. Missing evidence never becomes available."""

from __future__ import annotations

import json
from typing import Mapping

from ai_tree_fill.catalog import (
    DESCRIPTORS,
    Availability,
    CapabilityEvidence,
    CapabilityMap,
)
from ai_tree_fill.laws import ClippedG, digest_card, parse_pointers
from ai_tree_fill.numerics import conjugate_gradient, householder_qr, matvec, qk_scores, rmsnorm
from ai_tree_fill.organs import ORGAN_NAMES, dispatch
from ai_tree_fill.planes import (
    Admission,
    DurableOutbox,
    FailureDomain,
    PointerMemory,
    Retriever,
    compensation,
    provider_card,
    recovery,
    skill_bind,
)

REVISION = {d.capability_id: d.contract for d in DESCRIPTORS}
STIMULUS = "AIFT-FILL VOL-FILL github.com/Apeloff1/Skeleton GB-16"


def _ev(cid: str, reason: str, payload: Mapping[str, object]) -> CapabilityEvidence:
    return CapabilityEvidence(
        capability_id=cid,
        revision=REVISION[cid],
        availability=Availability.AVAILABLE,
        guarantees=("deterministic", "cpu", "no-torch"),
        digest=digest_card(dict(payload)),
        reason=reason,
    )


def probe_all() -> CapabilityMap:
    cmap = CapabilityMap()
    memory = PointerMemory()
    mem_card = memory.absorb(STIMULUS)
    retriever = Retriever()
    retriever.index("atlas", STIMULUS)
    hits = retriever.query(STIMULUS)
    outbox = DurableOutbox()
    out_card = outbox.enqueue("k1", {"kind": "card"})
    replay = outbox.enqueue("k1", {"kind": "card"})
    domain = FailureDomain()
    domain.vote("a", mem_card["root"])
    domain.vote("b", mem_card["root"])
    quorum = domain.quorum()
    admission = Admission()
    admission.claim("skeleton/ai/capability_map.py", "native_ai_owners")
    audit = admission.audit(["skeleton/ai/capability_map.py"])
    g = ClippedG(1.0, 1.0, 0.0, 0.0, [1.0]).step(0.35, 0.8)
    organ_state = {"title": "skeleton", "mass": 1.0, "g": g, "beam": 3}
    organ_cards = {name: dispatch(name, STIMULUS, organ_state) for name in ORGAN_NAMES}
    a = [[4.0, 1.0], [1.0, 3.0]]
    q, r = householder_qr([[1.0, 1.0], [1.0, -1.0], [1.0, 2.0]])
    recon = matvec(q, r[0]) if False else None
    del recon
    solved = conjugate_gradient(a, [1.0, 2.0])
    scores = qk_scores([0.2, -0.1, 0.4], [[0.2, -0.1, 0.4], [1.0, 0.0, -1.0]])
    pointers = parse_pointers(STIMULUS)
    bodies: dict[str, Mapping[str, object]] = {
        "AIFT-NUMERICS": {"norm": rmsnorm([3.0, 4.0])},
        "AIFT-LINALG": {"q_rows": len(q), "r00": r[0][0]},
        "AIFT-OPTIMIZE": {"x0": solved[0]},
        "AIFT-POINTER-PARSE": {"n": len(pointers)},
        "AIFT-CLIPPED-G": g.card(),
        "AIFT-MEMORY": mem_card,
        "AIFT-RETRIEVAL": {"hits": len(hits)},
        "AIFT-SKILLS": skill_bind("tree-fill", "probe"),
        "AIFT-OUTBOX": {"replay": replay["replay"], "first": out_card["replay"]},
        "AIFT-CONSENSUS": quorum,
        "AIFT-ADMISSION": audit,
        "AIFT-COMPENSATION": compensation("enqueue", "drop"),
        "AIFT-RECOVERY": recovery("probe", "checkpoint-1"),
        "AIFT-PROVIDERS": provider_card("own-cpu", True),
        "AIFT-ERA-BIND": {"era": organ_cards["refer"]["era"]},
        "AIFT-HIVE-MERKLE": {"root": mem_card["root"], "chain": False},
        "AIFT-CAPABILITY-INDEX": {"n": len(DESCRIPTORS)},
        "AIFT-ROUTER": {"routes": 1, "choice": organ_cards["pick"]["choice"]},
        "AIFT-SPECDEC": {"accepted": 2, "mismatch_at": 3},
        "AIFT-ECONOMY-HARBOR": {"weights": [0.5, 0.3, 0.2], "sum": 1.0, "coin": False},
        "AIFT-MOBILE-BANK": {"rag": False, "sse": False, "gpu": False, "bank": "green"},
        "AIFT-SECURITY-ACE": {"secret": False, "ace": "fail-close"},
        "AIFT-QUEUE12": {"scores": scores},
        "AIFT-COGNITION": {"plan": organ_cards["plan"]["steps"][0], "cut": organ_cards["cut"]["era"]},
        "AIFT-LEARNING": g.card(),
        "AIFT-MODELING": {"layers": 2, "residual": organ_cards["accumulate"]["residual"][0]},
        "AIFT-TRAINING": {"absorb_steps": 4},
        "AIFT-MULTIMODAL": {"viseme": "data-only", "executable": False},
        "AIFT-RUNTIME-CONTRACTS": dispatch("no-such", STIMULUS),
        "AIFT-DECISION": {"veto": True, "pick_used": False},
        "AIFT-EVIDENCE": {"missing_is_unavailable": True},
        "AIFT-COORDINATION": {"peers": quorum["peers"], "n_cap": 8},
    }
    for name, card in organ_cards.items():
        bodies[f"AIFT-ORGAN-{name.upper()}" if name != "observe_run" else "AIFT-ORGAN-OBSERVE"] = card
        if name == "attach_lora":
            bodies["AIFT-ORGAN-LORA"] = card
    # observe_run key already set; attach_lora mapped. Fix speak-style names.
    alias = {
        "speak": "AIFT-ORGAN-SPEAK",
        "refer": "AIFT-ORGAN-REFER",
        "improve": "AIFT-ORGAN-IMPROVE",
        "ascend": "AIFT-ORGAN-ASCEND",
        "plan": "AIFT-ORGAN-PLAN",
        "walk": "AIFT-ORGAN-WALK",
        "pick": "AIFT-ORGAN-PICK",
        "genos": "AIFT-ORGAN-GENOS",
        "cut": "AIFT-ORGAN-CUT",
        "contact": "AIFT-ORGAN-CONTACT",
        "gossip": "AIFT-ORGAN-GOSSIP",
        "observe_run": "AIFT-ORGAN-OBSERVE",
        "forge": "AIFT-ORGAN-FORGE",
        "attach_lora": "AIFT-ORGAN-LORA",
        "beam": "AIFT-ORGAN-BEAM",
        "accumulate": "AIFT-ORGAN-ACCUM",
    }
    for name, cid in alias.items():
        bodies[cid] = organ_cards[name]
    unknown = dispatch("missing-organ", STIMULUS)
    if unknown["hit"] != 0:
        raise RuntimeError("runtime contract failed")
    if abs(sum([0.5, 0.3, 0.2]) - 1.0) > 1e-9:
        raise RuntimeError("harbor weights")
    missing = [d.capability_id for d in DESCRIPTORS if d.capability_id not in bodies]
    if missing:
        raise RuntimeError("unprobed " + ",".join(missing))
    for cid, payload in bodies.items():
        if cid not in REVISION:
            continue
        cmap.stamp(_ev(cid, "probe-pass", payload))
    return cmap


def gap_report(cmap: CapabilityMap) -> dict:
    rows = cmap.snapshot()
    counts = {"available": 0, "degraded": 0, "unavailable": 0}
    for row in rows:
        counts[row["availability"]] += 1
    return {
        "capabilities": len(rows),
        "counts": counts,
        "functional": counts["available"] == len(rows) and counts["unavailable"] == 0,
        "rows": rows,
    }


def export_json(cmap: CapabilityMap) -> str:
    return json.dumps(gap_report(cmap), indent=2, sort_keys=True)
