from __future__ import annotations
"""
Full Zaibatsu room registry — studio + engineering + content + ops.
Every room is first-class: logs, twins, DNA, rep, VOX targets.
"""

from typing import Any, Dict, List

# Inline studio set to avoid circular imports with exocortex
STUDIO_ROOMS = {
    "boardroom": {"division": "Leadership", "role": "executive_consensus"},
    "evaluation_room": {"division": "Leadership", "role": "feature_eval_gate"},
    "design_room": {"division": "Product", "role": "systems_design"},
    "narrative_room": {"division": "Product", "role": "story_quest"},
    "ux_room": {"division": "Product", "role": "interface_flow"},
    "code_room": {"division": "Engineering", "role": "implementation"},
    "math_room": {"division": "Engineering", "role": "exocortex_math"},
    "runtime_room": {"division": "Engineering", "role": "agent_runtime"},
    "build_room": {"division": "Engineering", "role": "pipeline_build"},
    "qa_room": {"division": "Quality", "role": "test_regression"},
    "security_room": {"division": "Quality", "role": "zaibatsu_defense"},
    "world_room": {"division": "Content", "role": "world_gen"},
    "asset_room": {"division": "Content", "role": "mesh_sprite_audio"},
    "balance_room": {"division": "Content", "role": "economy_combat"},
    "neuro_room": {"division": "Experience", "role": "affect_jeeves"},
    "calendar_room": {"division": "Experience", "role": "schedule_era"},
}

# Engineering / game systems (extends prior assignments)
ENGINE_ROOMS: Dict[str, Dict[str, Any]] = {
    "game_engine": {"division": "Engineering", "role": "main_loop", "coders": ["niklas_frykholm", "john_carmack", "casey_muratori"]},
    "entity_component_system": {"division": "Engineering", "role": "ecs", "coders": ["mike_acton", "niklas_frykholm", "casey_muratori"]},
    "physics_core": {"division": "Engineering", "role": "simulation", "coders": ["john_carmack", "fabian_giesen", "casey_muratori"]},
    "rendering": {"division": "Engineering", "role": "frame_graph", "coders": ["fabian_giesen", "niklas_frykholm", "john_carmack"]},
    "shader_system": {"division": "Engineering", "role": "shaders", "coders": ["fabian_giesen", "john_carmack", "niklas_frykholm"]},
    "networking": {"division": "Engineering", "role": "replication", "coders": ["john_carmack", "casey_muratori", "niklas_frykholm"]},
    "tools_pipeline": {"division": "Engineering", "role": "asset_cook", "coders": ["niklas_frykholm", "jonathan_blow", "casey_muratori"]},
    "ai_navigation": {"division": "Engineering", "role": "navmesh", "coders": ["andrej_karpathy", "john_carmack", "casey_muratori"]},
    "serialization": {"division": "Engineering", "role": "binary_io", "coders": ["fabian_giesen", "casey_muratori", "mike_acton"]},
    "scripting_core": {"division": "Engineering", "role": "vm_bindings", "coders": ["jonathan_blow", "casey_muratori", "niklas_frykholm"]},
    "audio_engine": {"division": "Engineering", "role": "mixer_dsp", "coders": ["casey_muratori", "fabian_giesen", "niklas_frykholm"]},
    "animation_rig": {"division": "Engineering", "role": "skeletal", "coders": ["niklas_frykholm", "casey_muratori", "john_carmack"]},
    "input_system": {"division": "Engineering", "role": "devices", "coders": ["casey_muratori", "john_carmack", "niklas_frykholm"]},
    "memory_allocator": {"division": "Engineering", "role": "arenas", "coders": ["casey_muratori", "mike_acton", "fabian_giesen"]},
    "job_system": {"division": "Engineering", "role": "tasks", "coders": ["mike_acton", "casey_muratori", "niklas_frykholm"]},
    "debug_telemetry": {"division": "Engineering", "role": "profilers", "coders": ["fabian_giesen", "casey_muratori", "john_carmack"]},
    "save_load": {"division": "Engineering", "role": "persistence_game", "coders": ["niklas_frykholm", "casey_muratori", "fabian_giesen"]},
    "ui_framework": {"division": "Engineering", "role": "widgets", "coders": ["casey_muratori", "jonathan_blow", "niklas_frykholm"]},
    "localization": {"division": "Engineering", "role": "i18n", "coders": ["niklas_frykholm", "jonathan_blow", "casey_muratori"]},
    "platform_android": {"division": "Engineering", "role": "s20_shell", "coders": ["john_carmack", "casey_muratori", "niklas_frykholm"]},
}

