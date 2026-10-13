"""Source-pinned Python/JS/TS import explorer over the existing Jeeves inventory.

The graph is static evidence, not runtime authority or executable imports.
All reads use the canonical symlink-safe, private-path-aware source inventory.
"""
from __future__ import annotations

from collections import Counter, deque
from hashlib import sha256
from pathlib import PurePosixPath
import posixpath

from .jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, PRIVATE, _relative, digest,
)
from .jeeves_capability_intelligence import (
    CODE_SUFFIXES, _generic_contract, _python_contract,
)

SCHEMA = "skeleton.ai.jeeves_dependency_navigation.v1"
JS_SUFFIXES = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
MAX_SOURCE = 128_000


def _bounded(value, name, smallest, largest):
    if type(value) is not int or not smallest <= value <= largest:
        raise JeevesAppwideError("bounded " + name + " required")
    return value


class JeevesSourceDependencyGraph:
    """Finite, reproducible source import topology with exact SHA receipts."""

    def __init__(self, inventory: AppwideInventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("scanned Jeeves source inventory required")
        inventory._require_scanned()
        self.inventory = inventory

    def _available(self, path):
        entry = self.inventory._files.get(path)
        return (entry is not None and entry.readable
                and entry.kind == "source" and not PRIVATE.search(path)
                and PurePosixPath(path).suffix.lower() in CODE_SUFFIXES)

    def _resolve(self, source, imported):
        suffix = PurePosixPath(source).suffix.lower()
        if suffix == ".py":
            if not imported or imported.startswith(".") or "/" in imported:
                return None
            root = imported.replace(".", "/")
            candidates = (root + ".py", root + "/__init__.py")
        elif suffix in JS_SUFFIXES and imported.startswith("."):
            if "\\" in imported:
                return None
            root = posixpath.normpath(
                posixpath.join(posixpath.dirname(source), imported))
            if root == ".." or root.startswith("../") or root.startswith("/"):
                return None
            candidates = (
                root, *(root + ending for ending in JS_SUFFIXES),
                *(root + "/index" + ending for ending in JS_SUFFIXES),
            )
        else:
            return None
        return next((p for p in candidates if self._available(p)), None)

    def walk(self, *, paths, depth=3, max_nodes=64,
             max_source_bytes=1_000_000, expected_snapshot=None):
        inv = self.inventory
        if expected_snapshot is not None and expected_snapshot != inv._digest:
            raise JeevesAppwideError("stale graph source identity")
        if type(paths) is not list or not 1 <= len(paths) <= 8:
            raise JeevesAppwideError("1–8 source roots needed")
        _bounded(depth, "dependency depth", 0, 5)
        _bounded(max_nodes, "dependency nodes", 1, 128)
        _bounded(max_source_bytes, "dependency bytes", 128, 2_000_000)
        roots = [_relative(path) for path in paths]
        if (len(set(roots)) != len(roots) or max_nodes < len(roots) or
                not all(self._available(path) for path in roots)):
            raise JeevesAppwideError("missing, duplicate or restricted source root")
        queue = deque((path, 0) for path in sorted(roots))
        scheduled = set(roots)
        nodes, edges = {}, set()
        reasons = Counter()
        total_bytes = 0
        while queue:
            path, level = queue.popleft()
            source = inv._files[path]
            node = {
                "path": path, "depth": level,
                "source_bytes": source.bytes, "source_sha256": None,
                "language": PurePosixPath(path).suffix.lower(),
                "syntax_status": "not_loaded",
            }
            nodes[path] = node
            if source.bytes > MAX_SOURCE:
                node["syntax_status"] = "oversized"
                reasons["oversized"] += 1
                continue
            if total_bytes + source.bytes > max_source_bytes:
                node["syntax_status"] = "byte_budget"
                reasons["byte_budget"] += 1
                continue
            try:
                content = inv._safe_file(path, max_size=MAX_SOURCE)
            except JeevesAppwideError:
                node["syntax_status"] = "changed_or_unreadable"
                reasons["changed_or_unreadable"] += 1
                continue
            total_bytes += len(content.encode("utf-8"))
            node["source_sha256"] = sha256(content.encode("utf-8")).hexdigest()
            contract = (_python_contract(content, path) if path.endswith(".py")
                        else _generic_contract(content, path))
            node["syntax_status"] = contract["status"]
            node["declared_symbols"] = contract["total_symbols"]
            node["declared_imports"] = contract["total_imports"]
            if level >= depth:
                reasons["depth_capped_imports"] += contract["total_imports"]
                continue
            for import_token in contract["static_imports"][:96]:
                target = self._resolve(path, import_token)
                if target is None:
                    reasons["external_or_unresolved"] += 1
                    continue
                if target == path:
                    reasons["self_import"] += 1
                    continue
                if target not in scheduled:
                    if len(scheduled) >= max_nodes:
                        reasons["node_budget"] += 1
                        continue
                    scheduled.add(target)
                    queue.append((target, level + 1))
                edges.add((path, target, import_token))
        report = {
            "schema": SCHEMA,
            "inventory_snapshot": inv._digest,
            "roots": sorted(roots),
            "depth_limit": depth, "node_limit": max_nodes,
            "source_byte_limit": max_source_bytes,
            "source_bytes_read": total_bytes,
            "nodes": [nodes[p] for p in sorted(nodes)],
            "edges": [{
                "from": source, "to": target, "source_import": token,
                "runtime_import_verified": False,
            } for source, target, token in sorted(edges)],
            "node_count": len(nodes), "edge_count": len(edges),
            "unresolved_or_bounded": dict(sorted(reasons.items())),
            "complete_source_closure_proven": not bool(reasons),
            "syntax_imports_do_not_grant_execution_authority": True,
            "files_executed": 0, "source_edits_performed": 0,
        }
        return {**report, "digest": digest(report)}
