"""Bounded repair receipts for the existing authorized Builder Plane.

A receipt binds an already reviewed repair to its proposal, parent commit and
pull request. It carries custody evidence, not permission to execute or merge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Iterable, Mapping

from .builder_plane import (
    BuilderManifest, BuilderPlaneError, BuilderProposalReceipt,
    MAX_PROPOSAL_RECEIPT_BYTES, _canonical_digest, _fingerprint,
    _positive_int, _sha, _builder_path, compile_builder_proposal_receipt,
    validate_builder_proposal_receipt,
)
from .supervisor_runtime import canonical_json


def _repair_evidence(value: object, paths: tuple[str, ...]) -> bytes:
    from .build_repair import MAX_FOLLOWUP_CALLS, MAX_REPAIR_ROUNDS

    if not isinstance(value, dict):
        raise BuilderPlaneError("builder repair evidence must be an object")
    expected = {
        "followup_fingerprint", "architecture_fingerprint", "before_fingerprint",
        "after_fingerprint", "validation_fingerprint", "review_verdict",
        "review_rounds", "model_calls", "changed_paths", "fingerprint",
    }
    if set(value) != expected:
        raise BuilderPlaneError("builder repair evidence shape mismatch")
    for key in ("followup_fingerprint", "architecture_fingerprint", "before_fingerprint",
                "after_fingerprint", "validation_fingerprint", "fingerprint"):
        _fingerprint(value[key], label=f"builder repair {key}")
    if value["review_verdict"] != "accept":
        raise BuilderPlaneError("builder repair requires accepted review")
    if value["before_fingerprint"] == value["after_fingerprint"]:
        raise BuilderPlaneError("builder repair must change the candidate")
    _positive_int(value["review_rounds"], label="builder repair review rounds", maximum=MAX_REPAIR_ROUNDS)
    _positive_int(value["model_calls"], label="builder repair model calls", maximum=MAX_FOLLOWUP_CALLS)
    changed = value["changed_paths"]
    if not isinstance(changed, list) or len(changed) != len(paths):
        raise BuilderPlaneError("builder repair path mismatch")
    normalized = tuple(sorted(_builder_path(item) for item in changed))
    if normalized != paths:
        raise BuilderPlaneError("builder repair path mismatch")
    unsigned = {key: item for key, item in value.items() if key != "fingerprint"}
    if _canonical_digest(unsigned) != value["fingerprint"]:
        raise BuilderPlaneError("builder repair evidence fingerprint mismatch")
    return canonical_json(value)


@dataclass(frozen=True, slots=True)
class BuilderRepairReceipt:
    proposal: BuilderProposalReceipt
    pull_request: int
    parent_sha: str
    evidence_json: bytes = field(repr=False)
    version: int = 1

    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version != 1:
            raise BuilderPlaneError("unsupported builder repair receipt version")
        if not isinstance(self.proposal, BuilderProposalReceipt):
            raise BuilderPlaneError("builder repair requires a proposal receipt")
        _positive_int(self.pull_request, label="builder repair pull request", maximum=2_147_483_647)
        _sha(self.parent_sha)
        if self.parent_sha == self.proposal.base_sha:
            raise BuilderPlaneError("builder repair parent must be the PR head, not its base")
        if not isinstance(self.evidence_json, bytes) or len(self.evidence_json) > MAX_PROPOSAL_RECEIPT_BYTES:
            raise BuilderPlaneError("invalid builder repair evidence bytes")
        try:
            evidence = json.loads(self.evidence_json)
        except (ValueError, UnicodeError) as exc:
            raise BuilderPlaneError("invalid builder repair evidence JSON") from exc
        if _repair_evidence(evidence, self.proposal.paths) != self.evidence_json:
            raise BuilderPlaneError("builder repair evidence is not canonical")

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "version": self.version, "proposal": self.proposal.as_dict(),
            "pull_request": self.pull_request, "parent_sha": self.parent_sha,
            "repair_evidence": json.loads(self.evidence_json),
        }

    @property
    def receipt_digest(self) -> str:
        return _canonical_digest(self.unsigned_payload())

    def as_dict(self) -> dict[str, Any]:
        payload = {**self.unsigned_payload(), "receipt_digest": self.receipt_digest}
        if len(canonical_json(payload)) > MAX_PROPOSAL_RECEIPT_BYTES:
            raise BuilderPlaneError("builder repair receipt exceeds evidence budget")
        return payload

    @classmethod
    def from_payload(cls, value: object) -> BuilderRepairReceipt:
        if not isinstance(value, dict) or set(value) != {
            "version", "proposal", "pull_request", "parent_sha", "repair_evidence", "receipt_digest",
        }:
            raise BuilderPlaneError("builder repair receipt shape mismatch")
        proposal = BuilderProposalReceipt.from_payload(value["proposal"])
        receipt = cls(proposal, value["pull_request"], value["parent_sha"],
                      _repair_evidence(value["repair_evidence"], proposal.paths), value["version"])
        if value["receipt_digest"] != receipt.receipt_digest:
            raise BuilderPlaneError("builder repair receipt digest mismatch")
        receipt.as_dict()
        return receipt


def compile_builder_repair_receipt(
    manifest: BuilderManifest, *, pull_request: int, parent_sha: str,
    proposal_digest: str, branch: str, files: Iterable[Mapping[str, Any]],
    tests: Iterable[str], changed_lines: int, repair_evidence: Mapping[str, Any],
    followup_fingerprint: str | None = None,
) -> BuilderRepairReceipt:
    proposal = compile_builder_proposal_receipt(
        manifest, proposal_digest=proposal_digest, branch=branch, files=files,
        tests=tests, changed_lines=changed_lines,
    )
    evidence = _repair_evidence(repair_evidence, proposal.paths)
    if followup_fingerprint is not None:
        _fingerprint(followup_fingerprint, label="admitted followup fingerprint")
        if repair_evidence["followup_fingerprint"] != followup_fingerprint:
            raise BuilderPlaneError("builder repair admitted followup mismatch")
    receipt = BuilderRepairReceipt(proposal, pull_request, parent_sha, evidence)
    receipt.as_dict()
    return receipt


def validate_builder_repair_receipt(
    receipt: BuilderRepairReceipt, manifest: BuilderManifest, *,
    evidence: Mapping[str, Any] | None = None,
) -> None:
    if not isinstance(receipt, BuilderRepairReceipt):
        raise BuilderPlaneError("invalid builder repair receipt type")
    validate_builder_proposal_receipt(receipt.proposal, manifest, evidence=evidence)
    if evidence is None:
        return
    _positive_int(evidence.get("pull_request"), label="builder repair evidence pull request", maximum=2_147_483_647)
    expected = {
        "status": "pull-request-updated", "bot": "feature-builder",
        "pull_request": receipt.pull_request, "repair_parent_sha": receipt.parent_sha,
        "builder_repair_receipt": receipt.as_dict(),
    }
    for key, value in expected.items():
        if evidence.get(key) != value:
            raise BuilderPlaneError(f"builder repair evidence {key} mismatch")
