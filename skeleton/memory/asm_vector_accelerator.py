"""Assembly-backed dense vector scoring adapter.

This adapter exposes the same narrow search surface used by VectorStore's JVM
accelerator, but keeps scoring in-process through Skeleton's hand-written
Assembly microkernels.
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
_MAX_RANGE_HITS = 1_000_000


@dataclass(frozen=True, slots=True)
class AsmVectorHit:
    index: int
    similarity: float


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

    def top_k(
        self,
        query: Sequence[float],
        query_norm: float,
        candidates: Sequence[tuple[Sequence[float], float]],
        top_k: int,
    ) -> list[AsmVectorHit]:
        dimensions, matrix, norms = self._prepare_candidates(query, candidates)
        self._validate_query_norm(query_norm)
        if not 1 <= top_k <= len(candidates):
            raise ValueError("top_k outside candidate range")

        dots = self._kernel.dot_matrix_f32(
            query,
            matrix,
            rows=len(candidates),
            dimensions=dimensions,
        )
        hits = [
            AsmVectorHit(
                index=index,
                similarity=dot / (float(query_norm) * norms[index]),
            )
            for index, dot in enumerate(dots)
        ]
        hits.sort(key=lambda hit: (-hit.similarity, hit.index))
        return hits[:top_k]

    def top_k_many(
        self,
        queries: Sequence[tuple[Sequence[float], float]],
        candidates: Sequence[tuple[Sequence[float], float]],
        top_k: int,
    ) -> list[list[AsmVectorHit]]:
        query_count = len(queries)
        if not 1 <= query_count <= _MAX_QUERIES:
            raise ValueError("query count outside supported range")
        first_query = queries[0][0]
        dimensions, matrix, norms = self._prepare_candidates(first_query, candidates)
        if dimensions * (query_count + len(candidates)) > _MAX_ELEMENTS:
            raise ValueError("vector element count exceeds accelerator bound")
        if not 1 <= top_k <= len(candidates):
            raise ValueError("top_k outside candidate range")

        output: list[list[AsmVectorHit]] = []
        for query, query_norm in queries:
            if len(query) != dimensions:
                raise ValueError("query dimension mismatch")
            self._validate_query_norm(query_norm)
            dots = self._kernel.dot_matrix_f32(
                query,
                matrix,
                rows=len(candidates),
                dimensions=dimensions,
            )
            hits = [
                AsmVectorHit(
                    index=index,
                    similarity=dot / (float(query_norm) * norms[index]),
                )
                for index, dot in enumerate(dots)
            ]
            hits.sort(key=lambda hit: (-hit.similarity, hit.index))
            output.append(hits[:top_k])
        return output

    def range_search(
        self,
        query: Sequence[float],
        query_norm: float,
        candidates: Sequence[tuple[Sequence[float], float]],
        similarity_threshold: float,
        *,
        max_hits: int = _MAX_RANGE_HITS,
    ) -> list[AsmVectorHit]:
        threshold = self._validate_threshold(similarity_threshold)
        dimensions, matrix, norms = self._prepare_candidates(query, candidates)
        self._validate_query_norm(query_norm)
        if not 1 <= max_hits <= min(len(candidates), _MAX_RANGE_HITS):
            raise ValueError("max_hits outside candidate range")

        denominator = float(query_norm)
        dots = self._kernel.dot_matrix_f32(
            query,
            matrix,
            rows=len(candidates),
            dimensions=dimensions,
        )
        hits: list[AsmVectorHit] = []
        for index, dot in enumerate(dots):
            similarity = dot / (denominator * norms[index])
            if similarity + 1e-7 < threshold:
                continue
            hits.append(AsmVectorHit(index=index, similarity=similarity))
        hits.sort(key=lambda hit: (-hit.similarity, hit.index))
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
        query_count = len(queries)
        if not 1 <= query_count <= _MAX_QUERIES:
            raise ValueError("query count outside supported range")
        if not 1 <= max_total_hits <= _MAX_RANGE_HITS:
            raise ValueError("max_total_hits outside supported range")
        threshold = self._validate_threshold(similarity_threshold)
        dimensions, matrix, norms = self._prepare_candidates(
            queries[0][0],
            candidates,
        )
        if dimensions * (query_count + len(candidates)) > _MAX_ELEMENTS:
            raise ValueError("vector element count exceeds accelerator bound")

        total = 0
        output: list[list[AsmVectorHit]] = []
        for query, query_norm in queries:
            if len(query) != dimensions:
                raise ValueError("query dimension mismatch")
            self._validate_query_norm(query_norm)
            denominator = float(query_norm)
            dots = self._kernel.dot_matrix_f32(
                query,
                matrix,
                rows=len(candidates),
                dimensions=dimensions,
            )
            hits: list[AsmVectorHit] = []
            for index, dot in enumerate(dots):
                similarity = dot / (denominator * norms[index])
                if similarity + 1e-7 < threshold:
                    continue
                hits.append(AsmVectorHit(index=index, similarity=similarity))
            hits.sort(key=lambda hit: (-hit.similarity, hit.index))
            total += len(hits)
            if total > max_total_hits:
                raise ValueError("batch range result bound exceeded")
            output.append(hits)
        return output

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
    def _prepare_candidates(
        query: Sequence[float],
        candidates: Sequence[tuple[Sequence[float], float]],
    ) -> tuple[int, array.array, list[float]]:
        dimensions = len(query)
        candidate_count = len(candidates)
        if not 1 <= dimensions <= _MAX_DIMENSIONS:
            raise ValueError("query dimensions outside supported range")
        if not 1 <= candidate_count <= _MAX_CANDIDATES:
            raise ValueError("candidate count outside supported range")
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
            matrix.extend(float(value) for value in vector)
            norms.append(norm_value)
        return dimensions, matrix, norms


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
    "get_default_asm_vector_accelerator",
]
