from skeleton.api.v1_edge.tracing import parse_or_start, request_id
from skeleton.api.v1_edge.validation import validate

S = {"type": "object", "required": ["n"], "additionalProperties": False,
     "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 5},
                    "tags": {"type": "array", "maxItems": 2, "items": {"type": "string", "enum": ["a", "b"]}},
                    "s": {"type": "string", "maxLength": 3}}}


def test_validate_cases():
    assert validate({"n": 2, "tags": ["a"]}, S) == []
    paths = {e["path"] for e in validate({"n": True, "x": 1, "tags": ["z", "a", "b"], "s": "long"}, S)}
    assert paths == {"$.n", "$.x", "$.tags", "$.tags[0]", "$.s"}
    assert validate({}, S)[0]["error"] == "required"
    assert validate({"n": 9}, S)[0]["error"] == "above maximum"
    assert validate(None, {"type": ["null", "string"]}) == []


def test_traceparent():
    tp = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    t = parse_or_start(tp)
    assert t.trace_id == "a" * 32 and t.parent_id == "b" * 16 and t.sampled
    assert t.traceparent().startswith("00-" + "a" * 32)
    assert parse_or_start("00-" + "0" * 32 + "-" + "b" * 16 + "-01").parent_id is None
    assert parse_or_start("junk").parent_id is None


def test_request_id():
    assert request_id("abcdefgh-1") == "abcdefgh-1"
    assert request_id("bad id\n") != "bad id\n"
    assert len(request_id(None)) == 24