CONTENT_ROOMS: Dict[str, Dict[str, Any]] = {
    "level_design": {"division": "Content", "role": "spaces", "coders": ["jonathan_blow", "casey_muratori", "john_carmack"]},
    "combat_design": {"division": "Content", "role": "encounters", "coders": ["jonathan_blow", "john_carmack", "casey_muratori"]},
    "economy_design": {"division": "Content", "role": "sinks_sources", "coders": ["andrej_karpathy", "jonathan_blow", "niklas_frykholm"]},
    "quest_graph": {"division": "Content", "role": "narrative_logic", "coders": ["jonathan_blow", "andrej_karpathy", "casey_muratori"]},
    "vfx_room": {"division": "Content", "role": "particles", "coders": ["fabian_giesen", "john_carmack", "niklas_frykholm"]},
    "lighting_room": {"division": "Content", "role": "gi_probes", "coders": ["fabian_giesen", "john_carmack", "niklas_frykholm"]},
    "cinematic_room": {"division": "Content", "role": "cameras", "coders": ["jonathan_blow", "niklas_frykholm", "casey_muratori"]},
    "procedural_gen": {"division": "Content", "role": "pcg", "coders": ["andrej_karpathy", "jonathan_blow", "john_carmack"]},
    "mesh_pipeline": {"division": "Content", "role": "assets_3d", "coders": ["fabian_giesen", "niklas_frykholm", "john_carmack"]},
    "sprite_pipeline": {"division": "Content", "role": "assets_2d", "coders": ["casey_muratori", "fabian_giesen", "niklas_frykholm"]},
}

OPS_ROOMS: Dict[str, Dict[str, Any]] = {
    "ci_cd_room": {"division": "Ops", "role": "pipelines", "coders": ["niklas_frykholm", "casey_muratori", "john_carmack"]},
    "observability_room": {"division": "Ops", "role": "metrics_logs", "coders": ["fabian_giesen", "niklas_frykholm", "casey_muratori"]},
    "release_room": {"division": "Ops", "role": "ship_gate", "coders": ["niklas_frykholm", "john_carmack", "casey_muratori"]},
    "incident_room": {"division": "Ops", "role": "sev_response", "coders": ["john_carmack", "casey_muratori", "niklas_frykholm"]},
    "compliance_room": {"division": "Ops", "role": "audit_export", "coders": ["niklas_frykholm", "casey_muratori", "fabian_giesen"]},
}

ZAIBATSU_ROOMS: Dict[str, Dict[str, Any]] = {
    "vox_room": {"division": "Zaibatsu", "role": "command_net", "coders": []},
    "reputation_room": {"division": "Zaibatsu", "role": "standings", "coders": []},
    "truth_room": {"division": "Zaibatsu", "role": "sword_laws", "coders": []},
    "wiring_room": {"division": "Zaibatsu", "role": "cross_wire", "coders": []},
    "training_room": {"division": "Zaibatsu", "role": "idle_learn", "coders": []},
    "perimeter_room": {"division": "Zaibatsu", "role": "appwide_security", "coders": []},
}

