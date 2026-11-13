"""Original region atlas with source-leased scene placement and travel proof.

A region crossing is legal only when its exact authored world choice is
represented by one reviewed passage. This is an authoring overlay, not an
unreviewed rewrite of canonical world transitions.
"""
from __future__ import annotations

from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text,
    canonical, compile_html, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.atlas.v1"
REPORT_SCHEMA = "jeeves.world.atlas_report.v1"
RECEIPT_SCHEMA = "jeeves.world.atlas_receipt.v1"
MAX_REGIONS = 64
MAX_PASSAGES = 512
MAX_ATLAS_BYTES = 524288
MAX_PLAYABLE_BYTES = 1572864


def propose_atlas(world: Any, prompt: str) -> dict[str, Any]:
    """Create a conservative single-region proposal from the user's own prompt."""
    proof = prove(world)
    _text(prompt, "prompt", 4096)
    atlas = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": proof.source_digest, "prompt": prompt,
        "regions": [{
            "id": "origin", "name": world["region"],
            "description": prompt,
        }],
        "placements": [
            {"scene": item["id"], "region": "origin"}
            for item in sorted(world["scenes"], key=lambda s: s["id"])
        ],
        "passages": [], "approved": False,
        "review_note": "Awaiting explicit atlas review.",
    }
    return validate_atlas(atlas, world)


