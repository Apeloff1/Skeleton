"""Full capability body. One invoke path per catalog id. No facade card."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

from ai_tree_fill.catalog import DESCRIPTORS
from ai_tree_fill.chamber import Chamber
from ai_tree_fill.ed25519_hold import Ed25519Hold
from ai_tree_fill.hybrid_rank import HybridRank, MemoryRetrievalSink
from ai_tree_fill.laws import ClippedG, LawBreak, mass_admit, merkle_root, parse_pointers
from ai_tree_fill.memory_store import MemoryDistributedBackend
from ai_tree_fill.numerics import conjugate_gradient, householder_qr, matvec, qk_scores, rmsnorm, silu
from ai_tree_fill.organs import ORGAN_NAMES, dispatch
from ai_tree_fill.planes import Admission, DurableOutbox, FailureDomain, PointerMemory, compensation, recovery, skill_bind
from ai_tree_fill.p5_verifier import accept_until_mismatch, bind_frame, decide, mobile_bank, route, scan_secret, tournament


STIMULUS = "github.com/Apeloff1/Skeleton VOL-113 GB-16 AIFT-BODY"
ORGAN_ALIAS = {
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


@dataclass
class BodyState:
    memory: PointerMemory = field(default_factory=PointerMemory)
    outbox: DurableOutbox = field(default_factory=DurableOutbox)
    store: MemoryDistributedBackend = field(default_factory=MemoryDistributedBackend)
    sink: MemoryRetrievalSink = field(default_factory=MemoryRetrievalSink)
    hold: Ed25519Hold = field(default_factory=Ed25519Hold.mint)
    roots: list[str] = field(default_factory=list)
    g: ClippedG = field(default_factory=lambda: ClippedG(1.0, 1.0, 0.0, 0.0, [1.0]))


class CapabilityBody:
    def __init__(self, state: BodyState | None = None) -> None:
        self.state = state or BodyState()

    def invoke(self, capability_id: str, stimulus: str = STIMULUS) -> dict:
        handler = self._handlers().get(capability_id)
        if handler is None:
            return {"capability_id": capability_id, "hit": 0, "law": "unknown-capability"}
        card = handler(stimulus)
        card["capability_id"] = capability_id
        card["body"] = "capability-body"
        return card

    def invoke_all(self, stimulus: str = STIMULUS) -> dict[str, dict]:
        return {item.capability_id: self.invoke(item.capability_id, stimulus) for item in DESCRIPTORS}

    def _handlers(self):
        state = self.state
        def numerics(_stimulus: str) -> dict:
            vec = rmsnorm([3.0, 4.0])
            return {"hit": 1, "law": "numerics", "norm": vec, "finite": all(math.isfinite(x) for x in vec)}
        def linalg(_stimulus: str) -> dict:
            matrix = [[1.0, 1.0], [1.0, -1.0], [1.0, 2.0]]
            q, r = householder_qr(matrix)
            rebuilt = [sum(q[i][k] * r[k][j] for k in range(2)) for j in range(2) for i in range(1)]
            return {"hit": 1, "law": "linalg", "r00": r[0][0], "recon0": rebuilt[0]}
        def optimize(_stimulus: str) -> dict:
            matrix = [[4.0, 1.0], [1.0, 3.0]]
            solved = conjugate_gradient(matrix, [1.0, 2.0])
            ax = matvec(matrix, solved)
            return {"hit": 1, "law": "optimize", "residual": abs(ax[0] - 1.0)}
        def pointers(stimulus: str) -> dict:
            clauses = parse_pointers(stimulus)
            return {"hit": 1, "law": "pointer", "n": len(clauses), "clauses": clauses}
        def clipped(_stimulus: str) -> dict:
            state.g = state.g.step(0.2, 0.5)
            card = state.g.card()
            card["hit"] = 1
            return card
        def memory(stimulus: str) -> dict:
            card = state.memory.absorb(stimulus)
            state.roots.append(card["root"])
            return card
        def retrieval(stimulus: str) -> dict:
            state.sink.upsert({"content_hash": hashlib.sha256(stimulus.encode()).hexdigest(), "body": stimulus, "metadata": {}})
            rank = HybridRank([{"id": "atlas", "room": "forge", "text": stimulus}], [])
            hits = rank.retrieve("Skeleton", "forge")
            return {"hit": 1, "law": "retrieval", "hits": len(hits), "sink": len(state.sink.rows)}
        def skills(_stimulus: str) -> dict:
            return skill_bind("capability-body", "invoke")
        def outbox(_stimulus: str) -> dict:
            first = state.outbox.enqueue("body", {"kind": "card"})
            replay = state.outbox.enqueue("body", {"kind": "card"})
            return {"hit": 1, "law": "outbox", "replay": replay["replay"], "first": first["replay"]}
        def consensus(_stimulus: str) -> dict:
            root = state.roots[-1] if state.roots else merkle_root(["empty"])
            domain = FailureDomain()
            domain.vote("a", root)
            domain.vote("b", root)
            return domain.quorum()
        def admission(_stimulus: str) -> dict:
            gate = Admission()
            gate.claim("skeleton/ai/fill/capability_body.py", "native_ai_owners")
            return gate.audit(["skeleton/ai/fill/capability_body.py"])
        def providers(_stimulus: str) -> dict:
            return {"hit": 1, "law": "provider", "device": "cpu", "torch": False, "authority": "none"}
        def era(stimulus: str) -> dict:
            return dispatch("refer", stimulus, {"title": "skeleton"})
        def hive(_stimulus: str) -> dict:
            return {"hit": 1, "law": "hive-merkle", "root_history": list(state.roots), "chain": False}
        def index(_stimulus: str) -> dict:
            missing = [item.capability_id for item in DESCRIPTORS if not item.owner or not item.contract or not item.security]
            if missing:
                raise LawBreak("unowned", ",".join(missing))
            return {"hit": 1, "law": "index", "n": len(DESCRIPTORS)}
        def specdec(_stimulus: str) -> dict:
            return accept_until_mismatch([1, 1, 0, 1], [1, 1, 1, 1])
        def harbor(_stimulus: str) -> dict:
            weights = (0.5, 0.3, 0.2)
            if abs(sum(weights) - 1.0) > 1e-9:
                raise LawBreak("weight-sum", "harbor")
            return {"hit": 1, "law": "harbor", "sum": sum(weights), "coin": False}
        def mobile(_stimulus: str) -> dict:
            return mobile_bank("bank")
        def security(stimulus: str) -> dict:
            return scan_secret(stimulus)
        def queue12(_stimulus: str) -> dict:
            scores = qk_scores([0.2, -0.1, 0.4], [[0.2, -0.1, 0.4], [1.0, 0.0, -1.0]])
            return {"hit": 1, "law": "queue12", "scores": scores}
        def cognition(stimulus: str) -> dict:
            plan = dispatch("plan", stimulus, {"title": "gameforge"})
            cut = dispatch("cut", stimulus, {"title": "skeleton"})
            speak = dispatch("speak", stimulus)
            return {"hit": 1, "law": "cognition", "plan": plan["era"], "cut": cut["era"], "voice": speak["voice"]}
        def modeling(_stimulus: str) -> dict:
            hidden = silu(rmsnorm([0.2, -0.4, 0.8, 0.1]))
            out = silu(rmsnorm(hidden))
            return {"hit": 1, "law": "modeling", "layers": 2, "residual": out}
        def training(_stimulus: str) -> dict:
            g = ClippedG(1.0, 1.0, 0.0, 0.0, [1.0])
            for _ in range(4):
                g = g.step(0.1, 0.5)
            card = g.card()
            card["absorb_steps"] = 4
            card["hit"] = 1
            return card
        def multimodal(_stimulus: str) -> dict:
            return bind_frame(b"frame-bytes", False)
        def runtime(stimulus: str) -> dict:
            return dispatch("missing-organ", stimulus)
        def decision(_stimulus: str) -> dict:
            return decide([0.2, 0.9, 0.1], True)
        def evidence(_stimulus: str) -> dict:
            return {"hit": 0, "law": "evidence", "availability": "unavailable"}
        def coordination(_stimulus: str) -> dict:
            window = (state.roots or ["r1", "r1", "r2"])[-8:]
            return tournament(window)
        def chamber(stimulus: str) -> dict:
            return Chamber().walk(stimulus)
        handlers = {
            "AIFT-NUMERICS": numerics,
            "AIFT-LINALG": linalg,
            "AIFT-OPTIMIZE": optimize,
            "AIFT-POINTER-PARSE": pointers,
            "AIFT-CLIPPED-G": clipped,
            "AIFT-MEMORY": memory,
            "AIFT-RETRIEVAL": retrieval,
            "AIFT-SKILLS": skills,
            "AIFT-OUTBOX": outbox,
            "AIFT-CONSENSUS": consensus,
            "AIFT-ADMISSION": admission,
            "AIFT-COMPENSATION": lambda _s: compensation("enqueue", "drop"),
            "AIFT-RECOVERY": lambda _s: recovery("body", "checkpoint-body"),
            "AIFT-PROVIDERS": providers,
            "AIFT-ERA-BIND": era,
            "AIFT-HIVE-MERKLE": hive,
            "AIFT-CAPABILITY-INDEX": index,
            "AIFT-ROUTER": lambda _s: route("cascade"),
            "AIFT-SPECDEC": specdec,
            "AIFT-ECONOMY-HARBOR": harbor,
            "AIFT-MOBILE-BANK": mobile,
            "AIFT-SECURITY-ACE": security,
            "AIFT-QUEUE12": queue12,
            "AIFT-COGNITION": cognition,
            "AIFT-LEARNING": clipped,
            "AIFT-MODELING": modeling,
            "AIFT-TRAINING": training,
            "AIFT-MULTIMODAL": multimodal,
            "AIFT-RUNTIME-CONTRACTS": runtime,
            "AIFT-DECISION": decision,
            "AIFT-EVIDENCE": evidence,
            "AIFT-COORDINATION": coordination,
        }
        for name, cid in ORGAN_ALIAS.items():
            handlers[cid] = lambda stimulus, organ=name: dispatch(organ, stimulus, {"title": "skeleton", "mass": 1.0, "g": state.g})
        handlers["AIFT-CHAMBER"] = chamber
        return handlers


def run_body(stimulus: str = STIMULUS) -> dict:
    body = CapabilityBody()
    cards = body.invoke_all(stimulus)
    failed = [cid for cid, card in cards.items() if card.get("law") == "unknown-capability"]
    if failed:
        raise LawBreak("body", ",".join(failed))
    signed = body.state.hold.sign(merkle_root([cid for cid in cards]).encode())
    return {
        "capabilities": len(cards),
        "hit": sum(1 for card in cards.values() if card.get("hit") == 1),
        "organs": len(ORGAN_NAMES),
        "key_id": signed.key_id,
        "cards": cards,
    }
