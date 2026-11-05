"""Offline scene renderer and original text asset editor for playable salvage."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .harbor_crafting import HarborError, MAX_BUNDLE_BYTES, canonical, decode
from .harbor_crafting_salvage import MAX_BOARD_BYTES, MAX_REPORT_BYTES
from .harbor_crafting_salvage_assets import (
    MAX_BYTES as MAX_ASSET_BYTES, salvage_asset_manifest,
)
from .harbor_crafting_salvage_assets_authoring import (
    MAX_BYTES as MAX_REVISION_BYTES, edit_salvage_assets,
    verify_salvage_assets_revision,
)
from .harbor_crafting_salvage_map import (
    MAX_BYTES as MAX_MAP_BYTES, render_salvage_map, verify_salvage_map,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEFAULT_SOURCE = FIXTURES / "harbor_lantern_quay.json"
DEFAULT_BOARD = FIXTURES / "harbor_lantern_quay_salvage.json"
DEFAULT_ASSETS = FIXTURES / "harbor_lantern_quay_salvage_assets.json"
COMMANDS = ("render", "verify", "print", "manifest", "author", "verify-author")


def _read(path: str | None, maximum: int):
    if not path:
        raise HarborError("required salvage map input path missing")
    try:
        if path == "-":
            raw = sys.stdin.buffer.read(maximum + 1)
        else:
            with Path(path).open("rb") as stream:
                raw = stream.read(maximum + 1)
    except OSError as exc:
        raise HarborError("cannot read requested salvage map input") from exc
    return decode(raw, maximum)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render original salvage scenes and edit glyphs")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--board", default=str(DEFAULT_BOARD))
    parser.add_argument("--assets", default=str(DEFAULT_ASSETS))
    parser.add_argument("--report")
    parser.add_argument("--view")
    parser.add_argument("--edits")
    parser.add_argument("--revision")
    parser.add_argument("--expected-assets-digest")
    parser.add_argument("--reveal", action="store_true")
    args = parser.parse_args(argv)
    try:
        cmd = args.command
        if cmd in {"verify", "print"}:
            view = _read(args.view, MAX_MAP_BYTES)
            frame = verify_salvage_map(view)
            if cmd == "print":
                sys.stdout.write("\n".join(frame) + "\n")
                return 0
            result = frame
        elif cmd == "verify-author":
            result = verify_salvage_assets_revision(_read(args.revision, MAX_REVISION_BYTES))
        elif cmd == "render":
            result = render_salvage_map(
                _read(args.report, MAX_REPORT_BYTES),
                _read(args.assets, MAX_ASSET_BYTES), reveal=args.reveal,
            )
        else:
            source = _read(args.source, MAX_BUNDLE_BYTES)
            board = _read(args.board, MAX_BOARD_BYTES)
            assets = _read(args.assets, MAX_ASSET_BYTES)
            if cmd == "manifest":
                result = salvage_asset_manifest(assets, source, board)
            elif cmd == "author":
                result = edit_salvage_assets(
                    source, board, assets, _read(args.edits, MAX_ASSET_BYTES),
                    expected_assets_digest=args.expected_assets_digest or "",
                    preview_report=None if not args.report
                    else _read(args.report, MAX_REPORT_BYTES),
                )
            else:
                raise HarborError("unsupported salvage map command")
        sys.stdout.buffer.write(canonical(result) + b"\n")
        return 0
    except (HarborError, TypeError, KeyError) as exc:
        print("salvage map rejected: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
