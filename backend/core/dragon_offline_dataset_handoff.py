"""Explicit offline export-to-lead-graph handoff, never remote acquisition.

An operator supplies a finite manifest of independently obtained files and
expected inspection digests. Qualify every file before opening the graph.
Replay uses the existing exact-byte snapshot identity and page receipts.
Neither a crawler response nor a denied target may generate this manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from core.dragon_dataset_ingest import fingerprint, source_stream
from core.dragon_lead_ingest import inspect_export, ingest
from core.dragon_lead_graph import LeadGraph
from core.dragon_publisher_export_proof import PublisherExportProof
from core.dragon_corpus_runtime import _path

SCHEMA = "skeleton.dragon.offline-dataset-handoff.v1"
MAX_ITEMS = 16
MAX_MANIFEST_BYTES = 64 * 1024
MAX_BATCH_BYTES = 512 * 1024**3
HEX = re.compile(r"[a-f0-9]{64}\Z")
TARGET = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate handoff field")
        out[key] = value
    return out


def _finite(value):
    raise ValueError("nonfinite handoff number")


def _canonical_file(root, relative):
    if (not isinstance(relative, str) or not 1 <= len(relative) <= 512
            or "\\" in relative or ":" in relative or "\0" in relative
            or any(part in {"", ".", ".."} for part in relative.split("/"))):
        raise ValueError("handoff requires a safe relative local file")
    parsed = PurePosixPath(relative)
    if parsed.is_absolute():
        raise ValueError("absolute export path refused")
    path = root.joinpath(*parsed.parts)
    if path.resolve(strict=True) != path or not path.is_relative_to(root):
        raise ValueError("symlink or escaped export path")
    fingerprint(path)
    return path


def _manifest(path, *, expected_sha=None, publisher_proof=None):
    path = Path(path)
    witness = fingerprint(path)
    if witness[2] > MAX_MANIFEST_BYTES:
        raise ValueError("handoff manifest byte bound")
    with source_stream(path, None, witness) as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if not raw or len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("handoff manifest byte bound")
    raw_sha = hashlib.sha256(raw).hexdigest()
    if expected_sha is not None and raw_sha != expected_sha:
        raise ValueError("manifest SHA-256 differs")
    if publisher_proof is not None and not isinstance(publisher_proof, PublisherExportProof):
        raise ValueError("invalid publisher proof")
    proof_receipt = publisher_proof.verify(raw) if publisher_proof is not None else None
    try:
        doc = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_finite)
    except RecursionError as exc:
        raise ValueError("handoff manifest nesting") from exc
    if (not isinstance(doc, dict) or set(doc) != {"schema", "independent_export_acknowledged", "items"}
            or doc["schema"] != SCHEMA or doc["independent_export_acknowledged"] is not True
            or not isinstance(doc["items"], list) or not 1 <= len(doc["items"]) <= MAX_ITEMS):
        raise ValueError("explicit independent export manifest required")
    root = path.parent
    items, seen, total = [], set(), 0
    for entry in doc["items"]:
        if (not isinstance(entry, dict) or set(entry) != {
                "file", "format", "projection", "target", "rights_reference",
                "sha256", "inspection_digest", "grant_seconds"}
                or not isinstance(entry["target"], str) or not TARGET.fullmatch(entry["target"])
                or not isinstance(entry["rights_reference"], str)
                or not 1 <= len(entry["rights_reference"].strip()) <= 128
                or len(entry["rights_reference"]) > 128
                or type(entry["grant_seconds"]) is not int
                or not 900 <= entry["grant_seconds"] <= 7 * 86400
                or any(not isinstance(entry[k], str) or not HEX.fullmatch(entry[k])
                       for k in ("sha256", "inspection_digest"))):
            raise ValueError("invalid handoff entry")
        local = _canonical_file(root, entry["file"])
        if local == path:
            raise ValueError("manifest cannot be its own input")
        identity = (entry["target"], entry["inspection_digest"])
        if identity in seen:
            raise ValueError("duplicate handoff identity")
        seen.add(identity)
        total += fingerprint(local)[2]
        if total > MAX_BATCH_BYTES:
            raise ValueError("handoff total byte cap")
        items.append((dict(entry), local))
    return raw_sha, items, proof_receipt


def qualify_manifest(path, *, expected_manifest_sha, publisher_proof=None):
    """Return internal plan plus public aggregate; no writes or network."""
    if not isinstance(expected_manifest_sha, str) or not HEX.fullmatch(expected_manifest_sha):
        raise ValueError("exact manifest SHA-256 required")
    manifest_sha, items, proof_receipt = _manifest(path, expected_sha=expected_manifest_sha,
                                                      publisher_proof=publisher_proof)
    public = []
    for entry, local in items:
        receipt = inspect_export(local, entry["format"], entry["projection"],
                                 expected_sha=entry["sha256"])
        if receipt["inspection_digest"] != entry["inspection_digest"]:
            raise ValueError("entry inspection digest differs")
        public.append({"target": entry["target"], "input_sha256": receipt["input_sha256"],
                       "inspection_digest": receipt["inspection_digest"],
                       "rows": receipt["rows"], "pages": receipt["pages"]})
    final_sha, _, final_proof = _manifest(path, expected_sha=manifest_sha, publisher_proof=publisher_proof)
    if final_sha != manifest_sha or final_proof != proof_receipt:
        raise ValueError("manifest changed during qualification")
    return items, {"schema": SCHEMA, "manifest_sha256": manifest_sha,
                   "entries": public, "publisher_proof": proof_receipt,
                   "network_executed": False,
                   "graph_written": False, "license_verified": False,
                   "source_rights_verified": False}


def inspect_manifest(path, *, expected_manifest_sha, publisher_proof=None):
    return qualify_manifest(path, expected_manifest_sha=expected_manifest_sha,
                            publisher_proof=publisher_proof)[1]


def apply_manifest(path, *, expected_manifest_sha, scope, graph_factory, rights_acknowledged,
                   publisher_proof=None, authorize=None):
    """Explicit operator import; sequential independent canonical settlements.

    A failing later entry does not roll back a previously sealed snapshot.
    Retry the same exact manifest to replay already sealed snapshots.
    No scheduler or remote caller automatically invokes this import.
    """
    if rights_acknowledged is not True:
        raise ValueError("explicit independent metadata rights required")
    if (not isinstance(scope, dict) or set(scope) != {"tenant_id", "owner_id"}
            or any(not isinstance(v, str) or not 1 <= len(v.strip()) <= 256
                   for v in scope.values())):
        raise ValueError("explicit owner scope required")
    items, report = qualify_manifest(path, expected_manifest_sha=expected_manifest_sha,
                                      publisher_proof=publisher_proof)
    if authorize is not None: authorize()
    graph = graph_factory()
    settled = []
    for entry, local in items:
        if authorize is not None: authorize()
        receipt = ingest(graph, scope, path=local, format=entry["format"],
                         projection=entry["projection"], target=entry["target"],
                         rights_reference=entry["rights_reference"],
                         grant_seconds=entry["grant_seconds"], expected_sha=entry["sha256"],
                         expected_inspection=entry["inspection_digest"],
                         **({"authorize":authorize} if authorize is not None else {}))
        if (receipt["state"] != "sealed" or receipt["input_sha256"] != entry["sha256"]
                or receipt["inspection_digest"] != entry["inspection_digest"]):
            raise ValueError("canonical dataset settlement differs")
        if authorize is not None: authorize()
        settled.append({"target": entry["target"], "snapshot_id": receipt["snapshot_id"],
                        "inspection_digest": receipt["inspection_digest"],
                        "already_sealed": bool(receipt.get("already_sealed", False))})
    return {**report, "graph_written": None, "graph_apply_completed": True,
            "settlements": settled, "atomic_batch": False,
            "network_authorized": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--publisher-public-key", help="Raw Ed25519 public key (lowercase hex)")
    parser.add_argument("--publisher-key-sha256", help="Independently trusted raw public-key fingerprint")
    parser.add_argument("--publisher-signature", help="Detached manifest signature (lowercase hex)")
    parser.add_argument("--tenant")
    parser.add_argument("--owner")
    parser.add_argument("--acknowledge-metadata-rights", action="store_true")
    args = parser.parse_args(argv)
    path = args.manifest.expanduser().absolute()
    proof_fields = (args.publisher_public_key, args.publisher_key_sha256, args.publisher_signature)
    publisher_proof = None
    if any(x is not None for x in proof_fields):
        if not all(proof_fields):
            parser.error("signed export requires public key, independent key pin and detached signature")
        try:
            publisher_proof = PublisherExportProof(*proof_fields)
        except ValueError as exc:
            parser.error(str(exc))
    if not args.apply:
        if args.tenant is not None or args.owner is not None or args.acknowledge_metadata_rights:
            parser.error("inspection cannot include write authority")
        result = inspect_manifest(path, expected_manifest_sha=args.manifest_sha256,
                                  publisher_proof=publisher_proof)
    else:
        if not args.tenant or not args.owner or not args.acknowledge_metadata_rights:
            parser.error("apply requires explicit owner and metadata rights")
        scope = {"tenant_id": args.tenant, "owner_id": args.owner}
        result = apply_manifest(path, expected_manifest_sha=args.manifest_sha256, scope=scope,
                                graph_factory=lambda: LeadGraph(_path(scope=scope, create=False)),
                                rights_acknowledged=True, publisher_proof=publisher_proof)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
