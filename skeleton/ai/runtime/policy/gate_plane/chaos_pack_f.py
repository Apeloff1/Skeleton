"""Pack F chaos suite — deterministic fault injection across the s2s plane.

Every scenario runs on a :class:`ManualClock` with a seeded RNG, so it is
reproducible, sleeps nothing for real, and can run in CI. Each returns a
:class:`ChaosReport` of named invariants; a scenario *passes* only if every
invariant holds.

Scenarios
---------
``brownout_breaker_trips``        50% upstream 503s trip the breaker, upstream
                                   load is capped while open, half-open probe
                                   closes it once the upstream recovers.
``retry_storm_bounded``           a hard outage cannot amplify traffic: retries
                                   stay within the retry budget.
``deadline_caps_latency``         a slow upstream never holds a caller past the
                                   route deadline (idempotent calls).
``pack_h_outage_fallback``        Pack H missing / failing / schema v2 / stale:
                                   the AdaptiveGate fallback keeps deciding.
``pressure_spike_sheds``          a pressure spike sheds with 429/503 +
                                   Retry-After, never calls the upstream, and
                                   still admits priority-0 control traffic.
``key_rotation_under_load``       tokens keep verifying across a rotation
                                   overlap; retired and revoked kids get 401,
                                   never 5xx.
``flapping_upstream_backoff``     a flapping upstream grows the breaker
                                   cool-down so probes get rarer.
``telemetry_failure_isolation``   a broken metrics backend changes no verdict.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from skeleton.gate_plane.admit import AdmissionMatrix
from skeleton.gate_plane.backpressure import (
    AdaptiveGateSource,
    BackpressureGate,
    BackpressureStage,
    FallbackChain,
    PackHSource,
    StaticSource,
)
from skeleton.gate_plane.backpressure.snapshot import iso_now
from skeleton.gate_plane.pipeline import (
    BreakerConfig,
    BreakerRegistry,
    BreakerStage,
    CircuitBreaker,
    Pipeline,
    PipelineError,
    PipelineRequest,
    PipelineResponse,
    PipelineRouter,
    RetryBudget,
    RetrySpec,
    RetryStage,
    RouteConfig,
    RouteTable,
)
from skeleton.gate_plane.s2s.authz import default_gate_plane_policies
from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.gate_plane.s2s.gate import S2SAuthGate
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.tokens import TokenSigner, TokenVerifier
from skeleton.gate_plane.telemetry import GateTelemetry, TelemetryStage
from skeleton.kernel.adaptive_gate import AdaptiveGate
from skeleton.kernel.chaos import ChaosGovernor
from skeleton.observability.metrics import MetricsCollector


@dataclass(frozen=True)
class FaultPlan:
    """What a :class:`FaultyUpstream` does on each call."""

    error_rate: float = 0.0
    error_status: int = 503
    exception_rate: float = 0.0
    latency_s: float = 0.0
    slow_rate: float = 0.0
    slow_latency_s: float = 0.0
    outages: Tuple[Tuple[float, float], ...] = ()  # (start, end) seconds since upstream creation

    def __post_init__(self) -> None:
        for name in ("error_rate", "exception_rate", "slow_rate"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{name} must be within [0, 1]")
        for start, end in self.outages:
            if end <= start:
                raise ValueError("outage windows need start < end")


class FaultyUpstream:
    """Deterministic fault-injecting handler driven by a virtual clock."""

    def __init__(self, clock: ManualClock, plan: FaultPlan, *, seed: int = 0) -> None:
        self.clock = clock
        self.plan = plan
        self.rng = random.Random(seed)
        self.t0 = clock.monotonic()
        self.calls = 0
        self.failures = 0
        self.log: List[Dict[str, Any]] = []

    def in_outage(self) -> bool:
        t = self.clock.monotonic() - self.t0
        return any(start <= t < end for start, end in self.plan.outages)

    def __call__(self, request: PipelineRequest, ctx: Any) -> PipelineResponse:
        self.calls += 1
        p = self.plan
        latency = p.latency_s
        if p.slow_rate and self.rng.random() < p.slow_rate:
            latency = p.slow_latency_s
        if latency:
            self.clock.advance(latency)
        if self.in_outage() or (p.error_rate and self.rng.random() < p.error_rate):
            self.failures += 1
            self.log.append({"call": self.calls, "status": p.error_status})
            return PipelineResponse(p.error_status, {"error": "injected"})
        if p.exception_rate and self.rng.random() < p.exception_rate:
            self.failures += 1
            self.log.append({"call": self.calls, "status": "exc"})
            raise ConnectionError("injected connection reset")
        self.log.append({"call": self.calls, "status": 200})
        return PipelineResponse(200, {"ok": True})


@dataclass
class ChaosReport:
    name: str
    seed: int
    invariants: Dict[str, bool] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return bool(self.invariants) and all(self.invariants.values())

    def check(self, name: str, ok: bool) -> None:
        self.invariants[name] = bool(ok)

    def failed(self) -> List[str]:
        return [k for k, v in self.invariants.items() if not v]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "seed": self.seed,
            "passed": self.passed,
            "invariants": dict(self.invariants),
            "metrics": dict(self.metrics),
        }


GET = PipelineRequest("GET", "/api/v1/forge/jobs", priority=1)


def _call(pipe: Pipeline, req: PipelineRequest, handler: Callable) -> Tuple[Optional[int], Optional[str]]:
    try:
        return pipe.run(req, handler).status, None
    except PipelineError as exc:
        return exc.status, exc.reason
    except Exception as exc:  # noqa: BLE001
        return None, type(exc).__name__


# --------------------------------------------------------------------------- scenarios
def scenario_brownout_breaker_trips(seed: int = 7) -> ChaosReport:
    r = ChaosReport("brownout_breaker_trips", seed)
    clock = ManualClock()
    up = FaultyUpstream(clock, FaultPlan(error_rate=0.5), seed=seed)
    breaker = CircuitBreaker(
        "forge", BreakerConfig(consecutive_failures=50, failure_rate=0.4, window_size=20, min_calls=10, cooldown_s=5.0),
        clock=clock,
    )
    pipe = Pipeline([BreakerStage(breaker)], clock=clock)
    rejected = 0
    for _ in range(200):
        status, reason = _call(pipe, GET, up)
        if reason == "circuit_open":
            rejected += 1
        clock.advance(0.01)
    r.metrics.update(calls=up.calls, rejected=rejected, opened=breaker.stats()["opened"])
    r.check("breaker_opened", breaker.stats()["opened"] >= 1)
    r.check("upstream_load_capped", up.calls < 200)
    r.check("rejections_fast", rejected > 0)
    # recovery: upstream healthy again, cool-down elapses, probe closes the breaker
    up.plan = FaultPlan()
    clock.advance(60.0)
    statuses = [_call(pipe, GET, up)[0] for _ in range(5)]
    r.metrics["recovery_statuses"] = statuses
    r.check("recovered_closed", breaker.state.value == "closed")
    r.check("recovery_all_ok", all(s == 200 for s in statuses))
    return r


def scenario_retry_storm_bounded(seed: int = 11) -> ChaosReport:
    r = ChaosReport("retry_storm_bounded", seed)
    clock = ManualClock()
    up = FaultyUpstream(clock, FaultPlan(error_rate=1.0), seed=seed)
    budget = RetryBudget(retry_ratio=0.1, min_retries_per_s=1.0, window_s=10.0, clock=clock)
    pipe = Pipeline(
        [RetryStage(RetrySpec(max_attempts=5, base_backoff_s=0.0, max_backoff_s=0.0, jitter=0.0), budget=budget,
                    rng=random.Random(seed))],
        clock=clock,
    )
    n = 500
    for _ in range(n):
        _call(pipe, GET, up)
        clock.advance(0.01)  # 500 requests in 5 virtual seconds (inside one window)
    retries = up.calls - n
    bound = int(n * budget.retry_ratio + budget.min_retries_per_s * budget.window_s) + 1
    naive = n * 4
    r.metrics.update(requests=n, upstream_calls=up.calls, retries=retries, bound=bound, naive_retries=naive)
    r.check("retries_within_budget", retries <= bound)
    r.check("amplification_below_1_2x", up.calls <= n * 1.2)
    r.check("budget_denied_some", budget.stats()["denied"] > 0)
    return r


def scenario_deadline_caps_latency(seed: int = 13) -> ChaosReport:
    r = ChaosReport("deadline_caps_latency", seed)
    clock = ManualClock()
    up = FaultyUpstream(clock, FaultPlan(slow_rate=0.3, slow_latency_s=3.0, latency_s=0.05, error_rate=0.2), seed=seed)
    table = RouteTable(
        [RouteConfig(name="forge-read", pattern="/api/v1/forge/**", upstream="forge",
                     methods=frozenset({"GET"}), timeout_s=1.0, attempt_timeout_s=0.5,
                     retry=RetrySpec(max_attempts=3, base_backoff_s=0.05, jitter=0.0),
                     breaker=BreakerConfig(consecutive_failures=1000, failure_rate=1.0, window_size=20, min_calls=20))]
    )
    router = PipelineRouter(table, clock=clock, rng=random.Random(seed))
    worst = 0.0
    outcomes: Dict[str, int] = {}
    for _ in range(200):
        start = clock.monotonic()
        try:
            resp, _ = router.call(GET, up)
            key = str(resp.status)
        except PipelineError as exc:
            key = exc.reason
        # cooperative mode: a caller may overshoot the deadline only by the one
        # attempt already in flight — never by extra attempts or backoff sleeps
        elapsed = clock.monotonic() - start
        worst = max(worst, elapsed - 1.0)
        outcomes[key] = outcomes.get(key, 0) + 1
    r.metrics.update(outcomes=outcomes, worst_overshoot_s=round(worst, 3), upstream_calls=up.calls)
    one_attempt = up.plan.slow_latency_s + up.plan.latency_s
    r.check("overshoot_bounded_by_one_attempt", worst <= one_attempt + 1e-9)
    r.check("slow_calls_time_out", outcomes.get("deadline_exceeded", 0) + outcomes.get("attempt_timeout", 0) > 0)
    r.check("most_calls_succeed", outcomes.get("200", 0) > 100)
    return r


def scenario_pack_h_outage_fallback(seed: int = 17) -> ChaosReport:
    r = ChaosReport("pack_h_outage_fallback", seed)
    clock = ManualClock()
    gate = AdaptiveGate(100, 100)
    mode = {"m": "missing"}

    def snapshot(tenant_id: Optional[str] = None) -> Dict[str, Any]:
        m = mode["m"]
        if m == "raises":
            raise RuntimeError("pack h db down")
        base = {"schema_version": 1, "load": 0.2, "queue_depth": 2, "max_queue_depth": 100,
                "tenant_queue_depth": None, "retry_after_s": 0.0, "state": "open",
                "observed_at": iso_now(clock.now())}
        if m == "v2":
            base["schema_version"] = 2
        if m == "stale":
            base["observed_at"] = iso_now(clock.now() - 3600)
        return base

    def resolver() -> Optional[Callable[..., Any]]:
        # "missing" models Pack H not registered by the API layer yet
        return None if mode["m"] == "missing" else snapshot

    chain = FallbackChain(
        [PackHSource(resolver=resolver), AdaptiveGateSource(gate, clock=clock)],
        clock=clock, max_age_s=5.0,
    )
    bp = BackpressureGate(chain, on_no_signal="shed")
    served: Dict[str, List[str]] = {}
    for m in ("missing", "raises", "v2", "stale", "healthy"):
        mode["m"] = m
        sources = []
        for _ in range(10):
            d = bp.decide(GET)
            sources.append(d.source or "none")
            if not d.admitted:
                sources.append("SHED")
        served[m] = sorted(set(sources))
    r.metrics["served"] = served
    r.check("missing_falls_back", served["missing"] == ["adaptive_gate"])
    r.check("raising_falls_back", served["raises"] == ["adaptive_gate"])
    r.check("schema_v2_refused", served["v2"] == ["adaptive_gate"])
    r.check("stale_refused", served["stale"] == ["adaptive_gate"])
    r.check("healthy_uses_pack_h", served["healthy"] == ["pack_h"])
    r.check("never_no_signal", all("none" not in v and "SHED" not in v for v in served.values()))
    return r


def scenario_pressure_spike_sheds(seed: int = 19) -> ChaosReport:
    r = ChaosReport("pressure_spike_sheds", seed)
    clock = ManualClock()
    level = {"load": 0.1, "qd": 0}

    def view(_tenant: Optional[str]) -> Dict[str, Any]:
        load = level["load"]
        state = "shed" if load >= 0.95 or level["qd"] >= 100 else ("throttle" if load >= 0.7 else "open")
        return {"schema_version": 1, "load": load, "queue_depth": level["qd"], "max_queue_depth": 100,
                "tenant_queue_depth": None, "retry_after_s": 2.5 if state != "open" else 0.0, "state": state,
                "observed_at": iso_now(clock.now())}

    bp = BackpressureGate(StaticSource(view, name="pack_h"))
    budget = RetryBudget(clock=clock)
    up = FaultyUpstream(clock, FaultPlan(), seed=seed)
    pipe = Pipeline([BackpressureStage(bp), RetryStage(RetrySpec(), budget=budget)], clock=clock)
    control = PipelineRequest("GET", "/api/v1/admin/x", priority=0)
    results: Dict[str, List[Any]] = {"open": [], "throttle": [], "shed": [], "full": [], "control": []}
    for phase, load, qd in (("open", 0.1, 0), ("throttle", 0.8, 10), ("shed", 0.97, 10), ("full", 0.5, 100)):
        level.update(load=load, qd=qd)
        before = up.calls
        for _ in range(20):
            resp = pipe.run(GET, up)
            results[phase].append((resp.status, resp.header("retry-after")))
        results[phase].append(("upstream_calls", up.calls - before))
        if phase == "shed":
            results["control"].append(pipe.run(control, up).status)
    r.metrics["results"] = {k: v[-1] if v else None for k, v in results.items()}
    r.check("open_admits", all(s == 200 for s, _ in results["open"][:-1]))
    r.check("throttle_long_wait_429", all(s == 429 and h == "3" for s, h in results["throttle"][:-1]))
    r.check("shed_429_retry_after", all(s == 429 and h == "3" for s, h in results["shed"][:-1]))
    r.check("queue_full_503", all(s == 503 for s, _ in results["full"][:-1]))
    r.check("no_upstream_calls_while_shedding",
            all(results[p][-1] == ("upstream_calls", 0) for p in ("throttle", "shed", "full")))
    r.check("control_plane_exempt", results["control"] == [200])
    r.check("shed_spends_no_retry_budget", budget.stats()["deposits"] == 21)
    return r


def scenario_key_rotation_under_load(seed: int = 23) -> ChaosReport:
    r = ChaosReport("key_rotation_under_load", seed)
    clock = ManualClock()
    ring = KeyRing(clock=clock)
    ring.add_key("k1", random.Random(seed).randbytes(32), activate=True)
    verifier = TokenVerifier("gateway", ring, clock=clock)
    matrix = AdmissionMatrix(gate=AdaptiveGate(10_000, 10_000), governor=ChaosGovernor(min_samples=10_000))
    gate = S2SAuthGate(verifier, default_gate_plane_policies(), matrix=matrix)
    signer = TokenSigner("forge-worker", ring, clock=clock, default_ttl_s=900)
    path = "/api/v1/forge/jobs"
    outcomes: Dict[str, Dict[str, int]] = {}

    def burst(label: str, tokens: Sequence[str]) -> None:
        bucket = outcomes.setdefault(label, {})
        for tok in tokens:
            d = gate.evaluate("GET", path, {"Authorization": f"Service {tok}"})
            bucket[str(d.http_status)] = bucket.get(str(d.http_status), 0) + 1

    old_tokens = [signer.mint("gateway", ["forge:read"]) for _ in range(50)]
    burst("pre_rotation", old_tokens)
    ring.rotate("k2", random.Random(seed + 1).randbytes(32), overlap_s=60.0)
    new_tokens = [signer.mint("gateway", ["forge:read"]) for _ in range(50)]
    clock.advance(30)
    burst("overlap_old", old_tokens)
    burst("overlap_new", new_tokens)
    clock.advance(31)
    burst("post_overlap_old", old_tokens)
    burst("post_overlap_new", new_tokens)
    ring.revoke("k2", reason="chaos")
    burst("revoked_new", new_tokens)
    r.metrics["outcomes"] = outcomes
    r.check("pre_rotation_ok", outcomes["pre_rotation"] == {"200": 50})
    r.check("overlap_old_ok", outcomes["overlap_old"] == {"200": 50})
    r.check("overlap_new_ok", outcomes["overlap_new"] == {"200": 50})
    r.check("retired_kid_401", outcomes["post_overlap_old"] == {"401": 50})
    r.check("active_after_overlap_ok", outcomes["post_overlap_new"] == {"200": 50})
    r.check("revoked_kid_401", outcomes["revoked_new"] == {"401": 50})
    r.check("never_5xx", all(not k.startswith("5") for b in outcomes.values() for k in b))
    return r


def scenario_flapping_upstream_backoff(seed: int = 29) -> ChaosReport:
    r = ChaosReport("flapping_upstream_backoff", seed)
    clock = ManualClock()
    reg = BreakerRegistry(
        clock=clock,
        default=BreakerConfig(consecutive_failures=3, min_calls=3, window_size=10, cooldown_s=2.0,
                              cooldown_multiplier=2.0, max_cooldown_s=16.0),
    )
    breaker = reg.get("flappy")
    up = FaultyUpstream(clock, FaultPlan(error_rate=1.0), seed=seed)
    pipe = Pipeline([BreakerStage(breaker)], clock=clock)
    cooldowns: List[float] = []
    probes = 0
    for _ in range(4000):
        before = up.calls
        _call(pipe, GET, up)
        if breaker.state.value == "open":
            cd = breaker.stats()["cooldown_s"]
            if not cooldowns or cooldowns[-1] != cd:
                cooldowns.append(cd)
        if up.calls > before and up.calls > 3:
            probes += 1
        clock.advance(0.01)  # 40 virtual seconds total
    r.metrics.update(cooldowns=cooldowns, probes=probes, upstream_calls=up.calls)
    r.check("cooldown_grows", cooldowns[:4] == [2.0, 4.0, 8.0, 16.0])
    r.check("cooldown_capped", max(cooldowns) == 16.0)
    r.check("probes_rare", probes <= 6)
    return r


def scenario_telemetry_failure_isolation(seed: int = 31) -> ChaosReport:
    r = ChaosReport("telemetry_failure_isolation", seed)

    class BrokenMetrics(MetricsCollector):
        def increment(self, *a: Any, **k: Any) -> None:
            raise RuntimeError("metrics backend down")

        def gauge(self, *a: Any, **k: Any) -> None:
            raise RuntimeError("metrics backend down")

        def histogram(self, *a: Any, **k: Any) -> None:
            raise RuntimeError("metrics backend down")

    def run(with_broken: bool) -> List[Any]:
        clock = ManualClock()
        up = FaultyUpstream(clock, FaultPlan(error_rate=0.3, exception_rate=0.1), seed=seed)
        breaker = CircuitBreaker("u", BreakerConfig(consecutive_failures=4, min_calls=10, window_size=20), clock=clock)
        stages: List[Any] = []
        tel = None
        if with_broken:
            tel = GateTelemetry(metrics=BrokenMetrics(), clock=clock)
            breaker.add_listener(tel.breaker_listener)
            stages.append(TelemetryStage(tel))
        stages += [RetryStage(RetrySpec(max_attempts=2, jitter=0.0), rng=random.Random(seed)), BreakerStage(breaker)]
        pipe = Pipeline(stages, clock=clock)
        out = [_call(pipe, GET, up) for _ in range(100)]
        if tel is not None:
            r.metrics["dropped"] = tel.dropped
        return out

    plain = run(False)
    broken = run(True)
    r.check("identical_verdicts", plain == broken)
    r.check("drops_counted", r.metrics.get("dropped", 0) > 0)
    return r


PACK_F_CHAOS_SCENARIOS: Dict[str, Callable[..., ChaosReport]] = {
    "brownout_breaker_trips": scenario_brownout_breaker_trips,
    "retry_storm_bounded": scenario_retry_storm_bounded,
    "deadline_caps_latency": scenario_deadline_caps_latency,
    "pack_h_outage_fallback": scenario_pack_h_outage_fallback,
    "pressure_spike_sheds": scenario_pressure_spike_sheds,
    "key_rotation_under_load": scenario_key_rotation_under_load,
    "flapping_upstream_backoff": scenario_flapping_upstream_backoff,
    "telemetry_failure_isolation": scenario_telemetry_failure_isolation,
}


def run_pack_f_chaos(name: str, seed: Optional[int] = None) -> ChaosReport:
    if name not in PACK_F_CHAOS_SCENARIOS:
        raise KeyError(f"unknown Pack F chaos scenario {name!r}")
    fn = PACK_F_CHAOS_SCENARIOS[name]
    return fn() if seed is None else fn(seed)


def run_all_pack_f_chaos(seed: Optional[int] = None) -> List[ChaosReport]:
    return [run_pack_f_chaos(n, seed) for n in PACK_F_CHAOS_SCENARIOS]


__all__ = [
    "ChaosReport",
    "FaultPlan",
    "FaultyUpstream",
    "PACK_F_CHAOS_SCENARIOS",
    "run_all_pack_f_chaos",
    "run_pack_f_chaos",
]
