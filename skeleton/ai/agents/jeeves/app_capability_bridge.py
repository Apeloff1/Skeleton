"""Jeeves application awareness and typed creator proposal tools.

The host owns all filesystem capabilities. This adapter only *reads* bounded
canonical machine registries or compiles the existing creator command surface;
it NEVER executes an editor, writes a file, or supplies its own execution grant.
Host-side ToolExecutor / epistemic permits still gate every real action.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

SCHEMA = "jeeves.app_capability_bridge.v1"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_QUERY = 160
MAX_PAGE = 64
MAX_ROWS = 40000


class AppCapabilityBridgeError(ValueError):
    """Input or a canonical machine-index authority is invalid."""


def _root(root: Path | str | None) -> Path:
    if root is not None:
        value = Path(root).resolve()
        if not (value / "machine" / "ai_file_tree.json").is_file():
            raise AppCapabilityBridgeError("repository root has no canonical AI file-tree index")
        return value
    for path in Path(__file__).resolve().parents:
        if (path / "machine" / "ai_file_tree.json").is_file():
            return path
    raise AppCapabilityBridgeError("repository machine index is unavailable")


def _manifest(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise AppCapabilityBridgeError("machine index exceeds size budget")
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise AppCapabilityBridgeError(f"cannot read canonical machine index: {path.name}") from exc
    if not isinstance(raw, dict):
        raise AppCapabilityBridgeError("machine index must be a JSON object")
    return raw


def _page(query: str, limit: int, offset: int) -> tuple[str, int, int]:
    if not isinstance(query, str) or len(query) > MAX_QUERY:
        raise AppCapabilityBridgeError("query must be at most 160 characters")
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        raise AppCapabilityBridgeError("limit must be an integer in 1..64")
    if type(offset) is not int or not 0 <= offset <= MAX_ROWS:
        raise AppCapabilityBridgeError("offset exceeds index range")
    return query.casefold().strip(), limit, offset


def _row(mapping: Mapping[str, Any], roots: list[Mapping[str, Any]]) -> dict[str, Any]:
    identity = mapping.get("id")
    source = mapping.get("source")
    destination = mapping.get("destination")
    if not all(isinstance(x, str) and x and len(x) <= 1024 for x in (identity, source, destination)):
        raise AppCapabilityBridgeError("AI mapping has invalid identity/path")
    owner = ""
    for node in roots:
        prefix = node.get("path", "")
        if isinstance(prefix, str) and (source == prefix or source.startswith(prefix.rstrip("/") + "/")):
            if len(prefix) > len(owner):
                owner = prefix
    return {
        "id": identity,
        "source": source,
        "destination": destination,
        "owner_root": owner or "unresolved",
        "role": str(mapping.get("role") or "")[:512],
        "parity_mode": str(mapping.get("parity_mode") or "unspecified")[:80],
        "authority": "index-only",
    }


def capability_catalog(*, query: str = "", limit: int = 20, offset: int = 0,
                       root: Path | str | None = None) -> dict[str, Any]:
    """Paged machine index with a content hash; no recursive repository reads.

    An indexed/mirrored file is not automatically a working or granted editor.
    This returns what the architecture *declares*, not model-invented abilities.
    """
    needle, limit, offset = _page(query, limit, offset)
    home = _root(root)
    tree = _manifest(home / "machine" / "ai_file_tree.json")
    arch = _manifest(home / "machine" / "architecture.json")
    interfaces = _manifest(home / "machine" / "capability_interfaces.json")
    mappings, roots, links = tree.get("mappings"), arch.get("canonical_roots"), interfaces.get("entries")
    if not isinstance(mappings, list) or not isinstance(roots, list) or not isinstance(links, list):
        raise AppCapabilityBridgeError("canonical index arrays are absent")
    if len(mappings) > MAX_ROWS or len(links) > MAX_ROWS:
        raise AppCapabilityBridgeError("canonical index exceeds entry budget")
    rows = [_row(row, roots) for row in mappings if isinstance(row, dict)]
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise AppCapabilityBridgeError("AI mapping has duplicate IDs")
    rows.sort(key=lambda x: (x["source"], x["id"]))
    digest = sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True).encode("utf-8")).hexdigest()
    matches = [row for row in rows if not needle or needle in (
        row["id"] + " " + row["source"] + " " + row["destination"]
        + " " + row["role"] + " " + row["owner_root"]
    ).casefold()]
    page = matches[offset: offset + limit]
    return {
        "schema": SCHEMA,
        "query": query,
        "total_indexed": len(rows),
        "total_matched": len(matches),
        "interface_contracts": len(links),
        "owner_roots": len(roots),
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(page) < len(matches),
        "index_sha256": digest,
        "capabilities": page,
        "execution_authority": "none",
        "validation": "index-only; no runtime execution evidence",
    }


def creator_operation_catalog() -> dict[str, Any]:
    from skeleton.forge.creator.command_surface import surface_manifest
    surface = surface_manifest("api")
    return {
        "schema": SCHEMA,
        "catalog": surface.to_dict(),
        "execution_authority": "none",
        "approval_required_for_execution": True,
    }


def creator_proposal(operation: str, project_id: str,
                     payload: Mapping[str, Any]) -> dict[str, Any]:
    from skeleton.forge.creator.command_surface import build_creator_command
    command = build_creator_command(operation, project_id=project_id, payload=payload)
    return {
        "schema": SCHEMA,
        "kind": "creator-proposal",
        "command": command.to_dict(),
        "execution_authority": "none",
        "dispatch_performed": False,
    }


def register_app_tools(registry, *, root: Path | str | None = None) -> tuple[str, ...]:
    """Add only READ_ONLY tools to the existing trusted host registry.

    This intentionally registers NO mutating editor, export or release tool.
    Even an explicit host grant cannot make an unregistered tool execute.
    """
    from skeleton.jeeves.agent.tools import ArgumentRule, ToolRegistry, ToolSpec
    from skeleton.jeeves.agent.types import RiskTier

    if not isinstance(registry, ToolRegistry):
        raise TypeError("registry must be a host ToolRegistry")
    # Resolve root at registration, *not* from model-supplied arguments.
    home = _root(root)
    entries = (
        (ToolSpec(
            name="app.capabilities",
            description="Read paged, indexed app file ownership and mirror mappings; no execution.",
            risk=RiskTier.READ_ONLY,
            arguments=(
                ArgumentRule("query", "string", required=False, max_length=MAX_QUERY),
                ArgumentRule("limit", "integer", required=False, minimum=1, maximum=MAX_PAGE),
                ArgumentRule("offset", "integer", required=False, minimum=0, maximum=MAX_ROWS),
            ),
        ), lambda args, _ctx: capability_catalog(
            query=args.get("query", ""), limit=args.get("limit", 20),
            offset=args.get("offset", 0), root=home)),
        (ToolSpec(
            name="creator.operations",
            description="Read the canonical bounded creator operation schema; no execution.",
            risk=RiskTier.READ_ONLY,
        ), lambda _args, _ctx: creator_operation_catalog()),
        (ToolSpec(
            name="creator.propose",
            description="Validate and fingerprint a typed creator proposal without executing it.",
            risk=RiskTier.READ_ONLY,
            arguments=(
                ArgumentRule("operation", "string", choices=("create", "edit", "test", "preview", "export")),
                ArgumentRule("project_id", "string", max_length=128),
                ArgumentRule("payload", "object", max_length=512),
            ),
        ), lambda args, _ctx: creator_proposal(
            args["operation"], args["project_id"], args["payload"])),
    )
    for spec, handler in entries:
        registry.register(spec, handler)
    return tuple(spec.name for spec, _ in entries)
