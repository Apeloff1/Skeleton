"""Machine manifest of the landed P2 spine seams.

Lists names and laws. It does not dispatch and it does not sign work off.
"""

from __future__ import annotations

from typing import Any


SEAMS = (
    ("inbox", "exactly-once"),
    ("fence", "tenant-epoch-cas"),
    ("projection", "published-outbox-to-fence"),
    ("mongo-inbox", "exactly-once"),
    ("mongo-fence", "tenant-epoch-cas"),
    ("hook", "dispatch-project-cursor"),
    ("worker", "composed-drain"),
    ("batch", "bounded-batch-project"),
    ("witness", "lag-catalog-status"),
    ("drift", "fence-epoch-parity"),
    ("sweep", "bounded-drift-sweep"),
    ("replay", "replay-does-not-advance"),
    ("hold", "hold-does-not-apply"),
    ("export", "quarantine-json"),
    ("digest", "sha256-gap-drift"),
    ("ledger", "append-digest"),
    ("reaccept", "digest-stable-reaccept"),
    ("gate", "held-id-refused"),
    ("watch", "epoch-unchanged"),
    ("poison-ticket", "ticket-requires-hold"),
    ("poison-apply", "hold-digest-stable-epoch-unchanged"),
    ("poison-witness", "tenant-isolated-journal"),
    ("poison-chain", "journal-hash-chain"),
    ("dispatch-guard", "dispatcher-identity-unchanged"),
    ("index-bind", "create-index-only-when-present"),
    ("bind-audit", "bind-does-not-start-dispatcher"),
    ("cut-gate", "switch-refused"),
    ("surface", "surface-not-claimed"),
    ("provider-probe", "provider-surface-unclaimed"),
    ("pr-probe", "pr-automation-unclaimed"),
    ("unread-gap", "tenant-sequence-gap"),
    ("surface-seal", "green-claim-stripped"),
    ("ci-witness", "ci-green-unread"),
    ("merge-gate", "merge-refused"),
    ("probe-replay", "replay-does-not-insert"),
    ("motor-witness", "motor-not-imported"),
    ("dispatch-witness", "dispatcher-not-started"),
    ("dark", "unwired-surfaces-stay-dark"),
    ("epoch-witness", "side-card-epoch-unchanged"),
    ("quiet", "dark-card-not-rewritten"),
    ("quiet-witness", "quiet-row-stays-dark"),
    ("bind-card", "bind-card-stays-dark"),
    ("bind-journal", "bind-card-not-rewritten"),
    ("bind-read", "bind-row-stays-dark"),
    ("bind-chain", "bind-journal-hash-chain"),
    ("bind-tenant", "bind-tenant-isolated"),
    ("bind-replay", "bind-replay-does-not-insert"),
    ("bind-surface", "bind-surface-stays-unread"),
    ("bind-gap", "bind-gap-not-filled"),
    ("bind-snapshot", "bind-snapshot-stays-unactivated"),
    ("bind-recovery", "recovery-plan-does-not-activate"),
    ("bind-checkpoint", "checkpoint-is-immutable-and-unactivated"),
    ("bind-checkpoint-replay", "checkpoint-replay-does-not-insert"),
    ("bind-checkpoint-tenant", "checkpoint-tenant-isolated"),
    ("bind-checkpoint-chain", "checkpoint-hash-chain"),
    ("bind-bundle", "checkpoint-bundle-is-not-activation"),
    ("bind-bundle-verify", "bundle-verification-does-not-activate"),
)


class SpineManifest:
    """Return the seam list. hit stays false because apply is not landed."""

    def card(self) -> dict[str, Any]:
        return {
            "kind": "spine_manifest",
            "hit": False,
            "law": "manifest-is-not-signoff",
            "citation": "VOL-134",
            "seams": [{"name": name, "law": law} for name, law in SEAMS],
            "count": len(SEAMS),
            "apply_landed": False,
            "poison_apply_landed": True,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
