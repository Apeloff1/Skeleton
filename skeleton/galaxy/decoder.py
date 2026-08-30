"""SOTA house decoder — reconstruct commitments from codec atoms.

Mirrors Memory-Decoder spirit (plug-in domain memory that does not
touch base weights) without importing papers: blend a retrieved
atom prior with the current stimulus tokens. Round-trip metric is
token-Jaccard of reconstructed dialect vs source dialect.

Safety-critical / low-confidence atoms pass through uncollapsed.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from skeleton.galaxy.atoms import Atom, jaccard, token_set
from skeleton.galaxy.codec import KnowledgeCodec, render_ccl


class KnowledgeDecoder:
    def __init__(self, *, blend: float = 0.35) -> None:
        self.blend = max(0.0, min(1.0, float(blend)))
        self.codec = KnowledgeCodec()

    def prior(self, query: str, bank: Iterable[Atom], *, k: int = 5) -> List[Atom]:
        q = token_set(query)
        scored = sorted(
            ((jaccard(q, a.tokens) * a.confidence, a) for a in bank if not a.superseded_by),
            key=lambda p: p[0],
            reverse=True,
        )
        return [a for s, a in scored[: max(1, k)] if s > 0]

    def decode(self, query: str, bank: Iterable[Atom], *, k: int = 5) -> Dict[str, Any]:
        hits = self.prior(query, bank, k=k)
        qtoks = token_set(query)
        prior_toks: List[str] = []
        for a in hits:
            prior_toks.extend(list(a.tokens))
        # conservative: keep query tokens, sprinkle prior
        keep = list(qtoks)
        extra = [t for t in prior_toks if t not in keep][: max(2, int(len(keep) * self.blend))]
        reconstructed = "house:" + " ".join(keep + extra)
        recover = jaccard(qtoks, token_set(reconstructed))
        critical = [a.to_dict() for a in hits if a.risk >= 0.6 or a.confidence < 0.4]
        return {
            "query": " ".join(qtoks[:16]),
            "reconstructed": reconstructed,
            "hits": [a.to_dict() for a in hits],
            "critical_passthrough": critical,
            "atom_recall": round(recover, 4),
            "blend": self.blend,
            "ccl": [render_ccl(a) for a in hits],
            "stored_prose": 0,
        }

    def roundtrip(self, stimulus: str, bank: Optional[List[Atom]] = None) -> Dict[str, Any]:
        atom = self.codec.encode(stimulus, kind="capture", brain="memory")
        pool = list(bank or []) + [atom]
        card = self.decode(stimulus, pool, k=3)
        card["source_id"] = atom.id
        card["roundtrip"] = card["atom_recall"] >= 0.5
        return card
