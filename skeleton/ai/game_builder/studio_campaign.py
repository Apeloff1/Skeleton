"""Durable original game production across native targets, engines and media.

This is a synchronous operator-owned campaign journal, not an autonomous
training loop. It resumes only from exact current source and content receipts,
retains failures, and never marks a build as compiled/emulator-tested merely
because platform-specific source was successfully written.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile

from .contracts import canonical_digest
from .native_game_cli import _NATIVE, build_game
from .studio_asset_pipeline import ArtDirection, _palette
from .studio_sprite_authoring import import_artist_sprite_png
from .rights_evidence import read_rights_evidence
from .studio_campaign_lock import campaign_lock

SCHEMA = "skeleton.game_builder.studio_campaign.v1"
RECEIPT_SCHEMA = "skeleton.game_builder.studio_campaign_target.v1"
MAX_FILES = 128
MAX_BUNDLE_BYTES = 32 * 1024 * 1024


class StudioCampaignError(ValueError):
    """Campaign resume, provenance, budget, or ownership contract failed."""


@dataclass(frozen=True, slots=True)
class CampaignOrder:
    project_id: str
    title: str
    seed: int
    targets: tuple[str, ...]
    source_basis: str
    rights_document: str
    creative_identity: tuple[str, ...]
    width: int = 11
    height: int = 11
    levels: int = 2
    collectibles: int = 2
    hazards: int = 2
    health: int = 4
    theme: str = "forest"
    art: ArtDirection = ArtDirection()
    artist_png: str | None = None
    artist_sha256: str | None = None
    artist_quantization: str = "nearest"

    def __post_init__(self) -> None:
        if type(self.project_id) is not str or not self.project_id:
            raise StudioCampaignError("project identity required")
        if type(self.title) is not str or not 1 <= len(self.title) <= 120:
            raise StudioCampaignError("bounded original game title required")
        if (type(self.targets) is not tuple or not self.targets
                or len(self.targets) > len(_NATIVE) or len(set(self.targets)) != len(self.targets)
                or any(t not in _NATIVE for t in self.targets)):
            raise StudioCampaignError("target selection must be distinct registered native adapters")
        if not isinstance(self.art, ArtDirection):
            raise StudioCampaignError("original studio art controls required")
        if (type(self.creative_identity) is not tuple or not self.creative_identity
                or any(type(s) is not str for s in self.creative_identity)):
            raise StudioCampaignError("original authored identity statements required")
        if type(self.rights_document) is not str or not self.rights_document:
            raise StudioCampaignError("existing local documentary rights reference required")
        if (self.artist_png is None) != (self.artist_sha256 is None):
            raise StudioCampaignError("artist atlas and exact SHA must be supplied together")
        if self.artist_quantization not in {"nearest", "ordered4", "exact"}:
            raise StudioCampaignError("unsupported 2bpp artist palette conversion")

    def identity(self) -> str:
        documentary = read_rights_evidence(self.rights_document)
        if self.artist_png is not None:
            artwork_path = Path(self.artist_png)
            if (artwork_path.is_symlink() or not artwork_path.is_file()
                    or artwork_path.stat().st_size > 1024 * 1024):
                raise StudioCampaignError("original artist atlas must be a bounded real image")
            source = artwork_path.read_bytes()
            if sha256(source).hexdigest() != self.artist_sha256:
                raise StudioCampaignError("authored sprite PNG changed since campaign approval")
        return canonical_digest({
            "schema": SCHEMA,
            "project_id": self.project_id, "title": self.title,
            "seed": self.seed, "targets": list(self.targets),
            "source_basis": self.source_basis,
            "rights_sha256": documentary.document_sha256,
            "creative_identity": list(self.creative_identity),
            "world": [self.width, self.height, self.levels, self.collectibles,
                      self.hazards, self.health, self.theme],
            "artist_sha256": self.artist_sha256,
            "artist_quantization": self.artist_quantization,
            "art": {
                "style": self.art.style, "contrast": self.art.contrast,
                "seed": self.art.seed, "animation_frames": self.art.animation_frames,
                "outline": self.art.outline, "highlight": self.art.highlight,
                "foliage_density": self.art.foliage_density,
                "shadow_strength": self.art.shadow_strength,
                "parallax_layers": self.art.parallax_layers,
                "music_density": self.art.music_density,
                "animation_fps": self.art.animation_fps,
            },
        })


def _canonical(payload: dict) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def _atomic_json(path: Path, payload: dict) -> None:
    fd, candidate = tempfile.mkstemp(prefix=".campaign-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_canonical(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(candidate, path)
    finally:
        if os.path.exists(candidate):
            os.unlink(candidate)


def _load_json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 256_000:
        raise StudioCampaignError("campaign receipt missing or unsupported")
    try:
        payload = json.loads(path.read_bytes())
    except (ValueError, OSError, UnicodeError) as exc:
        raise StudioCampaignError("campaign receipt cannot be decoded") from exc
    if type(payload) is not dict:
        raise StudioCampaignError("campaign index must be an object")
    return payload


def _file_tree(root: Path) -> tuple[str, int, int]:
    if not root.is_dir() or root.is_symlink():
        raise StudioCampaignError("target artifact directory has changed")
    files = {}
    total = 0
    for location in sorted(root.rglob("*")):
        if location.is_symlink():
            raise StudioCampaignError("source artifact symlink not permitted")
        if not location.is_file():
            continue
        relative = location.relative_to(root).as_posix()
        if relative == "campaign_receipt.json":
            continue
        if len(files) >= MAX_FILES:
            raise StudioCampaignError("target artifact file count exceeds receipt budget")
        size = location.stat().st_size
        if size < 0 or size > MAX_BUNDLE_BYTES - total:
            raise StudioCampaignError("target artifact total byte budget exceeded")
        content = location.read_bytes()
        if len(content) != size:
            raise StudioCampaignError("source artifact changed during hashing")
        total += size
        files[relative] = sha256(content).hexdigest()
    if not files:
        raise StudioCampaignError("target source project is empty")
    return canonical_digest(files), len(files), total


def _verify_target(root: Path, expected_project: str, expected_target: str,
                   expected_campaign: str) -> dict:
    record = _load_json(root / "campaign_receipt.json")
    if record.get("schema") != RECEIPT_SCHEMA:
        raise StudioCampaignError("invalid source target receipt version")
    if (record.get("target") != expected_target or
            record.get("project_id") != expected_project or
            record.get("campaign_identity") != expected_campaign):
        raise StudioCampaignError("source target belongs to a different studio campaign")
    manifest = record.get("artifact")
    if type(manifest) is not dict or manifest.get("target") != expected_target:
        raise StudioCampaignError("source target provenance missing")
    tree, count, size = _file_tree(root)
    if (tree != record.get("tree_digest") or
            count != record.get("file_count") or size != record.get("bytes")):
        raise StudioCampaignError("built game changed after receipt commit")
    if canonical_digest({key: value for key, value in record.items()
                         if key != "receipt_digest"}) != record.get("receipt_digest"):
        raise StudioCampaignError("target receipt is not content-addressed")
    if not (root / "engines/index.html").is_file():
        raise StudioCampaignError("source target is missing browser engine")
    if not (root / "engines/godot/scripts/main.gd").is_file():
        raise StudioCampaignError("source target is missing Godot engine")
    if not (root / "assets/tiles/runtime.bin").is_file():
        raise StudioCampaignError("source target is missing genuine encoded sprite tiles")
    if record.get("native_binary_compiled") is not False:
        raise StudioCampaignError("source campaign cannot imply an executed console build")
    return record


def _reclaim_aborted_stages(root: Path) -> int:
    """Clear only orphaned owned temporary output while exclusive OS lock held.

    Never delete a published target, user source, symlink or unexpected
    directory. A crash releases the OS lock, enabling safe next-run cleanup.
    """
    staging = root / ".staging"
    if not staging.is_dir() or staging.is_symlink():
        raise StudioCampaignError("staging root is not a real controlled directory")
    cleaned = 0
    for entry in staging.iterdir():
        if entry.is_symlink() or not entry.is_dir() or not entry.name.startswith(".target-"):
            raise StudioCampaignError("unknown or linked leftover staging entry requires inspection")
        for child in entry.rglob("*"):
            if child.is_symlink():
                raise StudioCampaignError("aborted staging contains unsafe symlink")
        shutil.rmtree(entry)
        cleaned += 1
    return cleaned


def _index(root: Path, identity: str, order: CampaignOrder) -> dict:
    candidate = root / "index.json"
    if candidate.is_file():
        state = _load_json(candidate)
        if (state.get("schema") != SCHEMA or state.get("identity") != identity
                or state.get("targets") != list(order.targets)
                or type(state.get("completed")) is not dict
                or type(state.get("failed")) is not dict):
            raise StudioCampaignError("campaign index diverges from original production order")
        return state
    return {"schema": SCHEMA, "identity": identity,
            "project_id": order.project_id, "targets": list(order.targets),
            "completed": {}, "failed": {}, "revision": 0}


def _inspect_campaign_unlocked(order: CampaignOrder, destination: str | Path) -> dict:
    """Read-only full integrity scan of existing checkpoints."""
    identity = order.identity()
    root = Path(destination)
    if not root.is_dir() or root.is_symlink():
        raise StudioCampaignError("campaign root not present")
    state = _index(root, identity, order)
    completed = []
    for target in order.targets:
        source = root / "targets" / target
        if source.exists() or source.is_symlink():
            proof = _verify_target(source, order.project_id, target, identity)
            if state["completed"].get(target) != proof["receipt_digest"]:
                raise StudioCampaignError("published source checkpoint missing from journal")
            completed.append(target)
        elif target in state["completed"]:
            raise StudioCampaignError("checkpointed source output disappeared")
    return {
        "schema": SCHEMA, "identity": identity,
        "targets_requested": len(order.targets),
        "targets_with_verified_source": len(completed),
        "completed_targets": completed,
        "pending_targets": [t for t in order.targets if t not in completed],
        "failures": state["failed"],
        "aborted_owned_stages_recovered": int(state.get("aborted_owned_stages_recovered", 0)),
        "native_roms_compiled": 0,
        "native_emulator_playthroughs_verified": 0,
        "source_completion_percent": round(100 * len(completed) / len(order.targets), 2),
        "qualification_percent": 0,
    }


def _run_campaign_unlocked(order: CampaignOrder, destination: str | Path, *,
                 authorized: bool, max_targets: int | None = None) -> dict:
    """Run/resume ordered source targets; never overwrite or claim compiled ROMs.

    Even after an abrupt stop, targets carry their own receipts. A second
    invocation can recover a published target missing only its index entry.
    """
    if type(authorized) is not bool or not authorized:
        raise PermissionError("campaign authoring requires explicit local operator authority")
    if not isinstance(order, CampaignOrder):
        raise StudioCampaignError("typed original game campaign order required")
    if max_targets is not None and (type(max_targets) is not int or max_targets < 1):
        raise StudioCampaignError("max_targets must be a positive per-invocation throttle")
    identity = order.identity()
    root = Path(destination)
    if root.is_symlink():
        raise StudioCampaignError("campaign may not use a symlink destination")
    if not root.exists():
        if not root.parent.is_dir() or root.parent.is_symlink():
            raise StudioCampaignError("campaign parent directory must already exist")
        root.mkdir()
    if not root.is_dir() or root.is_symlink():
        raise StudioCampaignError("campaign output is not a contained directory")
    (root / "targets").mkdir(exist_ok=True)
    (root / ".staging").mkdir(exist_ok=True)
    if (root / "targets").is_symlink() or (root / ".staging").is_symlink():
        raise StudioCampaignError("campaign staging and target roots cannot be links")
    state = _index(root, identity, order)
    previously_recovered = state.get("aborted_owned_stages_recovered", 0)
    if type(previously_recovered) is not int or previously_recovered < 0:
        raise StudioCampaignError("invalid prior production recovery counter")
    recovered = _reclaim_aborted_stages(root)
    state["aborted_owned_stages_recovered"] = previously_recovered + recovered
    # Require valid source receipts before trusting an indexed completion.
    for target in order.targets:
        source = root / "targets" / target
        if source.exists() or source.is_symlink():
            proof = _verify_target(source, order.project_id, target, identity)
            if target in state["completed"] and state["completed"][target] != proof["receipt_digest"]:
                raise StudioCampaignError("target content differs from checkpoint")
            state["completed"][target] = proof["receipt_digest"]
    state["revision"] += 1
    _atomic_json(root / "index.json", state)
    artist_atlas = None
    if order.artist_png is not None:
        artist_atlas = import_artist_sprite_png(
            Path(order.artist_png).read_bytes(),
            expected_sha256=order.artist_sha256,
            palette=_palette(order.theme, order.art.contrast),
            quantization=order.artist_quantization, authorized=True,
        )
    attempts = 0
    for target in order.targets:
        if target in state["completed"]:
            continue
        if max_targets is not None and attempts >= max_targets:
            break
        attempts += 1
        stage = Path(tempfile.mkdtemp(prefix=".target-", dir=root / ".staging"))
        try:
            built = build_game(
                target=target, basis=order.source_basis,
                project_id=order.project_id, title=order.title,
                seed=order.seed, width=order.width, height=order.height,
                levels=order.levels, collectibles=order.collectibles,
                hazards=order.hazards, health=order.health,
                rights_evidence=order.rights_document,
                creative_identity=order.creative_identity,
                output=stage / "game", authorized=True,
                studio_art=order.art, theme=order.theme,
                artist_atlas=artist_atlas,
            )
            if (built["world_digest"] != built["engine_sources"]["world_digest"]
                    or built["native_binary_built"] is not False
                    or built["emulator_verified"] is not False):
                raise StudioCampaignError("target production results disagree with actual source")
            source_root = stage / "game"
            tree, count, size = _file_tree(source_root)
            receipt_body = {
                "schema": RECEIPT_SCHEMA,
                "campaign_identity": identity,
                "project_id": order.project_id,
                "target": target,
                "artifact": {
                    "target": target,
                    "world_digest": built["world_digest"],
                    "source_content_digest": built["source_content_digest"],
                    "art_pack_digest": built["studio_assets"]["pack_digest"],
                    "engine_manifest_digest": built["engine_sources"]["manifest_digest"],
                    "reference_replay_digest": built["winning_replay_digest"],
                },
                "tree_digest": tree, "file_count": count, "bytes": size,
                "native_binary_compiled": False,
                "emulator_qualified": False,
                "publication_approved": False,
            }
            proof = {**receipt_body, "receipt_digest": canonical_digest(receipt_body)}
            with (source_root / "campaign_receipt.json").open("xb") as stream:
                stream.write(_canonical(proof))
            published = root / "targets" / target
            if published.exists() or published.is_symlink():
                raise StudioCampaignError("target appeared concurrently during generation")
            os.rename(source_root, published)
            state["completed"][target] = proof["receipt_digest"]
            state["failed"].pop(target, None)
        except (OSError, ValueError, PermissionError, RuntimeError) as exc:
            # Do not silently mark a partially written game as successful.
            state["failed"][target] = type(exc).__name__ + ": " + str(exc)[:220]
        finally:
            shutil.rmtree(stage, ignore_errors=True)
            state["revision"] += 1
            _atomic_json(root / "index.json", state)
    return _inspect_campaign_unlocked(order, root)


def inspect_campaign(order: CampaignOrder, destination: str | Path) -> dict:
    """Read only a stable source checkpoint under the shared campaign lock."""
    with campaign_lock(destination):
        return _inspect_campaign_unlocked(order, destination)


def run_campaign(order: CampaignOrder, destination: str | Path, *,
                 authorized: bool, max_targets: int | None = None) -> dict:
    """Serialize the complete resume/build/checkpoint transaction."""
    if authorized is not True:
        raise PermissionError("campaign authoring requires explicit local operator authority")
    with campaign_lock(destination):
        return _run_campaign_unlocked(
            order, destination, authorized=True, max_targets=max_targets,
        )


__all__ = [
    "CampaignOrder", "StudioCampaignError", "run_campaign", "inspect_campaign",
]
