from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchBranchPolicy:
    prefix: str
    owner: str
    production_gates: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.prefix or not self.owner:
            raise ValueError("branch policy identity required")
        if (
            len(self.production_gates) != len(set(self.production_gates))
            or any(not gate for gate in self.production_gates)
        ):
            raise ValueError("unique production gates required")


@dataclass(frozen=True)
class ResearchBranch:
    name: str
    parent_sha: str
    experiment_id: str
    owner: str

    def __post_init__(self) -> None:
        if not all((self.name, self.parent_sha, self.experiment_id, self.owner)):
            raise ValueError("complete research branch lineage required")


@dataclass(frozen=True)
class ResearchMergeCandidate:
    branch: ResearchBranch
    evidence_ids: tuple[str, ...]
    passed_gates: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.branch, ResearchBranch):
            raise ValueError("research branch required")
        if (
            len(self.evidence_ids) != len(set(self.evidence_ids))
            or any(not evidence for evidence in self.evidence_ids)
        ):
            raise ValueError("unique promotion evidence required")
        if (
            not isinstance(self.passed_gates, frozenset)
            or any(not gate for gate in self.passed_gates)
        ):
            raise ValueError("valid passed gates required")


@dataclass(frozen=True)
class ResearchPromotionReceipt:
    branch: str
    parent_sha: str
    experiment_id: str
    evidence_ids: tuple[str, ...]
    passed_gates: tuple[str, ...]


def promote_with_receipt(
    candidate: ResearchMergeCandidate,
    policy: ResearchBranchPolicy,
) -> ResearchPromotionReceipt:
    if not isinstance(candidate, ResearchMergeCandidate) or not isinstance(
        policy, ResearchBranchPolicy
    ):
        raise ValueError("research merge candidate and policy required")
    if (
        not candidate.branch.name.startswith(policy.prefix)
        or candidate.branch.owner != policy.owner
    ):
        raise PermissionError("research branch ownership policy")
    if not set(policy.production_gates).issubset(candidate.passed_gates):
        raise PermissionError("production gates not satisfied")
    if not candidate.evidence_ids:
        raise PermissionError("promotion evidence required")
    return ResearchPromotionReceipt(
        candidate.branch.name,
        candidate.branch.parent_sha,
        candidate.branch.experiment_id,
        candidate.evidence_ids,
        tuple(sorted(candidate.passed_gates)),
    )


def promote(candidate: ResearchMergeCandidate, policy: ResearchBranchPolicy) -> bool:
    promote_with_receipt(candidate, policy)
    return True
