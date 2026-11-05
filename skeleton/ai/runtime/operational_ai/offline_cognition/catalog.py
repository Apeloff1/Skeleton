"""Ordered inventory of 64 offline AI capability families and their categories."""
FAMILIES=(
    "tokenizer_bridge","sampler_control","stream_commit","checkpoint_adapter",
    "gpu_pressure","cpu_fallback","prompt_reservation","token_limit",
    "history_projection","system_policy","turn_packing","retrieval_insertion",
    "context_digest","context_compaction","overflow_hold","window_allocator",
    "consent_custody","recall_catalog","source_retraction","expiry_enforcement",
    "tenant_compartment","snapshot_plan","memory_dedup","provenance_refresh",
    "lexical_search","embedding_search","hybrid_fusion","passage_rerank",
    "source_attribution","citation_proof","chunk_partition","duplicate_filter",
    "task_decompose","dependency_plan","tool_proposal","tool_result_proof",
    "deadline_gate","retry_classification","operator_escalation","circuit_recovery",
    "capacity_admission","fair_queue","memory_guard","disk_guard",
    "token_quota","burst_control","preemption_hold","budget_reconcile",
    "benchmark_admission","finite_metrics","output_shape","refusal_quality",
    "source_quality","answer_grounding","hallucination_hold","review_ready",
    "install_receipt","boot_sequence","session_scope","native_replay",
    "outbox_delivery","hash_journal","cold_restart","release_hold",
)
def names():
    return FAMILIES
def contains(name):
    return name in FAMILIES
