"""Original-world Studio to deterministic engine asset/temporal handoff.

Requires the reviewed seven-plane playable source plus reviewed original
asset briefs and the canonical temporal graph. No generated engine binaries.
"""
from __future__ import annotations

from hashlib import sha256
import os
from typing import Any

from .asset_briefs import compile_assets, validate_briefs
from .bundle import _artifact_read
from .chapters import engine_handoff as chapters_handoff, scene_index, validate_chapters
from .cinematics import engine_handoff as cinematics_handoff, validate_cinematics
from .weather import engine_handoff as weather_handoff, validate_weather
from .studio_assembly import StudioAssemblyStore, compile_studio_assembly
from .timeline import compile_timeline, validate_timeline
from .world_canon import CanonError, WorldStore, _id, canonical, digest, strict_json

SCHEMA = "jeeves.world.studio_engine_handoff.v1"
RECEIPT_SCHEMA = "jeeves.world.studio_engine_receipt.v1"
SOURCE_NAMES = ("world", "cast", "testimony", "rumors", "localization",
                "accessibility", "pacing", "assets", "timeline")


def compile_studio_engine(sources: tuple[Any, ...], era: str,
                          optional: dict[str, Any] | None = None) -> dict[str, Any]:
    if type(sources) is not tuple or len(sources) != 9:
        raise CanonError("studio_engine_invalid_sources")
    (world, cast, testimony, rumors, localization,
     accessibility, pacing, assets, timeline) = sources
    studio = compile_studio_assembly(
        world, cast, testimony, rumors, localization, accessibility, pacing)
    validate_briefs(assets, world)
    validate_timeline(timeline, world)
    engine_assets = compile_assets(assets, world, era)
    temporal = compile_timeline(timeline, world)
    scenes = {item["id"]: item for item in world["scenes"]}
    accessibility_by_scene = {item["id"]: item for item in accessibility["scenes"]}
    pacing_by_scene = {item["scene"]: item for item in pacing["beats"]}
    localized_scenes = {
        item["tag"]: {scene["id"]: scene for scene in item["scenes"]}
        for item in localization["locales"]
    }
    localized_choices = {
        item["tag"]: {choice["id"]: choice["label"] for choice in item["choices"]}
        for item in localization["locales"]
    }
    localized_endings = {
        item["tag"]: {ending["scene"]: ending["label"] for ending in item["endings"]}
        for item in localization["locales"]
    }
    accessible_actions = {item["id"]: item["action"] for item in accessibility["choices"]}
    accessible_endings = {item["scene"]: item["summary"] for item in accessibility["endings"]}
    scene_nodes = [{
        "id": sid, "title": scenes[sid]["title"],
        "narrative": scenes[sid]["narrative"],
        "accessibility": accessibility_by_scene[sid],
        "pacing": pacing_by_scene[sid],
        "locales": {tag: localized_scenes[tag][sid] for tag in sorted(localized_scenes)},
    } for sid in sorted(scenes)]
    choice_edges = [{
        **choice, "accessible_action": accessible_actions[choice["id"]],
        "locales": {tag: localized_choices[tag][choice["id"]]
                    for tag in sorted(localized_choices)},
    } for choice in sorted(world["choices"], key=lambda item: item["id"])]
    ending_nodes = [{
        **ending, "accessible_summary": accessible_endings[ending["scene"]],
        "locales": {tag: localized_endings[tag][ending["scene"]]
                    for tag in sorted(localized_endings)},
    } for ending in sorted(world["endings"], key=lambda item: item["scene"])]
    source_digests = {**studio["source_digests"],
                      "assets": digest(assets), "timeline": digest(timeline)}
    optional = optional or {}
    if set(optional) - {"chapters", "cinematics", "weather"}:
        raise CanonError("studio_engine_unknown_optional_source")
    optional_handoffs: dict[str, Any] = {}
    if "chapters" in optional:
        source = validate_chapters(optional["chapters"], world)
        optional_handoffs["chapters"] = chapters_handoff(source, world)
        source_digests["chapters"] = digest(source)
        index = scene_index(source)
        for node in scene_nodes:
            node["chapter"] = index[node["id"]]
    if "cinematics" in optional:
        source = validate_cinematics(optional["cinematics"], world)
        optional_handoffs["cinematics"] = cinematics_handoff(source, world)
        source_digests["cinematics"] = digest(source)
        sequences = {item["scene"]: item["beats"] for item in source["sequences"]}
        for node in scene_nodes:
            node["cinematic_beats"] = sequences.get(node["id"], [])
    if "weather" in optional:
        weather_source = validate_weather(optional["weather"], world)
        optional_handoffs["weather"] = weather_handoff(weather_source, world)
        source_digests["weather"] = digest(weather_source)
        conditions = {item["scene"]: item for item in weather_source["scenes"]}
        for node in scene_nodes:
            node["weather"] = conditions[node["id"]]
    manifest = {
        "schema": SCHEMA, "world_id": world["id"], "engine_era": era,
        "source_digests": source_digests,
        "studio_proof_digests": studio["proof_digests"],
        "scene_nodes": scene_nodes, "choice_edges": choice_edges,
        "ending_nodes": ending_nodes,
        "characters": cast["characters"], "dialogue": cast["lines"],
        "testimony": testimony["statements"],
        "rumor_sources": rumors["rumors"], "rumor_routes": rumors["routes"],
        "engine_assets": engine_assets, "temporal_events": temporal,
        "qualification": "reviewed_engine_recipe_not_built_or_device_certified",
    }
    if optional_handoffs:
        manifest["optional_handoffs"] = optional_handoffs
    return manifest