# Additional rooms to reach full zaibatsu capacity (user reported 130+; expanding to 140+ for completeness)
ART_ROOMS: Dict[str, Dict[str, Any]] = {
    "concept_art": {"division": "Art", "role": "visual_concept", "coders": ["concept_artist_1", "concept_artist_2"]},
    "3d_modeling": {"division": "Art", "role": "3d_assets", "coders": ["modeler_1", "modeler_2"]},
    "texturing": {"division": "Art", "role": "surface_art", "coders": ["texturer_1"]},
    "animation_2d": {"division": "Art", "role": "2d_anim", "coders": ["animator_2d"]},
    "rigging": {"division": "Art", "role": "skeletal_rig", "coders": ["rigger_1"]},
    "lighting_art": {"division": "Art", "role": "scene_light", "coders": ["lighter_1"]},
    "environment_art": {"division": "Art", "role": "world_build_art", "coders": ["env_artist"]},
    "character_design": {"division": "Art", "role": "char_art", "coders": ["char_designer"]},
    "ui_art": {"division": "Art", "role": "interface_art", "coders": ["ui_artist"]},
    "icon_design": {"division": "Art", "role": "iconography", "coders": ["icon_artist"]},
    "particle_art": {"division": "Art", "role": "vfx_art", "coders": ["particle_artist"]},
    "shader_art": {"division": "Art", "role": "material_shaders", "coders": ["shader_artist"]},
    "matte_painting": {"division": "Art", "role": "background_paint", "coders": ["matte_painter"]},
    "storyboarding": {"division": "Art", "role": "story_vis", "coders": ["storyboarder"]},
    "prop_design": {"division": "Art", "role": "prop_art", "coders": ["prop_designer"]},
    "illustration": {"division": "Art", "role": "key_art", "coders": ["illustrator_1"]},
    "color_grading_art": {"division": "Art", "role": "tone_art", "coders": ["color_artist"]},
}

SOUND_ROOMS: Dict[str, Dict[str, Any]] = {
    "music_composition": {"division": "Sound", "role": "score_creation", "coders": ["composer_1"]},
    "sound_design": {"division": "Sound", "role": "sfx_creation", "coders": ["sound_designer"]},
    "voice_acting": {"division": "Sound", "role": "dialogue_rec", "coders": ["voice_director"]},
    "foley": {"division": "Sound", "role": "action_sounds", "coders": ["foley_artist"]},
    "mixing": {"division": "Sound", "role": "audio_mix", "coders": ["mixer_1"]},
    "mastering": {"division": "Sound", "role": "final_master", "coders": ["mastering_eng"]},
    "audio_implementation": {"division": "Sound", "role": "engine_int", "coders": ["audio_impl"]},
    "adaptive_music": {"division": "Sound", "role": "dynamic_score", "coders": ["adaptive_comp"]},
    "dialogue_editing": {"division": "Sound", "role": "voice_edit", "coders": ["dialogue_editor"]},
    "sfx_library": {"division": "Sound", "role": "asset_lib", "coders": ["sfx_librarian"]},
}

MARKETING_ROOMS: Dict[str, Dict[str, Any]] = {
    "trailer_production": {"division": "Marketing", "role": "video_trailers", "coders": ["trailer_director"]},
    "social_media": {"division": "Marketing", "role": "social_strat", "coders": ["social_manager"]},
    "press_releases": {"division": "Marketing", "role": "pr_writing", "coders": ["pr_writer"]},
    "community_management": {"division": "Marketing", "role": "comm_mgmt", "coders": ["community_mgr"]},
    "influencer_outreach": {"division": "Marketing", "role": "influencer_rel", "coders": ["influencer_coord"]},
    "esports": {"division": "Marketing", "role": "competitive_events", "coders": ["esports_mgr"]},
    "live_events": {"division": "Marketing", "role": "irl_events", "coders": ["event_planner"]},
    "merch_design": {"division": "Marketing", "role": "merch_art", "coders": ["merch_designer"]},
}

