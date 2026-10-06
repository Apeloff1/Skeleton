#!/usr/bin/env python3
"""Deterministic owner lookup against the canonical architecture contract."""
from __future__ import annotations

import argparse
import json
from pathlib import PurePosixPath
from typing import Any

from scripts.check_architecture_map import ARCHITECTURE_PATH, REPO_ROOT, _load_json, _normalized_repo_path


class OwnershipError(ValueError):
    pass


def _contains(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


def build_owner_index(architecture: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in architecture.get("canonical_roots", []):
        if not isinstance(raw, dict):
            continue
        path = _normalized_repo_path(raw.get("path"))
        owner = raw.get("owner")
        root_id = raw.get("id")
        if not isinstance(owner, str) or not owner or not isinstance(root_id, str) or not root_id:
            raise OwnershipError(f"canonical root {path!r} lacks owner/id")
        rows.append({"path": path, "owner": owner, "root_id": root_id, "class": raw.get("class")})

    # Zone roots provide ownership for paths below a declared zone when no more
    # specific canonical root exists. Zone id is intentionally the owner token:
    # it is stable machine authority, not a guessed human/team name.
    for raw in architecture.get("zones", []):
        if not isinstance(raw, dict):
            continue
        zone_id = raw.get("id")
        if not isinstance(zone_id, str) or not zone_id:
            raise OwnershipError("zone lacks stable id")
        for value in raw.get("roots", []):
            path = _normalized_repo_path(value)
            rows.append({"path": path, "owner": zone_id, "root_id": zone_id, "class": "zone"})

    rows.sort(key=lambda row: (-len(PurePosixPath(row["path"]).parts), row["path"], row["root_id"]))
    return tuple(rows)


def resolve_owner(path: str, architecture: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalized_repo_path(path)
    matches = [row for row in build_owner_index(architecture) if _contains(normalized, row["path"])]
    if not matches:
        raise OwnershipError(f"no canonical architecture owner for {normalized}")
    depth = len(PurePosixPath(matches[0]["path"]).parts)
    peers = [row for row in matches if len(PurePosixPath(row["path"]).parts) == depth]
    authorities = {(row["owner"], row["root_id"]) for row in peers}
    if len(authorities) != 1:
        raise OwnershipError(f"ambiguous canonical ownership for {normalized}: {sorted(authorities)}")
    winner = peers[0]
    return {
        "path": normalized,
        "owner": winner["owner"],
        "authority_id": winner["root_id"],
        "matched_root": winner["path"],
        "ownership_class": winner["class"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--architecture", default=ARCHITECTURE_PATH.as_posix())
    args = parser.parse_args()
    architecture = _load_json(REPO_ROOT / _normalized_repo_path(args.architecture))
    try:
        result = resolve_owner(args.path, architecture)
    except (OwnershipError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"valid": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
