"""Safe operator planning for signed durable recovery requirement changes.

The requirement store is intentionally low-level: a sufficiently authorized
operator can sign a generation that adds or removes IDs.  This module provides
a safer default workflow for ordinary operations.

Additions are always allowed: discovering a missing or incomplete terminal
execution is exactly why the required-proof set exists.  Removals are allowed
only when the end-to-end durable recovery verifier currently proves the
finalization as VERIFIED.  The plan pins both manifest generation and digest,
so it cannot be applied after another operator changes the authority set.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from skeleton.shells.ai.durable_recovery import (
    DurableRecoveryStatus,
    DurableSessionRecoveryReport,
    DurableSessionRecoveryVerifier,
)
from skeleton.shells.ai.recovery_requirements import (
    DurableRecoveryRequirementConflict,
    DurableRecoveryRequirementStore,
    SignedDurableRecoveryRequirementManifest,
)


def _ids(values: Iterable[str]) -> tuple[str, ...]:
    items = tuple(values)
    if len(items) > 4096:
        raise ValueError("recovery operator finalization bound exceeded")
    if any(
        not isinstance(item, str)
        or not item
        or len(item) > 256
        for item in items
    ):
        raise ValueError("invalid recovery operator finalization_id")
    if len(items) != len(set(items)):
        raise ValueError("duplicate recovery operator finalization_id")
    return tuple(sorted(items))


@dataclass(frozen=True)
class RecoveryRequirementRemovalCheck:
    finalization_id: str
    status: DurableRecoveryStatus
    report_digest: str
    removable: bool
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.finalization_id or len(self.finalization_id) > 256:
            raise ValueError("invalid removal finalization_id")
        object.__setattr__(
            self,
            "status",
            DurableRecoveryStatus(self.status),
        )
        if len(self.report_digest) != 64:
            raise ValueError("removal report_digest must be 64 characters")
        if not isinstance(self.removable, bool):
            raise ValueError("removable must be bool")
        if len(self.reason) > 2048:
            raise ValueError("removal reason too long")
        if self.removable and self.status is not DurableRecoveryStatus.VERIFIED:
            raise ValueError("only verified finalization may be removable")

    def to_dict(self) -> dict[str, object]:
        return {
            "finalization_id": self.finalization_id,
            "status": self.status.value,
            "report_digest": self.report_digest,
            "removable": self.removable,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RecoveryRequirementChangePlan:
    scope: str
    base_generation: int
    base_manifest_digest: str
    current_ids: tuple[str, ...]
    desired_ids: tuple[str, ...]
    additions: tuple[str, ...]
    removals: tuple[str, ...]
    removal_checks: tuple[RecoveryRequirementRemovalCheck, ...]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.scope or len(self.scope) > 128:
            raise ValueError("invalid recovery change scope")
        if (
            isinstance(self.base_generation, bool)
            or not isinstance(self.base_generation, int)
            or self.base_generation <= 0
        ):
            raise ValueError("base_generation must be positive")
        if len(self.base_manifest_digest) != 64:
            raise ValueError("base_manifest_digest must be 64 characters")
        for name in (
            "current_ids",
            "desired_ids",
            "additions",
            "removals",
        ):
            object.__setattr__(
                self,
                name,
                _ids(getattr(self, name)),
            )
        object.__setattr__(
            self,
            "removal_checks",
            tuple(self.removal_checks),
        )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )
        expected_additions = tuple(
            sorted(set(self.desired_ids) - set(self.current_ids))
        )
        expected_removals = tuple(
            sorted(set(self.current_ids) - set(self.desired_ids))
        )
        if self.additions != expected_additions:
            raise ValueError("plan additions differ from desired/current delta")
        if self.removals != expected_removals:
            raise ValueError("plan removals differ from desired/current delta")
        if tuple(
            item.finalization_id
            for item in self.removal_checks
        ) != self.removals:
            raise ValueError("removal checks do not match removals")

    @property
    def allowed(self) -> bool:
        return (
            not self.reasons
            and all(
                item.removable
                for item in self.removal_checks
            )
        )

    @property
    def changed(self) -> bool:
        return bool(self.additions or self.removals)

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "scope": self.scope,
            "base_generation": self.base_generation,
            "base_manifest_digest": self.base_manifest_digest,
            "current_ids": list(self.current_ids),
            "desired_ids": list(self.desired_ids),
            "additions": list(self.additions),
            "removals": list(self.removals),
            "removal_checks": [
                item.to_dict()
                for item in self.removal_checks
            ],
            "reasons": list(self.reasons),
            "allowed": self.allowed,
            "changed": self.changed,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class RecoveryRequirementOperatorError(RuntimeError):
    pass


class DurableRecoveryRequirementOperator:
    """Plan and apply safe required-proof set changes."""

    def __init__(
        self,
        store: DurableRecoveryRequirementStore,
        verifier: DurableSessionRecoveryVerifier,
    ) -> None:
        if not isinstance(store, DurableRecoveryRequirementStore):
            raise TypeError("store must be DurableRecoveryRequirementStore")
        if not isinstance(verifier, DurableSessionRecoveryVerifier):
            raise TypeError("verifier must be DurableSessionRecoveryVerifier")
        self.store = store
        self.verifier = verifier

    def _removal_check(
        self,
        finalization_id: str,
    ) -> tuple[RecoveryRequirementRemovalCheck, DurableSessionRecoveryReport]:
        report = self.verifier.verify(finalization_id)
        removable = report.status is DurableRecoveryStatus.VERIFIED
        reason = (
            ""
            if removable
            else (
                "required finalization may not be retired while durable "
                f"recovery status is {report.status.value}"
            )
        )
        return (
            RecoveryRequirementRemovalCheck(
                finalization_id,
                report.status,
                report.digest,
                removable,
                reason,
            ),
            report,
        )

    def plan(
        self,
        scope: str,
        desired_ids: Iterable[str],
    ) -> RecoveryRequirementChangePlan:
        current = self.store.current(scope)
        if current is None:
            raise RecoveryRequirementOperatorError(
                "recovery requirement scope is not initialized"
            )
        _, item = current
        manifest = item.manifest
        desired = _ids(desired_ids)
        current_ids = manifest.finalization_ids
        additions = tuple(
            sorted(set(desired) - set(current_ids))
        )
        removals = tuple(
            sorted(set(current_ids) - set(desired))
        )

        checks: list[RecoveryRequirementRemovalCheck] = []
        reasons: list[str] = []
        for finalization_id in removals:
            try:
                check, _ = self._removal_check(finalization_id)
            except Exception as exc:
                check = RecoveryRequirementRemovalCheck(
                    finalization_id,
                    DurableRecoveryStatus.MANUAL_REVIEW,
                    hashlib.sha256(
                        (
                            "operator-removal-probe-error:"
                            + type(exc).__name__
                            + ":"
                            + finalization_id
                        ).encode()
                    ).hexdigest(),
                    False,
                    (
                        "required finalization verification raised "
                        f"{type(exc).__name__}"
                    ),
                )
            checks.append(check)
            if not check.removable:
                reasons.append(check.reason)

        return RecoveryRequirementChangePlan(
            manifest.scope,
            manifest.generation,
            manifest.digest,
            current_ids,
            desired,
            additions,
            removals,
            tuple(checks),
            tuple(reasons),
        )

    def require_plan(
        self,
        scope: str,
        desired_ids: Iterable[str],
    ) -> RecoveryRequirementChangePlan:
        plan = self.plan(scope, desired_ids)
        if not plan.allowed:
            raise RecoveryRequirementOperatorError(
                plan.reasons[0]
                if plan.reasons
                else "recovery requirement change plan denied"
            )
        return plan

    def _require_fresh(
        self,
        plan: RecoveryRequirementChangePlan,
    ) -> SignedDurableRecoveryRequirementManifest:
        current = self.store.current(plan.scope)
        if current is None:
            raise RecoveryRequirementOperatorError(
                "recovery requirement scope disappeared"
            )
        _, item = current
        manifest = item.manifest
        if manifest.generation != plan.base_generation:
            raise RecoveryRequirementOperatorError(
                "recovery requirement plan generation is stale"
            )
        if manifest.digest != plan.base_manifest_digest:
            raise RecoveryRequirementOperatorError(
                "recovery requirement plan digest is stale"
            )
        if manifest.finalization_ids != plan.current_ids:
            raise RecoveryRequirementOperatorError(
                "recovery requirement plan current set is stale"
            )
        return item

    def apply(
        self,
        plan: RecoveryRequirementChangePlan,
        *,
        change_id: str,
        reason: str,
    ) -> SignedDurableRecoveryRequirementManifest:
        if not isinstance(plan, RecoveryRequirementChangePlan):
            raise TypeError("plan must be RecoveryRequirementChangePlan")
        if not plan.allowed:
            raise RecoveryRequirementOperatorError(
                plan.reasons[0]
                if plan.reasons
                else "recovery requirement plan is not allowed"
            )
        if not plan.changed:
            raise RecoveryRequirementOperatorError(
                "recovery requirement plan contains no change"
            )
        current = self._require_fresh(plan)

        # Removal authority can become stale even when the manifest has not
        # changed, because evidence may be corrupted or deleted after planning.
        for expected in plan.removal_checks:
            fresh, _ = self._removal_check(
                expected.finalization_id
            )
            if not fresh.removable:
                raise RecoveryRequirementOperatorError(
                    fresh.reason
                )
            if fresh.report_digest != expected.report_digest:
                raise RecoveryRequirementOperatorError(
                    "recovery removal proof changed after planning"
                )

        try:
            return self.store.rollover(
                plan.scope,
                plan.desired_ids,
                expected_generation=current.manifest.generation,
                change_id=change_id,
                reason=reason,
            )
        except DurableRecoveryRequirementConflict as exc:
            raise RecoveryRequirementOperatorError(
                "recovery requirement change lost authority race"
            ) from exc
