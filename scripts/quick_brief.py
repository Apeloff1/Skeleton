#!/usr/bin/env python3
"""Tiny standalone brief generator. No Skeleton imports required.

Usage: python3 quick_brief.py "Game Title" adventure 16bit
"""

from __future__ import annotations

import json
import sys


def brief(title: str, genre: str = "adventure", era: str = "16bit") -> dict:
    return {
        "title": title,
        "genre": genre,
        "era": era,
        "pillars": ["tight feedback", "fair puzzles", "era-authentic"],
        "constraints": [
            "operator-approved content",
            "no native execution in design layer",
            "visible clue before any critical gate",
            "provenance on every asset",
        ],
        "next_steps": [
            "Run design review checklist",
            "Generate adventure or creation package",
            "Lock vertical slice scope",
        ],
    }


if __name__ == "__main__":
    title = sys.argv[1] if len(sys.argv) > 1 else "Untitled"
    genre = sys.argv[2] if len(sys.argv) > 2 else "adventure"
    era = sys.argv[3] if len(sys.argv) > 3 else "16bit"
    print(json.dumps(brief(title, genre, era), indent=2))
