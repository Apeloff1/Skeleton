"""
builder_dna_translator
======================

Translate a frontend 100-slider Build-DNA cockpit payload into a focused
prompt directive block that is injected into the code-generation LLM call.

Design goals
------------

• **Security**   - Every incoming key/value is validated before it ever
                   reaches the LLM. Unknown keys are dropped silently,
                   numerics are clamped to ``0.0..3.0`` and the payload
                   is capped at ``MAX_KEYS`` entries.

• **Performance**- Sliders that sit at the default ``1.0`` are skipped
                   entirely (zero token cost) and translation output is
                   memoised via an in-process LRU cache keyed by a hash
                   of the *clamped* payload.

• **Stability**  - The translator never raises. Any malformed input
                   degrades gracefully to "no directives" so the
                   generation endpoint stays alive.

• **Maintainability**
                  - All translation logic lives here. The downstream
                   prompt builder only sees a single string.

The cockpit groups (Performance / Quality / Testing / Security /
Deployment / Observability / UX-DX / Documentation / A11y /
Maintainability) mirror ``frontend/state/builderDnaData.ts``. Keep them
in sync.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from hashlib import blake2b
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger(__name__)

# ─── Limits / safety knobs ──────────────────────────────────────────────
# Keep these conservative — the 100-slider cockpit cannot legitimately
# exceed these bounds, so anything past them indicates abuse or a bug.
MAX_KEYS: int = 200            # generous head-room above 100
MIN_VALUE: float = 0.0
MAX_VALUE: float = 3.0
DEFAULT_VALUE: float = 1.0
DRIFT_EPSILON: float = 0.05     # below this delta we treat as "at default"
MAX_PROMPT_CHARS: int = 4_000   # hard cap on generated directive block

# Allowed key prefix — the cockpit always emits ``bdr_<cat>_<grp>_<slot>``.
KEY_PREFIX: str = "bdr_"

# Verb tables — index into these via the *bucketed* slider value.
#   bucket 0 = strongly suppress      (value <= 0.4)
#   bucket 1 = de-emphasise            (0.4 < value <= 0.8)
#   bucket 2 = default                 (0.8 <  value <  1.2)  → never emitted
#   bucket 3 = lean into                (1.2 <= value < 1.8)
#   bucket 4 = strongly emphasise       (1.8 <= value < 2.5)
#   bucket 5 = saturate                 (value >= 2.5)
_BUCKET_LABELS: Tuple[str, ...] = (
    "skip",
    "downplay",
    "default",        # never reached when DRIFT_EPSILON is respected
    "favour",
    "double-down on",
    "saturate",
)

# Group → human-readable section header used inside the prompt.
_GROUP_HEADERS: Dict[str, str] = {
    "perf":     "Performance & scaling",
    "quality":  "Code quality & style",
    "testing":  "Testing strategy",
    "security": "Security & compliance",
    "deploy":   "Deployment & DevOps",
    "obs":      "Observability & logging",
    "ux":       "UX / DX polish",
    "docs":     "Documentation",
    "a11y":     "Accessibility & i18n",
    "maint":    "Maintainability & evolution",
}

# Slot-level label table mirroring frontend/state/builderDnaData.ts SCHEMA.
# Only the slots used downstream are listed; keys with unknown slots are
# rendered as the raw slot identifier (still safe).
_SLOT_LABELS: Dict[str, Dict[str, str]] = {
    "perf": {
        "p95": "p95 latency", "cold": "cold-start budget", "hot": "hot-path tuning",
        "cache": "caching layers", "batch": "batched IO", "concurrency": "concurrency",
        "memory": "memory footprint", "bundle": "bundle / binary size",
        "profiling": "profiling hooks", "sla": "SLO strictness",
    },
    "quality": {
        "terse": "terseness", "naming": "descriptive naming", "types": "type strictness",
        "fp": "functional bias", "decomp": "function decomposition",
        "side": "side-effect avoidance", "magic": "magic-number elimination",
        "lint": "lint strictness", "fmt": "formatter discipline",
        "comments": "inline comment density",
    },
    "testing": {
        "unit": "unit-test coverage", "integ": "integration tests", "e2e": "E2E tests",
        "mock": "mocking aggression", "snapshot": "snapshot tests", "fuzz": "fuzz tests",
        "property": "property tests", "contract": "contract tests",
        "chaos": "chaos drills", "smoke": "smoke checks",
    },
    "security": {
        "input": "input validation", "authn": "authentication strictness",
        "authz": "authorisation strictness", "secret": "secret handling",
        "dep": "dependency audit", "csp": "CSP / sandbox", "sqli": "injection guards",
        "gdpr": "privacy compliance", "audit": "audit trail", "polp": "least privilege",
    },
    "deploy": {
        "cicd": "CI/CD coverage", "iac": "Infra-as-Code discipline",
        "containers": "containerisation", "rollback": "rollback ease",
        "canary": "canary rollouts", "flag": "feature-flag gating",
        "auto": "auto-scaling", "sec": "secret rotation",
        "env": "env parity", "monitor": "health probes",
    },
    "obs": {
        "log": "log verbosity", "struct": "structured logs", "metric": "metric coverage",
        "trace": "distributed traces", "sample": "sampling rate",
        "alert": "alert sensitivity", "sla": "SLO dashboards",
        "error": "error capture", "context": "log context propagation",
        "retain": "log retention",
    },
    "ux": {
        "loading": "loading states", "empty": "empty states", "error": "error states",
        "micro": "micro-interactions", "haptic": "haptic / sound feedback",
        "shortcut": "power-user shortcuts", "onboard": "onboarding flow",
        "help": "in-app help", "dx_log": "dev-mode logging", "dx_doc": "DX docstrings",
    },
    "docs": {
        "readme": "README depth", "api": "API reference", "tutorial": "tutorial walkthroughs",
        "examples": "code examples", "adr": "ADR records", "diagram": "diagrams",
        "patterns": "pattern catalogue", "edge": "edge-case notes",
        "cl": "changelog automation", "inline": "inline comments",
    },
    "a11y": {
        "contrast": "contrast", "sr": "screen-reader labels", "keyboard": "keyboard nav",
        "motion": "reduce-motion support", "font": "font scaling", "i18n": "i18n breadth",
        "rtl": "RTL support", "a11y_doc": "a11y documentation",
        "colorblind": "colour-blind safe palette", "subtitle": "captions / transcripts",
    },
    "maint": {
        "modular": "modularity", "ports": "ports & adapters",
        "di": "dependency injection", "migration": "migration friendliness",
        "dep_pin": "dependency pinning", "deprec": "deprecation hygiene",
        "compat": "backward compatibility", "plug": "plugin surface",
        "fork": "forkability", "license": "license clarity",
    },
}

# ─── Public API ─────────────────────────────────────────────────────────


def sanitise_dna(payload: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Defensive clean-up of an incoming cockpit payload.

    Returns a dict of *valid* keys mapped to clamped floats. Never raises.

    Invariants enforced:
        • All keys are strings that start with ``bdr_``.
        • Payload size is capped at ``MAX_KEYS`` entries.
        • Each value is finite and clamped to ``[MIN_VALUE, MAX_VALUE]``.
    """
    if not payload or not isinstance(payload, dict):
        return {}

    out: Dict[str, float] = {}
    for raw_key, raw_val in payload.items():
        if len(out) >= MAX_KEYS:
            log.warning("builder_dna: payload truncated at %d keys", MAX_KEYS)
            break
        if not isinstance(raw_key, str) or not raw_key.startswith(KEY_PREFIX):
            continue
        # Reject suspiciously long keys (defence-in-depth vs prompt injection
        # via crafted slider identifiers).
        if len(raw_key) > 80:
            continue
        try:
            num = float(raw_val)
        except (TypeError, ValueError):
            continue
        # Reject non-finite numbers (NaN / inf).
        if num != num or num in (float("inf"), float("-inf")):
            continue
        # Clamp into legal range.
        if num < MIN_VALUE:
            num = MIN_VALUE
        elif num > MAX_VALUE:
            num = MAX_VALUE
        out[raw_key] = num
    return out


