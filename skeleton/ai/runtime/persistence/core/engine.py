"""Exercise both persist gates."""

from __future__ import annotations

from typing import Any

from skeleton.persist.cards import persist_card
from skeleton.persist.store import Persist


class PersistEngine:
    def snapshot(self, disk_root: str | None = None) -> dict[str, Any]:
        local = Persist(env={})
        local.put("deck", "k", "v")
        local.put("jeeves", "j", "1")
        disk = Persist(env={"SKELETON_OWN": disk_root or ""})
        if disk_root:
            disk.put("helix", "obs", "1")
            disk.put("rotors", "r0", "on")
            disk.put("traces", "t0", "ok")
        paths = disk.disk_paths()
        ok = (
            local.gate() == "local"
            and local.has_local("deck", "k")
            and local.has_local("jeeves", "j")
            and (not disk_root or (paths["helix"] and paths["rotors"] and paths["traces"]))
        )
        return persist_card(
            kind="persist",
            hit=1 if ok else 0,
            law="persist 1.0",
            extra={"local_gate": local.gate(), "disk_gate": disk.gate()},
        )
