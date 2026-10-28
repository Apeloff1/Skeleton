"""Discover and invoke one hundred implemented game-builder capabilities.

The registry resolves only known local Python callables. It doesn't invent a
capability, execute downloaded source, or grant a build/acquisition permission.
"""
from __future__ import annotations
from dataclasses import dataclass
from importlib import import_module

@dataclass(frozen=True)
class Milestone:
    number:int
    domain:str
    operation:str
    module:str

_GROUPS=(
    ("World construction","game_scale_world",(
        "generate_room_graph","create_shortcuts","pack_world_rooms",
        "carve_world_rooms","connect_world_corridors","choose_distant_exit",
        "distribute_world_hazards","distribute_world_secrets",
        "select_world_checkpoints","generate_world_region")),
    ("NPC intelligence","game_scale_npc_ai",(
        "navigation_reachable","npc_astar","npc_dijkstra",
        "npc_line_of_sight","npc_find_cover","npc_patrol_route",
        "npc_chase","npc_flee","npc_separation","npc_choose_action")),
    ("Real-time combat","game_scale_combat",(
        "configure_weapon","create_weapon_loadout","combat_overlap",
        "melee_targets","fire_projectile","advance_projectiles",
        "apply_combat_damage","apply_knockback",
        "advance_combat_status","generate_combat_wave")),
    ("Economy and crafting","game_scale_economy",(
        "define_game_item","inventory_add","inventory_remove",
        "trade_inventory_item","craft_item","equip_character",
        "use_consumable","merchant_purchase","roll_loot_table",
        "simulate_game_economy")),
    ("Quests and narrative","game_scale_story",(
        "define_quest","schedule_quest_dependencies",
        "activate_available_quests","apply_quest_event","complete_quest",
        "available_dialogue_choices","advance_dialogue",
        "generate_dialogue_arc","update_faction_reputation","story_save_slot")),
    ("Original media assets","game_scale_assets",(
        "generate_game_palette","procedural_heightmap",
        "classify_terrain_biomes","procedural_sprite","sprite_to_svg",
        "animate_sprite","pack_sprite_atlas","synthesize_game_effect",
        "compose_game_melody","render_game_melody")),
    ("Playable balance","game_scale_balancing",(
        "estimate_level_clear_time","analyze_collectible_reachability",
        "compute_route_risk","evaluate_reward_distribution",
        "analyze_jump_gap_requirements","evaluate_game_balance",
        "tune_player_speed","tune_jump_physics","simulate_input_latency",
        "optimize_level_variants")),
    ("Visual level editing","game_scale_editor",(
        "paint_scene_tile","paint_scene_brush","flood_scene_region",
        "draw_scene_rectangle","relocate_player_spawn",
        "relocate_level_exit","copy_scene_region","paste_scene_region",
        "undo_scene_edit","redo_scene_edit")),
    ("Knowledge acquisition","game_scale_research",(
        "find_game_code_examples","identify_game_engine_families",
        "extract_game_glossary","extract_game_constraints",
        "summarize_game_topics","compare_engine_implementations",
        "retrieve_mechanic_examples","plan_game_knowledge_gaps",
        "compile_game_reference_pack","build_mechanic_learning_curriculum")),
    ("Campaign construction","game_scale_campaign",(
        "compose_game_campaign","validate_campaign_graph",
        "available_campaign_chapters","plan_campaign_path",
        "award_campaign_experience","upgrade_hero_skill",
        "complete_campaign_chapter","generate_game_campaign",
        "encode_campaign_save","export_campaign_archive")),
)
MILESTONES=tuple(
    Milestone(10*i+j+1,domain,operation,"."+module)
    for i,(domain,module,operations) in enumerate(_GROUPS)
    for j,operation in enumerate(operations)
)

def game_milestone_by_number(number:int):
    if not isinstance(number,int) or isinstance(number,bool) or not 1<=number<=100:
        raise ValueError("invalid implemented milestone number")
    milestone=MILESTONES[number-1]
    function=getattr(import_module(milestone.module,__package__),milestone.operation)
    if not callable(function):
        raise RuntimeError("registered milestone is not executable")
    return function

def grouped_game_milestones()->tuple[tuple[str,tuple[Milestone,...]],...]:
    return tuple((domain,MILESTONES[index*10:index*10+10])
                 for index,(domain,_,_) in enumerate(_GROUPS))
