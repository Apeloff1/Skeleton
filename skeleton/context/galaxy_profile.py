"""Bounded, versioned Galaxy Studio authoring metadata for GameForge output.

Full 14-matrix questionnaire payloads are accepted as inert source data,
never passed into code execution or interpreted as authorization to write
outside the caller's selected project. A canonical source artifact makes
the original design inspectable and reproducible after Forge export.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping, Optional

SCHEMA = "skeleton.gameforge.galaxy_profile.v1"
ARTIFACT_PATH = "design/galaxy_studio_profile.json"
MATRIX_FIELDS = (
    "mechanics_matrix", "world_matrix", "art_matrix", "audio_matrix",
    "tech_matrix", "monetisation_matrix", "qa_matrix", "agent_matrix",
    "vector_db_matrix", "plagiarism_matrix", "rdbms_matrix", "styles_matrix",
    "mutation_matrix", "unique_flair_matrix",
)
_MAX_BYTES = 600_000
_MAX_NODES = 24_000
_MAX_DEPTH = 9
_MAX_LIST = 4096
_KEY = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$")
_BLOCKED = frozenset(("__proto__", "prototype", "constructor"))


def _walk(value: Any, depth: int, count: list[int]) -> None:
    count[0] += 1
    if count[0] > _MAX_NODES or depth > _MAX_DEPTH:
        raise ValueError("Galaxy profile complexity exceeds limit")
    if value is None or type(value) is bool:
        return
    if type(value) in (int, float):
        if (type(value) is int and value.bit_length() > 53) or (
            type(value) is float and not math.isfinite(value)
        ):
            raise ValueError("non-finite or unsafe Galaxy number")
        return
    if type(value) is str:
        if len(value) > 12_000:
            raise ValueError("Galaxy text field exceeds limit")
        return
    if type(value) is list:
        if len(value) > _MAX_LIST:
            raise ValueError("Galaxy list exceeds limit")
        for child in value:
            _walk(child, depth + 1, count)
        return
    if type(value) is not dict or len(value) > _MAX_LIST:
        raise ValueError("Galaxy profile contains unsupported input")
    for key, child in value.items():
        if type(key) is not str or not _KEY.fullmatch(key) or key in _BLOCKED:
            raise ValueError("invalid Galaxy profile key")
        _walk(child, depth + 1, count)


def canonical_profile_bytes(profile: Mapping[str, Any]) -> bytes:
    return json.dumps(profile, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def normalise_galaxy_profile(raw: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    """Reject malformed/huge profile before the canonical ten-stage run starts."""
    if raw is None:
        return None
    if type(raw) is not dict or set(raw) != {"schema", "config"} or raw["schema"] != SCHEMA:
        raise ValueError("unsupported Galaxy questionnaire schema")
    config = raw["config"]
    if type(config) is not dict or type(config.get("title")) is not str or not config["title"].strip() \
            or len(config["title"]) > 120 or type(config.get("genre")) is not str \
            or not 1 <= len(config["genre"]) <= 128:
        raise ValueError("Galaxy profile requires a bounded title and genre")
    if any(type(config.get(field)) is not dict for field in MATRIX_FIELDS):
        raise ValueError("missing a Galaxy production matrix")
    for field in (*MATRIX_FIELDS, "narrative_phases"):
        phases = config[field]
        if len(phases) > 512:
            raise ValueError("too many Galaxy matrix phases")
        for values in phases.values():
            if type(values) is not dict or len(values) > 128 or any(
                type(value) not in (int, float) or not math.isfinite(value)
                or not 0 <= value <= 1000
                for value in values.values()
            ):
                raise ValueError("invalid Galaxy matrix axis value")
    if any(type(config.get(field)) is not dict for field in ("narrative_phases", "extra_params", "style_params")):
        raise ValueError("missing Galaxy narrative, extended or style controls")
    _walk(raw, 0, [0])
    encoded = canonical_profile_bytes(raw)
    if len(encoded) > _MAX_BYTES:
        raise ValueError("Galaxy profile exceeds 600KB")
    # Canonical JSON restores plain unaliased source metadata.
    return json.loads(encoded)


def galaxy_profile_receipt(profile: Mapping[str, Any]) -> dict[str, Any]:
    encoded = canonical_profile_bytes(profile)
    cfg = profile["config"]
    return {
        "schema": SCHEMA,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded),
        "source": "galaxy_studio",
        "artifact": ARTIFACT_PATH,
        "matrices": len(MATRIX_FIELDS),
        "narrative_phases": len(cfg["narrative_phases"]),
        "extra_controls": len(cfg["extra_params"]),
        "styles": len(cfg["style_params"]),
    }


def attach_galaxy_profile(files: Mapping[str, str], profile: Optional[Mapping[str, Any]]) -> dict[str, str]:
    """Attach a source-only JSON artifact; do not alter executable game code."""
    result = dict(files)
    if profile is None:
        return result
    if ARTIFACT_PATH in result:
        raise ValueError("Galaxy design artifact path collision")
    result[ARTIFACT_PATH] = canonical_profile_bytes(profile).decode("ascii") + "\n"
    return result
