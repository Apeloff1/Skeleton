"""House catalog. Pointer atoms. No stored prose."""

from __future__ import annotations

HOUSES: tuple[str, ...] = (
    "nexus", "caldera", "ionwake", "aphelion", "helios", "viscera",
    "sheaf", "spine", "motive", "graphs", "primitives", "cortex",
    "harbor", "chronicle", "genos", "tutolage", "jeeves", "skeleton",
    "hyperion", "mishima", "sabbaten", "zaibatsu", "fieldwalk", "diet",
    "cockpit", "snowball", "era", "queue12", "contact", "moddepth",
    "router", "security", "mobile", "parse", "swarm", "turn",
    "forge", "export", "doctor", "pulse", "bind", "cut",
    "week", "day", "dream", "sleep", "heat", "extract",
    "lineage", "census", "plane", "gate", "loom", "warp",
    "oracle", "ledger", "helix", "merkle", "gossip", "root",
    "organ", "deck", "bank", "clip",
)
ORGANS: tuple[str, ...] = (
    "mass", "pointer", "era", "merkle", "clip", "census", "helix", "gossip",
    "steer", "specdec", "lora", "beam", "accum", "rms", "silu", "qk", "remat",
    "barcode", "cech", "smash", "shunt", "harbor", "bag", "lineage", "cockpit",
    "critique", "emit", "pack", "world", "seed", "heat", "extract", "sleep",
    "doctor", "import", "secret",
)
VERBS: tuple[str, ...] = (
    "observe", "clip", "bind", "hash", "fold", "pulse", "cite", "split", "root",
    "leaf", "steer", "verify", "absorb", "bank", "route", "fail", "scan", "emit",
    "pack", "audit", "pin", "gossip", "tournament", "persist", "prefetch", "starve",
    "balance", "weigh", "reverse", "catalog", "decode", "stock", "place", "prefill",
    "reclaim", "doctor", "improve", "cut", "speak", "forge", "dream", "sleep",
    "heat", "extract", "warp", "tick", "measure", "seal",
)


def catalog_size() -> dict[str, int]:
    return {"houses": len(HOUSES), "organs": len(ORGANS), "verbs": len(VERBS), "modules": len(HOUSES) * len(ORGANS)}