def translate_dna_to_prompt(payload: Optional[Dict[str, Any]]) -> str:
    """Translate a sanitised cockpit payload into prompt directives.

    Output is a stable, deterministic, *sorted* multi-line string suitable
    for direct inclusion in an LLM system or user prompt. Returns an empty
    string when there is nothing to say (all sliders at default).
    """
    clean = sanitise_dna(payload)
    if not clean:
        return ""
    # Sort + hash to derive a deterministic cache key. We hash the sanitised
    # payload — not the raw input — so equivalent-but-differently-ordered
    # cockpits share a cache entry.
    sig = blake2b(digest_size=16)
    for k in sorted(clean):
        sig.update(f"{k}={clean[k]:.4f};".encode("ascii", "ignore"))
    return _translate_cached(sig.hexdigest(), tuple(sorted(clean.items())))


@lru_cache(maxsize=512)
def _translate_cached(_sig: str, items: Tuple[Tuple[str, float], ...]) -> str:
    """Cached translator. ``_sig`` is the deduplication key only.

    Items are a sorted tuple so cache equality is stable across requests.
    """
    drifted: Dict[str, list] = {}
    for key, val in items:
        if abs(val - DEFAULT_VALUE) < DRIFT_EPSILON:
            continue
        group, slot = _split_key(key)
        if group is None:
            continue
        bucket = _bucket(val)
        label = _slot_label(group, slot)
        drifted.setdefault(group, []).append((bucket, label, val))

    if not drifted:
        return ""

    lines: list = ["**Build DNA preferences** (per-category cockpit drift):"]
    # Stable group order — same as frontend.
    for group in ("perf", "quality", "testing", "security", "deploy",
                  "obs", "ux", "docs", "a11y", "maint"):
        rows = drifted.get(group)
        if not rows:
            continue
        # Sort within a group: strongest absolute deviation first so the
        # most important directives lead the section.
        rows.sort(key=lambda r: -abs(r[2] - DEFAULT_VALUE))
        section_header = _GROUP_HEADERS.get(group, group)
        lines.append(f"- {section_header}:")
        for bucket, label, val in rows:
            verb = _BUCKET_LABELS[bucket]
            lines.append(f"    • {verb} **{label}** (intensity {val:.1f}×)")

    text = "\n".join(lines)
    # Hard cap to keep token budget bounded. Truncate at line boundary.
    if len(text) > MAX_PROMPT_CHARS:
        text = text[:MAX_PROMPT_CHARS].rsplit("\n", 1)[0]
        text += "\n  …(truncated)…"
    return text


