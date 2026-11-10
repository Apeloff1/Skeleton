"""Evidence-family collapse stress test for bounded Dragon research objectives.

This is a deterministic, read-only *sensitivity* computation. It compares:
  (1) selected source-record identities,
  (2) exact captured-content hashes, and
  (3) potential near-duplicate lexical relationships.

Near-duplicate edges are review leads, not established shared authorship.
The resulting collapsed group count is a scenario, **not** a lower bound on
true independence. Even a unique and dissimilar source may contain copied,
fabricated or unlicensed claims. No source can be auto-approved by this audit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import defaultdict
from urllib.parse import urlsplit

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, integer
from .objectives import ObjectivePlan
from .policy_matrix import SourcePolicyProjection
from .retrieval_fusion import RetrievalFusion
from .retrieval_robustness import RetrievalRobustnessAudit, analyze_retrieval_robustness
from .near_duplicate_audit import SourceSimilarityAudit, inspect_selected_source_similarity


@dataclass(frozen=True)
class ObjectiveFamilyStress:
    objective_id: str
    desired_attested_source_groups: int
    observed_selected_passages: int
    source_record_count: int
    exact_content_family_count: int
    possible_near_duplicate_cluster_count: int
    possible_collapse_from_exact_families: int
    unscored_similarity_source_count: int
    worst_observed_host_removal_cluster_count: int
    hypothetical_target_shortfall: int
    observed_host_count: int
    concern: str
    independent_evidence_attested: bool = False
    fact_verification_performed: bool = False


@dataclass(frozen=True)
class EvidenceFamilyStress:
    mandate_digest: str
    source_snapshot_digest: str
    policy_digest: str
    retrieval_digest: str
    objective_plan_digest: str
    robustness_digest: str
    similarity_digest: str
    source_records_observed: int
    exact_content_families_observed: int
    possible_near_duplicate_clusters: int
    objectives: tuple[ObjectiveFamilyStress, ...]
    objectives_with_potential_dependence: tuple[str, ...]
    objectives_with_similarity_holds: tuple[str, ...]
    limitations: tuple[str, ...]
    stress_digest: str
    independent_sources_certified: bool = False
    claim_correctness_verified: bool = False
    source_text_exported: bool = False
    model_or_network_invoked: bool = False
    human_review_required: bool = True


_LIMITATIONS = (
    "selected_evidence_only",
    "lexical_near_duplicate_is_not_proven_shared_origin",
    "near_duplicate_components_are_heuristic_collapse_scenarios",
    "different_content_can_still_copy_the_same_factual_claim",
    "unscored_sources_are_explicit_uncertainty_not_independence",
    "human_source_lineage_and_fact_review_are_mandatory",
)


def _clusters(
    ids: set[str],
    *,
    hashes: dict[str, str],
    edges: tuple[tuple[str, str], ...],
) -> int:
    parent = {item: item for item in ids}
    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item
    # Same captured bytes always count as one *text family*, even if
    # the near-duplicate scanner held the source due to its size.
    identical: dict[str, str] = {}
    for item in sorted(ids):
        identity = hashes[item]
        if identity in identical:
            a, b = find(item), find(identical[identity])
            if a != b:
                parent[max(a, b)] = min(a, b)
        else:
            identical[identity] = item
    for a, b in edges:
        if a in ids and b in ids:
            left, right = find(a), find(b)
            if left != right:
                parent[max(left, right)] = min(left, right)
    return len({find(x) for x in ids})


def stress_test_evidence_families(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    objective_plan: ObjectivePlan,
    policy: SourcePolicyProjection,
    retrieval: RetrievalFusion,
    robustness: RetrievalRobustnessAudit,
    similarity: SourceSimilarityAudit,
    *,
    now: float,
    authorized: bool,
    max_objectives: int = 8,
    max_sources: int = 32,
    max_candidate_pairs: int = 496,
) -> EvidenceFamilyStress:
    """Compare objective evidence with explicit exact/near-copy collapse holds."""
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_objectives, "family objective cap", 1, 32)
    integer(max_sources, "family selected source cap", 1, 32)
    integer(max_candidate_pairs, "family pair cap", 1, 496)
    if not isinstance(objective_plan, ObjectivePlan) or (
        not isinstance(policy, SourcePolicyProjection) or
        not isinstance(retrieval, RetrievalFusion) or
        not isinstance(robustness, RetrievalRobustnessAudit) or
        not isinstance(similarity, SourceSimilarityAudit)
    ):
        raise TypeError("typed policy, objectives and selected source evidence required")
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    revision = canonical["snapshot_digest"]
    if any(x != mandate.fingerprint for x in (
        objective_plan.mandate_digest, policy.mandate_digest,
        retrieval.mandate_digest, robustness.mandate_digest,
        similarity.mandate_digest,
    )):
        raise PermissionError("cross-mandate evidence-family stress denied")
    if any(x != revision for x in (
        policy.source_snapshot_digest, retrieval.source_snapshot_digest,
        robustness.source_snapshot_digest, similarity.source_snapshot_digest,
    )):
        raise PermissionError("stale source-family snapshot")
    if robustness.policy_digest != policy.policy_digest or (
        similarity.source_policy_digest != policy.policy_digest
    ) or robustness.retrieval_digest != retrieval.fusion_digest or (
        similarity.retrieval_digest != retrieval.fusion_digest
    ) or robustness.objective_plan_digest != objective_plan.plan_digest:
        raise PermissionError("source-family analysis uses inconsistent receipts")
    if (policy.publication_authorized or policy.training_authorized or
        retrieval.publication_authorized or robustness.verified_independence or
        similarity.lineage_verified or similarity.factual_independence_certified):
        raise PermissionError("family analysis cannot use elevated source authority")
    allowed = set(policy.allowed_source_ids)
    excluded = set(policy.excluded_source_ids)
    if allowed & excluded or allowed | excluded != set(canonical["sources"]):
        raise PermissionError("incomplete source-family policy scope")
    if tuple(sorted(excluded)) != retrieval.excluded_sources:
        raise PermissionError("source withdrawal changed since selection")
    goals = tuple(x.objective_id for x in objective_plan.objectives)
    if not goals or len(goals) > max_objectives or len(set(goals)) != len(goals):
        raise ValueError("bounded distinct objective campaign required")
    selected_by_goal: dict[str, set[str]] = {x: set() for x in goals}
    all_selected: set[str] = set()
    for passage in retrieval.results:
        if passage.source_id not in allowed:
            raise PermissionError("withheld source entered family evidence")
        source = canonical["sources"][passage.source_id]
        if source["content_hash"] != passage.source_hash or (
            source["canonical_url"] != passage.canonical_url
        ):
            raise PermissionError("family source hash/URL mismatch")
        if not passage.matched_objective_ids or (
            set(passage.matched_objective_ids) - set(goals)
        ):
            raise PermissionError("family hit references unauthorized objective")
        all_selected.add(passage.source_id)
        for goal in passage.matched_objective_ids:
            selected_by_goal[goal].add(passage.source_id)
    if len(all_selected) > max_sources or len(similarity.similar_pairs) > max_candidate_pairs:
        raise ValueError("selected source or pair count exceeds family bounds")
    # A valid-looking digest string is not evidence of an authentic
    # provenance audit. Re-run each pure bounded source projection from the
    # canonical snapshot before allowing their relationship graph to affect
    # the objective family's count. This also rejects a forged report with
    # a recomputed self-consistent digest.
    canonical_robustness = analyze_retrieval_robustness(
        mandate, canonical, objective_plan, policy, retrieval,
        now=now, authorized=authorized,
    )
    if canonical_robustness != robustness:
        raise PermissionError("family stress received altered robustness provenance")
    canonical_similarity = inspect_selected_source_similarity(
        mandate, canonical, policy, retrieval,
        now=now, authorized=authorized,
    )
    if canonical_similarity != similarity:
        raise PermissionError("family stress received altered similarity provenance")
    if set(similarity.considered_source_ids) != all_selected:
        raise PermissionError("similarity did not inspect selected source identities")
    if set(similarity.compared_source_ids) | set(similarity.held_source_ids) != all_selected or (
        set(similarity.compared_source_ids) & set(similarity.held_source_ids)
    ):
        raise PermissionError("similarity omitted or duplicated source identity")
    hashes = {x: canonical["sources"][x]["content_hash"] for x in all_selected}
    hosts = {
        x: urlsplit(canonical["sources"][x]["canonical_url"]).hostname
        for x in all_selected
    }
    if any(x not in mandate.scope.allowed_hosts for x in hosts.values()):
        raise PermissionError("family selected source left approved host universe")
    if robustness.selected_sources != len(all_selected):
        raise PermissionError("robustness and selected identities disagree")
    edges = []
    for pair in similarity.similar_pairs:
        a, b = pair.left_source_id, pair.right_source_id
        if (a not in all_selected or b not in all_selected or
                a == b or hashes[a] != pair.left_content_hash or
                hashes[b] != pair.right_content_hash or
                hosts[a] != pair.left_host or hosts[b] != pair.right_host):
            raise PermissionError("similarity pair references foreign source")
        edges.append((a, b))
    if len(edges) != len(set(edges)):
        raise ValueError("duplicated source-family similarity edges")
    results = []
    flagged = []
    held_goals = []
    for goal in objective_plan.objectives:
        ids = selected_by_goal[goal.objective_id]
        records = len(ids)
        exact = len({hashes[x] for x in ids})
        candidate_components = _clusters(ids, hashes=hashes, edges=tuple(edges))
        unscored = len(ids & set(similarity.held_source_ids))
        hosts_for_goal = {hosts[x] for x in ids}
        worst = min((
            _clusters(
                {x for x in ids if hosts[x] != host},
                hashes=hashes, edges=tuple(edges),
            ) for host in hosts_for_goal
        ), default=0)
        if not records:
            concern = "no_selected_source_evidence"
        elif unscored:
            concern = "similarity_review_incomplete"
        elif candidate_components < exact:
            concern = "possible_near_duplicate_dependence"
        elif exact < records:
            concern = "exact_content_reuse"
        elif len(hosts_for_goal) == 1:
            concern = "single_host_evidence"
        else:
            concern = "no_collapse_detected_not_independence_proof"
        if candidate_components < records or unscored or not records:
            flagged.append(goal.objective_id)
        if unscored:
            held_goals.append(goal.objective_id)
        results.append(ObjectiveFamilyStress(
            objective_id=goal.objective_id,
            desired_attested_source_groups=goal.minimum_attested_groups,
            observed_selected_passages=sum(
                goal.objective_id in row.matched_objective_ids
                for row in retrieval.results
            ),
            source_record_count=records,
            exact_content_family_count=exact,
            possible_near_duplicate_cluster_count=candidate_components,
            possible_collapse_from_exact_families=exact - candidate_components,
            unscored_similarity_source_count=unscored,
            worst_observed_host_removal_cluster_count=worst,
            hypothetical_target_shortfall=max(
                0, goal.minimum_attested_groups - candidate_components,
            ),
            observed_host_count=len(hosts_for_goal),
            concern=concern,
        ))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": revision,
        "policy": policy.policy_digest,
        "retrieval": retrieval.fusion_digest,
        "objectives": objective_plan.plan_digest,
        "robustness": robustness.audit_digest,
        "similarity": similarity.audit_digest,
        "observed_ids": tuple(sorted(all_selected)),
        "exact_families": len(set(hashes.values())),
        "scenarios": [asdict(x) for x in results],
        "flagged": tuple(sorted(flagged)),
        "held": tuple(sorted(held_goals)),
        "limits": (max_objectives, max_sources, max_candidate_pairs),
        "caveats": _LIMITATIONS,
    }
    return EvidenceFamilyStress(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=revision,
        policy_digest=policy.policy_digest,
        retrieval_digest=retrieval.fusion_digest,
        objective_plan_digest=objective_plan.plan_digest,
        robustness_digest=robustness.audit_digest,
        similarity_digest=similarity.audit_digest,
        source_records_observed=len(all_selected),
        exact_content_families_observed=len(set(hashes.values())),
        possible_near_duplicate_clusters=_clusters(
            all_selected, hashes=hashes, edges=tuple(edges),
        ),
        objectives=tuple(results),
        objectives_with_potential_dependence=tuple(sorted(flagged)),
        objectives_with_similarity_holds=tuple(sorted(held_goals)),
        limitations=_LIMITATIONS,
        stress_digest=digest(payload),
    )
