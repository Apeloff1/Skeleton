"""GB-46 law. Five-axis cue. Tokens only. Stimulus dropped."""

from __future__ import annotations

PACKET = "GB-46"
LAYER = "cue"
VERSION = "1.0"
PARENT = "#80"
CITATION = "docs/lineage/cue.md"
STORED_PROSE = 0
AXES = ("house", "topic", "depth", "think", "obscure")
HOUSE = ("xarchive", "archive", "x", "github", "arxiv")
TOPIC = ("plan", "loop", "kv", "attn", "forge")
DEPTH = ("r1", "r2", "r3halt", "smelt", "etd")
THINK = ("why", "how", "reason", "proof", "latent")
OBSCURE = ("yarn", "sink", "mla", "softpick", "qkmla", "aqnoise")
VOCAB = {
    "house": HOUSE,
    "topic": TOPIC,
    "depth": DEPTH,
    "think": THINK,
    "obscure": OBSCURE,
}
