"""Author the SAME original playable game for all real native machine engines.

Not a bundle of ten filenames around one HTML game: every target contains its
own executable source for the real machine, generated independently from the
same proven authored world and rights reference. All output is built in an
isolated sibling staging folder then published in one directory move. Partial
cross-era portfolios never masquerade as successful final results.

Example:
    python -m skeleton.ai.game_builder.native_portfolio_cli \
      --basis bandai_wonderswan --project-id new-maze --title 'Star Voyage' \
      --seed 1986 --rights-evidence ./my-original-creation.txt \
      --identity "own star puzzles" --identity "my original artwork" \
      --out ./all-native-games --authorize-original-homebrew
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .native_game_cli import _NATIVE, build_game

_SCHEMA = "skeleton.game_builder.native_portfolio.v1"


class NativePortfolioError(ValueError):
    """The multi-platform export was refused or a source target lost identity."""


def compile_native_portfolio(
    *,
    basis: str,
    project_id: str,
    title: str,
    seed: int,
    rights_evidence: str | Path,
    creative_identity: tuple[str, ...],
    output: str | Path,
    authorized: bool,
    targets: tuple[str, ...] | None = None,
    width: int = 17,
    height: int = 15,
    levels: int = 3,
    collectibles: int = 3,
    hazards: int = 4,
    health: int = 4,
) -> dict[str, Any]:
    """Make a new all-or-nothing native-source portfolio, never a release claim."""
    if type(authorized) is not bool or not authorized:
        raise PermissionError("multi-era original game portfolio requires explicit authorization")
    if targets is None:
        destinations = tuple(sorted(_NATIVE))
    else:
        if not isinstance(targets, tuple):
            raise NativePortfolioError("portfolio targets must be a finite tuple")
        if not targets or len(targets) > len(_NATIVE):
            raise NativePortfolioError("portfolio target budget or count invalid")
        if any(not isinstance(t, str) or t not in _NATIVE for t in targets):
            raise NativePortfolioError("portfolio destination lacks a real native exporter")
        if len(set(targets)) != len(targets):
            raise NativePortfolioError("duplicate platform destinations forbidden")
        destinations = tuple(sorted(targets))
    dest = Path(output)
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(str(dest))
    if not dest.parent.is_dir() or dest.parent.is_symlink():
        raise NativePortfolioError("native portfolio parent must be an existing ordinary folder")

    with TemporaryDirectory(prefix=".skeleton-native-port-", dir=dest.parent) as staging:
        scratch = Path(staging) / "portfolio"
        (scratch / "targets").mkdir(parents=True, exist_ok=False)
        built = []
        world_digest: str | None = None
        replay_digest: str | None = None
        rights_digest: str | None = None
        for platform in destinations:
            out = scratch / "targets" / platform
            row = build_game(
                target=platform, basis=basis,
                project_id=project_id, title=title, seed=seed,
                width=width, height=height, levels=levels,
                collectibles=collectibles, hazards=hazards,
                health=health, rights_evidence=rights_evidence,
                creative_identity=creative_identity, output=out,
                authorized=True,
            )
            fingerprint = row["world_digest"]
            replay = row["winning_replay_digest"]
            clearance = row["rights_evidence_sha256"]
            if world_digest is None:
                world_digest = fingerprint
                replay_digest = replay
                rights_digest = clearance
            elif (fingerprint != world_digest
                    or replay != replay_digest or clearance != rights_digest):
                raise NativePortfolioError("historical port lost identical original source identity")
            if (row["native_binary_built"] is not False
                    or row["rights_independently_verified"] is not False
                    or row["compiler_execution"] is not False):
                raise NativePortfolioError("native authoring falsely asserted platform certification")
            meta = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            if meta["world_digest"] != fingerprint:
                raise NativePortfolioError("native platform manifest world identity corrupted")
            built.append({
                "platform": platform,
                "native_source_kind": row["source_kind"],
                "relative_source_directory": "targets/" + platform,
                "native_source_digest": row["source_content_digest"],
                "world_digest": fingerprint,
                "reference_replay_digest": replay,
                "native_binary_built": False,
                "emulator_playthrough_verified": False,
                "release_approved": False,
            })
        manifest = {
            "schema": _SCHEMA,
            "original_project_id": project_id,
            "source_era_hardware": basis,
            "original_world_digest": world_digest,
            "original_safe_replay_digest": replay_digest,
            "author_supplied_rights_evidence_sha256": rights_digest,
            "target_count": len(built),
            "native_projects": built,
            "binary_compilation_executed": False,
            "any_emulator_playthrough_verified": False,
            "independent_legal_clearance_verified": False,
            "rights_to_distribute": False,
            "derived_or_plagiarized_commercial_assets_allowed": False,
        }
        payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        manifest["portfolio_digest"] = sha256(payload.encode("utf-8")).hexdigest()
        with (scratch / "portfolio-manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
        if dest.exists() or dest.is_symlink():
            raise FileExistsError(str(dest))
        os.rename(scratch, dest)
    return {**manifest, "output_directory": str(dest)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--basis", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--rights-evidence", required=True, type=Path)
    parser.add_argument("--identity", required=True, action="append")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--target", action="append", choices=sorted(_NATIVE))
    parser.add_argument("--width", type=int, default=17)
    parser.add_argument("--height", type=int, default=15)
    parser.add_argument("--levels", type=int, default=3)
    parser.add_argument("--collectibles", type=int, default=3)
    parser.add_argument("--hazards", type=int, default=4)
    parser.add_argument("--health", type=int, default=4)
    parser.add_argument("--authorize-original-homebrew", action="store_true")
    args = parser.parse_args()
    evidence = compile_native_portfolio(
        basis=args.basis, project_id=args.project_id,
        title=args.title, seed=args.seed,
        rights_evidence=args.rights_evidence,
        creative_identity=tuple(args.identity), output=args.out,
        authorized=args.authorize_original_homebrew,
        targets=None if args.target is None else tuple(args.target),
        width=args.width, height=args.height,
        levels=args.levels, collectibles=args.collectibles,
        hazards=args.hazards, health=args.health,
    )
    print(json.dumps(evidence, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
