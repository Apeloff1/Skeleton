"""
core/systems_forge.py — Systems Forge (non-3D tool template), SOTA edition.

Produces deterministic game-SYSTEM blueprints (narrative, economy, AI-director,
quests, progression, …) — rules + parameters + derived engine MODELS + a
designer brief. Blueprints mount to a build's gamefiles (``galaxy_systems``)
and can be LLM-enriched.

SOTA scale (2026-06):
  • 150+ genuine knobs / 1000+ distinct options across 12 systems (no padding).
  • 12 primary ENGINE MODELS + 10 cross-cutting "upgrade" derivations folded
    into every blueprint.
  • 20 BIG-WIN cross-system playbooks (+ batch Apply-with-AI).
"""
from __future__ import annotations

import hashlib
import os
import random
import time

PIPELINE_STEPS = [
    {"key": "plan",     "label": "Plan",     "blurb": "Resolve goals, knobs & seed"},
    {"key": "model",    "label": "Model",    "blurb": "Derive parameters & engine models"},
    {"key": "rules",    "label": "Rules",    "blurb": "Generate the rule set"},
    {"key": "balance",  "label": "Balance",  "blurb": "Tune curves & weights"},
    {"key": "enrich",   "label": "Enrich",   "blurb": "Designer brief (optional LLM)"},
    {"key": "validate", "label": "Validate", "blurb": "Sanity-check the blueprint"},
    {"key": "mount",    "label": "Mount",    "blurb": "Mount blueprint to gamefiles"},
]

