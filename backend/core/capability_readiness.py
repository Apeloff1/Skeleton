"""Evidence-backed readiness for canonical product actions.

Executor binding alone is not convergence. An action is native-ready only when
its canonical policy exists, an exact executor contract is bound, stateful or
external effects are replay-safe, the effect class is explicit, and the runtime
uses provenance-capable receipt generation. The full matrix is canonical and
SHA-256 attested so readiness can be compared across restarts and deployments.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class ActionReadiness:
    capability_id: str
    action: str
    state: str
    policy_present: bool
    executor_bound: bool
    replay_safe: bool
    effect_class: str | None
    executor_name: str | None
    executor_version: int | None
    provenance_ready: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    canonical_actions: int
    ready_actions: int
    ready_pct: float
    governed_unbound: int
    unsafe_actions: int
    policy_gaps: int
    actions: tuple[ActionReadiness, ...]
    attestation_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def evaluate_readiness(
    *,
    canonical_policy: Iterable[Any],
    policy_domains: Iterable[dict[str, Any]],
    executor_bindings: Iterable[dict[str, Any]],
    receipt_stats: dict[str, Any],
) -> ReadinessReport:
    policy_actions = {
        (str(domain.get("domain")), str(rule.get("action")))
        for domain in policy_domains
        for rule in domain.get("rules", ())
        if domain.get("domain") and isinstance(rule, dict) and rule.get("action")
    }
    bindings = {
        (str(item.get("capability_id")), str(item.get("action"))): item
        for item in executor_bindings
        if item.get("capability_id") and item.get("action")
    }
    provenance_ready = int(receipt_stats.get("version", 0) or 0) >= 2

    actions: list[ActionReadiness] = []
    for domain in canonical_policy:
        capability_id = str(domain.domain)
        for action in domain.actions:
            action = str(action)
            policy_present = (capability_id, action) in policy_actions
            binding = bindings.get((capability_id, action))
            executor_bound = binding is not None
            effect_class = str(binding.get("effect_class")) if binding is not None else None
            version = int(binding.get("version", 0)) if binding is not None else None
            replay_safe = bool(binding.get("replay_safe")) if binding is not None else False
            executor_name = str(binding.get("name")) if binding is not None else None

            blockers: list[str] = []
            if not policy_present:
                blockers.append("policy_missing")
            if not executor_bound:
                blockers.append("executor_unbound")
            if executor_bound and effect_class not in {"query", "state", "external"}:
                blockers.append("effect_class_invalid")
            if executor_bound and effect_class in {"state", "external"} and not replay_safe:
                blockers.append("effect_not_replay_safe")
            if executor_bound and (version is None or version <= 0):
                blockers.append("executor_version_invalid")
            if executor_bound and not provenance_ready:
                blockers.append("provenance_unavailable")

            if not policy_present:
                state = "policy_gap"
            elif not executor_bound:
                state = "governed_unbound"
            elif blockers:
                state = "unsafe"
            else:
                state = "native_ready"

            actions.append(ActionReadiness(
                capability_id=capability_id,
                action=action,
                state=state,
                policy_present=policy_present,
                executor_bound=executor_bound,
                replay_safe=replay_safe,
                effect_class=effect_class,
                executor_name=executor_name,
                executor_version=version,
                provenance_ready=provenance_ready,
                blockers=tuple(blockers),
            ))

    actions.sort(key=lambda item: (item.capability_id, item.action))
    ready = sum(item.state == "native_ready" for item in actions)
    governed_unbound = sum(item.state == "governed_unbound" for item in actions)
    unsafe = sum(item.state == "unsafe" for item in actions)
    gaps = sum(item.state == "policy_gap" for item in actions)
    total = len(actions)
    payload = {
        "canonical_actions": total,
        "ready_actions": ready,
        "ready_pct": round((ready / total) * 100, 1) if total else 100.0,
        "governed_unbound": governed_unbound,
        "unsafe_actions": unsafe,
        "policy_gaps": gaps,
        "actions": [asdict(item) for item in actions],
    }
    return ReadinessReport(
        canonical_actions=total,
        ready_actions=ready,
        ready_pct=payload["ready_pct"],
        governed_unbound=governed_unbound,
        unsafe_actions=unsafe,
        policy_gaps=gaps,
        actions=tuple(actions),
        attestation_sha256=_digest(payload),
    )


def verify_readiness(report: ReadinessReport) -> bool:
    payload = {
        "canonical_actions": report.canonical_actions,
        "ready_actions": report.ready_actions,
        "ready_pct": report.ready_pct,
        "governed_unbound": report.governed_unbound,
        "unsafe_actions": report.unsafe_actions,
        "policy_gaps": report.policy_gaps,
        "actions": [asdict(item) for item in report.actions],
    }
    return _digest(payload) == report.attestation_sha256
