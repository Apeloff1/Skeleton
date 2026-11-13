"""Localization.
Maps keys to strings for dialogue, UI, and ending titles.
"""
from __future__ import annotations
from typing import Any, Dict

STRINGS = {
    "en": {
        "intro": "The ash settles. You move.",
        "extract": "You choose to leave.",
        "legend": "Ash legend",
        "grade_s": "Perfect run",
    },
    "no": {
        "intro": "Asken legger seg. Du beveger deg.",
        "extract": "Du velger \u00e5 forlate.",
        "legend": "Askelegende",
        "grade_s": "Perfekt l\u00f8p",
    },
}

class Localization:
    def __init__(self, lang: str = "en"):
        self.lang = lang if lang in STRINGS else "en"
    def get(self, key: str) -> str:
        return STRINGS.get(self.lang, STRINGS["en"]).get(key, key)
    def set_lang(self, lang: str) -> None:
        if lang in STRINGS:
            self.lang = lang
