"""HOAG cards. stored_prose forced to 0."""

from __future__ import annotations

from typing import Any, Mapping

from skeleton.hoag.law import CITATION, PACKET, STORED_PROSE


def hoag_card(
    *,
    kind: str,
    hit: int,
    law: str,
    citation: str = CITATION,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    card: dict[str, Any] = {
        "kind": kind,
        "hit": int(hit),
        "law": law,
        "citation": citation,
        "packet": PACKET,
        "stored_prose": STORED_PROSE,
    }
    if extra:
        for key, value in extra.items():
            if key == "stored_prose":
                continue
            card[key] = value
    card["stored_prose"] = STORED_PROSE
    return card
