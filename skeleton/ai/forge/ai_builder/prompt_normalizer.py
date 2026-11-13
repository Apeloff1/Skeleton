"""Bound and clean a raw user prompt before it reaches a model or the compiler."""
from __future__ import annotations

import re
import unicodedata

from skeleton.forge.game_design_spec import BRIEF_MAX

_SPACE = re.compile(r"\s+")


def normalize_prompt(prompt: object, *, limit: int = BRIEF_MAX) -> str:
    """NFKC, drop control/format chars, collapse whitespace, cap at ``limit``."""
    if not isinstance(prompt, str):
        raise ValueError("prompt must be a string")
    text = unicodedata.normalize("NFKC", prompt)
    text = "".join(" " if unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"} else c for c in text)
    text = _SPACE.sub(" ", text).strip()[:limit].strip()
    if not text:
        raise ValueError("prompt is required")
    return text
