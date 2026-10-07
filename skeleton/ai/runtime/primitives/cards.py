"""Card constructor. stored_prose is forced to 0."""

from __future__ import annotations

from typing import Any, Mapping

from skeleton.primitives.errors import CardError
from skeleton.primitives.law import CITATION, PACKET, STORED_PROSE


REQUIRED = ("kind", "hit", "law", "citation", "stored_prose")


def primitive_card(
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


def assert_card(card: Mapping[str, Any]) -> None:
    missing = [k for k in REQUIRED if k not in card]
    if missing:
        raise CardError("missing:" + ",".join(missing))
    if int(card["stored_prose"]) != 0:
        raise CardError("stored_prose")
    if not card.get("kind"):
        raise CardError("kind")
