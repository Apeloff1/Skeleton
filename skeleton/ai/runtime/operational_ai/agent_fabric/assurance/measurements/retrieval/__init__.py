"""Approved retrieval measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('precision_k', 'recall_k', 'mrr', 'ndcg_k', 'query_coverage', 'stale_source_fraction', 'chunk_overlap_ratio', 'evidence_bytes_per_hit', 'unique_document_fraction', 'source_revocation_rate', 'index_density', 'citation_identifier_validity'))
def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=import_module('skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval.'+name)
    return module.measure(observations)
