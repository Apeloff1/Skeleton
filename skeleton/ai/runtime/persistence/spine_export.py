"""Write a quarantine card to disk.

The file is a JSON card. It does not repair poison and it does not advance a fence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skeleton.persistence.spine_quarantine import SpineQuarantine


class SpineExportError(RuntimeError):
    """Export rejected its inputs. Not a maturity signal."""


class SpineExport:
    """Persist one tenant quarantine card."""

    def __init__(self, quarantine: SpineQuarantine) -> None:
        if not isinstance(quarantine, SpineQuarantine):
            raise SpineExportError("quarantine must be a SpineQuarantine")
        self.quarantine = quarantine

    def write(self, path: str | Path, *, tenant_id: str) -> dict[str, Any]:
        target = Path(path)
        card = self.quarantine.card(tenant_id)
        card["exported"] = True
        target.write_text(json.dumps(card, sort_keys=True), encoding="utf-8")
        return card
