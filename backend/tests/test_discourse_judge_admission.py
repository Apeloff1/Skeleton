"""Pure discourse contracts: admission, provider isolation and finite judge evidence."""
from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from routes import discourse


@pytest.mark.parametrize("value", [
    "[]", "true", "null", "NaN", '{"winner_index":NaN}',
    '{"scores": [], "scores": [1]}',
    "x" * (discourse.MAX_JUDGE_REPLY_CHARS + 1),
])
def test_judge_json_requires_bounded_object_and_unique_finite_values(value):
    assert discourse._extract_json(value) == {}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, False, "97", -1, 101])
def test_score_rejects_out_of_budget_values(value):
    assert discourse._score_int(value) is None


def test_legacy_embedded_and_fenced_judge_json_remain_supported():
    fence = chr(96) * 3
    assert discourse._extract_json(fence + 'json\n{"winner_index":0}\n' + fence) == {"winner_index": 0}
    assert discourse._extract_json('Judge:\n{"winner_index":0}\nDone.') == {"winner_index": 0}


@pytest.mark.parametrize("bad", [
    {"prompt": "x" * 20_001},
    {"panel": ["a"] * 6},
    {"rounds": 0},
    {"rounds": 5},
    {"system": "x" * 8_001},
])
def test_api_models_enforce_bounded_input(bad):
    with pytest.raises(ValidationError):
        discourse.DeliberateBody(**{"prompt": "hello there", **bad})


def test_async_overlong_prompt_rejected_before_any_database_access(monkeypatch):
    class NoDatabase:
        @property
        def discourse_jobs(self):
            raise AssertionError("database side effect before validation")

    monkeypatch.setattr(discourse, "_db", NoDatabase())
    body = discourse.DeliberateBody.model_construct(prompt="x" * 20_001, task="creative",
                                                    system="", panel=[], judge_model="",
                                                    discord=True, rounds=1)
    result = asyncio.run(discourse.deliberate_async(body))
    assert result["error"] == "prompt exceeds 20k char limit"


def test_direct_input_rejects_unknown_selected_panel_before_model_invocation(monkeypatch):
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("provider contacted before admission")

    monkeypatch.setattr(discourse, "route_complete", forbidden)
    result = asyncio.run(discourse.deliberate(
        "creative", "valid prompt", panel=[{"unhashable": "model"}], do_discord=False
    ))
    assert "error" in result


def test_malformed_judge_scores_do_not_create_fabricated_winner(monkeypatch):
    monkeypatch.setattr(discourse, "MODEL_CATALOG", {
        "m1": {"provider": "a"}, "m2": {"provider": "b"}, "judge": {"provider": "c"}
    })

    async def fake_route(*_args, model=None, **_kwargs):
        if model == "judge":
            return {"content": '{"winner_index":true,"scores":[{},false,"x",{"index":0,"quality":NaN,"fidelity":95}]}'}
        return {"content": "valid candidate from model"}

    monkeypatch.setattr(discourse, "route_complete", fake_route)
    result = asyncio.run(discourse.deliberate(
        "creative", "valid prompt", panel=["m1", "m2"], judge_model="judge", do_discord=False
    ))
    assert result["error"] == "judge_scores_unavailable"
    assert "winner_model" not in result


def test_provider_exception_does_not_cancel_surviving_candidate(monkeypatch):
    monkeypatch.setattr(discourse, "MODEL_CATALOG", {
        "m1": {"provider": "a"}, "m2": {"provider": "b"}, "judge": {"provider": "c"}
    })

    async def fake_route(*_args, model=None, **_kwargs):
        if model == "m1":
            raise RuntimeError("provider unavailable")
        if model == "judge":
            return {"content": '{"winner_index":0,"scores":[{"index":0,"quality":80,"fidelity":90}]}'}
        return {"content": "valid surviving candidate"}

    class Collection:
        async def insert_one(self, *_args):
            from types import SimpleNamespace
            return SimpleNamespace(acknowledged=True)

    class Database:
        discourse_log = Collection()

    monkeypatch.setattr(discourse, "route_complete", fake_route)
    monkeypatch.setattr(discourse, "_db", Database())
    result = asyncio.run(discourse.deliberate(
        "creative", "valid prompt", panel=["m1", "m2"], judge_model="judge", do_discord=False
    ))
    assert result["winner_model"] == "m2"
    assert result["judge_status"] == "reported_scores"
    assert result["winner_score"] > 0


def test_boolean_judge_index_must_not_select_second_candidate(monkeypatch):
    monkeypatch.setattr(discourse, "MODEL_CATALOG", {
        "m1": {"provider": "a"}, "m2": {"provider": "b"}, "judge": {"provider": "c"}
    })

    async def fake_route(*_args, model=None, **_kwargs):
        if model == "judge":
            return {"content": '{"winner_index":true,"scores":[{"index":0,"quality":95,"fidelity":95},'
                               '{"index":1,"quality":5,"fidelity":5}]}'}
        return {"content": "valid candidate"}

    class Collection:
        async def insert_one(self, *_args):
            from types import SimpleNamespace
            return SimpleNamespace(acknowledged=True)

    class Database:
        discourse_log = Collection()

    monkeypatch.setattr(discourse, "route_complete", fake_route)
    monkeypatch.setattr(discourse, "_db", Database())
    result = asyncio.run(discourse.deliberate(
        "creative", "valid prompt", panel=["m1", "m2"], judge_model="judge", do_discord=False
    ))
    assert result["winner_index"] == 0
    assert result["winner_model"] == "m1"



def test_large_integer_scores_do_not_overflow_float_conversion():
    assert discourse._score_int(10 ** 1000) is None
    assert discourse._score_int(100) == 100


def test_unacknowledged_log_write_is_not_reported_as_durable(monkeypatch):
    monkeypatch.setattr(discourse, "MODEL_CATALOG", {
        "m1": {"provider": "a"}, "judge": {"provider": "b"}
    })

    async def fake_route(*_args, model=None, **_kwargs):
        if model == "judge":
            return {"content": '{"winner_index":0,"scores":[{"index":0,"quality":85,"fidelity":92}]}'}
        return {"content": "candidate"}

    class Collection:
        async def insert_one(self, *_args):
            from types import SimpleNamespace
            return SimpleNamespace(acknowledged=False)

    class Database:
        discourse_log = Collection()

    monkeypatch.setattr(discourse, "route_complete", fake_route)
    monkeypatch.setattr(discourse, "_db", Database())
    result = asyncio.run(discourse.deliberate(
        "creative", "valid prompt", panel=["m1"], judge_model="judge", do_discord=False
    ))
    assert result["error"] == "deliberation_not_durable"
    assert result["persistence_status"] == "unconfirmed"
    assert result["winner_score"] > 0
