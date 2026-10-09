"""Deterministic native-desktop acceptance game and platform binary verifier.

The two modes deliberately never invoke a compiler or execute a binary:
CI explicitly chooses/installs its toolchain and runs the native smoke replay.
No downloaded ROM, original commercial-game material or firmware is used.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from skeleton.ai.game_builder.desktop_native_export import (
    compile_native_desktop,
    export_native_desktop_source,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource

TARGETS = ("linux_desktop", "macos_modern", "windows_modern")


def make_acceptance_game(target: str, output: Path) -> dict[str, object]:
    """Emit a playable, deterministic three-level ORIGINAL native C/SDL2 game."""
    if target not in TARGETS:
        raise ValueError("unsupported native desktop target")
    intent = GameBuildIntent(
        project_id="skeleton-native-acceptance",
        title="Star Cartographers - Original Homebrew",
        subtitle="Cross-era native game builder replay",
        seed=71368,
        width=17,
        height=15,
        levels=3,
        collectibles_per_level=3,
        hazards_per_level=5,
        starting_health=4,
        theme="space",
    )
    world = generate_playable_world(intent, authorized=True)
    # This is a *reference to the generated original world*, not an independent
    # legal certification or a substitute for shipping/license approval.
    evidence = sha256(
        json.dumps(world.to_payload(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    source = HomebrewSource(
        project_id=intent.project_id,
        platform_id="bandai_wonderswan",
        rights_basis="project_owned",
        evidence_sha256=evidence,
        creative_identity=("exploration in original mazes", "light-and-ink star maps", "collect-and-exit"),
    )
    project = compile_native_desktop(world, source, target, authorized=True)
    folder = export_native_desktop_source(project, output, authorized=True)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest["world_digest"] != world.digest
        or manifest["native_headless_replay_available"] is not True
        or manifest["native_headless_replay_executed"] is not False
        or manifest["releasable"] is not False
    ):
        raise RuntimeError("native artifact provenance or release boundary mismatched")
    return {
        "target": target,
        "source_directory": str(folder),
        "project_sha256": project.content_digest,
        "world_digest": world.digest,
        "replay_steps": manifest["native_replay_expected_steps"],
        "expected_score": manifest["native_replay_expected_score"],
        "binary_verified": False,
        "distribution_licensed": False,
    }


def check_binary(target: str, path: Path) -> dict[str, object]:
    """Identify real native executable headers, not filename extensions alone."""
    if target not in TARGETS:
        raise ValueError("unsupported native desktop target")
    with path.open("rb") as stream:
        magic = stream.read(8)
    supported = {
        "windows_modern": (b"MZ",),
        "linux_desktop": (b"\x7fELF",),
        "macos_modern": (
            b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf",
            b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
            b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca",
        ),
    }
    if not any(magic.startswith(prefix) for prefix in supported[target]):
        raise RuntimeError(f"{target} native executable signature missing")
    if path.stat().st_size < 4096:
        raise RuntimeError("unexpectedly small or truncated native executable")
    hasher = sha256()
    with path.open("rb") as stream:
        while data := stream.read(1024 * 1024):
            hasher.update(data)
    return {
        "target": target,
        "binary_file": path.name,
        "binary_size": path.stat().st_size,
        "binary_sha256": hasher.hexdigest(),
        "native_header_verified": True,
        "gameplay_replay_run_by_caller": False,
        "distribution_licensed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--emit", type=Path, metavar="NEW_DIRECTORY")
    mode.add_argument("--verify-binary", type=Path, metavar="NATIVE_BINARY")
    args = parser.parse_args()
    result = (
        make_acceptance_game(args.target, args.emit)
        if args.emit is not None
        else check_binary(args.target, args.verify_binary)
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
