"""Offline verification for quorum-finality records.

Kept separate from the mutable finality ledger so portable verifiers need only the
record schema and hashing rules, not the live writer implementation.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any, Mapping

from core.transparency_finality import FINALITY_VERSION

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def finality_record_hash(raw: Mapping[str, Any]) -> str:
    payload = {
        "version": FINALITY_VERSION,
        "sequence": int(raw.get("sequence", 0)),
        "log_id": str(raw.get("log_id", "")),
        "tree_size": int(raw.get("tree_size", 0)),
        "root_sha256": str(raw.get("root_sha256", "")),
        "witness_quorum_sha256": str(raw.get("witness_quorum_sha256", "")),
        "witness_groups": tuple(str(x) for x in raw.get("witness_groups", ())),
        "finalized_at": str(raw.get("finalized_at", "")),
        "previous_sha256": str(raw.get("previous_sha256", "")),
    }
    return _sha(payload)


def verify_finality_record(raw: Mapping[str, Any]) -> bool:
    try:
        if int(raw.get("version", 0)) != FINALITY_VERSION:
            return False
        if int(raw.get("sequence", 0)) < 1 or int(raw.get("tree_size", 0)) < 1:
            return False
        if not str(raw.get("log_id", "")).strip():
            return False
        root = str(raw.get("root_sha256", "")); quorum = str(raw.get("witness_quorum_sha256", ""))
        claimed = str(raw.get("sha256", "")); previous = str(raw.get("previous_sha256", ""))
        if not _SHA256.fullmatch(root) or not _SHA256.fullmatch(quorum) or not _SHA256.fullmatch(claimed):
            return False
        if previous and not _SHA256.fullmatch(previous):
            return False
        groups = tuple(str(x).strip() for x in raw.get("witness_groups", ()) if str(x).strip())
        if not groups or len(set(groups)) != len(groups):
            return False
        return hmac.compare_digest(finality_record_hash(raw), claimed)
    except (TypeError, ValueError):
        return False
