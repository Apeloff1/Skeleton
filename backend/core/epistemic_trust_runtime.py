"""Unified epistemic publication and finality runtime.

This runtime is the single owner of transparency publication, peer gossip,
transport-authenticated witnesses, Ed25519 signed witnesses, and quorum finality.
Scientific verification and publication finality remain separate concerns.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from core.epistemic_transparency import EpistemicTransparency
from core.signed_transparency_witness import SignedTransparencyWitnessLedger, SignedWitnessStatement
from core.transparency_finality import FinalityBlocked, TransparencyFinality
from core.transparency_gossip import TransparencyGossip
from core.transparency_witness import TransparencyWitnessLedger, WitnessReceipt
from core.transparency_witness_config import WitnessPolicyConfig, load_witness_policy


class EpistemicTrustRuntime:
    def __init__(self, root: str | Path, *, policy: WitnessPolicyConfig | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.policy = policy or load_witness_policy()
        self.transparency = EpistemicTransparency(self.root / "transparency")
        self.gossip = TransparencyGossip(self.root / "gossip")
        self.witnesses = TransparencyWitnessLedger(
            self.root / "witnesses",
            trusted_witnesses=self.policy.witnesses,
            required_groups=self.policy.required_groups,
            max_age_seconds=self.policy.max_age_seconds,
        )
        self.signed_witnesses = SignedTransparencyWitnessLedger(
            self.root / "signed-witnesses",
            trusted_witnesses=self.policy.witnesses,
            required_groups=self.policy.required_groups,
            max_age_seconds=self.policy.max_age_seconds,
        )
        self.finality = TransparencyFinality(
            self.root / "finality",
            transparency=self.transparency,
            gossip=self.gossip,
            witnesses=self.witnesses,
            signed_witnesses=self.signed_witnesses,
            require_signed_quorum=self.policy.signed_finality_required,
        )

    def publish(
        self,
        *,
        authority_root_sha256: str,
        epistemic_root_sha256: str,
        observed_at: str | None = None,
        source: str = "local-control-plane",
    ) -> dict[str, Any]:
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
            log_id=after["log_id"],
            tree_size=after["tree_size"],
            root_sha256=after["root_sha256"],
            source=source,
            consistency=consistency,
        )
        return {**published, "gossip": gossip_result, "trust": self.status()}

    def observe_peer_head(
        self,
        *,
        log_id: str,
        tree_size: int,
        root_sha256: str,
        source: str,
        consistency=None,
    ) -> dict[str, Any]:
        return self.gossip.observe(
            log_id=log_id,
            tree_size=tree_size,
            root_sha256=root_sha256,
            source=source,
            consistency=consistency,
        )

    def observe_witness(
        self,
        *,
        log_id: str,
        tree_size: int,
        root_sha256: str,
        witness_id: str,
        transport_authenticated: bool,
        observed_at: str | None = None,
    ) -> WitnessReceipt:
        return self.witnesses.observe(
            log_id=log_id,
            tree_size=tree_size,
            root_sha256=root_sha256,
            witness_id=witness_id,
            transport_authenticated=transport_authenticated,
            observed_at=observed_at,
        )

    def observe_signed_witness(
        self,
        statement: SignedWitnessStatement | Mapping[str, Any],
    ) -> SignedWitnessStatement:
        return self.signed_witnesses.observe(statement)

    def finalize(self, *, finalized_at: str | None = None) -> dict[str, Any]:
        return asdict(self.finality.finalize(finalized_at=finalized_at))

    def finality_for_current_head(self) -> dict[str, Any]:
        descriptor = self.transparency.log.descriptor()
        latest = self.finality.latest()
        matches = bool(
            latest
            and latest.tree_size == descriptor["tree_size"]
            and latest.root_sha256 == descriptor["root_sha256"]
        )
        signed_verified = False
        if matches and self.policy.signed_finality_required:
            when = datetime.fromisoformat(latest.finalized_at.replace("Z", "+00:00"))
            if when.tzinfo is None:
                matches = False
            else:
                quorum = self.signed_witnesses.quorum(
                    log_id=latest.log_id,
                    tree_size=latest.tree_size,
                    root_sha256=latest.root_sha256,
                    now=when.astimezone(UTC),
                )
                signed_verified = (
                    quorum.reached
                    and quorum.attestation_sha256 == latest.witness_quorum_sha256
                    and quorum.groups == latest.witness_groups
                )
                matches = matches and signed_verified
        return {
            "current_tree_size": descriptor["tree_size"],
            "current_root_sha256": descriptor["root_sha256"],
            "finalized": matches,
            "signed_finality_verified": signed_verified,
            "latest": asdict(latest) if latest else None,
        }

    def signed_finality_evidence(self) -> dict[str, Any] | None:
        latest = self.finality.latest()
        if latest is None or not self.policy.signed_finality_required:
            return None
        when = datetime.fromisoformat(latest.finalized_at.replace("Z", "+00:00")).astimezone(UTC)
        return {
            "finality": asdict(latest),
            "witness_evidence": self.signed_witnesses.evidence(
                log_id=latest.log_id,
                tree_size=latest.tree_size,
                root_sha256=latest.root_sha256,
                now=when,
            ),
        }

    def status(self) -> dict[str, Any]:
        transparency = self.transparency.health()
        gossip = self.gossip.status()
        witnesses = self.witnesses.status()
        signed = self.signed_witnesses.status()
        finality = self.finality.status()
        current = self.finality_for_current_head()
        configured_groups = witnesses["independence_groups"]
        signed_groups = signed["independence_groups"]
        configured = witnesses["trusted_witnesses"] > 0
        integrity_healthy = bool(
            transparency.get("verified")
            and transparency.get("prefix_aligned")
            and gossip.get("healthy")
            and gossip.get("cross_process_locking")
            and witnesses.get("healthy")
            and witnesses.get("cross_process_locking")
            and signed.get("healthy")
            and signed.get("cross_process_locking")
            and finality.get("verified")
            and finality.get("cross_process_locking")
        )
        quorum_capable = configured_groups >= self.policy.required_groups
        signed_quorum_capable = signed_groups >= self.policy.required_groups
        finality_satisfied = bool(current["finalized"])
        deploy_ready = integrity_healthy and (
            finality_satisfied if self.policy.finality_required else True
        )
        if self.policy.signed_finality_required:
            deploy_ready = (
                deploy_ready
                and finality_satisfied
                and signed_quorum_capable
                and current["signed_finality_verified"]
            )
        return {
            "transparency": transparency,
            "gossip": gossip,
            "witnesses": witnesses,
            "signed_witnesses": signed,
            "finality": finality,
            "current_head": current,
            "policy": {
                "configured": configured,
                "configured_independence_groups": configured_groups,
                "signed_independence_groups": signed_groups,
                "required_groups": self.policy.required_groups,
                "max_age_seconds": self.policy.max_age_seconds,
                "quorum_capable": quorum_capable,
                "signed_quorum_capable": signed_quorum_capable,
                "finality_required": self.policy.finality_required,
                "signed_finality_required": self.policy.signed_finality_required,
            },
            "integrity_healthy": integrity_healthy,
            "finality_satisfied": finality_satisfied,
            "deploy_ready": deploy_ready,
            "healthy": deploy_ready,
        }

    def maybe_finalize(self, *, finalized_at: str | None = None) -> dict[str, Any]:
        try:
            return {
                "finalized": True,
                "record": self.finalize(finalized_at=finalized_at),
                "blocked_reason": "",
            }
        except FinalityBlocked as exc:
            return {"finalized": False, "record": None, "blocked_reason": str(exc)}
