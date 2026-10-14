"""Seeded chaos for the agent edge: lost acks, duplicates, crashes, sick agents.

Each scenario drives an :class:`AgentBus` / :class:`AgentRouter` with a
:class:`ManualClock` and a ``random.Random(seed)`` so a failing run is
reproducible from its seed. Every scenario returns a :class:`ChaosReport`
whose ``violations`` must be empty; invariants checked:

* **no loss** — every accepted message is eventually acked or dead-lettered;
* **exactly-once effect** — an idempotent consumer (dedup on message id)
  applies each message at most once even though delivery is at-least-once;
* **per-conversation order** — the first *processing* of messages in a
  conversation follows their bus sequence;
* **dedup** — duplicate publishes never create a second queue entry;
* **breaker isolation** — a failing agent is removed from capability routing
  and traffic converges on healthy agents.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from skeleton.gate_plane.agent_edge.bus import AgentBus
from skeleton.gate_plane.agent_edge.dedup import DedupWindow
from skeleton.gate_plane.agent_edge.dlq import DeadLetterQueue
from skeleton.gate_plane.agent_edge.envelope import Envelope
from skeleton.gate_plane.agent_edge.routing import AgentEndpoint, AgentRegistry, AgentRouter
from skeleton.gate_plane.pipeline.breaker import BreakerConfig, BreakerRegistry
from skeleton.gate_plane.s2s.clock import ManualClock


@dataclass
class ChaosReport:
    scenario: str
    seed: int
    stats: Dict[str, Any] = field(default_factory=dict)
    violations: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_dict(self) -> Dict[str, Any]:
        return {"scenario": self.scenario, "seed": self.seed, "ok": self.ok, "stats": self.stats, "violations": list(self.violations)}


def _bus(clock: ManualClock, **kw: Any) -> AgentBus:
    return AgentBus(
        clock=clock,
        dedup=DedupWindow(window_s=86_400.0),
        dlq=DeadLetterQueue(),
        default_lease_s=kw.pop("lease_s", 5.0),
        backoff_base_s=kw.pop("backoff_base_s", 0.2),
        backoff_cap_s=kw.pop("backoff_cap_s", 2.0),
        lease_id_factory=kw.pop("lease_id_factory", None),
        **kw,
    )


def _lease_ids(rng: random.Random) -> Callable[[], str]:
    def make() -> str:
        return f"lease-{rng.getrandbits(64):016x}"

    return make


def scenario_unreliable_consumer(
    seed: int,
    *,
    conversations: int = 12,
    messages_per_conversation: int = 15,
    p_crash: float = 0.15,
    p_lost_ack: float = 0.1,
    p_duplicate_publish: float = 0.2,
    max_attempts: int = 25,
    max_steps: int = 20_000,
) -> ChaosReport:
    """Consumer crashes (nack), loses acks (lease expiry) and producers re-publish."""
    rng = random.Random(seed)
    clock = ManualClock()
    bus = _bus(clock, lease_id_factory=_lease_ids(rng))
    report = ChaosReport("unreliable_consumer", seed)
    accepted: Set[str] = set()
    planned: List[Envelope] = []
    for c in range(conversations):
        conv = f"conv-{seed}-{c:03d}"
        for m in range(messages_per_conversation):
            planned.append(
                Envelope.new(
                    sender="producer",
                    recipient="worker",
                    topic="work.item",
                    payload={"c": c, "m": m},
                    conversation_id=conv,
                    message_id=f"msg-{seed}-{c:03d}-{m:03d}",
                    priority=rng.randint(1, 6),
                    ttl_s=3600.0,
                    max_attempts=max_attempts,
                    now=clock.now(),
                )
            )
    rng.shuffle(planned)
    # producers keep per-conversation publish order; shuffle only interleaving
    by_conv: Dict[str, List[Envelope]] = {}
    for env in sorted(planned, key=lambda e: e.message_id):
        by_conv.setdefault(env.conversation_id, []).append(env)
    cursors = {k: 0 for k in by_conv}
    duplicates = 0
    applied: Dict[str, int] = {}
    effect_log: Dict[str, List[int]] = {}
    seq_of: Dict[str, int] = {}
    steps = 0
    while steps < max_steps:
        steps += 1
        live = [k for k, i in cursors.items() if i < len(by_conv[k])]
        if live and rng.random() < 0.5:
            conv = rng.choice(live)
            env = by_conv[conv][cursors[conv]]
            cursors[conv] += 1
            res = bus.publish(env)
            if res.accepted:
                accepted.add(env.message_id)
                seq_of[env.message_id] = int(res.sequence or 0)
            if rng.random() < p_duplicate_publish:
                dup = bus.publish(env)
                duplicates += 1
                if dup.accepted:
                    report.violations.append(f"duplicate publish accepted for {env.message_id}")
        for d in bus.pull("worker", max_messages=rng.randint(1, 8)):
            roll = rng.random()
            if roll < p_crash:
                bus.nack(d.lease_id, error="crash")
                continue
            mid = d.envelope.message_id
            if mid not in applied:
                applied[mid] = 1
                effect_log.setdefault(d.envelope.conversation_id, []).append(d.envelope.sequence)
            else:
                applied[mid] += 1  # redelivery after a lost ack: consumer dedups
            if roll < p_crash + p_lost_ack:
                continue  # ack lost -> lease expires -> redelivery
            bus.ack(d.lease_id)
        clock.advance(rng.choice((0.05, 0.2, 1.0, 6.0)))
        if not live and bus.depth() == 0:
            break
    dead = {dl.envelope.message_id for dl in bus.dlq.list(limit=1_000_000)}
    done = {m for m in accepted if bus.dedup.seen(Envelope.new(sender="producer", recipient="worker", topic="x", message_id=m).dedup_key, clock.now()) == "done"}
    lost = accepted - done - dead
    if lost:
        report.violations.append(f"{len(lost)} accepted messages neither acked nor dead-lettered")
    if bus.depth() != 0:
        report.violations.append(f"bus not drained: depth={bus.depth()}")
    for conv, seqs in effect_log.items():
        if seqs != sorted(seqs):
            report.violations.append(f"conversation {conv} processed out of order: {seqs[:10]}")
    report.stats = {
        "steps": steps,
        "accepted": len(accepted),
        "acked": len(done),
        "dead": len(dead),
        "duplicate_publishes": duplicates,
        "redelivered_effects_suppressed": sum(v - 1 for v in applied.values()),
        "bus": bus.stats()["events"],
    }
    return report


def scenario_poison_and_ttl(seed: int, *, messages: int = 60, p_poison: float = 0.1, p_short_ttl: float = 0.15) -> ChaosReport:
    """Poison messages and short TTLs must land in the DLQ without blocking their conversation."""
    rng = random.Random(seed)
    clock = ManualClock()
    bus = _bus(clock, lease_id_factory=_lease_ids(rng))
    report = ChaosReport("poison_and_ttl", seed)
    poison: Set[str] = set()
    short: Set[str] = set()
    for i in range(messages):
        conv = f"conv-{seed}-{i % 5}"
        ttl = 0.5 if rng.random() < p_short_ttl else 600.0
        env = Envelope.new(
            sender="producer", recipient="worker", topic="work.item", payload={"i": i},
            conversation_id=conv, message_id=f"msg-{seed}-{i:04d}", ttl_s=ttl, max_attempts=3, now=clock.now(),
        )
        if rng.random() < p_poison:
            poison.add(env.message_id)
        if ttl < 1:
            short.add(env.message_id)
        bus.publish(env)
    clock.advance(1.0)  # short TTLs elapse before first pull
    acked: Set[str] = set()
    for _ in range(500):
        ds = bus.pull("worker", max_messages=8)
        if not ds and bus.depth() == 0:
            break
        for d in ds:
            if d.envelope.message_id in poison:
                bus.nack(d.lease_id, error="bad payload", poison=True)
            else:
                bus.ack(d.lease_id)
                acked.add(d.envelope.message_id)
        clock.advance(0.1)
    letters = {dl.envelope.message_id: dl.reason.value for dl in bus.dlq.list(limit=10_000)}
    for mid in short:
        if letters.get(mid) != "ttl_expired":
            report.violations.append(f"{mid} expected ttl_expired, got {letters.get(mid)}")
    for mid in poison - short:
        if letters.get(mid) != "poison":
            report.violations.append(f"{mid} expected poison, got {letters.get(mid)}")
    if acked & set(letters):
        report.violations.append("a message was both acked and dead-lettered")
    if bus.depth():
        report.violations.append(f"conversation blocked: depth={bus.depth()}")
    report.stats = {"acked": len(acked), "dead": len(letters), "poison": len(poison), "short_ttl": len(short)}
    return report


def scenario_sick_agent(seed: int, *, agents: int = 4, calls: int = 400, sick_failure_rate: float = 0.9) -> ChaosReport:
    """One agent fails most calls: its breaker opens and routing drains away from it."""
    rng = random.Random(seed)
    clock = ManualClock()
    registry = AgentRegistry(
        AgentEndpoint.build(f"agent-{i}", "swarm", ["work.item"], capacity=1000) for i in range(agents)
    )
    breakers = BreakerRegistry(
        clock=clock, default=BreakerConfig(consecutive_failures=3, min_calls=5, window_size=10, cooldown_s=30.0)
    )
    router = AgentRouter(registry, breakers=breakers, clock=clock)
    sick = f"agent-{rng.randrange(agents)}"
    report = ChaosReport("sick_agent", seed)
    served: Dict[str, int] = {}
    late_sick = 0
    for i in range(calls):
        d = router.route("work.item", conversation_id=f"conv-{i}")
        if not d.routed:
            report.violations.append(f"call {i} unroutable: {d.outcome.value}")
            continue
        agent = d.agent_id or ""
        served[agent] = served.get(agent, 0) + 1
        router.begin(agent)
        ok = not (agent == sick and rng.random() < sick_failure_rate)
        router.end(agent, ok=ok)
        if i >= calls // 2 and agent == sick:
            late_sick += 1
        clock.advance(0.05)
    healthy_share = 1.0 - served.get(sick, 0) / max(1, calls)
    if late_sick > calls // 20:
        report.violations.append(f"sick agent still served {late_sick} calls in second half")
    report.stats = {"sick": sick, "served": served, "healthy_share": round(healthy_share, 3), "breakers": breakers.states()}
    return report


SCENARIOS: Dict[str, Callable[..., ChaosReport]] = {
    "unreliable_consumer": scenario_unreliable_consumer,
    "poison_and_ttl": scenario_poison_and_ttl,
    "sick_agent": scenario_sick_agent,
}


def run_all(seeds: Tuple[int, ...] = (1, 7, 42, 1337), names: Optional[List[str]] = None) -> List[ChaosReport]:
    out: List[ChaosReport] = []
    for name in names or sorted(SCENARIOS):
        for seed in seeds:
            out.append(SCENARIOS[name](seed))
    return out


__all__ = [
    "ChaosReport",
    "SCENARIOS",
    "run_all",
    "scenario_poison_and_ttl",
    "scenario_sick_agent",
    "scenario_unreliable_consumer",
]
