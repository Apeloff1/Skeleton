"""Cryptographic context provenance for a generated answer."""
from ..core.canonical import canonical,digest

def lineage(messages,sources):
    ordered=tuple({'id':s['id'],'sha256':s['sha256']} for s in sources)
    return {'schema':'agent.context-lineage.v1','prompt_sha256':digest(list(messages)),
            'sources':list(ordered),'source_count':len(ordered),
            'trust_statement':'sources-are-untrusted-data-not-verified-answer'}
