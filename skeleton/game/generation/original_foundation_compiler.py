"""Exact-indexed original causal world foundations, not cosmetic permutations.

128 separately authored ROOT laws, 80 separately authored CONSEQUENCE regimes
and 160 domain/regime coupling laws produce 10,240 identified, authored-
component compositions. These are NOT 10,240 individually prose-written
worlds and NOT 10,240 fully playable native builds. The previous 1,296
bespoke atlas worlds remain separate and unchanged for backwards-compatibility.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from types import MappingProxyType

from .original_foundation_roots_a import ROOT_GROUPS_A
from .original_foundation_roots_b import ROOT_GROUPS_B
from .original_foundation_regimes import REGIME_GROUPS
from .original_foundation_couplings import COUPLING_LAWS

FOUNDATION_VERSION = "original-foundation-atlas.v1"
ROOT_PER_GROUP = 8
REGIME_PER_GROUP = 8
ROOT_DOMAINS = 16
REGIME_FAMILIES = 10
COMPOSITION_PROVENANCE = "authored-causal-composition"
SINGLE_ROOT_PROVENANCE = "individually-authored-causal-law"


class FoundationError(ValueError):
    """Invalid world foundation identity, authoring inputs, or foundation state."""


@dataclass(frozen=True)
class RootLaw:
    root_id: str
    title: str
    domain: str
    meter: str
    hazard: str
    invariant: str
    lever: str
    failure: str
    ending_policy: str
    provenance: str = SINGLE_ROOT_PROVENANCE


@dataclass(frozen=True)
class RegimeLaw:
    regime_id: str
    title: str
    operator: str
    intensity: int
    invariant: str
    lever: str
    failure: str
    ending_policy: str
    provenance: str = SINGLE_ROOT_PROVENANCE


@dataclass(frozen=True)
class FoundationLaw:
    foundation_id: str
    foundation_index: int
    design_id: str
    title: str
    root: RootLaw
    regime: RegimeLaw
    coupling: str
    domain: str
    invariant: str
    player_lever: str
    failure_pressure: str
    ending_policy: str
    secondary_ending_policy: str
    provenance: str = COMPOSITION_PROVENANCE
    implementation_status: str = "bounded-reference-runtime"

    def as_dict(self) -> dict:
        result = asdict(self)
        result["foundation_index"] = str(self.foundation_index)
        result["version"] = FOUNDATION_VERSION
        return result


ENDING_POLICIES = frozenset({
    "closed", "open", "postgame", "persistent",
    "unwinnable", "branched", "looping",
})
OPERATORS = (
    "echo", "levy", "reverse", "threshold", "migration",
    "veto", "cascade", "exchange", "auction", "fork",
)


def _digest(value: object) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _load_roots() -> tuple[RootLaw, ...]:
    groups = ROOT_GROUPS_A + ROOT_GROUPS_B
    if len(groups) != ROOT_DOMAINS:
        raise FoundationError("root domain coverage must contain 16 disciplines")
    output = []
    signatures = set()
    domains = set()
    for domain, meter, hazard, lines in groups:
        if (domain in domains or meter == hazard or
                not domain or not meter or not hazard or len(lines) != ROOT_PER_GROUP):
            raise FoundationError("invalid original root domain inventory")
        domains.add(domain)
        for n, row in enumerate(lines, start=1):
            values = row.split("|")
            if len(values) != 5:
                raise FoundationError("root rows require title, invariant, lever, hazard, policy")
            title, invariant, lever, failure, ending = values
            if (ending not in ENDING_POLICIES or
                    any(len(field.strip()) < 8 for field in values[:4])):
                raise FoundationError("underspecified original world root")
            signature = (title.casefold().strip(), invariant.casefold().strip())
            if signature[0] in signatures or signature[1] in signatures:
                raise FoundationError("duplicate root title/invariant")
            signatures.update(signature)
            output.append(RootLaw(
                f"root-{domain}-{n:02d}", title, domain,
                meter, hazard, invariant, lever, failure, ending,
            ))
    if len(output) != ROOT_DOMAINS * ROOT_PER_GROUP:
        raise FoundationError("wrong number of individually authored roots")
    return tuple(output)


def _load_regimes() -> tuple[RegimeLaw, ...]:
    if len(REGIME_GROUPS) != REGIME_FAMILIES:
        raise FoundationError("missing causal overlay operator")
    out = []
    seen = set()
    for operator, rows in REGIME_GROUPS:
        if operator in seen or operator not in OPERATORS or len(rows) != REGIME_PER_GROUP:
            raise FoundationError("unsupported or duplicate causal overlay family")
        seen.add(operator)
        for n, row in enumerate(rows, start=1):
            fields = row.split("|")
            if len(fields) != 5:
                raise FoundationError("regime requires five authored fields")
            title, invariant, lever, failure, policy = fields
            if (policy not in ENDING_POLICIES or
                    any(len(field.strip()) < 8 for field in fields[:4])):
                raise FoundationError("incomplete regime authoring")
            out.append(RegimeLaw(
                f"regime-{operator}-{n:02d}", title, operator, n,
                invariant, lever, failure, policy,
            ))
    if set(OPERATORS) != seen or len(out) != REGIME_FAMILIES * REGIME_PER_GROUP:
        raise FoundationError("regime operator coverage is incomplete")
    if len({r.title.casefold() for r in out}) != len(out):
        raise FoundationError("duplicate overlay regime titles")
    return tuple(out)


ROOTS = _load_roots()
REGIMES = _load_regimes()
ROOT_BY_ID = MappingProxyType({root.root_id: root for root in ROOTS})
REGIME_BY_ID = MappingProxyType({regime.regime_id: regime for regime in REGIMES})

if set(COUPLING_LAWS) != {root.domain for root in ROOTS}:
    raise FoundationError("authored causal couplings missing a root domain")
if any(len(COUPLING_LAWS[domain]) != REGIME_FAMILIES
       for domain in COUPLING_LAWS):
    raise FoundationError("authored causal couplings missing a regime family")
if any(not text or len(text) < 24 for clauses in COUPLING_LAWS.values()
       for text in clauses):
    raise FoundationError("authorial domain coupling cannot be generic/empty")
if len({clause.casefold() for clauses in COUPLING_LAWS.values()
        for clause in clauses}) != ROOT_DOMAINS * REGIME_FAMILIES:
    raise FoundationError("authored causal coupling texts must be distinct")

ROOT_COUNT = len(ROOTS)                    # 128 fully individual
REGIME_COUNT = len(REGIMES)                # 80 separately authored overlay laws
COUPLING_COUNT = sum(map(len, COUPLING_LAWS.values()))   # 160 bespoke links
STRUCTURED_FOUNDATIONS = ROOT_COUNT * REGIME_COUNT      # 10,240 compositions
PREVIOUS_BESPOKE_WORLDS = 1_296
TOTAL_FOUNDATION_ENTRIES = PREVIOUS_BESPOKE_WORLDS + STRUCTURED_FOUNDATIONS
INDEPENDENTLY_AUTHORED_ROOT_WORLDS = PREVIOUS_BESPOKE_WORLDS + ROOT_COUNT


def foundation_at(index: int) -> FoundationLaw:
    """Return one exact deterministic authored-law composition, without enumeration."""
    if type(index) is not int or not 0 <= index < STRUCTURED_FOUNDATIONS:
        raise FoundationError("structured foundation index is out of range")
    root_i, regime_i = divmod(index, REGIME_COUNT)
    root, regime = ROOTS[root_i], REGIMES[regime_i]
    bridge = COUPLING_LAWS[root.domain][OPERATORS.index(regime.operator)]
    signature = {
        "version": FOUNDATION_VERSION,
        "root_id": root.root_id,
        "regime_id": regime.regime_id,
        "bridge": bridge,
    }
    return FoundationLaw(
        foundation_id=f"fnd-{root.root_id}-{regime.regime_id}",
        foundation_index=index,
        design_id=_digest(signature),
        title=f"{root.title} / {regime.title}",
        root=root,
        regime=regime,
        coupling=bridge,
        domain=root.domain,
        invariant=(
            f"{root.invariant}. Additionally: {regime.invariant}. "
            f"Joint causal obligation: {bridge}."
        ),
        player_lever=(
            f"{root.lever}. Regime interaction: {regime.lever}."
        ),
        failure_pressure=(
            f"{root.failure}. Cross-system risk: {regime.failure}."
        ),
        ending_policy=root.ending_policy,
        secondary_ending_policy=regime.ending_policy,
    )


def foundation_for(root_id: str, regime_id: str) -> FoundationLaw:
    try:
        root = ROOT_BY_ID[root_id]
        regime = REGIME_BY_ID[regime_id]
    except (KeyError, TypeError) as exc:
        raise FoundationError("unknown authored root/regime identity") from exc
    root_index = ROOTS.index(root)
    regime_index = REGIMES.index(regime)
    return foundation_at(root_index * REGIME_COUNT + regime_index)


def foundation_from_seed(seed: str) -> FoundationLaw:
    if not isinstance(seed, str) or not 0 < len(seed.encode("utf-8")) <= 4096:
        raise FoundationError("seed must be 1–4096 UTF-8 bytes")
    raw = sha256((FOUNDATION_VERSION + ":" + seed).encode("utf-8")).digest()
    return foundation_at(int.from_bytes(raw, "big") % STRUCTURED_FOUNDATIONS)


def foundation_by_id(identifier: str) -> FoundationLaw:
    """Resolve stable compound ids with exact root/regime matching."""
    if not isinstance(identifier, str) or not identifier.startswith("fnd-root-"):
        raise FoundationError("invalid structured foundation id")
    for root in ROOTS:
        prefix = "fnd-" + root.root_id + "-"
        if identifier.startswith(prefix):
            regime = identifier[len(prefix):]
            return foundation_for(root.root_id, regime)
    raise FoundationError("unknown foundation id")


def iter_foundations(*, start: int = 0, limit: int = 256):
    """Bounded paged streaming; never allocate all 10k entries just to browse."""
    if (type(start) is not int or type(limit) is not int or
            start < 0 or limit < 1 or limit > 2048 or
            start > STRUCTURED_FOUNDATIONS):
        raise FoundationError("invalid bounded foundation page")
    for idx in range(start, min(start + limit, STRUCTURED_FOUNDATIONS)):
        yield foundation_at(idx)


def provenance_report() -> dict:
    """Counting conventions prevent inflation by styles or index permutations."""
    return {
        "atlas_version": FOUNDATION_VERSION,
        "previous_individually_written_worlds": PREVIOUS_BESPOKE_WORLDS,
        "new_individually_written_world_roots": ROOT_COUNT,
        "new_individually_written_regime_laws": REGIME_COUNT,
        "new_individually_written_domain_regime_bridges": COUPLING_COUNT,
        "cross_law_composed_foundation_entries": STRUCTURED_FOUNDATIONS,
        "total_world_foundation_entries": TOTAL_FOUNDATION_ENTRIES,
        "individually_written_world_roots_total": INDEPENDENTLY_AUTHORED_ROOT_WORLDS,
        "cross_law_provenance": COMPOSITION_PROVENANCE,
        "does_not_count_visual_styles_as_new_worlds": True,
        "cross_law_entries_are_individually_hand_written": False,
        "every_composition_has_two_authored_laws_and_an_authored_bridge": True,
        "worlds_guaranteed_native_playable": 0,
    }
