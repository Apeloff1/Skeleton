"""Offline, provenance-pinned expansion of the existing Dragon source catalogue.

An export is a candidate locator list, never a crawl grant. This module has
no HTTP client, credential access, scheduler, or new persistence authority.
An operator reviews the resulting catalogue and receipt before packaging it.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .source_navigation import (
    Catalogue, REGISTRY_PATH, MAX_BYTES, MAX_REGISTRY, FAMILIES, KINDS, _root,
)

BASELINE = 382
TARGET_10X = BASELINE * 10
TARGET_100X = BASELINE * 100
MAX_EXPORT_BYTES = 32 * 1024 * 1024
MAX_LINE_BYTES = 4096
MAX_EXPORT_ROWS = 200_000
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
ROW_KEYS = {"name", "url", "family", "kind", "tags"}


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _row(value):
    if (not isinstance(value, dict) or set(value) != ROW_KEYS
            or not isinstance(value["family"], str)
            or value["family"] not in FAMILIES
            or not isinstance(value["kind"], str)
            or value["kind"] not in KINDS):
        raise ValueError("source export row schema")
    for key, bound in (("name", 100), ("tags", 256)):
        text = value[key]
        if (not isinstance(text, str) or not text.strip() or len(text) > bound
                or any(ord(c) < 32 or ord(c) == 127 for c in text)):
            raise ValueError("source export text bound")
    host, path = _root(value["url"])
    # GitHub repositories are case-insensitive; ordinary HTTP paths are not.
    if host == "github.com" and len(path.split("/")) == 3:
        path = path.casefold()
    return (host, path)


def _bytes(path, maximum):
    with Path(path).open("rb") as file:
        raw = file.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("source input byte bound")
    return raw


def expand(base_path, export_path, *, expected_base_sha256,
           expected_export_sha256, publisher, rights_reference, minimum=0):
    """Build catalogue bytes plus manifest; any invalid or changed input fails.

    The publisher and rights reference are *operator assertions* about the
    exported metadata, not adjudications of copyright or access permission.
    Only explicit URLs in the supplied export are used. No URL templates,
    guessed IDs, links fabricated from titles, or hidden HTTP requests.
    """
    if (not isinstance(expected_base_sha256, str)
            or not SHA256.fullmatch(expected_base_sha256)
            or not isinstance(expected_export_sha256, str)
            or not SHA256.fullmatch(expected_export_sha256)):
        raise ValueError("source input digest expected")
    if type(minimum) is not int or not 0 <= minimum <= MAX_REGISTRY:
        raise ValueError("minimum catalogue count")
    _root(publisher)
    if (not isinstance(rights_reference, str) or not rights_reference.strip()
            or len(rights_reference) > 512
            or any(ord(c) < 32 or ord(c) == 127 for c in rights_reference)):
        raise ValueError("explicit metadata rights reference required")
    raw = _bytes(base_path, MAX_BYTES)
    if _hash(raw) != expected_base_sha256:
        raise ValueError("base catalogue digest mismatch")
    base = Catalogue(raw)
    data = json.loads(raw, object_pairs_hook=_unique_pairs)
    seen = {}
    for record in data["sources"]:
        key = _row(record)
        if key in seen:
            raise ValueError("base has duplicate canonical roots")
        seen[key] = record
    additions, new_keys = [], set()
    conflicts, duplicates, existing = 0, 0, 0
    consumed = 0
    digest = hashlib.sha256()
    with Path(export_path).open("rb") as source:
        while True:
            line = source.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            consumed += len(line)
            digest.update(line)
            if consumed > MAX_EXPORT_BYTES or len(line) > MAX_LINE_BYTES:
                raise ValueError("source export byte bound")
            if not line.strip():
                continue
            if len(additions) + conflicts + duplicates + existing >= MAX_EXPORT_ROWS:
                raise ValueError("source export row bound")
            record = json.loads(line, object_pairs_hook=_unique_pairs)
            key = _row(record)
            if key in seen:
                if seen[key] != record:
                    conflicts += 1
                elif key in new_keys:
                    duplicates += 1
                else:
                    existing += 1
                continue
            if len(seen) >= MAX_REGISTRY:
                raise ValueError("source catalogue capacity exceeded")
            seen[key] = record
            new_keys.add(key)
            additions.append(record)
    if digest.hexdigest() != expected_export_sha256:
        raise ValueError("export digest mismatch")
    # Never silently replace curated metadata when provenance conflicts.
    # Critical admission remains a deliberate review operation.
    data["sources"].extend(sorted(additions, key=lambda row: _row(row)))
    output = json.dumps(data, ensure_ascii=True, separators=(",", ":"),
                        allow_nan=False).encode("ascii") + b"\n"
    result = Catalogue(output)
    if len(result.rows) < minimum:
        raise ValueError("minimum populated source count not reached")
    receipt = {
        "schema": "skeleton.dragon.source-catalogue-expansion.v1",
        "publisher_locator": publisher,
        "operator_metadata_rights_reference": rights_reference,
        "base_sha256": expected_base_sha256,
        "export_sha256": expected_export_sha256,
        "output_sha256": _hash(output),
        "source_registry_digest": result.digest,
        "prior_sources": len(base.rows),
        "added_sources": len(additions),
        "sources": len(result.rows),
        "distinct_hosts": result.summary()["hosts"],
        "added_families": dict(sorted(Counter(r["family"] for r in additions).items())),
        "duplicate_export_rows": duplicates,
        "existing_rows": existing,
        "conflicting_metadata_held": conflicts,
        "target_10x": TARGET_10X,
        "target_100x": TARGET_100X,
        "target_100x_reached": len(result.rows) >= TARGET_100X,
        "rights_verified": False,
        "access_verified": False,
        "network_authorized": False,
    }
    return output, receipt


def _publish_new(path, content):
    """No clobber; publish a complete same-directory fsynced file."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".dragon-catalogue-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--base-sha256", required=True)
    parser.add_argument("--export-sha256", required=True)
    parser.add_argument("--publisher", required=True)
    parser.add_argument("--rights-reference", required=True)
    parser.add_argument("--minimum", type=int, default=TARGET_100X)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.resolve() == args.receipt.resolve():
        parser.error("output and receipt must be distinct")
    if args.output.exists() or args.receipt.exists():
        parser.error("refuse existing output or receipt")
    output, receipt = expand(
        args.base, args.export, expected_base_sha256=args.base_sha256,
        expected_export_sha256=args.export_sha256, publisher=args.publisher,
        rights_reference=args.rights_reference, minimum=args.minimum,
    )
    # Publish the receipt last; consumers require both files and compare hashes.
    _publish_new(args.output, output)
    _publish_new(args.receipt, json.dumps(receipt, sort_keys=True,
                 indent=2).encode("utf-8") + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
