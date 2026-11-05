import pytest

from core.core_v1.concurrency import check_if_match, etag
from core.core_v1.errors import CoreError
from core.core_v1.pagination import CursorCodec, build_page, parse_limit


def test_limit_parsing():
    assert parse_limit(None) == 50
    assert parse_limit("10") == 10
    for bad in ("0", "201", "x", -1):
        with pytest.raises(CoreError) as ei:
            parse_limit(bad)
        assert ei.value.code == "CORE.PAGINATION.INVALID_LIMIT"


def test_cursor_roundtrip_and_scope_binding():
    c = CursorCodec(b"s" * 32)
    cur = c.encode("webhooks:t1", 12.5, "whk_1")
    assert c.decode("webhooks:t1", cur) == (12.5, "whk_1")
    with pytest.raises(CoreError):
        c.decode("webhooks:t2", cur)  # cross-tenant reuse rejected


def test_cursor_tamper_rejected():
    c = CursorCodec(b"s" * 32)
    cur = c.encode("a", 1.0, "x")
    with pytest.raises(CoreError):
        c.decode("a", cur[:-2] + ("AA" if not cur.endswith("AA") else "BB"))
    with pytest.raises(CoreError):
        c.decode("a", "garbage")
    with pytest.raises(CoreError):
        CursorCodec(b"other-key-xxxxxxxxxxxxxxxxxxxxxx").decode("a", cur)


def test_build_page_limit_plus_one():
    c = CursorCodec(b"s" * 32)
    rows = [(float(i), f"id{i}") for i in range(4)]
    p = build_page(rows, 3, lambda r: r, c, "s")
    assert len(p.items) == 3 and p.next_cursor
    assert c.decode("s", p.next_cursor) == (2.0, "id2")
    last = build_page(rows[:2], 3, lambda r: r, c, "s")
    assert last.next_cursor is None
    assert last.as_dict(lambda r: r[1]) == {"items": ["id0", "id1"], "next_cursor": None, "has_more": False}


def test_if_match():
    tag = etag("whk_1", 3)
    check_if_match(tag, "whk_1", 3)
    check_if_match("*", "whk_1", 3)
    check_if_match(f'"zzz", {tag}', "whk_1", 3)
    with pytest.raises(CoreError) as ei:
        check_if_match(None, "whk_1", 3)
    assert ei.value.http_status == 428
    with pytest.raises(CoreError) as ei:
        check_if_match(etag("whk_1", 2), "whk_1", 3)
    assert ei.value.http_status == 412 and ei.value.context["current_etag"] == tag
    with pytest.raises(CoreError):
        check_if_match("W/" + tag, "whk_1", 3)  # weak tags never match writes
    check_if_match(None, "whk_1", 3, required=False)


def test_cursor_rejects_nonfinite_boolean_and_malformed_base64():
    import base64
    import json

    c = CursorCodec(b"s" * 32)
    for value in (float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="bounded and finite"):
            c.encode("scope", value, "id")
    for bad in (float("nan"), float("inf"), True):
        body = json.dumps({"s": "scope", "t": bad, "i": "id"}).encode()
        forged = base64.urlsafe_b64encode(body).decode().rstrip("=") + "." + c._mac(body)
        with pytest.raises(CoreError):
            c.decode("scope", forged)
    with pytest.raises(CoreError):
        c.decode("scope", "!!!!.0000000000000000")
    with pytest.raises(CoreError):
        parse_limit(True)
