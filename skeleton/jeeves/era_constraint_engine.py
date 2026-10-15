"""Era constraint engine — Pareto hardware-as-design-feature.

Turns target era into concrete, checkable limits for design and assets.
"""

from __future__ import annotations

from typing import Any

ERA_LIMITS = {
    "8bit": {
        "palette": "very limited, high contrast required",
        "sprites": "few frames, strong silhouette",
        "text": "short, sparse",
        "audio": "simple tones / noise",
        "resolution": "low, readable at native",
    },
    "16bit": {
        "palette": "richer but still constrained per layer/tile",
        "sprites": "modest animation sets",
        "text": "short paragraphs",
        "audio": "chiptune or limited PCM",
        "resolution": "classic 16-bit",
    },
    "handheld": {
        "palette": "small screen, high contrast",
        "sprites": "compact, readable",
        "text": "very short",
        "audio": "short loops, clear SFX",
        "resolution": "handheld native",
    },
    "32bit": {
        "palette": "broader",
        "sprites": "or pre-render clarity",
        "text": "moderate",
        "audio": "CD-quality possible",
        "resolution": "higher, still era-authentic",
    },
}


def constraints_for(era: str) -> dict[str, Any]:
    return {
        "era": era,
        "limits": ERA_LIMITS.get(era, {"note": "respect declared core limits"}),
        "design_rule": "Constraints are features. Do not design past them.",
        "check": "Every asset and text block must pass the limit set before catalog entry",
    }


def violation_examples(era: str) -> list[str]:
    return [
        f"Palette or sprite count exceeding {era} norms",
        "Text blocks too long for readable presentation",
        "UI that obscures the scene",
        "Audio that clips or ignores era instrumentation",
    ]
