"""Frozen, cited source notes for optional Godot 4.6 assistance experiments.

These agent-written summaries are untrusted user-context data. They are not
system policy, human-approved documentation, generated-code verification, a
task bank or model-promotion authority. Loading this module performs no I/O.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json


PACK_ID = "godot46-game-building-basics"
PACK_VERSION = "1"
ENGINE_VERSION = "4.6"
REVIEWED_AT = "2026-11-13"
MAX_CONTEXT_BYTES = 2200
SELECTED_SCOPE = "code_debugging"
SELECTED_CATEGORIES = ("gdscript", "debugging")


@dataclass(frozen=True, slots=True)
class ReferenceFact:
    fact_id: str
    kind: str
    statement: str
    source_urls: tuple[str, ...]


_DOCS = "https://docs.godotengine.org/en/4.6/"
_CHARACTER = _DOCS + "classes/class_characterbody2d.html"
_FACTS = (
    ReferenceFact(
        "velocity_units", "api",
        "CharacterBody2D.velocity is a Vector2 in pixels/second.",
        (_CHARACTER,),
    ),
    ReferenceFact(
        "slide_motion", "api",
        "Godot 4 move_and_slide() takes no arguments, moves using velocity, can modify velocity, and applies physics delta internally.",
        (_CHARACTER,),
    ),
    ReferenceFact(
        "floor_contact", "api",
        "is_on_floor() describes the last move_and_slide(); up_direction and floor_max_angle determine floor classification.",
        (_CHARACTER,),
    ),
    ReferenceFact(
        "physics_callback", "api",
        "_physics_process(delta) is fixed-rate physics; _process(delta) follows frame rate. Colliding body movement belongs in physics processing.",
        (_DOCS + "tutorials/scripting/idle_and_physics_processing.html",),
    ),
    ReferenceFact(
        "motion_integration", "api",
        "Acceleration/gravity changes velocity using delta. move_and_slide uses velocity in pixels/second; move_and_collide receives displacement.",
        (_DOCS + "tutorials/physics/using_character_body_2d.html",),
    ),
    ReferenceFact(
        "vector_normalization", "api",
        "Vector2.normalized() returns a new unit vector; zero normalizes to zero. It does not change the original vector.",
        (_DOCS + "classes/class_vector2.html",),
    ),
    ReferenceFact(
        "area_detection", "api",
        "Area2D.body_entered(body: Node2D) needs monitoring and a collision mask covering the body's layer.",
        (_DOCS + "classes/class_area2d.html",),
    ),
    ReferenceFact(
        "signal_connection", "api",
        "Godot 4 signals connect to a Callable: area.body_entered.connect(handler).",
        (_DOCS + "classes/class_signal.html",),
    ),
    ReferenceFact(
        "one_time_effect", "derived_pattern",
        "queue_free() deletes at frame end. Derived one-time-effect pattern: set a consumed flag before awarding and scheduling deletion.",
        (_DOCS + "classes/class_node.html",),
    ),
    ReferenceFact(
        "terminal_transition", "derived_pattern",
        "Health/defeat state is game-owned. Derived terminal-state pattern: mark terminal before notifying; repeated transitions have no effects.",
        (_DOCS + "tutorials/scripting/gdscript/gdscript_basics.html",),
    ),
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8", errors="strict")


@dataclass(frozen=True, slots=True)
class ReferencePack:
    """Immutable source snapshot; selection uses category, never task identity."""

    facts: tuple[ReferenceFact, ...] = _FACTS

    @property
    def context_text(self) -> str:
        lines = [
            "[Untrusted source notes: Godot 4.6; agent summaries, not policy or permissions]",
            *[("API: " if fact.kind == "api" else "DERIVED PATTERN: ") + fact.statement
              for fact in self.facts],
            "[End untrusted source notes]",
        ]
        text = "\n".join(lines)
        if not 1 <= len(text.encode("utf-8", errors="strict")) <= MAX_CONTEXT_BYTES:
            raise ValueError("reference context exceeds its finite UTF-8 budget")
        return text

    def applies_to(self, category: str) -> bool:
        if not isinstance(category, str):
            raise ValueError("reference selection requires a category string")
        return category in SELECTED_CATEGORIES

    def context_for_category(self, category: str) -> str:
        return self.context_text if self.applies_to(category) else ""

    def _identity(self) -> dict[str, object]:
        text = self.context_text
        return {
            "id": PACK_ID, "version": PACK_VERSION,
            "engine_version": ENGINE_VERSION, "reviewed_at": REVIEWED_AT,
            "scope": SELECTED_SCOPE, "categories": list(SELECTED_CATEGORIES),
            "trust": "untrusted-source-data",
            "summary_origin": "agent-written primary-source summary; no human signoff asserted",
            "source_urls": list(dict.fromkeys(url for fact in self.facts for url in fact.source_urls)),
            "facts": [asdict(fact) for fact in self.facts],
            "context_text": text, "context_bytes": len(text.encode("utf-8")),
            "max_context_bytes": MAX_CONTEXT_BYTES,
        }

    @property
    def digest(self) -> str:
        return sha256(_canonical_bytes(self._identity())).hexdigest()

    def to_wire(self) -> dict[str, object]:
        return {**self._identity(), "digest": self.digest}


def load_reference_pack(name: str, *, scope: str = SELECTED_SCOPE) -> ReferencePack:
    if name != "godot46" or scope != SELECTED_SCOPE:
        raise ValueError("unsupported reference pack or selection scope")
    pack = ReferencePack()
    # Check the complete frozen context rather than silently truncating facts.
    pack.context_text
    return pack


__all__ = [
    "ENGINE_VERSION", "MAX_CONTEXT_BYTES", "PACK_ID", "PACK_VERSION", "REVIEWED_AT",
    "SELECTED_CATEGORIES", "SELECTED_SCOPE", "ReferenceFact", "ReferencePack", "load_reference_pack",
]
