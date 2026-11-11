"""Approved retrieval measurements and strict local lookup."""
ALLOWED=frozenset(('precision_k', 'recall_k', 'mrr', 'ndcg_k', 'query_coverage', 'stale_source_fraction', 'chunk_overlap_ratio', 'evidence_bytes_per_hit', 'unique_document_fraction', 'source_revocation_rate', 'index_density', 'citation_identifier_validity'))
def measure(name,observations):
    if type(name) is not str or name not in ALLOWED:
        raise ValueError('unknown measurement contract')
    if name == "precision_k":
        from . import precision_k as module
    elif name == "recall_k":
        from . import recall_k as module
    elif name == "mrr":
        from . import mrr as module
    elif name == "ndcg_k":
        from . import ndcg_k as module
    elif name == "query_coverage":
        from . import query_coverage as module
    elif name == "stale_source_fraction":
        from . import stale_source_fraction as module
    elif name == "chunk_overlap_ratio":
        from . import chunk_overlap_ratio as module
    elif name == "evidence_bytes_per_hit":
        from . import evidence_bytes_per_hit as module
    elif name == "unique_document_fraction":
        from . import unique_document_fraction as module
    elif name == "source_revocation_rate":
        from . import source_revocation_rate as module
    elif name == "index_density":
        from . import index_density as module
    elif name == "citation_identifier_validity":
        from . import citation_identifier_validity as module
    else:
        raise ValueError('unknown measurement contract')
    return module.measure(observations)
