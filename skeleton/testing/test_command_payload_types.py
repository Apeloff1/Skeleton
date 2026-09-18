"""Fail-closed integer/boolean payload types for shared command contracts."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from skeleton.application.command_contracts import CommandError, require_bool, require_int
from skeleton.application import build_runtime_command_service


def test_require_bool_rejects_truthy_stand_ins() -> None:
    assert require_bool({}, "repair", False) is False
    assert require_bool({"repair": True}, "repair", False) is True
    assert require_bool({"repair": False}, "repair", True) is False
    for value in (1, 0, "false", "true", None, 1.0):
        with pytest.raises(CommandError) as exc_info:
            require_bool({"repair": value}, "repair", False)
        assert exc_info.value.code == "invalid_argument"
        assert exc_info.value.http_status == 422


def test_require_int_rejects_bool_float_and_numeric_strings() -> None:
    assert require_int({}, "top_k", 3, minimum=1) == 3
    assert require_int({"top_k": 8}, "top_k", 3, minimum=1) == 8
    for value in (True, False, "3", 1.5, 3.0, None, "1"):
        with pytest.raises(CommandError) as exc_info:
            require_int({"top_k": value}, "top_k", 3, minimum=1)
        assert exc_info.value.code == "invalid_argument"
    with pytest.raises(CommandError) as too_small:
        require_int({"top_k": 0}, "top_k", 3, minimum=1)
    assert ">= 1" in too_small.value.message


class _MemoryHit:
    def __init__(self, text: str) -> None:
        self.chunk = type("Chunk", (), {"text": text})()


class _MemoryResult:
    facts = (_MemoryHit("fact"),)
    persona_frame = ()
    personal_history = ()
    combined_score = 1.0
    token_estimate = 4
    provenance_chain = []


class _Memory:
    def query_unified(self, query, top_k_per_tier=3, metadata_filter=None):
        self.query = query
        self.top_k_per_tier = top_k_per_tier
        self.metadata_filter = metadata_filter
        return _MemoryResult()


class _Game:
    def __init__(self, repair: bool) -> None:
        self.repair = repair

    def to_dict(self):
        return {"repair": self.repair}


class _Forge:
    def run(self, answers, title=None, target="json", repair=False):
        self.repair = repair
        return _Game(repair)


class _State:
    genesis = None
    memory_trinity = _Memory()
    gameforge = _Forge()
    registry = None

    def is_healthy(self):
        return {"overall": True, "checks": {}}


def test_memory_command_rejects_coerced_top_k() -> None:
    service = build_runtime_command_service(_State())
    ok = service.execute("memory", {"query": "hello", "top_k": 2})
    assert ok.ok is True
    assert ok.data["facts"] == ["fact"]

    defaulted = service.execute("memory", {"query": "hello"})
    assert defaulted.ok is True

    for payload in (
        {"query": "hello", "top_k": True},
        {"query": "hello", "top_k": "3"},
        {"query": "hello", "top_k": 1.5},
        {"query": "hello", "top_k": 0},
    ):
        result = service.execute("memory", payload)
        assert result.ok is False
        assert result.to_payload()["error"]["code"] == "invalid_argument"
        assert result.http_status == 422


def test_run_command_rejects_coerced_repair_flag() -> None:
    service = build_runtime_command_service(_State())
    ok = service.execute("run", {"answers": {}, "repair": True})
    assert ok.ok is True
    assert ok.data["game"]["repair"] is True

    defaulted = service.execute("run", {"answers": {}})
    assert defaulted.ok is True
    assert defaulted.data["game"]["repair"] is False

    for repair in (1, "false", "true", None):
        result = service.execute("run", {"answers": {}, "repair": repair})
        assert result.ok is False
        assert result.to_payload()["error"]["code"] == "invalid_argument"


def test_http_retrieval_query_rejects_coerced_k_and_cache_flag() -> None:
    from skeleton.api import routes

    class _Quad:
        def retrieve(self, query, k=8, use_cache=True):
            self.k = k
            self.use_cache = use_cache
            return []

        def stats(self):
            return {}

    class _Genesis:
        handles = {"quad": _Quad()}

    class _HttpState:
        genesis = _Genesis()

    body = asyncio.run(routes.retrieval_query({"query": "alpha", "k": 4, "use_cache": False}, _HttpState()))
    assert body["query"] == "alpha"
    assert body["results"] == []

    with pytest.raises(HTTPException) as coerced_k:
        asyncio.run(routes.retrieval_query({"query": "alpha", "k": True}, _HttpState()))
    assert coerced_k.value.status_code == 422

    with pytest.raises(HTTPException) as coerced_cache:
        asyncio.run(routes.retrieval_query({"query": "alpha", "use_cache": "false"}, _HttpState()))
    assert coerced_cache.value.status_code == 422


def test_require_float_rejects_bool_string_and_non_finite() -> None:
    from skeleton.application.command_contracts import require_float

    assert require_float({}, "salience", 0.5, minimum=0.0) == 0.5
    assert require_float({"salience": 1}, "salience", 0.5, minimum=0.0) == 1.0
    for value in (True, "0.5", None, float("nan"), float("inf")):
        with pytest.raises(CommandError):
            require_float({"salience": value}, "salience", 0.5, minimum=0.0)


def test_require_text_rejects_non_strings_and_unknown_targets() -> None:
    from skeleton.application.command_contracts import MATERIALISE_TARGETS, require_text

    assert require_text({}, "target", "json", allowed=MATERIALISE_TARGETS) == "json"
    assert require_text({"title": "Arena"}, "title", None, optional=True) == "Arena"
    assert require_text({}, "title", None, optional=True) is None
    with pytest.raises(CommandError):
        require_text({"target": 1}, "target", "json", allowed=MATERIALISE_TARGETS)
    with pytest.raises(CommandError):
        require_text({"target": "unity"}, "target", "json", allowed=MATERIALISE_TARGETS)


def test_run_command_rejects_coerced_target_and_title() -> None:
    service = build_runtime_command_service(_State())
    ok = service.execute("run", {"answers": {}, "target": "godot", "title": "Arena"})
    assert ok.ok is True

    for payload in (
        {"answers": {}, "target": True},
        {"answers": {}, "target": "unity"},
        {"answers": {}, "title": 12},
    ):
        result = service.execute("run", payload)
        assert result.ok is False
        assert result.to_payload()["error"]["code"] == "invalid_argument"


def test_http_ingest_and_include_files_reject_coerced_types() -> None:
    from skeleton.api import routes

    class _Quad:
        def ingest_document(self, doc_id, text, metadata=None, salience=0.5):
            self.salience = salience
            return 1

    class _Genesis:
        handles = {"quad": _Quad()}

    class _HttpState:
        genesis = _Genesis()

    body = asyncio.run(
        routes.retrieval_ingest({"doc_id": "a", "text": "hello", "salience": 0.25}, _HttpState())
    )
    assert body["status"] == "ingested"

    with pytest.raises(HTTPException) as coerced:
        asyncio.run(routes.retrieval_ingest({"doc_id": "a", "text": "hello", "salience": True}, _HttpState()))
    assert coerced.value.status_code == 422

    class _Forge:
        def execute(self, *args, **kwargs):
            return {"files": {"a.gd": "x"}}

    class _GameState:
        gameforge = _Forge()

    kept = asyncio.run(routes.gameforge_run(type("R", (), {"headers": {}})(), {"include_files": True}, _GameState()))
    assert "files" in kept
    stripped = asyncio.run(routes.gameforge_run(type("R", (), {"headers": {}})(), {}, _GameState()))
    assert "files" not in stripped
    with pytest.raises(HTTPException):
        asyncio.run(routes.gameforge_run(type("R", (), {"headers": {}})(), {"include_files": "false"}, _GameState()))


def test_require_mapping_rejects_string_and_array_stand_ins() -> None:
    from skeleton.application.command_contracts import require_mapping

    assert require_mapping({}, "metadata_filter", None, optional=True) is None
    assert require_mapping({"answers": {"era": "now"}}, "answers", {}, optional=False) == {"era": "now"}
    for value in ("{}", [], ("a",), 1, True):
        with pytest.raises(CommandError) as exc_info:
            require_mapping({"answers": value}, "answers", {}, optional=False)
        assert exc_info.value.code == "invalid_argument"


def test_require_list_rejects_string_iterables_and_bool_ints() -> None:
    from skeleton.application.command_contracts import require_list

    assert require_list({}, "deps", [], optional=False) == []
    assert require_list({"deps": ["a", "b"]}, "deps", [], optional=False, item_type=str) == ["a", "b"]
    with pytest.raises(CommandError):
        require_list({"deps": "ab"}, "deps", [], optional=False)
    with pytest.raises(CommandError):
        require_list({"xs": [True]}, "xs", [], optional=False, item_type=int)


def test_memory_and_run_commands_reject_coerced_objects() -> None:
    service = build_runtime_command_service(_State())
    ok = service.execute("memory", {"query": "hello", "metadata_filter": {"plane": "facts"}})
    assert ok.ok is True

    for payload in (
        {"query": "hello", "metadata_filter": ["facts"]},
        {"query": "hello", "metadata_filter": "facts"},
        {"query": 12},
    ):
        result = service.execute("memory", payload)
        assert result.ok is False
        assert result.to_payload()["error"]["code"] == "invalid_argument"

    answers = service.execute("run", {"answers": {"seed": 1}})
    assert answers.ok is True
    for payload in ({"answers": []}, {"answers": "nope"}):
        result = service.execute("run", payload)
        assert result.ok is False


def test_http_jeeves_session_and_hot_strings_fail_closed() -> None:
    from skeleton.jeeves.core import SessionMode
    from skeleton.api import routes

    class _Session:
        session_id = "s-1"
        mode = SessionMode.TUTORING

    class _Jeeves:
        def open_session(self, user_id, mode=None):
            self.user_id = user_id
            self.mode = mode
            return _Session()

    class _HttpState:
        jeeves = _Jeeves()
        intelligence = type("I", (), {"reason": staticmethod(lambda query, context=None: {"query": query, "context": context})})()
        resilience = type(
            "R",
            (),
            {
                "process_input": staticmethod(
                    lambda raw_input, user_id: (
                        raw_input,
                        type("Rep", (), {"level": type("L", (), {"name": "LOW"})(), "confidence": 1.0, "action_taken": "allow"})(),
                    )
                )
            },
        )()

    created = asyncio.run(routes.jeeves_session({"user_id": "api-user"}, _HttpState()))
    assert created["mode"] == "tutoring"
    with pytest.raises(HTTPException) as bad_mode:
        asyncio.run(routes.jeeves_session({"mode": "chat"}, _HttpState()))
    assert bad_mode.value.status_code == 422
    with pytest.raises(HTTPException):
        asyncio.run(routes.jeeves_session({"mode": True}, _HttpState()))

    reasoned = asyncio.run(routes.intelligence_reason({"query": "why", "context": {"k": 1}}, _HttpState()))
    assert reasoned["query"] == "why"
    with pytest.raises(HTTPException):
        asyncio.run(routes.intelligence_reason({"query": 1}, _HttpState()))
    with pytest.raises(HTTPException):
        asyncio.run(routes.intelligence_reason({"query": "why", "context": ["no"]}, _HttpState()))

    sanitised = asyncio.run(routes.resilience_sanitise({"input": "hello"}, _HttpState()))
    assert sanitised["sanitized"] == "hello"
    with pytest.raises(HTTPException):
        asyncio.run(routes.resilience_sanitise({"input": 9}, _HttpState()))