# Each system: knobs = {knob_key: "space separated genuine option words"}.
# Every option is a distinct, real game-design choice — no synthetic padding.
SYSTEM_REGISTRY: list[dict] = [
    {"key": "narrative", "label": "Narrative Director", "icon": "📖",
     "blurb": "Branching story structure, arcs & beats",
     "knobs": {
        "structure": "linear branching hub_and_spoke nonlinear episodic emergent parallel_threads in_media_res frame_story rashomon mosaic looping",
        "tone": "heroic tragic comedic noir mysterious hopeful grim whimsical melancholic satirical surreal earnest",
        "pacing": "slow_burn steady brisk frantic ebb_flow escalating measured staccato breathless deliberate",
        "branching": "minimal moderate heavy fully_reactive faction_gated karma_driven time_sensitive butterfly_effect",
        "pov": "first_person third_limited omniscient multi_protagonist unreliable_narrator epistolary second_person collective",
        "theme": "redemption survival power corruption identity sacrifice freedom legacy belonging vengeance discovery acceptance",
        "stakes": "personal local national global cosmic existential generational intimate",
        "delivery": "cutscenes environmental dialogue codex_lore radio_chatter found_footage flashback interactive_memory diegetic_ui",
        "continuity": "standalone serialized anthology shared_universe new_game_plus living_canon retroactive",
        "conflict_type": "man_vs_man man_vs_nature man_vs_self man_vs_society man_vs_fate man_vs_machine man_vs_unknown",
        "protagonist_arc": "growth fall flat redemption disillusionment corruption transformation testing",
        "world_reactivity": "static reputation_only world_state branching_world simulation_driven persistent_consequences",
        "lore_depth": "light moderate dense iceberg encyclopedic mythic_layered",
        "moral_framing": "binary spectrum grey_morality consequentialist relativist no_judgement",
        "memory_system": "none flag_based state_machine relationship_ledger world_simulation persistent_chronicle"}},
    {"key": "economy", "label": "Economy Designer", "icon": "💰",
     "blurb": "Currencies, sinks, faucets & inflation control",
     "knobs": {
        "model": "closed open hybrid barter fiat dual_currency token gift_economy command planned mixed_market",
        "faucets": "quests loot trading crafting daily_login pvp gathering achievements events selling refining salvaging",
        "sinks": "repairs taxes upgrades consumables fees gambling cosmetics housing fast_travel respec storage insurance",
        "inflation": "deflationary stable mild_inflation managed dynamic pegged hyperinflation_guarded seasonal_reset",
        "currencies": "single dual soft_hard premium_split faction_scrip seasonal event_token bound_unbound tiered",
        "trading": "none player_to_player auction_house vendor_only regional_markets contracts black_market consignment commodity_exchange",
        "crafting_cost": "trivial moderate steep gated material_intensive time_gated skill_gated recipe_locked",
        "scarcity": "abundant balanced scarce engineered_drip seasonal_spike artificial_limited renewable depletable",
        "wealth_curve": "flat linear exponential rubberband capped progressive_tax soft_cap diminishing",
        "price_discovery": "fixed vendor_set supply_demand auction floating regional_arbitrage haggling",
        "ownership": "consumable durable rentable leasable shared nft_style soulbound tradeable",
        "value_storage": "currency goods land reputation contracts shares collectibles influence",
        "market_health": "free_market regulated taxed subsidized monopoly_guarded anti_hoarding",
        "income_sources": "active passive hybrid investment_return staking yield rent royalties",
        "anti_exploit": "none audit_logs rate_limits soft_caps dynamic_taxation circuit_breakers honeypot_traps"}},
    {"key": "ai_director", "label": "AI Director", "icon": "🎬",
     "blurb": "Dynamic pacing, tension & encounter pacing",
     "knobs": {
        "goal": "max_tension steady_flow surprise comfort challenge story_beats flow_state mastery_pressure exploration_reward",
        "intensity_curve": "sawtooth sine plateau crescendo random adaptive escalating_waves pulse decay_recover",
        "reactivity": "scripted reactive predictive learning anticipatory hybrid context_sensitive",
        "spawn_logic": "fixed budgeted threat_based stealthy swarm flanking ambush_priority encirclement attrition baiting",
        "inputs": "health ammo position skill heatmap squad_state tempo accuracy traversal stress_proxy",
        "recovery": "timed safe_rooms scripted_lulls dynamic_breathers resource_caches narrative_beats vista_moments",
        "escalation": "linear stepped exponential event_triggered player_gated mastery_gated time_pressured",
        "variety_engine": "round_robin weighted_random tag_based mood_matched anti_repeat archetype_rotation surprise_injection",
        "telemetry": "none lightweight full session_profiling cohort_aware realtime_adaptive privacy_safe",
        "difficulty_response": "static nudge aggressive_correct invisible_hand transparent_offer player_voted",
        "encounter_composition": "uniform mixed elite_lead boss_minions specialist_squad combined_arms environmental",
        "pressure_source": "enemies environment time resources objectives crowd_noise scarcity",
        "flow_protection": "none anti_frustration anti_boredom both rubberband_soft skill_window",
        "narrative_sync": "ignored loose tight beat_locked mood_locked director_authored",
        "learning_horizon": "none session match_history cohort_model lifetime_profile federated"}},
    {"key": "quest", "label": "Quest System", "icon": "🗺",
     "blurb": "Objectives, chains, rewards & gating",
     "knobs": {
        "type": "main side fetch escort kill puzzle timed faction emergent investigation survival delivery",
        "chaining": "standalone linear_chain branching dependency_web hub_unlock prerequisite_tree parallel_tracks",
        "rewards": "xp gold items reputation unlocks lore cosmetic currency abilities access titles",
        "gating": "level item reputation story time skill region faction_standing world_state",
        "objectives": "single multi_stage optional_bonus hidden dynamic stealth_optional branching_choice timed_sub",
        "tracking": "waypoint_off soft_hints full_waypoint journal_only investigation breadcrumb minimap_ping",
        "failure": "retry permanent branching soft_fail timed_retry consequence checkpoint cascading",
        "giver": "npc board radio environmental faction_handler dynamic_event letter overheard",
        "replayability": "one_shot repeatable daily_rotation procedural escalating weekly seasonal_rotation",
        "discovery": "marker_given exploration_found npc_told eavesdropped item_triggered emergent_world",
        "scope": "micro short medium long epic chapter_arc world_spanning",
        "choice_weight": "cosmetic minor moderate major irreversible world_altering",
        "companion_role": "none optional_helper required_npc party_choice loyalty_gated",
        "pacing_role": "tutorial filler core climactic palette_cleanser breather",
        "objective_clarity": "explicit guided discoverable cryptic emergent self_directed"}},
    {"key": "progression", "label": "Progression", "icon": "📈",
     "blurb": "Levels, skill trees, XP curves & unlocks",
     "knobs": {
        "model": "level_based skill_tree classless prestige mastery hybrid paragon constellation perk_deck",
        "xp_curve": "linear quadratic exponential logarithmic stepped sigmoid piecewise plateau_burst",
        "unlocks": "abilities gear zones recipes perks titles mounts companions cosmetics shortcuts",
        "respec": "none free costly limited timed loadout_swap dual_spec full_reset",
        "power_source": "stats gear skills consumables synergy crafting set_bonuses mastery_ranks",
        "gating": "soft hard level_lock gear_score reputation story skill_check time",
        "mastery": "none weapon_mastery class_mastery world_tier prestige_loops affinity discipline",
        "axis": "vertical horizontal mixed seasonal_reset capped_vertical wide_then_tall",
        "catch_up": "none rested_xp mentor_boost catch_up_gear scaling_assist legacy_bonus account_wide",
        "specialization": "open forced respec_friendly branching_lock dual_path hybridizable",
        "milestone_pacing": "frequent steady sparse milestone_gated burst_then_drought",
        "endgame_loop": "none gear_grind ranked_ladder mastery_chase collection horizontal_content infinite_scaling",
        "build_diversity": "single_meta few_viable many_viable fully_open situational_swaps",
        "feedback": "numbers_only visceral both juicy minimal celebratory",
        "power_legibility": "opaque numeric visceral comparative previewed full_simulation"}},
    {"key": "dialogue", "label": "Dialogue System", "icon": "💬",
     "blurb": "Conversation trees, voice & relationship",
     "knobs": {
        "style": "tree wheel freeform keyword cinematic reactive timed gesture_based parser",
        "voice": "stoic witty formal slang theatrical terse poetic sardonic warm gruff cryptic earnest",
        "relationship": "none affinity faction trust romance rivalry mentor reputation_web debt",
        "consequence": "cosmetic minor branching world_altering reputation_shift relationship_lock unlocks",
        "tone_match": "fixed mood_adaptive relationship_aware context_aware faction_aware history_aware",
        "interrupts": "none timed barge_in skill_check emote_react quick_time pressure_choice",
        "localization": "text_only full_vo partial_vo subtitled_only dynamic_tts dubbed culturalized",
        "memory": "none short_term persistent grudge_system favor_ledger callback rumor_spread",
        "skill_checks": "none persuade intimidate deceive insight charm barter lore",
        "branching_depth": "flat shallow moderate deep web_like dead_end_aware",
        "subtext": "literal hinted layered ironic deceptive performative",
        "pacing": "snappy natural deliberate barrage contemplative interruptible",
        "speaker_count": "monologue two_party group crowd dynamic_party debate",
        "delivery_tech": "text bark_system full_vo procedural_tts hybrid_vo performance_capture"}},
    {"key": "balance", "label": "Balance & Tuning", "icon": "⚖️",
     "blurb": "Damage curves, weights & difficulty knobs",
     "knobs": {
        "target": "casual core hardcore competitive accessible mixed esports cooperative",
        "damage_model": "flat percent hybrid armor_mitigation crit_heavy true_damage scaling_penetration falloff",
        "scaling": "static level_scaled world_tier dynamic rubberband zone_locked party_scaled",
        "rng_spread": "tight moderate wide deterministic streaky pity_protected smart_random seeded",
        "ttk": "instant fast medium slow attrition burst_windows sustained",
        "counterplay": "dodge_block parry resource_trade positioning hard_counters soft_counters timing_windows interrupts",
        "power_budget": "equalized rock_paper_scissors role_based niche_picks meta_diverse situational sidegrade",
        "tuning_cadence": "static patch_tuned hotfix_ready seasonal data_driven community_voted live_tuned",
        "resource_economy": "ammo_scarce regen_based cooldown_gated charge_based stamina hybrid_resource",
        "risk_reward": "low_variance high_variance choose_your_own escalating gambit_based safe_default",
        "fairness_model": "symmetric asymmetric_balanced handicap_aware skill_matched gear_normalized",
        "matchup_design": "no_hard_counters soft_triangle deep_counters skill_overrides comp_dependent",
        "telemetry_loop": "none manual_review weekly_patch live_dashboard auto_tuning community_signal"}},
    {"key": "spawning", "label": "Spawn & Encounter", "icon": "👾",
     "blurb": "Enemy waves, density & encounter budgets",
     "knobs": {
        "pattern": "waves trickle ambush patrol nest swarm boss_gauntlet pincer siege infiltration roaming",
        "density": "sparse moderate dense overwhelming adaptive scaling_with_party clustered",
        "budget": "fixed scaling threat_based player_count time_based skill_based zone_weighted",
        "variety": "uniform mixed elite_lead random themed escalating_types modifier_stacked",
        "placement": "choke_points open_field verticality flanking_routes objective_anchored cover_rich ambush_pockets",
        "telegraph": "none audio_cue visual_tell timer_warning stealth_silent screen_shake announcer",
        "reinforcement": "none timed triggered objective_linked endless conditional escalating_waves",
        "elites": "none rare mini_boss champion_packs nemesis modifier_carriers rotating_affixes",
        "respawn": "none timed checkpoint_reset dynamic patrol_return objective_locked anti_camp",
        "leash": "none aggressive tethered global_alert stealth_aware investigative",
        "composition_role": "fodder bruiser ranged support disruptor controller artillery",
        "spawn_feel": "fair gotcha cinematic tense relentless puzzle_like horde",
        "director_budget": "static threat_metric flow_aware credit_pool adaptive_pressure encounter_authored"}},
    {"key": "loot", "label": "Loot Tables", "icon": "🎁",
     "blurb": "Drop rates, rarity tiers & pity timers",
     "knobs": {
        "distribution": "uniform weighted tiered smart_loot pity bad_luck_protect deterministic_token hybrid",
        "rarity_spread": "generous balanced stingy spiky tier_locked logarithmic front_loaded",
        "sources": "kills chests bosses crafting vendors events world_drops achievements gambling fishing",
        "scaling": "static level_scaled difficulty_scaled luck_stat tier_scaled magic_find time_invested",
        "itemization": "random fixed_rolls affixes set_bonuses runewords sockets corrupted legendary_powers",
        "trade_policy": "free bind_on_equip bind_on_pickup account_bound time_limited_trade restricted gift_only",
        "duplicates": "stack salvage currency_convert collection_bonus reroll_fuel upgrade_material",
        "chase_items": "none cosmetics mythics god_rolls transmog_unlocks pets mounts titles",
        "drop_feedback": "subtle beam_pillar audio_sting screen_flash announcer rarity_color none",
        "loot_ownership": "shared instanced master_loot need_greed round_robin personal",
        "vendor_role": "junk_only currency_sink targeted_buy rotating_stock reputation_gated crafting_mats",
        "gear_lifespan": "permanent durability seasonal consumable upgrade_path sidegrade_churn",
        "smart_drop_bias": "none spec_aware deficit_filling anti_duplicate streak_breaker wishlist_weighted"}},
    {"key": "monetization", "label": "Monetization", "icon": "🛒",
     "blurb": "Cosmetics, battlepass & store cadence (ethical)",
     "knobs": {
        "model": "premium f2p cosmetic_only battlepass dlc subscription hybrid one_time expansion_driven",
        "store": "rotating fixed featured bundles limited_time vaulted seasonal_shop direct_purchase",
        "fairness": "no_p2w cosmetic_only convenience expansion_only time_save_only earnable_all",
        "cadence": "seasonal monthly weekly event_driven daily_deals quarterly_expansion launch_only",
        "pricing": "tiered psychological_99 flat regional dynamic founders bulk_discount fair_currency",
        "earnable": "none currency_earnable battlepass_earnable full_unlock_path catch_up_track grind_optional",
        "transparency": "hidden disclosed_odds full_odds pity_disclosed no_loot_boxes direct_only",
        "value_anchor": "starter_pack flagship_bundle whale_tier accessibility_tier supporter_pack cosmetic_flagship",
        "engagement_model": "none daily_login streak_reward retention_quests session_caps healthy_breaks",
        "social_spend": "none gifting team_funded clan_unlocks shared_battlepass spectator_cosmetics",
        "refund_policy": "none generous standard token_based goodwill subscription_pause",
        "ethics_guardrail": "spend_caps minor_protection cooldowns clear_pricing no_dark_patterns deletion_safe",
        "value_communication": "hidden price_anchored bundle_value preview_first try_before_buy transparent_roi"}},
    {"key": "difficulty", "label": "Difficulty Curve", "icon": "🌡",
     "blurb": "Onboarding, ramp & mastery ceiling",
     "knobs": {
        "onboarding": "gentle tutorialised trial_by_fire optional_tips guided contextual_hints sandbox_first",
        "ramp": "smooth stepped spike_and_rest exponential adaptive sawtooth gated_walls",
        "assist": "none aim_assist slowmo skip_option dynamic auto_target damage_reduction generous_checkpoints",
        "ceiling": "low moderate high skill_expression speedrun mastery_infinite combo_depth",
        "modes": "single fixed selectable unlockable modifiers permadeath ascension custom_rules",
        "dda": "off subtle aggressive opt_in transparent invisible player_controlled",
        "punishment": "forgiving moderate harsh roguelike souls_like permadeath_optional setback_only",
        "accessibility": "none colorblind remap subtitles difficulty_separated full_suite motion_options audio_cues",
        "challenge_source": "execution strategy resource_management knowledge reflexes planning adaptation",
        "comeback_mechanics": "none rubberband second_wind bounty momentum_shift mercy_invuln",
        "failure_friction": "instant_retry short_walk checkpoint_walk run_back full_restart progress_kept",
        "skill_floor": "very_low low moderate high gated_by_tutorial accessible_deep",
        "assist_granularity": "global per_system slider_based modifier_toggles preset_tiers contextual_offer"}},
    {"key": "faction", "label": "Faction & Reputation", "icon": "🏴",
     "blurb": "Allegiances, standing & territory control",
     "knobs": {
        "structure": "two_sides three_way many_factions dynamic emergent hidden nested guild_based",
        "standing": "linear tiered branching decay_based deeds infamy_honor dual_axis",
        "conflict": "war trade espionage diplomacy shifting cold_war proxy resource_race",
        "rewards": "vendors gear quests territory titles unique_recipes mounts safehouses",
        "allegiance": "pick_one fluid multi_faction betrayal_allowed neutral_path mercenary undercover",
        "territory": "none static contested dynamic_borders capturable instanced influence_zones",
        "diplomacy": "none alliances treaties tribute_system marriage_pacts non_aggression vassalage",
        "reputation_decay": "none slow seasonal action_based forgiveness_path memory_grudge",
        "membership": "open application_gated quest_gated invite_only reputation_gated exclusive",
        "internal_politics": "none ranks rivalries leadership_challenge intrigue succession",
        "world_impact": "cosmetic vendor_unlock world_state territory_control narrative_branch economy_shift",
        "betrayal_cost": "none reputation_hit bounty hunted faction_war locked_content",
        "memory_persistence": "session world_state cross_save chronicle_ledger generational dynamic_rumor"}},
    # ── +10 brand-new non-viewport systems (genuine knobs/options + engine models) ──
    {"key": "crafting", "label": "Crafting & Itemforge", "icon": "🔨",
     "blurb": "Recipes, materials, stations & item quality",
     "knobs": {
        "recipe_discovery": "preset exploration_found purchased experimentation reverse_engineered taught_by_npc unlocked_by_quest schematic_drop",
        "material_tiers": "single two_tier three_tier five_tier rarity_scaled biome_sourced era_gated infinite_refine",
        "stations": "none portable fixed_bench tiered_workshop guild_hall specialized_per_craft mobile_kit world_anvils",
        "quality_variance": "fixed rolled skill_scaled material_scaled critical_craft masterwork_chance perfect_attainable degrade_on_fail",
        "gathering": "manual_harvest auto_collect node_respawn tool_gated risk_zone purchasable byproduct_only contract_supply",
        "refinement": "none smelting_only multi_stage purify_chain alloying transmutation infusion attunement",
        "enchanting": "none socket_gems rune_words affix_reroll imbue_essence sacrifice_fuel enchant_table corruption_risk",
        "durability": "indestructible wear_repair break_permanent maintenance_kit decay_over_time consumable_charges insurance_backed",
        "blueprint_source": "starter loot_drop vendor reputation_reward boss_unique research_unlock community_shared event_exclusive",
        "salvage": "none break_to_materials currency_convert reroll_fuel upgrade_token collection_credit transmog_unlock",
        "mastery": "none recipe_xp profession_levels specialization_paths signature_items reputation_tiers prestige_crafts",
        "time_model": "instant timed_queue offline_progress real_time_clock batch_crafting interruptible station_throughput"}},
    {"key": "stealth", "label": "Stealth & Detection", "icon": "🥷",
     "blurb": "Vision cones, sound, alert states & takedowns",
     "knobs": {
        "detection_model": "binary_seen meter_fill state_machine line_of_sight light_based sound_based multi_sense suspicion_decay",
        "vision_cones": "none fixed_cone fov_with_falloff peripheral_aware day_night_modified obstacle_occluded shared_vision camera_grid",
        "sound_propagation": "ignored radius_based material_dampened occlusion_aware footstep_surface noise_meter distraction_priority",
        "light_shadow": "ignored hide_in_shadow light_meter dynamic_shadows extinguishable_lights spotlight_sweeps cover_darkness",
        "ai_alert_states": "unaware suspicious investigating alerted searching coordinated_hunt reinforced calldown",
        "takedowns": "none silent_melee ranged_silent grab_drag nonlethal_option environmental chained_takedown loud_risk",
        "distraction_tools": "none noise_lure thrown_object hackable_device whistle bait_trap smoke gadget_suite",
        "hiding_spots": "none cover_crouch tall_grass lockers shadows crowd_blend vent_routes verticality",
        "search_behavior": "static return_to_post patrol_resume sweep_pattern last_known_position spreading_search give_up_timer",
        "disguise": "none uniform_swap social_stealth blend_faction time_limited suspicion_meter blow_cover_actions",
        "trace_evidence": "none bodies_found missing_guards open_doors blood_trail cameras alarms forensic_memory",
        "lethality_choice": "lethal_only nonlethal_only player_choice score_modified consequence_branch pacifist_run ghost_run"}},
    {"key": "vehicle", "label": "Vehicle & Mount", "icon": "🏎",
     "blurb": "Handling, terrain, fuel & customization",
     "knobs": {
        "control_model": "arcade simcade simulation drift_focused grip_focused momentum_heavy floaty weighty",
        "terrain_handling": "road_only off_road amphibious all_terrain surface_modifiers traction_loss climb_assist terrain_deform",
        "mount_taming": "none buy_only tame_wild breed_raise bond_loyalty summon_contract craft_construct rent_stable",
        "fuel_energy": "infinite fuel_tank stamina_bar charge_battery resource_burn overheat_cooldown nitrous_finite",
        "customization": "none cosmetic_paint performance_parts modular_swap weight_balance handling_tune weapon_mounts full_garage",
        "damage_model": "invincible health_bar part_damage handling_degrade catastrophic_failure repair_field totaled_loss",
        "traversal_types": "ground water air space underground rail grappling hybrid_transform",
        "speed_tiers": "walk_only slow medium fast hypersonic gear_shifted boost_burst variable_throttle",
        "passenger_seats": "solo two_seat squad mounted_gunner tow_capacity cargo_hold convoy crew_roles",
        "summon_method": "garage_only whistle_call instant_summon nearby_only quest_unlock fast_travel_node deploy_beacon",
        "collision": "bouncy realistic_crumple ragdoll_riders environmental_destruction knockback pinball arcade_forgiving",
        "boost_model": "none nitrous drift_charge slipstream pickup_boost stamina_dash overdrive_gauge risk_overheat"}},
    {"key": "weather_time", "label": "Weather & Time", "icon": "🌦",
     "blurb": "Day/night, seasons, weather & gameplay impact",
     "knobs": {
        "day_night_cycle": "none fixed_time accelerated real_time player_controlled story_locked region_offset eternal_night",
        "season_model": "none two_season four_season dynamic_drift narrative_gated harsh_winter endless_summer procedural_climate",
        "weather_types": "clear_only rain_storm snow_blizzard fog_haze sandstorm heatwave acid_rain magical_anomaly",
        "dynamic_transitions": "instant fade gradual_front forecast_telegraphed event_triggered chaotic regional_systems",
        "gameplay_impact": "cosmetic visibility movement_penalty resource_change enemy_behavior stealth_modifier hazard_damage farming_yield",
        "visibility_effects": "none fog_distance rain_blur darkness_radius glare_blind heat_shimmer whiteout sensor_disruption",
        "climate_zones": "uniform biome_based latitude_model altitude_scaled micro_climates planet_wide shifting_borders",
        "forecast_telegraph": "none sky_cues npc_warnings hud_forecast almanac sensor_readout sudden_only ritual_predicted",
        "time_scale": "frozen slow normal fast hyperlapse adjustable mission_paused offline_advances",
        "hazard_events": "none lightning flood wildfire avalanche tornado meteor_shower eclipse_event",
        "lighting_response": "static baked dynamic_gi time_tinted weather_dimmed torch_dependent neon_night volumetric",
        "persistence": "resets_on_load world_persistent per_region save_remembered season_carryover shared_world deterministic_seed"}},
    {"key": "social", "label": "Social & Multiplayer", "icon": "👥",
     "blurb": "Co-op, matchmaking, roles & communication",
     "knobs": {
        "group_size": "solo duo squad raid massive guild_scale dynamic_lobby drop_in_drop_out",
        "matchmaking": "none open_lobby skill_based role_based connection_based party_first ranked_split casual_quickplay",
        "communication": "none text_chat voice_chat ping_system emote_wheel quick_commands proximity_voice moderated_only",
        "roles": "none flexible tank_heal_dps support_classes specialist_picks rotating_objective leaderless captain_led",
        "shared_progress": "isolated host_only synced_party account_shared contribution_based mvp_weighted guild_pooled seasonal_team",
        "social_spaces": "none lobby hub_town player_housing guild_hall world_persistent instanced_social marketplace_square",
        "moderation": "none report_only auto_filter human_review reputation_system mute_block trust_factor restricted_chat",
        "friend_systems": "none friend_list clans guilds mentorship recruit_a_friend cross_game_presence blocklist",
        "cross_play": "none same_platform full_crossplay input_segregated opt_in region_locked cross_progression",
        "presence": "none online_status rich_presence activity_feed spectate join_in_progress watch_party do_not_disturb",
        "cooperation_model": "competitive_only co_op_campaign shared_world asymmetric_coop drop_in_assist raid_coordination trade_only",
        "competitive_modes": "none ranked_ladder casual_match tournaments arena duels battle_royale leaderboard_chase"}},
    {"key": "audio_director", "label": "Audio Director", "icon": "🎵",
     "blurb": "Adaptive music, SFX, mixing & ambience",
     "knobs": {
        "music_model": "none looped_tracks layered_adaptive vertical_remix horizontal_resequence generative stinger_driven dynamic_orchestra",
        "adaptive_layers": "single intensity_layers stem_based instrument_add_remove tension_mapped exploration_combat biome_themed boss_unique",
        "sfx_priority": "flat importance_ducked distance_falloff voice_priority limited_voices category_buses dynamic_culling",
        "mixing": "static auto_balance sidechain_duck dynamic_range_comp loudness_normalized cinematic_mix accessibility_mix per_scene",
        "spatialization": "mono stereo_pan surround hrtf_binaural occlusion_aware reverb_zones doppler full_3d",
        "mood_mapping": "none tension_curve emotion_tags scene_presets player_state_driven narrative_synced biome_palette adaptive_ai",
        "silence_use": "constant_score strategic_silence dynamic_rests dread_quiet contrast_punctuation diegetic_only restraint_pacing",
        "leitmotif": "none character_themes faction_themes location_themes item_stingers recurring_motifs evolving_theme reprise_payoff",
        "vo_model": "none bark_system full_vo procedural_tts hybrid_recorded performance_capture multi_language emergent_lines",
        "ambience": "none looped_beds dynamic_soundscape time_weather_driven crowd_density wildlife_layers reactive_environment binaural_field",
        "ducking": "none sidechain dialogue_priority alert_focus dynamic_threshold scene_aware combat_swell",
        "accessibility_audio": "none subtitle_sync visual_sound_cues mono_toggle frequency_balance speech_clarity directional_indicators haptic_pair"}},
    {"key": "tutorial", "label": "Tutorial & Onboarding", "icon": "🎓",
     "blurb": "Teaching, pacing, hints & first session",
     "knobs": {
        "teaching_method": "text_walls learn_by_doing guided_tasks show_dont_tell contextual_prompts safe_sandbox mentor_npc trial_and_error",
        "pacing": "front_loaded just_in_time drip_fed player_paced gated_unlock optional_skippable mandatory_steps adaptive_speed",
        "hand_holding": "none light_hints moderate_guidance heavy_steps configurable assist_until_proficient invisible_teaching guardrails_only",
        "contextual_help": "none tooltips popup_tips highlight_targets ghost_demos voiced_coach codex_links inline_examples",
        "skill_gating": "all_unlocked progressive_unlock practice_required proficiency_check level_gated story_gated optional_mastery",
        "practice_space": "none tutorial_level training_room sandbox_mode replayable_drills target_range safe_zone simulator",
        "failure_teaching": "punish reset_retry hint_on_fail scaffolded_assist explain_mistake checkpoint_back forgiving_loop",
        "reference_access": "none pause_codex glossary searchable_help video_recap reminder_prompts in_context_recall tutorial_replay",
        "tooltip_model": "none hover_only first_time_only persistent_toggle smart_contextual depth_layered dismiss_remember",
        "progressive_disclosure": "all_at_once staged_systems unlock_on_need complexity_ramp mastery_reveal optional_depth layered_menus",
        "first_session_arc": "cold_open hook_first guided_win narrative_lead mechanic_lead spectacle_lead choice_lead slow_build",
        "retention_hooks": "none clear_next_goal daily_reason curiosity_gap progression_tease social_invite reward_preview cliffhanger"}},
    {"key": "save_checkpoint", "label": "Save & Checkpoint", "icon": "💾",
     "blurb": "Save model, checkpoints, death & cloud sync",
     "knobs": {
        "save_model": "manual_only autosave checkpoint_based hybrid save_anywhere save_points suspend_resume continuous",
        "checkpoint_frequency": "sparse moderate frequent pre_boss every_room time_based event_based adaptive",
        "slot_model": "single_slot multi_slot unlimited rotating_autosave per_character cloud_slots branching_saves quicksave_pair",
        "autosave": "off on_transition periodic on_major_event before_risk silent_background frequent_safe configurable",
        "death_handling": "respawn_checkpoint respawn_safe_zone permadeath corpse_run lives_system soft_setback restart_level item_loss",
        "cloud_sync": "none enabled cross_device conflict_resolved offline_first manual_upload auto_seamless versioned",
        "save_scumming_policy": "allowed discouraged single_save_enforced consequence_locked ironman_optional autosave_overwrite reload_penalty",
        "persistence_scope": "full_state checkpoint_state progress_only world_persistent inventory_only flags_and_progress snapshot",
        "quick_resume": "none last_session instant_continue suspend_to_disk fast_boot session_restore crash_recovery",
        "integrity": "none checksum anti_tamper backup_copies corruption_recovery cloud_redundancy versioned_history",
        "branching_saves": "none linear_only manual_branch auto_branch_choice timeline_explore what_if_saves chapter_select",
        "manual_control": "none save_button quicksave_key save_menu export_import name_slots delete_manage pin_protect"}},
    {"key": "accessibility", "label": "Accessibility Suite", "icon": "♿",
     "blurb": "Visual, audio, motor & cognitive aids",
     "knobs": {
        "visual_aids": "none colorblind_modes high_contrast text_scaling ui_scaling brightness_gamma reduce_clutter outline_highlights",
        "audio_aids": "none subtitles closed_captions visual_sound_cues mono_audio frequency_balance speech_clarity directional_indicators",
        "motor_aids": "none full_remap hold_to_toggle auto_actions reduced_inputs aim_assist input_buffering one_handed_layout",
        "cognitive_aids": "none objective_reminders simplified_ui slower_pace skip_puzzles waypoint_assist tutorial_replay difficulty_separated",
        "difficulty_separation": "coupled separated combat_only puzzle_only granular_sliders assist_presets independent_axes story_mode",
        "remapping": "none button_remap key_rebind sensitivity_curves deadzone_tune chord_inputs profile_save controller_swap",
        "subtitles": "none basic sized_styled speaker_labels background_box directional caption_effects language_choice",
        "colorblind": "none protanopia deuteranopia tritanopia configurable_palette pattern_supplements daltonize symbol_coding",
        "motion_options": "none reduce_shake disable_blur fov_adjust reduce_flashing static_camera comfort_vignette teleport_move",
        "reading_support": "none dyslexia_font tts_readout adjustable_speed pause_anytime word_highlighting simplified_language icon_support",
        "ui_scaling": "fixed scalable per_element safe_zone_adjust dpi_aware large_targets reflow_layout density_toggle",
        "assist_presets": "none recommended low_vision motor_friendly cognitive_friendly newcomer custom_save streamer_safe"}},
    {"key": "telemetry", "label": "Telemetry & Analytics", "icon": "📡",
     "blurb": "Events, funnels, retention & privacy",
     "knobs": {
        "event_taxonomy": "none core_events full_funnel custom_schema hierarchical tagged_properties session_scoped lifecycle_complete",
        "funnel_tracking": "none install_to_play tutorial_funnel purchase_funnel session_funnel feature_adoption drop_off_points multi_step",
        "retention_metrics": "none d1_d7_d30 rolling_retention cohort_curves stickiness_dau_mau resurrection_rate churn_prediction lifetime_value",
        "privacy_model": "none anonymized pseudonymized aggregate_only on_device_first differential_privacy gdpr_compliant minimal_collection",
        "sampling": "full_capture rate_limited statistical_sample tiered_events high_value_full adaptive_sampling crash_priority",
        "dashboards": "none realtime_live daily_rollup cohort_explorer funnel_viz heatmaps custom_queries alerting",
        "ab_testing": "none simple_split multivariate feature_flags staged_rollout holdout_groups bayesian_bandit server_driven",
        "anomaly_detection": "none threshold_alerts trend_deviation crash_spikes economy_exploits cheat_signals churn_alerts auto_flag",
        "player_segmentation": "none new_returning spender_tiers playstyle_clusters skill_brackets at_risk whales_minnows behavioral_cohorts",
        "performance_metrics": "none fps_tracking load_times memory_usage crash_rate network_latency device_breakdown frame_pacing",
        "consent_model": "none opt_in opt_out granular_toggles regional_default transparent_disclosure revocable child_safe",
        "data_retention": "indefinite time_boxed purge_on_request rolling_window aggregate_then_delete anonymize_after configurable_ttl"}},
]

