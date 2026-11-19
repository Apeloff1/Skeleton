"""Canonical bounded 14-matrix Galaxy authoring source for a Forge run.

Maintains the user's explicit Galaxy questionnaire separately from the
compressed Forge design tensor; no model, template, or service may claim
that a condensed genre vote captures all original authored dimensions.
Validation and serialization are deterministic, read-only and safe to run
both at API admission and again at the pipeline execution boundary.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any

PROFILE_SCHEMA = "skeleton.gameforge.galaxy_profile.v1"
RECEIPT_SCHEMA = "skeleton.gameforge.galaxy_authoring_source.v1"
PROFILE_PATH = "docs/galaxy_profile.json"
MATRIX_FIELDS = (
    "mechanics_matrix", "world_matrix", "art_matrix", "audio_matrix",
    "tech_matrix", "monetisation_matrix", "qa_matrix", "agent_matrix",
    "vector_db_matrix", "plagiarism_matrix", "rdbms_matrix",
    "styles_matrix", "mutation_matrix", "unique_flair_matrix",
)
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_RESERVED = frozenset(("__proto__", "prototype", "constructor"))
MAX_CHARS = 450_000
MAX_FIELDS = 24_000
MAX_DEPTH = 9


class GalaxyAuthoringError(ValueError):
    """An original Galaxy authoring profile violates the transport contract."""


def _walk(value: Any, *, budget: list[int], depth: int = 0) -> None:
    budget[0] += 1
    if budget[0] > MAX_FIELDS or depth > MAX_DEPTH:
        raise GalaxyAuthoringError("Galaxy profile complexity budget exceeded")
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if abs(value) > (2 ** 53 - 1):
            raise GalaxyAuthoringError("Galaxy profile integer exceeds JSON-safe range")
        return
    if type(value) is float:
        if not math.isfinite(value) or abs(value) > 2 ** 53 - 1:
            raise GalaxyAuthoringError("Galaxy profile has unsafe numeric values")
        return
    if type(value) is str:
        if len(value) > 12_000:
            raise GalaxyAuthoringError("Galaxy profile string exceeds transport budget")
        return
    if type(value) is list:
        if len(value) > 4096:
            raise GalaxyAuthoringError("Galaxy profile array exceeds transport budget")
        for item in value:
            _walk(item, budget=budget, depth=depth + 1)
        return
    if type(value) is dict:
        if len(value) > 4096:
            raise GalaxyAuthoringError("Galaxy profile object exceeds transport budget")
        for key, item in value.items():
            if (type(key) is not str or KEY_RE.fullmatch(key) is None
                    or key in _RESERVED):
                raise GalaxyAuthoringError("Galaxy profile has untrusted property name")
            _walk(item, budget=budget, depth=depth + 1)
        return
    raise GalaxyAuthoringError("Galaxy profile contains non-JSON data")


def normalise_galaxy_authoring(profile: object) -> dict[str, Any]:
    """Reject incomplete, mixed-schema or oversized authored source."""
    if type(profile) is not dict or set(profile) != {"schema", "config"}:
        raise GalaxyAuthoringError("Galaxy authoring profile must be exactly versioned")
    if profile["schema"] != PROFILE_SCHEMA or type(profile["config"]) is not dict:
        raise GalaxyAuthoringError("Galaxy authoring profile schema or content invalid")
    config = profile["config"]
    if (type(config.get("title")) is not str or not config["title"].strip()
            or len(config["title"]) > 120
            or type(config.get("genre")) is not str or not config["genre"]
            or len(config["genre"]) > 128):
        raise GalaxyAuthoringError("Galaxy authored title or genre is invalid")
    for name in (*MATRIX_FIELDS, "narrative_phases"):
        matrix = config.get(name)
        if type(matrix) is not dict or len(matrix) > 512:
            raise GalaxyAuthoringError("Galaxy authoring is missing a bounded matrix")
        for axes in matrix.values():
            if type(axes) is not dict or len(axes) > 128:
                raise GalaxyAuthoringError("Galaxy matrix axes are malformed")
            if any(type(n) not in (int, float)
                   or not math.isfinite(n) or not 0 <= n <= 1000
                   for n in axes.values()):
                raise GalaxyAuthoringError("Galaxy matrix values must be finite and bounded")
    if type(config.get("extra_params")) is not dict or type(config.get("style_params")) is not dict:
        raise GalaxyAuthoringError("Galaxy extra/style control maps are required")
    _walk(config, budget=[0])
    try:
        raw = json.dumps(profile, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
        if len(raw) > MAX_CHARS or len(raw.encode("utf-8")) > MAX_CHARS:
            raise GalaxyAuthoringError("Galaxy profile exceeds 450 KB")
        copy = json.loads(raw)
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        if isinstance(exc, GalaxyAuthoringError):
            raise
        raise GalaxyAuthoringError("Galaxy authoring is not safely serializable") from None
    return copy


def authored_source(profile: object) -> tuple[str, dict[str, object]]:
    validated = normalise_galaxy_authoring(profile)
    output = json.dumps(validated, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), allow_nan=False) + "\n"
    data = output.encode("utf-8")
    if len(data) > MAX_CHARS:
        raise GalaxyAuthoringError("Galaxy profile exceeds source file budget")
    return output, {
        "schema": RECEIPT_SCHEMA,
        "path": PROFILE_PATH,
        "sha256": hashlib.sha256(data).hexdigest(),
        "byte_count": len(data),
        "matrix_count": len(MATRIX_FIELDS),
        "native_gameplay_qualified": False,
        "full_original_authoring_preserved": True,
    }


__all__ = [
    "PROFILE_SCHEMA", "RECEIPT_SCHEMA", "PROFILE_PATH", "MATRIX_FIELDS",
    "GalaxyAuthoringError", "normalise_galaxy_authoring", "authored_source",
]
