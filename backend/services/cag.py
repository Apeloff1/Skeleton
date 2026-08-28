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

Cut history:
  - 2026-08-27 (c553ef8): removed dead route-module imports; prefix text
    single-sourced here.
  - 2026-08-28 (B4): guarded shim — when the ``skeleton`` package is
    importable, the canonical implementation in
    ``skeleton.memory.prefix_renderer`` is re-exported and the local copy
    never executes. The backend production image copies only ``backend/``,
    so the ImportError branch (the byte-identical local implementation) is
    what runs there today; adding ``skeleton/`` to the image flips the
    switch with no code change.
"""
from __future__ import annotations

try:  # ── canonical implementation (skeleton on sys.path) ────────────────
    from skeleton.memory.prefix_renderer import (  # noqa: F401
        CAGPrefix,
        PrefixRegistry,
        PrefixSegment,
        build_prefix,
        content_hash,
        estimate_tokens,
    )
    from skeleton.memory.prefix_renderer import (
        JEEVES_LEARNING_STAGES_TEXT,
        JEEVES_PERSONA_TEXT,
        JEEVES_SYSTEM_LAWS_TEXT,
    )

    registry = PrefixRegistry()

    def jeeves_system_prefix() -> CAGPrefix:
        segments = [
            PrefixSegment("persona", JEEVES_PERSONA_TEXT, cache_breakpoint=True),
            PrefixSegment("system_laws", JEEVES_SYSTEM_LAWS_TEXT),
            PrefixSegment("learning_stages", JEEVES_LEARNING_STAGES_TEXT),
        ]
        key = "jeeves:system"
        existing = registry.get(key)
        if existing is not None:
            candidate = build_prefix(key, segments)
            if candidate.sha == existing.sha:
                return existing
            registry.register(candidate)
            return candidate
        prefix = build_prefix(key, segments)
        registry.register(prefix)
        return prefix

    def compose_prompt(prefix, dynamic_tail, retrieved=None):
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
            "cached_tokens": prefix.tokens,
            "fresh_tokens": estimate_tokens("".join(retrieved or [])) + estimate_tokens(dynamic_tail),
        }
        return prompt, meta

except ImportError:  # ── local implementation (backend-only deploy) ──────
    import hashlib
    import time
    from dataclasses import dataclass, field
    from typing import Any, Iterable

    # Approx tokens: 4 chars/token is the standard conservative estimate.
    def estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4)

    def content_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    JEEVES_PERSONA_TEXT = (
        "You are Jeeves, a young English butler AI tutor. Formal, precise, "
        "encouraging. You guide through Socratic questioning, track the "
        "learner's zone of proximal development, and never give answers "
        "before the learner has attempted the problem."
    )

    JEEVES_SYSTEM_LAWS_TEXT = (
        "System Laws: (1) Mastery before progression. (2) Cognitive load stays "
        "in the 40-70% band. (3) Errors are data, not failures. (4) Spaced "
        "retrieval beats massed review. (5) Graduated handoff: scaffold fades "
        "as mastery rises."
    )

    JEEVES_LEARNING_STAGES_TEXT = (
        "Learning stages: Onboarding (0-5h, heavy scaffolding) -> Foundation "
        "(5-50h, moderate) -> Growth (50-200h, light) -> Mastery (200h+, minimal)."
    )

    @dataclass(frozen=True)
    class PrefixSegment:
        """One stable segment of the cached prefix. Order matters: most stable first."""
        name: str
        text: str
        cache_breakpoint: bool = False

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
        breakpoints: list[int]
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

    class PrefixRegistry:
        def __init__(self) -> None:
            self._prefixes: dict[str, CAGPrefix] = {}
            self.hits = 0
            self.rebuilds = 0

        def get(self, key: str):
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

    def jeeves_system_prefix() -> CAGPrefix:
        """The Jeeves tutoring prefix: persona + system laws + learning stages."""
        segments: list[PrefixSegment] = [
            PrefixSegment("persona", JEEVES_PERSONA_TEXT, cache_breakpoint=True),
            PrefixSegment("system_laws", JEEVES_SYSTEM_LAWS_TEXT),
            PrefixSegment("learning_stages", JEEVES_LEARNING_STAGES_TEXT),
        ]
        key = "jeeves:system"
        existing = registry.get(key)
        if existing is not None:
            candidate = build_prefix(key, segments)
            if candidate.sha == existing.sha:
                return existing
            registry.register(candidate)
            return candidate
        prefix = build_prefix(key, segments)
        registry.register(prefix)
        return prefix

    def compose_prompt(prefix, dynamic_tail, retrieved=None):
        """Compose final prompt = cached prefix + retrieved snippets + dynamic tail."""
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
            "cached_tokens": prefix.tokens,
            "fresh_tokens": estimate_tokens("".join(retrieved or [])) + estimate_tokens(dynamic_tail),
        }
        return prompt, meta