# ─── Internals ──────────────────────────────────────────────────────────


def _split_key(key: str) -> Tuple[Optional[str], Optional[str]]:
    """``bdr_<category>_<group>_<slot>`` → ``(group, slot)``.

    Category is intentionally ignored at translation time — the LLM
    doesn't need to know which UI tab the user was on. Returns
    ``(None, None)`` for malformed keys (caller filters them out).
    """
    parts = key.split("_")
    if len(parts) < 4 or parts[0] != "bdr":
        return None, None
    # ``parts[1]`` = category, ``parts[2]`` = group, ``parts[3:]`` = slot tokens.
    return parts[2], "_".join(parts[3:]) or None


def _slot_label(group: str, slot: Optional[str]) -> str:
    """Human-readable label for a slot key, with safe fallback."""
    if slot is None:
        return "<unknown>"
    return _SLOT_LABELS.get(group, {}).get(slot, slot.replace("_", " "))


def _bucket(value: float) -> int:
    """Map a clamped slider value into a verb-bucket index."""
    if value <= 0.4:
        return 0
    if value <= 0.8:
        return 1
    if value < 1.2:
        return 2  # default — caller should have filtered this out
    if value < 1.8:
        return 3
    if value < 2.5:
        return 4
    return 5


# ─── Diagnostics (used by /info endpoints) ──────────────────────────────


def stats(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a small diagnostic snapshot of a payload — handy for logs.

    Output is intentionally *small* (4 fields) so it's cheap to log on
    every request without bloating the journal.
    """
    clean = sanitise_dna(payload)
    drift = sum(1 for v in clean.values() if abs(v - DEFAULT_VALUE) >= DRIFT_EPSILON)
    return {
        "received_keys": len(clean),
        "dropped_keys": (len(payload) if isinstance(payload, dict) else 0) - len(clean),
        "drift": drift,
        "at_default": len(clean) - drift,
    }