RESEARCH_ROOMS: Dict[str, Dict[str, Any]] = {
    "ai_research": {"division": "Research", "role": "ai_adv", "coders": ["ai_researcher"]},
    "gameplay_research": {"division": "Research", "role": "mech_study", "coders": ["gameplay_researcher"]},
    "player_analytics": {"division": "Research", "role": "data_insight", "coders": ["analyst_1"]},
    "market_research": {"division": "Research", "role": "market_study", "coders": ["market_analyst"]},
    "tech_research": {"division": "Research", "role": "tech_trends", "coders": ["tech_researcher"]},
    "narrative_research": {"division": "Research", "role": "story_study", "coders": ["narr_researcher"]},
    "psychology_research": {"division": "Research", "role": "player_psych", "coders": ["psych_researcher"]},
    "accessibility_research": {"division": "Research", "role": "access_study", "coders": ["access_researcher"]},
    "vr_ar_research": {"division": "Research", "role": "immersive_tech", "coders": ["vr_researcher"]},
    "multiplayer_research": {"division": "Research", "role": "social_play", "coders": ["multi_researcher"]},
}

LEGAL_ROOMS: Dict[str, Dict[str, Any]] = {
    "ip_management": {"division": "Legal", "role": "ip_prot", "coders": ["ip_lawyer"]},
    "contract_review": {"division": "Legal", "role": "contract_law", "coders": ["contract_attorney"]},
    "compliance_gdpr": {"division": "Legal", "role": "data_compliance", "coders": ["compliance_officer"]},
    "licensing": {"division": "Legal", "role": "license_mgmt", "coders": ["licensing_mgr"]},
    "patent_filing": {"division": "Legal", "role": "patent_proc", "coders": ["patent_attorney"]},
}

COMMUNITY_ROOMS: Dict[str, Dict[str, Any]] = {
    "forum_moderation": {"division": "Community", "role": "forum_mgmt", "coders": ["forum_mod"]},
    "discord_management": {"division": "Community", "role": "discord_ops", "coders": ["discord_admin"]},
    "feedback_collection": {"division": "Community", "role": "user_feedback", "coders": ["feedback_analyst"]},
    "event_hosting": {"division": "Community", "role": "virtual_events", "coders": ["event_host"]},
    "wiki_maintenance": {"division": "Community", "role": "knowledge_base", "coders": ["wiki_editor"]},
    "support_tickets": {"division": "Community", "role": "player_support", "coders": ["support_lead"]},
}

DATA_ROOMS: Dict[str, Dict[str, Any]] = {
    "analytics_pipeline": {"division": "Data", "role": "data_flow", "coders": ["data_engineer"]},
    "big_data_processing": {"division": "Data", "role": "large_scale_data", "coders": ["big_data_eng"]},
    "ml_training": {"division": "Data", "role": "model_train", "coders": ["ml_engineer"]},
    "data_visualization": {"division": "Data", "role": "viz_dash", "coders": ["data_viz"]},
    "user_segmentation": {"division": "Data", "role": "player_segments", "coders": ["segmentation_analyst"]},
    "ab_testing": {"division": "Data", "role": "exp_design", "coders": ["ab_tester"]},
    "telemetry_analysis": {"division": "Data", "role": "event_analysis", "coders": ["telemetry_analyst"]},
    "prediction_models": {"division": "Data", "role": "forecasting", "coders": ["predictive_modeler"]},
}

INFRA_ROOMS: Dict[str, Dict[str, Any]] = {
    "cloud_infra": {"division": "Infra", "role": "cloud_ops", "coders": ["cloud_eng"]},
    "ci_infra": {"division": "Infra", "role": "ci_cd_infra", "coders": ["ci_eng"]},
    "monitoring_infra": {"division": "Infra", "role": "obs_infra", "coders": ["monitoring_eng"]},
    "backup_systems": {"division": "Infra", "role": "data_backup", "coders": ["backup_eng"]},
    "scaling_automation": {"division": "Infra", "role": "auto_scale", "coders": ["scaling_eng"]},
    "security_infra": {"division": "Infra", "role": "sec_ops", "coders": ["sec_infra"]},
    "network_infra": {"division": "Infra", "role": "net_ops", "coders": ["net_eng"]},
    "database_admin": {"division": "Infra", "role": "db_mgmt", "coders": ["dba"]},
}


