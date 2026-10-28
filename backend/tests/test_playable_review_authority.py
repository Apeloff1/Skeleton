"""Model review advice never grants runtime qualification or shipping authority."""
from copy import deepcopy
import json

import pytest

from backend.tests.test_playable_private_creation import project_boundary
from backend.tests.test_private_memory_boundary import memory_boundary
from routes import playable, playable_access, playable_pipeline, playable_repair
from routes.playable_htmlutils import model_review_projection, playable_html_digest


HTML = "<!DOCTYPE html><html><body><canvas></canvas><script>const best=0;best=1;</script></body></html>"


def _review(html=HTML):
    return {"available": True, "overall": 100, "playability": 100, "coherence": 100,
            "fun": 100, "polish": 100, "verdict": "ship", "source_digest": playable_html_digest(html),
            "shippable": True, "runtime_checked": True, "release_qualified": True}


@pytest.fixture
def quality_boundary(project_boundary, monkeypatch):
    client, headers, users, database = project_boundary
    for module in (playable_repair, playable_pipeline):
        monkeypatch.setattr(module, "_db", playable._db)
        client.app.include_router(module.router)
    async def distinct(*args, **kwargs):
        return []
    monkeypatch.setattr(database.asset_genesis, "distinct", distinct, raising=False)
    router = playable_access.project_router(prefix="/api/playable")
    @router.post("/{pid}/test-source-replacement")
    async def replace_source(pid: str, body: dict):
        await playable._db.playables.update_one({"playable_id": pid}, {"$set": body})
        return {"ok": True}
    client.app.include_router(router)
    row = {"playable_id": "reviewed-game", "owner_id": "alice@example.test", "tenant_id": "tenant-a",
           "html": HTML, "html_digest": playable_html_digest(HTML), "status": "ready", "version": 1,
           "brief": "Original example", "playability_score": 100, "evaluation": _review()}
    database.playables.rows.append(deepcopy(row))
    return client, headers, database


def test_actual_positive_judge_json_remains_advice_even_when_it_claims_runtime_flags(quality_boundary, monkeypatch):
    client, headers, db = quality_boundary
    calls = []
    def judge(*args, **kwargs):
        calls.append((args, kwargs))
        return {"content": json.dumps(_review()), "model": "fixture-judge"}
    monkeypatch.setattr(playable, "_llm_in_thread", judge)
    response = client.post("/api/playable/reviewed-game/evaluate", headers=headers["alice"])
    assert response.status_code == 200, response.text
    review = response.json()["evaluation"]
    assert review["overall"] == 100 and review["verdict"] == "ship"
    assert review["advisory_recommendation"] == "ship" and review["scope"] == "model_review"
    assert review["source_bound"] is True and review["available"] is True
    assert review["source_digest"] == playable_html_digest(HTML)
    assert review["shippable"] is review["runtime_checked"] is review["release_qualified"] is False
    assert len(calls) == 1 and calls[0][1]["max_output_tokens"] == 256
    assert db.playables.rows[0]["evaluation"]["shippable"] is False


def test_legacy_unsafe_flags_are_projected_without_rewriting_historical_records(quality_boundary):
    client, headers, db = quality_boundary
    original = deepcopy(db.playables.rows[0])
    for path in ("/api/playable/reviewed-game", "/api/playable/list"):
        response = client.get(path, headers=headers["alice"])
        assert response.status_code == 200
        doc = response.json() if not path.endswith("/list") else response.json()["playables"][0]
        assert doc["evaluation"]["overall"] == 100
        assert doc["evaluation"]["verdict"] == "ship"
        assert doc["evaluation"]["shippable"] is False
        assert doc["evaluation"]["runtime_checked"] is False
    assert db.playables.rows[0] == original
    assert original["evaluation"]["shippable"] is True
    assert client.get("/api/playable/reviewed-game", headers=headers["bob"]).status_code == 404


