"""Pure discourse contracts: admission, provider isolation and finite judge evidence."""
from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from routes import discourse

ALICE = {"tenant_id": "tenant-1", "owner_id": "alice@example.test"}


@pytest.fixture(autouse=True)
def _source_declared_model_fixture(monkeypatch):
    """Provider tests inject catalog authority, never fake a legacy model pin."""
    from core.discourse_catalog import DeclaredModel, DeclaredPanel

    async def resolve(*, tenant_id, actor_id, selected=None, judge_key=None, maximum=5):
        assert tenant_id and actor_id
        names = selected or ["m1", "m2"]
        models = tuple(
            DeclaredModel("fixture:" + name, "fixture", name, index == 0)
            for index, name in enumerate(names[:maximum])
        )
        name = judge_key or "judge"
        judge = DeclaredModel("fixture:" + name, "fixture", name, False)
        return DeclaredPanel(
            models, judge,
            "multiple_models_one_provider" if len(models) > 1 else "single_model_self_review",
            False, judge.key not in {model.key for model in models},
        )

    monkeypatch.setattr(discourse, "tenant_panel", resolve)


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
    result = asyncio.run(discourse.deliberate_async(body, identity=ALICE))
    assert result["error"] == "prompt exceeds 20k char limit"


def test_direct_input_rejects_unknown_selected_panel_before_model_invocation(monkeypatch):
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("provider contacted before admission")

    monkeypatch.setattr(discourse, "route_complete", forbidden)
    result = asyncio.run(discourse.deliberate(
        "creative", "valid prompt", panel=[{"unhashable": "model"}], do_discord=False, identity=ALICE
    ))
    assert "error" in result


def test_direct_admission_exception_is_redacted_before_provider_io(monkeypatch):
    secret = "private-provider-credentials-do-not-return"

    def reject(*_args, **_kwargs):
        raise ValueError(secret)

    async def forbidden_provider(*_args, **_kwargs):
        raise AssertionError("provider contacted after rejected admission")

    monkeypatch.setattr(discourse, "_admit", reject)
    monkeypatch.setattr(discourse, "route_complete", forbidden_provider)
    result = asyncio.run(discourse.deliberate(
        "creative", "valid prompt", identity=ALICE,
    ))
    assert result == {"error": "invalid_deliberation_request"}
    assert secret not in repr(result)


def test_async_admission_exception_is_redacted_before_storage_io(monkeypatch):
    secret = "private-persistence-key-do-not-return"

    class ForbiddenDatabase:
        @property
        def discourse_jobs(self):
            raise AssertionError("database used after rejected admission")

    def reject(*_args, **_kwargs):
        raise ValueError(secret)

    monkeypatch.setattr(discourse, "_admit", reject)
    monkeypatch.setattr(discourse, "_db", ForbiddenDatabase())
    result = asyncio.run(discourse.deliberate_async(
        discourse.DeliberateBody(prompt="valid prompt"), identity=ALICE,
    ))
    assert result == {"error": "invalid_deliberation_request"}
    assert secret not in repr(result)


def test_malformed_judge_scores_do_not_create_fabricated_winner(monkeypatch):

    async def fake_route(*_args, model=None, **_kwargs):
        model = _kwargs.get("model_id", model)
        if model == "judge":
            return {"content": '{"winner_index":true,"scores":[{},false,"x",{"index":0,"quality":NaN,"fidelity":95}]}'}
        return {"content": "valid candidate from model"}

    monkeypatch.setattr(discourse, "route_complete", fake_route)
    result = asyncio.run(discourse.deliberate(
        "creative", "valid prompt", panel=["m1", "m2"], judge_model="judge", do_discord=False, identity=ALICE
    ))
    assert result["error"] == "judge_scores_unavailable"
    assert "winner_model" not in result


def test_provider_exception_does_not_cancel_surviving_candidate(monkeypatch):

    async def fake_route(*_args, model=None, **_kwargs):
        model = _kwargs.get("model_id", model)
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
        "creative", "valid prompt", panel=["m1", "m2"], judge_model="judge", do_discord=False, identity=ALICE
    ))
    assert result["winner_model"] == "fixture:m2"
    assert result["judge_status"] == "reported_scores"
    assert result["winner_score"] > 0