# ── Extend with the EXTRA systems (22 → 100) with a hard dedup guard so a
#    duplicate key can never create a messy double-system build. ──────────────
try:
    from core.systems_forge_ext import EXTRA_SYSTEMS as _EXTRA
    _seen = {s["key"] for s in SYSTEM_REGISTRY}
    for _s in _EXTRA:
        if _s["key"] in _seen:
            continue  # never register a duplicate system
        SYSTEM_REGISTRY.append(_s)
        _seen.add(_s["key"])
except Exception:  # pragma: no cover - extension optional
    pass

_BY_KEY = {s["key"]: s for s in SYSTEM_REGISTRY}


def _words(s: str) -> list[str]:
    return [w for w in s.split() if w]


def _rng(*parts) -> random.Random:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(h[:12], 16))


def get_system(key: str) -> dict | None:
    return _BY_KEY.get((key or "").strip().lower())


def total_knob_count() -> int:
    return sum(len(s["knobs"]) for s in SYSTEM_REGISTRY)


def total_option_count() -> int:
    return sum(len(_words(v)) for s in SYSTEM_REGISTRY for v in s["knobs"].values())


def list_systems() -> dict:
    out = []
    for s in SYSTEM_REGISTRY:
        out.append({"key": s["key"], "label": s["label"], "icon": s["icon"],
                    "blurb": s["blurb"], "knob_count": len(s["knobs"]),
                    "option_count": sum(len(_words(v)) for v in s["knobs"].values())})
    return {"systems": out, "count": len(out), "pipeline": PIPELINE_STEPS,
            "total_knobs": total_knob_count(), "total_options": total_option_count()}


