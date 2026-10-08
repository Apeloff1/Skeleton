"""Deck pointer. Does not import or rewrite the operator deck."""

from __future__ import annotations

from volume_forge.gate import gate


def card() -> dict[str, object]:
    body = gate()
    return {"plane": "volume", "verb": "cite", "url": "pointer://volume/eight", "stored_prose": 0, "ok": body["ok"], "eight_lines": body["eight_lines"], "x100_full": False}


if __name__ == "__main__":
    print(card())
