"""Authority rules for fictional survey fixes, minimap camera, and event commit."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.forge.game_frontier_event_authority import (
    CanonRules, EnvironmentalLedger, EventAuthorityError, QuestSpec, SaveState,
)
from skeleton.forge.game_frontier_rpg_events import (
    EnvironmentalTrigger, RPGEventAction, RPGEventPage, evaluate_environment_events,
)
from skeleton.frontier_nav.gps import (
    FictionalMapLayer, FictionalPortal, GPSRejected, follow_portal, opening_camera,
    pan_minimap, validate_fictional_portals, zoom_minimap,
)
from skeleton.frontier_nav.survey_approval import (
    FICTIONAL_DATUM, BaselineRecord, ControlStation, SightingRecord, SurveyAuthorityError,
    SurveyBook,
)

KEY = b"era-authority-key-0001"


def _canon():
    return CanonRules.build((
        QuestSpec("lantern-watch", ("notice", "sheltered"), era_engines=frozenset({"meadow"})),
    ))


def _page(page_id: str, priority: int, kind: str = "start_quest", value: str = "", cooldown: int = 0):
    return RPGEventPage(
        page_id, priority,
        (EnvironmentalTrigger("rain_mm_h", "above", 1.0),),
        (RPGEventAction(kind, "quest", "lantern-watch", value),),
        cooldown_ms=cooldown,
    )


def _ledger():
    return EnvironmentalLedger(SaveState("meadow"), _canon(), keys={"warden": KEY})


def _book():
    book = SurveyBook()
    book.put_baseline(BaselineRecord(
        "meadow-baseline", FICTIONAL_DATUM, "Third Lantern Era",
        "fictional bubble sextant", "Mara Quill", "game metres only",
        {
            "station-oak": ControlStation("station-oak", 0, 0, 12),
            "station-cairn": ControlStation("station-cairn", 10, 10, 12),
        },
    ))
    book.put_sighting(SightingRecord("sight-oak", "meadow-baseline", "station-oak", 90, 10, 0.4))
    book.put_sighting(SightingRecord("sight-cairn", "meadow-baseline", "station-cairn", 180, 10, 0.4))
    return book


def test_proposal_does_not_mutate_quest_canon_or_save():
    ledger = _ledger()
    before = ledger.canon_digest()
    proposal = ledger.propose(
        _page("rain", 5), current={"rain_mm_h": 4}, actor="scout", now_ms=1000,
    )
    assert proposal.decision.authority == "proposal_only_no_world_mutation"
    assert ledger.status(proposal.proposal_id) == "proposed"
    assert ledger.state.revision == 0
    assert ledger.state.quest_stage == {}
    assert ledger.canon_digest() == before


def test_commit_requires_authority_matching_digest_and_rejects_stale_and_replay():
    ledger = _ledger()
    proposal = ledger.propose(
        _page("rain", 5), current={"rain_mm_h": 4}, actor="scout", now_ms=1000,
    )
    with pytest.raises(EventAuthorityError, match="unauthorized commit"):
        ledger.commit(proposal.proposal_id, actor="thief", expected_canon_digest=ledger.canon_digest(), now_ms=2000)
    assert ledger.state.revision == 0
    with pytest.raises(EventAuthorityError, match="stale canon digest"):
        ledger.commit(proposal.proposal_id, actor="warden", expected_canon_digest="0" * 64, now_ms=2000)
    assert ledger.state.revision == 0
    result = ledger.commit(
        proposal.proposal_id, actor="warden",
        expected_canon_digest=proposal.canon_digest, now_ms=2000,
    )
    assert result.state.quest_stage["lantern-watch"] == 0
    assert result.state.revision == 1
    assert ledger.canon_digest() != proposal.canon_digest
    with pytest.raises(EventAuthorityError, match="double-submit"):
        ledger.commit(
            proposal.proposal_id, actor="warden",
            expected_canon_digest=ledger.canon_digest(), now_ms=3000,
        )
    assert ledger.state.revision == 1


def test_lower_priority_conflict_is_rejected_without_mutation():
    ledger = _ledger()
    low = ledger.propose(_page("late", 1), current={"rain_mm_h": 4}, actor="scout", now_ms=1000)
    high = ledger.propose(_page("early", 20), current={"rain_mm_h": 4}, actor="scout", now_ms=1000)
    digest = ledger.canon_digest()
    with pytest.raises(EventAuthorityError, match="conflicting higher-priority event"):
        ledger.commit(low.proposal_id, actor="warden", expected_canon_digest=digest, now_ms=2000)
    assert ledger.state.revision == 0
    committed = ledger.commit(high.proposal_id, actor="warden", expected_canon_digest=digest, now_ms=2000)
    assert committed.state.quest_stage["lantern-watch"] == 0
    with pytest.raises(EventAuthorityError, match="stale canon digest"):
        ledger.commit(low.proposal_id, actor="warden", expected_canon_digest=digest, now_ms=3000)


def test_commit_enforces_cooldown_against_the_current_digest():
    ledger = _ledger()
    page = _page("rain", 5, cooldown=5000)
    decision = evaluate_environment_events(
        (page,), current={"rain_mm_h": 4}, now_ms=1000,
    ).accepted[0]
    ledger.state = SaveState("meadow", last_fired_ms={page.page_id: 1000})
    proposal = ledger.stage(page, decision, actor="scout")
    with pytest.raises(EventAuthorityError, match="cooldown"):
        ledger.commit(
            proposal.proposal_id, actor="warden",
            expected_canon_digest=ledger.canon_digest(), now_ms=2000,
        )
    assert ledger.state.revision == 0
    with pytest.raises(EventAuthorityError, match="event conditions are not met"):
        ledger.propose(page, current={"rain_mm_h": 4}, actor="scout", now_ms=2000)


def test_fix_refuses_unapproved_and_consumed_sightings():
    book = _book()
    with pytest.raises(SurveyAuthorityError, match="unapproved sighting cannot enter a navigation fix"):
        book.solve(["sight-oak", "sight-cairn"])
    assert all(item.state == "draft" for item in book.sightings.values())
    with pytest.raises(SurveyAuthorityError, match="approve the baseline metadata first"):
        book.approve_sighting("sight-oak", "Ada Quill")
    book.approve_baseline("meadow-baseline", "Ada Quill")
    assert book.baselines["meadow-baseline"].approved_by == "Ada Quill"
    with pytest.raises(SurveyAuthorityError, match="actor identity required"):
        book.approve_sighting("sight-oak", "  ")
    book.approve_sighting("sight-oak", "Ada Quill")
    book.approve_sighting("sight-cairn", "Ada Quill")
    fix = book.solve(["sight-oak", "sight-cairn"])
    assert (fix.x, fix.y, fix.z) == (10, 0, 12)
    assert fix.region == "meadow-baseline"
    assert book.sightings["sight-oak"].state == "consumed"
    with pytest.raises(SurveyAuthorityError, match="consumed sighting cannot enter a navigation fix"):
        book.solve(["sight-oak"])


def test_earth_datum_is_rejected():
    with pytest.raises(SurveyAuthorityError, match="fictional planet frame"):
        BaselineRecord(
            "earth", "WGS84", "2026-01-01", "gnss", "Ada", "",
            {"a": ControlStation("a", 0, 0, 0)},
        )


def test_minimap_zoom_portal_and_clamp_are_deterministic():
    layers = (
        FictionalMapLayer("crypt", "underground", 24, 24, -18),
        FictionalMapLayer("meadow", "surface", 32, 32, 12),
        FictionalMapLayer("aether-isle", "sky-island", 16, 16, 240),
    )
    portals = validate_fictional_portals(layers, (
        FictionalPortal("well", "meadow", 8, 8, "crypt", 4, 4, True),
        FictionalPortal("spire", "meadow", 20, 6, "aether-isle", 3, 3, True),
    ))
    camera = opening_camera(layers)
    assert camera.layer_id == "meadow"
    zoomed = zoom_minimap(camera, layers[1], 1)
    assert zoomed.zoom == 2
    assert zoom_minimap(zoomed, layers[1], 1).zoom == 4
    capped = camera
    for _ in range(8):
        capped = zoom_minimap(capped, layers[1], 1)
    assert capped.zoom == 16
    assert zoom_minimap(capped, layers[1], 1).zoom == 16
    tight = camera
    for _ in range(3):
        tight = zoom_minimap(tight, layers[1], 1)
    shoved = tight
    for _ in range(40):
        shoved = pan_minimap(shoved, layers[1], -1, -1)
    assert shoved.center_x == 0 and shoved.center_y == 0
    assert pan_minimap(shoved, layers[1], -1, -1) == shoved
    underground = follow_portal(camera, layers, portals, "well")
    assert (underground.layer_id, underground.center_x, underground.center_y) == ("crypt", 4, 4)
    back = follow_portal(underground, layers, portals, "well")
    assert (back.layer_id, back.center_x, back.center_y) == ("meadow", 8, 8)
    sky = follow_portal(camera, layers, portals, "spire")
    assert sky.layer_id == "aether-isle"
    with pytest.raises(GPSRejected, match="does not match fictional elevation"):
        FictionalMapLayer("bad", "surface", 8, 8, -5)
    with pytest.raises(GPSRejected, match="portal is not on this layer"):
        follow_portal(underground, layers, portals, "spire")


def test_http_approval_commit_and_minimap_round_trip():
    from routes.game_frontier_cockpit import router
    from routes.gameforge_auth import get_current_user
    from core.frontier_cockpit import reset_service

    reset_service()
    app = FastAPI()
    app.include_router(router, prefix="/api")
    editor = {"email": "ada@studio.test", "role": "editor", "tenant_id": "studio"}
    viewer = {"email": "ada@studio.test", "role": "viewer", "tenant_id": "studio"}
    app.dependency_overrides[get_current_user] = lambda: editor
    with TestClient(app) as client:
        world = client.get("/api/game-frontier-cockpit/worlds/meadow-realm")
        assert world.status_code == 200
        body = world.json()
        assert body["device_geolocation"] is False
        assert body["datum"] == FICTIONAL_DATUM
        assert "latitude" not in world.text and "longitude" not in world.text
        assert body["events"]["revision"] == 0
        assert body["events"]["proposals"][0]["mutated"] is False
        digest = body["events"]["canon_digest"]
        proposal_id = body["events"]["proposals"][0]["proposal_id"]
        app.dependency_overrides[get_current_user] = lambda: viewer
        denied = client.post(
            "/api/game-frontier-cockpit/worlds/meadow-realm/baselines/meadow-baseline/approve",
            json={},
        )
        assert denied.status_code == 403
        app.dependency_overrides[get_current_user] = lambda: editor
        assert client.post(
            "/api/game-frontier-cockpit/worlds/meadow-realm/baselines/meadow-baseline/approve",
            json={"actor": "ada@studio.test"},
        ).status_code == 200
        for sighting in ("sight-oak", "sight-cairn"):
            approved = client.post(
                f"/api/game-frontier-cockpit/worlds/meadow-realm/sightings/{sighting}/approve",
                json={"actor": "ada@studio.test"},
            )
            assert approved.status_code == 200, approved.text
        early = client.post(
            "/api/game-frontier-cockpit/worlds/meadow-realm/fixes",
            json={"sighting_ids": ["sight-oak"], "actor": "someone-else"},
        )
        assert early.status_code == 403
        fixed = client.post(
            "/api/game-frontier-cockpit/worlds/meadow-realm/fixes",
            json={"sighting_ids": ["sight-oak", "sight-cairn"], "actor": "ada@studio.test"},
        )
        assert fixed.status_code == 200, fixed.text
        assert fixed.json()["fix"]["x"] == 10
        assert fixed.json()["fix"]["measured_earth_position"] is False
        again = client.post(
            "/api/game-frontier-cockpit/worlds/meadow-realm/fixes",
            json={"sighting_ids": ["sight-oak"], "actor": "ada@studio.test"},
        )
        assert again.status_code == 409
        assert "consumed" in again.json()["detail"]["message"]
        committed = client.post(
            f"/api/game-frontier-cockpit/worlds/meadow-realm/events/{proposal_id}/commit",
            json={"expected_canon_digest": digest, "actor": "ada@studio.test"},
        )
        assert committed.status_code == 200, committed.text
        assert committed.json()["events"]["revision"] == 1
        assert committed.json()["events"]["quest_stage"]["lantern-watch"] == 0
        assert committed.json()["events"]["quests"][0]["stages"] == ["notice", "sheltered"]
        replay = client.post(
            f"/api/game-frontier-cockpit/worlds/meadow-realm/events/{proposal_id}/commit",
            json={"expected_canon_digest": committed.json()["events"]["canon_digest"], "actor": "ada@studio.test"},
        )
        assert replay.status_code == 409
        assert "double-submit" in replay.json()["detail"]["message"]
        stale = client.post(
            "/api/game-frontier-cockpit/worlds/meadow-realm/events/propose",
            json={"preset": "advance-lantern", "signal": "rain_mm_h", "current_value": 4, "actor": "ada@studio.test"},
        )
        assert stale.status_code == 200
        assert stale.json()["events"]["revision"] == 1
        new_id = next(item["proposal_id"] for item in stale.json()["events"]["proposals"] if item["status"] == "proposed")
        wrong = client.post(
            f"/api/game-frontier-cockpit/worlds/meadow-realm/events/{new_id}/commit",
            json={"expected_canon_digest": digest, "actor": "ada@studio.test"},
        )
        assert wrong.status_code == 409
        assert "stale canon digest" in wrong.json()["detail"]["message"]
        moved = client.post(
            "/api/game-frontier-cockpit/worlds/meadow-realm/camera/portal",
            json={"portal_id": "spire", "actor": "ada@studio.test"},
        )
        assert moved.status_code == 200
        assert moved.json()["map"]["camera"]["layer_id"] == "aether-isle"
        zoomed = client.post(
            "/api/game-frontier-cockpit/worlds/meadow-realm/camera/zoom",
            json={"direction": 1, "actor": "ada@studio.test"},
        )
        assert zoomed.json()["map"]["camera"]["zoom"] == 2
        panned = client.post(
            "/api/game-frontier-cockpit/worlds/meadow-realm/camera/pan",
            json={"dx": -1, "dy": -1, "actor": "ada@studio.test"},
        )
        camera = panned.json()["map"]["camera"]
        assert camera["center_x"] >= 0 and camera["center_y"] >= 0
        assert camera["layer_id"] == "aether-isle"
