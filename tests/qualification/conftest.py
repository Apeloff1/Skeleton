import json

import pytest

from skeleton.qualification.evidence import canonical_digest

HEAD = "a" * 40
OTHER = "b" * 40


@pytest.fixture
def head():
    return HEAD


@pytest.fixture
def write_evidence(tmp_path):
    d = tmp_path / "evidence"
    d.mkdir()

    def _write(case_id, data, sha=HEAD, source="ci", digest=True):
        doc = {"case_id": case_id, "head_sha": sha, "source": source, "data": data}
        if digest:
            doc["digest"] = canonical_digest(data)
        (d / f"{case_id}.json").write_text(json.dumps(doc))
        return d

    _write.dir = d
    return _write