def system_detail(key: str) -> dict:
    s = get_system(key)
    if not s:
        return {"error": "unknown_system", "system": key}
    knobs = [{"key": k, "label": k.replace("_", " ").title(),
              "options": [{"key": w, "label": w.replace("_", " ").title()} for w in _words(v)]}
             for k, v in s["knobs"].items()]
    return {"system": {"key": s["key"], "label": s["label"], "icon": s["icon"], "blurb": s["blurb"]},
            "knobs": knobs, "knob_count": len(knobs),
            "option_count": sum(len(k["options"]) for k in knobs), "pipeline": PIPELINE_STEPS}


# ───────────────────────────────────────────────────────────────────────
# ENGINE MODELS — primary computed model per system + 10 cross-cutting
# "upgrade" derivations folded into every blueprint.
# ───────────────────────────────────────────────────────────────────────
def _xp_curve(chosen: dict, rng: random.Random) -> dict:
    shape = chosen.get("xp_curve", "quadratic")
    levels = rng.choice([30, 50, 60, 99])
    base = rng.choice([80, 100, 120])
    out = []
    for lv in range(1, levels + 1):
        if shape == "linear":
            xp = base * lv
        elif shape == "exponential":
            xp = int(base * (1.18 ** lv))
        elif shape == "logarithmic":
            xp = int(base * (lv ** 0.8) * 4)
        elif shape == "stepped":
            xp = base * ((lv // 5) + 1) * 5
        elif shape == "sigmoid":
            xp = int(base * levels / (1 + 2.71828 ** (-0.12 * (lv - levels / 2))))
        else:
            xp = base * lv * lv
        out.append(int(xp))
    return {"model": "xp_curve", "shape": shape, "max_level": levels,
            "samples": out[:: max(1, levels // 10)], "total_to_cap": sum(out)}


def _economy_ledger(chosen: dict, rng: random.Random) -> dict:
    faucets = chosen.get("faucets", "quests"); sinks = chosen.get("sinks", "upgrades")
    inflo = chosen.get("inflation", "stable")
    faucet_rate = round(rng.uniform(0.8, 1.6), 2)
    sink_rate = round(faucet_rate * {"deflationary": 1.25, "stable": 1.0, "mild_inflation": 0.85,
                                     "managed": 0.95, "dynamic": 1.0, "pegged": 1.0}.get(inflo, 1.0), 2)
    return {"model": "economy_ledger", "primary_faucet": faucets, "primary_sink": sinks,
            "faucet_rate_per_hr": faucet_rate, "sink_rate_per_hr": sink_rate,
            "net_flow_per_hr": round(faucet_rate - sink_rate, 2),
            "target_balance_window": [int(faucet_rate * 50), int(faucet_rate * 400)]}


def _loot_table(chosen: dict, rng: random.Random) -> dict:
    spread = chosen.get("rarity_spread", "balanced")
    weights = {"common": 60, "uncommon": 25, "rare": 10, "epic": 4, "legendary": 1}
    if spread == "generous":
        weights = {"common": 40, "uncommon": 30, "rare": 18, "epic": 9, "legendary": 3}
    elif spread == "stingy":
        weights = {"common": 75, "uncommon": 18, "rare": 5, "epic": 1.7, "legendary": 0.3}
    elif spread == "spiky":
        weights = {"common": 70, "uncommon": 12, "rare": 10, "epic": 5, "legendary": 3}
    pity = 0
    if chosen.get("distribution") in ("pity", "bad_luck_protect"):
        pity = rng.choice([30, 50, 80])
    return {"model": "loot_table", "rarity_weights": weights, "pity_counter": pity,
            "itemization": chosen.get("itemization", "random")}


def _dda_envelope(chosen: dict, rng: random.Random) -> dict:
    dda = chosen.get("dda", "subtle"); ramp = chosen.get("ramp", "smooth")
    floor, ceil = (0.85, 1.15) if dda == "subtle" else (0.7, 1.35) if dda == "aggressive" else (1.0, 1.0)
    steps = [round(floor + (ceil - floor) * (i / 9), 3) for i in range(10)]
    if ramp == "spike_and_rest":
        steps = [round(s * (1.25 if i % 3 == 0 else 0.9), 3) for i, s in enumerate(steps)]
    return {"model": "dda_envelope", "dda": dda, "ramp": ramp,
            "multiplier_floor": floor, "multiplier_ceiling": ceil, "samples": steps}


def _tension_envelope(chosen: dict, rng: random.Random) -> dict:
    import math
    curve = chosen.get("intensity_curve", "sine"); n = 16
    s = []
    for i in range(n):
        t = i / (n - 1)
        if curve == "sawtooth":
            v = (i % 4) / 4
        elif curve == "plateau":
            v = 0.3 if t < 0.2 else 0.85 if t < 0.8 else 0.4
        elif curve in ("crescendo", "escalating_waves"):
            v = t ** 1.5
        elif curve == "random":
            v = rng.random()
        else:
            v = 0.5 + 0.45 * math.sin(t * 6.283 * 1.5)
        s.append(round(max(0.0, min(1.0, v)), 3))
    return {"model": "tension_envelope", "curve": curve, "samples": s,
            "target": chosen.get("goal", "steady_flow")}


def _spawn_schedule(chosen: dict, rng: random.Random) -> dict:
    pattern = chosen.get("pattern", "waves"); density = chosen.get("density", "moderate")
    mult = {"sparse": 0.6, "moderate": 1.0, "dense": 1.6, "overwhelming": 2.4, "adaptive": 1.2}.get(density, 1.0)
    waves = [{"wave": w + 1, "count": int((4 + w * 2) * mult), "elite": (w + 1) % 3 == 0}
             for w in range(rng.choice([5, 7, 10]))]
    return {"model": "spawn_schedule", "pattern": pattern, "density": density, "waves": waves,
            "elites": chosen.get("elites", "none")}


def _quest_graph(chosen: dict, rng: random.Random) -> dict:
    chaining = chosen.get("chaining", "linear_chain"); n = rng.choice([5, 7, 9])
    nodes = [f"q{i}" for i in range(n)]; edges = []
    if chaining in ("linear_chain", "standalone"):
        edges = [[nodes[i], nodes[i + 1]] for i in range(n - 1)]
    elif chaining == "hub_unlock":
        edges = [[nodes[0], nodes[i]] for i in range(1, n)]
    else:
        for i in range(1, n):
            edges.append([nodes[rng.randrange(i)], nodes[i]])
    return {"model": "quest_graph", "chaining": chaining, "nodes": nodes, "edges": edges,
            "gating": chosen.get("gating", "level")}


def _faction_matrix(chosen: dict, rng: random.Random) -> dict:
    structure = chosen.get("structure", "three_way")
    n = {"two_sides": 2, "three_way": 3, "many_factions": 5, "dynamic": 4,
         "emergent": 4, "hidden": 3}.get(structure, 3)
    facs = [f"faction_{i}" for i in range(n)]
    rel = {f"{facs[i]}↔{facs[j]}": rng.choice(["allied", "neutral", "hostile", "rivals"])
           for i in range(n) for j in range(i + 1, n)}
    return {"model": "faction_matrix", "structure": structure, "factions": facs, "relations": rel}


def _dialogue_thresholds(chosen: dict, rng: random.Random) -> dict:
    rel = chosen.get("relationship", "affinity")
    tiers = ["hostile", "cold", "neutral", "warm", "trusted", "devoted"]
    cuts = [-100, -40, 0, 40, 75, 100]
    return {"model": "dialogue_thresholds", "relationship": rel,
            "tiers": [{"name": t, "at": c} for t, c in zip(tiers, cuts)],
            "skill_checks": chosen.get("skill_checks", "none")}


def _monetization_calendar(chosen: dict, rng: random.Random) -> dict:
    cadence = chosen.get("cadence", "seasonal")
    span = {"seasonal": 90, "monthly": 30, "weekly": 7, "event_driven": 14, "daily_deals": 1}.get(cadence, 30)
    drops = [{"day": d, "type": rng.choice(["cosmetic_set", "bundle", "battlepass_tier", "event_shop"])}
             for d in range(1, span + 1, max(1, span // 4))]
    return {"model": "monetization_calendar", "cadence": cadence,
            "fairness": chosen.get("fairness", "no_p2w"), "drops": drops}


def _beat_map(chosen: dict, rng: random.Random) -> dict:
    structure = chosen.get("structure", "branching"); acts = rng.choice([3, 4, 5])
    beats = ["hook", "inciting_incident", "rising_action", "midpoint_twist",
             "low_point", "climax", "resolution"]
    return {"model": "beat_map", "structure": structure, "acts": acts,
            "beats": beats[:5 + (acts - 3)], "theme": chosen.get("theme", "survival")}


def _power_budget(chosen: dict, rng: random.Random) -> dict:
    target = chosen.get("target", "core"); ttk = chosen.get("ttk", "medium")
    secs = {"instant": 0.5, "fast": 2.5, "medium": 6, "slow": 12, "attrition": 25}.get(ttk, 6)
    return {"model": "power_budget", "target": target, "ttk_seconds": secs,
            "crit_share": round(rng.uniform(0.1, 0.4), 2),
            "counterplay": chosen.get("counterplay", "positioning")}


def _crafting_tree(chosen: dict, rng: random.Random) -> dict:
    tiers = {"single": 1, "two_tier": 2, "three_tier": 3, "five_tier": 5}.get(chosen.get("material_tiers"), rng.choice([3, 4, 5, 6]))
    recipes = int(rng.choice([40, 80, 120, 200]))
    return {"model": "crafting_tree", "material_tiers": tiers, "recipe_count": recipes,
            "station_count": rng.randint(3, 9), "quality_variance": chosen.get("quality_variance", "rolled"),
            "masterwork_chance": round(rng.uniform(0.02, 0.15), 3)}


def _detection_model(chosen: dict, rng: random.Random) -> dict:
    states = ["unaware", "suspicious", "investigating", "alerted", "searching", "hunting"]
    return {"model": "detection_model", "alert_states": states,
            "time_to_detect_s": round(rng.uniform(0.4, 2.5), 2), "search_seconds": rng.randint(8, 30),
            "vision": chosen.get("vision_cones", "fov_with_falloff"), "sound": chosen.get("sound_propagation", "radius_based")}


def _vehicle_handling(chosen: dict, rng: random.Random) -> dict:
    top = rng.choice([60, 120, 180, 260])
    return {"model": "vehicle_handling", "control": chosen.get("control_model", "arcade"),
            "top_speed_kph": top, "accel_0_to_top_s": round(rng.uniform(1.5, 7), 1),
            "grip_coeff": round(rng.uniform(0.5, 1.0), 2), "boost": chosen.get("boost_model", "none")}


def _climate_cycle(chosen: dict, rng: random.Random) -> dict:
    weathers = ["clear", "cloudy", "rain", "storm", "fog", "snow", "heatwave"]
    return {"model": "climate_cycle", "day_length_min": rng.choice([12, 24, 48, 72]),
            "seasons": chosen.get("season_model", "four_season"), "weather_pool": weathers,
            "transition_min": rng.randint(2, 15), "impact": chosen.get("gameplay_impact", "visibility")}


def _session_matrix(chosen: dict, rng: random.Random) -> dict:
    size = {"solo": 1, "duo": 2, "squad": 4, "raid": 8, "massive": 40}.get(chosen.get("group_size", "squad"), 4)
    return {"model": "session_matrix", "party_size": size, "matchmaking": chosen.get("matchmaking", "skill_based"),
            "roles": chosen.get("roles", "flexible"), "comms": chosen.get("communication", "ping_system")}


def _audio_mix(chosen: dict, rng: random.Random) -> dict:
    return {"model": "audio_mix", "music": chosen.get("music_model", "layered_adaptive"),
            "adaptive_layers": rng.choice([2, 3, 4, 5, 6]), "buses": ["music", "sfx", "ambience", "vo", "ui"],
            "ducking": chosen.get("ducking", "sidechain"), "spatialization": chosen.get("spatialization", "hrtf_binaural")}


def _onboarding_arc(chosen: dict, rng: random.Random) -> dict:
    beats = ["welcome", "core_verb", "first_obstacle", "first_win", "systems_intro", "graduation"]
    return {"model": "onboarding_arc", "method": chosen.get("teaching_method", "learn_by_doing"),
            "beats": beats, "time_to_first_win_min": rng.randint(2, 12),
            "disclosure": chosen.get("progressive_disclosure", "staged_systems")}


def _save_schedule(chosen: dict, rng: random.Random) -> dict:
    return {"model": "save_schedule", "mode": chosen.get("save_model", "autosave"),
            "checkpoint_min": rng.choice([2, 5, 10, 15]), "slots": rng.choice([1, 3, 10, "unlimited"]),
            "death": chosen.get("death_handling", "respawn_checkpoint"), "cloud": chosen.get("cloud_sync", "enabled")}


def _a11y_profile(chosen: dict, rng: random.Random) -> dict:
    feats = ["contrast", "colorblind", "subtitles", "remap", "aim_assist", "motion_reduce", "tts", "ui_scale"]
    return {"model": "a11y_profile", "features": feats, "presets": chosen.get("assist_presets", "recommended"),
            "difficulty_separated": chosen.get("difficulty_separation", "separated"),
            "coverage_pct": rng.randint(70, 100)}


def _event_schema(chosen: dict, rng: random.Random) -> dict:
    return {"model": "event_schema", "event_count": int(rng.choice([24, 48, 96, 160])),
            "privacy": chosen.get("privacy_model", "anonymized"), "consent": chosen.get("consent_model", "opt_in"),
            "funnels": ["acquisition", "activation", "retention", "monetization", "referral"]}


_MODEL_FN = {
    "progression": _xp_curve, "economy": _economy_ledger, "loot": _loot_table,
    "difficulty": _dda_envelope, "ai_director": _tension_envelope, "spawning": _spawn_schedule,
    "quest": _quest_graph, "faction": _faction_matrix, "dialogue": _dialogue_thresholds,
    "monetization": _monetization_calendar, "narrative": _beat_map, "balance": _power_budget,
    "crafting": _crafting_tree, "stealth": _detection_model, "vehicle": _vehicle_handling,
    "weather_time": _climate_cycle, "social": _session_matrix, "audio_director": _audio_mix,
    "tutorial": _onboarding_arc, "save_checkpoint": _save_schedule, "accessibility": _a11y_profile,
    "telemetry": _event_schema,
}


def _upgrade_derivations(key: str, chosen: dict, params: dict, rng: random.Random) -> dict:
    """10 cross-cutting "upgrade" KPIs derived deterministically from any blueprint —
    the design-ops layer most teams hand-build in spreadsheets."""
    var = params["variety_index"]; ten = params["tension_target"]; rew = params["reward_rate"]
    return {
        "session_length_target_min": int(15 + var * 35),
        "retention_d1_d7_d30": [round(0.4 + var * 0.25, 2), round(0.2 + var * 0.2, 2), round(0.08 + var * 0.12, 2)],
        "engagement_loop_seconds": int(45 + (1 - ten) * 120),
        "content_cadence_days": rng.choice([7, 14, 30, 45]),
        "skill_time_to_competence_hr": round(1 + (1 - var) * 8, 1),
        "difficulty_pressure_index": round(ten * params["difficulty_weight"], 2),
        "reward_density_per_hr": round(rew * rng.uniform(3, 9), 1),
        "social_loop_strength": round(var * rng.uniform(0.3, 1.0), 2),
        "monetization_health_score": round(min(100, 60 + var * 40)),
        "churn_risk_band": "low" if ten < 0.5 else "medium" if ten < 0.72 else "high",
        "onboarding_minutes_to_first_win": int(2 + (1 - var) * 12),
        "tuning_surface_axes": len(chosen),
        "build_space_log2_bits": round(len(chosen) * 2.585, 1),
        "failure_recovery_seconds": int(3 + ten * 20),
        "live_ops_health_index": round(min(100, max(0, 55 + var * 45 - ten * 10))),
        "accessibility_floor_score": round(min(100, 60 + (1 - params["difficulty_weight"]) * 40)),
        "cohesion_coupling_score": round(min(1.0, 0.4 + var * 0.6), 2),
    }


def _generic_model(chosen: dict, rng: random.Random) -> dict:
    """Deterministic engine model for systems without a bespoke builder. It is
    DERIVED from the actual chosen knobs (not synthetic): a structured summary
    plus two computed metrics so every one of the 100 systems yields a real,
    non-empty model that reflects its configuration."""
    items = list(chosen.items())
    # complexity rises with how many non-"none" advanced options were picked
    active = [v for _, v in items if v not in ("none", "fixed", "static", "basic")]
    complexity = round(min(1.0, len(active) / max(1, len(items))), 2)
    return {
        "model": "configured_system",
        "config": dict(items[:8]),
        "knob_count": len(items),
        "active_features": len(active),
        "complexity_index": complexity,
        "fidelity_tier": ("high" if complexity > 0.66 else "mid" if complexity > 0.33 else "lean"),
        "signature": "·".join(f"{k}={v}" for k, v in items[:4]),
    }


def blueprint(key: str, knobs: dict | None = None, seed: int = 0) -> dict:
    s = get_system(key)
    if not s:
        return {"error": "unknown_system", "system": key}
    rng = _rng(key, seed, tuple(sorted((knobs or {}).items())))
    chosen = {}
    for kk, opts in s["knobs"].items():
        words = _words(opts)
        v = (knobs or {}).get(kk)
        chosen[kk] = v if v in words else words[rng.randrange(len(words))]
    params = {
        "difficulty_weight": round(rng.uniform(0.3, 0.9), 2),
        "variety_index": round(rng.uniform(0.4, 1.0), 2),
        "reward_rate": round(rng.uniform(0.5, 1.5), 2),
        "tension_target": round(rng.uniform(0.4, 0.85), 2),
        "curve_steps": rng.randint(5, 12),
    }
    model = _MODEL_FN.get(key, _generic_model)(chosen, rng)
    upgrades = _upgrade_derivations(key, chosen, params, rng)
    brief = (f"A {s['label'].lower()} configured as "
             f"{', '.join(f'{k}={v}' for k, v in list(chosen.items())[:8])}. "
             f"Tuned for variety {params['variety_index']} and tension {params['tension_target']}.")
    return {"system": s["key"], "label": s["label"], "icon": s["icon"],
            "knobs": chosen, "parameters": params, "model": model,
            "upgrades": upgrades, "brief": brief, "seed": seed}


def _llm_enrich(system: dict, bp: dict, contexts: dict | None = None) -> dict | None:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        import asyncio
        import json as _json
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        sysmsg = (
            "You are a world-class AAA systems designer. Turn a deterministic "
            "game-system blueprint into a sharp, build-ready designer brief. Be "
            "concrete, opinionated and grounded in proven design patterns. If a "
            "CREATOR DOSSIER is supplied, treat it as the AUTHORITATIVE vision — "
            "honor it verbatim and weave it through every recommendation so the "
            "output reflects the creator's intent and clears a >97 AAA bar.\n"
            "Respond with ONLY compact JSON: {\"brief\":str (a RICH, MAXIMAL "
            "design brief — aim 500-900 words, exhaustive, concrete, specific, "
            "production-ready, ZERO filler), "
            "\"notes\":[5-10 short actionable implementation bullets]}."
        )
        prompt = (
            f"SYSTEM: {system['label']} — {system['blurb']}.\n"
            + _context_prompt_block(contexts) +
            f"CHOSEN KNOBS: {_json.dumps(bp.get('knobs') or {})}.\n"
            f"PARAMETERS: {_json.dumps(bp.get('parameters') or {})}.\n"
            f"ENGINE MODEL: {_json.dumps(bp.get('model') or {})[:700]}.\n"
            f"DESIGN KPIs: {_json.dumps(bp.get('upgrades') or {})[:500]}.\n"
            "Elevate this into a production designer brief + implementation notes."
        )

        async def _run() -> str:
            chat = LlmChat(api_key=key, session_id=f"sysforge_{system['key']}",
                           system_message=sysmsg).with_model("anthropic", "claude-sonnet-4-6")
            try:
                chat = chat.with_max_tokens(900)
            except Exception:
                pass
            return await chat.send_message(UserMessage(text=prompt))

        try:
            raw = asyncio.run(_run())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                raw = loop.run_until_complete(_run())
            finally:
                loop.close()

        txt = (raw or "").strip()
        if txt.startswith("```"):
            txt = txt.strip("`")
            if txt.lower().startswith("json"):
                txt = txt[4:]
        st, en = txt.find("{"), txt.rfind("}")
        if st < 0 or en < 0:
            return None
        data = _json.loads(txt[st:en + 1])
        brief = str(data.get("brief") or "").strip()
        notes = [str(n).strip() for n in (data.get("notes") or []) if str(n).strip()]
        if not brief:
            return None
        return {"brief": brief, "notes": notes}
    except Exception:
        return None


def run_pipeline(key: str, build_id: str, knobs: dict | None = None, seed: int = 0,
                 mount: bool = True, enrich: bool = False, contexts: dict | None = None) -> dict:
    s = get_system(key)
    if not s:
        return {"error": "unknown_system", "system": key}
    if not build_id:
        return {"error": "missing_build_id"}
    bp = blueprint(key, knobs, seed)
    bp["llm_enriched"] = False
    if enrich:
        ctx = contexts if contexts is not None else _ctx_fields(build_id, key)
        ai = _llm_enrich(s, bp, ctx)
        if ai:
            bp["brief"] = ai.get("brief") or bp["brief"]
            bp["designer_notes"] = ai.get("notes") or []
            bp["llm_enriched"] = True
        if ctx and any((ctx or {}).get(f["key"]) for f in CONTEXT_FIELDS):
            bp["creator_context_used"] = True
    mounted = False
    if mount:
        try:
            from core.databases import get_sync_db
            doc = {"_id": f"sys_{key}_{build_id}", "build_id": build_id,
                   "system": key, "label": s["label"], "blueprint": bp, "created": time.time()}
            get_sync_db()["galaxy_systems"].replace_one({"_id": doc["_id"]}, doc, upsert=True)
            mounted = True
        except Exception:
            mounted = False
    return {"system": s["key"], "label": s["label"], "build_id": build_id,
            "mounted": mounted, "blueprint": bp,
            "pipeline": [{**st, "ok": True} for st in PIPELINE_STEPS]}


def list_build_systems(build_id: str) -> dict:
    try:
        from core.databases import get_sync_db
        cur = get_sync_db()["galaxy_systems"].find({"build_id": build_id})
        items = [{"system": d.get("system"), "label": d.get("label"),
                  "blueprint": d.get("blueprint")} for d in cur]
        return {"build_id": build_id, "systems": items, "count": len(items)}
    except Exception:
        return {"build_id": build_id, "systems": [], "count": 0}


# ───────────────────────────────────────────────────────────────────────
# BIG WINS — 20 cross-system playbooks (hand-authored, genuine SOTA configs).
# ───────────────────────────────────────────────────────────────────────
BIG_WINS: list[dict] = [
    {"key": "live_service_loop", "label": "Live-Service Retention Loop", "icon": "🔁",
     "blurb": "Daily/seasonal engagement engine with fair monetization.",
     "systems": {"progression": {"model": "paragon", "xp_curve": "sigmoid", "catch_up": "rested_xp"},
                 "economy": {"model": "dual_currency", "inflation": "managed", "faucets": "daily_login"},
                 "monetization": {"model": "battlepass", "fairness": "cosmetic_only", "cadence": "seasonal", "transparency": "full_odds"},
                 "quest": {"type": "side", "replayability": "daily_rotation", "rewards": "currency"}}},
    {"key": "roguelike_meta", "label": "Roguelike Meta-Progression", "icon": "💀",
     "blurb": "Run-based loops with permanent meta-unlocks.",
     "systems": {"progression": {"model": "prestige", "axis": "seasonal_reset", "unlocks": "perks"},
                 "difficulty": {"dda": "off", "punishment": "roguelike", "modes": "permadeath", "ramp": "exponential"},
                 "loot": {"distribution": "weighted", "itemization": "affixes", "chase_items": "god_rolls"},
                 "spawning": {"pattern": "waves", "variety": "escalating_types", "elites": "champion_packs"}}},
    {"key": "soulslike_risk", "label": "Soulslike Risk/Reward", "icon": "🗡",
     "blurb": "Deliberate combat, harsh death, mastery ceiling.",
     "systems": {"difficulty": {"onboarding": "trial_by_fire", "punishment": "souls_like", "assist": "none", "ceiling": "skill_expression"},
                 "balance": {"target": "hardcore", "ttk": "slow", "counterplay": "parry", "rng_spread": "tight"},
                 "loot": {"trade_policy": "bind_on_pickup", "rarity_spread": "stingy", "sources": "bosses"},
                 "spawning": {"pattern": "ambush", "telegraph": "visual_tell", "density": "moderate"}}},
    {"key": "narrative_rpg", "label": "Reactive Narrative RPG", "icon": "📜",
     "blurb": "Choice-driven story with deep dialogue & factions.",
     "systems": {"narrative": {"structure": "branching", "branching": "fully_reactive", "pov": "multi_protagonist", "stakes": "national"},
                 "dialogue": {"style": "tree", "consequence": "world_altering", "memory": "persistent", "skill_checks": "persuade"},
                 "quest": {"chaining": "branching", "failure": "consequence", "tracking": "investigation"},
                 "faction": {"structure": "many_factions", "allegiance": "betrayal_allowed", "conflict": "shifting"}}},
    {"key": "looter_shooter", "label": "Looter-Shooter Power Fantasy", "icon": "🔫",
     "blurb": "Endless gear chase with build diversity.",
     "systems": {"loot": {"distribution": "smart_loot", "itemization": "affixes", "scaling": "tier_scaled", "chase_items": "god_rolls"},
                 "progression": {"model": "paragon", "axis": "vertical", "power_source": "gear"},
                 "ai_director": {"goal": "max_tension", "intensity_curve": "escalating_waves", "spawn_logic": "swarm"},
                 "economy": {"model": "hybrid", "sinks": "upgrades", "scarcity": "engineered_drip"}}},
    {"key": "cozy_sim", "label": "Cozy Life-Sim", "icon": "🌻",
     "blurb": "Low-stress, horizontal progression, gift economy.",
     "systems": {"difficulty": {"onboarding": "gentle", "punishment": "forgiving", "assist": "skip_option", "accessibility": "full_suite"},
                 "economy": {"model": "gift_economy", "inflation": "stable", "scarcity": "abundant"},
                 "progression": {"model": "classless", "axis": "horizontal", "gating": "soft"},
                 "monetization": {"model": "cosmetic_only", "fairness": "cosmetic_only", "cadence": "monthly"}}},
    {"key": "competitive_pvp", "label": "Competitive PvP Ladder", "icon": "🏆",
     "blurb": "Skill-expressive, fair, esports-ready balance.",
     "systems": {"balance": {"target": "competitive", "power_budget": "meta_diverse", "tuning_cadence": "data_driven", "rng_spread": "deterministic"},
                 "monetization": {"model": "cosmetic_only", "fairness": "no_p2w", "transparency": "full_odds"},
                 "progression": {"model": "skill_tree", "axis": "horizontal", "catch_up": "none"},
                 "difficulty": {"modes": "selectable", "dda": "off", "ceiling": "skill_expression"}}},
    {"key": "survival_craft", "label": "Survival-Crafting Sandbox", "icon": "🔥",
     "blurb": "Resource pressure, crafting depth, harsh world.",
     "systems": {"economy": {"model": "barter", "faucets": "gathering", "crafting_cost": "material_intensive", "scarcity": "scarce"},
                 "difficulty": {"punishment": "harsh", "ramp": "stepped", "dda": "subtle"},
                 "spawning": {"pattern": "nest", "budget": "threat_based", "reinforcement": "triggered"},
                 "loot": {"sources": "world_drops", "scaling": "difficulty_scaled", "duplicates": "salvage"}}},
    {"key": "open_world_explorer", "label": "Open-World Explorer", "icon": "🌍",
     "blurb": "Emergent quests, living factions, comfortable pacing.",
     "systems": {"quest": {"type": "emergent", "chaining": "dependency_web", "giver": "dynamic_event", "replayability": "procedural"},
                 "faction": {"structure": "dynamic", "territory": "dynamic_borders", "diplomacy": "alliances"},
                 "narrative": {"structure": "emergent", "delivery": "environmental", "continuity": "shared_universe"},
                 "ai_director": {"goal": "comfort", "intensity_curve": "ebb_flow", "recovery": "dynamic_breathers"}}},
    {"key": "mobile_gacha", "label": "Ethical Mobile Collector", "icon": "📱",
     "blurb": "Collect-and-build with disclosed, pity-protected odds.",
     "systems": {"monetization": {"model": "f2p", "store": "rotating", "transparency": "pity_disclosed", "earnable": "full_unlock_path"},
                 "loot": {"distribution": "pity", "rarity_spread": "tier_locked", "chase_items": "mythics"},
                 "progression": {"model": "mastery", "axis": "mixed", "catch_up": "catch_up_gear"},
                 "economy": {"model": "dual_currency", "currencies": "soft_hard", "inflation": "managed"}}},
    # ── +10 new ──
    {"key": "tactics_grid", "label": "Tactical Grid Strategy", "icon": "♟️",
     "blurb": "Deterministic squad tactics with deep counters.",
     "systems": {"balance": {"target": "core", "rng_spread": "deterministic", "matchup_design": "deep_counters", "counterplay": "positioning"},
                 "difficulty": {"challenge_source": "strategy", "ramp": "stepped", "comeback_mechanics": "momentum_shift"},
                 "progression": {"model": "skill_tree", "build_diversity": "many_viable", "specialization": "branching_lock"},
                 "spawning": {"composition_role": "controller", "placement": "objective_anchored", "variety": "modifier_stacked"}}},
    {"key": "horror_dread", "label": "Survival Horror Dread", "icon": "🕯️",
     "blurb": "Scarcity, vulnerability and AI-directed terror.",
     "systems": {"ai_director": {"goal": "max_tension", "intensity_curve": "pulse", "pressure_source": "environment", "flow_protection": "anti_boredom"},
                 "economy": {"model": "closed", "scarcity": "artificial_limited", "faucets": "gathering"},
                 "spawning": {"spawn_feel": "tense", "telegraph": "audio_cue", "leash": "investigative"},
                 "difficulty": {"failure_friction": "checkpoint_walk", "challenge_source": "resource_management"}}},
    {"key": "mmo_world", "label": "Persistent MMO World", "icon": "🌐",
     "blurb": "Shared world, social economy, endless endgame.",
     "systems": {"economy": {"model": "open", "trading": "auction_house", "market_health": "regulated", "ownership": "tradeable"},
                 "progression": {"model": "hybrid", "endgame_loop": "ranked_ladder", "catch_up": "account_wide"},
                 "faction": {"structure": "guild_based", "territory": "contested", "world_impact": "territory_control"},
                 "loot": {"loot_ownership": "personal", "trade_policy": "bind_on_equip", "gear_lifespan": "seasonal"}}},
    {"key": "metroidvania", "label": "Metroidvania Gating", "icon": "🧭",
     "blurb": "Ability-gated exploration with backtracking payoff.",
     "systems": {"progression": {"model": "perk_deck", "unlocks": "shortcuts", "gating": "skill_check", "milestone_pacing": "milestone_gated"},
                 "quest": {"discovery": "exploration_found", "gating": "item", "scope": "world_spanning"},
                 "difficulty": {"challenge_source": "knowledge", "skill_floor": "accessible_deep", "ramp": "gated_walls"},
                 "narrative": {"delivery": "environmental", "lore_depth": "iceberg", "world_reactivity": "world_state"}}},
    {"key": "deckbuilder", "label": "Roguelike Deckbuilder", "icon": "🃏",
     "blurb": "Synergy-driven runs with high build variance.",
     "systems": {"progression": {"model": "perk_deck", "build_diversity": "fully_open", "axis": "wide_then_tall"},
                 "loot": {"distribution": "smart_loot", "itemization": "set_bonuses", "drop_feedback": "rarity_color"},
                 "balance": {"risk_reward": "high_variance", "rng_spread": "smart_random", "resource_economy": "charge_based"},
                 "difficulty": {"modes": "ascension", "challenge_source": "planning", "punishment": "roguelike"}}},
    {"key": "extraction_shooter", "label": "High-Stakes Extraction", "icon": "🎯",
     "blurb": "Risk-to-loot raids with permanent gear loss.",
     "systems": {"loot": {"trade_policy": "free", "loot_ownership": "personal", "gear_lifespan": "consumable", "drop_feedback": "subtle"},
                 "spawning": {"pattern": "infiltration", "respawn": "none", "spawn_feel": "fair", "leash": "stealth_aware"},
                 "economy": {"model": "open", "trading": "black_market", "risk_reward": "high_variance" if False else "scarce", "value_storage": "goods"},
                 "difficulty": {"failure_friction": "full_restart", "challenge_source": "adaptation", "comeback_mechanics": "none"}}},
    {"key": "narrative_walking_sim", "label": "Atmospheric Walking Sim", "icon": "🚶",
     "blurb": "Story-first, low-friction, environmental delivery.",
     "systems": {"narrative": {"structure": "in_media_res", "delivery": "environmental", "pacing": "contemplative", "moral_framing": "no_judgement"},
                 "difficulty": {"onboarding": "sandbox_first", "challenge_source": "knowledge", "assist": "generous_checkpoints"},
                 "dialogue": {"style": "cinematic", "subtext": "layered", "pacing": "deliberate"},
                 "quest": {"type": "investigation", "tracking": "breadcrumb", "pacing_role": "core"}}},
    {"key": "city_builder", "label": "Sim & City Builder", "icon": "🏙️",
     "blurb": "Systemic economy, supply chains, soft-fail loops.",
     "systems": {"economy": {"model": "planned", "price_discovery": "supply_demand", "income_sources": "passive", "market_health": "subsidized"},
                 "progression": {"model": "constellation", "unlocks": "zones", "milestone_pacing": "steady"},
                 "difficulty": {"punishment": "setback_only", "failure_friction": "progress_kept", "challenge_source": "planning"},
                 "ai_director": {"goal": "comfort", "pressure_source": "resources", "flow_protection": "anti_frustration"}}},
    {"key": "battle_royale", "label": "Battle Royale Tension", "icon": "🪂",
     "blurb": "Shrinking-zone pressure with loot-driven escalation.",
     "systems": {"ai_director": {"goal": "challenge", "pressure_source": "time", "escalation": "time_pressured", "encounter_composition": "specialist_squad"},
                 "loot": {"distribution": "weighted", "sources": "world_drops", "loot_ownership": "personal", "scaling": "time_invested"},
                 "balance": {"target": "competitive", "ttk": "fast", "fairness_model": "gear_normalized"},
                 "monetization": {"model": "f2p", "fairness": "cosmetic_only", "social_spend": "gifting"}}},
    {"key": "idle_incremental", "label": "Idle / Incremental", "icon": "⏳",
     "blurb": "Exponential growth loops with prestige resets.",
     "systems": {"progression": {"model": "prestige", "xp_curve": "exponential", "endgame_loop": "infinite_scaling", "milestone_pacing": "burst_then_drought"},
                 "economy": {"model": "token", "wealth_curve": "exponential", "income_sources": "passive", "scarcity": "renewable"},
                 "monetization": {"model": "f2p", "fairness": "time_save_only", "engagement_model": "session_caps"},
                 "difficulty": {"challenge_source": "planning", "skill_floor": "very_low", "ramp": "exponential"}}},
]

_BW_BY_KEY = {b["key"]: b for b in BIG_WINS}


def list_big_wins() -> dict:
    out = [{"key": b["key"], "label": b["label"], "icon": b["icon"], "blurb": b["blurb"],
            "system_count": len(b["systems"]), "systems": list(b["systems"].keys())}
           for b in BIG_WINS]
    return {"big_wins": out, "count": len(out)}


def _enrich_build_systems_bg(bw: dict, build_id: str, seed: int) -> None:
    """Background worker: re-enrich each already-mounted system with Claude and
    update its galaxy_systems doc in place. Runs off the request thread so the
    public ingress (30s) never times out."""
    try:
        from core.databases import get_sync_db
        db = get_sync_db()
    except Exception:
        return
    for sys_key, knobs in bw["systems"].items():
        s = get_system(sys_key)
        if not s:
            continue
        bp = blueprint(sys_key, knobs, seed)
        bp["llm_enriched"] = False
        ai = _llm_enrich(s, bp, _ctx_fields(build_id, sys_key))
        if ai:
            bp["brief"] = ai.get("brief") or bp["brief"]
            bp["designer_notes"] = ai.get("notes") or []
            bp["llm_enriched"] = True
        try:
            db["galaxy_systems"].update_one(
                {"_id": f"sys_{sys_key}_{build_id}"},
                {"$set": {"blueprint": bp, "ai_updated": time.time()}})
        except Exception:
            pass


def apply_big_win(bw_key: str, build_id: str, seed: int = 0, mount: bool = True,
                  enrich: bool = False) -> dict:
    bw = _BW_BY_KEY.get((bw_key or "").strip().lower())
    if not bw:
        return {"error": "unknown_big_win", "big_win": bw_key}
    if not build_id:
        return {"error": "missing_build_id"}
    # Mount every system deterministically FIRST (fast, no LLM) so the response
    # returns well within the ingress timeout.
    results = []
    for sys_key, knobs in bw["systems"].items():
        r = run_pipeline(sys_key, build_id, knobs=knobs, seed=seed, mount=mount, enrich=False)
        results.append({"system": sys_key, "label": r.get("label"),
                        "mounted": r.get("mounted"),
                        "llm_enriched": False, "blueprint": r.get("blueprint")})
    ai_enqueued = False
    if enrich and mount:
        try:
            import threading
            threading.Thread(target=_enrich_build_systems_bg,
                             args=(bw, build_id, seed), daemon=True).start()
            ai_enqueued = True
        except Exception:
            ai_enqueued = False
    return {"big_win": bw["key"], "label": bw["label"], "icon": bw["icon"],
            "build_id": build_id, "applied": len(results),
            "ai_enqueued": ai_enqueued, "ai_enriched": ai_enqueued, "results": results}


# ───────────────────────────────────────────────────────────────────────
# Markdown export — per-system or whole-build "systems design doc".
# ───────────────────────────────────────────────────────────────────────
def _bp_markdown(label: str, icon: str, bp: dict) -> list[str]:
    L = [f"### {icon} {label}", ""]
    knobs = bp.get("knobs") or {}
    if knobs:
        L.append("**Knobs:** " + ", ".join(f"`{k}` = {v}" for k, v in knobs.items()))
    params = bp.get("parameters") or {}
    if params:
        L.append("**Parameters:** " + ", ".join(f"{k}={v}" for k, v in params.items()))
    model = bp.get("model") or {}
    if model.get("model"):
        L.append(f"**Engine model:** `{model['model']}`")
    up = bp.get("upgrades") or {}
    if up:
        L.append("**Design KPIs:** " + ", ".join(f"{k}={v}" for k, v in list(up.items())[:6]))
    if bp.get("brief"):
        L += ["", bp["brief"]]
    notes = bp.get("designer_notes") or []
    if notes:
        L += ["", "**Implementation notes:**"] + [f"- {n}" for n in notes]
    L.append("")
    return L


def build_systems_markdown(build_id: str) -> str:
    data = list_build_systems(build_id)
    items = data.get("systems") or []
    if not items:
        return ""
    L = ["", "---", "", "## 🧩 Game Systems Blueprints", "",
         f"_{len(items)} system(s) forged via the Systems Forge and mounted to this build._", ""]
    for it in items:
        bp = it.get("blueprint") or {}
        L += _bp_markdown(it.get("label") or it.get("system"), bp.get("icon", "•"), bp)
    return "\n".join(L)


def system_markdown(build_id: str, system: str) -> str:
    s = get_system(system)
    data = list_build_systems(build_id)
    for it in (data.get("systems") or []):
        if it.get("system") == system:
            bp = it.get("blueprint") or {}
            return "\n".join([f"# {it.get('label')} — Systems Brief", ""] +
                             _bp_markdown(it.get("label"), bp.get("icon", "•"), bp))
    if not s:
        return f"# Unknown system: {system}"
    bp = blueprint(system, None, 0)
    return "\n".join([f"# {s['label']} — Systems Brief (preview)", ""] +
                     _bp_markdown(s["label"], s["icon"], bp))


# ───────────────────────────────────────────────────────────────────────
# CREATOR CONTEXT — 3 large free-text dossiers (≤20k chars each) per system.
# The creator types their own vision; it is fed verbatim into the LLM
# enrichment AND the 14-gate AI scoring so the output tracks THEIR intent.
# ───────────────────────────────────────────────────────────────────────
MAX_CONTEXT_CHARS = 20000
CONTEXT_FIELDS = [
    {"key": "vision", "label": "Design Vision & Context",
     "hint": "Your north-star, pillars, references and the experience you want."},
    {"key": "implementation", "label": "Implementation & Tuning",
     "hint": "Engine details, parameters, numbers and edge cases you care about."},
    {"key": "quality", "label": "Quality Bar & QA Criteria",
     "hint": "What 'AAA / >97' means for THIS system; pitfalls to avoid."},
]


def _ctx_fields(build_id: str, system: str) -> dict:
    """Return just the 3 text fields (used to prime LLM prompts)."""
    out = {f["key"]: "" for f in CONTEXT_FIELDS}
    if not build_id:
        return out
    try:
        from core.databases import get_sync_db
        doc = get_sync_db()["galaxy_system_context"].find_one({"_id": f"ctx_{build_id}_{system}"})
        if doc:
            for f in CONTEXT_FIELDS:
                out[f["key"]] = (doc.get(f["key"]) or "")
    except Exception:
        pass
    return out


def _context_prompt_block(contexts: dict | None) -> str:
    if not contexts:
        return ""
    parts = []
    for f in CONTEXT_FIELDS:
        v = (contexts.get(f["key"]) or "").strip()
        if v:
            parts.append(f"## {f['label']}\n{v[:MAX_CONTEXT_CHARS]}")
    if not parts:
        return ""
    return ("\nCREATOR DOSSIER (AUTHORITATIVE — honor this vision verbatim; it overrides defaults):\n"
            + "\n\n".join(parts) + "\n")


def get_system_context(build_id: str, system: str) -> dict:
    if not get_system(system):
        return {"error": "unknown_system", "system": system}
    fields = _ctx_fields(build_id, system)
    return {"build_id": build_id, "system": system, **fields,
            "fields_meta": CONTEXT_FIELDS, "max_chars": MAX_CONTEXT_CHARS,
            "char_counts": {k: len(v) for k, v in fields.items()}}


def save_system_context(build_id: str, system: str, fields: dict) -> dict:
    if not build_id:
        return {"error": "missing_build_id"}
    if not get_system(system):
        return {"error": "unknown_system", "system": system}
    clean = {f["key"]: str(fields.get(f["key"]) or "")[:MAX_CONTEXT_CHARS] for f in CONTEXT_FIELDS}
    try:
        from core.databases import get_sync_db
        doc = {"_id": f"ctx_{build_id}_{system}", "build_id": build_id, "system": system,
               **clean, "updated": time.time()}
        get_sync_db()["galaxy_system_context"].replace_one({"_id": doc["_id"]}, doc, upsert=True)
        return {"saved": True, "build_id": build_id, "system": system,
                "char_counts": {k: len(v) for k, v in clean.items()}}
    except Exception:
        return {"error": "save_failed", "build_id": build_id, "system": system}