def all_rooms() -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for rid, meta in STUDIO_ROOMS.items():
        merged[rid] = {**meta, "coders": meta.get("coders", [])}
    for block in (ENGINE_ROOMS, CONTENT_ROOMS, OPS_ROOMS, ZAIBATSU_ROOMS, ART_ROOMS, SOUND_ROOMS, MARKETING_ROOMS, RESEARCH_ROOMS, LEGAL_ROOMS, COMMUNITY_ROOMS, DATA_ROOMS, INFRA_ROOMS):
        for rid, meta in block.items():
            merged[rid] = meta
    return merged


def room_ids() -> List[str]:
    return sorted(all_rooms().keys())


def rooms_by_division() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for rid, meta in all_rooms().items():
        div = meta.get("division", "Other")
        out.setdefault(div, []).append(rid)
    return out

# Massive expansion to EXACTLY 1000 rooms — the internal studio "central nervous
# system" (CNS). Each room is an agent-team / specialized neuron, boardroom-connected,
# and (new) able to query external APIs + MCP connectors CONCURRENTLY.
def generate_massive_rooms(base_ids, target_total: int = 1000) -> Dict[str, Dict[str, Any]]:
    """Generate precisely ``target_total - len(base_ids)`` unique agent-team rooms
    so the merged registry always totals exactly ``target_total``."""
    additional: Dict[str, Dict[str, Any]] = {}
    base_divisions = ["Engineering", "Content", "Art", "Sound", "Design", "Research",
                      "Infra", "QA", "Ops", "Marketing", "Legal", "Community", "Data",
                      "Leadership", "Zaibatsu", "Multimodal", "AgenticResearch", "LoopEngineering"]
    specialties = ["lead", "specialist", "coordinator", "analyst", "engineer", "designer",
                   "researcher", "implementer", "tester", "optimizer", "integrator", "simulator",
                   "visualizer", "auditor", "trainer", "deployer", "monitor", "scaler", "securer",
                   "governor", "narrator", "worldbuilder", "asset_crafter", "physics_sim",
                   "ai_behav", "multiplayer_sync", "ui_flow", "audio_mix", "scene_bind",
                   "brain_pilot", "loop_engineer", "trace_graph", "knowledge_crafter", "pi_agent",
                   "specialist_team", "cns_neuron"]
    combos = [(d, s) for d in base_divisions for s in specialties]
    needed = max(0, target_total - len(base_ids))
    idx = 130
    i = 0
    while len(additional) < needed:
        div, spec = combos[i % len(combos)]
        rid = f"{div.lower()}_{spec}_{idx:04d}"
        idx += 1
        i += 1
        if rid in base_ids or rid in additional:
            continue
        additional[rid] = {
            "division": div,
            "role": f"{spec}_agent_team_for_game_building_cns",
            "coders": [f"agent_team_{spec}_{idx}"],
            "agent_team": True,
            "cns_role": "specialized_neuron_in_central_nervous_system_for_game_studio",
            "boardroom_connected": True,
            # ── concurrent external-API + MCP capability (per user request) ──
            "api_access": True,
            "mcp_access": True,
            "concurrent_query": True,
        }
    return additional

# Override all_rooms to include generated rooms for EXACTLY 1000 total.
_original_all_rooms = all_rooms
def all_rooms() -> Dict[str, Dict[str, Any]]:
    merged = _original_all_rooms()
    # Every base room also gains the concurrent query capability.
    for meta in merged.values():
        meta.setdefault("api_access", True)
        meta.setdefault("mcp_access", True)
        meta.setdefault("concurrent_query", True)
    merged.update(generate_massive_rooms(set(merged.keys()), 1000))
    return merged
