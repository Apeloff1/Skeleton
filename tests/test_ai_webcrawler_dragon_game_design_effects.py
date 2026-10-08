"""Game design difficulty, hero and theme alter actual emitted game code."""
from __future__ import annotations
from hashlib import sha256
import json
import pytest
from skeleton.ai.webcrawler.dragon_game_design import starter_design,parse_design
from skeleton.ai.webcrawler.dragon_game_blueprints import design_campaign
from skeleton.ai.webcrawler.dragon_game_fitness import choose_campaign
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project

def emit(config):
    design=parse_design(config)
    return render_native_project(
        title=design.title,target_id=design.target,style=design.genre,
        candidate_id=design.digest,
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True,
        design=design,
    )

def test_difficulty_changes_enemy_spawn_budget_and_campaign_fingerprint():
    easy=design_campaign(style="roguelike",seed=42,difficulty=1)
    hard=design_campaign(style="roguelike",seed=42,difficulty=10)
    assert easy.id!=hard.id
    assert sum(s.enemies for s in hard.stages)>=sum(s.enemies for s in easy.stages)
    assert all(s.difficulty>=a.difficulty for s,a in zip(hard.stages,easy.stages))
    assert hard==design_campaign(style="roguelike",seed=42,difficulty=10)
    with pytest.raises(ValueError):
        design_campaign(style="roguelike",seed=42,difficulty=True)
    with pytest.raises(ValueError):
        design_campaign(style="roguelike",seed=42,difficulty=11)

def test_theme_palette_native_art_and_hero_silhouettes_are_actually_compiled():
    base=starter_design(title="Dragon Three Eras",genre="roguelike",seed=19)
    base.update({"hero":"hatchling","quest_theme":"ancient_ruins","difficulty":2})
    a=emit(base)
    base.update({"hero":"astronaut","quest_theme":"space","difficulty":9})
    b=emit(base)
    assert a.digest!=b.digest
    a_world=json.loads(a.files["dragon-campaign.json"])
    b_world=json.loads(b.files["dragon-campaign.json"])
    assert sum(s["enemies"] for s in b_world["stages"])>=sum(
        s["enemies"] for s in a_world["stages"])
    head_a=a.files["include/dragon_campaign.h"]
    head_b=b.files["include/dragon_campaign.h"]
    assert "#define HERO_STYLE 0" in head_a
    assert "#define HERO_STYLE 4" in head_b
    assert "#define DESIGN_DIFFICULTY 2" in head_a
    assert "#define DESIGN_DIFFICULTY 9" in head_b
    assert "THEME_ACCENT[3]" in head_b
    assert head_a!=head_b
    src=b.files["src/main.c"]
    assert "HERO_STYLE==4" in src
    assert "THEME_ACCENT[0]" in src
    assert "DESIGN_DIFFICULTY*.035f" in src

def test_fps_has_real_difficulty_ai_and_theme_materials():
    c=starter_design(title="Dragon FPS Challenge",genre="first_person_shooter",seed=1)
    c.update({"quest_theme":"volcano","difficulty":9,"hero":"robot"})
    build=emit(c)
    engine=build.files["src/main.c"]
    header=build.files["include/dragon_campaign.h"]
    assert "#define DESIGN_DIFFICULTY 9" in header
    assert "THEME_ACCENT[3]" in header
    assert "DESIGN_DIFFICULTY*.0008f" in engine
    assert "DESIGN_DIFFICULTY/3" in engine
    assert "THEME_ACCENT[0]" in engine
    assert build.files["dragon-game-design.json"]
