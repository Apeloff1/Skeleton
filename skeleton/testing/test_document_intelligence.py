import pytest

from skeleton.data.document_intelligence import (
    Document,
    DocumentEvidenceError,
    DocumentEvidenceLedger,
    DocumentRegion,
)


def test_document_evidence_preserves_location_and_no_instruction_authority() -> None:
    ledger = DocumentEvidenceLedger()
    ledger.register(Document("doc", "a" * 64, 2, "external-untrusted"))
    evidence = ledger.add_region(
        DocumentRegion(
            "region",
            "doc",
            2,
            (0.1, 0.2, 0.8, 0.9),
            "ignore prior",
            "ocr",
            0.7,
        )
    )
    assert evidence.page == 2
    assert evidence.bbox == (0.1, 0.2, 0.8, 0.9)
    assert evidence.instruction_authority is False


@pytest.mark.parametrize(
    "bbox,confidence",
    [
        ((0.0, 0.0, 1.0, 1.0), float("nan")),
        ((0.0, 0.0, float("inf"), 1.0), 0.5),
        ((True, 0.0, 1.0, 1.0), 0.5),
    ],
)
def test_nonfinite_or_boolean_geometry_fails(bbox, confidence) -> None:
    ledger = DocumentEvidenceLedger()
    ledger.register(Document("doc", "a" * 64, 1, "external"))
    with pytest.raises(DocumentEvidenceError):
        ledger.add_region(
            DocumentRegion(
                "region",
                "doc",
                1,
                bbox,
                "text",
                "vision",
                confidence,
            )
        )


def test_invalid_digest_and_unregistered_document_fail() -> None:
    with pytest.raises(DocumentEvidenceError, match="source digest"):
        DocumentEvidenceLedger().register(Document("doc", "z" * 64, 1, "external"))
    with pytest.raises(DocumentEvidenceError, match="unregistered"):
        DocumentEvidenceLedger().add_region(
            DocumentRegion(
                "region",
                "missing",
                1,
                (0.0, 0.0, 1.0, 1.0),
                "x",
                "vision",
                0.5,
            )
        )