class StudioEngineStore:
    """Read all nine sources under one world lock, publish manifest then receipt."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)
        self.studio = StudioAssemblyStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str]:
        _id(world_id, "world_id")
        return (world_id + ".studio.engine.manifest.json",
                world_id + ".studio.engine.receipt.json")

    def _sources(self, fd: int, world_id: str) -> tuple[Any, ...]:
        sources = self.studio._sources(fd, world_id)
        world = sources[0]
        assets = strict_json(self.worlds._read(fd, world_id + ".assets.json"))
        timeline = strict_json(self.worlds._read(fd, world_id + ".timeline.json"))
        validate_briefs(assets, world)
        validate_timeline(timeline, world)
        return (*sources, assets, timeline)

    def _optional_sources(self, fd: int, world_id: str,
                          world: Any) -> dict[str, Any]:
        """Read optional approved authoring planes under the SAME world lease."""
        result: dict[str, Any] = {}
        for name, validate in (("chapters", validate_chapters),
                               ("cinematics", validate_cinematics),
                               ("weather", validate_weather)):
            try:
                source = strict_json(self.worlds._read(
                    fd, world_id + "." + name + ".json"))
            except CanonError as exc:
                if exc.code == "not_found":
                    continue
                raise
            validate(source, world)
            if not source["approved"]:
                raise CanonError("studio_engine_optional_review_required", name)
            result[name] = source
        return result

    def _outputs(self, sources: tuple[Any, ...], era: str,
                 optional: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
        manifest = compile_studio_engine(sources, era, optional)
        content = canonical(manifest)
        if len(content) > 1572864:
            raise CanonError("studio_engine_manifest_too_large")
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": sources[0]["id"],
            "engine_era": era, "source_digests": manifest["source_digests"],
            "studio_proof_digests": manifest["studio_proof_digests"],
            "manifest_file": self._names(sources[0]["id"])[0],
            "manifest_sha256": sha256(content).hexdigest(),
            "qualification": "source_verified_engine_recipe_not_release_certified",
        }
        return receipt, content

    def _inspect_snapshot(self, fd: int, world_id: str, era: str) -> dict[str, Any]:
        """Preview the engine recipe under the caller's existing world lease."""
        sources = self._sources(fd, world_id)
        optional = self._optional_sources(fd, world_id, sources[0])
        manifest = compile_studio_engine(sources, era, optional)
        return {"schema": SCHEMA, "world_id": world_id,
                "engine_era": era, "source_digests": manifest["source_digests"],
                "studio_proof_digests": manifest["studio_proof_digests"],
                "scene_count": len(manifest["scene_nodes"]),
                "choice_count": len(manifest["choice_edges"]),
                "ending_count": len(manifest["ending_nodes"]),
                "optional_planes": sorted(optional),
                "qualification": manifest["qualification"]}

    def inspect(self, world_id: str, era: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self.studio._locked(fd, world_id)
            try:
                return self._inspect_snapshot(fd, world_id, era)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def compile(self, world_id: str, expected_digests: Any, era: str) -> dict[str, Any]:
        if (type(expected_digests) is not dict or
                not set(SOURCE_NAMES) <= set(expected_digests) or
                set(expected_digests) - set(SOURCE_NAMES) - {"chapters", "cinematics", "weather"}):
            raise CanonError("studio_engine_invalid_lease")
        fd = self.worlds._directory()
        try:
            self.studio._locked(fd, world_id)
            try:
                sources = self._sources(fd, world_id)
                optional = self._optional_sources(fd, world_id, sources[0])
                receipt, content = self._outputs(sources, era, optional)
                if receipt["source_digests"] != expected_digests:
                    raise CanonError("studio_engine_stale_source")
                names = self._names(world_id)
                self.worlds._write(fd, names[0], content)
                self.worlds._write(fd, names[1], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _verify_snapshot(self, fd: int, world_id: str) -> dict[str, Any]:
        """Validate the engine owner receipt under an already-held world lease.

        This is the same verifier used by standalone Studio Engine and by
        Jeeves laptop acceptance. The caller must own the exclusive world
        lease; do not re-enter the non-reentrant lock here.
        """
        names = self._names(world_id)
        recorded = strict_json(self.worlds._read(fd, names[1]))
        if type(recorded) is not dict or recorded.get("schema") != RECEIPT_SCHEMA:
            raise CanonError("studio_engine_receipt_invalid")
        era = recorded.get("engine_era")
        if type(era) is not str or len(era) > 128:
            raise CanonError("studio_engine_era_invalid")
        sources = self._sources(fd, world_id)
        optional = self._optional_sources(fd, world_id, sources[0])
        receipt, content = self._outputs(sources, era, optional)
        if recorded != receipt:
            raise CanonError("studio_engine_receipt_mismatch")
        if _artifact_read(fd, names[0]) != content:
            raise CanonError("studio_engine_manifest_mismatch")
        return receipt

    def verify(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self.studio._locked(fd, world_id)
            try:
                return self._verify_snapshot(fd, world_id)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
