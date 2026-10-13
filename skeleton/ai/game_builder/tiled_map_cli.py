"""Offline operator CLI: map Tiled JSON designs into original playable games."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .contracts import canonical_json
from .playable_cli import MAX_INPUT_BYTES, _intent, _read_json
from .playable_compiler import PlayableCompilationError
from .tiled_map_import import (
    TiledImportError, import_tiled_levels, write_tiled_authored_json,
)
from .playable_world import PlayableWorldError


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.tiled_map_cli",
        description=(
            "Convert open-source Tiled editor numeric tile layers into "
            "verified original-only homebrew geometry. No imported assets."
        ),
    )
    root.add_argument("--intent", required=True, help="Original game-build intent JSON")
    root.add_argument("--tiled-level", required=True, action="append",
                      help="One local finite orthogonal Tiled map JSON per game level")
    root.add_argument("--output", required=True, help="New authored-world JSON file")
    root.add_argument("--palette", help="Optional local JSON object of decimal gid -> original tile code")
    root.add_argument("--human-reviewed", action="store_true",
                      help="Acknowledge separately performed original geometry review")
    root.add_argument("--trusted-local-operator", action="store_true",
                      help="Acknowledge externally established authorization")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.trusted_local_operator:
        print("error: operator authorization acknowledgement required", file=sys.stderr)
        return 2
    if not args.human_reviewed:
        print("error: original geometry human review acknowledgement required", file=sys.stderr)
        return 2
    try:
        intent = _intent(_read_json(args.intent, MAX_INPUT_BYTES))
        palette = None
        if args.palette:
            document = _read_json(args.palette, 3000)
            if not document or len(document) > 64:
                raise TiledImportError("palette must contain at most 64 numeric GIDs")
            palette = {}
            for key, value in document.items():
                if not isinstance(key, str) or not key.isdecimal():
                    raise TiledImportError("palette GIDs must be unsigned decimal IDs")
                number = int(key)
                if number in palette:
                    raise TiledImportError("duplicate mapped numeric GID")
                palette[number] = value
        conversion = import_tiled_levels(
            intent, tuple(args.tiled_level),
            human_reviewed=True, authorized=True, gid_palette=palette,
        )
        output = write_tiled_authored_json(
            conversion, Path(args.output), authorized=True,
        )
    except (TiledImportError, PlayableWorldError, PlayableCompilationError,
            OSError, ValueError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(canonical_json({
        "schema": "skeleton.game_builder.tiled_map_cli_result.v1",
        "output": str(output),
        "conversion_digest": conversion.digest,
        **conversion.receipt(),
        "next_step": "original_game_studio_cli --authored-world --human-reviewed",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "parser"]
