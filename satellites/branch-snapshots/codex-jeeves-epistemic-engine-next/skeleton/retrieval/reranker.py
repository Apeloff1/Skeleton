"""
Skeleton Retrieval — Feature-based re-ranking

Provides:
- FeatureReranker: Re-rank retrieval results using learned features
- FeatureExtractor: Extract relevance features from query-document pairs
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import EventBus


@dataclass
class RerankScore:
    """A re-ranking score with feature breakdown."""
    document_id: str
    original_score: float
    reranked_score: float
    features: Dict[str, float] = field(default_factory=dict)


class FeatureExtractor:
    """Extract relevance features from query-document pairs."""

    @staticmethod
    def extract(query: str, document: str) -> Dict[str, float]:
        """Extract features from a query-document pair.
        
        Features:
        - term_overlap: Jaccard similarity of terms
        - phrase_match: Exact phrase match count
        - length_ratio: Document length relative to query
        - position: Average position of query terms in document
        """
        query_terms = set(query.lower().split())
        doc_terms = document.lower().split()
        doc_set = set(doc_terms)
        
        # Term overlap (Jaccard)
        if query_terms and doc_set:
            overlap = len(query_terms & doc_set) / len(query_terms | doc_set)
        else:
            overlap = 0.0
        
        # Phrase matches
        phrase_count = sum(1 for i in range(len(doc_terms)) 
                          if " ".join(doc_terms[i:i+len(query_terms)]) == query.lower())
        
        # Length ratio (prefer medium-length documents)
        query_len = len(query_terms)
        doc_len = len(doc_terms)
        if query_len > 0:
            length_ratio = min(doc_len / query_len, 5.0) / 5.0  # Normalize, cap at 5x
        else:
            length_ratio = 0.5
        
        # Position feature (earlier is better)
        positions = []
        for term in query_terms:
            if term in doc_terms:
                positions.append(doc_terms.index(term) / max(len(doc_terms), 1))
        position = 1.0 - (sum(positions) / max(len(positions), 1)) if positions else 0.0
        
        return {
            "term_overlap": overlap,
            "phrase_match": min(phrase_count / 3.0, 1.0),  # Normalize
            "length_ratio": length_ratio,
            "position": position,
        }


class FeatureReranker:
    """Re-rank results using feature-based scoring.
    
    Learns feature weights from feedback and applies them
    to re-score retrieval results.
    """

    def __init__(self, bus: Optional[EventBus] = None):
        self._weights: Dict[str, float] = {
            "term_overlap": 1.0,
            "phrase_match": 1.5,
            "length_ratio": 0.3,
            "position": 0.8,
        }
        self._bus = bus
        self._stats = {"queries": 0, "reranked": 0, "feedback": 0}

    def rerank(self, query: str, results: List[Any], top_k: int = 10) -> List[Any]:
        """Re-rank results using extracted features.
        
        Args:
            query: The original query string
            results: List of result objects with 'content' and 'score' attributes
            top_k: Number of results to return
            
        Returns:
            Re-ranked list of results
        """
        self._stats["queries"] += 1
        
        scored = []
        for result in results:
            content = getattr(result, 'content', str(result))
            original_score = getattr(result, 'score', 0.5)
            
            features = FeatureExtractor.extract(query, content)
            
            # Compute weighted score
            feature_score = sum(
                features.get(f, 0) * w 
                for f, w in self._weights.items()
            )
            
            # Blend original and feature scores
            reranked_score = original_score * 0.6 + feature_score * 0.4
            
            scored.append((reranked_score, result, features))
        
        # Sort by reranked score
        scored.sort(key=lambda x: x[0], reverse=True)
        self._stats["reranked"] += len(scored)
        
        return [result for _, result, _ in scored[:top_k]]

    def record_feedback(self, query: str, document_id: str, relevant: bool) -> None:
        """Record user feedback to adjust weights.
        
        Simple online learning: boost weights for features
        that correlate with relevance.
        """
        self._stats["feedback"] += 1
        
        # In a real implementation, this would update weights
        # based on gradient descent or perceptron learning
        if relevant:
            # Slightly boost all weights (simplified)
            for key in self._weights:
                self._weights[key] *= 1.01
        
        if self._bus:
            self._bus.emit("retrieval.reranker.feedback", {
                "document_id": document_id,
                "relevant": relevant,
                "weights": dict(self._weights),
            })

    def get_weights(self) -> Dict[str, float]:
        """Return current feature weights."""
        return dict(self._weights)

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "weights": self.get_weights(),
        }
