from datetime import timezone

from skeleton.frontier.contracts import ProvenanceRecord


def test_provenance_record_is_json_friendly():
    record = ProvenanceRecord(
        source_repository="Apeloff1/Tutolage",
        source_revision="abc123",
        source_path="backend/routes/jeeves_core.py",
        metadata={"role": "candidate"},
    )

    data = record.as_dict()

    assert data["source_repository"] == "Apeloff1/Tutolage"
    assert data["source_revision"] == "abc123"
    assert data["metadata"] == {"role": "candidate"}
    assert record.timestamp.tzinfo == timezone.utc