def test_boolean_judge_index_must_not_select_second_candidate(monkeypatch):

    async def fake_route(*_args, model=None, **_kwargs):
        model = _kwargs.get("model_id", model)
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
        "creative", "valid prompt", panel=["m1", "m2"], judge_model="judge", do_discord=False, identity=ALICE
    ))
    assert result["winner_index"] == 0
    assert result["winner_model"] == "fixture:m1"



def test_judge_cannot_publish_a_winner_below_its_own_validated_scores(monkeypatch):
    """The winner label must agree with the weighted score evidence."""

    async def fake_route(*_args, model=None, **_kwargs):
        model = _kwargs.get("model_id", model)
        if model == "judge":
            return {"content": '{"winner_index":1,"scores":['
                               '{"index":0,"quality":95,"fidelity":95},'
                               '{"index":1,"quality":5,"fidelity":5}]}'}
        return {"content": "valid candidate from model"}

    class Collection:
        async def insert_one(self, *_args):
            from types import SimpleNamespace
            return SimpleNamespace(acknowledged=True)

    class Database:
        discourse_log = Collection()

    monkeypatch.setattr(discourse, "route_complete", fake_route)
    monkeypatch.setattr(discourse, "_db", Database())
    result = asyncio.run(discourse.deliberate(
        "creative", "valid prompt", panel=["m1", "m2"], judge_model="judge",
        do_discord=False, identity=ALICE,
    ))
    assert result["persistence_status"] == "durable"
    assert result["winner_index"] == 0
    assert result["winner_model"] == "fixture:m1"
    assert result["winner_score"] == 95


def test_large_integer_scores_do_not_overflow_float_conversion():
    assert discourse._score_int(10 ** 1000) is None
    assert discourse._score_int(100) == 100


def test_unacknowledged_log_write_is_not_reported_as_durable(monkeypatch):

    async def fake_route(*_args, model=None, **_kwargs):
        model = _kwargs.get("model_id", model)
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
        "creative", "valid prompt", panel=["m1"], judge_model="judge", do_discord=False, identity=ALICE
    ))
    assert result["error"] == "deliberation_not_durable"
    assert result["persistence_status"] == "unconfirmed"
    assert result["winner_score"] > 0



def test_malformed_outer_object_cannot_salvage_nested_forged_judgment():
    payload = (
        '{"candidate":{"scores":[{"index":0,"quality":99,"fidelity":99}],'
        '"winner_index":0},"candidate":{}}'
    )
    assert discourse._extract_json(payload) == {}



@pytest.fixture(autouse=True)
def isolate_async_admission_registry(monkeypatch):
    monkeypatch.setattr(discourse, "_ACTIVE_DELIBERATIONS", set())


def test_unacknowledged_async_admission_never_schedules_work(monkeypatch):
    from fastapi import HTTPException
    from types import SimpleNamespace

    class Collection:
        async def insert_one(self, *_args, **_kw):
            return SimpleNamespace(acknowledged=False)

    class Database:
        discourse_jobs = Collection()

    monkeypatch.setattr(discourse, "_db", Database())
    body = discourse.DeliberateBody(prompt="Build the game system")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(discourse.deliberate_async(body, identity=ALICE))
    assert exc.value.status_code == 503
    assert not discourse._ACTIVE_DELIBERATIONS


def test_async_capacity_refuses_new_jobs_before_database(monkeypatch):
    from fastapi import HTTPException

    class ForbiddenDatabase:
        @property
        def discourse_jobs(self):
            raise AssertionError("Database used after capacity was exhausted")

    monkeypatch.setattr(discourse, "_db", ForbiddenDatabase())
    discourse._ACTIVE_DELIBERATIONS.update(f"{i:032x}" for i in range(
        discourse.MAX_ASYNC_DELIBERATIONS
    ))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(discourse.deliberate_async(
            discourse.DeliberateBody(prompt="Build the game system"), identity=ALICE
        ))
    assert exc.value.status_code == 503


