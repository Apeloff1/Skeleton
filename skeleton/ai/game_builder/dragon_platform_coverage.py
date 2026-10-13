"""Evidence-bound platform/era discovery coverage for the original game forge.

Catalog headings and links are only search signals. A platform keyword in a URL
does not prove its technical compatibility, rights, licensing, developer access,
source quality, or that any game is original. Raw leads, deduplicated URLs and
actual verified references must never be conflated.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import re
from urllib.parse import urlsplit

from .dragon_almanacs import read_source_registry
from .dragon_discovery_admission import _evidence_headers, validate_discovery_chain
from .dragon_discovery_reconciled import _chain, EXPECTED_RAW_TOTAL, SOURCE_BATCHES
from .dragon_source_catalog import canonical_source_url
from .reviewed_knowledge import _integer

# Non-exhaustive *search aliases*, not hardware specifications or game rights.
# Long or specific aliases distinguish generations without permitting a generic
# word like "play" or "ps" to fabricate a platform coverage hit.
PLATFORM_ALIASES = (
    ("arcade", "arcade", ("arcade", "mame", "coin op", "coin-op")),
    ("atari_2600", "early_console", ("atari 2600", "atari2600", "vcs 2600")),
    ("atari_7800", "early_console", ("atari 7800", "atari7800")),
    ("nes", "eight_bit", ("nintendo entertainment system", "nesdev", "nes homebrew", "famicom")),
    ("master_system", "eight_bit", ("sega master system", "mastersystem", "smsdev")),
    ("game_boy", "handheld", ("game boy", "gameboy", "gbdev", "gbdk", "dmg 01")),
    ("game_boy_color", "handheld", ("game boy color", "gameboycolor", "gbcdev", "gbc homebrew")),
    ("snes", "sixteen_bit", ("super nintendo", "super famicom", "snesdev", "snes homebrew")),
    ("mega_drive", "sixteen_bit", ("mega drive", "megadrive", "sega genesis", "sgdk")),
    ("neo_geo", "sixteen_bit", ("neo geo", "neogeo")),
    ("amiga", "classic_computer", ("commodore amiga", "amiga os", "amiga homebrew", "amiga")),
    ("commodore_64", "classic_computer", ("commodore 64", "commodore64", "c64dev", "c64 homebrew")),
    ("zx_spectrum", "classic_computer", ("zx spectrum", "zxspectrum", "spectrum 48k")),
    ("msx", "classic_computer", ("msx2", "msx homebrew", "msx computer")),
    ("dos", "classic_computer", ("dos game", "dosgames", "ms dos", "msdos", "dosbox")),
    ("nintendo_64", "three_dimensional", ("nintendo 64", "nintendo64", "n64dev", "libdragon")),
    ("playstation_1", "three_dimensional", ("playstation 1", "playstation one", "ps1dev", "psxdev", "ps1 homebrew")),
    ("saturn", "three_dimensional", ("sega saturn", "saturn homebrew", "jo engine")),
    ("dreamcast", "three_dimensional", ("dreamcast", "kallisti os", "kallistios")),
    ("game_boy_advance", "handheld", ("game boy advance", "gameboyadvance", "gba homebrew", "gbadev", "devkitarm")),
    ("nintendo_ds", "handheld", ("nintendo ds", "nds homebrew", "devkitpro nds", "libnds")),
    ("psp", "handheld", ("playstation portable", "psp homebrew", "pspdev")),
    ("nintendo_3ds", "handheld", ("nintendo 3ds", "3ds homebrew", "devkitctrulib", "ctrulib")),
    ("playstation_2", "sixth_generation", ("playstation 2", "ps2dev", "ps2 homebrew")),
    ("gamecube", "sixth_generation", ("gamecube", "game cube", "libogc")),
    ("original_xbox", "sixth_generation", ("original xbox", "xbox homebrew", "nxdk")),
    ("xbox_360", "seventh_generation", ("xbox 360", "xbox360", "xenon console")),
    ("playstation_3", "seventh_generation", ("playstation 3", "ps3 homebrew", "ps3dev")),
    ("wii", "seventh_generation", ("nintendo wii", "wii homebrew", "wiibrew")),
    ("wii_u", "eighth_generation", ("wii u", "wiiu", "wii u homebrew")),
    ("playstation_4", "eighth_generation", ("playstation 4", "ps4 homebrew", "ps4dev")),
    ("xbox_one", "eighth_generation", ("xbox one", "xboxone")),
    ("nintendo_switch", "hybrid", ("nintendo switch", "switch homebrew", "libnx", "devkitpro switch")),
    ("playstation_5", "ninth_generation", ("playstation 5", "ps5 homebrew")),
    ("xbox_series", "ninth_generation", ("xbox series", "xboxseries")),
    ("windows", "modern_computer", ("windows game", "windows gaming", "win32", "directx", "direct3d")),
    ("linux", "modern_computer", ("linux game", "linux gaming", "sdl2", "vulkan")),
    ("macos", "modern_computer", ("mac os", "macos", "mac gaming", "metal api")),
    ("android", "mobile", ("android gaming", "android game", "android ndk")),
    ("ios", "mobile", ("ios gaming", "ios game", "iphone game", "ipad game")),
    ("web", "web", ("web game", "webgl", "webgpu", "wasm game", "webassembly")),
    ("vr_xr", "immersive", ("virtual reality", "extended reality", "openxr", "steamvr", "oculus quest")),
)
if len({x[0] for x in PLATFORM_ALIASES}) != len(PLATFORM_ALIASES):
    raise RuntimeError("duplicated platform search identifier")

WORDS = re.compile(r"[a-z0-9]+")
RISK_TERMS = frozenset({"rom", "roms", "bios", "warez", "cracked", "torrent",
                        "iso", "pirated", "dumps", "dump", "firmware", "keygen"})


def _tokens(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("discovery heading text required")
    return " " + " ".join(WORDS.findall(value.casefold())) + " "


def _matches(text: str, aliases: tuple[str, ...]) -> bool:
    return any(_tokens(alias) in text for alias in aliases)


def platform_discovery_matrix(registry: dict, *, samples_per_platform: int = 3,
                              include_unclassified: bool = True) -> dict:
    """Read the full checked original discovery lineage; never mutate it.

    Cross-platform link matches are allowed and declared; per-platform counts
    cannot be summed into independent sources. Overlapping aliases are
    intentionally retained as ambiguous metadata search clues.
    """
    _integer(samples_per_platform, "samples per platform", 0, 10)
    if type(include_unclassified) is not bool:
        raise ValueError("include_unclassified must be bool")
    evidence = _chain()
    validated = validate_discovery_chain(registry, evidence)
    if (len(evidence) != len(SOURCE_BATCHES) or
            validated["raw_total_discovered"] != EXPECTED_RAW_TOTAL):
        raise ValueError("platform discovery requires the frozen, complete lineage")
    raw_counts = defaultdict(int)
    canonical_sets = defaultdict(set)
    host_sets = defaultdict(set)
    risk_hits = defaultdict(int)
    samples = defaultdict(set)
    multi_platform_raw = 0
    unclassified_raw = 0
    seen_unique = set()
    all_rows = [(row["url"], []) for row in registry["sources"]]
    for path, document in evidence:
        all_rows.extend((row["url"], row["discoveries"]) for row in document["candidates"])
    if len(all_rows) != EXPECTED_RAW_TOTAL:
        raise ValueError("platform scan source count differs from checked chain")
    for url, origins in all_rows:
        normalized = canonical_source_url(url)
        host = urlsplit(normalized).hostname
        if not host:
            raise ValueError("no canonical host in discovery")
        fragments = [host, urlsplit(normalized).path]
        for origin in origins:
            if not isinstance(origin, dict):
                raise ValueError("invalid observed discovery origin")
            fragments.extend(_evidence_headers(origin))
            repository = origin.get("repository")
            if isinstance(repository, str):
                fragments.append(repository)
        text = _tokens(" ".join(fragments))
        matched = [key for key, _, aliases in PLATFORM_ALIASES
                   if _matches(text, aliases)]
        if len(matched) > 1:
            multi_platform_raw += 1
        if not matched:
            unclassified_raw += 1
        found_risks = set(WORDS.findall(text)) & RISK_TERMS
        for key in matched:
            raw_counts[key] += 1
            canonical_sets[key].add(normalized)
            host_sets[key].add(host)
            if found_risks:
                risk_hits[key] += 1
            if samples_per_platform:
                samples[key].add(normalized)
        seen_unique.add(normalized)
    if len(seen_unique) != validated["total_discovered"]:
        raise ValueError("canonical platform denominator differs from validated chain")
    # Count each distinct URL once within each generation family. Summing
    # individual consoles would double-count shared references and exaggerate
    # discovery coverage for cross-platform libraries.
    era_sources = defaultdict(set)
    era_hosts = defaultdict(set)
    era_members = defaultdict(list)
    for key, era, _ in PLATFORM_ALIASES:
        era_sources[era].update(canonical_sets[key])
        era_hosts[era].update(host_sets[key])
        era_members[era].append(key)
    generation_coverage = [
        {
            "group": era,
            "platform_count": len(era_members[era]),
            "platforms_with_metadata_matches": sum(bool(canonical_sets[k])
                                                  for k in era_members[era]),
            "canonical_distinct_candidate_urls": len(era_sources[era]),
            "distinct_hosts": len(era_hosts[era]),
            "unmatched_platforms": sorted(
                k for k in era_members[era] if not canonical_sets[k]),
            "coverage_is_unreviewed": True,
        }
        for era in sorted(era_members)
    ]
    rows = []
    for key, era, aliases in PLATFORM_ALIASES:
        sources = canonical_sets[key]
        rows.append({
            "platform": key, "platform_group": era,
            "raw_link_mentions": raw_counts[key],
            "canonical_candidate_urls": len(sources),
            "distinct_hosts": len(host_sets[key]),
            "rights_risk_keyword_link_mentions": risk_hits[key],
            "metadata_examples": sorted(samples[key])[:samples_per_platform],
            "search_alias_count": len(aliases),
            "coverage_status": "keyword_discovered_not_verified" if sources
                               else "no_matching_metadata_observed",
            "rights_approved": False,
            "training_authorized": False,
        })
    result = {
        "schema": "skeleton.dragon.platform_discovery_matrix.v1",
        "raw_link_leads": len(all_rows),
        "canonical_distinct_urls_global": len(seen_unique),
        "platforms_in_heuristic_catalog": len(PLATFORM_ALIASES),
        "platforms_with_keyword_matches": sum(bool(canonical_sets[key])
                                             for key, _, _ in PLATFORM_ALIASES),
        "multi_platform_raw_link_mentions": multi_platform_raw,
        "unclassified_raw_link_mentions": unclassified_raw,
        "platforms": rows,
        "generation_coverage": generation_coverage,
        "discovery_attention_queue": [
            item["platform"] for item in sorted(
                rows,
                key=lambda item: (
                    item["canonical_candidate_urls"],
                    item["distinct_hosts"],
                    item["platform"],
                ),
            )
        ],
        "generation_coverage_urls_may_overlap_between_groups": True,
        "source_content_or_hardware_verified": False,
        "metadata_keyword_overlap_is_not_independent_evidence": True,
        "lack_of_metadata_match_is_not_proof_of_no_support": True,
        "legal_rights_review_required": True,
        "crawler_authorized": False,
        "training_authorized": False,
        "memory_promotion_authorized": False,
    }
    if include_unclassified:
        result["unclassified"] = {
            "raw_link_mentions": unclassified_raw,
            "potentially_unlabeled_platforms": True,
            "training_authorized": False,
        }
    return result
