"""Unified epistemic publication/trust runtime.

This replaces duplicated transparency wiring across product surfaces. One runtime
owns append-only publication, gossip/fork detection, trusted witness quorum, and
hash-chained finality. Scientific truth and publication finality remain distinct:
finality proves a committed state was consistently witnessed, not that its claims
are scientifically correct.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.epistemic_transparency import EpistemicTransparency
from core.transparency_finality import FinalityBlocked, TransparencyFinality
from core.transparency_gossip import TransparencyGossip
from core.transparency_witness import TransparencyWitnessLedger, WitnessReceipt
from core.transparency_witness_config import WitnessPolicyConfig, load_witness_policy


class EpistemicTrustRuntime:
    def __init__(self, root: str | Path, *, policy: WitnessPolicyConfig | None = None) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.policy = policy or load_witness_policy()
        self.transparency = EpistemicTransparency(self.root / "transparency")
        self.gossip = TransparencyGossip(self.root / "gossip")
        self.witnesses = TransparencyWitnessLedger(
            self.root / "witnesses", trusted_witnesses=self.policy.witnesses,
            required_groups=self.policy.required_groups,
        )
        self.finality = TransparencyFinality(
            self.root / "finality", transparency=self.transparency,
            gossip=self.gossip, witnesses=self.witnesses,
        )

    def publish(self, *, authority_root_sha256: str, epistemic_root_sha256: str,
                observed_at: str | None = None, source: str = "local-control-plane") -> dict[str, Any]:
        before = self.transparency.log.descriptor()
        published = self.transparency.publish(
            authority_root_sha256=authority_root_sha256,
            epistemic_root_sha256=epistemic_root_sha256,
            observed_at=observed_at,
        )
        after = published["transparency"]
        consistency = None
        if before["tree_size"] and after["tree_size"] > before["tree_size"]:
            consistency = self.transparency.log.consistency(before["tree_size"])
        gossip_result = self.gossip.observe(
            log_id=after["log_id"], tree_size=after["tree_size"], root_sha256=after["root_sha256"],
            source=source, consistency=consistency,
        )
        return {**published, "gossip": gossip_result, "trust": self.status()}

    def observe_peer_head(self, *, log_id: str, tree_size: int, root_sha256: str, source: str,
                          consistency=None) -> dict[str, Any]:
        return self.gossip.observe(log_id=log_id, tree_size=tree_size, root_sha256=root_sha256,
                                   source=source, consistency=consistency)

    def observe_witness(self, *, log_id: str, tree_size: int, root_sha256: str, witness_id: str,
                        transport_authenticated: bool, observed_at: str | None = None) -> WitnessReceipt:
        return self.witnesses.observe(
            log_id=log_id, tree_size=tree_size, root_sha256=root_sha256,
            witness_id=witness_id, transport_authenticated=transport_authenticated,
            observed_at=observed_at,
        )

    def finalize(self, *, finalized_at: str | None = None) -> dict[str, Any]:
        record = self.finality.finalize(finalized_at=finalized_at)
        return asdict(record)

    def finality_for_current_head(self) -> dict[str, Any]:
        descriptor = self.transparency.log.descriptor(); latest = self.finality.latest()
        finalized = bool(latest and latest.tree_size == descriptor["tree_size"] and latest.root_sha256 == descriptor["root_sha256"])
        return {"current_tree_size": descriptor["tree_size"], "current_root_sha256": descriptor["root_sha256"],
                "finalized": finalized, "latest": asdict(latest) if latest else None}

    def status(self) -> dict[str, Any]:
        transparency = self.transparency.health(); gossip = self.gossip.status()
        witnesses = self.witnesses.status(); finality = self.finality.status()
        current = self.finality_for_current_head()
        configured_groups = witnesses["independence_groups"]
        configured = witnesses["trusted_witnesses"] > 0
        healthy = bool(transparency.get("verified") and gossip.get("healthy") and witnesses.get("healthy") and finality.get("verified"))
        if self.policy.finality_required:
            healthy = healthy and current["finalized"]
        return {
            "transparency": transparency,
            "gossip": gossip,
            "witnesses": witnesses,
            "finality": finality,
            "current_head": current,
            "policy": {"configured": configured, "configured_independence_groups": configured_groups,
                       "required_groups": self.policy.required_groups,
                       "finality_required": self.policy.finality_required},
            "healthy": healthy,
        }

    def maybe_finalize(self) -> dict[str, Any]:
        try:
            return {"finalized": True, "record": self.finalize(), "blocked_reason": ""}
        except FinalityBlocked as exc:
            return {"finalized": False, "record": None, "blocked_reason": str(exc)}
