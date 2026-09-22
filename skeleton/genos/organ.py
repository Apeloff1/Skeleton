"""genos organ. Reads the coil after forge emit."""

from __future__ import annotations

from pathlib import Path

from skeleton.genos.helix import DNAHelix


class Genos:
    def __init__(self, helix: DNAHelix | None = None, root: Path | None = None) -> None:
        self.helix = helix or DNAHelix(root)

    def pulse(self) -> dict:
        pairs = self.helix.read()
        return {
            "kind": "genos",
            "n": len(pairs),
            "pairs": pairs,
            "path": str(self.helix.path),
            "stored_prose": 0,
        }

    def forge_emit(self, vision: str = "extraction") -> dict:
        self.helix.emit("forge", vision)
        return self.pulse()
