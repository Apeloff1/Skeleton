"""Small deterministic BM25 evidence index with bounded top-k and stable ties."""
from collections import Counter
from math import log
from .documents import Document
from .tokenization import terms
from ..contracts.errors import ContractError

class EvidenceIndex:

    def __init__(self, documents: list[Document], *, max_docs: int=10000):
        if not isinstance(documents, list) or len(documents) > max_docs or len({d.id for d in documents}) != len(documents):
            raise ContractError('invalid/duplicate evidence corpus')
        self.docs = {d.id: d for d in documents}
        self.freq = {d.id: Counter(terms(d.text)) for d in documents}
        self.length = {k: sum(v.values()) for k, v in self.freq.items()}
        self.avg = sum(self.length.values()) / max(1, len(documents))
        self.df = Counter()
        for counts in self.freq.values():
            self.df.update(counts.keys())

    def query(self, text: str, *, top_k: int=5, minimum_score: float=0.0) -> list[dict]:
        if type(top_k) is not int or not 1 <= top_k <= 100:
            raise ContractError('invalid retrieval limit')
        q = set(terms(text, limit=3000))
        out = []
        n = len(self.docs)
        for id, counts in self.freq.items():
            score = 0.0
            for term in q & counts.keys():
                tf = counts[term]
                idf = log(1 + (n - self.df[term] + 0.5) / (self.df[term] + 0.5))
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * self.length[id] / max(1, self.avg)))
            if score > minimum_score:
                d = self.docs[id]
                out.append({'id': id, 'score': round(score, 7), 'sha256': d.sha256, 'source': d.source, 'trust': d.trust})
        return sorted(out, key=lambda x: (-x['score'], x['id']))[:top_k]
