"""Mission-ranked registry of twenty concrete crawler operations.

The registry is a discovery/inspection contract, not an executable agent
or authority grant. Functions are separately implemented in the sibling
quality, token-feed and scheduler modules. Registry order reflects expected
value to the native-model data mission, not order of execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module


@dataclass(frozen=True)
class MissionCapability:
    rank: int
    name: str
    module: str
    outcome: str
    fail_closed_on: str
    mission_stage: str


_SPECS = (
    ("encode_verified_tokens","dragon_mission_token_feed","Lossless real-tokenizer IDs and exact replay","invalid IDs or non-reversible decoding","native_llm"),
    ("require_training_grant","dragon_mission_quality","Version/purpose-bound positive training rights","missing or expired grant","acquisition"),
    ("curate_training_fragment","dragon_mission_token_feed","Licensed evidence fragment with exact original span","injection flags or low query relevance","evidence"),
    ("scan_untrusted_instructions","dragon_mission_quality","Quarantine of page-borne instruction attempts","bounded text/inspection","security"),
    ("mask_personal_data","dragon_mission_quality","Coordinate-stable personal data minimization","redaction overflow","security"),
    ("segment_passages","dragon_mission_quality","Deterministic span-preserving research chunks","segment budget exceeded","evidence"),
    ("pack_token_windows","dragon_mission_token_feed","Exact token-count context windows with overlap","invalid tokens or oversized window count","native_llm"),
    ("assign_dependency_splits","dragon_mission_token_feed","Leakage-safe experiment families by provenance","unknown/oversized dependency graph","training"),
    ("rank_query_passages","dragon_mission_quality","Topical evidence selection with reproducible offsets","invalid query or passage capacity","evidence"),
    ("near_duplicate_groups","dragon_mission_quality","Flag near-copied research pages beyond hash equality","hash integrity or pairwise scan capacity","evidence"),
    ("exact_revision_groups","dragon_mission_quality","Remove identical document copies across URLs","document hash mismatch","evidence"),
    ("compile_training_manifest","dragon_mission_token_feed","Auditable token IDs, splits, licenses and replay digest","unassigned source or split leakage","training"),
    ("rank_acquisition_candidates","dragon_mission_scheduler","Budget-aware expected information-gain prioritization","nonpublic URLs and oversize responses","acquisition"),
    ("allocate_host_dispatches","dragon_mission_scheduler","Round-robin host fairness and future ready-times","forged admission or cooldown violation","acquisition"),
    ("plan_adaptive_recrawls","dragon_mission_scheduler","Volatility/value-aware refresh schedule proposals","invalid targets or timing","acquisition"),
    ("locate_uncertainty_cues","dragon_mission_quality","Trace explicit negation and hedging for review","inspection budget overflow","evidence"),
    ("extract_citation_candidates","dragon_mission_quality","Bounded DOI and canonical URL candidates","citation capacity overflow","evidence"),
    ("measure_information_quality","dragon_mission_quality","Information density and boilerplate/repetition diagnostics","invalid quality thresholds","evidence"),
    ("balance_decade_windows","dragon_mission_token_feed","Decade-stratified training data sampling","invalid years/duplicate windows","training"),
    ("decide_mission_stop","dragon_mission_scheduler","Completion, uncertainty and novelty-plateau escalation","unresolved gaps or exhausted budgets","governance"),
)

CAPABILITY_CATALOG = tuple(
    MissionCapability(i+1, name, module, outcome, failure, stage)
    for i,(name,module,outcome,failure,stage) in enumerate(_SPECS)
)


def resolve_mission_capability(rank: int):
    """Resolve a known callable for authorized callers, no implicit execution."""
    if not isinstance(rank,int) or isinstance(rank,bool) or not 1<=rank<=len(CAPABILITY_CATALOG):
        raise ValueError("unknown mission capability rank")
    capability=CAPABILITY_CATALOG[rank-1]
    result=getattr(import_module("." + capability.module, __package__),capability.name)
    if not callable(result):
        raise RuntimeError("capability registry points to non-callable implementation")
    return result


def describe_mission_capabilities() -> tuple[MissionCapability, ...]:
    return CAPABILITY_CATALOG
