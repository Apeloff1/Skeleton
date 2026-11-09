from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class CoderStyle:
    key: str
    coder_name: str
    style_name: str
    description: str
    keywords: tuple
    influence: Dict[str, float]


CODER_POOL: Dict[str, CoderStyle] = {
    "casey_muratori": CoderStyle(
        key="casey_muratori",
        coder_name="Casey Muratori",
        style_name="Intentional Clarity",
        description="Explicit control flow, minimal abstraction, performance-aware simplicity.",
        keywords=("explicit", "simple", "performance", "clear"),
        influence={"abstraction": -0.7, "performance_focus": 0.85, "simplicity": 0.95, "comment_density": 0.4},
    ),
    "john_carmack": CoderStyle(
        key="john_carmack",
        coder_name="John Carmack",
        style_name="First Principles Systems",
        description="Deep systems thinking, tight loops, pragmatic engineering.",
        keywords=("systems", "pragmatic", "low-level", "focus"),
        influence={"abstraction": -0.4, "performance_focus": 0.95, "simplicity": 0.7, "math_rigor": 0.8},
    ),
    "mike_acton": CoderStyle(
        key="mike_acton",
        coder_name="Mike Acton",
        style_name="Data-Oriented Design",
        description="Transforms over objects; contiguous data; batch processing.",
        keywords=("dod", "soa", "batch", "cache"),
        influence={"abstraction": -0.8, "performance_focus": 0.9, "data_oriented": 0.95, "simplicity": 0.6},
    ),
    "jonathan_blow": CoderStyle(
        key="jonathan_blow",
        coder_name="Jonathan Blow",
        style_name="Craftsmanship & Taste",
        description="Strong opinions, intentional language design, long-term code health.",
        keywords=("craft", "taste", "intentional", "language"),
        influence={"abstraction": -0.3, "simplicity": 0.75, "explicitness": 0.85},
    ),
    "andrej_karpathy": CoderStyle(
        key="andrej_karpathy",
        coder_name="Andrej Karpathy",
        style_name="Educational Clarity",
        description="Readable ML/systems code that teaches while it runs.",
        keywords=("clear", "educational", "numpy-style", "comments"),
        influence={"comment_density": 0.9, "simplicity": 0.8, "abstraction": 0.1},
    ),
    "fabian_giesen": CoderStyle(
        key="fabian_giesen",
        coder_name="Fabian Giesen",
        style_name="Low-Level Mastery",
        description="Bit-level insight, compression, and careful micro-architecture awareness.",
        keywords=("bits", "compression", "simd", "careful"),
        influence={"performance_focus": 0.95, "abstraction": -0.6, "math_rigor": 0.85},
    ),
    "niklas_frykholm": CoderStyle(
        key="niklas_frykholm",
        coder_name="Niklas Frykholm",
        style_name="Engine Practicality",
        description="Bitsquid/Stingray-style practical engine architecture.",
        keywords=("engine", "resources", "practical"),
        influence={"simplicity": 0.7, "performance_focus": 0.75, "data_oriented": 0.7},
    ),

    "tim_sweeney": CoderStyle(
        key="tim_sweeney",
        coder_name="Tim Sweeney",
        style_name="Engine Platform Ambition",
        description="Large-scale engine architecture, tooling platforms, long-horizon systems.",
        keywords=("engine", "platform", "scale", "tools"),
        influence={"abstraction": 0.2, "performance_focus": 0.75, "simplicity": 0.4},
    ),
    "gabe_newell": CoderStyle(
        key="gabe_newell",
        coder_name="Gabe Newell",
        style_name="Player-Centric Systems",
        description="Ship value to players; pragmatic platform and content pipeline decisions.",
        keywords=("player", "pipeline", "pragmatic", "platform"),
        influence={"simplicity": 0.55, "performance_focus": 0.5, "explicitness": 0.6},
    ),
    "john_romero": CoderStyle(
        key="john_romero",
        coder_name="John Romero",
        style_name="Design-Driven Iteration",
        description="Fast creative iteration with strong level/design feedback loops.",
        keywords=("design", "iterate", "feel", "levels"),
        influence={"simplicity": 0.65, "comment_density": 0.35, "abstraction": -0.2},
    ),
    "christer_ericson": CoderStyle(
        key="christer_ericson",
        coder_name="Christer Ericson",
        style_name="Real-Time Collision Craft",
        description="Geometric robustness and practical real-time collision systems.",
        keywords=("collision", "geometry", "realtime", "robust"),
        influence={"math_rigor": 0.9, "performance_focus": 0.85, "simplicity": 0.55},
    ),
    "brendan_gregg": CoderStyle(
        key="brendan_gregg",
        coder_name="Brendan Gregg",
        style_name="Observability First",
        description="Measure, then optimize; systems performance methodology.",
        keywords=("metrics", "tracing", "perf", "methodology"),
        influence={"observability": 0.95, "performance_focus": 0.8, "comment_density": 0.5},
    ),
}


def get_coder(key: str) -> CoderStyle | None:
    return CODER_POOL.get(key)


def list_coders() -> list[dict[str, Any]]:
    return [
        {
            "key": c.key,
            "coder_name": c.coder_name,
            "style_name": c.style_name,
            "description": c.description,
            "keywords": list(c.keywords),
            "influence": c.influence,
        }
        for c in CODER_POOL.values()
    ]
