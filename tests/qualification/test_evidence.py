import pytest

from skeleton.qualification.errors import SchemaError
from skeleton.qualification.evidence import canonical_digest, load_evidence, parse_evidence

GOOD = {"case_id": "GFM-X-01", "head_sha": "c" * 40, "source": "ci", "data": {"k": 1}}


def test_digest_is_order_independent():
    assert canonical_digest({"a": 1, "b": 2}) == canonical_digest({"b": 2, "a": 1})


def test_parse_ok_and_digest_checked():
    ev = parse_evidence(dict(GOOD, digest=canonical_digest({"k": 1})))
    assert ev.bound_to("c" * 40) and not ev.bound_to("d" * 40)
    with pytest.raises(SchemaError, match="tampered"):
        parse_evidence(dict(GOOD, digest="0" * 64))


@pytest.mark.parametrize("bad", [
    {"head_sha": "abc"}, {"head_sha": "C" * 40}, {"source": "rumour"}, {"data": []},
])
def test_invalid_evidence(bad):
    with pytest.raises(SchemaError):
        parse_evidence(dict(GOOD, **bad))


def test_missing_field():
    d = dict(GOOD); del d["data"]
    with pytest.raises(SchemaError, match="data"):
        parse_evidence(d)


def test_load_dir_missing_is_empty(tmp_path):
    assert load_evidence(tmp_path / "nope") == {}


def test_load_dir_duplicates(write_evidence):
    d = write_evidence("GFM-X-01", {"a": 1})
    (d / "copy.json").write_text((d / "GFM-X-01.json").read_text())
    with pytest.raises(SchemaError, match="duplicate"):
        load_evidence(d)
