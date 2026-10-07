"""Worldforge naming — REALISM DOCTRINE name generator + toponym etymology.

Extracted from worldforge.py (Session 13c refactor). Real-world toponymy (Earth
place-name morphology) for terrestrial scales + real astronomical catalogue
designations for cosmic scales. Zero fantasy, zero Tolkien syllables, zero invented
mythos. Every name could plausibly appear on a real map (USGS GNIS / OpenStreetMap)
or in a real star catalogue (HD/Gliese/NGC/Bayer). Deterministic via _h01.
"""
from __future__ import annotations

from .worldforge_noise import _h01

_TOPO_DESC = {
    "default":  ["Red", "White", "Black", "Green", "Grey", "Blue", "Clear", "Cold",
                 "High", "Long", "Great", "Little", "Fair", "New", "Old", "Stone",
                 "Iron", "Silver", "Gold", "North", "South", "East", "West", "Mill"],
    "forest":   ["Oak", "Pine", "Cedar", "Ash", "Elm", "Birch", "Maple", "Willow",
                 "Aspen", "Fern", "Spruce", "Hazel", "Alder", "Hickory"],
    "coast":    ["Salt", "Bay", "Tide", "Pearl", "Anchor", "Gull", "Reef", "Marsh",
                 "Surf", "Cape", "Sea", "Bayou"],
    "arid":     ["Sand", "Ochre", "Dust", "Mesa", "Dune", "Sun", "Cactus", "Copper",
                 "Rust", "Bone", "Flint", "Adobe"],
    "cold":     ["Frost", "Glacier", "Snow", "Ice", "Pale", "Winter", "Aurora",
                 "Cobalt", "Crystal", "Polar", "Birch"],
    "mountain": ["Granite", "Slate", "Marble", "Ridge", "Cliff", "Summit", "Eagle",
                 "Boulder", "Quartz", "Basalt", "Pinnacle"],
    "tropical": ["Palm", "Mango", "Cane", "Cocoa", "Emerald", "Monsoon", "Jade",
                 "Orchid", "Teak", "Mahogany"],
}
_TOPO_FUSED = ["ton", "ville", "field", "ford", "burg", "borough", "dale", "vale",
               "wood", "wick", "mouth", "haven", "port", "hampton", "bury", "stead",
               "well", "brook", "ridge", "crest", "view", "side", "land", "gate"]
_TOPO_GENERIC = ["Creek", "Falls", "Springs", "Bluff", "Bend", "Crossing", "Flats",
                 "Heights", "Basin", "Hollow", "Junction", "Landing", "Point", "Mesa",
                 "Pass", "Cove", "Mills", "Hills", "Valley", "Ridge", "Plains", "Reach",
                 "Delta", "Gorge", "Glen", "Harbor", "Meadows"]
_TOPO_REGION = ["Basin", "Plateau", "Lowlands", "Highlands", "Plains", "Valley", "Range",
                "Coast", "Peninsula", "Delta", "Steppe", "Uplands", "Watershed",
                "Province", "Territory", "Flats", "Massif", "Escarpment"]
_TOPO_PREFIX = ["Fort", "Port", "Mount", "Lake", "Cape", "Saint", "New", "Grand"]
_TOPO_SURNAME = ["Calder", "Hadley", "Whitman", "Brennan", "Hollis", "Marlowe", "Aberdeen",
                 "Sterling", "Donovan", "Ashford", "Carrington", "Lindgren", "Okonkwo",
                 "Vasquez", "Nakamura", "Halloran", "Brandt", "Esposito", "Mbeki", "Larsen"]

# real astronomical catalogues / designations
_GREEK = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta",
          "Iota", "Kappa", "Lambda", "Mu", "Nu", "Xi", "Omicron", "Sigma", "Tau", "Upsilon"]
