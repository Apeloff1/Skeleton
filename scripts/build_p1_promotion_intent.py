#!/usr/bin/env python3
"""Build an exact-head PROM-03 intent for signing or explicit rejection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.contracts.p1_failure_journeys import P1FailureJourneyDecision
from skeleton.contracts.p1_promotion_decision import (
    P1PromotionDecisionError,
    P1PromotionIntent,
    PromotionDisposition,
)


ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = Path("machine/ai_p1_execution_map.json")


class PromotionIntentBuildError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionIntentBuildError(
            f"cannot read {path}"
        ) from exc


def _prom02(raw: Any) -> P1FailureJourneyDecision:
    if not isinstance(raw, dict):
        raise PromotionIntentBuildError(
            "PROM-02 bundle must be an object"
        )
    return P1FailureJourneyDecision(
        accepted=raw.get("accepted"),
        reasons=tuple(raw.get("reasons") or ()),
        repository=raw.get("repository"),
        commit_sha=raw.get("commit_sha"),
        prom01_bundle_digest=raw.get("prom01_bundle_digest"),
        prom01_promotion_ready=raw.get(
            "prom01_promotion_ready"
        ),
        required_families=tuple(
            raw.get("required_families") or ()
        ),
        required_journey_classes=tuple(
            raw.get("required_journey_classes") or ()
        ),
        observation_digests=tuple(
            raw.get("observation_digests") or ()
        ),
    )


def _deferred_refs(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, dict):
        raise PromotionIntentBuildError(
            "execution map must be an object"
        )
    scope = raw.get("scope_summary")
    if not isinstance(scope, dict):
        raise PromotionIntentBuildError(
            "execution map scope_summary missing"
        )
    refs = scope.get("deferred_volume_refs")
    count = scope.get("deferred_volume_count")
    if not isinstance(refs, list) or not refs:
        raise PromotionIntentBuildError(
            "deferred volume refs missing"
        )
    if count != len(refs):
        raise PromotionIntentBuildError(
            "deferred volume count/list mismatch"
        )
    return tuple(str(item) for item in refs)


def build_intent(
    *,
    repository: str,
    commit_sha: str,
    prom02_bundle_path: Path,
    disposition: PromotionDisposition,
    blockers: tuple[str, ...],
    signer_id: str | None,
    signer_type: str | None,
    signer_identity_digest: str | None,
    public_key_fingerprint: str | None,
) -> P1PromotionIntent:
    prom02 = _prom02(_load(prom02_bundle_path))
    if prom02.repository != repository:
        raise PromotionIntentBuildError(
            "PROM-02 repository mismatch"
        )
    if prom02.commit_sha != commit_sha:
        raise PromotionIntentBuildError(
            "PROM-02 exact-head mismatch"
        )
    return P1PromotionIntent(
        repository=repository,
        commit_sha=commit_sha,
        prom02_decision_digest=prom02.decision_digest,
        prom02_accepted=prom02.accepted,
        prom01_bundle_digest=prom02.prom01_bundle_digest,
        prom01_promotion_ready=prom02.prom01_promotion_ready,
        disposition=disposition,
        deferred_volume_refs=_deferred_refs(
            _load(ROOT / MAP_PATH)
        ),
        explicit_blockers=blockers,
        signer_id=signer_id,
        signer_type=signer_type,
        signer_identity_digest=signer_identity_digest,
        public_key_fingerprint=public_key_fingerprint,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument(
        "--prom02-bundle",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--disposition",
        choices=("promote", "reject"),
        required=True,
    )
    parser.add_argument(
        "--blocker",
        action="append",
        default=[],
    )
    parser.add_argument("--signer-id")
    parser.add_argument(
        "--signer-type",
        choices=("human", "ci", "service"),
    )
    parser.add_argument("--signer-identity-digest")
    parser.add_argument("--public-key-fingerprint")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--signing-payload-out",
        type=Path,
        required=True,
    )
    args = parser.parse_args(argv)

    try:
        intent = build_intent(
            repository=args.repository,
            commit_sha=args.commit_sha,
            prom02_bundle_path=args.prom02_bundle,
            disposition=PromotionDisposition(
                args.disposition
            ),
            blockers=tuple(args.blocker),
            signer_id=args.signer_id,
            signer_type=args.signer_type,
            signer_identity_digest=args.signer_identity_digest,
            public_key_fingerprint=args.public_key_fingerprint,
        )
    except (
        PromotionIntentBuildError,
        P1PromotionDecisionError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"P1 promotion intent: rejected: {exc}",
            file=sys.stderr,
        )
        return 1

    payload = {
        **intent.payload(),
        "intent_digest": intent.intent_digest,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.signing_payload_out.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.signing_payload_out.write_bytes(
        intent.signing_bytes()
    )
    print(
        "P1 promotion intent:",
        intent.disposition.value,
        intent.intent_digest,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
