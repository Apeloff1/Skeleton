"""Resume a native console/engine/media studio campaign from a JSON order.

Run only when an operator explicitly authorizes project source generation.
No external model inference, background tasks, or toolchain launch.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .studio_asset_pipeline import ArtDirection
from .studio_campaign import CampaignOrder, inspect_campaign, run_campaign


def parse_campaign_order_file(path: Path) -> CampaignOrder:
    """Parse the exact original production schema used by both operator CLIs."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if type(raw) is not dict or raw.get("schema") != "skeleton.game_builder.studio_campaign_order.v1":
        raise ValueError("typed original campaign order schema required")
    allowed = {
        "schema", "project_id", "title", "seed", "targets",
        "source_basis", "rights_document", "creative_identity",
        "width", "height", "levels", "collectibles", "hazards",
        "health", "theme", "art", "artist_png",
        "artist_sha256", "artist_quantization",
    }
    if set(raw) - allowed:
        raise ValueError("unknown campaign order parameters")
    art = raw.pop("art", {})
    raw.pop("schema")
    if type(art) is not dict or set(art) - set(ArtDirection.__dataclass_fields__):
        raise ValueError("unknown original art controls")
    raw["targets"] = tuple(raw["targets"])
    raw["creative_identity"] = tuple(raw["creative_identity"])
    raw["art"] = ArtDirection(**art)
    order = CampaignOrder(**raw)
    return order


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--authorize-original-homebrew", action="store_true")
    parser.add_argument("--max-targets", type=int)
    args = parser.parse_args(argv)
    try:
        order = parse_campaign_order_file(args.order)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    if args.inspect:
        result = inspect_campaign(order, args.output)
    else:
        if not args.authorize_original_homebrew:
            parser.error("explicit original-homebrew authorization required")
        if args.output.exists() and not args.resume:
            parser.error("existing campaign requires --resume to prevent unintended reuse")
        result = run_campaign(
            order, args.output, authorized=True, max_targets=args.max_targets,
        )
    print(json.dumps(result, sort_keys=True))
    return 0 if not result["pending_targets"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
