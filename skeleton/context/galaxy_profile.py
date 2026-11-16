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
            type(value) is float and (not math.isfinite(value) or abs(value) > 2**53 - 1)
        ):
            raise ValueError("non-finite or unsafe Galaxy number")
        return
    if type(value) is str:
        if len(value) > 12_000:
            raise ValueError("Galaxy text field exceeds limit")
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise ValueError("invalid Galaxy Unicode text") from exc
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
    # Check structure before serialization, then count actual escaped bytes.
    # iterencode avoids allocating a multi-megabyte encoded profile before
    # rejecting it; every individual string already has a bounded length.
    _walk(profile, 0, [0])
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False)
    output = bytearray()
    for part in encoder.iterencode(profile):
        if len(part) > _MAX_BYTES - len(output):
            raise ValueError("Galaxy profile exceeds 600KB")
        output.extend(part.encode("ascii"))
    return bytes(output)


def normalise_galaxy_profile(raw: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    """Reject malformed/huge profile before the canonical ten-stage run starts."""
    if raw is None:
        return None
    if type(raw) is not dict or len(raw) != 2:
        raise ValueError("unsupported Galaxy questionnaire schema")
    encoded = canonical_profile_bytes(raw)
    # Semantic validation operates on the same detached object that is
    # admitted and returned, not on mutable caller-owned references.
    raw = json.loads(encoded)
    if set(raw) != {"schema", "config"} or raw["schema"] != SCHEMA:
        raise ValueError("unsupported Galaxy questionnaire schema")
    config = raw["config"]
    if type(config) is not dict or type(config.get("title")) is not str or not config["title"].strip() \
            or len(config["title"]) > 120 or type(config.get("genre")) is not str \
            or not 1 <= len(config["genre"]) <= 128:
        raise ValueError("Galaxy profile requires a bounded title and genre")
    if any(type(config.get(field)) is not dict for field in MATRIX_FIELDS):
        raise ValueError("missing a Galaxy production matrix")
    if any(type(config.get(field)) is not dict for field in ("narrative_phases", "extra_params", "style_params")):
        raise ValueError("missing Galaxy narrative, extended or style controls")
    for field in (*MATRIX_FIELDS, "narrative_phases"):
        phases = config[field]
        if len(phases) > 512:
            raise ValueError("too many Galaxy matrix phases")
        for values in phases.values():
            if type(values) is not dict or len(values) > 128 or any(
                type(value) not in (int, float)
                or (type(value) is int and value.bit_length() > 53)
                or (type(value) is float and not math.isfinite(value))
                or not 0 <= value <= 1000
                for value in values.values()
            ):
                raise ValueError("invalid Galaxy matrix axis value")
    # Extra controls are numeric sliders, not JSON boolean switches.
    # Python bool otherwise silently acts like 0 or 1 in arithmetic.
    if any(type(value) is bool for value in config["extra_params"].values()):
        raise ValueError("Galaxy numeric slider cannot be boolean")
    return raw


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
    if any(name.casefold() == ARTIFACT_PATH.casefold() for name in result):
        raise ValueError("Galaxy design artifact path collision")
    result[ARTIFACT_PATH] = canonical_profile_bytes(profile).decode("ascii") + "\n"
    return result


def apply_galaxy_mechanics(plan: Any, profile: Optional[Mapping[str, Any]]) -> tuple[Any, Optional[dict[str, Any]]]:
    """Compile *supported* historical mechanics into real Godot world settings.

    The original 14 matrices describe much more than the current Godot
    extraction runtime supports. Currently only an explicit, nonzero
    ranged/gunplay mechanic means "start with a weapon". This directly
    drives emitted GameState.gd and data/build_plan.json. All other dials
    remain source-bound project design, not falsely presented as gameplay.
    """
    if profile is None:
        return plan, None
    from dataclasses import replace

    mechanics = profile["config"]["mechanics_matrix"]
    requested = tuple(
        f"mechanics_matrix.{name}.count"
        for name in ("gunplay", "ranged")
        if mechanics.get(name, {}).get("count", 0) > 0
    )
    active_total = sum(
        1
        for key in MATRIX_FIELDS
        for axes in profile["config"][key].values()
        for value in axes.values()
        if value > 0
    )
    receipt: dict[str, Any] = {
        "schema": "skeleton.gameforge.galaxy_mechanics.v1",
        "source_sha256": galaxy_profile_receipt(profile)["sha256"],
        "active_matrix_dials": active_total,
        "supported_inputs": list(requested),
        "applied": [],
        "unmapped_matrix_dials": active_total - len(requested),
    }
    if requested:
        prior = plan.spawn_weapon
        if not prior:
            plan = replace(
                plan,
                spawn_weapon=True,
                notes=[*plan.notes, "Galaxy requested ranged/gunplay: equip starting weapon"],
            )
        receipt["applied"].append({
            "target": "build_plan.spawn_weapon",
            "value": True,
            "changed": not prior,
            "source": list(requested),
        })
    # The Godot world generator supports only combat, loot and heat room
    # categories. Treat historical matrix counts as explicit votes for those
    # real room distributions, not as fictitious new world biomes.
    categories = (
        ("combat", "mechanics_matrix", ("melee", "tactical")),
        ("loot", "mechanics_matrix", ("crafting", "forging")),
        ("heat", "world_matrix", ("volcanic",)),
    )
    votes = []
    for category, matrix_name, features in categories:
        matrix = profile["config"][matrix_name]
        activated = [
            (feature, matrix.get(feature, {}).get("count", 0))
            for feature in features if matrix.get(feature, {}).get("count", 0) > 0
        ]
        if activated:
            strength = sum(value for _, value in activated)
            sources = [f"{matrix_name}.{feature}.count" for feature, _ in activated]
            receipt["supported_inputs"].extend(sources)
            votes.append((strength, category, sources))
    if votes:
        strongest = max(weight for weight, _, _ in votes)
        _, chosen, sources = next(v for v in votes if v[0] == strongest)
        prior = plan.room_bias
        if chosen != prior:
            plan = replace(
                plan, room_bias=chosen,
                notes=[*plan.notes, f"Galaxy room distribution {chosen}: {', '.join(sources)}"],
            )
        receipt["applied"].append({
            "target": "build_plan.room_bias", "value": chosen,
            "changed": chosen != prior, "source": sources,
        })
        receipt["room_votes"] = {category: strength for strength, category, _ in votes}
    receipt["unmapped_matrix_dials"] = max(0, active_total - len(receipt["supported_inputs"]))
    return plan, receipt


# Sparse historical authoring -> existing native gameplay compiler.
# A zero is the historical default, not an explicit zero-valued Forge edit.
# Saturating maximum avoids additive amplification across related dials.
PLAYABLE_RECEIPT_PATH = "design/galaxy_playable_controls.json"
PLAYABLE_RECEIPT_SCHEMA = "skeleton.gameforge.galaxy_playable_controls.v1"
_M = "mechanics_matrix"
_W = "world_matrix"
_PLAYABLE_RULES = {
    "extraction": {
        "grind": ((_W, "dungeon", "secrets"), (_W, "ruin", "secrets"), (_M, "investigation", "count")),
        "risk": ((_W, "volcanic", "complexity"), (_W, "wasteland", "complexity")),
        "scarcity": ((_W, "desert", "complexity"), (_W, "tundra", "complexity")),
        "agency": ((_M, "crafting", "complexity"), (_M, "trading", "complexity")),
    },
    "combat_loop": {
        "lethality": ((_M, "melee", "complexity"), (_M, "gunplay", "complexity"), (_M, "ranged", "complexity")),
        "grind": ((_W, "raid", "count"), (_W, "lair", "count"), (_M, "tactical", "count")),
        "agency": ((_M, "melee", "intricacy"), (_M, "tactical", "intricacy")),
    },
    "pipeline": {
        "risk": ((_M, "economy", "complexity"),),
        "scarcity": ((_M, "economy", "intricacy"), (_M, "trading", "complexity")),
        "grind": ((_M, "building", "count"), (_M, "crafting", "count"), (_M, "forging", "count")),
        "agency": ((_M, "building", "intricacy"), (_M, "crafting", "intricacy")),
    },
    "puzzle": {
        "opacity": ((_M, "puzzle", "complexity"), (_M, "investigation", "complexity")),
        "grind": ((_M, "puzzle", "count"),),
        "agency": ((_M, "puzzle", "intricacy"),),
    },
    "racing": {
        "risk": ((_M, "driving", "complexity"),),
        "scarcity": ((_M, "economy", "complexity"),),
        "grind": ((_M, "driving", "count"),),
        "agency": ((_M, "driving", "intricacy"),),
    },
    "survival": {
        "risk": ((_W, "weather", "complexity"), (_W, "volcanic", "complexity")),
        "scarcity": ((_W, "desert", "complexity"), (_W, "tundra", "complexity"), (_W, "wasteland", "complexity")),
        "grind": ((_M, "cooking", "count"), (_M, "farming", "count")),
        "agency": ((_M, "farming", "intricacy"),),
    },
    "stealth": {
        "risk": ((_M, "stealth", "complexity"),),
        "lethality": ((_M, "stealth", "secrets"),),
        "grind": ((_M, "stealth", "count"), (_M, "hacking", "count")),
        "opacity": ((_M, "stealth", "intricacy"), (_M, "hacking", "intricacy")),
        "agency": ((_M, "hacking", "complexity"),),
    },
    "crafting": {
        "risk": ((_M, "crafting", "complexity"), (_M, "forging", "complexity")),
        "grind": ((_M, "crafting", "count"), (_M, "forging", "count"), (_M, "alchemy", "count")),
        "agency": ((_M, "crafting", "intricacy"), (_M, "forging", "intricacy")),
    },
}


def compile_galaxy_playable_axes(
    profile: Optional[Mapping[str, Any]], mode: str, operator_axes: Mapping[str, float],
) -> tuple[dict[str, float], Optional[dict[str, Any]]]:
    """Resolve supported native controls without changing the base world tensor.

    Explicit Forge controls, including zero, take priority. Other Galaxy
    intentions remain source metadata; no arbitrary source or feature
    implementation is inferred from a positive matrix value.
    """
    if mode not in _PLAYABLE_RULES:
        raise ValueError("unsupported Galaxy playable mode")
    axes = dict(operator_axes)
    if profile is None:
        return axes, None
    config = profile["config"]
    rules = {"tempo": ((_M, "parkour", "complexity"),), **_PLAYABLE_RULES[mode]}
    rows = []
    for axis, sources in sorted(rules.items()):
        votes = []
        for matrix, phase, dial in sources:
            value = config[matrix].get(phase, {}).get(dial, 0)
            if value > 0:
                votes.append({"path": f"{matrix}.{phase}.{dial}", "value": value})
        if not votes:
            continue
        requested = max(0.01, round(max(vote["value"] for vote in votes) / 1000, 2))
        overridden = axis in axes
        if not overridden:
            axes[axis] = requested
        rows.append({"axis": axis, "requested": requested, "effective": axes[axis],
                     "authority": "forge_override" if overridden else "galaxy_matrix",
                     "sources": votes})
    active = sum(1 for matrix in MATRIX_FIELDS for phase in config[matrix].values()
                 for value in phase.values() if value > 0)
    mapped = {vote["path"] for row in rows for vote in row["sources"]}
    return axes, {
        "schema": PLAYABLE_RECEIPT_SCHEMA,
        "mode": mode,
        "profile_sha256": galaxy_profile_receipt(profile)["sha256"],
        "active_matrix_dials": active,
        "mapped_matrix_dials": len(mapped),
        "unmapped_matrix_dials": active - len(mapped),
        "axes": rows,
        "effective_axes": dict(sorted(axes.items())),
    }


def seal_galaxy_playable_controls(
    files: Mapping[str, str], receipt: Mapping[str, Any],
    *, operator_axes: Optional[Mapping[str, float]] = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Bind exact native source, canonical profile and resolved authoring controls.

    Live compilation supplies the original operator axes. Independent archive
    inspection may reconstruct explicit overrides from the detached receipt;
    that verifies consistency, not an external author identity.
    """
    from skeleton.forge.archetype_content import verify_archetype_content
    from skeleton.forge.playable_tuning import SOURCE_PATH
    if receipt.get("schema") != PLAYABLE_RECEIPT_SCHEMA or receipt.get("mode") not in _PLAYABLE_RULES:
        raise ValueError("invalid Galaxy playable receipt")
    if any(name.casefold() == PLAYABLE_RECEIPT_PATH.casefold() for name in files):
        raise ValueError("Galaxy playable receipt path collision")
    mode = receipt["mode"]
    native_paths = (
        f"scenes/archetypes/{mode}/main.tscn",
        f"scripts/archetypes/{mode}/player_controller.gd",
        f"scripts/archetypes/{mode}/core_loop.gd",
    )
    if any(path not in files or type(files[path]) is not str for path in native_paths):
        raise ValueError("Galaxy playable generated source missing")
    raw = files.get(ARTIFACT_PATH)
    if (type(raw) is not str or len(raw) > _MAX_BYTES + 1
            or sum(name.casefold() == ARTIFACT_PATH.casefold() for name in files) != 1):
        raise ValueError("Galaxy playable profile source missing or ambiguous")
    try:
        profile = normalise_galaxy_profile(json.loads(raw))
        if profile is None or canonical_profile_bytes(profile).decode("ascii") + "\n" != raw:
            raise ValueError("noncanonical Galaxy profile source")
        if operator_axes is None:
            effective = receipt["effective_axes"]
            rows = receipt["axes"]
            if type(effective) is not dict or type(rows) is not list or len(rows) > 10:
                raise ValueError("invalid Galaxy control inventory")
            inherited = {row["axis"] for row in rows if row["authority"] == "galaxy_matrix"}
            operator_axes = {key: value for key, value in effective.items() if key not in inherited}
        resolved, expected = compile_galaxy_playable_axes(profile, mode, operator_axes)
        # Serialized comparison also rejects boolean/numeric equivalence,
        # duplicate/extra receipt fields and nonfinite numeric data.
        def canonical(value: Any) -> str:
            return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        if canonical(expected) != canonical(dict(receipt)):
            raise ValueError("Galaxy control receipt differs from canonical profile")
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError) as exc:
        raise ValueError("Galaxy playable profile or control receipt mismatch") from exc
    if not verify_archetype_content(files, mode, operator_axes=resolved):
        raise ValueError("Galaxy playable source does not match resolved controls")
    document = {**receipt, "native_sources": {
        path: hashlib.sha256(files[path].encode("utf-8", errors="strict")).hexdigest()
        for path in native_paths
    }, "source_verified": True, "native_execution_qualified": False}
    if SOURCE_PATH in files:
        document["tuning_receipt_sha256"] = hashlib.sha256(files[SOURCE_PATH].encode("utf-8")).hexdigest()
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    output = dict(files)
    output[PLAYABLE_RECEIPT_PATH] = encoded + "\n"
    return output, document
