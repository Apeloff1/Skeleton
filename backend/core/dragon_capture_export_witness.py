"""Read-only bridge from a witnessed capture hash to independent local data.

The crawler deliberately does not retain response bodies. An operator may
compare an independently supplied file with a capture's recorded raw-body
digest. Matching bytes are not an entitlement, grant, signature, license,
or automatic approval to import. No network or storage write occurs here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "skeleton.dragon.capture-export-witness.v1"
HASH = re.compile(r"[a-f0-9]{64}\Z")
_FIELDS = {"schema", "session_id", "session_version", "source_id", "snapshot_digest",
           "intent_digest", "source_policy_version", "raw_body_sha256",
           "raw_bytes_retained", "dataset_import_authorized", "network_authorized"}
_FLAGS = ("raw_bytes_retained", "dataset_import_authorized", "network_authorized")


def _sha(value):
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def _digest(body):
    raw = json.dumps(body, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
                     allow_nan=False).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def build_witness(*, session_id, session_version, source_id, snapshot_digest,
                  intent_digest, source_policy_version, raw_body_sha256):
    body = {"schema": SCHEMA, "session_id": session_id,
            "session_version": session_version, "source_id": source_id,
            "snapshot_digest": snapshot_digest, "intent_digest": intent_digest,
            "source_policy_version": source_policy_version, "raw_body_sha256": raw_body_sha256,
            **dict.fromkeys(_FLAGS, False)}
    value = {**body, "witness_digest": _digest(body)}
    validate_witness(value)
    return value


def validate_witness(value):
    if (not isinstance(value, dict) or set(value) != _FIELDS | {"witness_digest"}
            or value["schema"] != SCHEMA
            or not isinstance(value["session_id"], str)
            or not 1 <= len(value["session_id"]) <= 128
            or any(ord(c) < 32 or ord(c) > 126 for c in value["session_id"])
            or type(value["session_version"]) is not int or not 1 <= value["session_version"] < 2**53
            or type(value["source_policy_version"]) is not int
            or not 0 <= value["source_policy_version"] <= 2**31 - 1
            or any(not _sha(value[k]) for k in ("source_id", "snapshot_digest",
                  "intent_digest", "raw_body_sha256", "witness_digest"))
            or any(value[k] is not False for k in _FLAGS)):
        raise ValueError("invalid capture export witness")
    body = {k: value[k] for k in _FIELDS}
    if _digest(body) != value["witness_digest"]:
        raise ValueError("capture export witness digest differs")
    return dict(value)


def inspect_independent_export(path, *, witness, expected_witness_digest, member=None):
    from core.dragon_dataset_ingest import inspect_dataset

    value = validate_witness(witness)
    if not _sha(expected_witness_digest) or expected_witness_digest != value["witness_digest"]:
        raise ValueError("explicit capture witness digest differs")
    # Existing versioned importer validates raw container hash before
    # decoding or projecting any records. Never substitute text encoding.
    result = inspect_dataset(Path(path), member, expected_sha=value["raw_body_sha256"])
    return {**result, "capture_witness_digest": value["witness_digest"],
            "capture_raw_hash_matched": True, "live_capture_authority_rechecked": False,
            "witness_signature_verified": False, "dataset_import_authorized": False,
            "source_rights_verified": False}


def main(argv=None):
    from core.dragon_mongo_receipt import _read_json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True,
                        help="Private canonical JSON receipt copied from the authorized API")
    parser.add_argument("--witness-digest", required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--member")
    args = parser.parse_args(argv)
    report = inspect_independent_export(args.export.expanduser().absolute(),
                witness=_read_json(args.receipt.expanduser().absolute()),
                expected_witness_digest=args.witness_digest, member=args.member)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
