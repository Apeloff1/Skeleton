"""Transactional world editor and bounded static route guidance."""
from pathlib import Path
import pytest
from skeleton.game.gameplay.ridge_rescue.schema import parse_world, world_dict
from skeleton.game.gameplay.ridge_rescue.custody import digest
from skeleton.game.gameplay.ridge_rescue.authoring import revise, verify_revision, AuthoringError, validate_reachability
from skeleton.game.gameplay.ridge_rescue.guidance import route, hint
from skeleton.game.gameplay.ridge_rescue.engine import initial_state

WORLD = parse_world((Path(__file__).resolve().parents[1] / "game/gameplay/ridge_rescue/cinder_ridge.json").read_bytes())

def test_reachable_original_source():
    validate_reachability(WORLD)
    assert route(WORLD, WORLD.start, WORLD.shelter)
    assert route(WORLD, WORLD.start, (-1, 0)) is None

def test_cas_authoring_revision_and_replay():
    operation = {"kind": "rename", "target": "world", "value": "Cinder Ridge Rebuilt"}
    revision = revise(WORLD, expected_sha256=digest(world_dict(WORLD)), operation=operation)
    assert revision["world"]["name"] == "Cinder Ridge Rebuilt"
    assert verify_revision(WORLD, revision, operation)
    assert WORLD.name == "Cinder Ridge - Last Signal"

def test_stale_revision_fails_without_mutation():
    before = world_dict(WORLD)
    with pytest.raises(AuthoringError, match="conflict"):
        revise(WORLD, expected_sha256="0" * 64, operation={"kind": "rename", "target": "world", "value": "Invalid"})
    assert world_dict(WORLD) == before

def test_invalid_edit_and_impassable_spawn_fail_closed():
    sha = digest(world_dict(WORLD))
    with pytest.raises(AuthoringError):
        revise(WORLD, expected_sha256=sha, operation={"kind": "set-tile", "target": [0, 0], "value": "#"})
    with pytest.raises(AuthoringError):
        revise(WORLD, expected_sha256=sha, operation={"kind": "set-resource-count", "target": "pine", "value": 100})

def test_revision_tamper_is_detected():
    operation = {"kind": "rename", "target": "world", "value": "New Ridge"}
    revision = revise(WORLD, expected_sha256=digest(world_dict(WORLD)), operation=operation)
    revision["sha256"] = "f" * 64
    with pytest.raises(AuthoringError):
        verify_revision(WORLD, revision, operation)

def test_guidance_is_explicitly_not_guaranteed():
    guidance = hint(WORLD, initial_state(WORLD))
    assert guidance["guaranteed"] is False
    assert guidance["kind"] in {"rescue", "gather", "shelter"}
