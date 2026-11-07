"""Approved retrieval measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('precision_k', 'recall_k', 'mrr', 'ndcg_k', 'query_coverage', 'stale_source_fraction', 'chunk_overlap_ratio', 'evidence_bytes_per_hit', 'unique_document_fraction', 'source_revocation_rate', 'index_density', 'citation_identifier_validity'))
_LOADERS = {
    "precision_k": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval.precision_k"),
    "recall_k": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval.recall_k"),
    "mrr": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval.mrr"),
    "ndcg_k": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval.ndcg_k"),
    "query_coverage": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval.query_coverage"),
    "stale_source_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval.stale_source_fraction"),
    "chunk_overlap_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval.chunk_overlap_ratio"),
    "evidence_bytes_per_hit": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval.evidence_bytes_per_hit"),
    "unique_document_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval.unique_document_fraction"),
    "source_revocation_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval.source_revocation_rate"),
    "index_density": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval.index_density"),
    "citation_identifier_validity": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval.citation_identifier_validity"),
}

def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=_LOADERS[name]()
    return module.measure(observations)
