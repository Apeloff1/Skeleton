"""Optional chapter and cinematic planes integrate with nine-source engine recipe."""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.worlds.chapters import ChapterStore
from skeleton.jeeves.worlds.cinematics import CinematicsStore
from skeleton.jeeves.worlds.studio_engine import StudioEngineStore
from skeleton.jeeves.worlds.weather import WeatherStore
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore
from skeleton.testing.test_jeeves_world_studio_engine import ERA, fixture


def reject(code, callback):
    with pytest.raises(CanonError) as exc:
        callback()
    assert exc.value.code == code


def test_optional_planes_are_source_leased_and_integrated(tmp_path):
    engine = fixture(tmp_path)
    world = WorldStore(tmp_path).read("harbor")
    chapter_store = ChapterStore(tmp_path)
    chapters = chapter_store.propose("harbor", prompt="Original harbor chapters",
        chapters=[{"id": "harbor_story", "title": "The Harbor Story",
                   "summary": "Authored harbor journey",
                   "acts": [{"id": "act_" + str(i), "title": scene["title"],
                             "summary": "Authored scene grouping",
                             "scenes": [scene["id"]]}
                            for i, scene in enumerate(world["scenes"])]}])
    cd = chapter_store.publish("harbor", chapters, create=True)
    reject("studio_engine_optional_review_required",
           lambda: engine.inspect("harbor", ERA))
    chapter_store.approve("harbor", cd, "Reviewed original chapter structure")
    cinema_store = CinematicsStore(tmp_path)
    cinema = cinema_store.propose("harbor", prompt="Original harbor opening storyboard",
        sequences=[{"scene": world["start"], "beats": [{
            "id": "opening_beat", "cue": "arrival",
            "caption": "The harbor beacon glows.", "duration_ms": 1200}]}])
    digest = cinema_store.publish("harbor", cinema, create=True)
    reject("studio_engine_optional_review_required",
           lambda: engine.inspect("harbor", ERA))
    cinema_store.approve("harbor", digest, "Reviewed original storyboard")
    info = engine.inspect("harbor", ERA)
    assert info["optional_planes"] == ["chapters", "cinematics"]
    assert "chapters" in info["source_digests"]
    assert "cinematics" in info["source_digests"]
    stale = dict(info["source_digests"])
    stale["cinematics"] = "0" * 64
    reject("studio_engine_stale_source",
           lambda: engine.compile("harbor", stale, ERA))
    receipt = engine.compile("harbor", info["source_digests"], ERA)
    assert engine.verify("harbor") == receipt
    manifest = json.loads((tmp_path / receipt["manifest_file"]).read_text())
    assert set(manifest["optional_handoffs"]) == {"chapters", "cinematics"}
    assert all("chapter" in node and "cinematic_beats" in node
               for node in manifest["scene_nodes"])
    assert any(node["cinematic_beats"] for node in manifest["scene_nodes"])
    assert manifest["optional_handoffs"]["chapters"]["navigation_policy"] == (
        "actual_choice_graph_not_linearized")


def test_optional_source_revision_invalidates_existing_engine_receipt(tmp_path):
    engine = fixture(tmp_path)
    world = WorldStore(tmp_path).read("harbor")
    info = engine.inspect("harbor", ERA)
    engine.compile("harbor", info["source_digests"], ERA)
    chapters = ChapterStore(tmp_path)
    proposal = chapters.propose("harbor", prompt="Chapter structure",
        chapters=[{"id": "story", "title": "Story", "summary": "Original scenes",
                   "acts": [{"id": "act", "title": "Act", "summary": "The journey",
                             "scenes": [scene["id"] for scene in world["scenes"]]}]}])
    digest = chapters.publish("harbor", proposal, create=True)
    reject("studio_engine_optional_review_required",
           lambda: engine.verify("harbor"))
    chapters.approve("harbor", digest, "Reviewed")
    reject("studio_engine_receipt_mismatch", lambda: engine.verify("harbor"))


def test_weather_environment_requires_review_and_recompiles_engine(tmp_path):
    engine = fixture(tmp_path)
    world = WorldStore(tmp_path).read("harbor")
    initial = engine.inspect("harbor", ERA)
    engine.compile("harbor", initial["source_digests"], ERA)
    weather = WeatherStore(tmp_path)
    source = weather.propose(
        "harbor", prompt="Original harbor environmental conditions",
        scenes=[{
            "scene": scene["id"], "weather": "fog", "visibility": "limited",
            "description": "The harbor is misty near " + scene["title"],
        } for scene in sorted(world["scenes"], key=lambda item: item["id"])],
        overrides=[],
    )
    lease = weather.publish("harbor", source, create=True)
    reject("studio_engine_optional_review_required",
           lambda: engine.inspect("harbor", ERA))
    weather.approve("harbor", lease, "Reviewed original scene weather")
    reject("studio_engine_receipt_mismatch",
           lambda: engine.verify("harbor"))
    info = engine.inspect("harbor", ERA)
    assert info["optional_planes"] == ["weather"]
    assert "weather" in info["source_digests"]
    stale = dict(info["source_digests"])
    stale["weather"] = "0" * 64
    reject("studio_engine_stale_source",
           lambda: engine.compile("harbor", stale, ERA))
    receipt = engine.compile("harbor", info["source_digests"], ERA)
    assert engine.verify("harbor") == receipt
    manifest = json.loads((tmp_path / receipt["manifest_file"]).read_text())
    assert set(manifest["optional_handoffs"]) == {"weather"}
    assert all(node["weather"]["weather"] == "fog"
               for node in manifest["scene_nodes"])
    assert manifest["optional_handoffs"]["weather"]["source_digest"] == (
        info["source_digests"]["weather"])