def test_acknowledged_async_job_completes_and_frees_capacity(monkeypatch):
    from types import SimpleNamespace

    seen = []

    class Jobs:
        async def insert_one(self, row):
            seen.append(("admitted", row["status"]))
            return SimpleNamespace(acknowledged=True)

        async def update_one(self, query, update, **_kw):
            seen.append(("terminal", update["$set"]["status"]))
            return SimpleNamespace(acknowledged=True, matched_count=1)

    class Database:
        discourse_jobs = Jobs()

    async def fake_deliberation(*_a, **_kw):
        return {"winner_model": "m", "winner_score": 80}

    monkeypatch.setattr(discourse, "_db", Database())
    monkeypatch.setattr(discourse, "deliberate", fake_deliberation)

    async def scenario():
        result = await discourse.deliberate_async(
            discourse.DeliberateBody(prompt="Build the game system"), identity=ALICE
        )
        for _ in range(10):
            if not discourse._ACTIVE_DELIBERATIONS:
                break
            await asyncio.sleep(0)
        return result

    result = asyncio.run(scenario())
    assert result["status"] == "running"
    assert seen == [("admitted", "running"), ("terminal", "done")]
    assert not discourse._ACTIVE_DELIBERATIONS


def test_async_terminal_write_without_ack_marks_error(monkeypatch):
    from types import SimpleNamespace

    updates = []

    class Jobs:
        async def update_one(self, query, update, **_kw):
            updates.append(update["$set"])
            return SimpleNamespace(acknowledged=len(updates) > 1)

    class Database:
        discourse_jobs = Jobs()

    async def fake_deliberation(*_a, **_kw):
        return {"winner_model": "m", "winner_score": 80}

    monkeypatch.setattr(discourse, "_db", Database())
    monkeypatch.setattr(discourse, "deliberate", fake_deliberation)
    did = "a" * 32
    discourse._ACTIVE_DELIBERATIONS.add(did)
    asyncio.run(discourse._run_bg(
        did, discourse.DeliberateBody(prompt="Build the game system"), ALICE
    ))
    assert [row["status"] for row in updates] == ["done", "error"]
    assert not discourse._ACTIVE_DELIBERATIONS


@pytest.mark.parametrize("limit", [0, -1, 101, True, "10", 2.3])
def test_history_invalid_budget_rejected_before_db(monkeypatch, limit):
    from fastapi import HTTPException

    class ForbiddenDatabase:
        @property
        def discourse_log(self):
            raise AssertionError("database accessed before pagination validation")

    monkeypatch.setattr(discourse, "_db", ForbiddenDatabase())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(discourse.history(limit))
    assert exc.value.status_code == 422


def test_history_db_outage_is_not_an_empty_success(monkeypatch):
    from fastapi import HTTPException

    class Broken:
        def find(self, *_a, **_kw):
            raise ConnectionError("offline")

    class Database:
        discourse_log = Broken()

    monkeypatch.setattr(discourse, "_db", Database())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(discourse.history(identity=ALICE))
    assert exc.value.status_code == 503


def test_invalid_job_identity_does_not_access_database(monkeypatch):
    class ForbiddenDatabase:
        @property
        def discourse_jobs(self):
            raise AssertionError("invalid job ID reached storage")

    monkeypatch.setattr(discourse, "_db", ForbiddenDatabase())
    assert asyncio.run(discourse.get_result("../../../etc/passwd")) == {
        "error": "not found", "status": "unknown",
    }



def test_every_discourse_http_route_requires_authenticated_identity():
    """Prevent the private UI from silently reverting to anonymous endpoints."""
    from fastapi.routing import APIRoute

    routes = [route for route in discourse.router.routes if isinstance(route, APIRoute)]
    expected = {
        "/api/discourse/panel",
        "/api/discourse/deliberate",
        "/api/discourse/deliberate/async",
        "/api/discourse/result/{job_id}",
        "/api/discourse/jobs",
        "/api/discourse/history",
    }
    assert expected.issubset({route.path for route in routes})
    for route in routes:
        assert any(
            dependency.call is discourse.require_authenticated_identity
            for dependency in route.dependant.dependencies
        ), route.path