_CONSTEL = ["Andromedae", "Aquarii", "Aquilae", "Arietis", "Aurigae", "Bootis", "Cancri",
            "Canis Majoris", "Capricorni", "Carinae", "Cassiopeiae", "Centauri", "Ceti",
            "Cygni", "Draconis", "Eridani", "Geminorum", "Herculis", "Hydrae", "Leonis",
            "Lyrae", "Orionis", "Pegasi", "Persei", "Sagittarii", "Scorpii", "Tauri",
            "Ursae Majoris", "Virginis", "Velorum"]
_STAR_CAT = ["HD", "HIP", "HR", "Gliese", "Kepler", "TOI", "Wolf", "Ross", "LHS", "GJ", "TRAPPIST"]
_DEEPSKY_CAT = ["NGC", "Messier", "IC", "UGC", "Abell", "Caldwell", "PGC"]


def _biome_topo_key(biome):
    if biome in ("beach", "wetland"):
        return "coast"
    if biome in ("desert", "savanna"):
        return "arid"
    if biome in ("snow", "tundra", "taiga"):
        return "cold"
    if biome == "bare":
        return "mountain"
    if biome == "tropical_forest":
        return "tropical"
    if biome in ("temperate_forest", "shrubland"):
        return "forest"
    return "default"


def _astro_name(h, deep=False):
    if deep:
        cat = _DEEPSKY_CAT[h % len(_DEEPSKY_CAT)]
        return f"{cat} {(h // 7) % 9000 + 100}"
    if h % 100 < 35:
        return f"{_GREEK[h % len(_GREEK)]} {_CONSTEL[(h // 11) % len(_CONSTEL)]}"
    cat = _STAR_CAT[(h // 13) % len(_STAR_CAT)]
    return f"{cat} {(h // 17) % 9000 + 100}"


def _name(seed, rx, ry, space=False, biome=None, kind=None):
    h = int(_h01(rx, ry, seed) * 1e9)
    if space:
        deep = kind in ("galaxy", "cosmos", "nebula", "spiral", "elliptical",
                        "cluster", "quasar", "core")
        return _astro_name(h, deep=deep)
    if kind is None:
        # broad regional name: "<Descriptor> <Region generic>" (e.g. "Granite Basin")
        desc = _TOPO_DESC["default"][h % len(_TOPO_DESC["default"])]
        return f"{desc} {_TOPO_REGION[(h // 7) % len(_TOPO_REGION)]}"
    # biome-aware settlement toponym across 4 real-world naming patterns
    pool = _TOPO_DESC[_biome_topo_key(biome)] + _TOPO_DESC["default"]
    desc = pool[h % len(pool)]
    pat = (h // 31) % 4
    if pat == 0:
        return f"{desc}{_TOPO_FUSED[(h // 7) % len(_TOPO_FUSED)]}"
    if pat == 1:
        return f"{desc} {_TOPO_GENERIC[(h // 7) % len(_TOPO_GENERIC)]}"
    if pat == 2:
        return f"{_TOPO_PREFIX[(h // 13) % len(_TOPO_PREFIX)]} {_TOPO_SURNAME[(h // 5) % len(_TOPO_SURNAME)]}"
    return f"{_TOPO_SURNAME[(h // 5) % len(_TOPO_SURNAME)]}{_TOPO_FUSED[(h // 19) % len(_TOPO_FUSED)]}"


# ── 📄 SCIENTIFIC NAME KEY — real-world toponymic etymology of generated names ──
# Glosses ground each morpheme in genuine Earth place-name conventions (USGS GNIS /
# Ordnance Survey style), so every generated name is explainable, not invented mythos.
_TOPO_GLOSS = {
    # fused generic suffixes (Old English / Norse / Latin roots used across real maps)
    "ton": "OE tūn — an enclosed farmstead or village", "ville": "Latin villa — a town/estate",
    "field": "OE feld — open cleared land", "ford": "OE — a shallow river crossing",
    "burg": "Germanic — a fortified town", "borough": "OE burh — a fortified settlement",
    "dale": "ON dalr — a valley", "vale": "Latin vallis — a valley",
    "wood": "OE wudu — woodland", "wick": "OE wīc / Latin vicus — a dwelling or trading place",
    "mouth": "OE mūþa — a river estuary", "haven": "OE hæfen — a sheltered harbour",
    "port": "Latin portus — a harbour town", "hampton": "OE hām-tūn — a home settlement",
    "bury": "OE byrig — a fortified place", "stead": "OE stede — a settlement site",
    "well": "OE wella — a spring", "brook": "OE brōc — a small stream",
    "ridge": "OE hrycg — an elongated crest of high ground", "crest": "Latin crista — a summit ridge",
    "view": "a scenic vantage / overlook", "side": "OE — beside a feature (hillside/lakeside)",
    "land": "OE — a tract of ground", "gate": "ON gata — a road or mountain pass",
    # standalone generic terms
    "Creek": "a small watercourse", "Falls": "a waterfall", "Springs": "natural groundwater seeps",
    "Bluff": "a steep headland or cliff", "Bend": "a meander of a river", "Crossing": "a fording point",
    "Flats": "level alluvial ground", "Heights": "elevated terrain", "Basin": "a drainage depression",
    "Hollow": "a small sheltered valley", "Junction": "a confluence or route meeting-point",
    "Landing": "a riverside/coastal docking place", "Point": "a promontory", "Mesa": "a flat-topped upland",
    "Pass": "a gap through high ground", "Cove": "a sheltered coastal inlet", "Mills": "a watermill site",
    "Hills": "rolling high ground", "Valley": "a lowland between hills", "Plains": "extensive flat land",
    "Reach": "a straight stretch of river/coast", "Delta": "a river's depositional mouth",
    "Gorge": "a deep narrow ravine", "Glen": "a narrow glaciated valley", "Harbor": "a sheltered anchorage",
    "Meadows": "low grassland", "Plateau": "an elevated plain", "Lowlands": "low-lying terrain",
    "Highlands": "mountainous upland", "Range": "a line of mountains", "Coast": "the land–sea margin",
    "Peninsula": "land projecting into water", "Steppe": "semi-arid grassland", "Uplands": "higher ground",
    "Watershed": "a drainage divide", "Massif": "a compact mountain block", "Escarpment": "a long cliff/scarp",
    # prefixes
    "Fort": "a fortified/garrison settlement", "Port": "a harbour settlement",
    "Mount": "named for an adjacent mountain", "Lake": "named for an adjacent lake",
    "Cape": "named for a coastal headland", "Saint": "named for a patron (hagiotoponym)",
    "New": "a daughter settlement named after an older one", "Grand": "denoting the larger of paired sites",
}


def _explain_toponym(name: str, biome: str = None):
    """Decompose a generated toponym into real-world morphemes + glosses."""
    parts = []
    words = name.split()
    # prefix pattern (Fort/Port/Saint X)
    if words and words[0] in _TOPO_GLOSS and len(words) > 1:
        parts.append({"part": words[0], "meaning": _TOPO_GLOSS[words[0]]})
        parts.append({"part": " ".join(words[1:]), "meaning": "settler/surname or feature element"})
        return parts
    # standalone generic (Descriptor + Generic)
    if len(words) == 2 and words[1] in _TOPO_GLOSS:
        parts.append({"part": words[0], "meaning": "descriptive element (colour/material/flora/landform)"})
        parts.append({"part": words[1], "meaning": _TOPO_GLOSS[words[1]]})
        return parts
    # fused single word — find the longest known suffix
    low = name.lower()
    for suf in sorted(_TOPO_GLOSS, key=len, reverse=True):
        if suf.islower() and low.endswith(suf) and len(low) > len(suf):
            parts.append({"part": name[: len(name) - len(suf)], "meaning": "descriptive root (colour/material/flora/founder)"})
            parts.append({"part": suf, "meaning": _TOPO_GLOSS[suf]})
            return parts
    parts.append({"part": name, "meaning": "compound toponym following Earth naming conventions"})
    return parts
