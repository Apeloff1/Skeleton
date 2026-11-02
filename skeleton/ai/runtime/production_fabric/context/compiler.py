"""Bounded evidence projection; untrusted text is explicitly quoted as data."""
from ..contracts.errors import ContractError
from .index import EvidenceIndex
from .tokenization import rough_tokens

def compile_context(index: EvidenceIndex, query: str, *, budget: int=4096, top_k: int=8) -> dict:
    if type(budget) is not int or not 128 <= budget <= 100000:
        raise ContractError('invalid context budget')
    retained = []
    spent = 0
    for hit in index.query(query, top_k=top_k):
        d = index.docs[hit['id']]
        header = f'[EVIDENCE id={d.id} sha256={d.sha256} trust={d.trust} source={d.source}]'
        passage = d.text[:min(len(d.text), 12000)]
        tokens = rough_tokens(header) + rough_tokens(passage)
        if spent + tokens > budget:
            continue
        retained.append({'id': d.id, 'source': d.source, 'sha256': d.sha256, 'trust': d.trust, 'passage': passage, 'instruction_authority': False})
        spent += tokens
    return {'query': query, 'evidence': retained, 'estimated_tokens': spent, 'token_budget': budget, 'trust_policy': 'evidence-is-not-instruction'}
