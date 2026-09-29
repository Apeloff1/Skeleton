"""GB-48 era admit. Citation token required. Spaced text is refused."""

from __future__ import annotations


def admit(card: dict) -> dict:
    raw = card.get("citation")
    token = raw if isinstance(raw, str) else ""
    ok = 1 if token and " " not in token else 0
    return {
        "kind": "era-admit",
        "ok": ok,
        "citation": token if ok else "",
        "stored_prose": 0,
    }
