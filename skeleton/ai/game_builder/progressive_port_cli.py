"""Offline, design-only multi-hop port preview for original homebrew projects.

The operator supplies an evidence digest for provenance *reference*, never a
credential or certificate. This tool does not validate possession of rights,
compile binaries, contact a network, write assets or grant distribution rights.

Example:
  python -m skeleton.ai.game_builder.progressive_port_cli \
    --project-id my-own-game --source bandai_wonderswan \
    --destination windows_modern --destination nintendo_game_boy \
    --rights-basis project_owned --evidence-sha256 <64-char-sha256> \
    --identity 'own original play rules' --mode enhanced
"""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from .editor_platforms import editor_progressive_route_preview
from .port_planner import HomebrewSource, PortMode, PortPlanningError


def preview_from_argv(argv: Sequence[str] | None = None) -> dict[str, object]:
    """Build a deterministic review-only JSON contract without side effects."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", action="append", required=True)
    parser.add_argument("--rights-basis", required=True, choices=(
        "project_owned", "licensed_homebrew", "public_domain_homebrew",
    ))
    parser.add_argument("--evidence-sha256", required=True)
    parser.add_argument("--identity", action="append", required=True)
    parser.add_argument("--mode", choices=(
        PortMode.FAITHFUL.value, PortMode.ENHANCED.value,
        PortMode.REVERSE_CONSTRAINED.value,
    ), default=PortMode.ENHANCED.value)
    args = parser.parse_args(argv)
    try:
        source = HomebrewSource(
            project_id=args.project_id, platform_id=args.source,
            rights_basis=args.rights_basis, evidence_sha256=args.evidence_sha256,
            creative_identity=tuple(args.identity),
        )
        result = editor_progressive_route_preview(
            source, tuple(args.destination), mode=PortMode(args.mode),
        )
    except PortPlanningError as exc:
        parser.error(str(exc))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    result = preview_from_argv(argv)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
