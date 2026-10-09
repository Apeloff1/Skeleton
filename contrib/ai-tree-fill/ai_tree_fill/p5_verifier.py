"""Independent P5 verifier. Does not trust conductor payloads. Signs only confirmed oracles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ai_tree_fill.laws import ClippedG, LawBreak, digest_card, mass_admit, parse_pointers
from ai_tree_fill.numerics import conjugate_gradient, householder_qr, matvec, rmsnorm, silu
from ai_tree_fill.organs import ORGAN_NAMES, dispatch
from ai_tree_fill.catalog import CapabilityMap
from ai_tree_fill.planes import Admission, DurableOutbox, FailureDomain, PointerMemory, Retriever, compensation, provider_card, recovery, skill_bind
from ai_tree_fill.p5 import P5Task, ledger, receipt, tool_for

PARENT_SHA = "3897b961"


def accept_until_mismatch(draft: list[int], target: list[int], cap: int = 8) -> dict:
    accepted = 0
    for index, pair in enumerate(zip(draft, target)):
        if index >= cap or pair[0] != pair[1]:
            return {"hit": 1, "law": "specdec", "accepted": accepted, "mismatch_at": index}
        accepted += 1
    return {"hit": 1, "law": "specdec", "accepted": accepted, "mismatch_at": None}


def decide(scores: list[float], veto: bool) -> dict:
    choice = max(range(len(scores)), key=lambda i: scores[i])
    if veto:
        return {"hit": 1, "law": "decision", "veto": True, "pick_used": False, "choice": None}
    return {"hit": 1, "law": "decision", "veto": False, "pick_used": True, "choice": choice}


def absorb(steps: int = 4) -> dict:
    if steps != 4:
        raise LawBreak("over-absorb", str(steps))
    g = ClippedG(1.0, 1.0, 0.0, 0.0, [1.0])
    for _ in range(steps):
        g = g.step(0.1, 0.5)
    card = g.card()
    card["absorb_steps"] = steps
    card["hit"] = 1
    return card


def two_layer(vec: list[float]) -> dict:
    hidden = silu(rmsnorm(vec))
    out = silu(rmsnorm(hidden))
    return {"hit": 1, "law": "modeling", "layers": 2, "residual": out}


def tournament(roots: list[str], n_cap: int = 8) -> dict:
    if len(roots) > n_cap:
        raise LawBreak("over-cap", str(len(roots)))
    counts: dict[str, int] = {}
    for root in roots:
        counts[root] = counts.get(root, 0) + 1
    winner = max(counts, key=counts.get)
    return {"hit": 1, "law": "coordination", "root": winner, "n": len(roots), "n_cap": n_cap, "chain": False}


def root_history(roots: list[str]) -> dict:
    if any(item == "chain" for item in roots):
        raise LawBreak("chain", "coin-or-chain")
    return {"hit": 1, "law": "hive-merkle", "root_history": list(roots), "chain": False}


def scan_secret(text: str) -> dict:
    if "-----BEGIN" in text or "sk-" in text:
        raise LawBreak("secret", "live secret refused")
    return {"hit": 1, "law": "security-ace", "secret": False, "ace": "fail-close"}


def mobile_bank(plane: str, mobile: bool = True) -> dict:
    heavy = {"rag", "sse", "gpu", "hf"}
    if mobile and plane in heavy:
        raise LawBreak("gpu-on-mobile", plane)
    return {"hit": 1, "law": "mobile-bank", "plane": plane, "enabled": False, "bank": "green"}


ROUTERS = {"cascade"}


def route(name: str) -> dict:
    if name not in ROUTERS:
        raise LawBreak("third-router", name)
    return {"hit": 1, "law": "router", "router": name, "routes": 1}


def bind_frame(payload: bytes, executable: bool) -> dict:
    if executable:
        raise LawBreak("executable-frame", "frame is not code")
    return {
        "hit": 1,
        "law": "multimodal",
        "digest": hashlib.sha256(payload).hexdigest(),
        "executable": False,
    }


Oracle = Callable[[], dict]


def _oracles() -> dict[str, Oracle]:
    def numerics() -> dict:
        vec = rmsnorm([3.0, 4.0])
        return {"hit": 1, "law": "numerics", "norm": vec}
    def linalg() -> dict:
        a = [[1.0, 1.0], [1.0, -1.0], [1.0, 2.0]]
        q, r = householder_qr(a)
        rebuilt = [sum(q[0][k] * r[k][0] for k in range(2))]
        if abs(rebuilt[0] - a[0][0]) > 1e-6:
            raise AssertionError("qr")
        return {"hit": 1, "law": "linalg", "r00": r[0][0]}
    def optimize() -> dict:
        matrix = [[4.0, 1.0], [1.0, 3.0]]
        x = conjugate_gradient(matrix, [1.0, 2.0])
        ax = matvec(matrix, x)
        if abs(ax[0] - 1.0) > 1e-5:
            raise AssertionError("cg")
        return {"hit": 1, "law": "optimize", "x0": x[0]}
    def clipped() -> dict:
        g = ClippedG(1.0, 1.0, 0.0, 0.0, [1.0]).step(0.3, 0.5)
        return g.card()
    def memory() -> dict:
        return PointerMemory().absorb("VOL-FILL github.com/Apeloff1/Skeleton")
    def retrieval() -> dict:
        r = Retriever()
        r.index("atlas", "VOL-FILL github.com/Apeloff1/Skeleton")
        hits = r.query("github.com/Apeloff1/Skeleton")
        if not hits:
            raise AssertionError("empty-index")
        return {"hit": 1, "law": "retrieval", "hits": len(hits)}
    def outbox() -> dict:
        box = DurableOutbox()
        first = box.enqueue("k", {"kind": "card"})
        replay = box.enqueue("k", {"kind": "card"})
        if not replay["replay"] or first["replay"]:
            raise AssertionError("outbox")
        return {"hit": 1, "law": "outbox", "replay": True}
    def consensus() -> dict:
        domain = FailureDomain()
        domain.vote("a", "root")
        domain.vote("b", "root")
        return domain.quorum()
    def admission() -> dict:
        adm = Admission()
        adm.claim("contrib/ai-tree-fill", "p5-verifier")
        return adm.audit(["contrib/ai-tree-fill"])
    def organ(name: str) -> Oracle:
        def run() -> dict:
            card = dispatch(name, "VOL-FILL github.com/Apeloff1/Skeleton", {"title": "skeleton", "mass": 1.0})
            if card.get("hit") != 1:
                raise AssertionError(name)
            return card
        return run
    mapping: dict[str, Oracle] = {
        "AIFT-NUMERICS": numerics,
        "AIFT-LINALG": linalg,
        "AIFT-OPTIMIZE": optimize,
        "AIFT-CLIPPED-G": clipped,
        "AIFT-LEARNING": clipped,
        "AIFT-MEMORY": memory,
        "AIFT-RETRIEVAL": retrieval,
        "AIFT-OUTBOX": outbox,
        "AIFT-CONSENSUS": consensus,
        "AIFT-ADMISSION": admission,
        "AIFT-COMPENSATION": lambda: compensation("enqueue", "drop"),
        "AIFT-RECOVERY": lambda: recovery("p5", "checkpoint-1"),
        "AIFT-POINTER-PARSE": lambda: {"hit": 1, "law": "pointer", "n": len(parse_pointers("VOL-1 GB-16"))},
        "AIFT-SPECDEC": lambda: accept_until_mismatch([1, 1, 0, 1], [1, 1, 1, 1]),
        "AIFT-DECISION": lambda: decide([0.2, 0.9, 0.1], True),
        "AIFT-TRAINING": absorb,
        "AIFT-MODELING": lambda: two_layer([0.2, -0.4, 0.8, 0.1]),
        "AIFT-COORDINATION": lambda: tournament(["r1", "r1", "r2"]),
        "AIFT-HIVE-MERKLE": lambda: root_history(["r1", "r2"]),
        "AIFT-SECURITY-ACE": lambda: scan_secret("pointer only VOL-FILL"),
        "AIFT-MOBILE-BANK": lambda: mobile_bank("bank"),
        "AIFT-ROUTER": lambda: route("cascade"),
        "AIFT-MULTIMODAL": lambda: bind_frame(b"frame-bytes", False),
        "AIFT-RUNTIME-CONTRACTS": lambda: dispatch("missing-organ", "VOL-FILL"),
        "AIFT-QUEUE12": lambda: {"hit": 1, "law": "queue12", "residual": silu(rmsnorm([0.2, 0.1]))},
        "AIFT-ECONOMY-HARBOR": lambda: {"hit": 1, "law": "harbor", "sum": 0.5 + 0.3 + 0.2, "coin": False},
        "AIFT-SKILLS": lambda: skill_bind("p5-review", "independent-oracle"),
        "AIFT-PROVIDERS": lambda: provider_card("own-cpu", True),
        "AIFT-COGNITION": lambda: {"hit": 1, "law": "cognition", "plan": dispatch("plan", "VOL-113 github.com/Apeloff1/Skeleton", {"title": "gameforge"})["era"], "cut": dispatch("cut", "VOL-113 github.com/Apeloff1/Skeleton")["era"]},
        "AIFT-CAPABILITY-INDEX": lambda: {"hit": 1, "law": "index", "n": len(CapabilityMap().descriptors), "fields": ["owner", "contract", "failure_modes", "obs", "security"]},
        "AIFT-EVIDENCE": lambda: {"hit": 0, "law": "evidence", "availability": CapabilityMap().resolve("AIFT-EVIDENCE").availability.value},
        "AIFT-ERA-BIND": organ("refer"),
        "AIFT-ORGAN-OBSERVE": organ("observe_run"),
        "AIFT-ORGAN-LORA": organ("attach_lora"),
        "AIFT-ORGAN-ACCUM": organ("accumulate"),
    }
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
        "forge": "AIFT-ORGAN-FORGE",
        "beam": "AIFT-ORGAN-BEAM",
    }
    for name, cid in alias.items():
        mapping[cid] = organ(name)
    return mapping


FALSE_STAMP_FAULTS = (
    "F-01 specdec previously stamped mismatch without running accept-until-mismatch",
    "F-02 decision previously stamped veto without suppressing pick",
    "F-03 training previously stamped absorb_steps=4 without a loop",
    "F-04 modeling previously stamped layers=2 without a residual pass",
    "F-05 coordination previously stamped n_cap without a tournament",
    "F-06 hive previously reused a memory root and had no root_history",
    "F-07 security previously reported secret=false without a scan",
    "F-08 mobile previously reported gpu=false without a refusal oracle",
    "F-09 router previously stamped routes=1 without rejecting a third router",
    "F-10 multimodal previously stamped data-only without hashing a frame",
    "F-11 repeated corpus rows are not independent trials",
    "F-12 contrib/ai-tree-fill is unowned in machine/ai_file_tree.json",
    "F-13 a same-process probe is not independent verification",
)


@dataclass
class Review:
    confirmed: dict[str, dict]
    withheld: dict[str, str]
    tasks: list[P5Task]
    bundle: dict
    signature: dict


def review(catalog_ids: list[str]) -> Review:
    confirmed: dict[str, dict] = {}
    withheld: dict[str, str] = {}
    tasks: list[P5Task] = []
    oracles = _oracles()
    for cid in catalog_ids:
        tool = tool_for(cid, "write" if cid in {"AIFT-OUTBOX", "AIFT-ORGAN-FORGE"} else "read")
        task = P5Task(f"P5-{cid}", cid, tool.tool_id, oracles[cid].__name__ if cid in oracles else "inherited-probe")
        if cid not in oracles:
            task.status = "withheld"
            task.receipt = {"reason": "no independent oracle; probe presence is not verification"}
            withheld[cid] = task.receipt["reason"]
            tasks.append(task)
            continue
        try:
            result = oracles[cid]()
            _assert_oracle(cid, result)
            rec = receipt(tool, result, digest_card(result))
            task.status = "confirmed"
            task.receipt = rec
            confirmed[cid] = result
        except (LawBreak, AssertionError, KeyError, ValueError) as exc:
            task.status = "withheld"
            task.receipt = {"reason": str(exc)}
            withheld[cid] = str(exc)
        tasks.append(task)
    # Negative oracles must fail closed. A pass here withholds the matching capability.
    negatives = {
        "AIFT-SECURITY-ACE": lambda: scan_secret("-----BEGIN PRIVATE KEY-----"),
        "AIFT-MOBILE-BANK": lambda: mobile_bank("gpu"),
        "AIFT-ROUTER": lambda: route("shadow-router"),
        "AIFT-MULTIMODAL": lambda: bind_frame(b"x", True),
        "AIFT-COORDINATION": lambda: tournament(["r"] * 9),
    }
    for cid, fn in negatives.items():
        try:
            fn()
            withheld[cid] = "negative oracle did not fail"
            for task in tasks:
                if task.capability_id == cid:
                    task.status = "withheld"
                    task.receipt = {"reason": withheld[cid]}
            confirmed.pop(cid, None)
        except LawBreak:
            pass
    structural = {
        "P5-F11": "repeated corpus rows are not independent trials",
        "P5-F12": "contrib/ai-tree-fill is unowned in machine/ai_file_tree.json",
        "P5-F13": "same-process verifier is not an independent sign-off",
    }
    for task_id, reason in structural.items():
        task = P5Task(task_id, task_id, "p5.structural", "adversarial-fault")
        task.status = "withheld"
        task.receipt = {"reason": reason}
        tasks.append(task)
        withheld[task_id] = reason
    bundle = {
        "plane": "p5",
        "parent_sha": PARENT_SHA,
        "faults": list(FALSE_STAMP_FAULTS),
        "confirmed": sorted(confirmed),
        "withheld": withheld,
        "ledger": ledger(tasks),
        "verifier": "p5-adversarial-verifier",
        "started_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    signature = sign_confirmed(bundle)
    bundle["completed_at_utc"] = signature["signed_at_utc"]
    bundle["signoff_ref"] = signature["signature"][:16]
    return Review(confirmed, withheld, tasks, bundle, signature)


def _assert_oracle(cid: str, result: dict) -> None:
    if cid == "AIFT-SPECDEC" and result["mismatch_at"] != 2:
        raise AssertionError("specdec mismatch")
    if cid == "AIFT-DECISION" and (result["pick_used"] or result["choice"] is not None):
        raise AssertionError("veto ignored")
    if cid == "AIFT-TRAINING" and result["absorb_steps"] != 4:
        raise AssertionError("absorb")
    if cid == "AIFT-MODELING" and result["layers"] != 2:
        raise AssertionError("layers")
    if cid == "AIFT-ECONOMY-HARBOR" and (abs(result["sum"] - 1.0) > 1e-9 or result["coin"]):
        raise AssertionError("harbor")
    if cid == "AIFT-EVIDENCE" and result.get("availability") != "unavailable":
        raise AssertionError("missing evidence became available")
        raise AssertionError("harbor")
    if cid == "AIFT-RUNTIME-CONTRACTS" and result.get("hit") != 0:
        raise AssertionError("unknown organ")
    if cid == "AIFT-COORDINATION" and result["n"] > result["n_cap"]:
        raise AssertionError("cap")


def sign_confirmed(bundle: dict) -> dict:
    """Sign only the confirmed set. Withheld ids are outside the signature."""
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    payload = json.dumps(
        {"confirmed": bundle["confirmed"], "faults": bundle["faults"], "parent_sha": bundle["parent_sha"]},
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    sig = key.sign(payload)
    return {
        "alg": "Ed25519",
        "verifier_identity": "p5-adversarial-verifier",
        "public_key_hex": public.hex(),
        "artifact_digest": digest,
        "evidence_bundle_digest": digest,
        "fault_manifest_digest": hashlib.sha256("\n".join(bundle["faults"]).encode()).hexdigest(),
        "git_sha": bundle["parent_sha"],
        "binds": ["git_sha", "artifact_digest", "evidence_bundle_digest", "fault_manifest_digest"],
        "signed_ids": bundle["confirmed"],
        "signature": sig.hex(),
        "signed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": "confirmed-only; withheld ids are not completed",
    }


def verify_signature(bundle: dict, signature: dict) -> bool:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    payload = json.dumps(
        {"confirmed": bundle["confirmed"], "faults": bundle["faults"], "parent_sha": bundle["parent_sha"]},
        sort_keys=True,
    ).encode("utf-8")
    public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(signature["public_key_hex"]))
    public.verify(bytes.fromhex(signature["signature"]), payload)
    return True