def test_html_replacement_invalidates_previous_review_but_preserves_scores(quality_boundary):
    client, headers, db = quality_boundary
    changed = HTML.replace("best=1", "best=2")
    response = client.post("/api/playable/reviewed-game/test-source-replacement", headers=headers["alice"],
                           json={"html": changed})
    assert response.status_code == 200, response.text
    row = client.get("/api/playable/reviewed-game", headers=headers["alice"]).json()
    assert row["html_digest"] == playable_html_digest(changed)
    assert row["evaluation"]["overall"] == 100
    assert row["evaluation"]["stale"] is True and row["evaluation"]["available"] is False
    assert row["evaluation"]["source_bound"] is False and row["evaluation"]["shippable"] is False
    assert db.playables.rows[0]["evaluation"]["source_digest"] == playable_html_digest(HTML)


@pytest.mark.parametrize("correct_digest", [False, True])
def test_atomic_source_and_review_requires_matching_bytes_and_cannot_forge_release(quality_boundary, correct_digest):
    client, headers, _ = quality_boundary
    changed = HTML.replace("best=1", "best=3")
    review = _review(changed if correct_digest else HTML)
    response = client.post("/api/playable/reviewed-game/test-source-replacement", headers=headers["alice"],
                           json={"html": changed, "html_digest": "0" * 64, "evaluation": review})
    assert response.status_code == 200
    row = client.get("/api/playable/reviewed-game", headers=headers["alice"]).json()
    assert row["html_digest"] == playable_html_digest(changed)
    assert row["evaluation"]["available"] is correct_digest
    assert row["evaluation"]["source_bound"] is correct_digest
    assert row["evaluation"]["stale"] is not correct_digest
    assert row["evaluation"]["shippable"] is row["evaluation"]["runtime_checked"] is False


def test_identical_source_does_not_unnecessarily_invalidate_a_bound_review(quality_boundary):
    client, headers, _ = quality_boundary
    response = client.post("/api/playable/reviewed-game/test-source-replacement", headers=headers["alice"],
                           json={"html": HTML})
    assert response.status_code == 200
    review = client.get("/api/playable/reviewed-game", headers=headers["alice"]).json()["evaluation"]
    assert review["available"] is True and review["stale"] is False
    assert review["shippable"] is False


@pytest.mark.parametrize("source_report", [False, True])
def test_pipeline_does_not_claim_playtest_completion_from_model_or_source_booleans(quality_boundary, source_report):
    client, headers, db = quality_boundary
    if source_report:
        db.game_kb.rows.append({"game_id": "reviewed-game", "owner_id": "alice@example.test", "tenant_id": "tenant-a",
                               "artifacts": {"qa_report": {"score": 100, "runtime_checked": True, "shippable": True}}})
    response = client.get("/api/playable/reviewed-game/pipeline", headers=headers["alice"])
    assert response.status_code == 200, response.text
    stage = next(stage for stage in response.json()["stages"] if stage["key"] == "qa")
    assert stage["status"] == "partial"
    assert stage["runtime_checked"] is stage["shippable"] is False
    assert "unqualified" in stage["detail"]


def test_job_projection_clears_legacy_release_claims_but_other_collections_remain_data(quality_boundary):
    client, headers, db = quality_boundary
    db.playable_jobs.rows.append({"job_id": "legacy-review", "job_status": "done", "evaluation": _review(),
                                  "html_digest": playable_html_digest(HTML), "owner_id": "alice@example.test", "tenant_id": "tenant-a"})
    job = client.get("/api/playable/job/legacy-review", headers=headers["alice"]).json()
    assert job["evaluation"]["shippable"] is False
    source = {"evaluation": _review()}
    assert playable_access._review_record(source, "game_kb") is source
    assert playable_access._review_update({"$set": source}, "game_kb") == {"$set": source}


def test_unbound_or_forged_review_does_not_make_any_runtime_claim():
    incoming = _review()
    incoming.update(runtime_checked=True, shippable=True, release_qualified=True,
                    trusted_runtime={"passed": True})
    projected = model_review_projection(incoming, current_source_digest="f" * 64)
    assert projected["overall"] == 100 and projected["verdict"] == "ship"
    assert projected["stale"] is True and projected["available"] is False
    assert projected["shippable"] is projected["runtime_checked"] is projected["release_qualified"] is False
    assert incoming["shippable"] is True
