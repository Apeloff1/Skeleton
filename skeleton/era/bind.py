"""Like-titles resolve to HOUSE_ERA. Same resolver for plan/cut/speak/forge."""

from __future__ import annotations

from skeleton.era.law import HOUSE_ERA, HOUSE_URL

LIKE = {
    "house": HOUSE_ERA,
    "extraction": HOUSE_ERA,
    "extract": HOUSE_ERA,
    "default": HOUSE_ERA,
}


class EraBind:
    def __init__(self) -> None:
        self.era = HOUSE_ERA

    def resolve(self, vision: str | None = None) -> dict:
        key = (vision or "house").strip().lower()
        era = LIKE.get(key, self.era if key == self.era.lower() else HOUSE_ERA)
        if key not in LIKE and key != HOUSE_ERA.lower() and vision:
            era = vision.strip()
            self.era = era
        return {
            "title": vision or "house",
            "era": era,
            "citation": "era_bind",
            "url": HOUSE_URL,
            "stored_prose": 0,
        }

    def cut(self, era: str) -> dict:
        self.era = era or HOUSE_ERA
        return self.resolve(self.era)

    def plan(self, vision: str | None = None) -> dict:
        return self.resolve(vision or self.era)

    def speak(self, vision: str | None = None) -> dict:
        return self.resolve(vision or self.era)


era_bind = EraBind()
