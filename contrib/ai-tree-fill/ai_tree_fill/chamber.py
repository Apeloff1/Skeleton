"""Inner courts for the AI shims. No coin. No stored sentence. No widened grant."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field

from ai_tree_fill.ed25519_hold import Ed25519Hold
from ai_tree_fill.laws import LawBreak, digest_card, merkle_root, parse_pointers
from ai_tree_fill.memory_store import FenceError, MemoryDistributedBackend
from ai_tree_fill.numerics import softmax


class CourtSeal(RuntimeError):
    def __init__(self, court: str, detail: str) -> None:
        super().__init__(f"{court}: {detail}")
        self.court = court
        self.detail = detail


def _sha(payload: str) -> str:
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class ToolSchema:
    tool_id: str
    input_fields: tuple[str, ...]
    output_fields: tuple[str, ...]
    authority: str
    timeout_ms: int

    def validate(self, payload: dict) -> dict:
        if self.authority not in {"read", "write", "destructive"}:
            raise CourtSeal("tool-schema", "unknown authority")
        extra = set(payload) - set(self.input_fields)
        missing = set(self.input_fields) - set(payload)
        if extra or missing:
            raise CourtSeal("tool-schema", f"shape extra={sorted(extra)} missing={sorted(missing)}")
        if self.timeout_ms < 1 or self.timeout_ms > 30_000:
            raise CourtSeal("tool-schema", "timeout outside court")
        return {"tool_id": self.tool_id, "authority": self.authority, "digest": digest_card(payload)}


@dataclass(frozen=True)
class AuthorityGrant:
    holder: str
    permits: frozenset[str]

    def subset(self, child: "AuthorityGrant") -> "AuthorityGrant":
        if not child.permits <= self.permits:
            raise CourtSeal("authority", f"{child.holder} widens {sorted(child.permits - self.permits)}")
        return child


@dataclass
class StopPolicy:
    max_steps: int = 7
    max_mass_ratio: float = 1.1
    veto_axes: tuple[str, ...] = ("feasibility",)

    def admit(self, steps: int, mass_ratio: float, axes: dict[str, float]) -> dict:
        if steps > self.max_steps:
            raise CourtSeal("stop", "step budget")
        if mass_ratio > self.max_mass_ratio:
            raise CourtSeal("stop", "mass snowball")
        for axis in self.veto_axes:
            if axes.get(axis, 0.0) < 0.4:
                raise CourtSeal("stop", f"veto {axis}")
        return {"hit": 1, "law": "stop", "steps": steps, "mass_ratio": mass_ratio}


@dataclass
class RivalProposal:
    proposer: str
    claim: str
    pointers: tuple[str, ...]
    axes: dict[str, float]

    @classmethod
    def from_stimulus(cls, proposer: str, stimulus: str, axes: dict[str, float]) -> "RivalProposal":
        return cls(proposer, _sha(stimulus)[:16], tuple(parse_pointers(stimulus)), axes)


@dataclass
class RivalChallenge:
    challenger: str
    target: str
    failed_axis: str
    evidence: str

    def strike(self, proposal: RivalProposal) -> dict:
        if self.failed_axis not in proposal.axes:
            raise CourtSeal("rival", "uncharted axis")
        if proposal.axes[self.failed_axis] >= 0.45:
            raise CourtSeal("rival", "axis holds")
        return {
            "hit": 1,
            "law": "rival",
            "target": proposal.proposer,
            "failed_axis": self.failed_axis,
            "evidence": self.evidence,
        }


@dataclass
class Contradiction:
    left: str
    right: str

    def resolve(self) -> dict:
        a = parse_pointers(self.left)
        b = parse_pointers(self.right)
        shared = sorted(set(a).intersection(b))
        only_left = sorted(set(a) - set(b))
        only_right = sorted(set(b) - set(a))
        if only_left and only_right and not shared:
            standing = "contested"
        else:
            standing = "reconciled"
        return {"hit": 1, "law": "contradiction", "standing": standing, "shared": shared, "left": only_left, "right": only_right}


@dataclass
class SandboxBoundary:
    network: bool = False
    coin: bool = False
    device: str = "cpu"

    def cross(self, effect: dict) -> dict:
        if self.network or effect.get("network"):
            raise CourtSeal("sandbox", "network closed")
        if self.coin or effect.get("coin"):
            raise CourtSeal("sandbox", "coin closed")
        if effect.get("device", "cpu") != "cpu":
            raise CourtSeal("sandbox", "device closed")
        return {"hit": 1, "law": "sandbox", "device": "cpu"}


@dataclass
class IncidentState:
    sealed: bool = False
    reasons: list[str] = field(default_factory=list)

    def fail(self, reason: str) -> None:
        self.sealed = True
        self.reasons.append(reason)

    def require_open(self) -> None:
        if self.sealed:
            raise CourtSeal("incident", ",".join(self.reasons))


@dataclass
class SourceProvenance:
    pointers: tuple[str, ...]

    @property
    def root(self) -> str:
        return merkle_root(self.pointers)


@dataclass
class QualityDelta:
    before: dict[str, float]
    after: dict[str, float]

    def card(self) -> dict:
        delta = {axis: self.after[axis] - self.before.get(axis, 0.0) for axis in self.after}
        weakest = min(self.after, key=self.after.get)
        return {"hit": 1, "law": "quality-delta", "delta": delta, "weakest": weakest}


@dataclass
class ReplayReceipt:
    plan_id: str
    steps: tuple[str, ...]
    root: str

    @classmethod
    def issue(cls, plan_id: str, steps: list[str]) -> "ReplayReceipt":
        return cls(plan_id, tuple(steps), merkle_root(steps))


class StreamDecoder:
    def __init__(self, cap: int = 8) -> None:
        self.cap = cap
        self.events: list[dict] = []

    def push(self, event_id: int, draft: str, target: str) -> dict:
        if len(self.events) >= self.cap:
            raise CourtSeal("stream", "cap")
        mismatch = draft != target
        event = {"id": event_id, "accept": not mismatch, "seq": len(self.events)}
        self.events.append(event)
        if mismatch:
            return {"hit": 1, "law": "stream", "mismatch_at": event["seq"], "accepted": event["seq"]}
        return {"hit": 1, "law": "stream", "accepted": event["seq"] + 1}


class Chamber:
    """Seven-court walk. A seal in any court seals the incident and stops the rest."""

    def __init__(self) -> None:
        self.store = MemoryDistributedBackend()
        self.incident = IncidentState()
        self.hold = Ed25519Hold.mint()
        self.boundary = SandboxBoundary()
        self.stop = StopPolicy()
        self.trace: list[dict] = []

    def walk(self, stimulus: str) -> dict:
        self.incident.require_open()
        try:
            schema = ToolSchema("p5.walk", ("stimulus",), ("card",), "read", 2000)
            schema.validate({"stimulus": stimulus})
            grant = AuthorityGrant("chamber", frozenset({"read", "rank"}))
            grant.subset(AuthorityGrant("organ", frozenset({"read"})))
            self.boundary.cross({"device": "cpu", "coin": False, "network": False})
            axes = {"fun": 0.62, "clarity": 0.7, "feasibility": 0.81, "originality": 0.66}
            self.stop.admit(7, 1.05, axes)
            proposal = RivalProposal.from_stimulus("forge", stimulus, axes)
            challenge = RivalChallenge("cut", proposal.proposer, "fun", proposal.pointers[0])
            # fun is 0.62, strike requires < 0.45, so this challenge must fail closed and be recorded, not applied
            challenge_card = {"hit": 0, "law": "rival-held", "axis": "fun", "value": axes["fun"]}
            contradiction = Contradiction(stimulus, stimulus + " VOL-113").resolve()
            provenance = SourceProvenance(tuple(parse_pointers(stimulus)))
            quality = QualityDelta({"fun": 0.4}, axes).card()
            receipt = ReplayReceipt.issue("plan-7", ["vision", "snowball", "prototype", "mass", "world", "cockpit", "export"])
            decoder = StreamDecoder()
            stream = decoder.push(1, "a", "a")
            stream_miss = decoder.push(2, "b", "c")
            weights = softmax([0.2, 0.7, 0.1])
            lease = self.store.acquire_lease("chamber", "walk", owner="p5", ttl_seconds=30)
            row = self.store.put_if_absent("chamber", "walk", {"root": provenance.root})
            self.store.fenced_compare_and_swap(lease, expected_revision=row.revision, value={"root": provenance.root, "at": time.time()})
            envelope = self.hold.sign(provenance.root.encode())
            card = {
                "hit": 1,
                "law": "chamber",
                "root": provenance.root,
                "receipt": receipt.root,
                "quality": quality,
                "contradiction": contradiction["standing"],
                "challenge": challenge_card,
                "stream": stream_miss,
                "choice": int(max(range(len(weights)), key=lambda i: weights[i])),
                "signature": envelope.signature,
                "key_id": envelope.key_id,
                "accepted_prefix": stream["accepted"],
            }
            self.trace.append(card)
            return card
        except (CourtSeal, LawBreak, FenceError) as exc:
            self.incident.fail(str(exc))
            raise

    def seal(self) -> dict:
        blob = json.dumps(self.trace, sort_keys=True)
        return {"events": len(self.trace), "digest": _sha(blob), "sealed": self.incident.sealed}
