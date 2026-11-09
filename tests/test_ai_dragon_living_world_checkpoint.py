"""Renewable HMAC-secured endless original world play without fake state."""
from __future__ import annotations
from dataclasses import replace
import base64,json
import pytest

from skeleton.ai.webcrawler.dragon_living_world import (
    create_world,initial_state,replay,take_action,
)
from skeleton.ai.webcrawler.dragon_living_world_checkpoint import (
    SCHEMA,SECRET_SETTING,TTL_SECONDS,seal_checkpoint,open_checkpoint,
    continue_world,
)

OWNER="e"*64
NEIGHBOR="f"*64
SECRET="original-world-hmac-long-test-key-2026-10-11-64bytes!"


@pytest.fixture(autouse=True)
def configured_signing_key(monkeypatch):
    monkeypatch.setenv(SECRET_SETTING,SECRET)


def test_actual_endless_game_can_continuously_cross_multiple_192_action_windows():
    world=create_world(world_id=17,style="creative_sandbox")
    beginning=continue_world(world,OWNER,actions=("observe","forage")*80,
                             now=1_800_000_000)
    assert beginning["schema"]==SCHEMA
    assert beginning["cumulative_actions"]==160
    middle=continue_world(
        world,OWNER,previous_token=beginning["new_checkpoint"],
        actions=("rest","forage")*85,now=1_800_000_010)
    assert middle["cumulative_actions"]==330
    final=continue_world(
        world,OWNER,previous_token=middle["new_checkpoint"],
        actions=("observe","rest")*96,now=1_800_000_020)
    assert final["cumulative_actions"]==522
    assert final["player"]["turn"]==522
    state=open_checkpoint(world,final["new_checkpoint"],OWNER,
                          now=1_800_000_030)
    assert state.alive
    assert not state.endings_seen
    assert state.actions_played==522
    assert state.history_digest==final["current_history_digest"]
    assert final["expires_after_seconds"]==7*24*60*60
    assert "not durable backend archival" in final["scope"]


def test_player_can_revisit_postending_world_with_unaltered_faction_history():
    world=create_world(world_id=21,style="open_world_story")
    receipt=continue_world(world,OWNER,actions=(
        "help_settlers","help_settlers","ending_civic_union",
    ),now=1_800_000_000)
    next=continue_world(world,OWNER,
        previous_token=receipt["new_checkpoint"],
        actions=("forage","observe","wait","rest"),
        now=1_800_000_001)
    end=open_checkpoint(world,next["new_checkpoint"],OWNER,
                        now=1_800_000_002)
    assert end.endings_seen==("civic_union",)
    assert end.era==1
    assert "era_civic_union" in end.world_changes
    assert end.turn==7
    assert next["prior_history_digest"]==receipt["current_history_digest"]
    assert next["current_history_digest"]!=receipt["current_history_digest"]


def test_cross_account_or_tenant_checkpoint_reuse_is_never_accepted():
    world=create_world(world_id=100,style="survival_sandbox")
    token=seal_checkpoint(world,initial_state(world),OWNER,now=1_800_000_000)
    with pytest.raises(PermissionError):
        open_checkpoint(world,token,NEIGHBOR,now=1_800_000_001)
    with pytest.raises(PermissionError):
        open_checkpoint(world,token,"improper principal",now=1_800_000_001)


def test_original_session_cannot_jump_across_world_seed_variation_or_lifecycle():
    a=create_world(world_id=77,variant=1,style="open_world_story")
    token=seal_checkpoint(a,initial_state(a),OWNER,now=1_800_000_000)
    for mismatch in (
        create_world(world_id=78,variant=1,style="open_world_story"),
        create_world(world_id=77,variant=2,style="open_world_story"),
        create_world(world_id=77,variant=1,style="mutable_labyrinth"),
        create_world(world_id=77,variant=1,style="open_world_story",
                     lifecycle="unending"),
    ):
        with pytest.raises(PermissionError):
            open_checkpoint(mismatch,token,OWNER,now=1_800_000_001)


def test_minted_checkpoint_cannot_claim_forged_endings_or_add_free_items():
    world=create_world(world_id=31,style="post_story_wasteland")
    real=continue_world(world,OWNER,actions=("forage",),now=1_800_000_000)
    token=real["new_checkpoint"]
    body,mac=token.split(".",1)
    raw=base64.urlsafe_b64decode(body+"="*((-len(body))%4))
    record=json.loads(raw)
    record["player"]["wood"]=999
    record["player"]["endings_seen"]=["civic_union"]
    bad_body=base64.urlsafe_b64encode(json.dumps(
        record,sort_keys=True,separators=(",",":")).encode()).rstrip(b"=").decode()
    with pytest.raises(PermissionError):
        open_checkpoint(world,bad_body+"."+mac,OWNER,now=1_800_000_001)


def test_signed_original_world_checkpoint_has_expiry_and_no_future_creation():
    world=create_world(world_id=17)
    token=seal_checkpoint(world,initial_state(world),OWNER,now=1_800_000_000)
    assert open_checkpoint(world,token,OWNER,now=1_800_000_000)
    assert open_checkpoint(world,token,OWNER,now=1_800_000_000+TTL_SECONDS)
    with pytest.raises(PermissionError):
        open_checkpoint(world,token,OWNER,now=1_800_000_000+TTL_SECONDS+1)
    with pytest.raises(PermissionError):
        open_checkpoint(world,token,OWNER,now=1_799_999_999)


def test_world_checkpoint_secret_is_never_implicitly_defaulted(monkeypatch):
    world=create_world(world_id=0)
    monkeypatch.delenv(SECRET_SETTING,raising=False)
    with pytest.raises(RuntimeError):
        seal_checkpoint(world,initial_state(world),OWNER)
    monkeypatch.setenv(SECRET_SETTING,"short")
    with pytest.raises(RuntimeError):
        seal_checkpoint(world,initial_state(world),OWNER)


def test_untrusted_state_cannot_be_signed_with_out_of_range_resource_values():
    world=create_world(world_id=0)
    fake=replace(initial_state(world),wood=1000000)
    with pytest.raises(ValueError):
        seal_checkpoint(world,fake,OWNER,now=1_800_000_000)


def test_game_checkpoint_supports_revisiting_a_branch_but_not_lying_about_custody():
    world=create_world(world_id=200,style="open_world_story")
    saved=continue_world(world,OWNER,actions=(
        "help_settlers","help_settlers",
    ),now=1_800_000_000)
    civic=continue_world(world,OWNER,
        previous_token=saved["new_checkpoint"],
        actions=("ending_civic_union",),now=1_800_000_002)
    alternate=continue_world(world,OWNER,
        previous_token=saved["new_checkpoint"],
        actions=("forage","observe"),now=1_800_000_002)
    assert civic["current_history_digest"]!=alternate["current_history_digest"]
    assert civic["player"]["endings_seen"]==("civic_union",)
    assert alternate["player"]["endings_seen"]==()


@pytest.mark.parametrize("garbage",[
    "",".","x"*12001,"no.signature","unsafe+/characters.signed",
])
def test_malformed_token_encoding_is_refused_before_state_deserialization(garbage):
    world=create_world(world_id=0)
    with pytest.raises((ValueError,PermissionError)):
        open_checkpoint(world,garbage,OWNER,now=1_800_000_000)
