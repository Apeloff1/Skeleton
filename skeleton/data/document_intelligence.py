"""Document evidence preserving coordinates, trust and extraction uncertainty."""
from __future__ import annotations

from dataclasses import dataclass
import math


class DocumentEvidenceError(ValueError):
    pass


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _unit_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


@dataclass(frozen=True, slots=True)
class Document:
    document_id: str
    source_digest: str
    page_count: int
    trust_context: str


@dataclass(frozen=True, slots=True)
class DocumentRegion:
    region_id: str
    document_id: str
    page: int
    bbox: tuple[float, float, float, float]
    text: str
    extraction_method: str
    confidence: float


@dataclass(frozen=True, slots=True)
class ExtractionEvidence:
    document_id: str
    source_digest: str
    region_id: str
    page: int
    bbox: tuple[float, float, float, float]
    extraction_method: str
    confidence: float
    trust_context: str
    instruction_authority: bool = False


class DocumentEvidenceLedger:
    def __init__(self) -> None:
        self._documents: dict[str, Document] = {}
        self._regions: dict[str, DocumentRegion] = {}

    def register(self, document: Document) -> None:
        if not isinstance(document.document_id, str) or not document.document_id:
            raise DocumentEvidenceError("invalid document identity")
        if not _is_digest(document.source_digest):
            raise DocumentEvidenceError("invalid source digest")
        if (
            isinstance(document.page_count, bool)
            or not isinstance(document.page_count, int)
            or document.page_count < 1
        ):
            raise DocumentEvidenceError("invalid page count")
        if not isinstance(document.trust_context, str) or not document.trust_context:
            raise DocumentEvidenceError("missing trust context")

        old = self._documents.get(document.document_id)
        if old is not None and old != document:
            raise DocumentEvidenceError("document identity cannot be rebound")
        self._documents[document.document_id] = document

    def add_region(self, region: DocumentRegion) -> ExtractionEvidence:
        document = self._documents.get(region.document_id)
        if document is None:
            raise DocumentEvidenceError("unregistered document")
        if not isinstance(region.region_id, str) or not region.region_id:
            raise DocumentEvidenceError("invalid region identity")
        if (
            isinstance(region.page, bool)
            or not isinstance(region.page, int)
            or region.page < 1
            or region.page > document.page_count
        ):
            raise DocumentEvidenceError("invalid extraction page")
        if region.extraction_method not in {"native_text", "ocr", "vision"}:
            raise DocumentEvidenceError("invalid extraction method")
        if not isinstance(region.text, str):
            raise DocumentEvidenceError("region text must be text")
        if len(region.bbox) != 4 or not all(_unit_number(v) for v in region.bbox):
            raise DocumentEvidenceError("invalid bbox")
        x0, y0, x1, y1 = (float(v) for v in region.bbox)
        if not (x0 < x1 and y0 < y1) or not _unit_number(region.confidence):
            raise DocumentEvidenceError("invalid region geometry/confidence")

        old = self._regions.get(region.region_id)
        if old is not None and old != region:
            raise DocumentEvidenceError("region identity cannot be rebound")
        self._regions[region.region_id] = region
        return ExtractionEvidence(
            document.document_id,
            document.source_digest,
            region.region_id,
            region.page,
            (x0, y0, x1, y1),
            region.extraction_method,
            float(region.confidence),
            document.trust_context,
            False,
        )
