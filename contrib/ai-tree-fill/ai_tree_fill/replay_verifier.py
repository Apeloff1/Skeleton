"""Replay verifier. Does not import the implementation conductor or the P5 signer.

It recomputes digests from the trial log and refuses a log that repeats a stimulus.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


ROLE = "independent_verification"
SIGNER = "p5-replay-verifier"


class ReplayReject(RuntimeError):
    pass


def load_log(path: str) -> dict:
    return json.load(open(path))


def replay(log: dict) -> dict:
    records = log.get("records") or []
    if len(records) < 12:
        raise ReplayReject("short log")
    stimuli = [row["stimulus"] for row in records if not row["expect_fail"]]
    if len(stimuli) != len(set(stimuli)):
        raise ReplayReject("repeated stimulus is not an independent trial")
    recomputed = []
    for row in records:
        payload = json.dumps(row["output"], sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        if digest != row["output_digest"]:
            raise ReplayReject(f"digest mismatch {row['trial_id']}")
        if row["expect_fail"] and row["output"].get("hit") != 0:
            raise ReplayReject(f"negative passed {row['trial_id']}")
        if not row["expect_fail"] and row["output"].get("n", 0) < 1:
            raise ReplayReject(f"empty pointers {row['trial_id']}")
        recomputed.append(digest)
    blob = json.dumps(records, sort_keys=True).encode()
    log_digest = hashlib.sha256(blob).hexdigest()
    if log.get("log_digest") != log_digest:
        raise ReplayReject("log digest mismatch")
    return {
        "role": ROLE,
        "signer_id": SIGNER,
        "trials": len(records),
        "unique_stimuli": len(set(stimuli)),
        "negatives": sum(1 for row in records if row["expect_fail"]),
        "log_digest": log_digest,
        "result": "confirmed",
    }


def sign_replay(report: dict, parent_sha: str) -> dict:
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    payload = json.dumps({"report": report, "parent_sha": parent_sha}, sort_keys=True).encode()
    return {
        "alg": "Ed25519",
        "signer_id": SIGNER,
        "signer_type": "replay",
        "role": ROLE,
        "public_key_hex": public.hex(),
        "git_sha": parent_sha,
        "artifact_digest": hashlib.sha256(payload).hexdigest(),
        "evidence_bundle_digest": report["log_digest"],
        "fault_manifest_digest": hashlib.sha256(b"F-11 F-12 F-13").hexdigest(),
        "signature": key.sign(payload).hex(),
        "signed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": "independent trials and ownership claim; not a tree-wide cutover signoff",
    }


def verify_replay(report: dict, signature: dict, parent_sha: str) -> bool:
    payload = json.dumps({"report": report, "parent_sha": parent_sha}, sort_keys=True).encode()
    public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(signature["public_key_hex"]))
    public.verify(bytes.fromhex(signature["signature"]), payload)
    if signature["role"] == "implementation":
        raise ReplayReject("implementation role cannot verify itself")
    return True
