"""forge_dna — the Universal Forge's identity & efficiency layer.

Implements four things requested for the "next phase":

  1. ECS Bitmasking        — every forge's components encoded in one integer
                             bitmask (Entity-Component-System style) for O(1)
                             capability filtering.
  2. 2048-bit Procedural   — every unique variation compressed into a
     DNA Token               deterministic 2048-bit hash (SHAKE-256, 512 hex
                             chars) so any forge can be referenced/verified by
                             a single token.
  3. Contextual Semantic   — drops style-axis selections that are semantically
     Pruning                 incompatible with a forge's family, keeping specs
                             coherent and shrinking the token payload.
  4. Lazy Token Pruning    — a bounded LRU cache that lazily mints DNA tokens
                             and prunes least-recently-used entries, so we never
                             hold more than `capacity` tokens in memory.

No dependency on universal_forge → safe to import from it.
"""
from __future__ import annotations

import base64
import hashlib
import json
from collections import OrderedDict

# ── 1. ECS component bits ──────────────────────────────────────────────────
# Each forge is described by a single integer bitmask. Bit set = component
# present. Cheap to store, cheap to AND/OR-filter across millions of forges.
COMPONENT_BITS: dict[str, int] = {
    "geometry":    1 << 0,
    "skin":        1 << 1,
    "style_axes":  1 << 2,
    "treatment":   1 << 3,
    "inscription": 1 << 4,
    "vfx":         1 << 5,
    "region":      1 << 6,
    "variant":     1 << 7,    # tier-3 modifier present ('{mod}-...')
    "descriptor":  1 << 8,    # tier-2 descriptor present ('{desc}.{noun}')
    "era":         1 << 9,
    "llm":         1 << 10,
    "emissive":    1 << 11,
    "script":      1 << 12,
    "tattoo":      1 << 13,
    "mesh":        1 << 14,
    "engraving":   1 << 15,
    "metallic":    1 << 16,
    "animated":    1 << 17,
}


def component_mask(spec: dict) -> int:
    """Derive the ECS component bitmask for a generated forge spec."""
    m = 0
    ax = spec.get("style_axes") or {}
    geo = spec.get("geometry") or []
    if geo:
        m |= COMPONENT_BITS["geometry"]
    if spec.get("skin_style") or spec.get("skin"):
        m |= COMPONENT_BITS["skin"]
    if ax:
        m |= COMPONENT_BITS["style_axes"]
    if spec.get("treatment") and spec.get("treatment") != "none":
        m |= COMPONENT_BITS["treatment"]
    if spec.get("inscription") or spec.get("inscription_text"):
        m |= COMPONENT_BITS["inscription"]
    if spec.get("vfx"):
        m |= COMPONENT_BITS["vfx"]
    if spec.get("region"):
        m |= COMPONENT_BITS["region"]
    cat = spec.get("category") or ""
    if "-" in cat:
        m |= COMPONENT_BITS["variant"]
    if "." in cat:
        m |= COMPONENT_BITS["descriptor"]
    if spec.get("era"):
        m |= COMPONENT_BITS["era"]
    if spec.get("llm_enriched"):
        m |= COMPONENT_BITS["llm"]
    if any(p.get("emissive") for p in geo):
        m |= COMPONENT_BITS["emissive"]
    if ax.get("script"):
        m |= COMPONENT_BITS["script"]
    if ax.get("tattoo"):
        m |= COMPONENT_BITS["tattoo"]
    if ax.get("mesh"):
        m |= COMPONENT_BITS["mesh"]
    if ax.get("engraving"):
        m |= COMPONENT_BITS["engraving"]
    if ax.get("metal_grade") or any(p.get("metalness", 0) and p["metalness"] > 0.5 for p in geo):
        m |= COMPONENT_BITS["metallic"]
    if spec.get("animated") or any(p.get("anim") for p in geo):
        m |= COMPONENT_BITS["animated"]
    return m


def mask_to_components(mask: int) -> list[str]:
    """Decode a bitmask back to the list of component names it carries."""
    return [name for name, bit in COMPONENT_BITS.items() if mask & bit]


def mask_matches(mask: int, required: int) -> bool:
    """True if `mask` has ALL the bits in `required` (ECS query)."""
    return (mask & required) == required


# ── 2. 2048-bit Procedural DNA Token ───────────────────────────────────────
DNA_BITS = 2048
_DNA_BYTES = DNA_BITS // 8        # 256 bytes → 512 hex chars

# Only identity-defining fields go into the token (visual-only derivatives are
# excluded so the token is stable for the same logical variation).
_DNA_FIELDS = (
    "category", "era", "skin_style", "complexity", "intricacy", "detail_level",
    "style_axes", "treatment", "region", "inscription_text", "seed",
)


