#!/usr/bin/env python3
"""Independently verify a detached Ed25519 PROM-03 intent signature."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from skeleton.contracts.p1_promotion_decision import (
    IndependentSignatureObservation,
    P1PromotionDecisionError,
    P1PromotionIntent,
)


ROOT = Path(__file__).resolve().parents[1]


class PromotionSignatureVerificationError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionSignatureVerificationError(
            f"cannot read {path}"
        ) from exc


def _run(
    args: list[str],
    *,
    input_bytes: bytes | None = None,
) -> bytes:
    try:
        completed = subprocess.run(
            args,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise PromotionSignatureVerificationError(
            f"cannot execute {args[0]}"
        ) from exc
    if completed.returncode != 0:
        raise PromotionSignatureVerificationError(
            completed.stderr.decode(
                "utf-8",
                errors="replace",
            ).strip()
            or f"{args[0]} exited {completed.returncode}"
        )
    return completed.stdout


def verify_signature(
    *,
    intent_json_path: Path,
    payload_path: Path,
    public_key_path: Path,
    signature_path: Path,
    signer_id: str,
    signer_type: str,
    signer_identity_digest: str,
    verifier_id: str,
) -> IndependentSignatureObservation:
    raw = _load(intent_json_path)
    intent = P1PromotionIntent.from_mapping(raw)
    claimed = raw.get("intent_digest")
    if claimed != intent.intent_digest:
        raise PromotionSignatureVerificationError(
            "intent digest mismatch"
        )
    payload = payload_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != intent.intent_digest:
        raise PromotionSignatureVerificationError(
            "signing payload digest mismatch"
        )
    if signer_id != intent.signer_id:
        raise PromotionSignatureVerificationError(
            "signer ID does not match intent"
        )
    if signer_type != intent.signer_type:
        raise PromotionSignatureVerificationError(
            "signer type does not match intent"
        )
    if signer_identity_digest != intent.signer_identity_digest:
        raise PromotionSignatureVerificationError(
            "signer identity digest does not match intent"
        )

    public_der = _run(
        [
            "openssl",
            "pkey",
            "-pubin",
            "-in",
            str(public_key_path),
            "-outform",
            "DER",
        ]
    )
    fingerprint = hashlib.sha256(public_der).hexdigest()
    if fingerprint != intent.public_key_fingerprint:
        raise PromotionSignatureVerificationError(
            "public key fingerprint mismatch"
        )

    _run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public_key_path),
            "-rawin",
            "-in",
            str(payload_path),
            "-sigfile",
            str(signature_path),
        ]
    )
    signature = signature_path.read_bytes()
    version = _run(["openssl", "version"]).strip()
    verifier_digest = hashlib.sha256(
        (ROOT / "scripts/verify_p1_promotion_signature.py").read_bytes()
        + b"\0"
        + version
    ).hexdigest()

    return IndependentSignatureObservation(
        repository=intent.repository,
        commit_sha=intent.commit_sha,
        intent_digest=intent.intent_digest,
        signer_id=signer_id,
        signer_type=signer_type,
        signer_identity_digest=signer_identity_digest,
        public_key_fingerprint=fingerprint,
        signature_digest=hashlib.sha256(signature).hexdigest(),
        verifier_id=verifier_id,
        verifier_digest=verifier_digest,
        signature_method="ed25519",
        verified=True,
        independent=(verifier_id != signer_id),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent-json", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--signer-id", required=True)
    parser.add_argument(
        "--signer-type",
        choices=("human", "ci", "service"),
        required=True,
    )
    parser.add_argument(
        "--signer-identity-digest",
        required=True,
    )
    parser.add_argument(
        "--verifier-id",
        default="openssl:ed25519-independent-verifier",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        observation = verify_signature(
            intent_json_path=args.intent_json,
            payload_path=args.payload,
            public_key_path=args.public_key,
            signature_path=args.signature,
            signer_id=args.signer_id,
            signer_type=args.signer_type,
            signer_identity_digest=args.signer_identity_digest,
            verifier_id=args.verifier_id,
        )
    except (
        PromotionSignatureVerificationError,
        P1PromotionDecisionError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"P1 promotion signature: rejected: {exc}",
            file=sys.stderr,
        )
        return 1

    payload = {
        **observation.payload(),
        "observation_digest": observation.observation_digest,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "P1 promotion signature: verified",
        observation.observation_digest,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
