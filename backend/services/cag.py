"""
services/cag.py — Cache-Augmented Generation (CAG) layer.

2026 SOTA context engineering. The expensive part of an LLM call is not the
generation — it's re-processing the same long system/context prefix on every
request. CAG eliminates that:

1. Static context (system laws, curriculum, persona, domain canon) is
   rendered ONCE into a deterministic prefix block.
2. The block is content-hashed; identical hashes across requests mean the
   provider's KV-cache (OpenAI prompt caching, Anthropic cache_control,
   Gemini context caching) hits and the prefix is billed at ~10% rate.
3. Only the dynamic tail (user query, retrieved snippets) is processed fresh.

Design rules for KV-cache friendliness:
  - Prefix bytes must be IDENTICAL across calls (sorted keys, no timestamps,
    no random ids — volatile data goes in the tail).
  - Longest-prefix-first ordering: the most stable content leads.
  - Cache breakpoints are explicit so callers can place cache_control markers.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

# Approx tokens: 4 chars/token is the standard conservative estimate.
def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class PrefixSegment:
    """One stable segment of the cached prefix. Order matters: most stable first."""
    name: str
    text: str
    cache_breakpoint: bool = False   # provider cache_control marker goes here

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


@dataclass
class CAGPrefix:
    """A rendered, hash-versioned prompt prefix ready for KV-cached reuse."""
    key: str
    text: str
    sha: str
    tokens: int
    segments: list[str]
    breakpoints: list[int]          # char offsets where cache_control may attach
    built_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "sha": self.sha,
            "tokens": self.tokens,
            "segments": self.segments,
            "breakpoint_count": len(self.breakpoints),
            "built_at": self.built_at,
        }


def build_prefix(key: str, segments: Iterable[PrefixSegment]) -> CAGPrefix:
    """Render segments into one deterministic prefix.

    Deterministic = same segments in → same bytes out → same hash → KV hit.
    """
    parts: list[str] = []
    breakpoints: list[int] = []
    offset = 0
    for seg in segments:
        block = f"# {seg.name}\n{seg.text.rstrip()}\n\n"
        parts.append(block)
        if seg.cache_breakpoint:
            breakpoints.append(offset + len(block))
        offset += len(block)
    text = "".join(parts)
    return CAGPrefix(
        key=key,
        text=text,
        sha=content_hash(text),
        tokens=estimate_tokens(text),
        segments=[s.name for s in segments],
        breakpoints=breakpoints,
    )


# ────────────────────────────────────────────────────────────────────────────
# Prefix registry — process-wide, keyed by (key). Value = latest CAGPrefix.
# Callers compare .sha to detect drift; MAG (mag.py) owns refresh policy.
# ────────────────────────────────────────────────────────────────────────────

class PrefixRegistry:
    def __init__(self) -> None:
        self._prefixes: dict[str, CAGPrefix] = {}
        self.hits = 0
        self.rebuilds = 0

    def get(self, key: str) -> CAGPrefix | None:
        return self._prefixes.get(key)

    def register(self, prefix: CAGPrefix) -> bool:
        """Store prefix. Returns True if this was a rebuild (hash changed)."""
        old = self._prefixes.get(prefix.key)
        changed = old is None or old.sha != prefix.sha
        self._prefixes[prefix.key] = prefix
        if changed:
            self.rebuilds += 1
        else:
            self.hits += 1
        return changed

    def stats(self) -> dict:
        return {
            "prefixes": len(self._prefixes),
            "hits": self.hits,
            "rebuilds": self.rebuilds,
            "total_cached_tokens": sum(p.tokens for p in self._prefixes.values()),
            "keys": sorted(self._prefixes),
        }


registry = PrefixRegistry()


# ────────────────────────────────────────────────────────────────────────────
# Tutolage prefix builders — the actual hot context for Jeeves.
# ────────────────────────────────────────────────────────────────────────────

def jeeves_system_prefix() -> CAGPrefix:
    """The Jeeves tutoring prefix: persona + system laws + learning stages.

    Pulled lazily from cs_bible / jeeves modules when present; falls back to
    a compact built-in so the service degrades gracefully on minimal deploys.
    """
    segments: list[PrefixSegment] = []

    persona = (
        "You are Jeeves, a young English butler AI tutor. Formal, precise, "
        "encouraging. You guide through Socratic questioning, track the "
        "learner's zone of proximal development, and never give answers "
        "before the learner has attempted the problem."
    )
    try:
        from routes.jeeves_persona import PERSONA_TEXT  # type: ignore
        persona = PERSONA_TEXT
    except Exception:
        pass
    segments.append(PrefixSegment("persona", persona, cache_breakpoint=True))

    laws = (
        "System Laws: (1) Mastery before progression. (2) Cognitive load stays "
        "in the 40-70% band. (3) Errors are data, not failures. (4) Spaced "
        "retrieval beats massed review. (5) Graduated handoff: scaffold fades "
        "as mastery rises."
    )
    try:
        from routes.jeeves_core import SYSTEM_LAWS_TEXT  # type: ignore
        laws = SYSTEM_LAWS_TEXT
    except Exception:
        pass
    segments.append(PrefixSegment("system_laws", laws))

    stages = (
        "Learning stages: Onboarding (0-5h, heavy scaffolding) -> Foundation "
        "(5-50h, moderate) -> Growth (50-200h, light) -> Mastery (200h+, minimal)."
    )
    segments.append(PrefixSegment("learning_stages", stages))

    key = "jeeves:system"
    existing = registry.get(key)
    if existing is not None:
        # Rebuild only if the underlying text drifted (hash compare).
        candidate = build_prefix(key, segments)
        if candidate.sha == existing.sha:
            return existing
        registry.register(candidate)
        return candidate
    prefix = build_prefix(key, segments)
    registry.register(prefix)
    return prefix


def compose_prompt(
    prefix: CAGPrefix,
    dynamic_tail: str,
    retrieved: list[str] | None = None,
) -> tuple[str, dict]:
    """Compose final prompt = cached prefix + retrieved snippets + dynamic tail.

    Retrieved snippets sit BETWEEN prefix and tail: they vary per request but
    are short, so they only invalidate the tail of the KV cache, not the
    expensive prefix.
    """
    parts = [prefix.text]
    if retrieved:
        parts.append("# retrieved_context\n")
        for i, snippet in enumerate(retrieved, 1):
            parts.append(f"[{i}] {snippet.rstrip()}\n")
        parts.append("\n")
    parts.append("# request\n")
    parts.append(dynamic_tail)
    prompt = "".join(parts)
    meta = {
        "prefix_sha": prefix.sha,
        "prefix_tokens": prefix.tokens,
        "retrieved_tokens": estimate_tokens("".join(retrieved or [])),
        "tail_tokens": estimate_tokens(dynamic_tail),
        "total_tokens": estimate_tokens(prompt),
        # Tokens billed at cached rate (~10%) on a KV hit:
        "cached_tokens": prefix.tokens,
        "fresh_tokens": estimate_tokens("".join(retrieved or [])) + estimate_tokens(dynamic_tail),
    }
    return prompt, meta
