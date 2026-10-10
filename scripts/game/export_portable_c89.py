"""Portable ISO C89 interactive game source from verified rights-bound projects.

This is a REAL buildable computer-game source emitter for ordinary C
toolchains. It is NOT a Game Boy/NES/PlayStation/Xbox binary exporter and
does NOT use platform SDKs, ROM/BIOS copying, circumvention or external
game assets. Semantics are deliberately defined as turn-based grid
movement (WASD), not a false translation of platformer physics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from scripts.game.game_project import _read_json
from skeleton.ai.runtime.game_project_capsule import (
    GameCapsuleError, verify_game_capsule,
)
from skeleton.ai.runtime.gameplay_capabilities import compile_level


def emit_portable_c89(capsule: dict[str, Any]) -> dict[str, Any]:
    result = verify_game_capsule(capsule)
    level = compile_level({"tiles": capsule["tilemap"]})
    if not level["goal_reachable"]:
        raise GameCapsuleError("a portable game needs a connected player/goal map")
    if capsule["rights_receipt"]["legal_compliance_certified"] is not False:
        raise GameCapsuleError("source-level export cannot self-certify legal rights")
    if capsule["rights_receipt"]["source_kind_summary"] != ["original"]:
        raise GameCapsuleError(
            "generic game source export currently requires entirely original tiles"
        )
    width, height = level["width"], level["height"]
    lines = ",\n".join('    "' + line + '"' for line in capsule["tilemap"])
    source=(
        "/* Original, locally authored game source. Export is NOT legal release approval. */\n"
        "/* Cross-era portable C89 TURN-BASED text game, not console ROM or modern 3D title. */\n"
        "/* Source identity (portable capsule SHA-256): " + result["capsule_sha256"] + " */\n"
        "#include <stdio.h>\n\n"
        "#define GAME_WIDTH " + str(width) + "\n"
        "#define GAME_HEIGHT " + str(height) + "\n\n"
        "static const char *const skeleton_map[GAME_HEIGHT] = {\n" + lines + "\n};\n"
        "static int player_x = " + str(level["spawn"]["x"]) + ";\n"
        "static int player_y = " + str(level["spawn"]["y"]) + ";\n\n"
        "static int tile_walkable(int x, int y)\n"
        "{\n"
        "    if (x < 0 || y < 0 || x >= GAME_WIDTH || y >= GAME_HEIGHT) return 0;\n"
        "    return skeleton_map[y][x] != '#';\n"
        "}\n\n"
        "static void draw_world(void)\n"
        "{\n"
        "    int y, x;\n"
        "    for (y = 0; y < GAME_HEIGHT; ++y) {\n"
        "        for (x = 0; x < GAME_WIDTH; ++x) {\n"
        "            if (x == player_x && y == player_y) putchar('@');\n"
        "            else if (skeleton_map[y][x] == 'S') putchar('.');\n"
        "            else putchar(skeleton_map[y][x]);\n"
        "        }\n"
        "        putchar('\\n');\n"
        "    }\n"
        "}\n\n"
        "int main(void)\n"
        "{\n"
        "    int input;\n"
        "    puts(\"SKELETON ORIGINAL GAME - W/A/S/D to move, Q to quit\");\n"
        "    draw_world();\n"
        "    while ((input = getchar()) != EOF) {\n"
        "        int dx = 0, dy = 0;\n"
        "        int nx, ny;\n"
        "        if (input == 'q' || input == 'Q') { puts(\"QUIT\"); return 0; }\n"
        "        if (input == 'a' || input == 'A') dx = -1;\n"
        "        else if (input == 'd' || input == 'D') dx = 1;\n"
        "        else if (input == 'w' || input == 'W') dy = -1;\n"
        "        else if (input == 's' || input == 'S') dy = 1;\n"
        "        else continue;\n"
        "        nx = player_x + dx;\n"
        "        ny = player_y + dy;\n"
        "        if (!tile_walkable(nx, ny)) { puts(\"BLOCKED\"); continue; }\n"
        "        player_x = nx;\n"
        "        player_y = ny;\n"
        "        draw_world();\n"
        "        if (skeleton_map[player_y][player_x] == 'G') {\n"
        "            puts(\"WIN\");\n"
        "            return 0;\n"
        "        }\n"
        "    }\n"
        "    return 0;\n"
        "}\n"
    )
    binary = source.encode("ascii")
    if len(binary) > 24 * 1024:
        raise GameCapsuleError("portable C89 source exceeds 24 KiB")
    return {
        "schema_version": "skeleton.game.portable_c89.v1",
        "source": source,
        "source_sha256": hashlib.sha256(binary).hexdigest(),
        "source_bytes": len(binary),
        "source_game_capsule_sha256": result["capsule_sha256"],
        "language": "ISO C89",
        "play_semantics": "turn_based_integer_tile_grid",
        "compiled_binary_exists": False,
        "console_rom_created": False,
        "licensed_platform_sdk_used": False,
        "source_rights_independently_verified": False,
        "publish_authorized": False,
        "training_examples_added": 0,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit ISO C89 game source from verified original project; no console ROM produced.",
    )
    parser.add_argument("--capsule", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        project = _read_json(args.capsule)
        artifact = emit_portable_c89(project)
        destination = args.output.expanduser().absolute()
        if (
            destination.exists() or destination.is_symlink()
            or not destination.parent.is_dir()
            or destination == args.capsule.expanduser().absolute()
        ):
            raise GameCapsuleError("portable C source output must be an unused path")
        fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(artifact["source"].encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
        public = {key: value for key, value in artifact.items() if key != "source"}
        public["output_path"] = str(destination)
        print(json.dumps(public, sort_keys=True))
        return 0
    except (GameCapsuleError, UnicodeError, ValueError, TypeError,
            KeyError, OSError) as exc:
        print("portable game C source export rejected: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
