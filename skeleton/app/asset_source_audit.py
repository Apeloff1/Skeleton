"""Installed source-bound asset intake, including external dependency bytes.

Composes the canonical descriptor-anchored asset importer and manifest.
Only explicitly declared paths are admitted; this is not a full directory
inventory, content rights judgment, renderer execution or publication.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Sequence

from skeleton.game.build.asset_ingest.importers import AssetImportError
from skeleton.game.build.asset_ingest.manifest import AssetManifest, MAX_MANIFEST_JSON_BYTES
from skeleton.game.build.asset_ingest.pipeline import (
    MAX_IMPORT_FILES, MAX_EXTERNAL_TOTAL_BYTES, MAX_TOTAL_EXTERNAL_REFS,
    _import_from_fd, _root_fd, _parts, _regular,
)


SCHEMA = "skeleton.game.asset-source-audit.v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")


class AssetAuditError(ValueError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _digest(value):
    return sha256(_canonical(value)).hexdigest()


def _root_identity(fd):
    info = os.fstat(fd)
    return info.st_dev, info.st_ino


def audit_assets(root: str | Path, paths: Sequence[str], *, authorized: bool,
                 expected_catalog_sha256: str | None = None,
                 max_sidecar_bytes: int = MAX_EXTERNAL_TOTAL_BYTES):
    if authorized is not True:
        raise PermissionError("explicit local asset operator required")
    if type(paths) not in (list, tuple) or not 1 <= len(paths) <= MAX_IMPORT_FILES:
        raise AssetAuditError("invalid explicit asset path count")
    if not all(type(path) is str for path in paths) or len(set(paths)) != len(paths):
        raise AssetAuditError("invalid or duplicate asset paths")
    if type(max_sidecar_bytes) is not int or not 1 <= max_sidecar_bytes <= MAX_EXTERNAL_TOTAL_BYTES:
        raise AssetAuditError("invalid sidecar byte budget")
    if expected_catalog_sha256 is not None and (
        type(expected_catalog_sha256) is not str or not HEX.fullmatch(expected_catalog_sha256)
    ):
        raise AssetAuditError("invalid independent catalog pin")
    fd = None
    try:
        for path in paths:
            _parts(path)
        fd = _root_fd(root)
        identity = _root_identity(fd)
        result = _import_from_fd(fd, sorted(paths))
        if not result.ok:
            raise AssetAuditError("canonical importer rejected explicit asset set")
        manifest = result.manifest.to_dict()
        raw_manifest = result.manifest.to_json()
        if len(raw_manifest.encode("utf-8")) > MAX_MANIFEST_JSON_BYTES:
            raise AssetAuditError("asset manifest exceeds canonical restore bound")
        if AssetManifest.from_json(raw_manifest).to_dict() != manifest:
            raise AssetAuditError("canonical manifest round-trip differs")
        references = {}
        link_count = 0
        sidecar_size = 0
        for entry in result.manifest.entries:
            refs = entry.metadata.get("external_refs", [])
            for source in (entry.path, *entry.aliases):
                for target in refs:
                    link_count += 1
                    if link_count > MAX_TOTAL_EXTERNAL_REFS:
                        raise AssetAuditError("sidecar reference bound exceeded")
                    _parts(target)
                    relative = (PurePosixPath(source).parent / target).as_posix()
                    _parts(relative)
                    references.setdefault(relative, set()).add(source)
        observed = {}
        # Admit aggregate sidecar sizes before materializing sidecar bytes.
        for relative in sorted(references):
            size = _regular(fd, relative, read=False)
            if type(size) is not int or size < 0:
                raise AssetAuditError("sidecar size unknown")
            sidecar_size += size
            if sidecar_size > max_sidecar_bytes:
                raise AssetAuditError("sidecar read budget exceeded")
            observed[relative] = size
        sidecars = []
        actual_bytes = 0
        for relative in sorted(references):
            data = _regular(fd, relative, read=True)
            if type(data) is not bytes or len(data) != observed[relative]:
                raise AssetAuditError("sidecar size changed")
            actual_bytes += len(data)
            if actual_bytes > max_sidecar_bytes:
                raise AssetAuditError("sidecar actual byte budget exceeded")
            sidecars.append({"path": relative, "bytes": len(data),
                             "sha256": sha256(data).hexdigest(),
                             "referenced_by": sorted(references[relative])})
        # The source path must still resolve to the original held root.
        reopened = _root_fd(root)
        try:
            if _root_identity(reopened) != identity:
                raise AssetAuditError("asset root changed during source observation")
        finally:
            os.close(reopened)
        body = {
            "schema": SCHEMA,
            "asset_manifest": manifest,
            "requested_paths": sorted(paths),
            "sidecars": sidecars,
            "sidecar_reference_count": link_count,
            "sidecar_bytes": actual_bytes,
            "full_directory_verified": False,
            "atomic_source_snapshot": False,
            "native_import_executed": False,
            "rights_certified": False,
            "release_certified": False,
        }
        digest = _digest(body)
        if expected_catalog_sha256 is not None and not hmac.compare_digest(
            digest, expected_catalog_sha256,
        ):
            raise AssetAuditError("observed asset or sidecar catalog differs from independent pin")
        return {**body, "catalog_sha256": digest,
                "independent_pin_verified": expected_catalog_sha256 is not None}
    except (AssetImportError, OSError, TypeError, UnicodeError) as exc:
        raise AssetAuditError("asset source observation rejected") from exc
    finally:
        if fd is not None:
            os.close(fd)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inventory", "verify"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--asset", action="append", required=True)
    parser.add_argument("--expected-catalog-sha256")
    parser.add_argument("--max-sidecar-bytes", type=int, default=MAX_EXTERNAL_TOTAL_BYTES)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if (args.action == "verify") != (args.expected_catalog_sha256 is not None):
            raise AssetAuditError("verify requires an independent pin; inventory does not accept one")
        result = audit_assets(args.root, args.asset, authorized=args.trusted_local_operator,
                              expected_catalog_sha256=args.expected_catalog_sha256,
                              max_sidecar_bytes=args.max_sidecar_bytes)
    except (AssetAuditError, PermissionError, ValueError, OSError) as exc:
        print(json.dumps({"verified": False, "error": type(exc).__name__}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0
