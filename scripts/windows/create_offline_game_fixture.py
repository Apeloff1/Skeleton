"""Create only original, rights-attested native game smoke fixtures for CI.

No third-party ROM, console assets or model training; input is the same
procedural original game shipped as Skeleton's native demo.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from skeleton.app.offline_game_preview import OfflineGamePreview
from skeleton.ai.runtime.gameplay_capabilities import compile_level
from skeleton.ai.runtime.game_rights import SCHEMA as RIGHTS_SCHEMA
from skeleton.ai.runtime.game_project_capsule import (
    make_game_capsule, verify_game_capsule,
)


def create_fixture(seed: int = 42) -> dict:
    source = list(OfflineGamePreview(seed=seed).tiles)
    source_digest = compile_level({"tiles": source})["tile_digest"]
    asset = {
        "asset_id": "tilemap",
        "sha256": source_digest,
        "source_kind": "original",
        "licensor": "skeleton-internal-test-fixture",
        "license_reference": "original-procedural-ci-fixture-v1",
        "allowed_uses": ["embed", "modify"],
        "contains_third_party_content": False,
        "contains_trademarks": False,
        "contains_technological_protection": False,
    }
    rights = {
        "schema_version": RIGHTS_SCHEMA,
        "project_id": f"ci-original-game-{seed}",
        "title": "Original procedural game fixture",
        "rights_contact": "local-ci-unverified",
        "assets": [asset],
        "source_game_reference": None,
        "sdk_authorization": None,
    }
    capsule = make_game_capsule(
        source_tiles=source,
        rights_manifest=rights,
        target_ids=["windows-11", "game-boy", "playstation-5"],
        required_features=["tile2d", "input"],
        action="original_game", jurisdiction="NO",
    )
    if not capsule["playability"]["actual_controller_replay_qualified"]:
        raise ValueError("original fixture is not controllably playable")
    verify_game_capsule(capsule)
    return capsule


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    capsule = create_fixture(args.seed)
    target = args.output.expanduser().absolute()
    if target.is_symlink() or target.exists() or not target.parent.is_dir():
        parser.error("CI fixture output must be an unused regular local file")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(
            (json.dumps(capsule, sort_keys=True, separators=(",", ":")) + "\n")
            .encode("ascii")
        )
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({
        "capsule_sha256": capsule["capsule_sha256"],
        "controller_status": capsule["playability"]["controller_search_status"],
        "ready_for_native_preview": True,
        "console_rom_created": False,
        "legal_release_approved": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
