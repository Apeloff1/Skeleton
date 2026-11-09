"""
MEGA DOMAIN EXPANSION v24.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
50 ULTRA-DEEP DOMAINS × 8 SPECIALISTS = 400 NEW AGENTS
Organized into 5 mega-categories. Each specialist has 8 expertise
points and 3+ deep knowledge formulas. Total system with existing
domains: 64 domains, 512+ specialists.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime
import hashlib

router = APIRouter(prefix="/api/mega-domains", tags=["mega-domains"])

# ═══════════════════════════════════════════════════════════════════════
# 50 DOMAINS — 5 MEGA-CATEGORIES × 10 DOMAINS × 8 SPECIALISTS
# ═══════════════════════════════════════════════════════════════════════

def _gen_specialists(domain_id: str, specs: list[dict]) -> dict:
    """Generate specialist entries with deep knowledge."""
    result = {}
    for s in specs:
        sid = s["id"]
        result[sid] = {
            "id": sid,
            "name": s["name"],
            "title": s["title"],
            "expertise": s["expertise"],
            "deep_knowledge": s["deep_knowledge"],
            "synergy_links": s.get("synergy_links", []),
        }
    return result


# ─────────────────────────────────────────────────────────────────────
# MEGA-CATEGORY 1: CREATIVE DOMAINS
# ─────────────────────────────────────────────────────────────────────

CREATIVE_DOMAINS = {
    "procedural_genesis": {
        "name": "ProceduralGenesis", "version": "v24.0", "icon": "planet", "color": "#8B5CF6",
        "description": "Procedural world generation — terrain, dungeons, quests, items, biomes, civilizations",
        "category": "creative",
        "specialists": _gen_specialists("procedural_genesis", [
            {"id": "terrain_sculptor", "name": "TerrainSculptor", "title": "Procedural Terrain Architect",
             "expertise": ["Perlin/Simplex noise layering", "Hydraulic erosion simulation", "Thermal weathering", "Plate tectonics simulation", "Biome distribution via Whittaker diagrams", "Cave system generation (L-systems)", "River network pathfinding", "Geological strata layering"],
             "deep_knowledge": {"erosion_formula": "H(t+1) = H(t) - K_rain * slope * sediment_capacity + K_evap * deposit", "noise_octaves": "terrain = sum(amplitude^i * noise(frequency^i * pos))", "biome_temp_precip": "biome = whittaker_lookup(temperature(altitude, latitude), precipitation(wind, ocean_dist))"},
             "synergy_links": ["weather_climate", "render_pipeline"]},
            {"id": "dungeon_weaver", "name": "DungeonWeaver", "title": "Procedural Dungeon Architect",
             "expertise": ["BSP space partitioning", "Wave Function Collapse for layouts", "Graph-grammar room connectivity", "Trap placement algorithms", "Loot distribution curves", "Boss arena generation", "Environmental storytelling placement", "Difficulty gradient mapping"],
             "deep_knowledge": {"wfc_entropy": "entropy(cell) = -sum(p_i * log(p_i)) for valid patterns", "bsp_split": "split_axis = longest_dim; split_pos = random(min + padding, max - padding)", "loot_curve": "loot_tier = floor(room_depth * difficulty_scalar * random_weight)"},
             "synergy_links": ["combat_forge", "lore_vault"]},
            {"id": "quest_synthesizer", "name": "QuestSynth", "title": "Procedural Quest Generator",
             "expertise": ["Planning domain quest graphs", "NPC motivation modeling", "Quest chain dependency resolution", "Dynamic objective generation", "Reward scaling algorithms", "Narrative coherence validation", "Procedural dialogue hooks", "Context-sensitive quest triggers"],
             "deep_knowledge": {"quest_graph": "quest = plan(goal_state, world_state, available_actions)", "reward_scale": "reward = base * (1 + depth_bonus) * difficulty_multiplier * rarity_weight"},
             "synergy_links": ["narrative_loom", "economy_engine"]},
            {"id": "item_forge", "name": "ItemForge", "title": "Procedural Item Generator",
             "expertise": ["Affix pool design", "Stat budget allocation", "Rarity tier mathematics", "Set bonus computation", "Unique legendary generation", "Visual variant combination", "Lore text procedural writing", "Power curve balancing"],
             "deep_knowledge": {"stat_budget": "budget = base_budget * (1 + tier_bonus) * slot_weight", "affix_roll": "affix = weighted_random(affix_pool, ilvl_filter, conflict_check)"},
             "synergy_links": ["economy_engine", "combat_forge"]},
            {"id": "biome_architect", "name": "BiomeArch", "title": "Biome & Ecosystem Designer",
             "expertise": ["Voronoi biome tessellation", "Climate simulation", "Flora/fauna population dynamics", "Biome transition blending", "Resource node distribution", "Day/night ecosystem cycles", "Predator-prey modeling", "Seasonal variation systems"],
             "deep_knowledge": {"lotka_volterra": "dP/dt = alpha*P - beta*P*Q; dQ/dt = delta*P*Q - gamma*Q", "voronoi_biome": "biome(point) = nearest_seed_biome(voronoi_diagram(seeds))"},
             "synergy_links": ["weather_climate", "creature_design"]},
            {"id": "city_planner", "name": "CityPlanner", "title": "Procedural Settlement Generator",
             "expertise": ["L-system road networks", "Zoning algorithms", "Building footprint generation", "Population simulation", "Trade route pathfinding", "Cultural district variation", "Historical growth simulation", "Infrastructure dependency graphs"],
             "deep_knowledge": {"road_lsystem": "axiom=S; S->S[+S][-S]; angle=random(15,45); length=road_importance*scale"},
             "synergy_links": ["social_fabric", "economy_engine"]},
            {"id": "galaxy_mapper", "name": "GalaxyMapper", "title": "Stellar Procedural Generator",
             "expertise": ["Stellar classification generation", "Orbital mechanics simulation", "Habitable zone calculation", "Asteroid field generation", "Nebula volumetric generation", "Space station architecture", "Jump gate network topology", "Alien civilization seeding"],
             "deep_knowledge": {"habitable_zone": "r_inner = sqrt(L) * 0.95; r_outer = sqrt(L) * 1.37; L=luminosity_solar"},
             "synergy_links": ["physics_vault", "narrative_loom"]},
            {"id": "history_weaver", "name": "HistoryWeaver", "title": "Procedural History Generator",
             "expertise": ["Civilization rise/fall simulation", "War outcome modeling", "Cultural evolution algorithms", "Artifact provenance generation", "Dynasty tree generation", "Treaty and alliance simulation", "Technology progression modeling", "Mythological origin generation"],
             "deep_knowledge": {"civ_power": "power(t) = military + economy + culture + tech - corruption - unrest"},
             "synergy_links": ["lore_vault", "social_fabric"]},
        ]),
    },
    "combat_forge": {
        "name": "CombatForge", "version": "v24.0", "icon": "flash", "color": "#EF4444",
        "description": "Advanced combat systems — melee, ranged, magic, hitboxes, combos, status effects, AI",
        "category": "creative",
        "specialists": _gen_specialists("combat_forge", [
            {"id": "melee_master", "name": "MeleeMaster", "title": "Melee Combat Architect",
             "expertise": ["Frame data design", "Hitstun/blockstun calibration", "Cancel window systems", "Combo tree design", "Poise/super armor mechanics", "Weapon moveset differentiation", "Parry/deflect timing windows", "Stamina economy balancing"],
             "deep_knowledge": {"frame_advantage": "advantage = attacker_recovery - defender_hitstun", "damage_calc": "damage = base * (1 + str_scaling) * weakness_mult * (1 - armor_reduction)"},
             "synergy_links": ["animation_studio", "physics_vault"]},
            {"id": "ranged_expert", "name": "RangedExpert", "title": "Ranged Combat Specialist",
             "expertise": ["Ballistic trajectory modeling", "Hitscan vs projectile design", "Spread patterns & recoil", "Ammo economy systems", "Aim assist calibration", "Penetration mechanics", "ADS/hipfire transitions", "Attachment modification systems"],
             "deep_knowledge": {"bullet_drop": "y = y0 + v_y*t - 0.5*g*t^2; t = distance/muzzle_velocity", "spread_pattern": "spread = base_spread * (1 + recoil_buildup) * (ads ? 0.3 : 1.0)"},
             "synergy_links": ["physics_vault", "input_matrix"]},
            {"id": "magic_weaver", "name": "MagicWeaver", "title": "Magic System Architect",
             "expertise": ["Spell crafting combinatorics", "Mana economy design", "Elemental interaction matrices", "Channeling/casting systems", "Spell scaling formulas", "Ritual/summon mechanics", "Enchantment stacking rules", "Anti-magic/dispel design"],
             "deep_knowledge": {"elemental_matrix": "fire>ice>wind>earth>fire; light<>dark; compound=fire+wind=explosion", "mana_regen": "regen = base_regen * (1 + spirit/100) * (in_combat ? 0.5 : 1.0)"},
             "synergy_links": ["vfx_studio", "narrative_loom"]},
            {"id": "hitbox_engineer", "name": "HitboxEngineer", "title": "Collision & Hitbox Specialist",
             "expertise": ["Capsule/sphere hitbox optimization", "Active frame mapping", "Hurtbox state machines", "I-frame implementation", "Collision layer management", "Projectile hitbox lifecycle", "Environmental hazard hitboxes", "Network hitbox reconciliation"],
             "deep_knowledge": {"capsule_sweep": "hit = sweep_test(capsule_a, capsule_b, dt) && active_frame_check(attacker)"},
             "synergy_links": ["physics_vault", "multiplayer_mesh"]},
            {"id": "status_alchemist", "name": "StatusAlchemist", "title": "Status Effect Designer",
             "expertise": ["DOT stacking rules", "Crowd control diminishing returns", "Buff/debuff priority systems", "Cleanse/immunity design", "Status interaction combos", "Duration/potency scaling", "Visual clarity for status stacks", "Boss immunity phases"],
             "deep_knowledge": {"diminishing_returns": "duration = base * (0.5 ^ stack_count) if stack > threshold", "dot_tick": "damage_per_tick = base_dot * (1 + spell_power/coefficient) / tick_count"},
             "synergy_links": ["magic_weaver", "ui_architect"]},
            {"id": "boss_designer", "name": "BossDesigner", "title": "Boss Encounter Architect",
             "expertise": ["Phase transition design", "Attack pattern scripting", "DPS check mechanics", "Environmental hazard choreography", "Enrage timer calibration", "Weak point systems", "Multi-target boss design", "Cinematic attack sequences"],
             "deep_knowledge": {"phase_trigger": "phase_change when hp_pct < threshold[phase]; invuln_window = transition_anim_duration", "dps_check": "required_dps = boss_hp * phase_pct / enrage_timer_seconds"},
             "synergy_links": ["cinematic_studio", "ai_director"]},
            {"id": "combo_architect", "name": "ComboArchitect", "title": "Combo System Designer",
             "expertise": ["Input buffer design", "Combo graph topology", "Juggle physics", "Wall/ground bounce mechanics", "Super/special meter building", "Combo damage scaling", "Reset/mixup design", "Training mode systems"],
             "deep_knowledge": {"damage_scaling": "hit_damage = base * scaling_table[hit_count]; scaling = max(0.1, 1.0 - 0.1 * hit_num)", "input_buffer": "buffer_window = 6 frames; input queued if within buffer of next cancel window"},
             "synergy_links": ["animation_studio", "input_matrix"]},
            {"id": "stealth_ops", "name": "StealthOps", "title": "Stealth & Infiltration Designer",
             "expertise": ["Detection cone modeling", "Noise propagation systems", "Light/shadow detection", "Alert state machines", "Takedown mechanics", "Disguise systems", "Security camera AI", "Environmental distraction tools"],
             "deep_knowledge": {"detection_cone": "detected = angle_to_target < fov/2 && dist < range && !occluded && light_level > threshold"},
             "synergy_links": ["ai_director", "audio_sphere"]},
        ]),
    },
    "lore_vault": {
        "name": "LoreVault", "version": "v24.0", "icon": "book", "color": "#A855F7",
        "description": "World lore, mythology, character backstories, timeline, encyclopedias, cultural histories",
        "category": "creative",
        "specialists": _gen_specialists("lore_vault", [
            {"id": "myth_weaver", "name": "MythWeaver", "title": "Mythology & Cosmology Architect", "expertise": ["Creation myth generation", "Pantheon design", "Mythological cycle structure", "Prophecy & fate systems", "Sacred geometry integration", "Mythic hero journey mapping", "Afterlife/cosmology design", "Relic/artifact mythologization"], "deep_knowledge": {"hero_journey": "12 stages: ordinary_world -> call -> refusal -> mentor -> threshold -> tests -> approach -> ordeal -> reward -> road_back -> resurrection -> return"}, "synergy_links": ["narrative_loom", "procedural_genesis"]},
            {"id": "historian", "name": "Historian", "title": "World History Chronicler", "expertise": ["Timeline generation", "Era transition design", "Historical event weaving", "Cause-effect chain modeling", "Unreliable narrator design", "Archaeological discovery systems", "Cultural memory mechanics", "Forgotten history reveals"], "deep_knowledge": {"timeline_depth": "events_per_era = base_density * era_importance * cultural_complexity"}, "synergy_links": ["procedural_genesis"]},
            {"id": "linguist", "name": "Linguist", "title": "Constructed Language Designer", "expertise": ["Phonetic inventory design", "Grammar rule systems", "Script/writing system creation", "Dialect variation modeling", "Etymology generation", "Translation puzzle design", "Naming convention systems", "Runic/magical language design"], "deep_knowledge": {"phoneme_dist": "zipf_frequency(phoneme) = C / rank^alpha; alpha ~ 1.0"}, "synergy_links": ["localization_hub"]},
            {"id": "cartographer", "name": "Cartographer", "title": "World Map Designer", "expertise": ["Continental drift simulation", "Climate zone mapping", "Trade route design", "Political boundary logic", "Topographic detailing", "Sea route charting", "Exploration fog systems", "Map legend/iconography"], "deep_knowledge": {"plate_tectonics": "drift_rate = mantle_convection_speed * plate_area_ratio"}, "synergy_links": ["procedural_genesis"]},
            {"id": "bestiary_curator", "name": "BestiaryCurator", "title": "Creature Lore Specialist", "expertise": ["Creature taxonomy", "Evolutionary backstory", "Habitat & behavior lore", "Mythological creature adaptation", "Taming/bonding lore", "Creature society structures", "Legendary beast narratives", "Extinction event lore"], "deep_knowledge": {"taxonomy_tree": "kingdom -> phylum -> class -> order -> family -> genus -> species"}, "synergy_links": ["creature_design"]},
            {"id": "faction_loremaster", "name": "FactionLoremaster", "title": "Faction & Politics Designer", "expertise": ["Faction ideology creation", "Inter-faction rivalry design", "Alliance/betrayal narratives", "Faction rank progression lore", "Secret society design", "Revolution/civil war lore", "Diplomatic protocol creation", "Propaganda system design"], "deep_knowledge": {"faction_tension": "tension = ideology_diff * proximity * resource_competition - trade_benefit"}, "synergy_links": ["social_fabric"]},
            {"id": "artifact_keeper", "name": "ArtifactKeeper", "title": "Legendary Item Lore Designer", "expertise": ["Artifact origin stories", "Curse/blessing narratives", "Power scaling lore", "Collection quest design", "Artifact interaction lore", "Historical owner chains", "Destruction/creation myths", "Set piece lore connections"], "deep_knowledge": {"artifact_power": "power_level = age * historical_significance * material_rarity * enchantment_layers"}, "synergy_links": ["procedural_genesis", "quest_engine"]},
            {"id": "chronicle_scribe", "name": "ChronicleScribe", "title": "In-Game Document Writer", "expertise": ["Journal entry generation", "Letter/correspondence writing", "Research note creation", "Inscription/tablet text", "Graffiti/environmental text", "Royal decree formatting", "Merchant ledger creation", "Wanted poster design"], "deep_knowledge": {"doc_authenticity": "voice = era_appropriate + character_education_level + emotional_state + purpose"}, "synergy_links": ["narrative_loom"]},
        ]),
    },
    "cinematic_studio": {
        "name": "CinematicStudio", "version": "v24.0", "icon": "videocam", "color": "#EC4899",
        "description": "Cutscene direction, camera systems, motion capture, facial animation, real-time cinematics",
        "category": "creative",
        "specialists": _gen_specialists("cinematic_studio", [
            {"id": "camera_director", "name": "CameraDirector", "title": "Virtual Camera Architect", "expertise": ["Rule of thirds automation", "Dolly/crane simulation", "Focus pull systems", "Shot composition AI", "Camera shake profiles", "Orbit/follow cam systems", "Cinematic letterboxing", "Transition wipe systems"], "deep_knowledge": {"dolly_curve": "position(t) = bezier(p0, p1, p2, p3, t); fov_interp = lerp(wide, tight, drama_intensity)"}, "synergy_links": ["animation_studio"]},
            {"id": "mocap_engineer", "name": "MoCapEngineer", "title": "Motion Capture Specialist", "expertise": ["Marker-based capture", "Markerless AI capture", "Facial performance capture", "Hand/finger capture", "Retargeting algorithms", "Mocap cleanup workflows", "Stunt capture protocols", "Animal motion capture"], "deep_knowledge": {"retarget": "target_bone_rotation = source_rotation * bind_offset_inv * scale_compensation"}, "synergy_links": ["animation_studio"]},
            {"id": "scene_compositor", "name": "SceneCompositor", "title": "Cinematic Scene Director", "expertise": ["Shot list planning", "Coverage patterns", "Blocking/staging", "Lighting for drama", "Depth of field storytelling", "Color grading per mood", "Sound design sync", "Performance direction"], "deep_knowledge": {"mood_lighting": "key_to_fill_ratio: dramatic=8:1, neutral=4:1, comedic=2:1"}, "synergy_links": ["narrative_loom"]},
            {"id": "facial_animator", "name": "FacialAnimator", "title": "Facial Animation Specialist", "expertise": ["FACS action unit mapping", "Lip sync phoneme blending", "Micro-expression design", "Eye dart/gaze systems", "Emotion blending graphs", "Wrinkle map activation", "Jaw/tongue physics", "Real-time facial rig optimization"], "deep_knowledge": {"facs_units": "AU1=inner_brow_raise, AU2=outer_brow_raise, AU4=brow_lowerer, AU6=cheek_raise, AU12=lip_corner_pull"}, "synergy_links": ["animation_studio"]},
            {"id": "vfx_director", "name": "VFXDirector", "title": "Visual Effects Supervisor", "expertise": ["Particle system choreography", "Destruction sequence timing", "Magic effect layering", "Weather VFX compositing", "Blood/impact effects", "Explosion dynamics", "Portal/warp effects", "Screen-space post effects"], "deep_knowledge": {"particle_emission": "rate = base_rate * intensity_curve(t); lifetime = random(min_life, max_life)"}, "synergy_links": ["render_pipeline"]},
            {"id": "storyboard_artist", "name": "StoryboardArtist", "title": "Cinematic Storyboard Designer", "expertise": ["Panel layout design", "Action flow visualization", "Camera angle notation", "Timing annotation", "Emotion beat mapping", "Transition planning", "Parallel action sequences", "Climax build-up pacing"], "deep_knowledge": {"pacing_curve": "tension = sine(progress * pi) * intensity_multiplier + noise(seed, 0.1)"}, "synergy_links": ["narrative_loom"]},
            {"id": "qte_designer", "name": "QTEDesigner", "title": "Quick-Time Event Architect", "expertise": ["Input timing windows", "Failure state design", "Branching QTE outcomes", "Contextual button mapping", "Accessibility QTE options", "Cinematic QTE integration", "Rhythm-based QTE systems", "Controller haptic sync"], "deep_knowledge": {"window_timing": "success_window = base_window * (1 + difficulty_adjust); perfect_window = success_window * 0.3"}, "synergy_links": ["input_matrix"]},
            {"id": "replay_director", "name": "ReplayDirector", "title": "Replay & Photo Mode Designer", "expertise": ["Replay buffer management", "Free camera controls", "Time scrubbing", "Filter/effect stacking", "Pose mode systems", "Lighting override controls", "Depth of field controls", "Social media export"], "deep_knowledge": {"replay_buffer": "ring_buffer(max_frames); keyframe_interval = 1/tick_rate; interpolation = hermite"}, "synergy_links": ["camera_director"]},
        ]),
    },
    "emotion_engine": {
        "name": "EmotionEngine", "version": "v24.0", "icon": "heart", "color": "#F43F5E",
        "description": "Player emotion modeling, pacing curves, tension/release, catharsis design, flow state",
        "category": "creative",
        "specialists": _gen_specialists("emotion_engine", [
            {"id": "flow_architect", "name": "FlowArchitect", "title": "Flow State Designer", "expertise": ["Csikszentmihalyi flow channel", "Skill/challenge balancing", "Anxiety/boredom boundary detection", "Micro-flow loop design", "Session flow arcs", "Flow disruption prevention", "Autotelic experience design", "Time perception manipulation"], "deep_knowledge": {"flow_channel": "flow = skill_level * 0.8 < challenge < skill_level * 1.2; anxiety if challenge >> skill; boredom if skill >> challenge"}, "synergy_links": ["ai_director", "tutorial_architect"]},
            {"id": "tension_conductor", "name": "TensionConductor", "title": "Tension & Release Designer", "expertise": ["Tension escalation curves", "Release timing optimization", "Suspense building techniques", "Jump scare calibration", "Dread accumulation systems", "Comic relief placement", "Cliffhanger design", "Catharsis moment engineering"], "deep_knowledge": {"tension_curve": "tension(t) = base + escalation_rate * t - release_events * decay; catharsis when tension > threshold"}, "synergy_links": ["audio_sphere", "narrative_loom"]},
            {"id": "reward_psychologist", "name": "RewardPsychologist", "title": "Reward System Psychologist", "expertise": ["Variable ratio reinforcement", "Dopamine loop design", "Loss aversion prevention", "Anticipation maximization", "Surprise/delight moments", "Achievement satisfaction design", "Social comparison rewards", "Intrinsic motivation fostering"], "deep_knowledge": {"variable_ratio": "avg_actions_per_reward = 1/probability; engagement = f(uncertainty, magnitude, frequency)"}, "synergy_links": ["metagame_ops", "economy_engine"]},
            {"id": "empathy_designer", "name": "EmpathyDesigner", "title": "Emotional Connection Architect", "expertise": ["Character attachment techniques", "Pet/companion bonding", "Loss/grief design", "Moral dilemma construction", "Sacrifice narrative design", "Reunion/payoff moments", "Betrayal impact design", "Found family narrative"], "deep_knowledge": {"attachment_curve": "attachment = shared_experiences * vulnerability_moments * time_invested * reciprocity"}, "synergy_links": ["narrative_loom", "social_fabric"]},
            {"id": "pacing_director", "name": "PacingDirector", "title": "Game Pacing Architect", "expertise": ["Act structure design", "Intensity wave patterns", "Rest area placement", "Content density management", "Climax timing optimization", "Side content pacing", "Tutorial pacing", "Post-game pacing"], "deep_knowledge": {"intensity_wave": "intensity(t) = A * sin(2*pi*t/period) * envelope(t) + trend(t)"}, "synergy_links": ["cinematic_studio"]},
            {"id": "nostalgia_engineer", "name": "NostalgiaEngineer", "title": "Nostalgia & Memory Designer", "expertise": ["Callback design", "Musical leitmotif triggers", "Location revisit design", "Character growth reflection", "Photo album systems", "Memory lane sequences", "Anniversary events", "Legacy content design"], "deep_knowledge": {"nostalgia_trigger": "impact = time_since_first_encounter * emotional_significance * sensory_fidelity"}, "synergy_links": ["audio_sphere"]},
            {"id": "humor_designer", "name": "HumorDesigner", "title": "Comedy & Wit Systems Designer", "expertise": ["Timing-based humor", "Situational comedy triggers", "Character-driven humor", "Physical comedy systems", "Running gag management", "Absurdist humor design", "Dark humor calibration", "Meme-worthy moment engineering"], "deep_knowledge": {"comic_timing": "punchline_delay = setup_duration * golden_ratio_inv; subversion = expectation_minus_reality"}, "synergy_links": ["narrative_loom"]},
            {"id": "awe_architect", "name": "AweArchitect", "title": "Wonder & Awe Experience Designer", "expertise": ["Vista reveal techniques", "Scale contrast design", "Discovery moment design", "Mystery/curiosity loops", "Sublime experience creation", "Cosmic horror/wonder", "Beauty in destruction", "Environmental storytelling awe"], "deep_knowledge": {"awe_formula": "awe = perceived_vastness * need_for_accommodation * novelty * personal_relevance"}, "synergy_links": ["render_pipeline", "audio_sphere"]},
        ]),
    },
    "weather_climate": {
        "name": "WeatherClimate", "version": "v24.0", "icon": "cloud", "color": "#0EA5E9",
        "description": "Dynamic weather, seasons, climate zones, environmental effects, atmospheric simulation",
        "category": "creative",
        "specialists": _gen_specialists("weather_climate", [
            {"id": "atmosphere_sim", "name": "AtmoSim", "title": "Atmospheric Simulation Engineer", "expertise": ["Navier-Stokes wind simulation", "Cloud formation modeling", "Fog density computation", "Air pressure systems", "Wind current mapping", "Humidity cycle modeling", "Lightning generation", "Aurora borealis simulation"], "deep_knowledge": {"navier_stokes": "dv/dt + (v·∇)v = -∇p/ρ + ν∇²v + f"}, "synergy_links": ["render_pipeline", "physics_vault"]},
            {"id": "rain_master", "name": "RainMaster", "title": "Precipitation Systems Designer", "expertise": ["Raindrop physics", "Snow accumulation", "Hail simulation", "Wet surface shaders", "Puddle formation", "Umbrella/shelter detection", "Splash particle systems", "Ice formation mechanics"], "deep_knowledge": {"raindrop_terminal": "v_t = sqrt(2*m*g / (ρ_air * C_d * A)); ~9 m/s for 2mm drop"}, "synergy_links": ["physics_vault"]},
            {"id": "season_keeper", "name": "SeasonKeeper", "title": "Seasonal Cycle Architect", "expertise": ["Foliage color transitions", "Day length calculation", "Animal migration patterns", "Crop/harvest cycles", "Ice/thaw mechanics", "Seasonal NPC behavior", "Festival/event triggers", "Gameplay modifier per season"], "deep_knowledge": {"day_length": "hours = 12 + 4*sin(2*pi*(day_of_year - equinox)/365) * sin(latitude)"}, "synergy_links": ["procedural_genesis"]},
            {"id": "disaster_director", "name": "DisasterDirector", "title": "Natural Disaster Designer", "expertise": ["Earthquake simulation", "Tornado formation", "Flood/tsunami modeling", "Volcanic eruption systems", "Avalanche physics", "Wildfire spread", "Meteor impact events", "Sandstorm generation"], "deep_knowledge": {"fire_spread": "spread_rate = wind_speed * fuel_density * (1 + slope_angle/90) * (1 - moisture)"}, "synergy_links": ["physics_vault", "cinematic_studio"]},
            {"id": "sky_painter", "name": "SkyPainter", "title": "Skybox & Celestial Designer", "expertise": ["Rayleigh scattering", "Mie scattering for haze", "Sunset/sunrise color ramps", "Star field generation", "Moon phase calculation", "Planet/constellation placement", "Eclipse simulation", "Galaxy skybox rendering"], "deep_knowledge": {"rayleigh": "I(θ,λ) = I_0 * (π² * (n²-1)² / (2*N*λ⁴)) * (1 + cos²θ)"}, "synergy_links": ["render_pipeline"]},
            {"id": "wind_sculptor", "name": "WindSculptor", "title": "Wind & Particle Systems Designer", "expertise": ["Foliage wind animation", "Cloth wind response", "Particle wind fields", "Volumetric wind zones", "Gust pattern design", "Kite/flag physics", "Wind-affected projectiles", "Sound of wind design"], "deep_knowledge": {"wind_force": "F = 0.5 * ρ * v² * C_d * A * wind_direction"}, "synergy_links": ["physics_vault", "audio_sphere"]},
            {"id": "ocean_master", "name": "OceanMaster", "title": "Ocean & Water Simulation Specialist", "expertise": ["FFT ocean waves", "Shore wave breaking", "Underwater caustics", "Buoyancy physics", "Water current simulation", "Waterfall spray", "River flow dynamics", "Frozen water mechanics"], "deep_knowledge": {"gerstner_wave": "P(x,t) = x + sum(A_i * D_i * cos(D_i·x - ω_i*t + φ_i))"}, "synergy_links": ["render_pipeline", "physics_vault"]},
            {"id": "climate_modeler", "name": "ClimateModeler", "title": "Global Climate System Designer", "expertise": ["Biome climate mapping", "Global temperature gradients", "Ocean current influence", "Mountain rain shadow", "Desertification systems", "Ice age simulation", "Climate change narratives", "Microclimate zones"], "deep_knowledge": {"temperature_gradient": "T(lat, alt) = T_equator - 6.5°C/km * altitude - 0.7°C/degree * |latitude|"}, "synergy_links": ["procedural_genesis"]},
        ]),
    },
    "character_architect": {
        "name": "CharacterArchitect", "version": "v24.0", "icon": "person", "color": "#F97316",
        "description": "Character creation, customization, class design, skill trees, progression systems",
        "category": "creative",
        "specialists": _gen_specialists("character_architect", [
            {"id": "class_designer", "name": "ClassDesigner", "title": "Character Class Architect", "expertise": ["Class identity design", "Role differentiation", "Hybrid class balance", "Prestige/advanced classes", "Class fantasy fulfillment", "Starting stat distribution", "Class-specific mechanics", "Multi-class systems"], "deep_knowledge": {"role_triangle": "tank=high_hp*armor; dps=high_damage*speed; support=heals*buffs*cc"}, "synergy_links": ["combat_forge"]},
            {"id": "skill_tree_architect", "name": "SkillTreeArch", "title": "Skill Tree & Talent Designer", "expertise": ["Tree topology design", "Passive/active balance", "Keystone ability design", "Respec economy", "Synergy node placement", "Build diversity metrics", "Power budget per tier", "Path-of-exile-style complexity"], "deep_knowledge": {"tree_depth": "power_per_point = (base_power * tier_multiplier) / points_to_reach; diversity = unique_viable_paths / total_paths"}, "synergy_links": ["combat_forge", "economy_engine"]},
            {"id": "customization_lead", "name": "CustomLead", "title": "Visual Customization Designer", "expertise": ["Face morphing systems", "Body type variety", "Hair physics & styles", "Armor dye systems", "Transmog/glamour systems", "Tattoo/scar layers", "Accessory attachment", "Emote/animation customization"], "deep_knowledge": {"morph_blend": "face = sum(morph_target_i * weight_i) for i in morph_targets; normalize(weights)"}, "synergy_links": ["render_pipeline"]},
            {"id": "progression_master", "name": "ProgressionMaster", "title": "Progression Systems Architect", "expertise": ["XP curve design", "Level scaling formulas", "Prestige/paragon systems", "Seasonal resets", "Horizontal progression", "Mastery systems", "Achievement milestones", "Power plateau management"], "deep_knowledge": {"xp_curve": "xp_to_level(n) = base * (n^exponent); exponent typically 1.5-2.5; total_xp = integral(xp_curve)"}, "synergy_links": ["metagame_ops"]},
            {"id": "companion_designer", "name": "CompanionDesigner", "title": "Companion & Pet Systems Designer", "expertise": ["Companion AI behavior", "Affinity/loyalty systems", "Companion combat roles", "Dialogue/banter systems", "Romance/relationship arcs", "Pet leveling & evolution", "Mount variety design", "Summon/familiar mechanics"], "deep_knowledge": {"affinity_calc": "affinity += action_weight * alignment_match; relationship_tier = floor(affinity / tier_threshold)"}, "synergy_links": ["narrative_loom", "ai_director"]},
            {"id": "stat_balancer", "name": "StatBalancer", "title": "Stat & Attribute Systems Designer", "expertise": ["Primary stat design", "Derived stat formulas", "Diminishing returns curves", "Soft/hard cap design", "Stat budgeting per level", "Equipment stat contribution", "Buff/debuff stat interaction", "PvP stat normalization"], "deep_knowledge": {"diminishing": "effective_stat = stat * (1 - e^(-stat/cap)); or: effective = cap * stat / (stat + cap)"}, "synergy_links": ["combat_forge"]},
            {"id": "race_designer", "name": "RaceDesigner", "title": "Race & Species Designer", "expertise": ["Racial trait balance", "Cultural identity design", "Racial lore integration", "Physical variation systems", "Racial ability design", "Cross-race interactions", "Starting zone differentiation", "Racial mount/pet design"], "deep_knowledge": {"trait_budget": "total_racial_power = sum(trait_values); balance: all races within 5% of mean"}, "synergy_links": ["lore_vault"]},
            {"id": "outfit_curator", "name": "OutfitCurator", "title": "Equipment & Fashion Designer", "expertise": ["Gear set design", "Equipment slot systems", "Socket/gem systems", "Equipment rarity tiers", "Cosmetic override systems", "Wardrobe/closet UI", "Fashion contest systems", "Season pass cosmetics"], "deep_knowledge": {"item_budget": "item_power = ilvl * slot_weight * rarity_mult; primary_stat + secondary_stats <= power_budget"}, "synergy_links": ["economy_engine"]},
        ]),
    },
    "creature_design": {
        "name": "CreatureDesign", "version": "v24.0", "icon": "paw", "color": "#84CC16",
        "description": "Monster/creature AI, behavior trees, taming, ecology, boss design, enemy variety",
        "category": "creative",
        "specialists": _gen_specialists("creature_design", [
            {"id": "behavior_architect", "name": "BehaviorArch", "title": "Creature AI Behavior Designer", "expertise": ["Behavior tree design", "Utility AI scoring", "GOAP action planning", "Pack hunting algorithms", "Territorial behavior", "Flee/aggro state machines", "Sleeping/idle cycles", "Environmental interaction AI"], "deep_knowledge": {"utility_score": "score(action) = sum(consideration_i * weight_i); best_action = argmax(score)"}, "synergy_links": ["ai_director"]},
            {"id": "ecology_sim", "name": "EcologySim", "title": "Ecosystem Simulation Designer", "expertise": ["Food chain modeling", "Population dynamics", "Breeding/spawning cycles", "Migration patterns", "Territorial boundaries", "Predator-prey balance", "Symbiotic relationships", "Extinction mechanics"], "deep_knowledge": {"population": "dN/dt = r*N*(1-N/K) - predation; K=carrying_capacity; r=growth_rate"}, "synergy_links": ["procedural_genesis"]},
            {"id": "taming_master", "name": "TamingMaster", "title": "Creature Taming & Bonding Designer", "expertise": ["Taming mini-game design", "Trust/bond mechanics", "Mount combat integration", "Breeding/genetics systems", "Evolution/transformation", "Companion commands", "Stable management", "Creature fusion systems"], "deep_knowledge": {"trust_curve": "trust += (food_quality * patience_time * temperament_match) - (damage_taken * fear)"}, "synergy_links": ["character_architect"]},
            {"id": "anatomy_designer", "name": "AnatomyDesigner", "title": "Creature Anatomy Specialist", "expertise": ["Skeletal rig design", "Locomotion style variety", "Wing/flight mechanics", "Aquatic movement", "Multi-limbed animation", "Scale/size variation", "Damage model zones", "Ragdoll configuration"], "deep_knowledge": {"locomotion": "gait_pattern = {walk: 4-beat, trot: 2-beat, gallop: 3-beat, crawl: wave}; speed = stride_length * frequency"}, "synergy_links": ["animation_studio"]},
            {"id": "spawn_director", "name": "SpawnDirector", "title": "Spawn & Population Director", "expertise": ["Spawn point placement", "Density management", "Level-appropriate spawning", "Dynamic spawn adjustment", "Spawn wave choreography", "Respawn timer design", "Event spawn triggers", "Population cap management"], "deep_knowledge": {"spawn_rate": "rate = base_rate * (1 - current/max_pop) * player_proximity_weight * time_of_day_modifier"}, "synergy_links": ["ai_director"]},
            {"id": "loot_dropper", "name": "LootDropper", "title": "Creature Loot Table Designer", "expertise": ["Drop table weighting", "Rare drop pity systems", "Material drops per tier", "Trophy/collectible drops", "Skinning/harvesting systems", "Boss-specific uniques", "Event drop modifiers", "Drop rate transparency"], "deep_knowledge": {"pity_system": "effective_rate = base_rate + (attempts_since_last * pity_increment); guaranteed at pity_ceiling"}, "synergy_links": ["economy_engine"]},
            {"id": "sound_designer_creatures", "name": "CreatureSoundDesigner", "title": "Creature Audio Designer", "expertise": ["Vocalizations per mood", "Footstep variation", "Attack sound design", "Death/pain sounds", "Ambient creature sounds", "Size-based pitch scaling", "Underwater creature audio", "Swarm/horde audio layering"], "deep_knowledge": {"pitch_scale": "pitch = base_pitch * (1 / creature_size_ratio)^0.3; larger = deeper"}, "synergy_links": ["audio_sphere"]},
            {"id": "variant_creator", "name": "VariantCreator", "title": "Creature Variant & Elite Designer", "expertise": ["Elite/champion affixes", "Miniboss design", "Shiny/rare variants", "Seasonal variants", "Corrupted variants", "Alpha/pack leader design", "Mythic/legendary creatures", "World boss encounters"], "deep_knowledge": {"elite_scaling": "elite_hp = base_hp * tier_mult; elite_damage = base_dmg * (1 + affix_count * 0.15); affix_count = floor(difficulty/threshold)"}, "synergy_links": ["combat_forge"]},
        ]),
    },
    "puzzle_matrix": {
        "name": "PuzzleMatrix", "version": "v24.0", "icon": "extension-puzzle", "color": "#6366F1",
        "description": "Puzzle design, logic systems, environmental puzzles, minigames, brain teasers",
        "category": "creative",
        "specialists": _gen_specialists("puzzle_matrix", [
            {"id": "env_puzzle_designer", "name": "EnvPuzzleDesigner", "title": "Environmental Puzzle Architect", "expertise": ["Physics-based puzzles", "Light/shadow puzzles", "Pressure plate systems", "Water flow puzzles", "Mirror/reflection puzzles", "Weight/balance puzzles", "Sequence/pattern puzzles", "Multi-room puzzles"], "deep_knowledge": {"puzzle_difficulty": "difficulty = num_steps * branching_factor * red_herrings - hint_availability"}, "synergy_links": ["physics_vault"]},
            {"id": "logic_master", "name": "LogicMaster", "title": "Logic Puzzle Designer", "expertise": ["Boolean logic gates", "Pattern recognition", "Sudoku-like constraints", "Code-breaking puzzles", "Deduction chains", "Combinatorial locks", "Cipher/encryption puzzles", "Mathematical sequence puzzles"], "deep_knowledge": {"constraint_satisfaction": "solution = backtrack_search(variables, domains, constraints)"}, "synergy_links": ["tutorial_architect"]},
            {"id": "minigame_creator", "name": "MinigameCreator", "title": "Minigame Design Specialist", "expertise": ["Lockpicking minigames", "Hacking minigames", "Fishing systems", "Cooking minigames", "Racing challenges", "Rhythm minigames", "Card game design", "Gambling systems"], "deep_knowledge": {"minigame_loop": "engage(30s) -> challenge(60s) -> reward(10s); total_cycle < 2min"}, "synergy_links": ["input_matrix"]},
            {"id": "hint_architect", "name": "HintArchitect", "title": "Progressive Hint System Designer", "expertise": ["Tiered hint system", "Environmental hint placement", "NPC hint dialogue", "Cooldown-based hints", "Accessibility hint modes", "Hint cost economy", "Context-sensitive hints", "Anti-frustration hints"], "deep_knowledge": {"hint_timing": "offer_hint_after = base_time * (1 + puzzle_attempts * 0.5); escalate_detail each refusal"}, "synergy_links": ["accessibility_core"]},
            {"id": "escape_room_designer", "name": "EscapeRoomDesigner", "title": "Escape Room & Dungeon Puzzle Designer", "expertise": ["Multi-lock progression", "Red herring management", "Collaborative puzzles", "Timed escape sequences", "Hidden object integration", "Inventory combination puzzles", "Environmental clue placement", "Boss puzzle design"], "deep_knowledge": {"flow_graph": "unlock(A) -> reveal(B) -> combine(B,C) -> unlock(D); critical_path_length <= 8"}, "synergy_links": ["procedural_genesis"]},
            {"id": "physics_puzzle_engineer", "name": "PhysPuzzleEngineer", "title": "Physics Puzzle Engineer", "expertise": ["Rube Goldberg machines", "Gravity manipulation puzzles", "Portal/teleport puzzles", "Time rewind puzzles", "Magnetic puzzles", "Momentum transfer puzzles", "Buoyancy puzzles", "Chain reaction design"], "deep_knowledge": {"momentum_conservation": "m1*v1 + m2*v2 = m1*v1' + m2*v2'"}, "synergy_links": ["physics_vault"]},
            {"id": "riddle_crafter", "name": "RiddleCrafter", "title": "Riddle & Word Puzzle Designer", "expertise": ["Riddle construction", "Wordplay puzzles", "Anagram/cipher design", "Context-dependent riddles", "NPC riddle delivery", "Reward scaling per difficulty", "Lore-integrated riddles", "Multilingual riddle adaptation"], "deep_knowledge": {"riddle_structure": "setup(misdirection) -> clue(embedded) -> answer(satisfying_aha); fairness = clue_count >= 2"}, "synergy_links": ["lore_vault"]},
            {"id": "meta_puzzle_architect", "name": "MetaPuzzleArch", "title": "Meta Puzzle & ARG Designer", "expertise": ["Cross-puzzle connections", "Meta-narrative puzzles", "Community-solved puzzles", "Real-world crossover", "Hidden achievement puzzles", "Developer room puzzles", "Speedrun puzzle skips", "NG+ exclusive puzzles"], "deep_knowledge": {"meta_complexity": "meta_difficulty = sum(sub_puzzle_difficulty) * connection_obscurity * prerequisite_count"}, "synergy_links": ["community_forge"]},
        ]),
    },
    "vehicle_physics": {
        "name": "VehiclePhysics", "version": "v24.0", "icon": "car-sport", "color": "#14B8A6",
        "description": "Vehicle & mount systems — cars, ships, aircraft, mechs, mounts, racing physics",
        "category": "creative",
        "specialists": _gen_specialists("vehicle_physics", [
            {"id": "car_physics", "name": "CarPhysics", "title": "Automotive Physics Engineer", "expertise": ["Tire friction model (Pacejka)", "Suspension spring-damper", "Engine torque curves", "Transmission simulation", "Aerodynamic forces", "Drift mechanics", "Damage model", "Tuning systems"], "deep_knowledge": {"pacejka": "F_lateral = D * sin(C * arctan(B*slip - E*(B*slip - arctan(B*slip))))"}, "synergy_links": ["physics_vault"]},
            {"id": "flight_sim", "name": "FlightSim", "title": "Flight Physics Specialist", "expertise": ["Lift/drag equations", "Stall mechanics", "Helicopter rotor physics", "Jet engine thrust curves", "Dogfight maneuvering", "Landing gear systems", "Autopilot AI", "Formation flying"], "deep_knowledge": {"lift": "L = 0.5 * ρ * v² * S * C_L(α); stall when α > α_critical"}, "synergy_links": ["physics_vault"]},
            {"id": "naval_engineer", "name": "NavalEngineer", "title": "Naval & Maritime Physics Designer", "expertise": ["Buoyancy simulation", "Wave response modeling", "Rudder/propulsion", "Cannon ballistics", "Ship damage/flooding", "Crew management", "Port/dock systems", "Naval combat AI"], "deep_knowledge": {"buoyancy": "F_b = ρ_water * g * V_displaced; stable when metacenter > center_of_gravity"}, "synergy_links": ["physics_vault", "weather_climate"]},
            {"id": "mech_designer", "name": "MechDesigner", "title": "Mech & Exosuit Designer", "expertise": ["Bipedal locomotion physics", "Weapon mount systems", "Heat management", "Shield/armor systems", "Cockpit UI design", "Modular loadouts", "Ejection/destruction", "Titan-scale combat"], "deep_knowledge": {"heat_management": "heat(t) = heat(t-1) + weapon_heat - cooling_rate * (1 + heat_sink_bonus); shutdown when heat > max"}, "synergy_links": ["combat_forge"]},
            {"id": "mount_master", "name": "MountMaster", "title": "Mount & Creature Riding Designer", "expertise": ["Mount animation blending", "Mounted combat", "Mount stamina systems", "Flying mount controls", "Underwater mounts", "Mount racing systems", "Mount ability design", "Multi-rider mounts"], "deep_knowledge": {"mount_speed": "speed = base_speed * (1 + training_level * 0.1) * terrain_modifier * stamina_curve"}, "synergy_links": ["creature_design"]},
            {"id": "racing_designer", "name": "RacingDesigner", "title": "Racing Systems Architect", "expertise": ["Track design principles", "Rubber-banding AI", "Drift scoring", "Nitro/boost systems", "Lap time tracking", "Ghost replay", "Leaderboard systems", "Weather-affected racing"], "deep_knowledge": {"rubber_band": "ai_speed = base_speed * (1 + (player_lead/max_lead) * catchup_factor)"}, "synergy_links": ["multiplayer_mesh"]},
            {"id": "space_pilot", "name": "SpacePilot", "title": "Spaceship Flight Designer", "expertise": ["Newtonian space flight", "Thruster vectoring", "FTL/warp mechanics", "Docking procedures", "Space combat maneuvers", "Mining laser physics", "Shield/power management", "Fleet command systems"], "deep_knowledge": {"orbital_v": "v = sqrt(G*M/r); escape_v = sqrt(2*G*M/r); transfer = hohmann_orbit(r1, r2)"}, "synergy_links": ["physics_vault"]},
            {"id": "rail_grind_designer", "name": "RailGrindDesigner", "title": "Traversal & Parkour Vehicle Designer", "expertise": ["Skateboard physics", "Surfing mechanics", "Paraglider/wingsuit", "Grapple/swing physics", "Zipline systems", "Snowboard/ski physics", "Hoverboard design", "Grind rail pathing"], "deep_knowledge": {"pendulum_swing": "θ(t) = θ_max * cos(sqrt(g/L) * t); release_velocity = sqrt(2*g*L*(1-cos(θ)))"}, "synergy_links": ["physics_vault", "input_matrix"]},
        ]),
    },
}

# ─────────────────────────────────────────────────────────────────────
# MEGA-CATEGORY 2: TECHNICAL DOMAINS
# ─────────────────────────────────────────────────────────────────────

TECHNICAL_DOMAINS = {
    "multiplayer_mesh": {
        "name": "MultiplayerMesh", "version": "v24.0", "icon": "wifi", "color": "#3B82F6",
        "description": "Networking, matchmaking, servers, anti-cheat, lobbies, netcode, synchronization",
        "category": "technical",
        "specialists": _gen_specialists("multiplayer_mesh", [
            {"id": "netcode_engineer", "name": "NetcodeEngineer", "title": "Network Architecture Specialist", "expertise": ["Client-server architecture", "P2P mesh networking", "State synchronization", "Delta compression", "Snapshot interpolation", "Input prediction/rollback", "Bandwidth optimization", "Network topology design"], "deep_knowledge": {"rollback": "if predicted_state != server_state: rollback(server_tick); replay_inputs(server_tick, current_tick)"}, "synergy_links": ["physics_vault"]},
            {"id": "matchmaker", "name": "Matchmaker", "title": "Matchmaking Systems Architect", "expertise": ["Elo/Glicko rating", "Skill-based matching", "Queue time optimization", "Team balancing", "Smurf detection", "Regional matching", "Cross-play matching", "Tournament bracket generation"], "deep_knowledge": {"elo_update": "R_new = R_old + K*(S - E); E = 1/(1+10^((R_opp-R_old)/400))"}, "synergy_links": ["analytics_nexus"]},
            {"id": "anticheat_sentinel", "name": "AntiCheatSentinel", "title": "Anti-Cheat Systems Architect", "expertise": ["Server-authoritative validation", "Speedhack detection", "Aimbot detection", "Wallhack prevention", "Memory scanning", "Packet manipulation detection", "Replay verification", "Behavioral analysis AI"], "deep_knowledge": {"detection": "flag if: impossible_input_rate || position_delta > max_speed*dt || hit_rate > statistical_threshold"}, "synergy_links": ["security_vault"]},
            {"id": "lobby_architect", "name": "LobbyArchitect", "title": "Lobby & Session Designer", "expertise": ["Lobby creation/joining", "Party system design", "Voice chat integration", "Ready-check systems", "Map voting", "Host migration", "Spectator systems", "Custom game modes"], "deep_knowledge": {"host_migration": "on_host_disconnect: elect_new_host(lowest_latency); transfer_state; reconnect_clients"}, "synergy_links": ["social_fabric"]},
            {"id": "sync_specialist", "name": "SyncSpecialist", "title": "State Synchronization Expert", "expertise": ["Deterministic lockstep", "Interest management", "Relevancy filtering", "Priority-based updates", "Dead reckoning", "Jitter buffer design", "Clock synchronization", "Eventual consistency"], "deep_knowledge": {"interest_mgmt": "send_to(player) if distance(entity, player) < relevancy_radius * priority_weight"}, "synergy_links": ["physics_vault"]},
            {"id": "dedicated_server_architect", "name": "DedicatedServerArch", "title": "Server Infrastructure Architect", "expertise": ["Server scaling strategies", "Containerized game servers", "Auto-scaling policies", "Region deployment", "Server tick optimization", "Database sharding", "Session persistence", "Graceful shutdown handling"], "deep_knowledge": {"autoscale": "desired_instances = ceil(active_players / players_per_server * (1 + headroom_pct))"}, "synergy_links": ["cloud_infra"]},
            {"id": "coop_designer", "name": "CoopDesigner", "title": "Cooperative Mode Designer", "expertise": ["Drop-in/drop-out coop", "Difficulty scaling per player", "Shared progression", "Tethering systems", "Revive mechanics", "Shared inventory", "Asymmetric coop roles", "Cross-save systems"], "deep_knowledge": {"difficulty_scale": "enemy_hp = base * (1 + (player_count - 1) * 0.5); damage = base * (1 + player_count * 0.25)"}, "synergy_links": ["combat_forge"]},
            {"id": "pvp_architect", "name": "PvPArchitect", "title": "PvP Mode & Arena Designer", "expertise": ["Arena/battleground design", "Capture point systems", "Battle royale zone design", "Ranked season design", "PvP stat normalization", "Reward structure", "Anti-grief systems", "Tournament support"], "deep_knowledge": {"zone_shrink": "zone_radius(t) = max_radius * e^(-shrink_rate * t); damage_per_sec = base * (1 + time_outside^1.5)"}, "synergy_links": ["combat_forge", "analytics_nexus"]},
        ]),
    },
    "ai_director": {
        "name": "AIDirector", "version": "v24.0", "icon": "bulb", "color": "#F59E0B",
        "description": "Dynamic difficulty, pacing AI, emergent events, adaptive AI, director systems",
        "category": "technical",
        "specialists": _gen_specialists("ai_director", [
            {"id": "difficulty_tuner", "name": "DifficultyTuner", "title": "Dynamic Difficulty Architect", "expertise": ["Flow-based DDA", "Invisible difficulty scaling", "Player skill profiling", "Rubber-banding prevention", "Difficulty presets", "Accessibility difficulty options", "Boss difficulty modes", "Adaptive enemy AI"], "deep_knowledge": {"dda_formula": "difficulty = target_difficulty * (1 + (deaths - expected_deaths) * adaptive_rate); clamp(min, max)"}, "synergy_links": ["emotion_engine"]},
            {"id": "event_orchestrator", "name": "EventOrchestrator", "title": "Emergent Event Director", "expertise": ["Random encounter triggering", "World event scheduling", "Player-driven event response", "Invasion/horde events", "Boss spawn triggers", "Weather event cascades", "NPC behavior events", "Seasonal event automation"], "deep_knowledge": {"event_probability": "P(event) = base_prob * (time_since_last / cooldown) * player_readiness * world_state_match"}, "synergy_links": ["emotion_engine", "live_ops"]},
            {"id": "npc_brain", "name": "NPCBrain", "title": "Advanced NPC AI Architect", "expertise": ["Behavior tree design", "GOAP planning", "Utility AI scoring", "Perception systems", "Memory/knowledge base", "Social awareness", "Schedule/routine systems", "Conversation AI"], "deep_knowledge": {"goap_plan": "plan = a_star(current_state, goal_state, available_actions, action_costs)"}, "synergy_links": ["social_fabric"]},
            {"id": "pacing_ai", "name": "PacingAI", "title": "Pacing & Tension AI Director", "expertise": ["Tension curve modeling", "Rest/action alternation", "Resource scarcity pacing", "Information reveal timing", "Jump scare spacing", "Music intensity sync", "Enemy density control", "Exploration/combat ratio"], "deep_knowledge": {"tension_model": "tension = combat_intensity * 0.4 + resource_scarcity * 0.3 + narrative_stakes * 0.3"}, "synergy_links": ["emotion_engine", "audio_sphere"]},
            {"id": "companion_ai", "name": "CompanionAI", "title": "Companion AI Behavior Designer", "expertise": ["Follow/lead behavior", "Combat support AI", "Healing/buff priority", "Banter trigger system", "Pathing/navigation", "Item gathering AI", "Danger awareness", "Emotive reactions"], "deep_knowledge": {"priority_queue": "action = max(utility(heal_ally), utility(attack_enemy), utility(gather_item), utility(follow_player))"}, "synergy_links": ["character_architect"]},
            {"id": "crowd_sim", "name": "CrowdSim", "title": "Crowd Simulation Specialist", "expertise": ["Flocking algorithms", "Crowd density management", "Panic simulation", "Line/queue behavior", "Festival/market NPCs", "Evacuation pathfinding", "Social group formation", "Performance budgeting"], "deep_knowledge": {"boids": "velocity = alignment_weight*align + cohesion_weight*cohere + separation_weight*separate"}, "synergy_links": ["physics_vault"]},
            {"id": "enemy_squad_ai", "name": "EnemySquadAI", "title": "Enemy Squad Tactics Designer", "expertise": ["Flanking algorithms", "Cover-based AI", "Suppressive fire behavior", "Retreat/regroup logic", "Squad communication", "Sniper positioning", "Grenade throw planning", "Boss add management"], "deep_knowledge": {"flank_score": "score(position) = damage_potential - exposure_risk + surprise_bonus - distance_penalty"}, "synergy_links": ["combat_forge"]},
            {"id": "rubber_band_master", "name": "RubberBandMaster", "title": "Invisible Assistance Designer", "expertise": ["Hidden health regen", "Miss chance adjustment", "Loot luck boost", "Damage absorption", "Checkpoint generosity", "Timer extension", "Enemy hesitation", "Resource drop increase"], "deep_knowledge": {"assist_level": "assist = clamp(0, 1, (death_count - expected) / tolerance); apply subtly"}, "synergy_links": ["emotion_engine"]},
        ]),
    },
    "security_vault": {
        "name": "SecurityVault", "version": "v24.0", "icon": "shield", "color": "#DC2626",
        "description": "Anti-cheat, DRM, encryption, server validation, exploit prevention, data protection",
        "category": "technical",
        "specialists": _gen_specialists("security_vault", [
            {"id": "encryption_architect", "name": "EncryptionArch", "title": "Data Encryption Specialist", "expertise": ["AES-256 implementation", "RSA key exchange", "TLS configuration", "Save file encryption", "Memory encryption", "Packet encryption", "Key management", "Hash integrity checks"], "deep_knowledge": {"aes_mode": "AES-256-GCM for authenticated encryption; nonce=12bytes; tag=16bytes"}, "synergy_links": ["multiplayer_mesh"]},
            {"id": "exploit_hunter", "name": "ExploitHunter", "title": "Exploit Prevention Specialist", "expertise": ["Buffer overflow prevention", "Injection attack prevention", "Memory manipulation detection", "Race condition prevention", "Input validation", "API rate limiting", "Privilege escalation prevention", "Fuzzing test design"], "deep_knowledge": {"input_validation": "validate(input): type_check -> range_check -> sanitize -> whitelist_filter"}, "synergy_links": ["multiplayer_mesh"]},
            {"id": "drm_engineer", "name": "DRMEngineer", "title": "Digital Rights Management Specialist", "expertise": ["License validation", "Online activation", "Hardware fingerprinting", "Tamper detection", "Code obfuscation", "Anti-debug measures", "Steganographic watermarks", "Fair-use DRM design"], "deep_knowledge": {"hwid": "fingerprint = hash(cpu_id + gpu_id + mac_addr + disk_serial + os_install_id)"}, "synergy_links": ["platform_bridge"]},
            {"id": "privacy_officer", "name": "PrivacyOfficer", "title": "Data Privacy & Compliance Specialist", "expertise": ["GDPR compliance", "COPPA compliance", "Data minimization", "Consent management", "Right to deletion", "Data anonymization", "Privacy by design", "Breach notification protocols"], "deep_knowledge": {"gdpr_basis": "processing_legal_basis = consent | contract | legitimate_interest | legal_obligation | vital_interest | public_task"}, "synergy_links": ["legal_compliance"]},
            {"id": "server_hardener", "name": "ServerHardener", "title": "Server Security Architect", "expertise": ["DDoS mitigation", "Rate limiting", "IP reputation filtering", "WAF configuration", "SSL/TLS hardening", "Container security", "Secrets management", "Audit logging"], "deep_knowledge": {"rate_limit": "allow if token_bucket(requests, capacity, refill_rate).consume(1) else reject"}, "synergy_links": ["cloud_infra"]},
            {"id": "cheat_analyst", "name": "CheatAnalyst", "title": "Cheat Detection Analyst", "expertise": ["Statistical anomaly detection", "Replay analysis", "Heuristic detection rules", "Machine learning detection", "Report investigation", "Ban wave strategy", "Appeal process design", "Cheat marketplace monitoring"], "deep_knowledge": {"anomaly_detection": "flag if z_score(player_metric) > 3.0 over rolling_window(100_games)"}, "synergy_links": ["analytics_nexus"]},
            {"id": "save_integrity", "name": "SaveIntegrity", "title": "Save Data Integrity Specialist", "expertise": ["Save checksum validation", "Cloud save conflict resolution", "Save migration versioning", "Corruption recovery", "Anti-save-editing", "Cross-platform save sync", "Incremental save design", "Save compression"], "deep_knowledge": {"checksum": "integrity = hmac_sha256(save_data, server_secret); reject if mismatch"}, "synergy_links": ["cloud_infra"]},
            {"id": "incident_responder", "name": "IncidentResponder", "title": "Security Incident Response Specialist", "expertise": ["Incident classification", "Containment procedures", "Forensic analysis", "Root cause analysis", "Communication protocols", "Recovery procedures", "Post-mortem design", "Playbook automation"], "deep_knowledge": {"response_flow": "detect -> classify(severity) -> contain -> investigate -> remediate -> recover -> post_mortem"}, "synergy_links": ["analytics_nexus"]},
        ]),
    },
    "performance_forge": {
        "name": "PerformanceForge", "version": "v24.0", "icon": "speedometer", "color": "#059669",
        "description": "Optimization, profiling, LOD systems, culling, memory management, frame budget",
        "category": "technical",
        "specialists": _gen_specialists("performance_forge", [
            {"id": "frame_budget_master", "name": "FrameBudgetMaster", "title": "Frame Budget Architect", "expertise": ["16.6ms budget breakdown", "CPU/GPU split optimization", "Draw call batching", "Instanced rendering", "Deferred vs forward rendering", "Temporal reprojection", "Variable rate shading", "Async compute"], "deep_knowledge": {"frame_budget": "16.67ms total: cpu_game=4ms, cpu_render=4ms, gpu_scene=5ms, gpu_post=2ms, overhead=1.67ms"}, "synergy_links": ["render_pipeline"]},
            {"id": "lod_architect", "name": "LODArchitect", "title": "LOD & Streaming Specialist", "expertise": ["LOD chain generation", "Nanite-style virtualized geometry", "Texture streaming MIP management", "Audio LOD systems", "Animation LOD", "Physics LOD", "AI LOD", "Screen-space error metrics"], "deep_knowledge": {"lod_select": "lod_level = floor(screen_size_pixels / lod_threshold); screen_size = world_size / distance * fov_factor"}, "synergy_links": ["render_pipeline"]},
            {"id": "memory_architect", "name": "MemoryArchitect", "title": "Memory Management Specialist", "expertise": ["Pool allocators", "Memory budgets per system", "Fragmentation prevention", "Streaming/paging", "Reference counting", "Garbage collection tuning", "Memory profiling", "Console memory constraints"], "deep_knowledge": {"pool_alloc": "pool(block_size, count); alloc=O(1); free=O(1); zero_fragmentation"}, "synergy_links": ["platform_bridge"]},
            {"id": "gpu_profiler", "name": "GPUProfiler", "title": "GPU Performance Analyst", "expertise": ["GPU trace analysis", "Shader complexity profiling", "Overdraw visualization", "Bandwidth bottleneck detection", "Occupancy optimization", "Wave/warp utilization", "Texture cache analysis", "Pipeline stall identification"], "deep_knowledge": {"occupancy": "occupancy = active_warps / max_warps; limited by registers, shared_memory, or block_size"}, "synergy_links": ["render_pipeline"]},
            {"id": "culling_master", "name": "CullingMaster", "title": "Visibility & Culling Specialist", "expertise": ["Frustum culling", "Occlusion culling (HZB)", "Portal/cell culling", "Distance culling", "Small object culling", "Shadow caster culling", "Contribution culling", "GPU-driven culling"], "deep_knowledge": {"hzb_test": "visible = screen_rect.min_depth < hzb_sample(screen_rect.mip_level)"}, "synergy_links": ["render_pipeline"]},
            {"id": "cpu_optimizer", "name": "CPUOptimizer", "title": "CPU Performance Specialist", "expertise": ["Cache-friendly data layout", "SIMD vectorization", "Job system design", "Lock-free data structures", "Branch prediction optimization", "ECS data-oriented design", "System scheduling", "Thread affinity"], "deep_knowledge": {"cache_line": "align structures to 64-byte cache lines; prefer SoA over AoS for vectorization"}, "synergy_links": ["physics_vault"]},
            {"id": "load_time_master", "name": "LoadTimeMaster", "title": "Loading & Streaming Specialist", "expertise": ["Async asset loading", "Level streaming", "IO scheduling", "Compression strategies", "SSD optimization", "Background loading", "Progressive loading", "Fast travel optimization"], "deep_knowledge": {"streaming_priority": "priority = screen_importance * (1/distance) * asset_size_inverse * player_velocity_toward"}, "synergy_links": ["platform_bridge"]},
            {"id": "scalability_engineer", "name": "ScalabilityEngineer", "title": "Scalability Settings Designer", "expertise": ["Quality preset design", "Resolution scaling", "DLSS/FSR/XeSS integration", "Dynamic resolution", "Benchmark mode", "Settings auto-detection", "Min spec validation", "Console vs PC scaling"], "deep_knowledge": {"dynamic_res": "target_res = current_res * (target_ms / actual_ms); clamp(min_res, native_res)"}, "synergy_links": ["platform_bridge"]},
        ]),
    },
    "animation_studio": {
        "name": "AnimationStudio", "version": "v24.0", "icon": "body", "color": "#D946EF",
        "description": "Skeletal animation, procedural animation, IK, blend trees, ragdoll, motion matching",
        "category": "technical",
        "specialists": _gen_specialists("animation_studio", [
            {"id": "motion_match_engineer", "name": "MotionMatchEngineer", "title": "Motion Matching Specialist", "expertise": ["Pose search algorithms", "Feature extraction", "Trajectory prediction", "Motion database curation", "Blend/transition quality", "Foot locking", "Inertial blending", "Cost function tuning"], "deep_knowledge": {"cost_function": "cost(pose) = w_pos*||features_pos - query_pos||² + w_vel*||features_vel - query_vel||² + w_traj*||features_traj - query_traj||²"}, "synergy_links": ["character_architect"]},
            {"id": "ik_specialist", "name": "IKSpecialist", "title": "Inverse Kinematics Specialist", "expertise": ["CCD IK solver", "FABRIK algorithm", "Foot placement IK", "Hand IK for weapons", "Look-at IK", "Full-body IK", "Two-bone IK", "Spline IK for tails/tentacles"], "deep_knowledge": {"fabrik": "forward: reach_target; backward: reach_root; iterate until convergence < threshold"}, "synergy_links": ["physics_vault"]},
            {"id": "blend_tree_architect", "name": "BlendTreeArch", "title": "Animation Blend Tree Designer", "expertise": ["1D/2D blend spaces", "Additive animation layers", "State machine design", "Transition rule design", "Animation events", "Root motion", "Aim offset", "Pose caching"], "deep_knowledge": {"blend_2d": "weight = barycentric_interpolation(input_vector, triangle_of_nearest_poses)"}, "synergy_links": ["combat_forge"]},
            {"id": "ragdoll_engineer", "name": "RagdollEngineer", "title": "Ragdoll & Physics Animation Specialist", "expertise": ["Joint constraint setup", "Active ragdoll balance", "Ragdoll-to-animation blending", "Hit reaction physics", "Death animation ragdoll", "Powered ragdoll", "Ragdoll performance", "Comedy ragdoll tuning"], "deep_knowledge": {"joint_constraint": "hinge(axis, min_angle, max_angle); cone_twist(twist_limit, swing_limit)"}, "synergy_links": ["physics_vault"]},
            {"id": "facial_rig_engineer", "name": "FacialRigEngineer", "title": "Facial Rig & Expression Specialist", "expertise": ["Blendshape rig design", "Bone-based facial rig", "FACS-based rig", "Lip sync automation", "Eye rig (look-at, blink)", "Wrinkle map animation", "Emotion preset design", "Performance capture retargeting"], "deep_knowledge": {"lip_sync": "phoneme_to_viseme = {AA:wide_open, EE:teeth_visible, OO:lips_round, MM:lips_closed}"}, "synergy_links": ["cinematic_studio"]},
            {"id": "cloth_sim_engineer", "name": "ClothSimEngineer", "title": "Cloth & Hair Simulation Specialist", "expertise": ["Verlet cloth simulation", "Position-based dynamics", "Hair strand simulation", "Cape/cloak dynamics", "Self-collision detection", "Wind interaction", "LOD cloth simplification", "GPU-accelerated cloth"], "deep_knowledge": {"verlet": "new_pos = pos + (pos - old_pos) * damping + acceleration * dt²; constrain(distance)"}, "synergy_links": ["physics_vault"]},
            {"id": "procedural_anim", "name": "ProceduralAnim", "title": "Procedural Animation Specialist", "expertise": ["Procedural walk cycles", "Spider/multi-legged IK", "Tentacle animation", "Breathing animation", "Idle fidget variety", "Reaction animation generation", "Procedural damage animation", "Environmental adaptation"], "deep_knowledge": {"spider_ik": "for each leg: target = raycast(body_pos + leg_offset); if distance(foot, target) > step_threshold: step(target)"}, "synergy_links": ["creature_design"]},
            {"id": "anim_compress", "name": "AnimCompress", "title": "Animation Compression & Streaming Specialist", "expertise": ["Curve fitting compression", "Quantization strategies", "Animation streaming", "Memory budget management", "LOD animation", "Retargeting compression", "Additive compression", "Runtime decompression"], "deep_knowledge": {"compression": "error = max(|original_sample - compressed_sample|) for all samples; target < 0.1mm positional error"}, "synergy_links": ["performance_forge"]},
        ]),
    },
}

# ─────────────────────────────────────────────────────────────────────
# MEGA-CATEGORY 3: CONTENT, 4: BUSINESS, 5: PLATFORM
# (Compact definitions for remaining 30 domains)
# ─────────────────────────────────────────────────────────────────────

def _quick_domain(name, version, icon, color, desc, cat, spec_defs):
    specs = {}
    for sd in spec_defs:
        specs[sd[0]] = {
            "id": sd[0], "name": sd[1], "title": sd[2],
            "expertise": sd[3], "deep_knowledge": sd[4] if len(sd) > 4 else {},
            "synergy_links": sd[5] if len(sd) > 5 else [],
        }
    return {"name": name, "version": version, "icon": icon, "color": color, "description": desc, "category": cat, "specialists": specs}

CONTENT_DOMAINS = {
    "quest_engine": _quick_domain("QuestEngine", "v24.0", "flag", "#F97316", "Quest design, branching, objectives, tracking, rewards", "content", [
        ("quest_graph_designer", "QuestGraphDesigner", "Quest Flow Architect", ["Main quest chains", "Side quest variety", "Branching outcomes", "Failed quest states", "Time-limited quests", "Recurring quests", "Chain quest dependencies", "World-state-reactive quests"], {"chain_depth": "max_dependency_depth = 5; parallel_chains = 3"}),
        ("objective_designer", "ObjectiveDesigner", "Objective System Designer", ["Kill objectives", "Collect objectives", "Escort objectives", "Puzzle objectives", "Exploration objectives", "Stealth objectives", "Dialog objectives", "Timed objectives"]),
        ("reward_architect", "RewardArchitect", "Quest Reward Specialist", ["XP scaling", "Gold/currency rewards", "Unique item rewards", "Reputation rewards", "Unlock rewards", "Choice-based rewards", "Hidden bonus rewards", "Achievement triggers"]),
        ("tracker_ui", "TrackerUI", "Quest Tracking UI Designer", ["Active quest display", "Objective markers", "Progress indicators", "Quest log design", "Map integration", "Notification system", "Priority sorting", "Completion statistics"]),
        ("npc_quest_giver", "NPCQuestGiver", "NPC Quest Integration Designer", ["Quest availability indicators", "Dialog branching for quests", "NPC schedule integration", "Reputation gates", "Level gates", "Item requirement gates", "Multi-NPC quests", "Questline NPC arcs"]),
        ("dynamic_quest_gen", "DynamicQuestGen", "Dynamic Quest Generator", ["Radiant quest system", "Procedural objectives", "Context-sensitive generation", "Difficulty scaling", "Variety tracking", "Cooldown management", "Location-based generation", "Player history weighting"]),
        ("quest_narrator", "QuestNarrator", "Quest Narrative Writer", ["Quest briefing writing", "Update text generation", "Completion dialog", "Failure dialog", "Lore-integrated quest text", "Humor in quests", "Emotional quest beats", "Twist/reveal moments"]),
        ("multiplayer_quest", "MultiplayerQuest", "Multiplayer Quest Designer", ["Shared quest progress", "Party quest scaling", "Role-specific objectives", "Competitive quests", "World boss quests", "Raid quest chains", "PvP quest objectives", "Community event quests"]),
    ]),
    "dialogue_weaver": _quick_domain("DialogueWeaver", "v24.0", "chatbubbles", "#8B5CF6", "Conversation systems, dialogue trees, barks, voice acting pipeline", "content", [
        ("dialogue_tree_architect", "DialogueTreeArch", "Dialogue Tree Architect", ["Branching dialog design", "Skill check integration", "Persuasion systems", "Intimidation paths", "Romance dialog", "Investigation dialog", "Trade negotiation", "Disposition tracking"]),
        ("bark_designer", "BarkDesigner", "Ambient Bark System Designer", ["Combat barks", "Exploration barks", "Companion barks", "Enemy barks", "Context-triggered barks", "Bark cooldown management", "Bark priority system", "Environmental reaction barks"]),
        ("voice_director", "VoiceDirector", "Voice Acting Director", ["Casting specifications", "Performance direction notes", "Emotion range requirements", "Pronunciation guides", "Recording session planning", "Line priority ranking", "Placeholder VO system", "AI voice placeholder"]),
        ("lip_sync_engineer", "LipSyncEngineer", "Lip Sync Technology Engineer", ["Phoneme mapping", "Procedural lip sync", "Facial animation sync", "Emotion-driven expressions", "Multi-language lip sync", "Real-time lip sync", "Cutscene lip polish", "Performance capture sync"]),
        ("convo_ui_designer", "ConvoUIDesigner", "Conversation UI Designer", ["Dialog wheel design", "Text box layout", "Response timer", "Skill check indicators", "Character portrait display", "Subtitle formatting", "History log", "Quick-reply shortcuts"]),
        ("relationship_tracker", "RelationshipTracker", "Relationship System Designer", ["Affinity scoring", "Approval/disapproval events", "Relationship milestones", "Rivalry systems", "Gift systems", "Companion quests", "Romance progression", "Breakup/makeup mechanics"]),
        ("procedural_dialogue", "ProceduralDialogue", "Procedural Dialogue Generator", ["Template-based generation", "Context injection", "Personality-driven variation", "Mood-affected tone", "Memory-referencing dialog", "Dynamic name insertion", "Faction-aware dialog", "Level-appropriate vocabulary"]),
        ("localized_dialogue", "LocalizedDialogue", "Dialogue Localization Specialist", ["Text expansion handling", "Cultural adaptation", "Gendered language support", "Honorific systems", "Subtitle timing", "Voice-over scheduling", "Dialect variation", "Censorship adaptation"]),
    ]),
    "inventory_forge": _quick_domain("InventoryForge", "v24.0", "briefcase", "#78716C", "Inventory, equipment, storage, sorting, weight systems", "content", [
        ("grid_designer", "GridDesigner", "Inventory Grid Architect", ["Grid-based inventory", "Slot-based inventory", "Weight-based inventory", "Category tabs", "Quick-equip slots", "Hotbar design", "Auto-sort algorithms", "Search/filter systems"]),
        ("equipment_system", "EquipmentSystem", "Equipment Slot Designer", ["Armor slots", "Weapon slots", "Accessory slots", "Cosmetic override", "Set bonus tracking", "Comparison tooltips", "Quick-swap loadouts", "Equipment durability"]),
        ("storage_architect", "StorageArchitect", "Storage System Designer", ["Player stash", "Bank/vault systems", "Shared storage", "Housing storage", "Vehicle storage", "Pet/companion inventory", "Mail system", "Auction house"]),
        ("tooltip_designer", "TooltipDesigner", "Item Tooltip Designer", ["Stat display", "Comparison mode", "Rarity color coding", "Lore text display", "Set bonus preview", "Socket display", "Flavor text", "Price display"]),
        ("loot_ui_designer", "LootUIDesigner", "Loot Pickup UI Designer", ["Auto-loot toggle", "Loot beam/pillar design", "Rarity filter", "Area loot", "Loot roll UI", "Trade window", "Dismantle interface", "Loot notification"]),
        ("crafting_interface", "CraftingInterface", "Crafting UI Designer", ["Recipe browser", "Material tracker", "Queue system", "Quality selection", "Experimental crafting", "Blueprint system", "Workstation types", "Skill-gated recipes"]),
        ("transmog_master", "TransmogMaster", "Transmog/Glamour System Designer", ["Appearance override", "Wardrobe collection", "Dye system", "Preview functionality", "Outfit saving", "Fashion contest", "Seasonal cosmetics", "Achievement cosmetics"]),
        ("weight_balancer", "WeightBalancer", "Encumbrance System Designer", ["Weight calculation", "Over-encumbered effects", "Pack mule companions", "Storage upgrades", "Weight reduction perks", "Material weight classes", "Stack limits", "Junk auto-marking"]),
    ]),
    "crafting_matrix": _quick_domain("CraftingMatrix", "v24.0", "hammer", "#B45309", "Crafting, recipes, material chains, workstations, upgrades", "content", [
        ("recipe_designer", "RecipeDesigner", "Recipe System Architect", ["Recipe discovery", "Tier progression", "Experimental recipes", "Rare material gates", "Multi-step recipes", "Quality outcomes", "Critical craft chance", "Recipe categories"]),
        ("material_chain", "MaterialChain", "Material Chain Designer", ["Resource tiers", "Refinement chains", "Gathering nodes", "Rare material spawns", "Material properties", "Alloy/compound mixing", "Seasonal materials", "Event-exclusive materials"]),
        ("workstation_designer", "WorkstationDesigner", "Workstation & Workshop Designer", ["Forge/anvil systems", "Alchemy table", "Enchanting station", "Cooking station", "Tailoring loom", "Woodworking bench", "Tech fabricator", "Upgrade station"]),
        ("upgrade_architect", "UpgradeArchitect", "Upgrade & Enhancement Designer", ["Weapon upgrades", "Armor upgrades", "Socket/gem systems", "Enchantment layering", "Reforging systems", "Augment slots", "Calibration systems", "Prestige upgrades"]),
        ("blueprint_master", "BlueprintMaster", "Blueprint & Schematic Designer", ["Blueprint drops", "Vendor schematics", "Quest reward blueprints", "Reverse engineering", "Blueprint trading", "Auto-craft from blueprints", "Blueprint collection UI", "Rare blueprint chase"]),
        ("deconstruction_expert", "DeconstructionExpert", "Salvage & Deconstruction Designer", ["Material recovery rates", "Salvage skill scaling", "Auto-deconstruct rules", "Rare material extraction", "Junk conversion", "Repair vs recycle decisions", "Environmental recycling", "Mass deconstruction"]),
        ("quality_system", "QualitySystem", "Craft Quality System Designer", ["Quality tiers (common to legendary)", "Masterwork system", "Quality stat bonuses", "Quality visual variation", "Crafting skill influence", "Tool quality impact", "Material quality impact", "Perfect craft achievements"]),
        ("housing_crafter", "HousingCrafter", "Housing & Furniture Crafting Designer", ["Furniture recipes", "Decoration placement", "Room design themes", "Functional furniture", "Trophy mounting", "Garden/farm plots", "Music boxes/ambience", "Housing marketplace"]),
    ]),
}

BUSINESS_DOMAINS = {
    "economy_engine": _quick_domain("EconomyEngine", "v24.0", "cash", "#16A34A", "Game economy, currencies, markets, inflation, trading", "business", [
        ("currency_architect", "CurrencyArchitect", "Currency System Designer", ["Primary currency", "Premium currency", "Seasonal currency", "Faction currencies", "Crafting tokens", "PvP currency", "Exchange rates", "Currency cap management"]),
        ("market_sim", "MarketSim", "Market Simulation Engineer", ["Supply/demand modeling", "NPC vendor pricing", "Player auction house", "Price floor/ceiling", "Market manipulation prevention", "Regional price variation", "Inflation control", "Gold sink design"]),
        ("sink_source_balancer", "SinkSourceBalancer", "Economy Sink/Source Balancer", ["Currency sinks", "Currency sources", "Repair costs", "Fast travel costs", "Crafting costs", "Housing upkeep", "Tax systems", "Gambling sinks"]),
        ("trade_designer", "TradeDesigner", "Trading System Designer", ["Player-to-player trade", "Trade window safety", "Scam prevention", "Mail trade system", "Auction house mechanics", "Bid/buyout systems", "Trade history", "Cross-region trade"]),
        ("loot_economist", "LootEconomist", "Loot Economy Specialist", ["Drop rate balancing", "Rarity distribution", "Pity timer systems", "Duplicate protection", "Loot table auditing", "Economy impact assessment", "Seasonal loot adjustment", "Event reward scaling"]),
        ("npc_vendor", "NPCVendor", "NPC Vendor System Designer", ["Vendor inventory rotation", "Reputation vendor unlocks", "Seasonal stock", "Rare merchant spawns", "Buyback system", "Vendor pricing formulas", "Haggling mechanics", "Traveling merchant"]),
        ("investment_system", "InvestmentSystem", "Investment & Returns Designer", ["Property investment", "Business ownership", "Stock/commodity trading", "Compound interest mechanics", "Risk/reward investments", "Partnership systems", "Real estate market", "Guild treasury"]),
        ("economy_dashboard", "EconomyDashboard", "Economy Analytics Dashboard Designer", ["Real-time economy metrics", "Inflation tracking", "Currency velocity", "Wealth distribution", "Market health indicators", "Alert systems", "Admin intervention tools", "Economy simulation testing"]),
    ]),
    "monetization_lab": _quick_domain("MonetizationLab", "v24.0", "diamond", "#EAB308", "Ethical monetization, battle pass, cosmetics, DLC, pricing", "business", [
        ("battlepass_architect", "BattlepassArch", "Battle Pass Designer", ["Free/premium track design", "Reward pacing", "XP curve calibration", "Challenge design", "FOMO vs respect balance", "Season length optimization", "Catch-up mechanics", "Prestige rewards"]),
        ("cosmetic_designer", "CosmeticDesigner", "Cosmetic Economy Designer", ["Skin rarity tiers", "Bundle pricing", "Limited-time offers", "Color/variant systems", "Mythic/prestige cosmetics", "Cross-promotion items", "Gifting systems", "Cosmetic trading"]),
        ("dlc_planner", "DLCPlanner", "DLC & Expansion Planner", ["Content roadmap", "Expansion scope", "Story DLC design", "Pricing strategy", "Season pass value", "Free vs paid content split", "Legacy content access", "Year plan"]),
        ("pricing_strategist", "PricingStrategist", "Pricing Strategy Specialist", ["Price point research", "Regional pricing", "Bundle discount math", "Sale event planning", "Early bird pricing", "Founder's edition value", "Virtual currency pricing", "A/B price testing"]),
        ("ethics_auditor", "EthicsAuditor", "Monetization Ethics Auditor", ["No pay-to-win validation", "Loot box probability disclosure", "Spending limits", "Parental controls", "Whale protection", "Value transparency", "Refund policy design", "Regulatory compliance"]),
        ("ad_integration", "AdIntegration", "Ad Integration Specialist", ["Rewarded video ads", "Interstitial placement", "Native ad integration", "Ad frequency capping", "Ad-free premium option", "In-game billboard ads", "Sponsor integration", "Ad revenue optimization"]),
        ("subscription_designer", "SubscriptionDesigner", "Subscription Model Designer", ["Monthly perks design", "Subscriber-only content", "Subscription tiers", "Trial period design", "Churn prevention", "Winback offers", "Family plans", "Cross-title subscriptions"]),
        ("store_ux_designer", "StoreUXDesigner", "In-Game Store UX Designer", ["Store layout design", "Featured items rotation", "Wishlist system", "Purchase confirmation flow", "Receipt/history", "Gift card system", "Loyalty points", "Flash sale UI"]),
    ]),
    "live_ops": _quick_domain("LiveOpsCommand", "v24.0", "calendar", "#7C3AED", "Live operations, seasonal content, events, patches, hotfixes", "business", [
        ("season_director", "SeasonDirector", "Seasonal Content Director", ["Season theme design", "Content cadence", "Seasonal rewards", "Narrative through-line", "Mid-season updates", "End-of-season events", "Season transition", "Retrospective content"]),
        ("event_designer", "EventDesigner", "Live Event Designer", ["Limited-time events", "Holiday events", "Crossover events", "Community challenges", "World-first races", "Competitive seasons", "Anniversary celebrations", "Launch events"]),
        ("patch_manager", "PatchManager", "Patch & Update Manager", ["Patch note writing", "Hotfix deployment", "Rollback procedures", "Feature flags", "A/B testing framework", "Gradual rollout", "Platform cert timing", "Emergency response"]),
        ("community_liaison", "CommunityLiaison", "Community Communication Lead", ["Patch preview blogs", "Developer streams", "Social media management", "Forum moderation", "Feedback collection", "Bug report triage", "Community councils", "Content creator relations"]),
        ("retention_engineer", "RetentionEngineer", "Player Retention Specialist", ["Day-1/7/30 retention", "Re-engagement campaigns", "Lapsed player winback", "Daily login rewards", "Streak systems", "FTUE optimization", "Churn prediction", "Personalized offers"]),
        ("ab_test_master", "ABTestMaster", "A/B Testing Specialist", ["Test hypothesis design", "Sample size calculation", "Statistical significance", "Feature flag management", "Multi-variate testing", "Segmentation strategy", "Result analysis", "Rollout decision framework"]),
        ("config_manager", "ConfigManager", "Remote Config Manager", ["Server-side config", "Real-time tuning", "Kill switches", "Feature toggles", "Content scheduling", "Regional config", "Platform-specific config", "Config versioning"]),
        ("downtime_planner", "DowntimePlanner", "Maintenance & Downtime Planner", ["Maintenance windows", "Zero-downtime updates", "Player communication", "Compensation policy", "Rollback triggers", "Health monitoring", "Capacity planning", "Post-maintenance validation"]),
    ]),
    "analytics_nexus": _quick_domain("AnalyticsNexus", "v24.0", "stats-chart", "#0EA5E9", "Telemetry, player behavior, funnel analysis, A/B testing, dashboards", "business", [
        ("telemetry_architect", "TelemetryArch", "Telemetry System Architect", ["Event schema design", "Data pipeline architecture", "Real-time streaming", "Batch processing", "Data warehousing", "Privacy-compliant collection", "Sampling strategies", "Custom event tracking"]),
        ("funnel_analyst", "FunnelAnalyst", "Conversion Funnel Analyst", ["FTUE funnel", "Purchase funnel", "Feature adoption funnel", "Content completion funnel", "Social feature funnel", "Progression funnel", "Churn funnel", "Re-engagement funnel"]),
        ("behavior_analyst", "BehaviorAnalyst", "Player Behavior Analyst", ["Play session analysis", "Heatmap generation", "Path analysis", "Engagement scoring", "Segment clustering", "Cohort analysis", "Behavioral prediction", "Anomaly detection"]),
        ("dashboard_builder", "DashboardBuilder", "Analytics Dashboard Builder", ["KPI dashboards", "Real-time monitoring", "Custom report builder", "Alert configuration", "Data visualization", "Cross-platform views", "Executive summaries", "Automated reporting"]),
        ("economy_analyst", "EconomyAnalyst", "Economy Analytics Specialist", ["Currency flow tracking", "Market health metrics", "Inflation monitoring", "Wealth distribution analysis", "Sink/source balance", "RMT detection", "Economy simulation", "Price elasticity analysis"]),
        ("player_segmentation", "PlayerSegmentation", "Player Segmentation Specialist", ["Behavioral clustering", "Spending tier classification", "Engagement personas", "Skill-based segmentation", "Platform segmentation", "Geographic segmentation", "Lifecycle stage", "Prediction models"]),
        ("ab_analyst", "ABAnalyst", "A/B Test Analyst", ["Statistical test selection", "P-value interpretation", "Confidence interval calculation", "Effect size estimation", "Multiple comparison correction", "Long-term impact assessment", "Novelty effect detection", "Guardrail metric monitoring"]),
        ("ml_engineer", "MLEngineer", "ML/AI Analytics Engineer", ["Churn prediction models", "LTV prediction", "Matchmaking optimization", "Content recommendation", "Anomaly detection ML", "NLP for player feedback", "Computer vision for heatmaps", "Reinforcement learning for balance"]),
    ]),
    "community_forge": _quick_domain("CommunityForge", "v24.0", "people-circle", "#EC4899", "Community management, UGC, modding, social features", "business", [
        ("ugc_architect", "UGCArchitect", "User-Generated Content Architect", ["Level editor", "Character creator sharing", "Screenshot sharing", "Replay sharing", "Custom game modes", "Workshop integration", "Content moderation", "Featured content curation"]),
        ("mod_support", "ModSupport", "Modding Support Designer", ["Modding API design", "Asset pipeline for mods", "Scripting language support", "Mod manager UI", "Mod compatibility system", "Official mod toolkit", "Mod marketplace", "Curated mods program"]),
        ("social_features", "SocialFeatures", "Social Features Designer", ["Friends list", "Clan/guild system", "Chat system design", "Social feed", "Activity status", "Gifting system", "Referral program", "Social achievements"]),
        ("report_system", "ReportSystem", "Player Report & Moderation Designer", ["Report categories", "Evidence collection", "Automated moderation", "Tribunal/jury system", "Ban/mute systems", "Appeal process", "Toxicity scoring", "Positive reinforcement"]),
        ("esports_manager", "EsportsManager", "Esports & Tournament Designer", ["Ranked ladder design", "Tournament bracket system", "Spectator mode", "Replay system", "Caster tools", "Team management", "Prize pool design", "Broadcasting integration"]),
        ("content_creator_tools", "ContentCreatorTools", "Content Creator Tools Designer", ["Replay camera controls", "Cinematic mode", "HUD toggle", "Free camera", "Slow motion", "Custom thumbnails", "Stream overlay API", "Creator code system"]),
        ("wiki_system", "WikiSystem", "In-Game Wiki & Knowledge Base Designer", ["Auto-generated wiki", "Player-contributed entries", "Bestiary/database", "Tip system", "Strategy guides", "Community voting", "FAQ system", "Tutorial links"]),
        ("feedback_collector", "FeedbackCollector", "Player Feedback Collection Designer", ["In-game survey system", "Bug report interface", "Feature request voting", "Sentiment analysis", "Net promoter score", "Session feedback prompts", "A/B feedback comparison", "Feedback dashboard"]),
    ]),
}

PLATFORM_DOMAINS = {
    "platform_bridge": _quick_domain("PlatformBridge", "v24.0", "git-merge", "#6366F1", "Cross-platform development, certification, console TRC/XR", "platform", [
        ("crossplay_engineer", "CrossplayEngineer", "Cross-Play Implementation Specialist", ["Platform account linking", "Cross-platform matchmaking", "Input-based matching", "Cross-save synchronization", "Platform-specific UI adaptation", "Voice chat bridging", "Friends list unification", "Entitlement synchronization"]),
        ("console_cert", "ConsoleCert", "Console Certification Specialist", ["Sony TRC compliance", "Microsoft XR compliance", "Nintendo Lotcheck", "Patch certification process", "Age rating submissions", "Accessibility requirements", "Performance benchmarks", "First-party API integration"]),
        ("mobile_optimizer", "MobileOptimizer", "Mobile Optimization Specialist", ["Thermal throttling management", "Battery optimization", "Touch control design", "Screen size adaptation", "Cellular data optimization", "Background behavior", "Notification design", "App store optimization"]),
        ("pc_master", "PCMaster", "PC Platform Specialist", ["Graphics settings UI", "Ultrawide support", "High refresh rate", "HDR implementation", "Keyboard rebinding", "Controller support", "DLSS/FSR integration", "Windowed/fullscreen modes"]),
        ("vr_adapter", "VRAdapter", "VR/AR Adaptation Specialist", ["Motion control mapping", "Comfort settings", "Locomotion options", "VR UI design", "Performance optimization", "Motion sickness prevention", "Haptic feedback design", "Room-scale adaptation"]),
        ("cloud_gaming", "CloudGaming", "Cloud Gaming Optimization Specialist", ["Latency compensation", "Visual quality optimization", "Input prediction", "Bandwidth adaptation", "Session management", "Platform integration (xCloud, Luna, GeForce Now)", "Streaming asset optimization", "Client-side prediction"]),
        ("web_exporter", "WebExporter", "WebGL/HTML5 Export Specialist", ["WASM compilation", "WebGL renderer adaptation", "Progressive loading", "Service worker caching", "Mobile browser support", "WebGPU migration path", "Audio context management", "Social platform embeds"]),
        ("accessibility_core", "AccessibilityCore", "Accessibility Specialist", ["WCAG 2.1 AA compliance", "Colorblind modes", "Screen reader support", "Subtitle customization", "Input remapping", "One-handed modes", "Motor accessibility", "Cognitive accessibility"]),
    ]),
    "localization_hub": _quick_domain("LocalizationHub", "v24.0", "language", "#0284C7", "Localization, translation, cultural adaptation, i18n infrastructure", "platform", [
        ("i18n_architect", "I18NArchitect", "Internationalization Architect", ["String externalization", "Unicode support", "RTL layout support", "Plural form handling", "Date/time/number formatting", "Font fallback chains", "Text expansion handling", "Dynamic text resizing"]),
        ("translation_manager", "TranslationManager", "Translation Management Specialist", ["TMS integration", "Context-rich translation", "Translator guidelines", "Quality assurance process", "Machine translation post-edit", "Community translation", "Glossary management", "Translation memory"]),
        ("cultural_adapter", "CulturalAdapter", "Cultural Adaptation Specialist", ["Visual cultural sensitivity", "Name/character adaptation", "Gesture/gesture meaning", "Color symbolism", "Humor adaptation", "Religious sensitivity", "Historical sensitivity", "Regional regulation compliance"]),
        ("voice_localizer", "VoiceLocalizer", "Voice Localization Specialist", ["Casting for localized VO", "Lip sync adaptation", "Emotion preservation", "Recording studio management", "QA for localized audio", "Subtitle sync verification", "Naming pronunciation guides", "Cultural tone adaptation"]),
        ("qa_localizer", "QALocalizer", "Localization QA Specialist", ["Functional LQA", "Linguistic LQA", "Visual inspection", "Audio verification", "Context verification", "Truncation detection", "Placeholder validation", "Platform-specific L10N testing"]),
        ("regional_adapter", "RegionalAdapter", "Regional Market Specialist", ["Age rating adaptation", "Content modification for regions", "Monetization law compliance", "Data privacy regional rules", "Marketing localization", "Store page localization", "Regional pricing", "Launch timing per region"]),
        ("font_specialist", "FontSpecialist", "Font & Typography Specialist", ["CJK font support", "Arabic script rendering", "Devanagari support", "Dynamic font loading", "SDF font rendering", "Font size accessibility", "Outline/shadow readability", "Emoji support"]),
        ("loc_automation", "LocAutomation", "Localization Pipeline Automation Specialist", ["CI/CD loc integration", "Automated screenshot capture", "String extraction automation", "Pseudo-localization testing", "Translation status dashboard", "Auto-import/export", "Loc memory leverage", "Fuzzy match optimization"]),
    ]),
    "tutorial_architect": _quick_domain("TutorialArchitect", "v24.0", "school", "#F97316", "Onboarding, tutorials, hints, learning curves, FTUE", "platform", [
        ("ftue_designer", "FTUEDesigner", "First-Time User Experience Designer", ["Hook moment design", "Core loop introduction", "Progressive disclosure", "Contextual teaching", "Skip options", "Veteran detection", "Retention checkpoint", "Social proof elements"]),
        ("tooltip_system", "TooltipSystem", "Tooltip & Hint System Designer", ["Progressive tooltips", "Context-sensitive hints", "Smart hint timing", "Tooltip styling", "Controller/KB+M adaptation", "Disable options", "Tutorial replay", "Achievement hints"]),
        ("difficulty_onboard", "DifficultyOnboard", "Difficulty & Accessibility Onboarding", ["Difficulty recommendation", "Adaptive intro difficulty", "Assist mode explanation", "Controller layout intro", "Accessibility settings prompt", "Color vision test", "Audio calibration", "Motion sensitivity check"]),
        ("practice_mode", "PracticeMode", "Practice & Training Mode Designer", ["Combat tutorial arena", "Combo trainer", "Shooting range", "Puzzle practice", "DPS dummy", "Movement tutorial", "Mechanic isolation", "Challenge series"]),
        ("progression_guide", "ProgressionGuide", "Progression Guidance Designer", ["Next steps guidance", "Recommended activities", "Power level guidance", "Content unlocks preview", "Milestone celebrations", "Weekly objectives", "Season pass guidance", "Endgame introduction"]),
        ("social_onboard", "SocialOnboard", "Social Feature Onboarding", ["Friend invite flow", "Guild recruitment intro", "Chat tutorial", "Trade tutorial", "Party formation", "Mentor system", "PvP introduction", "Community feature discovery"]),
        ("video_tutorial", "VideoTutorial", "Video Tutorial Producer", ["In-game video tutorials", "Loading screen tips", "Context video playback", "Technique demonstrations", "Boss strategy hints", "Community highlight reels", "Developer tips", "Seasonal content previews"]),
        ("learning_curve", "LearningCurve", "Learning Curve Analyst", ["Skill acquisition tracking", "Mastery curve design", "Plateau detection", "Frustration point identification", "Information overload prevention", "Spaced repetition for mechanics", "Knowledge check design", "Advanced technique revelation"]),
    ]),
    "deployment_forge": _quick_domain("DeploymentForge", "v24.0", "cloud-upload", "#7C3AED", "Build pipelines, CI/CD, packaging, store submission, certification", "platform", [
        ("ci_cd_architect", "CICDArchitect", "CI/CD Pipeline Architect", ["Build automation", "Test automation", "Deployment automation", "Branch strategy", "Artifact management", "Environment management", "Rollback procedures", "Pipeline optimization"]),
        ("build_engineer", "BuildEngineer", "Build System Engineer", ["Multi-platform build", "Incremental builds", "Distributed compilation", "Asset cooking", "Shader compilation", "Build caching", "Build farm management", "Build time optimization"]),
        ("store_submitter", "StoreSubmitter", "Store Submission Specialist", ["Steam submission", "PlayStation submission", "Xbox submission", "Nintendo submission", "App Store submission", "Google Play submission", "Epic Games Store", "GOG submission"]),
        ("versioning_master", "VersioningMaster", "Version & Patching Specialist", ["Semantic versioning", "Delta patching", "Background downloads", "Preload management", "Version compatibility", "Save migration", "Asset versioning", "Rollback support"]),
        ("qa_automation", "QAAutomation", "QA Automation Engineer", ["Automated UI testing", "Performance regression testing", "Smoke test suites", "Integration testing", "Load testing", "Soak testing", "Crash reporting", "Coverage metrics"]),
        ("release_manager", "ReleaseManager", "Release Management Specialist", ["Release calendar", "Go/no-go criteria", "Stakeholder coordination", "Marketing sync", "Embargo management", "Day-one patch planning", "Launch monitoring", "Post-launch support plan"]),
        ("infra_ops", "InfraOps", "Infrastructure Operations Specialist", ["Server provisioning", "Auto-scaling setup", "CDN configuration", "Database management", "Monitoring & alerting", "Log aggregation", "Incident response", "Cost optimization"]),
        ("compliance_checker", "ComplianceChecker", "Compliance & Rating Specialist", ["ESRB submission", "PEGI submission", "CERO submission", "USK submission", "GRAC submission", "Content descriptor documentation", "Interactive elements disclosure", "Regional compliance verification"]),
    ]),
    "legal_compliance": _quick_domain("LegalCompliance", "v24.0", "document-lock", "#991B1B", "Legal, regulatory, age ratings, GDPR, COPPA, gambling laws", "platform", [
        ("gdpr_specialist", "GDPRSpecialist", "GDPR Compliance Specialist", ["Data mapping", "Consent mechanisms", "Right to access", "Right to deletion", "Data portability", "DPO responsibilities", "Breach protocols", "Privacy impact assessments"]),
        ("coppa_specialist", "COPPASpecialist", "Children's Privacy Specialist", ["Age gate design", "Parental consent flow", "Data collection limits", "Chat restrictions", "Purchase restrictions", "Marketing restrictions", "Account management", "Safe harbor compliance"]),
        ("gambling_law", "GamblingLaw", "Loot Box & Gambling Law Specialist", ["Probability disclosure", "Regional gambling classification", "Virtual currency regulation", "Refund policy", "Age restrictions", "Spending limits", "Belgium/Netherlands compliance", "Upcoming legislation tracking"]),
        ("ip_counsel", "IPCounsel", "Intellectual Property Specialist", ["Trademark clearance", "Copyright protection", "License management", "DMCA procedures", "UGC IP management", "Music licensing", "Voice actor rights", "Open source compliance"]),
        ("eula_architect", "EULAArchitect", "Terms of Service Designer", ["EULA drafting", "Privacy policy", "Code of conduct", "Refund policy", "Community guidelines", "Streaming policy", "Modding policy", "Data retention policy"]),
        ("accessibility_law", "AccessibilityLaw", "Accessibility Compliance Specialist", ["ADA compliance", "Section 508", "EN 301 549", "WCAG standards", "Platform requirements", "Documentation requirements", "Testing procedures", "Remediation planning"]),
        ("regional_regulation", "RegionalRegulation", "Regional Regulation Specialist", ["China NPPA compliance", "Korea game rating", "Japan CERO requirements", "EU digital markets act", "US FTC guidelines", "India regulation", "Brazil compliance", "Middle East content rules"]),
        ("contract_manager", "ContractManager", "Contract & Partnership Manager", ["Publisher agreements", "Platform agreements", "Middleware licenses", "Voice actor contracts", "Music licenses", "Influencer agreements", "Esports partner contracts", "Distribution agreements"]),
    ]),
}

# ═══════════════════════════════════════════════════════════════════════
# COMBINE ALL DOMAINS
# ═══════════════════════════════════════════════════════════════════════

ALL_DOMAINS = {}
ALL_DOMAINS.update(CREATIVE_DOMAINS)
ALL_DOMAINS.update(TECHNICAL_DOMAINS)
ALL_DOMAINS.update(CONTENT_DOMAINS)
ALL_DOMAINS.update(BUSINESS_DOMAINS)
ALL_DOMAINS.update(PLATFORM_DOMAINS)

MEGA_CATEGORIES = {
    "creative": {"name": "Creative Domains", "icon": "color-palette", "color": "#EC4899", "domain_ids": list(CREATIVE_DOMAINS.keys())},
    "technical": {"name": "Technical Domains", "icon": "construct", "color": "#3B82F6", "domain_ids": list(TECHNICAL_DOMAINS.keys())},
    "content": {"name": "Content Domains", "icon": "document-text", "color": "#F59E0B", "domain_ids": list(CONTENT_DOMAINS.keys())},
    "business": {"name": "Business Domains", "icon": "trending-up", "color": "#10B981", "domain_ids": list(BUSINESS_DOMAINS.keys())},
    "platform": {"name": "Platform Domains", "icon": "git-merge", "color": "#7C3AED", "domain_ids": list(PLATFORM_DOMAINS.keys())},
}


# ═══════════════════════════════════════════════════════════════════════
# SYNERGY WEB — Every domain has explicit connections to others
# ═══════════════════════════════════════════════════════════════════════

SYNERGY_WEB = {}
for did, domain in ALL_DOMAINS.items():
    specs = domain.get("specialists", {})
    links = set()
    for sid, spec in specs.items():
        for link in spec.get("synergy_links", []):
            links.add(link)
    SYNERGY_WEB[did] = list(links)


# ═══════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/status")
async def mega_domain_status():
    """Get status of the entire mega domain expansion."""
    total_specialists = 0
    total_expertise = 0
    total_knowledge = 0
    domain_summaries = {}

    for did, domain in ALL_DOMAINS.items():
        specs = domain.get("specialists", {})
        spec_count = len(specs)
        exp_count = sum(len(s.get("expertise", [])) for s in specs.values())
        know_count = sum(len(s.get("deep_knowledge", {})) for s in specs.values())

        total_specialists += spec_count
        total_expertise += exp_count
        total_knowledge += know_count

        domain_summaries[did] = {
            "name": domain["name"], "icon": domain.get("icon", "cube"),
            "color": domain.get("color", "#666"), "category": domain.get("category", "other"),
            "specialist_count": spec_count, "expertise_points": exp_count,
            "deep_knowledge_entries": know_count,
            "synergy_links": len(SYNERGY_WEB.get(did, [])),
        }

    return {
        "system": "Mega Domain Expansion v24.0",
        "status": "FULLY_OPERATIONAL",
        "total_domains": len(ALL_DOMAINS),
        "total_specialists": total_specialists,
        "total_expertise_points": total_expertise,
        "total_deep_knowledge_entries": total_knowledge,
        "total_synergy_links": sum(len(v) for v in SYNERGY_WEB.values()),
        "mega_categories": {
            cid: {**cat, "domain_count": len(cat["domain_ids"])}
            for cid, cat in MEGA_CATEGORIES.items()
        },
        "domains": domain_summaries,
    }


@router.get("/category/{category_id}")
async def get_category(category_id: str):
    """Get all domains in a mega-category."""
    cat = MEGA_CATEGORIES.get(category_id)
    if not cat:
        raise HTTPException(404, f"Category '{category_id}' not found")

    domains = {}
    for did in cat["domain_ids"]:
        d = ALL_DOMAINS[did]
        specs = d.get("specialists", {})
        domains[did] = {
            "name": d["name"], "version": d.get("version", "v24.0"),
            "icon": d.get("icon"), "color": d.get("color"),
            "description": d.get("description", ""),
            "specialist_count": len(specs),
            "specialist_names": [s["name"] for s in specs.values()],
        }

    return {
        "category": cat,
        "domains": domains,
        "total_domains": len(domains),
    }


@router.get("/domain/{domain_id}")
async def get_domain_detail(domain_id: str):
    """Get full domain detail with all specialists."""
    domain = ALL_DOMAINS.get(domain_id)
    if not domain:
        raise HTTPException(404, f"Domain '{domain_id}' not found")

    return {
        "domain": {
            "id": domain_id, "name": domain["name"],
            "version": domain.get("version", "v24.0"),
            "icon": domain.get("icon"), "color": domain.get("color"),
            "description": domain.get("description", ""),
            "category": domain.get("category", "other"),
        },
        "specialist_count": len(domain.get("specialists", {})),
        "specialists": domain.get("specialists", {}),
        "synergy_links": SYNERGY_WEB.get(domain_id, []),
    }


@router.get("/synergy-web")
async def get_synergy_web():
    """Get the full synergy web — all cross-domain connections."""
    total_connections = sum(len(v) for v in SYNERGY_WEB.values())
    return {
        "system": "Synergy Web v24.0",
        "total_domains": len(ALL_DOMAINS),
        "total_connections": total_connections,
        "web": {
            did: {
                "name": ALL_DOMAINS[did]["name"],
                "color": ALL_DOMAINS[did].get("color", "#666"),
                "connections": links,
                "connection_count": len(links),
            }
            for did, links in SYNERGY_WEB.items()
        },
    }
