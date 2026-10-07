"""
dna_translator_core
===================

Generic, hardened core used by the three domain-specific translators
(``builder_dna_translator``, ``jeeves_dna_translator``,
``academy_dna_translator``).

The core handles every safety concern that is *not* domain specific:

    • Key-prefix validation
    • Value clamping + NaN/inf rejection
    • Payload-size cap (MAX_KEYS)
    • LRU memoisation
    • Deterministic, sorted-by-drift output
    • Prompt-length cap

A domain wraps this module by providing:

    • ``KEY_PREFIX``       — e.g. ``"bdr_"``, ``"jv_"``, ``"ac_"``
    • ``GROUP_HEADERS``    — ``{group_id: "human title"}``
    • ``SLOT_LABELS``      — ``{group_id: {slot_id: "human label"}}``
    • ``KEY_GROUP_INDEX``  — index of which token in ``key.split('_')`` is the
                              group identifier (depends on namespace depth).
    • ``KEY_SLOT_START``   — index from which slot tokens begin.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import blake2b
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger(__name__)

# Shared safety limits. Domains may shadow these if they ever need to.
MAX_KEYS: int = 200
MIN_VALUE: float = 0.0
MAX_VALUE: float = 3.0
DEFAULT_VALUE: float = 1.0
DRIFT_EPSILON: float = 0.05
MAX_PROMPT_CHARS: int = 4_000
MAX_KEY_LEN: int = 80

# Verb tables shared across all domains.
_BUCKET_LABELS: Tuple[str, ...] = (
    "skip",
    "downplay",
    "default",
    "favour",
    "double-down on",
    "saturate",
)


@dataclass(frozen=True)
class DnaDomain:
    """Configuration that distinguishes one cockpit domain from another."""
    name: str                                   # for logs/diagnostics
    key_prefix: str                             # e.g. "bdr_", "jv_", "ac_"
    group_headers: Dict[str, str]               # group_id → readable title
    slot_labels: Dict[str, Dict[str, str]]      # group_id → {slot_id → label}
    key_group_index: int                        # index of "group" token in split
    key_slot_start: int                         # index where slot tokens start
    group_order: Tuple[str, ...] = field(default_factory=tuple)
    blurb: str = ""                             # short description for prompt header


def sanitise(payload: Optional[Dict[str, Any]], domain: DnaDomain) -> Dict[str, float]:
    """Defensive clean-up of an incoming payload. Never raises.

    Drops:
        • non-string keys
        • keys not starting with ``domain.key_prefix``
        • keys exceeding ``MAX_KEY_LEN`` characters
        • non-numeric values, NaN, inf
    Clamps every accepted value into ``[MIN_VALUE, MAX_VALUE]``. Caps at
    ``MAX_KEYS`` entries to bound prompt size.
    """
    if not payload or not isinstance(payload, dict):
        return {}
    out: Dict[str, float] = {}
    for raw_key, raw_val in payload.items():
        if len(out) >= MAX_KEYS:
            log.warning("%s_dna: payload truncated at %d keys", domain.name, MAX_KEYS)
            break
        if not isinstance(raw_key, str) or not raw_key.startswith(domain.key_prefix):
            continue
        if len(raw_key) > MAX_KEY_LEN:
            continue
        try:
            num = float(raw_val)
        except (TypeError, ValueError):
            continue
        if num != num or num in (float("inf"), float("-inf")):
            continue
        if num < MIN_VALUE:
            num = MIN_VALUE
        elif num > MAX_VALUE:
            num = MAX_VALUE
        out[raw_key] = num
    return out


def translate(payload: Optional[Dict[str, Any]], domain: DnaDomain) -> str:
    """Translate a payload into a prompt directive block.

    Returns ``""`` when nothing drifts from the default — keeping zero
    token cost for the unmodified case.
    """
    clean = sanitise(payload, domain)
    if not clean:
        return ""
    sig = blake2b(digest_size=16)
    sig.update(domain.name.encode("ascii", "ignore") + b":")
    for k in sorted(clean):
        sig.update(f"{k}={clean[k]:.4f};".encode("ascii", "ignore"))
    return _translate_cached(domain.name, sig.hexdigest(), tuple(sorted(clean.items())))


@lru_cache(maxsize=512)
def _translate_cached(
    domain_name: str,
    _sig: str,
    items: Tuple[Tuple[str, float], ...],
) -> str:
    """Cached translator. ``_sig`` deduplicates within a domain."""
    domain = _DOMAIN_REGISTRY.get(domain_name)
    if domain is None:  # pragma: no cover — defensive
        return ""

    drifted: Dict[str, list] = {}
    for key, val in items:
        if abs(val - DEFAULT_VALUE) < DRIFT_EPSILON:
            continue
        group, slot = _split_key(key, domain)
        if group is None:
            continue
        label = _slot_label(group, slot, domain)
        drifted.setdefault(group, []).append((_bucket(val), label, val))

    if not drifted:
        return ""

    header = domain.blurb or f"**{domain.name.title()} DNA preferences** (cockpit drift):"
    lines = [header]
    order = domain.group_order or tuple(domain.group_headers)
    for group in order:
        rows = drifted.get(group)
        if not rows:
            continue
        rows.sort(key=lambda r: -abs(r[2] - DEFAULT_VALUE))
        section_header = domain.group_headers.get(group, group)
        lines.append(f"- {section_header}:")
        for bucket, label, val in rows:
            verb = _BUCKET_LABELS[bucket]
            lines.append(f"    • {verb} **{label}** (intensity {val:.1f}×)")

    text = "\n".join(lines)
    if len(text) > MAX_PROMPT_CHARS:
        text = text[:MAX_PROMPT_CHARS].rsplit("\n", 1)[0]
        text += "\n  …(truncated)…"
    return text


def stats(payload: Optional[Dict[str, Any]], domain: DnaDomain) -> Dict[str, Any]:
    clean = sanitise(payload, domain)
    drift = sum(1 for v in clean.values() if abs(v - DEFAULT_VALUE) >= DRIFT_EPSILON)
    return {
        "received_keys": len(clean),
        "dropped_keys": (len(payload) if isinstance(payload, dict) else 0) - len(clean),
        "drift": drift,
        "at_default": len(clean) - drift,
    }


def limits() -> Dict[str, Any]:
    """Shared limits surfaced to the client."""
    return {
        "max_keys": MAX_KEYS,
        "value_range": [MIN_VALUE, MAX_VALUE],
        "default_value": DEFAULT_VALUE,
        "max_prompt_chars": MAX_PROMPT_CHARS,
    }


# ─── Internals ─────────────────────────────────────────────────────────


def _split_key(key: str, domain: DnaDomain) -> Tuple[Optional[str], Optional[str]]:
    parts = key.split("_")
    if len(parts) <= max(domain.key_group_index, domain.key_slot_start):
        return None, None
    return parts[domain.key_group_index], "_".join(parts[domain.key_slot_start:]) or None


def _slot_label(group: str, slot: Optional[str], domain: DnaDomain) -> str:
    if slot is None:
        return "<unknown>"
    return domain.slot_labels.get(group, {}).get(slot, slot.replace("_", " "))


def _bucket(value: float) -> int:
    if value <= 0.4:
        return 0
    if value <= 0.8:
        return 1
    if value < 1.2:
        return 2
    if value < 1.8:
        return 3
    if value < 2.5:
        return 4
    return 5


# ─── Domain registry ───────────────────────────────────────────────────


_DOMAIN_REGISTRY: Dict[str, DnaDomain] = {}


def register_domain(domain: DnaDomain) -> None:
    """Add (or replace) a domain config. Idempotent."""
    _DOMAIN_REGISTRY[domain.name] = domain


def get_domain(name: str) -> Optional[DnaDomain]:
    return _DOMAIN_REGISTRY.get(name)
