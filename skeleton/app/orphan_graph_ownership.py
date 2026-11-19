"""Classify source graph observations against the staged AI-tree declaration.

Machine declarations are planning metadata, not independent ownership,
parity or cutover evidence. No graph edges or candidate identities are
collapsed. Overlay boundaries and explicit parity exceptions are retained.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
import re

from skeleton.app.orphan_cli_audit import AuditError


class OwnershipError(ValueError):
    pass


def _path(value):
    if (type(value) is not str or not value or len(value) > 1024
            or "\\" in value or value.startswith("/")):
        raise OwnershipError("invalid ownership path")
    path = PurePosixPath(value)
    if path.as_posix() != value or ".." in path.parts or "." in path.parts:
        raise OwnershipError("invalid ownership path")
    return value


def _relative(value):
    return _path(value)


def _prefix(path, prefix):
    return path == prefix or path.startswith(prefix + "/")


def _strings(value):
    if type(value) is not list or len(value) > 4096:
        raise OwnershipError("invalid ownership path array")
    return tuple(_relative(item) for item in value)


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise OwnershipError("duplicate ownership key")
        result[key] = value
    return result


@dataclass(frozen=True)
class Rule:
    mapping_id: str
    source: str
    destination: str
    kind: str
    mode: str
    exclusions: tuple[str, ...]
    overlays: tuple[str, ...]
    exceptions: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Native:
    owner_id: str
    path: str
    kind: str
    residual_only: bool


class OwnershipIndex:
    def __init__(self, raw: bytes):
        if type(raw) is not bytes or len(raw) > 8 * 1024 * 1024:
            raise OwnershipError("ownership byte ceiling")
        try:
            obj = json.loads(raw, object_pairs_hook=_object_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 OwnershipError("nonfinite ownership value")))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise OwnershipError("invalid ownership document") from exc
        if type(obj) is not dict or obj.get("schema_version") != 1:
            raise OwnershipError("unsupported ownership schema")
        mappings, natives = obj.get("mappings"), obj.get("native_ai_owners")
        if (type(mappings) is not list or type(natives) is not list
                or len(mappings) > 4096 or len(natives) > 4096):
            raise OwnershipError("ownership declaration ceiling")
        self.rules = {}
        self.natives = {}
        self.ids = set()
        for row in mappings:
            if type(row) is not dict:
                raise OwnershipError("invalid mapping record")
            key, kind = row.get("id"), row.get("kind")
            self._id(key)
            if kind not in ("file", "tree"):
                raise OwnershipError("unknown mapping kind")
            src, dst = _path(row.get("source")), _path(row.get("destination"))
            if src == dst or _prefix(src, dst) or _prefix(dst, src):
                raise OwnershipError("recursive mapping declaration")
            mode = row.get("parity_mode", "exact_or_declared")
            if type(mode) is not str or len(mode) > 128:
                raise OwnershipError("invalid parity mode")
            excludes = _strings(row.get("source_exclusions", []))
            overlays = _strings(row.get("overlay_children", []))
            exceptions = []
            values = row.get("parity_exceptions", [])
            if type(values) is not list or len(values) > 4096:
                raise OwnershipError("invalid parity exceptions")
            for item in values:
                if type(item) is not dict or type(item.get("mode")) is not str:
                    raise OwnershipError("invalid parity exception")
                exceptions.append((_relative(item.get("path")), item["mode"]))
            if len({item[0] for item in exceptions}) != len(exceptions):
                raise OwnershipError("duplicate parity exception")
            rule = Rule(key, src, dst, kind, mode, excludes, overlays, tuple(exceptions))
            self.rules.setdefault(src, []).append(("source", rule))
            self.rules.setdefault(dst, []).append(("destination", rule))
        for row in natives:
            if type(row) is not dict:
                raise OwnershipError("invalid native owner")
            key = row.get("id")
            self._id(key)
            path, kind = _path(row.get("path")), row.get("kind")
            if kind not in ("file", "tree") or type(row.get("residual_only", False)) is not bool:
                raise OwnershipError("invalid native declaration")
            self.natives.setdefault(path, []).append(
                Native(key, path, kind, row.get("residual_only", False)))

    def _id(self, value):
        if (type(value) is not str or not value or len(value) > 256
                or value in self.ids):
            raise OwnershipError("invalid or duplicate ownership identity")
        self.ids.add(value)

    def classify(self, node, by_path):
        path = node.path
        parts = path.split("/")
        prefixes = ["/".join(parts[:i]) for i in range(len(parts), 0, -1)]
        matches = []
        for base in prefixes:
            suffix = path[len(base):].lstrip("/")
            for side, rule in self.rules.get(base, ()):
                if rule.kind == "file" and suffix:
                    continue
                if suffix and any(_prefix(suffix, item) for item in
                                  (*rule.exclusions, *rule.overlays)):
                    matches.append({"mapping_id": rule.mapping_id,
                                    "classification": "excluded_or_overlay",
                                    "counterpart": None, "byte_equality": "not_checked",
                                    "specificity": len(base)})
                    continue
                counterpart = (rule.destination if side == "source" else rule.source)
                if suffix:
                    counterpart += "/" + suffix
                other = by_path.get(counterpart)
                parity = dict(rule.exceptions).get(suffix, rule.mode)
                classification = ("declared_source_owner" if side == "source"
                                  else "declared_staged_destination")
                matches.append({
                    "mapping_id": rule.mapping_id,
                    "classification": classification,
                    "counterpart": counterpart,
                    "byte_equality": ("counterpart_not_observed" if other is None else
                                      "equal" if node.sha256 == other.sha256 else "different"),
                    "parity_mode": parity,
                    "specificity": len(base),
                })
            for native in self.natives.get(base, ()):
                if native.kind == "file" and suffix:
                    continue
                matches.append({
                    "mapping_id": native.owner_id,
                    "classification": ("declared_native_residual" if native.residual_only
                                       else "declared_native_owner"),
                    "counterpart": None, "byte_equality": "not_applicable",
                    "specificity": len(base),
                })
        matches.sort(key=lambda item: (-item["specificity"], item["mapping_id"],
                                       item["classification"]))
        active = [m for m in matches if m["classification"] != "excluded_or_overlay"]
        top = active[0]["specificity"] if active else -1
        primary = [m for m in active if m["specificity"] == top]
        status = ("ambiguous_declaration" if len(primary) > 1 else
                  primary[0]["classification"] if primary else
                  "excluded_or_overlay" if matches else "unclassified")
        return {"path": path, "status": status, "declarations": matches,
                "owner_cutover_authorized": False}
