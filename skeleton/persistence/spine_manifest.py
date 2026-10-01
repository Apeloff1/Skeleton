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
