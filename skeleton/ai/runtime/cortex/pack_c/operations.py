"""Pack C operations facade."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from skeleton.cortex.pack_c.amalgam_policy import AmalgamPolicy, decide_amalgam
from skeleton.cortex.pack_c.hybrid_router import HybridRouter, Stimulus
from skeleton.cortex.pack_c.ledger_hybrid import HybridLedger, mint_entry
from skeleton.cortex.pack_c.telemetry import CortexPackTelemetry
from skeleton.cortex.pack_c.persistence import HybridPersistence, demo_state
from skeleton.cortex.pack_c.contracts import PackCManifest


@dataclass
class PackCOperations:
    router: HybridRouter = field(default_factory=HybridRouter)
    policy: AmalgamPolicy = field(default_factory=AmalgamPolicy)
    ledger: HybridLedger = field(default_factory=HybridLedger)
    telemetry: CortexPackTelemetry = field(default_factory=CortexPackTelemetry)
    persistence: HybridPersistence = field(default_factory=HybridPersistence)
    manifest: PackCManifest = field(default_factory=PackCManifest)

    def boot(self) -> Dict[str, Any]:
        self.manifest.locks.validate()
        self.telemetry.mark_pfc_lock()
        plan = self.router.plan(Stimulus(text="pack-c-boot", urgency=0.4))
        self.router.assert_pfc_lock(plan)
        self.ledger.append(mint_entry(0, slot="pfc", kind="own"))
        return {
            "manifest": self.manifest.as_dict(),
            "route": plan.as_dict(),
            "telemetry": self.telemetry.snapshot().as_dict(),
        }

    def amalgam_unfitted(self, text: str = "tape") -> Dict[str, Any]:
        d = decide_amalgam(lm=None, composed_text=text)
        self.telemetry.mark_amalgam(d.kind)
        return d.as_dict()

    def snapshot(self) -> str:
        state = demo_state()
        state["ledger"] = self.ledger.snapshot()
        return self.persistence.dump(state)
