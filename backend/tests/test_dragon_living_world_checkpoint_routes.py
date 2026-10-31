"""Dragon Academy living-world signed checkpoint API security and continuity."""
from __future__ import annotations
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes import dragon_academy as route
from skeleton.ai.webcrawler.dragon_living_world_checkpoint import SECRET_SETTING

SECRET="non-production-test-secret-for-original-living-world-checkpoints-2026"


def editor(email="world-maker@example.test",tenant="studio-account"):
    return route._native_source_editor({
        "email":email,"role":"editor","tenant_id":tenant,
    })


@pytest.fixture(autouse=True)
def configure_test_key(monkeypatch):
    monkeypatch.setenv(SECRET_SETTING,SECRET)


def request(moves=(),token=None):
    return route.NativeLivingCheckpointRequest(
        world_id=77,variation=4,style="open_world_story",lifecycle="postgame",
        token=token,moves=list(moves),
    )


def test_creator_can_use_signed_checkpoints_for_continuation_past_192_moves():
    owner=editor()
    first=route.native_living_world_checkpoint_advance(
        request(moves=("observe","forage")*90),owner=owner)
    assert first["ok"]
    assert first["cumulative_actions"]==180
    assert first["current"]["playable"]
    token=first["new_checkpoint"]
    assert "." in token
    second=route.native_living_world_checkpoint_advance(
        request(moves=("wait","rest")*90,token=token),owner=owner)
    assert second["cumulative_actions"]==360
    assert second["current"]["player"]["turn"]==360
    assert second["prior_history_digest"]==first["current_history_digest"]
    third=route.native_living_world_checkpoint_inspect(
        route.NativeLivingCheckpointInspectRequest(
            world_id=77,variation=4,style="open_world_story",
            lifecycle="postgame",token=second["new_checkpoint"],
        ),owner=owner)
    assert third["ok"]
    assert third["checkpoint_bound_to_authenticated_owner"]
    assert third["current"]["player"]["turn"]==360


def test_creator_can_make_an_ending_then_keep_playing_same_world_after_checkpoint():
    owner=editor()
    completed=route.native_living_world_checkpoint_advance(
        request(moves=(
            "help_settlers","help_settlers","ending_civic_union",
        )),owner=owner)
    assert completed["current"]["has_completed_ending"]
    assert completed["current"]["postgame_active"]
    continued=route.native_living_world_checkpoint_advance(
        request(moves=("forage","rest"),
                token=completed["new_checkpoint"]),owner=owner)
    assert continued["current"]["player"]["endings_seen"]==["civic_union"]
    assert continued["current"]["player"]["turn"]==5
    assert continued["current"]["playable"]


def test_signed_creator_checkpoint_is_bound_to_owner_tenant_and_seed():
    creator=editor()
    other=editor(email="attacker@example.test")
    issued=route.native_living_world_checkpoint_advance(
        request(moves=("forage",)),owner=creator)
    token=issued["new_checkpoint"]
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_checkpoint_inspect(
            route.NativeLivingCheckpointInspectRequest(
                world_id=77,variation=4,style="open_world_story",
                lifecycle="postgame",token=token,
            ),owner=other)
    assert denied.value.status_code==403
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_checkpoint_inspect(
            route.NativeLivingCheckpointInspectRequest(
                world_id=78,variation=4,style="open_world_story",
                lifecycle="postgame",token=token,
            ),owner=creator)
    assert denied.value.status_code==403


def test_no_checkpoint_signing_key_is_a_503_not_an_insecure_default(monkeypatch):
    monkeypatch.delenv(SECRET_SETTING,raising=False)
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_checkpoint_advance(request(),owner=editor())
    assert denied.value.status_code==503


@pytest.mark.parametrize("endpoint",[
    "/api/dragon-academy/native/production/worlds/checkpoint/advance",
    "/api/dragon-academy/native/production/worlds/checkpoint/inspect",
])
def test_long_lived_world_sessions_never_allow_untrusted_viewers(endpoint):
    found=next(x for x in route.router.routes if x.path==endpoint)
    assert any(dep.call is route._native_source_editor
               for dep in found.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"untrusted@example.test","role":"viewer",
            "tenant_id":"studio-account",
        })
    assert denied.value.status_code==403



def test_checkpoint_rejects_distinct_signature_strings_with_identical_decoded_mac():
    """Unused base64 pad bits cannot create alternate accepted signed tokens."""
    import base64

    owner = editor()
    token = route.native_living_world_checkpoint_advance(
        request(moves=("forage",)), owner=owner
    )["new_checkpoint"]
    prefix, signature = token.split(".", 1)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    alternate_last = alphabet[alphabet.index(signature[-1]) ^ 1]
    forged_signature = signature[:-1] + alternate_last

    def decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * ((-len(value)) % 4))

    # This is a real malleability probe, not an invalid-MAC corruption.
    assert signature != forged_signature
    assert decode(signature) == decode(forged_signature)
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_checkpoint_advance(
            request(token=prefix + "." + forged_signature, moves=("observe",)),
            owner=owner,
        )
    assert denied.value.status_code in (403, 422)


def test_invalid_tampered_token_and_illegal_new_world_action_are_refused():
    first=route.native_living_world_checkpoint_advance(request(),owner=editor())
    token=first["new_checkpoint"]
    tampered=token[:-1]+("A" if token[-1]!="A" else "B")
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_checkpoint_advance(
            request(token=tampered,moves=("observe",)),owner=editor())
    assert denied.value.status_code in (403,422)
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_checkpoint_advance(
            request(token=token,moves=("ending_starfarer",)),owner=editor())
    assert denied.value.status_code==422


@pytest.mark.parametrize("bad",[
    {"token":"too short"},
    {"token":7},
    {"token":"_"*12001},
    {"moves":["forage"]*193},
    {"moves":[1,2,3]},
])
def test_checkpoint_input_has_strict_bounded_api_envelope(bad):
    with pytest.raises(ValidationError):
        request(**bad)