def canonical_payload(spec: dict) -> str:
    """Deterministic JSON of the identity-defining fields (sorted keys)."""
    sub = {k: spec[k] for k in _DNA_FIELDS if spec.get(k) is not None}
    return json.dumps(sub, sort_keys=True, separators=(",", ":"), default=str)


def dna_token(spec: dict) -> dict:
    """Compress a unique variation into a deterministic 2048-bit token."""
    payload = canonical_payload(spec)
    hex_digest = hashlib.shake_256(payload.encode("utf-8")).hexdigest(_DNA_BYTES)
    return {
        "bits": DNA_BITS,
        "hex": hex_digest,                                  # 512 hex chars
        "short": f"{hex_digest[:8]}…{hex_digest[-8:]}",
        "checksum": hashlib.sha256(hex_digest.encode()).hexdigest()[:16],
    }


# ── 3. Contextual Semantic Pruning ─────────────────────────────────────────
# Axes that make no semantic sense for a given family are pruned from the spec.
_FAMILY_AXIS_BLOCK: dict[str, set[str]] = {
    "food":      {"metal_grade", "mesh", "tattoo", "engraving"},
    "fruit":     {"metal_grade", "engraving", "tattoo"},
    "vegetable": {"metal_grade", "engraving", "tattoo"},
    "beverage":  {"metal_grade", "engraving", "tattoo"},
    "spice":     {"metal_grade", "engraving", "tattoo"},
    "fish":      {"metal_grade", "engraving"},
    "flora":     {"metal_grade", "tattoo"},
    "herb":      {"metal_grade", "tattoo"},
    "crop":      {"metal_grade", "tattoo"},
    "sound":     {"metal_grade", "mesh", "tattoo", "engraving", "script"},
    "light":     {"tattoo", "engraving"},
}


def semantic_prune(axes: dict | None, family: str | None) -> tuple[dict, list[str]]:
    """Return (kept_axes, pruned_axis_keys) for a family context. Also drops
    empty/'none' selections so the DNA payload stays minimal."""
    if not axes:
        return {}, []
    blocked = _FAMILY_AXIS_BLOCK.get(family or "", set())
    kept: dict = {}
    pruned: list[str] = []
    for k, v in axes.items():
        if k in blocked or v in (None, "", "none"):
            pruned.append(k)
        else:
            kept[k] = v
    return kept, pruned


# ── 4. Lazy Token Pruning (bounded LRU) ─────────────────────────────────────
class LazyTokenCache:
    """Lazily mints values and prunes the least-recently-used entries once the
    capacity is exceeded — so memory stays O(capacity) regardless of how many
    of the 10^110+ variations get touched."""

    def __init__(self, capacity: int = 4096):
        self.capacity = capacity
        self._d: "OrderedDict[str, dict]" = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get_or_make(self, key: str, make):
        if key in self._d:
            self._d.move_to_end(key)
            self.hits += 1
            return self._d[key]
        self.misses += 1
        val = make()
        self._d[key] = val
        while len(self._d) > self.capacity:
            self._d.popitem(last=False)
            self.evictions += 1
        return val

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "size": len(self._d), "capacity": self.capacity,
            "hits": self.hits, "misses": self.misses, "evictions": self.evictions,
            "hit_rate": round(self.hits / total, 4) if total else 0.0,
        }


TOKEN_CACHE = LazyTokenCache(capacity=4096)


def forge_code(spec: dict) -> str:
    """A REVERSIBLE share code (base64url of the canonical params). Unlike the
    one-way DNA hash, this can be decoded to rebuild the exact forge."""
    payload = canonical_payload(spec)
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_forge_code(code: str) -> dict:
    """Decode a forge_code back into its params dict ({} if invalid / if a
    one-way DNA hash was pasted by mistake)."""
    code = (code or "").strip()
    try:
        pad = "=" * (-len(code) % 4)
        raw = base64.urlsafe_b64decode((code + pad).encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def attach_dna_and_mask(spec: dict) -> dict:
    """Stamp a spec with its ECS component mask + lazily-pruned 2048-bit DNA
    token + a reversible forge_code. Mutates and returns the spec."""
    spec["component_mask"] = component_mask(spec)
    spec["components"] = mask_to_components(spec["component_mask"])
    dna = TOKEN_CACHE.get_or_make(canonical_payload(spec), lambda: dna_token(spec))
    spec["dna"] = dna
    spec["dna_token"] = dna["hex"]
    spec["forge_code"] = forge_code(spec)
    return spec