def test_private_result_uses_tenant_account_filter_and_redacts_worker_token(monkeypatch):
    """Even a valid job ID cannot bypass tenant ownership or leak CAS custody."""
    from types import SimpleNamespace

    job_id = "a" * 32

    class Jobs:
        async def find_one(self, query, projection):
            assert query == {"job_id": job_id, **ALICE}
            assert projection["owner_id"] == projection["tenant_id"] == 0
            return {
                "job_id": job_id, "status": "done", "content": "owned receipt",
                "run_token": "private-worker-cas",
                "tenant_id": ALICE["tenant_id"], "owner_id": ALICE["owner_id"],
            }

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    result = asyncio.run(discourse.get_result(job_id, identity=ALICE))
    assert result["content"] == "owned receipt"
    assert not {"run_token", "tenant_id", "owner_id"}.intersection(result)


def test_private_job_discovery_scopes_query_and_omits_prompt(monkeypatch):
    """Resume UI receives metadata only, never stored private provider inputs."""
    from types import SimpleNamespace

    job_id = "b" * 32

    class Cursor:
        def sort(self, *_args):
            return self

        def limit(self, *_args):
            return self

        async def to_list(self, *_args):
            return [{
                "job_id": job_id, "status": "done",
                "created_at": "2026-11-11T05:00:00+00:00",
                "prompt": "secret prompt", "run_token": "secret token",
            }]

    class Jobs:
        def find(self, query, projection):
            assert query == ALICE
            assert projection["job_id"] == projection["status"] == 1
            assert "prompt" not in projection and "run_token" not in projection
            return Cursor()

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    result = asyncio.run(discourse.list_jobs(identity=ALICE))
    assert result["count"] == 1
    assert result["jobs"] == [{
        "job_id": job_id, "status": "done",
        "created_at": "2026-11-11T05:00:00+00:00",
        "worker_continuity_verified": False,
    }]


def _authorized_catalog_for_direct_boundary_tests():
    return {"models": [
        {"id": "provider:model", "provider_id": "provider", "model_id": "model",
         "available": True, "selectable": True, "active": True},
    ]}


@pytest.mark.parametrize("selected,judge_key,maximum", [
    ([[]], None, 5),
    ([{"model": "provider:model"}], None, 5),
    ([None], None, 5),
    ({"model": "provider:model"}, None, 5),
    ("provider:model", None, 5),
    (None, [], 5),
    (None, {}, 5),
    (None, True, 5),
    (None, None, True),
    (None, None, 0),
    (None, None, 6),
    (["provider:model"] * 6, None, 5),
    (["x" * 386], None, 5),
])
def test_catalog_direct_caller_rejects_malformed_panel_before_dispatch(
    selected, judge_key, maximum,
):
    from core.discourse_catalog import PanelUnavailable, _catalog_panel

    with pytest.raises(PanelUnavailable):
        _catalog_panel(
            _authorized_catalog_for_direct_boundary_tests(),
            selected=selected, judge_key=judge_key, maximum=maximum,
        )


def test_catalog_direct_caller_preserves_valid_tuple_and_default_judge():
    from core.discourse_catalog import _catalog_panel

    catalog = _authorized_catalog_for_direct_boundary_tests()
    explicit = _catalog_panel(
        catalog, selected=("provider:model",), judge_key="provider:model",
    )
    assert tuple(model.key for model in explicit.models) == ("provider:model",)
    assert explicit.judge.key == "provider:model"
    automatic = _catalog_panel(catalog, selected=[], judge_key="")
    assert automatic.models == explicit.models
    assert automatic.judge == explicit.judge

