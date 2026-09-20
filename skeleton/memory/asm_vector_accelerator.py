"""Assembly-backed dense vector scoring adapter.

This adapter exposes the same narrow search surface used by VectorStore's JVM
accelerator, but keeps scoring in-process through Skeleton's hand-written
Assembly microkernels. Candidate matrices can be prepared once and reused
across repeated queries.
"""
from __future__ import annotations

import array
import math
from dataclasses import dataclass
from threading import Lock
from typing import Sequence

from skeleton.native.asm_accelerator import (
    AsmVectorAccelerator,
    get_default_asm_accelerator,
)

_MAX_DIMENSIONS = 4096
_MAX_CANDIDATES = 100_000
_MAX_QUERIES = 512
_MAX_ELEMENTS = 4_000_000
_MAX_SCORE_ELEMENTS = 4_000_000
_MAX_RANGE_HITS = 1_000_000
_SIMILARITY_EPSILON = 1e-4


@dataclass(frozen=True, slots=True)
class AsmVectorHit:
    index: int
    similarity: float


@dataclass(frozen=True, slots=True)
class PreparedAsmCandidates:
    dimensions: int
    count: int
    matrix: array.array
    norms: tuple[float, ...]


class AsmVectorSearchAccelerator:
    """Cosine top-K and threshold search using an Assembly dot-product kernel."""

    def __init__(
        self,
        kernel: AsmVectorAccelerator | None = None,
        *,
        minimum_candidates: int = 32,
        build_if_missing: bool = False,
    ) -> None:
        if (
            isinstance(minimum_candidates, bool)
            or not isinstance(minimum_candidates, int)
            or minimum_candidates < 1
        ):
            raise ValueError("minimum_candidates must be a positive integer")
        self._kernel = kernel or get_default_asm_accelerator(
            build_if_missing=build_if_missing
        )
        self.minimum_candidates = minimum_candidates

    @property
    def kernel(self) -> AsmVectorAccelerator:
        return self._kernel

    def prepare_candidates(
        self,
        candidates: Sequence[tuple[Sequence[float], float]],
    ) -> PreparedAsmCandidates:
        candidate_count = len(candidates)
        if not 1 <= candidate_count <= _MAX_CANDIDATES:
            raise ValueError("candidate count outside supported range")

        dimensions = len(candidates[0][0])
        if not 1 <= dimensions <= _MAX_DIMENSIONS:
            raise ValueError("candidate dimensions outside supported range")
        if dimensions * candidate_count > _MAX_ELEMENTS:
            raise ValueError("vector element count exceeds accelerator bound")

        matrix = array.array("f")
        norms: list[float] = []
        for vector, norm in candidates:
            if len(vector) != dimensions:
                raise ValueError("candidate dimension mismatch")
            norm_value = float(norm)
            if not math.isfinite(norm_value) or norm_value <= 0:
                raise ValueError("candidate norm must be finite and positive")
            try:
                row = array.array("f", (float(value) for value in vector))
            except (OverflowError, TypeError, ValueError) as exc:
                raise ValueError("candidate vector is not representable as float32") from exc
            if not all(math.isfinite(value) for value in row):
                raise ValueError("candidate vector must contain finite values")
            matrix.extend(row)
            norms.append(norm_value)

        return PreparedAsmCandidates(
            dimensions=dimensions,
            count=candidate_count,
            matrix=matrix,
            norms=tuple(norms),
        )

    def top_k(
        self,
        query: Sequence[float],
        query_norm: float,
        candidates: Sequence[tuple[Sequence[float], float]],
        top_k: int,
    ) -> list[AsmVectorHit]:
        return self.top_k_prepared(
            query,
            query_norm,
            self.prepare_candidates(candidates),
            top_k,
        )

    def top_k_prepared(
        self,
        query: Sequence[float],
        query_norm: float,
        prepared: PreparedAsmCandidates,
        top_k: int,
    ) -> list[AsmVectorHit]:
        self._validate_query(query, query_norm, prepared)
        if not 1 <= top_k <= prepared.count:
            raise ValueError("top_k outside candidate range")

        hits = self._score_prepared(query, query_norm, prepared)
        return hits[:top_k]

    def top_k_many(
        self,
        queries: Sequence[tuple[Sequence[float], float]],
        candidates: Sequence[tuple[Sequence[float], float]],
        top_k: int,
    ) -> list[list[AsmVectorHit]]:
        return self.top_k_many_prepared(
            queries,
            self.prepare_candidates(candidates),
            top_k,
        )

    def top_k_many_prepared(
        self,
        queries: Sequence[tuple[Sequence[float], float]],
        prepared: PreparedAsmCandidates,
        top_k: int,
    ) -> list[list[AsmVectorHit]]:
        query_count = len(queries)
        if not 1 <= query_count <= _MAX_QUERIES:
            raise ValueError("query count outside supported range")
        if prepared.dimensions * (query_count + prepared.count) > _MAX_ELEMENTS:
            raise ValueError("vector element count exceeds accelerator bound")
        if query_count * prepared.count > _MAX_SCORE_ELEMENTS:
            raise ValueError("score matrix exceeds accelerator bound")
        if not 1 <= top_k <= prepared.count:
            raise ValueError("top_k outside candidate range")

        return [
            hits[:top_k]
            for hits in self._score_many_prepared(queries, prepared)
        ]

    def range_search(
        self,
        query: Sequence[float],
        query_norm: float,
        candidates: Sequence[tuple[Sequence[float], float]],
        similarity_threshold: float,
        *,
        max_hits: int = _MAX_RANGE_HITS,
    ) -> list[AsmVectorHit]:
        return self.range_search_prepared(
            query,
            query_norm,
            self.prepare_candidates(candidates),
            similarity_threshold,
            max_hits=max_hits,
        )

    def range_search_prepared(
        self,
        query: Sequence[float],
        query_norm: float,
        prepared: PreparedAsmCandidates,
        similarity_threshold: float,
        *,
        max_hits: int = _MAX_RANGE_HITS,
    ) -> list[AsmVectorHit]:
        threshold = self._validate_threshold(similarity_threshold)
        self._validate_query(query, query_norm, prepared)
        if not 1 <= max_hits <= min(prepared.count, _MAX_RANGE_HITS):
            raise ValueError("max_hits outside candidate range")

        hits = [
            hit
            for hit in self._score_prepared(query, query_norm, prepared)
            if hit.similarity + _SIMILARITY_EPSILON >= threshold
        ]
        if len(hits) > max_hits:
            raise ValueError("range result bound exceeded")
        return hits

    def range_search_many(
        self,
        queries: Sequence[tuple[Sequence[float], float]],
        candidates: Sequence[tuple[Sequence[float], float]],
        similarity_threshold: float,
        *,
        max_total_hits: int = _MAX_RANGE_HITS,
    ) -> list[list[AsmVectorHit]]:
        return self.range_search_many_prepared(
            queries,
            self.prepare_candidates(candidates),
            similarity_threshold,
            max_total_hits=max_total_hits,
        )

    def range_search_many_prepared(
        self,
        queries: Sequence[tuple[Sequence[float], float]],
        prepared: PreparedAsmCandidates,
        similarity_threshold: float,
        *,
        max_total_hits: int = _MAX_RANGE_HITS,
    ) -> list[list[AsmVectorHit]]:
        query_count = len(queries)
        if not 1 <= query_count <= _MAX_QUERIES:
            raise ValueError("query count outside supported range")
        if not 1 <= max_total_hits <= _MAX_RANGE_HITS:
            raise ValueError("max_total_hits outside supported range")
        if prepared.dimensions * (query_count + prepared.count) > _MAX_ELEMENTS:
            raise ValueError("vector element count exceeds accelerator bound")
        if query_count * prepared.count > _MAX_SCORE_ELEMENTS:
            raise ValueError("score matrix exceeds accelerator bound")
        threshold = self._validate_threshold(similarity_threshold)

        total = 0
        output: list[list[AsmVectorHit]] = []
        for scored in self._score_many_prepared(queries, prepared):
            hits = [
                hit
                for hit in scored
                if hit.similarity + _SIMILARITY_EPSILON >= threshold
            ]
            total += len(hits)
            if total > max_total_hits:
                raise ValueError("batch range result bound exceeded")
            output.append(hits)
        return output

    def _score_many_prepared(
        self,
        queries: Sequence[tuple[Sequence[float], float]],
        prepared: PreparedAsmCandidates,
    ) -> list[list[AsmVectorHit]]:
        query_matrix = array.array("f")
        query_norms: list[float] = []
        for query, query_norm in queries:
            self._validate_query(query, query_norm, prepared)
            query_matrix.extend(self._float32_query(query))
            query_norms.append(float(query_norm))

        dots = self._kernel.dot_queries_matrix_f32(
            query_matrix,
            prepared.matrix,
            query_count=len(queries),
            rows=prepared.count,
            dimensions=prepared.dimensions,
        )
        expected = len(queries) * prepared.count
        if len(dots) != expected:
            raise RuntimeError("Assembly kernel returned wrong score matrix size")

        output: list[list[AsmVectorHit]] = []
        for query_index, query_norm in enumerate(query_norms):
            start = query_index * prepared.count
            query_dots = dots[start : start + prepared.count]
            hits: list[AsmVectorHit] = []
            for index, dot in enumerate(query_dots):
                similarity = float(dot) / (
                    query_norm * prepared.norms[index]
                )
                similarity = self._bounded_similarity(similarity)
                hits.append(AsmVectorHit(index=index, similarity=similarity))
            hits.sort(key=lambda hit: (-hit.similarity, hit.index))
            output.append(hits)
        return output

    def _score_prepared(
        self,
        query: Sequence[float],
        query_norm: float,
        prepared: PreparedAsmCandidates,
    ) -> list[AsmVectorHit]:
        query_values = self._float32_query(query)
        dots = self._kernel.dot_matrix_f32(
            query_values,
            prepared.matrix,
            rows=prepared.count,
            dimensions=prepared.dimensions,
        )
        if len(dots) != prepared.count:
            raise RuntimeError("Assembly kernel returned wrong row count")

        denominator = float(query_norm)
        hits: list[AsmVectorHit] = []
        for index, dot in enumerate(dots):
            similarity = float(dot) / (denominator * prepared.norms[index])
            similarity = self._bounded_similarity(similarity)
            hits.append(AsmVectorHit(index=index, similarity=similarity))
        hits.sort(key=lambda hit: (-hit.similarity, hit.index))
        return hits

    @staticmethod
    def _float32_query(query: Sequence[float]) -> array.array:
        try:
            values = array.array("f", (float(value) for value in query))
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("query vector is not representable as float32") from exc
        if not all(math.isfinite(value) for value in values):
            raise ValueError("query vector must contain finite values")
        return values

    @classmethod
    def _validate_query(
        cls,
        query: Sequence[float],
        query_norm: float,
        prepared: PreparedAsmCandidates,
    ) -> None:
        if len(query) != prepared.dimensions:
            raise ValueError("query dimension mismatch")
        cls._validate_query_norm(query_norm)

    @staticmethod
    def _validate_query_norm(query_norm: float) -> None:
        value = float(query_norm)
        if not math.isfinite(value) or value <= 0:
            raise ValueError("query_norm must be finite and positive")

    @staticmethod
    def _validate_threshold(similarity_threshold: float) -> float:
        value = float(similarity_threshold)
        if not math.isfinite(value) or not -1.0 <= value <= 1.0:
            raise ValueError("similarity_threshold outside [-1, 1]")
        return value

    @staticmethod
    def _bounded_similarity(similarity: float) -> float:
        if not math.isfinite(similarity):
            raise RuntimeError("Assembly kernel produced non-finite similarity")
        if (
            similarity < -1.0 - _SIMILARITY_EPSILON
            or similarity > 1.0 + _SIMILARITY_EPSILON
        ):
            raise RuntimeError("Assembly cosine similarity outside supported range")
        return min(1.0, max(-1.0, similarity))


_default_search_accelerator: AsmVectorSearchAccelerator | None = None
_default_search_lock = Lock()


def get_default_asm_vector_accelerator() -> AsmVectorSearchAccelerator:
    global _default_search_accelerator
    with _default_search_lock:
        if _default_search_accelerator is None:
            _default_search_accelerator = AsmVectorSearchAccelerator()
        return _default_search_accelerator


__all__ = [
    "AsmVectorHit",
    "AsmVectorSearchAccelerator",
    "PreparedAsmCandidates",
    "get_default_asm_vector_accelerator",
]
