"""Actual native key/door/boss/chest narrative chapter compiler checks."""
from __future__ import annotations
from collections import deque
from hashlib import sha256
import json
import pytest

from skeleton.ai.webcrawler.dragon_game_blueprints import (
    design_campaign,W,H,PRNG,
)
from skeleton.ai.webcrawler.dragon_campaign_quests import (
    QUEST_SYMBOLS,place_quests,
)
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

PLAYABLE_QUEST_GENRES=(
    "top_down_adventure","roguelike","tactical_rpg",
    "survival_horror","educational",
)

def _before_gate(stage,start):
    queue=deque([start])
    seen={start}
    while queue:
        x,y=queue.popleft()
        for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if (nx,ny) in seen or not (0<=nx<W and 0<=ny<H):
                continue
            if stage.terrain[ny][nx] in "#^~D":
                continue
            seen.add((nx,ny));queue.append((nx,ny))
    return seen

@pytest.mark.parametrize("style",PLAYABLE_QUEST_GENRES)
@pytest.mark.parametrize("seed",[1,17,80,2345])
def test_chapter_key_gate_boss_and_chest_are_mechanically_reachable(style,seed):
    campaign=design_campaign(style=style,seed=seed,stages=4)
    assert len(campaign.stages)==4
    for n,stage in enumerate(campaign.stages):
        q=stage.quest
        assert q is not None
        assert q["chapter"]==n
        assert stage.quest["accessible_without_key"] is True
        if stage.quest["mode"] not in ("adventure","dungeon","tactics"):
            continue
        assert q["chests"]==1
        if n>=1:
            assert q["gate_requires_key"]
            assert len(q["key_locations"])==len(q["door_locations"])==1
            unlocked_area=_before_gate(stage,stage.start)
            for key in q["key_locations"]:
                assert tuple(key) in unlocked_area
                assert stage.terrain[key[1]][key[0]]=="K"
            for door in q["door_locations"]:
                assert stage.terrain[door[1]][door[0]]=="D"
        if n>=2:
            assert q["guardians"]==1
            for boss in q["guardian_locations"]:
                assert stage.terrain[boss[1]][boss[0]]=="B"
            assert stage.enemies>=q["guardians"]
        if q["mode"]=="adventure" and n>=2:
            assert q["caretakers"]==1

def test_quest_spec_uses_bounded_placement_and_rejects_malformed_map():
    board=[["." for x in range(W)] for y in range(H)]
    for x in range(W):
        board[0][x]=board[H-1][x]="#"
    for y in range(H):
        board[y][0]=board[y][W-1]="#"
    result=place_quests(board,rng=PRNG(55),chapter=3,mode="dungeon",
                        start=(3,3),goal=(26,17))
    assert result.gate_requires_key
    assert result.chests==1 and result.guardians==1
    assert result.evidence_hash
    with pytest.raises(ValueError):
        place_quests(board[:1],rng=PRNG(5),chapter=3,mode="dungeon",
                     start=(3,3),goal=(26,17))
    with pytest.raises(ValueError):
        place_quests(board,rng=PRNG(5),chapter=99,mode="dungeon",
                     start=(3,3),goal=(26,17))

def test_generated_native_engine_enforces_keys_doors_boss_and_quests():
    p=render_native_project(
        title="Dragon Native Quest",target_id="pc_linux",
        style="roguelike",candidate_id=sha256(b"quest").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )
    world=json.loads(p.files["dragon-campaign.json"])
    assert len(world["stages"])==4
    assert world["stages"][1]["quest"]["gate_requires_key"]
    code=p.files["src/main.c"]
    assert "game.keys==0" in code
    assert "game.quest_requires_key" in code
    assert "game.guardians==0" in code
    assert "game.key_collected" in code
    assert "game.chests_opened" in code
    assert "game.guardians=MAX(0,game.guardians-1)" in code
    assert "else if(t=='D'&&game.keys>0)" in code
    assert "else if(t=='K')" in code
    assert "else if(t=='C')" in code
    assert "else if(t=='N')" in code
