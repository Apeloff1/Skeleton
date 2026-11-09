"""Card schema for the artifact plane. stored_prose is always 0."""

from __future__ import annotations

from typing import Any, Mapping


def plane_card(
    *,
    kind: str,
    hit: int,
    law: str,
    citation: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    card: dict[str, Any] = {
        "kind": kind,
        "hit": int(hit),
        "law": law,
        "citation": citation,
        "stored_prose": 0,
    }
    if extra:
        for key, value in extra.items():
            if key == "stored_prose":
                continue
            card[key] = value
    card["stored_prose"] = 0
    return card
