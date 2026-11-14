"""skeleton/gameforge/serving.py

One product path for GameForge: the 7-step conductor feeds the live
ten-stage ``GameForgeRun``.

    vision -> snowball -> prototype -> mass_forge -> world -> cockpit -> export
        |  (receipt-chained conductor manifest, fail-closed)
        v
    ingest -> detect -> tensor -> lattice -> oracle -> forge -> jeeves -> sim
        -> emit (Godot project + playable slice + conductor manifest file) -> seal

The conductor's verified manifest is passed into ``GameForgeRun.execute`` as
``conductor_manifest``. The ingest stage commits its digest to the cockpit
ledger and the emit stage writes it into the project as
``design/gameforge_conductor_manifest.json``, so the Godot source manifest
and ledger both bind the exact 7-step plan that produced them.

``GameForgeRun`` is wrapped, never replaced. A failed conductor step halts
before any Godot emission. A failed ten-stage run is reported as not ok.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional

from .conductor import ConductorConfig, GameForgeConductor
from .errors import GameForgeError, InputError
from .manifest import canonical_json, digest, verify_manifest
from .plans import VisionRequest

SCHEMA = "skeleton.gameforge.conduct.v1"
MANIFEST_PATH = "design/gameforge_conductor_manifest.json"

# Conductor genre -> preferred authored playable mode. A mode that the
# installed library does not provide falls back to ``extraction`` and the
# receipt says so; nothing pretends a genre engine exists.
GENRE_PLAYABLE: Dict[str, str] = {
    "puzzle": "puzzle",
    "racing": "racing",
    "shooter": "combat_loop",
    "rpg": "combat_loop",
    "strategy": "pipeline",
    "sandbox": "crafting",
    "adventure": "extraction",
    "platformer": "extraction",
}


def conductor_manifest_source(manifest: Mapping[str, Any]) -> str:
    """Canonical, inert project artifact for a verified conductor manifest."""
    verify_manifest(manifest)
    return canonical_json(dict(manifest)) + "\n"


def admit_conductor_manifest(raw: Any) -> Dict[str, Any]:
    """Fail closed unless ``raw`` is a self-consistent conductor manifest."""
    if not isinstance(raw, Mapping):
        raise ValueError("conductor manifest must be a mapping")
    data = json.loads(canonical_json(dict(raw)))
    try:
        verify_manifest(data)
    except GameForgeError as exc:
        raise ValueError(f"conductor manifest rejected: {exc}") from None
    if tuple(data.get("steps") or ()) != tuple(GameForgeConductor.STEPS):
        raise ValueError("conductor manifest must cover all seven steps")
    return data


def _playable_mode(genre: str) -> tuple[str, bool]:
    from skeleton.forge.archetype_content import content_archetypes
    preferred = GENRE_PLAYABLE.get(genre, "extraction")
    available = content_archetypes()
    if preferred in available:
        return preferred, False
    return "extraction", True


def _vision_text(plan: Any) -> str:
    pillars = ", ".join(plan.pillars)
    return f"{plan.title}: {plan.pitch} ({plan.genre}; pillars: {pillars})"[:4000]


def conduct(
    request: Mapping[str, Any] | VisionRequest,
    *,
    conductor_era: Optional[str] = None,
    forge_era: Optional[str] = None,
    playable_content: bool = True,
    operator_axes: Optional[Mapping[str, float]] = None,
    project_root: Optional[str] = None,
    overwrite: bool = False,
    playtest: Optional[str] = None,
    budget_bytes: int = 1_000_000,
    runner_factory: Optional[Callable[[], Any]] = None,
) -> Dict[str, Any]:
    """Run the 7-step conductor, then the live ten-stage forge, as one product.

    Returns a JSON-safe envelope. ``ok`` is true only when all seven conductor
    steps completed, the manifest verified, the ten-stage run succeeded and
    the emitted project carries the exact conductor manifest file.
    """
    if type(playable_content) is not bool or type(overwrite) is not bool:
        raise ValueError("playable_content and overwrite must be booleans")
    conductor = GameForgeConductor(config=ConductorConfig(
        budget_bytes=budget_bytes, target="desktop",
    ))
    result = conductor.run(request, era_key=conductor_era)
    envelope: Dict[str, Any] = {
        "schema": SCHEMA,
        "ok": False,
        "conductor": result.to_dict(),
        "forge": None,
    }
    if not result.ok or result.manifest is None:
        envelope["halted_at"] = (result.error.step if result.error else None) or (
            GameForgeConductor.STEPS[len(result.completed)]
            if len(result.completed) < len(GameForgeConductor.STEPS) else None
        )
        return envelope
    manifest = admit_conductor_manifest(result.manifest.to_dict())
    vision_plan = result.plans["vision"]
    mode, fallback = _playable_mode(vision_plan.genre)
    if runner_factory is None:
        from skeleton.context.pipeline import GameForgeRun
        runner_factory = GameForgeRun
    runner = runner_factory()
    payload = runner.execute(
        _vision_text(vision_plan),
        era=forge_era,
        archetype=mode if playable_content else None,
        target="godot",
        project_root=project_root,
        overwrite=overwrite,
        playtest=playtest,
        operator_axes=operator_axes,
        playable_content=playable_content,
        conductor_manifest=manifest,
    )
    files = payload.get("files") or {}
    expected = conductor_manifest_source(manifest)
    bound = files.get(MANIFEST_PATH) == expected
    source_manifest = payload.get("source_manifest") or {}
    sealed_digest = (source_manifest.get("files") or {}).get(MANIFEST_PATH)
    envelope.update({
        "ok": bool(payload.get("succeeded")) and bound and sealed_digest is not None,
        "conductor_manifest_digest": manifest["manifest_digest"],
        "conductor_manifest_path": MANIFEST_PATH,
        "conductor_manifest_bound": bound,
        "conductor_manifest_file_sha256": sealed_digest,
        "playable": {
            "requested": playable_content,
            "mode": (payload.get("forge") or {}).get("playable_archetype"),
            "preferred_mode": GENRE_PLAYABLE.get(vision_plan.genre, "extraction"),
            "fallback": fallback if playable_content else None,
        },
        "forge": {
            key: payload.get(key)
            for key in ("run", "succeeded", "era", "mass", "complete", "forge", "source_manifest",
                        "project", "playtest", "playable_portal", "playable_mechanics",
                        "playable_scene_playtest", "conductor")
            if key in payload
        },
        "ledger": payload.get("ledger"),
        "files": files,
    })
    return envelope


def public_envelope(envelope: Mapping[str, Any], *, include_files: bool = False) -> Dict[str, Any]:
    out = dict(envelope)
    files = out.pop("files", None) or {}
    out["file_names"] = sorted(files)
    if include_files:
        out["files"] = files
    return out


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m skeleton gameforge-conduct",
        description="GameForge 7-step conductor -> ten-stage forge -> Godot project",
    )
    p.add_argument("--title", required=True)
    p.add_argument("--pitch", required=True)
    p.add_argument("--genre", required=True)
    p.add_argument("--pillar", action="append", default=[], dest="pillars")
    p.add_argument("--minutes", type=int, default=10)
    p.add_argument("--era", default=None, help="conductor style era (e.g. HOUSE_ERA, PIXEL_8BIT)")
    p.add_argument("--forge-era", default=None, help="forge design era (default: detected)")
    p.add_argument("--no-playable", action="store_true")
    p.add_argument("--out", default=None)
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--playtest", choices=("off", "auto", "require"), default=None)
    p.add_argument("--json", action="store_true")
    return p


def cli(argv: List[str], *, runner_factory: Optional[Callable[[], Any]] = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    request = {
        "title": args.title, "pitch": args.pitch, "genre": args.genre,
        "pillars": args.pillars, "target_minutes": args.minutes,
        **({"era": args.era} if args.era else {}),
    }
    if runner_factory is None:
        from skeleton.context.pipeline import GameForgeRun
        runner_factory = GameForgeRun.live  # same live forge as ``python -m skeleton run``
    try:
        envelope = conduct(
            request, conductor_era=args.era, forge_era=args.forge_era,
            playable_content=not args.no_playable, project_root=args.out,
            overwrite=args.overwrite, playtest=args.playtest,
            runner_factory=runner_factory,
        )
    except (ValueError, InputError) as exc:
        print(f"gameforge-conduct: {exc}", file=sys.stderr)
        return 2
    public = public_envelope(envelope)
    if args.json:
        print(json.dumps(public, indent=2, sort_keys=True, default=str))
    else:
        conductor = public["conductor"]
        print(f"conductor ok={conductor['ok']} steps={len(conductor['completed'])}/7 "
              f"manifest={public.get('conductor_manifest_digest', '-')[:16]}")
        forge = public.get("forge") or {}
        print(f"forge succeeded={forge.get('succeeded')} files={len(public['file_names'])} "
              f"playable={(public.get('playable') or {}).get('mode')} ok={public['ok']}")
        if not conductor["ok"]:
            print(f"halted at {public.get('halted_at')}: {(conductor.get('error') or {}).get('message')}",
                  file=sys.stderr)
    return 0 if public["ok"] else 1


__all__ = [
    "GENRE_PLAYABLE", "MANIFEST_PATH", "SCHEMA", "admit_conductor_manifest", "cli", "conduct",
    "conductor_manifest_source", "public_envelope",
]
