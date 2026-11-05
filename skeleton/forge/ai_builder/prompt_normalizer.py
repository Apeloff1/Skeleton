"""Bound and clean a raw user prompt before it reaches a model or the compiler."""
from __future__ import annotations

import re
import unicodedata

from skeleton.forge.game_design_spec import BRIEF_MAX

_SPACE = re.compile(r"\s+")
MAX_RAW_PROMPT_CHARS = 64_000


def normalize_prompt(prompt: object, *, limit: int = BRIEF_MAX) -> str:
    """NFKC, drop control/format chars, collapse whitespace, cap at ``limit``."""
    if type(prompt) is not str:
        raise ValueError("prompt must be a string")
    if type(limit) is not int or not 1 <= limit <= BRIEF_MAX:
        raise ValueError("prompt output limit must be a bounded integer")
    # Validate raw size before NFKC expansion or whitespace regex allocation.
    if len(prompt) > MAX_RAW_PROMPT_CHARS:
        raise ValueError("raw prompt exceeds input budget")
    text = unicodedata.normalize("NFKC", prompt)
    if len(text) > MAX_RAW_PROMPT_CHARS:
        raise ValueError("normalized prompt exceeds input budget")
    text = "".join(" " if unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"} else c for c in text)
    text = _SPACE.sub(" ", text).strip()[:limit].strip()
    if not text:
        raise ValueError("prompt is required")
    return text