@pytest.mark.parametrize("selected,judge_key,maximum", [
    ([{"id": "provider:model"}], None, 5),
    ([[]], None, 5),
    ({"id": "provider:model"}, None, 5),
    ("provider:model", None, 5),
    (("provider:model", None), None, 5),
    (["provider:model"] * 6, None, 5),
    (["x" * 386], None, 5),
    (None, {}, 5),
    (None, True, 5),
    (None, "x" * 386, 5),
    (None, None, True),
    (None, None, 0),
    (None, None, 6),
])
def test_tenant_panel_invalid_direct_request_has_no_engine_or_catalog_io(
    monkeypatch, selected, judge_key, maximum,
):
    from core import discourse_catalog

    def forbidden_engine():
        raise AssertionError("invalid direct request instantiated the engine")

    async def forbidden_catalog(*_args, **_kwargs):
        raise AssertionError("invalid direct request queried provider inventory")

    monkeypatch.setattr(discourse_catalog.EngineClient, "from_env", forbidden_engine)
    monkeypatch.setattr(discourse_catalog, "model_catalog", forbidden_catalog)
    with pytest.raises(discourse_catalog.PanelUnavailable):
        asyncio.run(discourse_catalog.tenant_panel(
            tenant_id="tenant", actor_id="owner", selected=selected,
            judge_key=judge_key, maximum=maximum,
        ))


def test_tenant_panel_valid_direct_request_preserves_authorized_catalog(monkeypatch):
    from core import discourse_catalog

    client = object()

    def fake_engine():
        return client

    async def fake_catalog(actual_client, *, tenant_id, actor_id):
        assert actual_client is client
        assert (tenant_id, actor_id) == ("tenant", "owner")
        return _authorized_catalog_for_direct_boundary_tests()

    monkeypatch.setattr(discourse_catalog.EngineClient, "from_env", fake_engine)
    monkeypatch.setattr(discourse_catalog, "model_catalog", fake_catalog)
    result = asyncio.run(discourse_catalog.tenant_panel(
        tenant_id="tenant", actor_id="owner", selected=["provider:model"],
        judge_key="provider:model", maximum=5,
    ))
    assert [model.key for model in result.models] == ["provider:model"]
    assert result.judge.key == "provider:model"

@pytest.mark.parametrize("tenant_id,actor_id", [
    ("", "owner"),
    ("tenant", ""),
    (None, "owner"),
    ("tenant", False),
    (" tenant", "owner"),
    ("tenant", "owner "),
    ("tenant\nother", "owner"),
    ("tenant", "owner\x00other"),
    ("x" * 513, "owner"),
    ("tenant", "x" * 513),
])
def test_tenant_panel_invalid_identity_rejected_before_engine_io(
    monkeypatch, tenant_id, actor_id,
):
    from core import discourse_catalog

    def forbidden_engine():
        raise AssertionError("invalid tenant identity instantiated the engine")

    async def forbidden_catalog(*_args, **_kwargs):
        raise AssertionError("invalid tenant identity queried provider inventory")

    monkeypatch.setattr(discourse_catalog.EngineClient, "from_env", forbidden_engine)
    monkeypatch.setattr(discourse_catalog, "model_catalog", forbidden_catalog)
    with pytest.raises(discourse_catalog.PanelUnavailable, match="invalid_panel_identity"):
        asyncio.run(discourse_catalog.tenant_panel(
            tenant_id=tenant_id, actor_id=actor_id,
        ))


@pytest.mark.parametrize("catalog", [
    None,
    [],
    {"models": [{}] * 65},
])
def test_catalog_direct_call_rejects_invalid_or_truncated_inventory(catalog):
    from core.discourse_catalog import PanelUnavailable, _catalog_panel

    with pytest.raises(PanelUnavailable, match="engine_model_inventory_unavailable"):
        _catalog_panel(catalog, selected=None, judge_key=None)


def test_catalog_direct_call_admits_bounded_inventory():
    from core.discourse_catalog import _catalog_panel

    panel = _catalog_panel(
        _authorized_catalog_for_direct_boundary_tests(),
        selected=("provider:model",), judge_key="provider:model",
    )
    assert panel.models[0].key == "provider:model"
    assert panel.judge.key == "provider:model"
