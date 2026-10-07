#!/usr/bin/env python3
"""Build a non-authoritative exact-head P1-PROM-02 failure-journey bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.p1_failure_journeys import (
    FailureJourneyObservation,
    P1FailureJourneyError,
    qualify_p1_failure_journeys,
)
from skeleton.contracts.p1_terminal_evidence import (
    P1TerminalEvidenceDecision,
    TerminalTaskEvidence,
)
from scripts.check_p1_terminal_failure_journeys import (
    POLICY_PATH,
    ROOT,
    validate_repository,
)


class FailureJourneyBuildError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FailureJourneyBuildError(f"cannot read {path}") from exc


def _digest_paths(paths: list[str]) -> str:
    h = hashlib.sha256()
    for raw in paths:
        path = ROOT / raw
        if not path.is_file():
            raise FailureJourneyBuildError(
                f"missing failure-journey test path: {raw}"
            )
        h.update(raw.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def build_bundle(
    *,
    repository: str,
    commit_sha: str,
    prom01_bundle_path: Path,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    validate_repository(ROOT)
    policy = _load(ROOT / POLICY_PATH)
    prom01 = _load(prom01_bundle_path)
    if not isinstance(policy, dict):
        raise FailureJourneyBuildError("policy must be an object")
    if not isinstance(prom01, dict):
        raise FailureJourneyBuildError("PROM-01 bundle must be an object")
    if prom01.get("accepted") is not True:
        raise FailureJourneyBuildError("PROM-01 bundle is not accepted")
    if prom01.get("commit_sha") != commit_sha:
        raise FailureJourneyBuildError("PROM-01 exact-head mismatch")
    prom01_digest = prom01.get("decision_digest")
    if not isinstance(prom01_digest, str) or len(prom01_digest) != 64:
        raise FailureJourneyBuildError(
            "PROM-01 decision digest missing or malformed"
        )
    task_evidence_raw = prom01.get("task_evidence")
    if not isinstance(task_evidence_raw, list):
        raise FailureJourneyBuildError(
            "PROM-01 task_evidence missing or malformed"
        )
    prom01_decision = P1TerminalEvidenceDecision(
        accepted=prom01.get("accepted"),
        promotion_ready=prom01.get("promotion_ready"),
        reasons=tuple(prom01.get("reasons") or ()),
        promotion_blockers=tuple(
            prom01.get("promotion_blockers") or ()
        ),
        repository=prom01.get("repository"),
        commit_sha=prom01.get("commit_sha"),
        task_evidence=tuple(
            TerminalTaskEvidence(
                task_id=row["task_id"],
                accountability_id=row["accountability_id"],
                subject_digest=row["subject_digest"],
                receipt_digest=row["receipt_digest"],
                evidence_digest=row["evidence_digest"],
            )
            for row in task_evidence_raw
        ),
        maturity_report_digest=prom01.get(
            "maturity_report_digest"
        ),
        maturity_coverage_digest=prom01.get(
            "maturity_coverage_digest"
        ),
        primary_volume_count=prom01.get("primary_volume_count"),
        blocking_volume_keys=tuple(
            prom01.get("blocking_volume_keys") or ()
        ),
    )
    if prom01_decision.decision_digest != prom01_digest:
        raise FailureJourneyBuildError(
            "PROM-01 decision digest mismatch"
        )

    shared_paths = [
        "skeleton/contracts/p1_failure_journeys.py",
        "scripts/check_p1_terminal_failure_journeys.py",
        "scripts/build_p1_terminal_failure_journeys.py",
        "machine/p1_terminal_failure_journeys.json",
    ]
    observations: list[FailureJourneyObservation] = []
    serialized: list[dict[str, Any]] = []
    for row in policy["failure_families"]:
        family = str(row["family"])
        test_paths = list(row["test_paths"])
        test_digest = _digest_paths(test_paths)
        verifier_digest = _digest_paths([*shared_paths, *test_paths])
        observation = FailureJourneyObservation(
            family=family,
            repository=repository,
            commit_sha=commit_sha,
            verifier_id="github-actions:p1-terminal-failure-journeys",
            verifier_digest=verifier_digest,
            test_manifest_digest=test_digest,
            passed=True,
            independent=True,
            evidence_refs=(
                EvidenceRef(
                    source=f"p1:prom-02:exact-head:{family}",
                    digest=test_digest,
                    category="terminal_failure_journey",
                ),
            ),
        )
        observations.append(observation)
        serialized.append(
            {
                **observation.payload(),
                "observation_digest": observation.observation_digest,
                "test_paths": test_paths,
            }
        )

    decision = qualify_p1_failure_journeys(
        observations=tuple(observations),
        expected_repository=repository,
        expected_head=commit_sha,
        required_families=tuple(
            str(row["family"]) for row in policy["failure_families"]
        ),
        required_journey_classes=tuple(policy["journey_classes"]),
        journey_class_families={
            str(key): tuple(str(item) for item in value)
            for key, value in policy["journey_classes"].items()
        },
        prom01_bundle=prom01_decision,
    )
    if not decision.accepted:
        raise FailureJourneyBuildError(
            "failure-journey aggregation rejected: "
            + ",".join(decision.reasons)
        )
    evidence = decision.accepted_evidence_ref()
    payload = {
        **decision.payload(),
        "decision_digest": decision.decision_digest,
        "observation_count": len(observations),
        "observations": serialized,
    }
    refs = [
        {
            "source": evidence.source,
            "digest": evidence.digest,
            "category": evidence.category,
        }
    ]
    return payload, refs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--prom01-bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--refs-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload, refs = build_bundle(
            repository=args.repository,
            commit_sha=args.commit_sha,
            prom01_bundle_path=args.prom01_bundle,
        )
    except (
        FailureJourneyBuildError,
        P1FailureJourneyError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"P1 terminal failure journeys: rejected: {exc}",
            file=sys.stderr,
        )
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.refs_out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.refs_out.write_text(
        json.dumps(refs, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "P1 terminal failure journeys:",
        f"{payload['observation_count']} families;",
        f"digest={payload['decision_digest']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