def validate_atlas(atlas: Any, world: Any) -> dict[str, Any]:
    proof = prove(world)
    obj = _keys(atlas, {
        "schema", "world_id", "world_digest", "prompt", "regions",
        "placements", "passages", "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("atlas_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != proof.source_digest:
        raise CanonError("atlas_source_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("atlas_invalid_approval")
    regions = _list(obj["regions"], "regions", MAX_REGIONS)
    if not regions:
        raise CanonError("atlas_empty_regions")
    region_ids: set[str] = set()
    for region in regions:
        _keys(region, {"id", "name", "description"})
        rid = _id(region["id"], "region.id")
        if rid in region_ids:
            raise CanonError("atlas_duplicate_region", rid)
        region_ids.add(rid)
        _text(region["name"], "region.name")
        _text(region["description"], "region.description", 4096)
    if [item["id"] for item in regions] != sorted(region_ids):
        raise CanonError("atlas_regions_not_sorted")
    placements = _list(obj["placements"], "placements", 128)
    location: dict[str, str] = {}
    for placement in placements:
        _keys(placement, {"scene", "region"})
        scene = _id(placement["scene"], "placement.scene")
        region = _id(placement["region"], "placement.region")
        if scene in location:
            raise CanonError("atlas_duplicate_placement", scene)
        if region not in region_ids:
            raise CanonError("atlas_unknown_region", region)
        location[scene] = region
    expected_scenes = {item["id"] for item in world["scenes"]}
    if set(location) != expected_scenes:
        raise CanonError("atlas_incomplete_placements")
    if [item["scene"] for item in placements] != sorted(location):
        raise CanonError("atlas_placements_not_sorted")
    choices = {item["id"]: item for item in world["choices"]}
    passages = _list(obj["passages"], "passages", MAX_PASSAGES)
    represented: dict[str, str] = {}
    ids: set[str] = set()
    for passage in passages:
        _keys(passage, {"id", "choice", "from_region", "to_region", "description"})
        pid = _id(passage["id"], "passage.id")
        cid = _id(passage["choice"], "passage.choice")
        src = _id(passage["from_region"], "passage.from_region")
        dst = _id(passage["to_region"], "passage.to_region")
        _text(passage["description"], "passage.description", 1024)
        if pid in ids or cid in represented:
            raise CanonError("atlas_duplicate_passage", cid)
        ids.add(pid)
        represented[cid] = pid
        choice = choices.get(cid)
        if choice is None:
            raise CanonError("atlas_unknown_choice", cid)
        if src == dst or src != location[choice["from"]] or dst != location[choice["to"]]:
            raise CanonError("atlas_passage_placement_mismatch", cid)
    if [item["id"] for item in passages] != sorted(ids):
        raise CanonError("atlas_passages_not_sorted")
    crossing = {
        cid for cid, choice in choices.items()
        if location[choice["from"]] != location[choice["to"]]
    }
    if set(represented) != crossing:
        raise CanonError("atlas_crossing_coverage_mismatch")
    if len(canonical(obj)) > MAX_ATLAS_BYTES:
        raise CanonError("atlas_too_large")
    return obj


def review_atlas(atlas: Any, world: Any, note: str) -> dict[str, Any]:
    validate_atlas(atlas, world)
    _text(note, "review_note", 512)
    candidate = strict_json(canonical(atlas))
    candidate["approved"] = True
    candidate["review_note"] = note
    return validate_atlas(candidate, world)


def atlas_report(atlas: Any, world: Any) -> dict[str, Any]:
    validate_atlas(atlas, world)
    proof = prove(world)
    location = {p["scene"]: p["region"] for p in atlas["placements"]}
    passages = {p["choice"]: p for p in atlas["passages"]}
    choices = {c["id"]: c for c in world["choices"]}
    itineraries: dict[str, list[dict[str, str]]] = {}
    for ending, witness in sorted(proof.ending_witnesses.items()):
        current = world["start"]
        travel: list[dict[str, str]] = []
        for cid in witness:
            choice = choices[cid]
            if choice["from"] != current:
                raise CanonError("atlas_invalid_witness")
            if cid in passages:
                p = passages[cid]
                travel.append({
                    "choice": cid, "passage": p["id"],
                    "from_region": location[current],
                    "to_region": location[choice["to"]],
                })
            current = choice["to"]
        if current != ending:
            raise CanonError("atlas_invalid_witness")
        itineraries[ending] = travel
    counts = {
        region["id"]: sum(p["region"] == region["id"] for p in atlas["placements"])
        for region in atlas["regions"]
    }
    return {
        "schema": REPORT_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "atlas_digest": digest(atlas),
        "approved": atlas["approved"], "scene_counts": counts,
        "passage_count": len(passages), "ending_itineraries": itineraries,
        "witnessed_endings": sorted(itineraries),
        "qualification": "source_placement_proof_only_not_device_certified",
    }


def render_playable(atlas: Any, world: Any) -> bytes:
    if not atlas["approved"]:
        raise CanonError("atlas_review_required")
    report = atlas_report(atlas, world)
    sections = [
        '<section id="atlas" aria-labelledby="atlas-heading">',
        '<h2 id="atlas-heading">Original region atlas</h2>',
        '<p>World source: ', html.escape(report["world_digest"]),
        '</p><ul>',
    ]
    for region in atlas["regions"]:
        sections.extend([
            "<li><h3>", html.escape(region["name"], quote=True),
            "</h3><p>", html.escape(region["description"], quote=True),
            "</p><p>Scenes: ", str(report["scene_counts"][region["id"]]),
            "</p></li>",
        ])
    sections.append("</ul><h3>Reviewed passages</h3><ol>")
    for passage in atlas["passages"]:
        sections.extend([
            "<li>", html.escape(passage["description"], quote=True),
            " (choice ", html.escape(passage["choice"], quote=True),
            ")</li>",
        ])
    sections.append("</ol></section>")
    original = compile_html(world)
    if original.count("</body>") != 1:
        raise CanonError("atlas_player_template_mismatch")
    playable = original.replace("</body>", "".join(sections) + "</body>").encode("utf-8")
    if len(playable) > MAX_PLAYABLE_BYTES:
        raise CanonError("atlas_playable_too_large")
    return playable


class AtlasStore:
    """World-serialized, descriptor-anchored optimistic atlas publication."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (
            world_id + ".atlas.json",
            world_id + ".atlas.playable.html",
            world_id + ".atlas.receipt.json",
        )

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        try:
            handle = os.open(
                world_id + ".lock",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=fd,
            )
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("atlas_world_identity_mismatch")
        return world

    def _atlas(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        atlas = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
        return validate_atlas(atlas, world)

    def propose(self, world_id: str, prompt: str) -> dict[str, Any]:
        return propose_atlas(self.worlds.read(world_id), prompt)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            atlas = self._atlas(fd, world_id, world)
            return {"atlas": atlas, "report": atlas_report(atlas, world)}
        finally:
            os.close(fd)

    def save(self, world_id: str, atlas: Any, *, expected_world_digest: str,
             expected_atlas_digest: str | None = None, create: bool = False) -> str:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                if digest(world) != expected_world_digest:
                    raise CanonError("atlas_stale_world")
                validate_atlas(atlas, world)
                if atlas["approved"]:
                    raise CanonError("atlas_approval_requires_review")
                try:
                    existing = self._atlas(fd, world_id, world)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    existing = None
                if create:
                    if existing is not None or expected_atlas_digest is not None:
                        raise CanonError("atlas_already_exists")
                elif existing is None or digest(existing) != expected_atlas_digest:
                    raise CanonError("atlas_stale_edit")
                self.worlds._write(fd, self._names(world_id)[0], canonical(atlas))
                return digest(atlas)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def approve(self, world_id: str, *, expected_atlas_digest: str,
                review_note: str) -> str:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                atlas = self._atlas(fd, world_id, world)
                if digest(atlas) != expected_atlas_digest:
                    raise CanonError("atlas_stale_edit")
                approved = review_atlas(atlas, world, review_note)
                self.worlds._write(fd, self._names(world_id)[0], canonical(approved))
                return digest(approved)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, world: Any, atlas: Any) -> tuple[dict[str, Any], bytes]:
        report = atlas_report(atlas, world)
        playable = render_playable(atlas, world)
        names = self._names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "atlas_digest": digest(atlas),
            "report": report,
            "artifacts": {names[1]: sha256(playable).hexdigest()},
            "qualification": "reviewed_source_handoff_not_release_certified",
        }
        if len(canonical(receipt)) > MAX_ATLAS_BYTES:
            raise CanonError("atlas_receipt_too_large")
        return receipt, playable

    def editor(self, world_id: str, *, expected_atlas_digest: str) -> dict[str, str]:
        """Publish a CSP-bound offline editor for the current unapproved source."""
        from .atlas_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                atlas = self._atlas(fd, world_id, world)
                if digest(atlas) != expected_atlas_digest:
                    raise CanonError("atlas_stale_edit")
                output = render_editor(atlas, world)
                name = world_id + ".atlas.editor.html"
                self.worlds._write(fd, name, output)
                return {"html_file": name, "html_sha256": sha256(output).hexdigest(),
                        "atlas_digest": digest(atlas)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def compile(self, world_id: str, *, expected_atlas_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                atlas = self._atlas(fd, world_id, world)
                if digest(atlas) != expected_atlas_digest:
                    raise CanonError("atlas_stale_edit")
                receipt, playable = self._outputs(world, atlas)
                names = self._names(world_id)
                self.worlds._write(fd, names[1], playable)
                self.worlds._write(fd, names[2], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                atlas = self._atlas(fd, world_id, world)
                receipt, playable = self._outputs(world, atlas)
                names = self._names(world_id)
                stored = strict_json(self.worlds._read(fd, names[2]))
                if stored != receipt:
                    raise CanonError("atlas_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable:
                    raise CanonError("atlas_playable_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
