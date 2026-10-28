"""
Galaxy Studio — Phase & Mutation Generators (extracted Jun 2026)
─────────────────────────────────────────────────────────────────────────────
The 56 per-phase content generators (_phase_*) plus the mutation-permutation
engine, split out of routes/galaxy_studio.py to shrink that monolith.

Names still owned by the parent module (a handful of data-tables + 3 helper
generators) are reached through the `_gs` proxy — `import routes.galaxy_studio
as _gs` returns the partially-initialised parent at import time but every
attribute access happens later, at build time, when the parent is fully loaded.
The parent re-imports every _phase_* / _gen_mutation_* name below so its
globals()-based dispatch (_call_phase_func) and public surface stay intact.
"""
import routes.galaxy_studio as _gs
from routes.galaxy_studio_codegen import (
    _expand_massive, _gen_ai_behavior_tree, _gen_animation_hook, _gen_audio_hook,
    _gen_babel_config, _gen_camera_hook, _gen_color_utils, _gen_combat_store,
    _gen_combat_types, _gen_component_aaa, _gen_constants, _gen_data_file,
    _gen_design_directives, _gen_design_doc, _gen_entity_store, _gen_eslint_config,
    _gen_formatters, _gen_game_loop_hook, _gen_helpers, _gen_input_hook,
    _gen_inventory_hook, _gen_inventory_store, _gen_inventory_types, _gen_layout_code,
    _gen_logic_aaa, _gen_math_utils, _gen_metro_config, _gen_network_hook,
    _gen_network_store, _gen_network_types, _gen_physics_hook, _gen_procgen_code,
    _gen_screen_aaa, _gen_shader_code, _gen_test_file, _gen_types,
    _gen_ui_store, _gen_ui_types, _gen_validators, _gen_world_store,
    _gen_world_types,
)
from routes.jeeves_master_build import (
    _gen_app_json, _gen_eas_json, _gen_game_state, _gen_package_json, _gen_tsconfig,
)


def _phase_vision(build, t, g, gi, v, sy, la, ins, complexity, age_target):
    files = {}
    files["DESIGN_DOCUMENT.md"] = _gen_design_doc(t, g, gi, v, sy, la, ins, complexity, age_target)
    files["app.json"] = _gen_app_json(t, g)
    files["package.json"] = _gen_package_json(t)
    files["eas.json"] = _gen_eas_json()
    files["tsconfig.json"] = _gen_tsconfig()
    files["babel.config.js"] = _gen_babel_config(t)
    files[".eslintrc.json"] = _gen_eslint_config(t)
    files["metro.config.js"] = _gen_metro_config(t)
    files["store/gameState.ts"] = _gen_game_state(g, t)
    files["store/designDirectives.ts"] = _gen_design_directives(t, g, v, sy, la, ins)
    # ═══ EXPANDED: Foundational systems to reach 200+ pages ═══
    vision_systems = [
        ("coreConfig", "Core configuration system with environment detection, feature flags, A/B testing, dynamic config loading"),
        ("bootloader", "Application bootloader with dependency graph resolution, init sequencing, health probing, splash management"),
        ("errorBoundary", "Global error boundary with crash reporting, recovery strategies, graceful degradation, user messaging"),
        ("telemetryCore", "Telemetry foundation with event schema, batching, offline queue, consent management, anonymization"),
        ("featureFlagEngine", "Feature flag engine with remote config, targeting rules, percentage rollouts, kill switches"),
    ]
    for name, desc in vision_systems:
        files[f"core/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    # ═══ NARRATIVE VAULT INJECTION ═══
    # Pull cross-vault context and write narrative design docs the swarm can
    # consume in subsequent phases. Makes every game's story measurably more
    # unique by anchoring it to ~200 specialized domain vaults + 6 core
    # narrative libraries + the selected Era-by-Age year.
    try:
        narrative_files = _gs._gen_narrative_vault_docs(build, t, g, gi)
        if isinstance(narrative_files, dict):
            files.update(narrative_files)
    except Exception as _ne:
        print(f"[GALAXY][vision] narrative injection skipped: {_ne}")
    # ═══ GAME KNOWLEDGE VAULT INJECTION (500 DBs → no lazy agents) ═══
    # Pulls from the 500-topic game_knowledge_vault collection and its
    # in-memory fallback so every downstream phase has a canonical knowledge
    # reference. Also stashes `build["_gk_context"]` for _phase_generic.
    try:
        gk_files = _gs._gen_game_knowledge_docs(build, t, g)
        if isinstance(gk_files, dict):
            files.update(gk_files)
    except Exception as _ge:
        print(f"[GALAXY][vision] game-knowledge injection skipped: {_ge}")
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2: BROADENED SCOPE — Expanded stores, types, constants
# ═══════════════════════════════════════════════════════════════════════
def _phase_scope(build, t, g, gi, v, sy, la, ins, m):
    files = {}
    files["store/entityStore.ts"] = _gen_entity_store(t, g)
    files["store/inventoryStore.ts"] = _gen_inventory_store(t, g)
    files["store/combatStore.ts"] = _gen_combat_store(t, g)
    files["store/worldStore.ts"] = _gen_world_store(t, g)
    files["store/networkStore.ts"] = _gen_network_store(t, g)
    files["store/uiStore.ts"] = _gen_ui_store(t, g)
    files["types/index.ts"] = _gen_types(t, g)
    files["types/combat.ts"] = _gen_combat_types(t, g)
    files["types/inventory.ts"] = _gen_inventory_types(t, g)
    files["types/world.ts"] = _gen_world_types(t, g)
    files["types/network.ts"] = _gen_network_types(t, g)
    files["types/ui.ts"] = _gen_ui_types(t, g)
    files["utils/constants.ts"] = _gen_constants(t, g)
    files["utils/helpers.ts"] = _gen_helpers(t, g)
    files["utils/formatters.ts"] = _gen_formatters(t, g)
    files["utils/validators.ts"] = _gen_validators(t, g)
    # Scope expansion doc
    scope_items = ["multiplayer", "crafting", "housing", "mounts", "pets", "guilds", "pvp", "raids", "seasonal events", "battle pass", "mod support", "streaming", "accessibility", "cross-platform", "cloud saves"]
    files["docs/SCOPE_MATRIX.md"] = f"# {t} — Scope Matrix\n\n" + "\n".join(f"- [x] **{s.title()}**: Full implementation planned" for s in scope_items) + f"\n\n## Scale Multiplier: {m}x\n## Total Scope Items: {len(scope_items)}\n"
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE 3: CORE MECHANICS — Screens, input, combat, movement
# ═══════════════════════════════════════════════════════════════════════
def _phase_mechanics(build, t, g):
    files = {}
    all_screens = [
        "GameScreen", "SettingsScreen", "InventoryScreen", "AchievementsScreen",
        "LeaderboardScreen", "ShopScreen", "LevelSelectScreen", "ProfileScreen",
        "TutorialScreen", "MapScreen", "QuestLogScreen", "DialogueScreen",
        "CraftingScreen", "LoadoutScreen", "SkillTreeScreen", "DeckBuilderScreen",
        "CardCollectionScreen", "BuildingScreen", "ResearchScreen", "JournalScreen",
        "SanityScreen", "CombatScreen", "MultiplayerLobbyScreen", "GuildScreen",
        "AuctionHouseScreen", "PvPArenaScreen", "DungeonScreen", "BossRushScreen",
        "CharacterCreateScreen", "GachaScreen", "EventScreen", "SeasonPassScreen",
    ]
    for s in all_screens:
        files[f"screens/{s}.tsx"] = _gen_screen_aaa(s, t, g)
    build["_all_screens"] = all_screens
    # Core logic
    core_logic = [
        ("combatEngine", "Full combat system with hitboxes, damage calc, combos, parry, dodge, status effects, critical hits"),
        ("movementSystem", "Character movement with acceleration, friction, jumping, dashing, wall-sliding, swimming"),
        ("inputManager", "Input handling with action maps, rebinding, gamepad, touch, gesture recognition, context switching"),
        ("interactionSystem", "World interaction with pickup, use, examine, talk, trade, craft, open, push, pull"),
        ("progressionEngine", "XP, leveling, skill points, stat allocation, prestige, mastery, class advancement"),
        ("economySystem", "Currency system with gold, premium, trading, taxes, sinks, inflation control"),
    ]
    for name, desc in core_logic:
        files[f"logic/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE 4: WORLD GENERATION — Procedural terrain, dungeons, biomes
# ═══════════════════════════════════════════════════════════════════════
def _phase_world_gen(build, t, g):
    files = {}
    procgen = [
        ("noise_generator", "Perlin/simplex/worley noise with octaves, persistence, lacunarity, domain warping"),
        ("dungeon_generator", "BSP/cellular automata dungeon with rooms, corridors, traps, secrets, boss rooms"),
        ("terrain_generator", "Heightmap terrain with erosion, biome placement, rivers, cliffs, caves, plateaus"),
        ("city_generator", "Procedural city with districts, roads, buildings, landmarks, traffic, NPCs"),
        ("cave_generator", "Procedural caves with stalactites, water, crystal formations, treasures, hazards"),
        ("biome_generator", "Biome system with climate zones, vegetation, wildlife, resources, transitions"),
        ("weather_generator", "Weather patterns with seasons, storms, climate zones, dynamic transitions"),
        ("name_generator", "Markov chain name generator for NPCs, items, places, factions, spells"),
        ("lore_generator", "Procedural lore with history, factions, conflicts, mythology, artifacts"),
        ("encounter_generator", "Dynamic encounters with difficulty, variety, narrative hooks, ambushes"),
    ]
    for name, desc in procgen:
        files[f"procgen/{name}.ts"] = _gen_procgen_code(name, desc, t, g)
    # World data
    files["data/world_regions_database.ts"] = _gen_data_file("world_regions_database", "World regions with biomes, resources, enemies, NPCs, secrets", t, g)
    files["data/weather_patterns_database.ts"] = _gen_data_file("weather_patterns_database", "Weather patterns with transitions, effects, seasonal cycles", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE 5: PHYSICS & MATH — Physics engine, collision, pathfinding
# ═══════════════════════════════════════════════════════════════════════
def _phase_physics_math(build, t, g):
    files = {}
    files["utils/mathUtils.ts"] = _gen_math_utils(t, g)
    files["utils/colorUtils.ts"] = _gen_color_utils(t, g)
    physics_files = [
        ("physicsEngine", "2D/3D physics with rigid bodies, collision detection, resolution, constraints, joints, ragdoll"),
        ("collisionSystem", "Spatial hashing, broadphase AABB, narrowphase SAT/GJK, trigger volumes, layers, masks"),
        ("pathfinding", "A* pathfinding with navmesh, jump points, hierarchical, dynamic obstacle avoidance, flow fields"),
        ("particlePhysics", "Particle simulation with gravity, wind, turbulence, attractors, soft body, fluid"),
        ("raycastSystem", "Raycasting with line/sphere/box/capsule casts, layered, batched, continuous detection"),
        ("kinematicsEngine", "Forward/inverse kinematics with chain solving, constraints, blending, procedural animation"),
        ("fluidDynamics", "SPH fluid simulation with surface tension, viscosity, buoyancy, wave propagation"),
        ("destructionSystem", "Procedural destruction with voronoi fracture, debris, structural integrity, cascading"),
    ]
    for name, desc in physics_files:
        files[f"logic/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE 6: GRAPHICS & RENDERING — Shaders, VFX, post-processing
# ═══════════════════════════════════════════════════════════════════════
def _phase_graphics(build, t, g):
    files = {}
    shaders = [
        ("pbr_material", "PBR with metallic/roughness, normal mapping, AO, emission, parallax"),
        ("toon_shader", "Cel/toon shading with edge detection, color ramps, specular bands, hatching"),
        ("water_surface", "Water with reflection, refraction, foam, caustics, FFT waves, depth fog"),
        ("particle_shader", "GPU particles with billboarding, soft particles, distortion, trails"),
        ("post_bloom", "Bloom with threshold, scatter, anamorphic, lens dirt, adaptive exposure"),
        ("post_tonemap", "Tonemapping ACES/Reinhard/filmic, color grading, LUT, vignette"),
        ("shadow_cascade", "Cascaded shadow maps with PCF, VSM, PCSS, contact hardening"),
        ("terrain_blend", "Multi-texture terrain with splatmap, triplanar, height blending"),
        ("volumetric_fog", "Volumetric fog with ray marching, light scattering, temporal reprojection"),
        ("screen_space_ao", "GTAO/HBAO with temporal stability, bilateral blur, bent normals"),
        ("atmosphere_scatter", "Rayleigh/Mie scattering with day/night cycle, god rays, aerial perspective"),
        ("ocean_fft", "FFT ocean with Gerstner waves, foam, spray, subsurface, caustics on seabed"),
        ("skin_subsurface", "SSS for skin with pre-integrated BRDF, thickness estimation, translucency"),
        ("foliage_wind", "Vegetation with procedural wind, interaction bending, phase variation, LOD"),
        ("energy_shield", "Force field with hex pattern, impact ripples, charge level, edge glow"),
        ("dissolve_death", "Death dissolve with edge emission, ash particles, noise mask, directional"),
    ]
    for name, desc in shaders:
        files[f"shaders/{name}.glsl"] = _gen_shader_code(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE 7: ASSETS & MEDIA — Data databases, UI components
# ═══════════════════════════════════════════════════════════════════════
def _phase_assets(build, t, g):
    files = {}
    databases = [
        ("items_database", "500+ items: weapons, armor, consumables, materials, keys, quest items, mounts, pets"),
        ("enemies_database", "Enemy definitions with stats, abilities, loot tables, AI profiles, spawn rules"),
        ("skills_database", "Skill trees with prerequisites, scaling, synergies, animations, cooldowns"),
        ("quests_database", "Quest chains with objectives, dialogue, branching paths, rewards, prerequisites"),
        ("recipes_database", "Crafting recipes with ingredients, outputs, skill requirements, stations"),
        ("achievements_database", "Achievement definitions with conditions, rewards, chains, tracking"),
        ("dialogue_database", "NPC dialogue trees with conditions, variables, emotions, localizations"),
        ("loot_tables_database", "Loot tables with weights, pity system, guaranteed drops, rarity curves"),
        ("buff_debuff_database", "Status effects with stacking, duration, interactions, cleanse rules"),
        ("music_tracks_database", "Music tracks with regions, combat/explore modes, adaptive layers, transitions"),
    ]
    for name, desc in databases:
        files[f"data/{name}.ts"] = _gen_data_file(name, desc, t, g)
    # Core UI components
    components = [
        ("HealthBar", "Animated health bar with damage preview, heal flash, shield overlay, numbers"),
        ("MiniMap", "Radar minimap with zoom, fog of war, objective markers, player arrow"),
        ("InventoryGrid", "Grid inventory with drag-drop, stacking, sorting, tooltips, context menu"),
        ("DialogBox", "Dialogue box with typewriter text, portraits, choices, voice playback"),
        ("HUDOverlay", "Full HUD with health, mana, minimap, quest tracker, buffs, compass"),
        ("LoadingScreen", "Loading screen with tips, progress bar, artwork, mini-game"),
        ("SkillTreeView", "Visual skill tree with nodes, connections, preview, reset option"),
        ("DamageNumbers", "Floating damage numbers with crits, elements, heal, miss, parry"),
    ]
    for name, desc in components:
        files[f"components/{name}.tsx"] = _gen_component_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE 8: AI & BEHAVIOR — Behavior trees, NPC logic, enemy AI
# ═══════════════════════════════════════════════════════════════════════
def _phase_ai_behavior(build, t, g):
    files = {}
    ai = [
        ("bt_enemy_melee", "Melee enemy: patrol-detect-chase-attack-retreat-heal-call_backup"),
        ("bt_enemy_ranged", "Ranged enemy: position-aim-fire-cover-reload-reposition-suppress"),
        ("bt_boss_phase", "Multi-phase boss: phase1-transition-phase2-enrage-desperation-final"),
        ("bt_npc_civilian", "Civilian NPC: schedule-work-eat-socialize-sleep-flee_danger-gossip"),
        ("bt_companion", "Companion: follow-assist-heal-revive-gather-dialog-buff-protect"),
        ("bt_squad_tactics", "Squad: formation-flank-suppress-advance-retreat-regroup-ambush"),
        ("bt_wildlife", "Wildlife: wander-graze-flee-fight-migrate-den-breed-hunt"),
        ("bt_merchant", "Merchant: open_shop-restock-price_adjust-travel-negotiate-barter"),
        ("bt_boss_dragon", "Dragon boss: fly-breath_attack-land-tail_sweep-summon-enrage-dive"),
        ("bt_necromancer_boss", "Necro boss: summon_undead-curse-life_drain-bone_wall-death_nova-resurrect"),
        ("bt_guard", "Guard: patrol-alert-investigate-challenge-engage-call_backup-return"),
        ("bt_healer", "Healer: assess_allies-triage-heal-shield-cleanse-mana_manage-fallback"),
        ("bt_assassin", "Assassin: stealth-position_behind-opener-burst-vanish-reset-restealth"),
        ("bt_tank", "Tank: aggro_check-position-taunt-cooldown_rotation-mitigate-self_heal"),
        ("bt_summoner", "Summoner: summon-command-position_pets-buff_pets-sacrifice-resummon"),
        ("bt_crowd_npc", "Crowd: wander-gather-react_event-flee-cheer-trade-gossip-sleep"),
        ("bt_hunting_pack", "Pack: track_prey-surround-alpha_signal-coordinate_attack-share_kill"),
        ("bt_world_tree", "World Tree: grow-heal_allies-root_attack-spawn_treants-seasonal_shift"),
        ("bt_void_entity", "Void Entity: phase_through-reality_tear-gravity_well-consume-dimension_shift"),
        ("bt_lich_king", "Lich King: phylactery_check-soul_harvest-ice_storm-raise_dead-dominate"),
    ]
    for name, desc in ai:
        files[f"ai/{name}.ts"] = _gen_ai_behavior_tree(name, desc, t, g)
    # AI controller
    files["controllers/aiController.ts"] = _gen_logic_aaa("aiController", "AI orchestrator with entity budgeting, LOD, priority, pathfinding requests", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE 9: NETWORKING & SCALE UP — Multiplayer + scale expansion
# ═══════════════════════════════════════════════════════════════════════
def _phase_networking(build, t, g, m, v, sy, la, ins):
    files = {}
    net = [
        ("protocol", "Binary protocol with message types, serialization, versioning, compression"),
        ("client", "Game client with connection, reconnection, heartbeat, encryption, buffering"),
        ("server_sim", "Server simulation with tick rate, authority, anti-cheat, state broadcast"),
        ("sync_system", "State sync with interpolation, extrapolation, snapshot, delta compression"),
        ("lobby_manager", "Lobby with room codes, matchmaking queue, party, ready check, SBMM"),
        ("chat_system", "Chat with channels, whisper, moderation, emotes, history, spam filter"),
        ("replication", "State replication with ownership, relevancy, priority, bandwidth"),
        ("voice_chat", "Voice chat with spatial, channels, mute, recording, echo cancel"),
        ("party_sync", "Party sync with invites, roles, shard state, leader election, persistence"),
    ]
    for name, desc in net:
        files[f"networking/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    # Scale expansion
    if m > 1:
        _gs._expand_for_scale(files, t, g, m, v, sy, la, ins)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE 10: BALANCING & TUNING — Game balance, economy, difficulty
# ═══════════════════════════════════════════════════════════════════════
def _phase_balancing(build, t, g):
    files = {}
    balance = [
        ("difficultyManager", "Dynamic difficulty with player skill tracking, scaling curves, adaptive AI, rubber banding"),
        ("economyBalancer", "Economy tuning with currency sinks/faucets, inflation curves, market simulation, price floor/ceiling"),
        ("combatBalancer", "Combat balance with DPS curves, TTK targets, mitigation formulas, stat weights, breakpoints"),
        ("lootBalancer", "Loot distribution with pity timers, bad luck protection, rarity curves, smart loot, duplicate detection"),
        ("progressionBalancer", "XP curves, level scaling, power budgets, gear score, content gating, catch-up mechanics"),
        ("matchmakingBalancer", "MMR system with ELO/Glicko, placement, decay, seasonal resets, smurf detection, queue priority"),
        ("spawnBalancer", "Spawn system with density, respawn timers, population caps, dynamic throttling, camp prevention"),
        ("resourceBalancer", "Resource economy with gather rates, processing costs, market dynamics, scarcity events"),
    ]
    for name, desc in balance:
        files[f"logic/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    files["data/balance_tables_database.ts"] = _gen_data_file("balance_tables_database", "Master balance spreadsheet with all tuning values, curves, formulas", t, g)
    files["data/difficulty_curves_database.ts"] = _gen_data_file("difficulty_curves_database", "Difficulty progression curves per zone, encounter, boss, with adaptive scaling", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# MUTATION PERMUTATION ENGINE (2026-06-18)
# Generates code for EVERY permutation/combination of the user-selected
# mutations (from the questionnaire `mutation_matrix`). Each generated
# module is WRAPPED with redundancy (retry + safe-default + reversible
# rollback) and full error handling so a mutation can never crash the game.
# ═══════════════════════════════════════════════════════════════════════
MUTATION_OPERATORS = ["drift", "jitter", "mutate", "recombine"]
_MUT_MAX_MATERIALIZED = 750   # hard cap on concrete combination files (engine covers the full product at runtime)
_MUT_MAX_COMBO_SIZE = 4       # materialise combos up to this arity; larger arities handled by the runtime engine


def _mut_camel(s: str) -> str:
    return ''.join(w.capitalize() for w in str(s).replace('-', '_').replace(' ', '_').split('_') if w)


def _extract_active_mutations(build: dict):
    """Return [(mutation_id, {axis: int}), ...] for every mutation the user
    actually dialed in (any axis > 0). Tolerant of missing/garbage input."""
    out = []
    try:
        mm = build.get("mutation_matrix")
        if not isinstance(mm, dict):
            return out
        for phase_id, axes in mm.items():
            if not isinstance(phase_id, str) or not isinstance(axes, dict):
                continue
            vals = {}
            for k, v in axes.items():
                try:
                    vals[str(k)] = int(v)
                except (TypeError, ValueError):
                    continue
            if any(x > 0 for x in vals.values()):
                out.append((phase_id[:48], vals))
    except Exception as _e:
        print(f"[GALAXY mutations] _extract_active_mutations failed: {_e}")
    return out[:32]  # safety bound on the number of active axes


def _gen_mutation_module(mid: str, vals: dict, title: str, genre: str) -> str:
    """A single mutation's redundant, error-handled mutator class."""
    cls = _mut_camel(mid)
    rate = vals.get("rate", 0); mag = vals.get("magnitude", 0)
    safety = vals.get("safety", 0); novelty = vals.get("novelty", 0)
    rev = vals.get("reversibility", 0)
    return f'''// ═══ {title} — {cls}Mutator ═══
// Mutation axis: {mid} | genre={genre} | Galaxy Studio Mutation Engine
// REDUNDANT + ERROR-HANDLED: retry → safe-default → reversible rollback.

export interface MutationContext {{ seed: number; intensity: number; tick: number; }}
export interface MutationResult<T> {{ ok: boolean; value: T; applied: string[]; rolledBack: boolean; error?: string; }}

const RATE = {rate};
const MAGNITUDE = {mag};
const SAFETY = {safety};        // ≥50 ⇒ never throw past the safety net
const NOVELTY = {novelty};
const REVERSIBILITY = {rev};    // >0 ⇒ rollback to last good snapshot on failure

export class {cls}Mutator<T = any> {{
  private history: T[] = [];
  private readonly maxRetries = 3;
  private readonly maxHistory = 16;

  /** Apply every operator with per-operator retry + global rollback. Never throws. */
  apply(input: T, ctx: MutationContext): MutationResult<T> {{
    const applied: string[] = [];
    const snapshot = this._clone(input);
    try {{
      this._pushHistory(snapshot);
      let value = input;
      for (const op of {MUTATION_OPERATORS!r} as const) {{
        value = this._withRetry(() => this._operator(op, value, ctx), op, applied);
      }}
      if (!this._validate(value, ctx)) throw new Error('post-mutation validation failed for {mid}');
      return {{ ok: true, value, applied, rolledBack: false }};
    }} catch (err: any) {{
      const canRollback = REVERSIBILITY > 0 && this.history.length > 0;
      const value = canRollback ? this.history[this.history.length - 1] : snapshot;
      return {{ ok: false, value, applied, rolledBack: canRollback, error: String(err?.message ?? err) }};
    }}
  }}

  private _withRetry(fn: () => T, op: string, applied: string[]): T {{
    let lastErr: unknown;
    for (let i = 0; i < this.maxRetries; i++) {{
      try {{ const r = fn(); applied.push(op); return r; }}
      catch (e) {{ lastErr = e; }}
    }}
    if (SAFETY >= 50) return this._safeDefault();   // redundant safe path
    throw lastErr instanceof Error ? lastErr : new Error(String(lastErr));
  }}

  private _operator(op: string, value: T, ctx: MutationContext): T {{
    const amp = (MAGNITUDE / 1000) * (1 + NOVELTY / 1000);
    const jitter = (Math.sin(ctx.seed + ctx.tick) * amp) || 0;
    switch (op) {{
      case 'drift':     return this._mapNumbers(value, (n) => n + jitter * 0.1);
      case 'jitter':    return this._mapNumbers(value, (n) => n + jitter * (Math.random() - 0.5));
      case 'mutate':    return this._mapNumbers(value, (n) => n * (1 + amp * (Math.random() - 0.5)));
      case 'recombine': return this._recombine(value, ctx);
      default:          return value;
    }}
  }}

  private _recombine(value: T, ctx: MutationContext): T {{
    if (this.history.length < 2) return value;
    const a = this.history[this.history.length - 1];
    return (Math.random() < 0.5 ? a : value) as T;
  }}

  private _mapNumbers(value: T, fn: (n: number) => number): T {{
    try {{
      if (typeof value === 'number') return fn(value) as unknown as T;
      if (value && typeof value === 'object') {{
        const out: any = Array.isArray(value) ? [] : {{}};
        for (const k of Object.keys(value as any)) {{
          const v = (value as any)[k];
          out[k] = typeof v === 'number' ? fn(v) : v;
        }}
        return out as T;
      }}
    }} catch {{ /* fall through to identity */ }}
    return value;
  }}

  private _validate(value: T, _ctx: MutationContext): boolean {{
    if (value == null) return false;
    if (typeof value === 'number') return Number.isFinite(value);
    return true;
  }}

  private _safeDefault(): T {{ return (this.history[0] ?? (null as any)) as T; }}
  private _pushHistory(v: T) {{ this.history.push(v); if (this.history.length > this.maxHistory) this.history.shift(); }}
  private _clone(v: T): T {{ try {{ return JSON.parse(JSON.stringify(v)); }} catch {{ return v; }} }}
}}

export const {cls.lower()}MutatorMeta = {{ id: '{mid}', rate: RATE, magnitude: MAGNITUDE, safety: SAFETY, novelty: NOVELTY, reversibility: REVERSIBILITY }};
'''


def _gen_mutation_operator_module(mid: str, op: str, vals: dict, title: str, genre: str) -> str:
    """A concrete (mutation × operator) variant — one of the materialised permutation atoms."""
    cls = _mut_camel(mid)
    opc = _mut_camel(op)
    return f'''// {title} — {cls}__{opc} (mutation={mid}, operator={op}) | genre={genre}
// Materialised permutation atom — error-handled + redundant.
import {{ {cls}Mutator, MutationContext, MutationResult }} from '../{cls}Mutator';

export function apply{cls}{opc}<T = any>(input: T, ctx: MutationContext): MutationResult<T> {{
  const m = new {cls}Mutator<T>();
  try {{
    const res = m.apply(input, ctx);
    // Redundancy: if the full chain failed, degrade to identity rather than crash.
    if (!res.ok && !res.rolledBack) return {{ ok: false, value: input, applied: res.applied, rolledBack: false, error: res.error }};
    return res;
  }} catch (err: any) {{
    return {{ ok: false, value: input, applied: [], rolledBack: false, error: String(err?.message ?? err) }};
  }}
}}

export const {cls.lower()}{opc}Permutation = {{ mutation: '{mid}', operator: '{op}' }};
'''


def _gen_mutation_combo_module(combo, active_map: dict, title: str, genre: str) -> str:
    """A concrete combination (Cartesian permutation slice) applying several mutations in sequence."""
    name = '_'.join(_mut_camel(c) for c in combo)
    imports = "\n".join(
        f"import {{ {_mut_camel(c)}Mutator }} from '../{_mut_camel(c)}Mutator';" for c in combo
    )
    chain = "\n    ".join(
        f"r = this._step('{c}', new {_mut_camel(c)}Mutator(), r, ctx, applied);" for c in combo
    )
    return f'''// {title} — Permutation[{name}] | genre={genre}
// Combination permutation of {len(combo)} mutations — fully error-handled + redundant.
import {{ MutationContext, MutationResult }} from '../{_mut_camel(combo[0])}Mutator';
{imports}

export class Permutation{name} {{
  apply<T = any>(input: T, ctx: MutationContext): MutationResult<T> {{
    const applied: string[] = [];
    let r: any = input;
    try {{
      {chain}
      return {{ ok: true, value: r, applied, rolledBack: false }};
    }} catch (err: any) {{
      // Redundancy: any sub-mutation failure degrades gracefully to the last good value.
      return {{ ok: false, value: r ?? input, applied, rolledBack: r !== input, error: String(err?.message ?? err) }};
    }}
  }}

  private _step<T>(id: string, mut: any, value: T, ctx: MutationContext, applied: string[]): T {{
    try {{
      const res = mut.apply(value, ctx);
      applied.push(id + (res.ok ? ':ok' : ':skip'));
      return res.ok ? res.value : value;   // skip-on-failure keeps the chain alive
    }} catch {{ applied.push(id + ':error'); return value; }}
  }}
}}

export const permutation{name}Spec = {{ mutations: {list(combo)!r}, arity: {len(combo)} }};
'''


def _gen_mutation_permutation_engine(active, title: str, genre: str) -> str:
    """Runtime engine that lazily enumerates the FULL Cartesian product of
    all active mutations × {off + operators} — every permutation, no OOM."""
    ids = [mid for mid, _ in active]
    operators = ["off"] + MUTATION_OPERATORS
    return f'''// ═══ {title} — MutationPermutationEngine ═══
// genre={genre} | Galaxy Studio
// Enumerates the FULL Cartesian product of every active mutation across
// {{off, drift, jitter, mutate, recombine}}. TOTAL = {len(operators)}^{len(ids)} permutations.
// Enumeration is a lazy odometer — all permutations are reachable, zero pre-allocation.

import {{ MutationContext, MutationResult }} from './{(_mut_camel(ids[0]) if ids else 'Noop')}Mutator';

export const ACTIVE_MUTATIONS: string[] = {ids!r};
export const OPERATORS = {operators!r} as const;
export type Operator = typeof OPERATORS[number];

/** Total number of permutations in the full Cartesian product. */
export const TOTAL_PERMUTATIONS = Math.pow(OPERATORS.length, ACTIVE_MUTATIONS.length);

/** Lazy generator over EVERY permutation (memory-safe odometer). */
export function* enumeratePermutations(): Generator<Record<string, Operator>> {{
  const n = ACTIVE_MUTATIONS.length;
  if (n === 0) return;
  const radix = OPERATORS.length;
  const idx = new Array(n).fill(0);
  while (true) {{
    const combo: Record<string, Operator> = {{}};
    for (let i = 0; i < n; i++) combo[ACTIVE_MUTATIONS[i]] = OPERATORS[idx[i]];
    yield combo;
    let k = n - 1;
    while (k >= 0) {{ idx[k]++; if (idx[k] < radix) break; idx[k] = 0; k--; }}
    if (k < 0) break;
  }}
}}

/** Decode a single permutation by its global index (0 ≤ i < TOTAL_PERMUTATIONS). */
export function permutationAt(i: number): Record<string, Operator> {{
  const n = ACTIVE_MUTATIONS.length;
  const radix = OPERATORS.length;
  const combo: Record<string, Operator> = {{}};
  let rem = Math.max(0, Math.floor(i));
  for (let p = n - 1; p >= 0; p--) {{ combo[ACTIVE_MUTATIONS[p]] = OPERATORS[rem % radix]; rem = Math.floor(rem / radix); }}
  return combo;
}}

type MutatorFactory = () => {{ apply: (v: any, ctx: MutationContext) => MutationResult<any> }};

/** Apply one permutation with full error handling + redundant skip-on-failure. */
export function applyPermutation<T = any>(
  input: T,
  combo: Record<string, Operator>,
  registry: Record<string, MutatorFactory>,
  ctx: MutationContext,
): MutationResult<T> {{
  const applied: string[] = [];
  let value: any = input;
  try {{
    for (const id of ACTIVE_MUTATIONS) {{
      const op = combo[id];
      if (!op || op === 'off') continue;
      const factory = registry[id];
      if (!factory) {{ applied.push(id + ':missing'); continue; }}
      try {{
        const res = factory().apply(value, ctx);
        applied.push(`${{id}}:${{op}}:${{res.ok ? 'ok' : 'skip'}}`);
        if (res.ok) value = res.value;       // redundancy: skip-on-failure
      }} catch (e) {{ applied.push(id + ':' + op + ':error'); }}
    }}
    return {{ ok: true, value, applied, rolledBack: false }};
  }} catch (err: any) {{
    return {{ ok: false, value: value ?? input, applied, rolledBack: value !== input, error: String(err?.message ?? err) }};
  }}
}}
'''


def _gen_mutation_permutation_registry(active, materialized, title: str, genre: str) -> str:
    ids = [mid for mid, _ in active]
    reg_lines = "\n".join(
        f"  '{mid}': () => new {_mut_camel(mid)}Mutator()," for mid in ids
    )
    imports = "\n".join(
        f"import {{ {_mut_camel(mid)}Mutator }} from './{_mut_camel(mid)}Mutator';" for mid in ids
    )
    operators = ["off"] + MUTATION_OPERATORS
    return f'''// ═══ {title} — MutationPermutationRegistry ═══
// genre={genre} | Galaxy Studio
// Central registry of every active mutation mutator + permutation bookkeeping.
{imports}

export const MUTATION_REGISTRY: Record<string, () => any> = {{
{reg_lines}
}};

// Concrete combination modules materialised at build time (engine covers the rest):
export const MATERIALISED_PERMUTATIONS = {[ '_'.join(c) for c in materialized ]!r};
export const MATERIALISED_COUNT = {len(materialized)};

// Full Cartesian product size (computed; enumerated lazily by the engine):
export const TOTAL_PERMUTATIONS = Math.pow({len(operators)}, {len(ids)});

export function listMutations(): string[] {{ return Object.keys(MUTATION_REGISTRY); }}
'''


def _gen_all_mutation_permutations(active, t: str, g: str) -> dict:
    """Materialise the mutation permutation codebase (capped) + the runtime engine."""
    import itertools
    files: dict = {}
    active_map = {mid: vals for mid, vals in active}
    ids = [mid for mid, _ in active]

    # 1) per-mutation base mutator (redundant + error-handled)
    for mid, vals in active:
        files[f"logic/mutations/{_mut_camel(mid)}Mutator.ts"] = _gen_mutation_module(mid, vals, t, g)

    # 2) per (mutation × operator) materialised permutation atoms
    for mid, vals in active:
        for op in MUTATION_OPERATORS:
            files[f"logic/mutations/variants/{_mut_camel(mid)}__{op}.ts"] = \
                _gen_mutation_operator_module(mid, op, vals, t, g)

    # 3) higher-arity combination permutations (capped; engine handles the full product)
    materialized = []
    for r in range(2, min(_MUT_MAX_COMBO_SIZE, len(ids)) + 1):
        if len(materialized) >= _MUT_MAX_MATERIALIZED:
            break
        for combo in itertools.combinations(ids, r):
            if len(materialized) >= _MUT_MAX_MATERIALIZED:
                break
            fname = f"logic/mutations/permutations/perm_{'_'.join(_mut_camel(c) for c in combo)}.ts"
            files[fname] = _gen_mutation_combo_module(combo, active_map, t, g)
            materialized.append(combo)

    # 4) runtime engine + registry (always)
    files["logic/mutations/MutationPermutationEngine.ts"] = _gen_mutation_permutation_engine(active, t, g)
    files["logic/mutations/MutationPermutationRegistry.ts"] = \
        _gen_mutation_permutation_registry(active, materialized, t, g)
    return files



# ═══════════════════════════════════════════════════════════════════════
# PHASE 11: UNIQUE PERMUTATIONS — Variations, randomization, mutations
# ═══════════════════════════════════════════════════════════════════════
def _phase_permutations(build, t, g, m):
    files = {}
    perms = [
        ("itemPermutator", "Item variation engine with random affixes, rarity tiers, synergy bonuses, visual variants, naming"),
        ("enemyMutator", "Enemy mutation system with stat modifiers, ability swaps, elemental affinities, elite/champion tiers"),
        ("dungeonPermutator", "Dungeon variation with room shuffling, trap placement, loot seeding, themed modifiers, rift keys"),
        ("questVariator", "Quest variation with alternative objectives, randomized NPCs, context-aware dialogue, dynamic rewards"),
        ("weaponForge", "Weapon forge with procedural stats, gem sockets, enchantment slots, set bonuses, unique properties"),
        ("armorSmith", "Armor generation with defense profiles, set bonuses, cosmetic variants, dye channels, transmogrify"),
        ("spellWeaver", "Spell creation with element mixing, shape selection, modifier stacking, custom animations, combos"),
        ("encounterShuffler", "Encounter shuffling with difficulty modifiers, loot bonuses, time challenges, wave variations"),
        ("biomeRemixer", "Biome remixing with season variants, corruption modes, pristine/chaotic states, resource shifts"),
        ("npcPersonality", "NPC personality generator with traits, voice styles, interaction preferences, mood shifts, memories"),
    ]
    for name, desc in perms:
        files[f"logic/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    # Extended screens for permutations
    perm_screens = [
        "StatsScreen", "EncyclopediaScreen", "ReplayScreen", "PhotoModeScreen",
        "FishingScreen", "MiningScreen", "FarmingScreen", "CookingScreen",
        "AlchemyScreen", "EnchantingScreen", "BlacksmithScreen", "TailorScreen",
        "PetScreen", "MountScreen", "HousingScreen", "GardenScreen",
    ]
    for s in perm_screens:
        files[f"screens/{s}.tsx"] = _gen_screen_aaa(s, t, g)
    build["_all_screens"] = build.get("_all_screens", []) + perm_screens

    # ── Mutation permutation codebase (every permutation of selected mutations) ──
    try:
        active = _extract_active_mutations(build)
        if active:
            mut_files = _gen_all_mutation_permutations(active, t, g)
            files.update(mut_files)
            build["mutation_permutation_files"] = len(mut_files)
            build["mutation_active_axes"] = [mid for mid, _ in active]
    except Exception as _me:
        print(f"[GALAXY mutations] permutation generation failed (non-fatal): {_me}")

    # ── 40 Capability Systems (each with its own mutation permutation engine) ──
    try:
        from routes import galaxy_studio_capabilities as _caps
        cap_files = _caps.generate_all_capabilities(build, t, g)
        files.update(cap_files)
        build["capability_files"] = len(cap_files)
    except Exception as _ce:
        print(f"[GALAXY capabilities] generation failed (non-fatal): {_ce}")

    # ── Maximal Game Development Pipeline (8-stage AAA orchestrator) ──
    try:
        from routes import galaxy_studio_gamedev_pipeline as _gdp
        pipe_files = _gdp.generate_gamedev_pipeline(build, t, g)
        files.update(pipe_files)
    except Exception as _pe2:
        print(f"[GALAXY gamedev-pipeline] generation failed (non-fatal): {_pe2}")

    # ── Agent self-sufficiency datasets (local knowledge fabric) ──
    try:
        from routes import galaxy_studio_datasets as _ds
        ds_files = _ds.generate_datasets(build, t, g)
        files.update(ds_files)
    except Exception as _de:
        print(f"[GALAXY datasets] generation failed (non-fatal): {_de}")

    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE 12: ENHANCEMENT & OPTIMIZATION — Performance, caching, memory
# ═══════════════════════════════════════════════════════════════════════
def _phase_enhancement(build, t, g):
    files = {}
    enhance = [
        ("cacheService", "Multi-layer cache with LRU, TTL, invalidation, prefetch, compression, persistence"),
        ("eventBus", "Event bus with pub/sub, typed events, middleware, replay, dead letter queue, batching"),
        ("configService", "Config management with env, feature flags, remote config, A/B testing, rollback"),
        ("compressionService", "Data compression with gzip, lz4, brotli, streaming, dictionary coding"),
        ("serializationService", "Serialization with binary, JSON, msgpack, protobuf, schema evolution"),
        ("memoryPoolManager", "Memory pool with pre-allocation, recycling, defragmentation, budget tracking"),
        ("lodManager", "LOD management with distance, screen-size, budget, streaming, cross-fade"),
        ("asyncJobQueue", "Async job queue with priority, retry, batching, throttling, cancellation"),
    ]
    for name, desc in enhance:
        files[f"services/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    # Controllers
    controllers = [
        ("gameController", "Main game loop with state transitions, pause, resume, tick management, delta time"),
        ("combatController", "Combat flow with turn order, action resolution, animation sync, combo chains"),
        ("sceneController", "Scene management with loading, transitions, streaming, memory budget"),
        ("cameraController", "Camera with modes, transitions, constraints, shake, cinematic, orbit"),
    ]
    for name, desc in controllers:
        files[f"controllers/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE 13: STATE OF THE ART — Cutting-edge: ML, neural, procedural
# ═══════════════════════════════════════════════════════════════════════
def _phase_sota(build, t, g):
    files = {}
    sota = [
        ("neuralPathfinding", "Neural network pathfinding with learned navigation meshes, dynamic obstacle prediction, fleet behavior"),
        ("mlDifficultyPredictor", "ML difficulty prediction with player behavior analysis, engagement scoring, churn prevention"),
        ("proceduralAnimation", "Procedural animation with IK solving, motion matching, ragdoll blending, facial expressions"),
        ("adaptiveAudioEngine", "Adaptive audio with layered music, emotion tracking, procedural SFX, spatial HRTF, dynamic mix"),
        ("realTimeGI", "Real-time GI with irradiance probes, light propagation volumes, SH encoding, temporal filtering"),
        ("cloudStreamEngine", "Cloud streaming with adaptive quality, input prediction, frame pacing, edge compute, codec optimization"),
        ("mlAntiCheat", "ML anti-cheat with behavioral analysis, anomaly detection, player fingerprinting, replay validation"),
        ("generativeContentEngine", "Procedural content with grammar-based generation, constraint solving, quality evaluation, caching"),
        ("emotionEngine", "Emotion system with NPC mood, player sentiment, dynamic narrative, atmospheric response"),
        ("timeManipulation", "Time mechanics with slow-mo, rewind, fast-forward, timeline branching, paradox resolution"),
    ]
    for name, desc in sota:
        files[f"logic/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    # SOTA shaders
    sota_shaders = [
        ("ray_traced_gi", "Ray traced global illumination with denoising, temporal accumulation"),
        ("neural_upscale", "ML upscaling (DLSS/FSR style) with temporal anti-aliasing, sharpening"),
        ("strand_hair", "Strand-based hair rendering with translucency, wind, self-shadow"),
        ("cloud_volumetric", "Volumetric clouds with ray marching, wind erosion, silver lining"),
        ("lava_flow", "Lava surface with flow simulation, cooling, crust, emission patterns"),
        ("hologram_display", "Holographic shader with scan lines, flicker, interference, distortion"),
    ]
    for name, desc in sota_shaders:
        files[f"shaders/{name}.glsl"] = _gen_shader_code(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# ★ ANIMATIONS PACK (2026-02) — scales file count + density with the
# `animation_fluidity` and `animation_style` sliders set in the Galaxy
# Studio frontend. Emits ready-to-drop React Native `Animated` helpers.
# At fluidity 0 → 0 files. At fluidity 10 → ~120 files covering tweens,
# springs, loops, gestures, camera shake, particle bursts, parallax,
# screen transitions, HUD pulses, damage flashes, idle breathers, etc.
# ═══════════════════════════════════════════════════════════════════════
_ANIM_STYLE_PROFILES = {
    "subtle":     {"dur": (600, 900), "tens": (40, 70),  "amp": 0.5, "eased": "inOut"},
    "smooth":     {"dur": (400, 700), "tens": (70, 110), "amp": 0.8, "eased": "inOut"},
    "punchy":     {"dur": (180, 320), "tens": (180, 260),"amp": 1.2, "eased": "out"},
    "cinematic":  {"dur": (800, 1400),"tens": (55, 95),  "amp": 1.5, "eased": "inOut"},
}

_ANIM_PATTERNS = [
    ("fade_in",      "Smooth fade from 0→1 opacity with soft ease."),
    ("slide_up",     "Translate up 24→0 with spring."),
    ("slide_left",   "Translate left 32→0 with spring."),
    ("pop_in",       "Scale 0.75→1 spring, combined with opacity."),
    ("pulse_loop",   "Infinite pulse loop for HUD elements."),
    ("breathing",    "Slow breathing loop for idle characters."),
    ("shake",        "Camera / UI shake on damage."),
    ("float_drift",  "Gentle bobbing float for pickups."),
    ("rotate_loop",  "Continuous rotation for magical glyphs."),
    ("flash_damage", "Red flash on health damage."),
    ("levelup_burst","Golden radial burst on level-up."),
    ("pickup_bump",  "Quick scale bump on item pickup."),
    ("cursor_trail", "Cursor / touch trail fading over time."),
    ("parallax",     "Multi-layer parallax scroll speed factor."),
    ("dialog_enter", "Dialog box bottom-in with bounce."),
    ("menu_fly",     "Menu items fly in with staggered delay."),
    ("explosion",    "Multi-stage expand + fade + shock ring."),
    ("trail_dash",   "Character dash with afterimage trail."),
    ("hit_freeze",   "Micro hit-freeze frame on critical damage."),
    ("slow_motion",  "Engine timescale slowdown on boss kill."),
    ("screen_wipe",  "Scene transition horizontal wipe."),
    ("iris_open",    "Iris-open scene reveal."),
    ("portal_warp",  "Warp portal swirl distortion."),
    ("boss_intro",   "Boss intro camera dolly + title crash."),
    ("scoreflash",   "Score increase ticker with number pulse."),
    ("combo_grow",   "Combo counter grow + color shift."),
    ("respawn_glow", "Respawn aura ring."),
    ("quest_toast",  "Quest complete toast slide + icon spin."),
    ("speech_blip",  "Dialogue letter-by-letter typewriter."),
    ("pagewipe_in",  "Radial page wipe in."),
    ("chromatic_snap","Chromatic aberration pulse on critical impact."),
]

# ═══════════════════════════════════════════════════════════════════════
# ★ 31 ANIMATION TECHNIQUES (2026-02)
# Motion techniques / rigging approaches that every modern game animator
# should know. Emitted as one reference doc per technique so the final
# build folder teaches the project team the vocabulary.
# ═══════════════════════════════════════════════════════════════════════
_ANIM_TECHNIQUES = [
    ("keyframe",             "Classic pose-to-pose: key frames define critical poses; tangents control curves."),
    ("tween_interpolation",  "Interpolate between two values over time with an easing curve."),
    ("spring_physics",       "Mass-spring dynamics for natural overshoot/settle motion."),
    ("inverse_kinematics",   "Goal-driven limb placement — the hand reaches; the elbow follows."),
    ("forward_kinematics",   "Direct joint rotation — the shoulder drives the arm."),
    ("motion_matching",      "Pick the closest pose from a motion database on-the-fly at runtime."),
    ("root_motion",          "The animation drives character position instead of code."),
    ("blend_trees",          "2-D parameter blend between movement anims (walk/run/strafe)."),
    ("state_machine",        "Named states + transition rules (idle → walk → run → land)."),
    ("additive_layer",       "Layer an additive anim on top of base (aim, lean, damage)."),
    ("mask_layer",           "Per-bone weighting so upper body animates separate from legs."),
    ("blend_shape",          "Facial morph targets — smile, frown, phonemes."),
    ("skeletal_skinning",    "Vertices follow weighted bones with smooth deformation."),
    ("vertex_animation",     "Baked vertex positions per frame (VAT — great for foliage/crowds)."),
    ("procedural_walk",      "Generate footstep placement from terrain + velocity at runtime."),
    ("ragdoll_physics",      "Switch to physics-driven bones on death/knockdown."),
    ("dynamic_bones",        "Spring physics on hair, tails, cloth fringes."),
    ("cloth_simulation",     "Particle-constraint mesh sim for capes, flags, robes."),
    ("ik_lookat",            "Head/eyes aim at a world-space target."),
    ("foot_ik",              "Plant feet on uneven terrain, match heel-to-ground."),
    ("motion_capture",       "Performance-captured raw clip retargeted to game skeleton."),
    ("anticipation_squash",  "12-principles: windup, squash/stretch, follow-through."),
    ("sprite_sheet",         "Frame-flipbook for 2-D games."),
    ("vector_rig",           "Live 2-D bones with mesh deform (Spine/Live2D style)."),
    ("shader_vertex_wave",   "Vertex shader animates water, grass, flags without rig."),
    ("particle_driven",      "Emitter-controlled visuals (sparks, explosions, magic)."),
    ("dynamic_lod",          "Swap anim complexity by camera distance for perf."),
    ("lip_sync",             "Map audio analysis / phonemes to mouth shapes per frame."),
    ("camera_shake",         "Procedural 3-axis noise for explosions and impacts."),
    ("cinematic_sequencer",  "Timeline editor: camera + anim + audio in one clip."),
    ("contextual_idle",      "Pick ambient idle that matches holstered weapon / mood."),
]


def _gen_animation_pattern_file(name: str, desc: str, t: str, g: str, profile: dict, fluid: int, idx: int) -> str:
    dur_lo, dur_hi = profile["dur"]
    tens_lo, tens_hi = profile["tens"]
    amp = profile["amp"]
    dur = dur_lo + (dur_hi - dur_lo) * (idx % 5) // 4
    tens = tens_lo + (tens_hi - tens_lo) * (idx % 3) // 2
    return f"""// ═══ {t} — Animation Pattern: {name} ═══
// {desc}
// Genre: {g} | Fluidity: {fluid}/10 | Style profile: duration={dur}ms tension={tens} amp={amp}
// Galaxy Studio Factory — auto-generated animation preset #{idx:03d}
import {{ Animated, Easing }} from 'react-native';

/**
 * {name}: {desc}
 *
 * Usage:
 *   const anim = useRef(new Animated.Value(0)).current;
 *   useEffect(() => run_{name}(anim), []);
 */
export const {name}_DURATION = {dur};
export const {name}_TENSION = {tens};
export const {name}_AMPLITUDE = {amp};

export function run_{name}(value: Animated.Value, opts: {{ loop?: boolean; delay?: number }} = {{}}): void {{
  const {{ loop = false, delay = 0 }} = opts;
  const seq = Animated.sequence([
    Animated.timing(value, {{ toValue: 1, duration: {dur}, easing: Easing.inOut(Easing.ease), delay, useNativeDriver: true }}),
    Animated.timing(value, {{ toValue: 0, duration: {dur}, easing: Easing.inOut(Easing.ease), useNativeDriver: true }}),
  ]);
  if (loop) Animated.loop(seq).start();
  else seq.start();
}}

export function spring_{name}(value: Animated.Value, to = 1): void {{
  Animated.spring(value, {{
    toValue: to,
    tension: {tens},
    friction: 8,
    useNativeDriver: true,
  }}).start();
}}

export function shake_{name}(value: Animated.Value, amplitude = {amp}, count = 4): void {{
  const dx = amplitude * 6;
  const seq: any[] = [];
  for (let i = 0; i < count; i++) {{
    seq.push(Animated.timing(value, {{ toValue: i % 2 === 0 ? dx : -dx, duration: 60, useNativeDriver: true }}));
  }}
  seq.push(Animated.timing(value, {{ toValue: 0, duration: 80, useNativeDriver: true }}));
  Animated.sequence(seq).start();
}}

export default {{
  DURATION: {name}_DURATION,
  TENSION: {name}_TENSION,
  AMPLITUDE: {name}_AMPLITUDE,
  run: run_{name},
  spring: spring_{name},
  shake: shake_{name},
}};
"""


def _phase_animations_pack(build: dict, t: str, g: str) -> dict:
    """Generate animations/ folder with density scaling to animation_fluidity.

    Files per build = fluid * pattern_count * style_variants.
    fluidity 0 → 0 files (opt-out).
    fluidity 1 → ~12 files (one style, minimal coverage).
    fluidity 5 → ~60 files.
    fluidity 10 → ~120 files across all styles.
    """
    fluid = int(build.get("animation_fluidity", 7) or 0)
    if fluid <= 0:
        return {}
    style = str(build.get("animation_style", "smooth")).lower()
    if style not in _ANIM_STYLE_PROFILES:
        style = "smooth"
    profile = _ANIM_STYLE_PROFILES[style]
    # Coverage: number of distinct patterns to emit scales with fluidity
    coverage = max(3, min(len(_ANIM_PATTERNS), int(len(_ANIM_PATTERNS) * fluid / 10)))
    # Variants: at high fluidity we emit multiple tuned variants per pattern
    variants = max(1, min(4, 1 + fluid // 3))
    out: dict = {}
    idx = 0
    for (name, desc) in _ANIM_PATTERNS[:coverage]:
        for v in range(variants):
            idx += 1
            fname = f"animations/{name}_v{v+1}.ts"
            out[fname] = _gen_animation_pattern_file(name, desc, t, g, profile, fluid, idx)
    # Add an index file that re-exports everything
    exports = "\n".join([f"export * from './{p[0]}_v1';" for p in _ANIM_PATTERNS[:coverage]])
    out["animations/index.ts"] = f"""// ═══ {t} — Animation Library Index ═══
// Generated at animation_fluidity={fluid}/10, style='{style}'.
// {len(out)} pattern files exported.
{exports}
"""

    # ★ 2026-02 — 31 animation techniques as reference docs. Always emitted
    # whenever fluidity > 0 so the team has the vocabulary in the repo.
    for (tname, desc) in _ANIM_TECHNIQUES:
        out[f"animation_techniques/{tname}.md"] = (
            f"# Technique — {tname.replace('_',' ').title()}\n\n"
            f"> {desc}\n\n"
            f"## When to use in **{t}** ({g})\n"
            f"Use `{tname}` when you need to achieve the above effect. Typical\n"
            f"integration points: character controller, combat feedback, UI motion.\n\n"
            f"## Integration checklist\n"
            f"- [ ] Define bones / blendshapes required.\n"
            f"- [ ] Wire to input / state machine.\n"
            f"- [ ] Profile per-frame cost; apply LOD if > 0.5 ms.\n"
            f"- [ ] Test on min-spec device.\n"
            f"- [ ] Layer masks (upper body vs lower body)?\n"
        )
    out["animation_techniques/INDEX.md"] = (
        f"# {t} — 31 Animation Techniques\n\n"
        f"Curated reference of the motion techniques every animator on\n"
        f"this project should recognise. One file per technique.\n\n"
        + "\n".join([f"- `{n}.md` — {d}" for (n, d) in _ANIM_TECHNIQUES])
    )

    # ★ 2026-02 — Locomotion pack (walk/run/sprint/jump/crouch/slide/...).
    # Controlled by `locomotion_depth` (0..10) and `locomotion_style`.
    try:
        out.update(_phase_locomotion_pack(build, t, g))
    except Exception as _lerr:
        print(f"[GALAXY] locomotion pack skipped: {_lerr}")

    return out


# ═══════════════════════════════════════════════════════════════════════
# ★ LOCOMOTION PACK (2026-02) — slider-scaled movement system output.
# locomotion_depth 0 → no files; 10 → every verb including slide, wall-run,
# vault, mantle, ledge-grab, cover, climb, swim, swim_fast, dodge_roll,
# dive, backstep, mount, dismount, parachute, zipline, grappling_hook.
# locomotion_style in {basic, tactical, parkour, als, gunplay, melee}
# changes the per-verb tuning (sprint_speed, crouch_speed, jump_height).
# ═══════════════════════════════════════════════════════════════════════
_LOCOMOTION_VERBS = [
    ("walk",            "Base bipedal walk; blend by input magnitude."),
    ("run",             "Transition at 0.5 input mag; reusable for strafing."),
    ("sprint",          "Max sustainable ground speed; FOV nudge optional."),
    ("jump",            "Ground jump; variable height by button hold."),
    ("crouch",          "Crouch walk + stealth move-speed modifier."),
    ("slide",           "Momentum slide from sprint+crouch; exits into crouch or jump."),
    ("dodge_roll",      "Short-distance i-frame roll (8-frame invuln)."),
    ("dash",            "Instant burst toward input direction."),
    ("wall_run",        "Parkour: run along vertical wall for N seconds."),
    ("wall_jump",       "Bounce off wall into new direction + height."),
    ("vault",           "Hurdle low obstacles without breaking momentum."),
    ("mantle",          "Climb over medium ledges; hand-plant animation."),
    ("ledge_grab",      "Catch ledge during falling jump; shimmy left/right."),
    ("climb",           "Hand-over-hand vertical climb surface."),
    ("cover_enter",     "Snap to cover surface; crouch or stand variants."),
    ("cover_peek",      "Lean peek from cover; drives aim offset."),
    ("cover_exit",      "Pop out of cover into sprint or roll."),
    ("swim",            "Surface swim; breath meter interaction."),
    ("swim_fast",       "Sprint-swim with reduced turn rate."),
    ("dive",            "Dive into water from ledge."),
    ("backstep",        "Fighting-game style backdash."),
    ("mount",           "Enter a vehicle/mount; context prompt."),
    ("dismount",        "Exit vehicle/mount; idle-matching pose."),
    ("parachute",       "Glide/parachute from height; slow descent."),
    ("zipline",         "Attach to zipline; auto-travel with input lean."),
    ("grappling_hook",  "Swing/pull toward target; momentum-preserving."),
    ("climb_ladder",    "Step-based ladder ascent/descent."),
    ("crawl",           "Prone movement for stealth sections."),
    ("sprint_slide",    "Dedicated sprint→slide chain with cooldown."),
    ("air_dash",        "Mid-jump reposition; consumes stamina."),
    ("double_jump",     "Second mid-air jump; unlock-gated."),
    ("land_recovery",   "Hard-landing settle animation; disables input 0.3s."),
]

_LOCOMOTION_STYLE_TUNING = {
    "basic":    {"walk_s":  3.0, "run_s": 5.0, "sprint_s": 7.0,  "jump_h": 1.2, "slide_frames": 0},
    "tactical": {"walk_s":  2.4, "run_s": 4.5, "sprint_s": 6.5,  "jump_h": 1.0, "slide_frames": 24},
    "parkour":  {"walk_s":  3.0, "run_s": 6.0, "sprint_s": 9.0,  "jump_h": 1.8, "slide_frames": 30},
    "als":      {"walk_s":  3.0, "run_s": 5.5, "sprint_s": 7.8,  "jump_h": 1.4, "slide_frames": 28},
    "gunplay":  {"walk_s":  2.2, "run_s": 4.2, "sprint_s": 6.2,  "jump_h": 1.1, "slide_frames": 22},
    "melee":    {"walk_s":  2.8, "run_s": 5.2, "sprint_s": 7.2,  "jump_h": 1.3, "slide_frames": 26},
}


def _phase_locomotion_pack(build: dict, t: str, g: str) -> dict:
    import json as _json
    depth = int(build.get("locomotion_depth", 5) or 0)
    if depth <= 0:
        return {}
    style = str(build.get("locomotion_style", "als")).lower()
    if style not in _LOCOMOTION_STYLE_TUNING:
        style = "als"
    tuning = _LOCOMOTION_STYLE_TUNING[style]
    # Coverage: pick first N verbs proportional to depth.
    cov = max(4, min(len(_LOCOMOTION_VERBS), int(len(_LOCOMOTION_VERBS) * depth / 10)))
    out: dict = {}

    for i, (verb, desc) in enumerate(_LOCOMOTION_VERBS[:cov], 1):
        out[f"locomotion/{verb}.ts"] = (
            f"// ═══ {t} — Locomotion verb: {verb} ═══\n"
            f"// {desc}\n"
            f"// Style: {style} | depth: {depth}/10\n"
            f"import {{ Animated, Easing }} from 'react-native';\n\n"
            f"export const {verb.upper()}_CONFIG = {_json.dumps({'verb': verb, 'style': style, **tuning}, indent=2)};\n\n"
            f"export interface {verb.title().replace('_','')}Input {{\n"
            f"  stamina: number;\n"
            f"  grounded: boolean;\n"
            f"  inputDir: [number, number];\n"
            f"}}\n\n"
            f"export function can_{verb}(ctx: {verb.title().replace('_','')}Input): boolean {{\n"
            f"  // Minimum stamina / ground-state requirements for '{verb}'.\n"
            f"  if (ctx.stamina < 0.1) return false;\n"
            f"  return {'ctx.grounded' if verb in ('walk','run','sprint','crouch','slide','dodge_roll','cover_enter','cover_peek','cover_exit','climb_ladder','crawl','sprint_slide') else 'true'};\n"
            f"}}\n\n"
            f"export function begin_{verb}(anim: Animated.Value): void {{\n"
            f"  Animated.timing(anim, {{ toValue: 1, duration: 240, easing: Easing.inOut(Easing.ease), useNativeDriver: true }}).start();\n"
            f"}}\n\n"
            f"export function end_{verb}(anim: Animated.Value): void {{\n"
            f"  Animated.timing(anim, {{ toValue: 0, duration: 180, easing: Easing.out(Easing.ease), useNativeDriver: true }}).start();\n"
            f"}}\n"
        )

    # State-machine glue so all verbs chain together.
    transitions = {
        "walk":         ["run", "crouch", "jump"],
        "run":          ["walk", "sprint", "jump", "dodge_roll"],
        "sprint":       ["run", "slide", "jump", "sprint_slide"],
        "crouch":       ["walk", "crawl", "slide"],
        "slide":        ["crouch", "jump", "run"],
        "jump":         ["walk", "land_recovery", "double_jump", "air_dash", "wall_jump", "ledge_grab"],
        "dodge_roll":   ["run", "walk"],
        "wall_run":     ["wall_jump", "jump", "land_recovery"],
        "vault":        ["run", "walk"],
        "mantle":       ["walk", "climb"],
        "ledge_grab":   ["climb", "jump", "land_recovery"],
        "climb":        ["mantle", "jump"],
        "cover_enter":  ["cover_peek", "cover_exit"],
        "cover_peek":   ["cover_enter", "cover_exit"],
        "cover_exit":   ["sprint", "dodge_roll"],
        "swim":         ["swim_fast", "dive"],
        "swim_fast":    ["swim"],
        "dive":         ["swim"],
        "sprint_slide": ["sprint", "jump", "crouch"],
        "air_dash":     ["jump", "land_recovery"],
        "double_jump":  ["air_dash", "land_recovery"],
        "land_recovery":["walk", "crouch"],
    }
    used_verbs = {v for (v, _) in _LOCOMOTION_VERBS[:cov]}
    filtered_trans = {k: [d for d in dests if d in used_verbs] for k, dests in transitions.items() if k in used_verbs}
    out["locomotion/state_machine.ts"] = (
        f"// ═══ {t} — Locomotion state machine ({style}, depth={depth}/10) ═══\n"
        f"// {len(used_verbs)} verbs in graph. Use `canTransition(from, to)`.\n"
        f"export const LOCOMOTION_TRANSITIONS: Record<string, string[]> = "
        f"{_json.dumps(filtered_trans, indent=2)};\n\n"
        f"export function canTransition(from: string, to: string): boolean {{\n"
        f"  return (LOCOMOTION_TRANSITIONS[from] || []).includes(to);\n"
        f"}}\n"
    )

    out["locomotion/tuning.ts"] = (
        f"// ═══ {t} — Locomotion tuning ({style}) ═══\n"
        f"export const LOCOMOTION_TUNING = {_json.dumps(tuning, indent=2)};\n"
        f"export const LOCOMOTION_STYLE = '{style}';\n"
        f"export const LOCOMOTION_DEPTH = {depth};\n"
    )

    out["locomotion/README.md"] = (
        f"# Locomotion — {style} (depth {depth}/10)\n\n"
        f"{len(used_verbs)} movement verbs shipped for **{t}**:\n\n"
        + "\n".join([f"- `{v}` — {d}" for (v, d) in _LOCOMOTION_VERBS[:cov]])
        + f"\n\n## Advanced Locomotion System (ALS)\n"
        f"Style `{style}` wires the following extras:\n"
        f"- Predicted landing spots (toggle by `can_jump`).\n"
        f"- Dynamic step-over on 30 cm or lower obstacles.\n"
        f"- Context-sensitive slide from sprint (frames: {tuning['slide_frames']}).\n"
        f"- Walk speed {tuning['walk_s']} m/s / run {tuning['run_s']} / sprint {tuning['sprint_s']}.\n"
        f"- Jump peak height {tuning['jump_h']} m.\n"
    )
    return out


# ═══════════════════════════════════════════════════════════════════════
# ★ STORY & STYLE PACK (2026-02) — every questionnaire slider now visibly
# modifies the generated file tree. 9 separate folders get populated:
#   storyline/, tone/, pace/, difficulty/, perspective/, combat/,
#   progression/, visual_style/, audio/
# Each file is a real design doc / runtime config the game can import.
# ═══════════════════════════════════════════════════════════════════════
_STORYLINE_BEATS = {
    "heroic":        ["Call to Adventure", "Refusal", "Meeting the Mentor", "Crossing the Threshold", "Trials", "Revelation", "Final Boss", "Return Home"],
    "tragedy":       ["Normal World", "Fatal Flaw Revealed", "Hubris Climb", "Reversal", "Recognition", "Catastrophe", "Lament", "Aftermath"],
    "mystery":       ["The Incident", "The Investigator Enters", "Clue Chain", "Red Herring", "Suspect Parade", "Midpoint Twist", "Confrontation", "Revelation"],
    "redemption":    ["The Fall", "Rock Bottom", "A Helping Hand", "Atonement Task", "Doubt", "Sacrifice", "Forgiveness", "Rebirth"],
    "coming_of_age": ["Innocence", "First Loss", "New Peer Group", "Rite of Passage", "Identity Crisis", "Mentor's Lesson", "Choice", "Adulthood"],
    "comedy":        ["Status Quo", "The Absurd Arrives", "Escalation", "Misunderstanding", "Farcical Climax", "The Chase", "Resolution", "Return with Joke"],
    "cosmic_horror": ["Mundane Routine", "Anomaly", "Investigation", "Forbidden Knowledge", "Boundary Failing", "Cosmic Reveal", "Futility", "Cold Aftermath"],
}
_TONE_PALETTES = {
    "heroic":       {"primary": "#F59E0B", "secondary": "#3B82F6", "mood": "triumphant"},
    "dark":         {"primary": "#111827", "secondary": "#991B1B", "mood": "oppressive"},
    "humorous":     {"primary": "#FBBF24", "secondary": "#EC4899", "mood": "buoyant"},
    "melancholic":  {"primary": "#334155", "secondary": "#94A3B8", "mood": "wistful"},
    "epic":         {"primary": "#7C3AED", "secondary": "#F59E0B", "mood": "monumental"},
    "cozy":         {"primary": "#F3E8FF", "secondary": "#A78BFA", "mood": "warm"},
    "unsettling":   {"primary": "#1F2937", "secondary": "#DC2626", "mood": "uncanny"},
}
_PACE_PROFILES = {
    "slow_burn":      {"encounters_per_hr": 4,  "rest_ratio": 0.6, "dialogue_weight": 0.7},
    "standard":       {"encounters_per_hr": 8,  "rest_ratio": 0.4, "dialogue_weight": 0.5},
    "action_packed":  {"encounters_per_hr": 16, "rest_ratio": 0.2, "dialogue_weight": 0.3},
    "breakneck":      {"encounters_per_hr": 28, "rest_ratio": 0.1, "dialogue_weight": 0.15},
}
_DIFFICULTY_CURVES = {
    "gentle":     [1.0, 1.03, 1.06, 1.10, 1.14, 1.18, 1.22, 1.27, 1.32, 1.38],
    "steady":     [1.0, 1.08, 1.17, 1.28, 1.40, 1.54, 1.70, 1.87, 2.05, 2.25],
    "adaptive":   [1.0, 1.10, 1.22, 1.36, 1.52, 1.70, 1.88, 2.06, 2.24, 2.42],  # runtime-tuned
    "punishing":  [1.0, 1.18, 1.40, 1.66, 1.96, 2.30, 2.68, 3.10, 3.56, 4.06],
}
_PERSPECTIVE_RIG = {
    "first_person":  {"fov": 90, "cam_height_m": 1.7, "input": "mouse_wasd"},
    "third_person":  {"fov": 60, "cam_distance_m": 4.5, "input": "gamepad"},
    "isometric":     {"angle_deg": 30, "tile_size_px": 64, "input": "click_to_move"},
    "top_down":      {"angle_deg": 90, "input": "gamepad"},
    "side_scroll":   {"depth": "2d", "input": "gamepad"},
    "vr":            {"fov": 110, "input": "motion_controllers", "locomotion": "teleport+smooth"},
}
_COMBAT_RULES = {
    "realtime":    {"tick_hz": 60, "blocking": "directional", "stamina": True},
    "turn_based":  {"atb": False, "initiative": "d20+speed", "stamina": False},
    "action_rpg":  {"tick_hz": 60, "combo_windows_ms": [180, 240, 320], "stamina": True},
    "rhythm":      {"bpm_range": [90, 180], "hit_window_ms": 80},
    "tactical":    {"grid": "square", "action_points": 4, "cover": True},
    "none":        {"system": "narrative_only"},
}
_VISUAL_STYLE_SPEC = {
    "photoreal":      {"shading": "PBR", "lod_levels": 5, "texture_budget_mb": 512, "ssao": True, "bloom": True},
    "cel_shaded":     {"shading": "toon", "outline_px": 2, "palette_lock": True},
    "pixel_art":      {"resolution_px": 240, "palette_size": 32, "dither": True},
    "low_poly":       {"tri_budget": 5000, "flat_shade": True},
    "voxel":          {"voxel_size_cm": 10, "ambient_occlusion": True},
    "hand_painted":   {"shading": "custom", "brushstroke_texture": True, "warm_palette": True},
    "anime":          {"shading": "toon", "speed_lines": True, "rim_light": True},
}
_AUDIO_MOOD_SPEC = {
    "orchestral":  {"instruments": ["strings", "brass", "woodwinds", "percussion"], "tempo_bpm": 90, "key": "D_minor"},
    "synthwave":   {"instruments": ["analog_synth", "gated_drums", "arpeggiator"], "tempo_bpm": 115, "key": "A_minor"},
    "ambient":     {"instruments": ["pads", "drones", "field_rec"], "tempo_bpm": 60, "key": "F_major"},
    "chiptune":    {"instruments": ["square", "triangle", "noise", "sawtooth"], "tempo_bpm": 135, "key": "C_major"},
    "rock":        {"instruments": ["electric_guitar", "bass", "drums"], "tempo_bpm": 120, "key": "E_minor"},
    "folk":        {"instruments": ["acoustic_guitar", "fiddle", "harp", "flute"], "tempo_bpm": 95, "key": "G_major"},
    "silent":      {"instruments": [], "tempo_bpm": 0, "use_diegetic_sfx_only": True},
}


def _phase_story_style_pack(build: dict, t: str, g: str) -> dict:
    """Emit files reflecting every Story & Style slider value. This is how
    each questionnaire choice visibly modifies the generated file tree."""
    import json as _json
    out: dict = {}

    storyline = str(build.get("storyline_style", "heroic")).lower()
    tone = str(build.get("game_tone", "epic")).lower()
    pace = str(build.get("game_pace", "standard")).lower()
    diff = str(build.get("difficulty_curve", "steady")).lower()
    persp = str(build.get("perspective", "third_person")).lower()
    combat = str(build.get("combat_style", "action_rpg")).lower()
    prog = str(build.get("progression_type", "open_world")).lower()
    visual = str(build.get("visual_style", "hand_painted")).lower()
    audio = str(build.get("audio_mood", "orchestral")).lower()

    # Storyline outline (one file per beat → 8 files)
    beats = _STORYLINE_BEATS.get(storyline, _STORYLINE_BEATS["heroic"])
    for i, beat in enumerate(beats, 1):
        slug = beat.lower().replace(" ", "_").replace("'", "")
        out[f"storyline/{i:02d}_{slug}.md"] = (
            f"# {t} — Act {i}: {beat}\n\n"
            f"Archetype: **{storyline}**. Tone: **{tone}**. Genre: **{g}**.\n\n"
            f"## Purpose\n"
            f"This beat anchors the player in the **{storyline.replace('_',' ')}** arc. "
            f"Expected play-time: {10 + 8*i} minutes for the critical path.\n\n"
            f"## Scene brief\n"
            f"- POV: {persp.replace('_', '-')}\n"
            f"- Pace: {pace.replace('_', ' ')}\n"
            f"- Required NPCs: {max(1, i // 2)}\n"
            f"- Music cue: {audio}, dynamic {_AUDIO_MOOD_SPEC.get(audio, {}).get('key', 'D_minor')}\n\n"
            f"## Fail / Branch hooks\n"
            f"- On fail: fallback to beat {max(1, i-1)} with 'bruised' flag.\n"
            f"- Branch: if player has `mentor_saved` flag, unlock side scene `{slug}_alt`.\n"
        )
    out["storyline/README.md"] = (
        f"# Storyline — {storyline.replace('_',' ').title()}\n\n"
        f"Archetype-driven beat structure generated for **{t}**.\n"
        f"Tone: {tone} | Pace: {pace} | Difficulty: {diff}\n\n"
        f"Files in this folder correspond to the critical beats that must\n"
        f"fire in order. Use the runtime hook `useStoryBeat(n)` to advance.\n"
    )

    # Tone palette + UI theme
    palette = _TONE_PALETTES.get(tone, _TONE_PALETTES["epic"])
    out["tone/palette.ts"] = (
        f"// ═══ {t} — Tone palette ({tone}) ═══\n"
        f"export const TONE_PALETTE = {_json.dumps(palette, indent=2)};\n"
        f"export const TONE_MOOD = '{palette['mood']}';\n"
    )
    out["tone/writing_guide.md"] = (
        f"# Writing guide — {tone}\n\n"
        f"All dialogue, item descriptions, and barks should land on a **{palette['mood']}** register.\n"
        f"- Sentence length: {'short' if tone in ('dark', 'unsettling', 'humorous') else 'medium-to-long'}\n"
        f"- Humor: {'frequent' if tone == 'humorous' else 'absent' if tone in ('dark', 'melancholic', 'unsettling') else 'sparing'}\n"
        f"- Metaphor density: {'high' if tone in ('epic', 'melancholic', 'cosmic_horror') else 'moderate'}\n"
    )

    # Pace config
    pace_cfg = _PACE_PROFILES.get(pace, _PACE_PROFILES["standard"])
    out["pace/pace_config.ts"] = (
        f"// ═══ {t} — Pace config ({pace}) ═══\n"
        f"export const PACE = {_json.dumps(pace_cfg, indent=2)};\n"
        f"export const PACE_LABEL = '{pace}';\n"
    )

    # Difficulty curve (one file + level-by-level scalars)
    curve = _DIFFICULTY_CURVES.get(diff, _DIFFICULTY_CURVES["steady"])
    out["difficulty/curve.ts"] = (
        f"// ═══ {t} — Difficulty curve ({diff}) ═══\n"
        f"// Multiplier applied to enemy HP + damage at each level 1..10.\n"
        f"export const DIFFICULTY_CURVE: number[] = {_json.dumps(curve)};\n"
        f"export const DIFFICULTY_NAME = '{diff}';\n"
        f"export function difficultyFor(level: number) {{ return DIFFICULTY_CURVE[Math.min(9, Math.max(0, level - 1))]; }}\n"
    )
    # Enemy-stats table per level (10 files → visible granularity)
    for lvl, mult in enumerate(curve, 1):
        out[f"difficulty/enemy_stats_L{lvl:02d}.json"] = _json.dumps({
            "level": lvl, "multiplier": mult,
            "enemy_hp_base": int(50 * mult), "enemy_dmg_base": int(8 * mult),
            "xp_reward": int(25 * mult), "gold_reward": int(12 * mult),
        }, indent=2)

    # Perspective rig
    rig = _PERSPECTIVE_RIG.get(persp, _PERSPECTIVE_RIG["third_person"])
    out["perspective/camera_rig.ts"] = (
        f"// ═══ {t} — Camera / input rig ({persp}) ═══\n"
        f"export const CAMERA_RIG = {_json.dumps(rig, indent=2)};\n"
        f"export const PERSPECTIVE = '{persp}';\n"
    )

    # Combat rules
    combat_cfg = _COMBAT_RULES.get(combat, _COMBAT_RULES["action_rpg"])
    out["combat/rules.ts"] = (
        f"// ═══ {t} — Combat rules ({combat}) ═══\n"
        f"export const COMBAT_RULES = {_json.dumps(combat_cfg, indent=2)};\n"
        f"export const COMBAT_STYLE = '{combat}';\n"
    )
    out["combat/README.md"] = (
        f"# Combat — {combat.replace('_',' ')}\n\n"
        f"This build uses **{combat.replace('_',' ')}** combat. Tuning knobs:\n"
        + "\n".join([f"- `{k}` = `{v}`" for k, v in combat_cfg.items()])
    )

    # Progression map
    prog_structure = {
        "linear":         {"gates": "sequential", "backtracking": False},
        "open_world":     {"gates": "level-keys", "backtracking": True, "regions": 8},
        "metroidvania":   {"gates": "ability-keys", "backtracking": True, "regions": 6},
        "roguelike":      {"gates": "runs", "permadeath": True, "meta_progression": True},
        "sandbox":        {"gates": "self-directed", "objectives": "emergent"},
        "hub_and_spoke":  {"gates": "hub-unlock", "levels_per_hub": 5},
    }.get(prog, {"gates": "level-keys"})
    out["progression/world_structure.ts"] = (
        f"// ═══ {t} — World structure ({prog}) ═══\n"
        f"export const PROGRESSION = {_json.dumps(prog_structure, indent=2)};\n"
        f"export const PROGRESSION_TYPE = '{prog}';\n"
    )

    # Visual style
    vspec = _VISUAL_STYLE_SPEC.get(visual, _VISUAL_STYLE_SPEC["hand_painted"])
    out["visual_style/style_guide.md"] = (
        f"# Visual style — {visual.replace('_', ' ')}\n\n"
        f"All art must be produced to these specs:\n\n"
        + "\n".join([f"- **{k}**: `{v}`" for k, v in vspec.items()])
    )
    out["visual_style/renderer_config.ts"] = (
        f"// ═══ {t} — Renderer config ({visual}) ═══\n"
        f"export const VISUAL_SPEC = {_json.dumps(vspec, indent=2)};\n"
        f"export const VISUAL_STYLE = '{visual}';\n"
    )

    # Audio mood + starter cue list
    aspec = _AUDIO_MOOD_SPEC.get(audio, _AUDIO_MOOD_SPEC["orchestral"])
    out["audio/mood_config.ts"] = (
        f"// ═══ {t} — Audio mood ({audio}) ═══\n"
        f"export const AUDIO_MOOD = {_json.dumps(aspec, indent=2)};\n"
        f"export const MOOD_LABEL = '{audio}';\n"
    )
    for i, scene in enumerate(["menu", "overworld", "combat", "boss", "victory", "defeat"], 1):
        out[f"audio/cue_{i:02d}_{scene}.json"] = _json.dumps({
            "cue": scene,
            "mood": audio,
            "key": aspec.get("key", "D_minor"),
            "tempo_bpm": aspec.get("tempo_bpm", 90),
            "instruments": aspec.get("instruments", []),
            "loop": scene in ("menu", "overworld"),
        }, indent=2)

    # Top-level combined manifest so tooling can see every pick in one shot
    out["design/STYLE_MANIFEST.json"] = _json.dumps({
        "storyline_style": storyline, "game_tone": tone, "game_pace": pace,
        "difficulty_curve": diff, "perspective": persp, "combat_style": combat,
        "visual_style": visual, "progression_type": prog, "audio_mood": audio,
        "title": t, "genre": g,
    }, indent=2)

    return out


# ═══════════════════════════════════════════════════════════════════════
# PHASE 14: POLISH & JUICE — UX, accessibility, localization, feel
# ═══════════════════════════════════════════════════════════════════════
def _phase_polish(build, t, g):
    files = {}
    polish_components = [
        ("ScreenTransition", "Screen transitions with slide, fade, dissolve, iris, custom shaders"),
        ("ToastNotification", "Toast notifications with queue, priority, icons, actions, auto-dismiss"),
        ("ContextMenu", "Context menu with nested items, icons, shortcuts, adaptive positioning"),
        ("ParticleOverlay", "Screen particle effects for levelup, achievement, rare drop, celebration"),
        ("AccessibilityManager", "Accessibility with colorblind modes, text scaling, audio cues, haptics"),
        ("TutorialOverlay", "Tutorial with highlights, tooltips, step-by-step, skip, adaptive pacing"),
        ("EmoteWheel", "Emote wheel with categories, favorites, preview, combo emotes, cooldown"),
        ("AchievementPopup", "Achievement popup with tier, progress, chain, rare animation, sound"),
    ]
    for name, desc in polish_components:
        files[f"components/{name}.tsx"] = _gen_component_aaa(name, desc, t, g)
    # Hooks
    files["hooks/useGameLoop.ts"] = _gen_game_loop_hook(t, g)
    files["hooks/useInput.ts"] = _gen_input_hook(t, g)
    files["hooks/useAudio.ts"] = _gen_audio_hook(t, g)
    files["hooks/useNetwork.ts"] = _gen_network_hook(t, g)
    files["hooks/useAnimation.ts"] = _gen_animation_hook(t, g)
    files["hooks/useCamera.ts"] = _gen_camera_hook(t, g)
    files["hooks/usePhysics.ts"] = _gen_physics_hook(t, g)
    files["hooks/useInventory.ts"] = _gen_inventory_hook(t, g)
    # ★ 2026-02 — Animations pack that SCALES with the slider.
    # animation_fluidity ranges 0..10; we emit count files like
    # animations/pack_<style>_<idx>.ts with ready-to-wire motion patterns.
    # At fluidity 0 we emit nothing; at 10 we emit 120 files.
    try:
        files.update(_phase_animations_pack(build, t, g))
    except Exception as _apack_err:
        print(f"[GALAXY] animations pack skipped: {_apack_err}")
    # Polish screens
    polish_screens = [
        "AccessibilityScreen", "ControlsScreen", "AudioSettingsScreen",
        "GraphicsSettingsScreen", "CreditsScreen", "PatchNotesScreen",
    ]
    for s in polish_screens:
        files[f"screens/{s}.tsx"] = _gen_screen_aaa(s, t, g)
    build["_all_screens"] = build.get("_all_screens", []) + polish_screens
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE 15: TESTING & QA — Test suites, validation, integration
# ═══════════════════════════════════════════════════════════════════════
def _phase_testing(build, t, g):
    files = {}
    tests = [
        "combatEngine", "inventoryManager", "questEngine", "economySystem",
        "aiDirector", "worldGenerator", "craftingSystem", "progressionEngine",
        "networkManager", "audioManager", "particleManager", "saveManager",
        "weatherSystem", "dialogueSystem", "lootTableManager", "guildManager",
        "pvpManager", "auctionHouse", "petSystem", "mountSystem",
        "fishingSystem", "reputationSystem", "eventManager", "battlePassManager",
        "ecsFramework", "navMeshSystem", "renderPipeline", "physicsEngine",
        "matchmakingEngine", "destructionSystem", "emotionEngine", "timeManipulation",
    ]
    for name in tests:
        files[f"tests/{name}.test.ts"] = _gen_test_file(name, t, g)
    # Middleware
    middleware = [
        ("authMiddleware", "Auth with token validation, refresh, role checks, CORS, rate limiting"),
        ("loggingMiddleware", "Structured logging with timing, sanitization, correlation IDs"),
        ("errorMiddleware", "Error handling with categorization, retry, user-friendly messages"),
        ("validationMiddleware", "Input validation with schema, sanitization, type coercion"),
        ("metricsMiddleware", "Request metrics with latency, throughput, error rates, status codes"),
    ]
    for name, desc in middleware:
        files[f"middleware/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE 16: FINAL COMPILATION — Layout, build manifests, assembly
# ═══════════════════════════════════════════════════════════════════════
def _phase_compilation(build, t, g):
    files = {}
    all_screens = build.get("_all_screens", ["GameScreen"])
    files["app/_layout.tsx"] = _gen_layout_code(t, g, all_screens)

    # ═══ CRITICAL: Generate placeholder asset files for EAS builds ═══
    # 1x1 transparent PNG (minimal valid PNG)
    import base64
    _PLACEHOLDER_PNG = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    # Write as binary-safe base64 strings for later zip writing
    files["assets/icon.png"] = "__BINARY_BASE64__" + base64.b64encode(_PLACEHOLDER_PNG).decode()
    files["assets/splash.png"] = "__BINARY_BASE64__" + base64.b64encode(_PLACEHOLDER_PNG).decode()
    files["assets/adaptive-icon.png"] = "__BINARY_BASE64__" + base64.b64encode(_PLACEHOLDER_PNG).decode()
    files["assets/favicon.png"] = "__BINARY_BASE64__" + base64.b64encode(_PLACEHOLDER_PNG).decode()

    # Services layer
    services = [
        ("authService", "Authentication with JWT, OAuth, session, 2FA, rate limiting, RBAC"),
        ("storageService", "Persistent storage with encryption, migration, backup, compression"),
        ("logService", "Structured logging with levels, rotation, remote transport, search"),
        ("metricsService", "Metrics collection with counters, gauges, histograms, percentiles"),
        ("schedulerService", "Task scheduler with cron, intervals, priority queue, retry"),
        ("rateLimiter", "Rate limiting with sliding window, token bucket, distributed, backoff"),
        ("healthCheck", "Health monitoring with dependency checks, degraded states, probes"),
    ]
    for name, desc in services:
        files[f"services/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    # Final data
    extra_data = [
        ("factions_database", "All factions with ranks, rewards, exclusive items, diplomacy, history, leaders"),
        ("mounts_database", "Mount collection with stats, abilities, sources, customization"),
        ("pets_database", "Pet collection with abilities, evolution trees, breeding"),
        ("cosmetics_database", "Cosmetics with previews, sets, seasonal exclusives, dye channels"),
        ("seasonal_events_database", "Seasonal event configs with dates, quests, items, cosmetics"),
    ]
    for name, desc in extra_data:
        files[f"data/{name}.ts"] = _gen_data_file(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: SYSTEM DESIGN — Core system architecture files
# ═══════════════════════════════════════════════════════════════════════
def _phase_system(build, t, g):
    files = {}
    systems = [
        ("systemKernel", "Core system kernel with process scheduling, memory management, resource allocation, signal handling"),
        ("eventDispatcher", "System event dispatcher with priority queues, async handlers, bubbling, capture, middleware hooks"),
        ("taskScheduler", "Multi-threaded task scheduler with worker pools, load balancing, priority queues, deadlock detection"),
        ("resourceManager", "System resource manager with pooling, lifecycle management, garbage collection, leak detection"),
        ("stateManager", "Global state management with snapshots, rollback, diff tracking, middleware, observers"),
        ("pluginSystem", "Plugin architecture with hot-loading, dependency resolution, sandboxing, API versioning"),
        ("fileSystemLayer", "Virtual file system with caching, streaming, compression, encryption, virtual mounts"),
        ("debugConsole", "Developer debug console with runtime inspection, hot reload, profiling, command registry"),
    ]
    for name, desc in systems:
        files[f"system/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    files["system/SystemBootstrap.ts"] = _gen_logic_aaa("SystemBootstrap", "Boot sequence orchestrator with dependency init, health checks, graceful shutdown, recovery", t, g)
    files["docs/SYSTEM_ARCHITECTURE.md"] = f"# {t} — System Architecture\n\n## Core Systems\n" + "\n".join(f"- **{n}**: {d}" for n, d in systems) + "\n\n## Boot Order\n1. Kernel → 2. Resource Manager → 3. Event Dispatcher → 4. State Manager → 5. Plugin System → 6. File System → 7. Task Scheduler → 8. Debug Console\n"
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: FRAMEWORK SELECTION — Framework config, adapters, abstractions
# ═══════════════════════════════════════════════════════════════════════
def _phase_framework(build, t, g):
    files = {}
    frameworks = [
        ("frameworkCore", "Core framework with dependency injection, lifecycle hooks, module system, configuration"),
        ("renderFramework", "Rendering framework adapter with scene graph, draw calls, batching, culling, LOD"),
        ("inputFramework", "Input framework with device abstraction, action maps, rebinding, gesture recognition"),
        ("audioFramework", "Audio framework with bus routing, effects chain, spatial audio, streaming, format support"),
        ("uiFramework", "UI framework with layout engine, styling, themes, animations, accessibility, focus management"),
        ("testFramework", "Test framework with unit/integration/e2e, mocking, coverage, snapshot, benchmark"),
        ("buildFramework", "Build pipeline framework with asset processing, bundling, optimization, tree shaking"),
    ]
    for name, desc in frameworks:
        files[f"framework/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    files["framework/FrameworkRegistry.ts"] = _gen_logic_aaa("FrameworkRegistry", "Framework registry with version management, compatibility matrix, migration helpers, feature detection", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: ENGINE CORE — Core engine systems, ECS, rendering pipeline
# ═══════════════════════════════════════════════════════════════════════
def _phase_engine(build, t, g):
    files = {}
    engine_parts = [
        ("ecsEngine", "Entity Component System with archetype storage, system scheduling, query optimization, prefabs"),
        ("renderPipeline", "Render pipeline with forward/deferred paths, shadow pass, post-processing stack, GPU culling"),
        ("sceneGraph", "Scene graph with spatial indexing, frustum culling, octree, BVH, instancing, streaming"),
        ("assetPipeline", "Asset pipeline with import, processing, compression, caching, hot reload, format conversion"),
        ("animationEngine", "Animation engine with state machines, blend trees, IK, ragdoll, morph targets, timeline"),
        ("audioEngine", "Audio engine with 3D spatialization, reverb zones, occlusion, DSP effects, streaming decode"),
        ("scriptingEngine", "Scripting engine with VM, bytecode, hot reload, debugging, profiling, sandboxing"),
        ("memoryAllocator", "Custom memory allocator with pool, stack, frame, buddy system, tracking, defragmentation"),
        ("jobSystem", "Job system with fiber-based scheduling, work stealing, dependency graph, parallel-for"),
        ("profilingEngine", "Profiler with CPU/GPU/memory, frame analysis, timeline, markers, remote debugging"),
    ]
    for name, desc in engine_parts:
        files[f"engine/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    files["engine/EngineConfig.ts"] = _gen_logic_aaa("EngineConfig", "Engine configuration with platform detection, capability querying, quality presets, dynamic scaling", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: ARCHITECTURE BLUEPRINT — Design patterns, modules, interfaces
# ═══════════════════════════════════════════════════════════════════════
def _phase_architecture(build, t, g):
    files = {}
    arch_parts = [
        ("moduleLoader", "Dynamic module loader with lazy loading, circular detection, tree shaking, code splitting"),
        ("serviceLocator", "Service locator with singleton/transient/scoped lifetimes, auto-wiring, mocking support"),
        ("messageQueue", "Internal message queue with pub/sub, request/reply, dead letters, backpressure, batching"),
        ("pipelineOrchestrator", "Pipeline orchestrator with stages, filters, transformations, error handling, retry"),
        ("repositoryPattern", "Data repository with CRUD, query builder, caching, pagination, transactions, migration"),
        ("middlewareChain", "Middleware chain with composition, error boundary, logging, timing, validation"),
        ("adapterLayer", "Adapter layer with platform abstraction, feature detection, polyfills, fallbacks"),
        ("observerHub", "Observer hub with typed events, weak references, auto-cleanup, batch notifications"),
    ]
    for name, desc in arch_parts:
        files[f"architecture/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    # Architecture docs
    files["docs/ARCHITECTURE_PATTERNS.md"] = f"# {t} — Architecture Patterns\n\n" + "\n".join(f"## {n}\n{d}\n" for n, d in arch_parts) + "\n## Design Principles\n- SOLID principles\n- Composition over inheritance\n- Dependency inversion\n- Event-driven architecture\n- CQRS for complex domains\n"
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: LORE & MYTHOLOGY — World-building, history, factions
# ═══════════════════════════════════════════════════════════════════════
def _phase_lore(build, t, g):
    files = {}
    lore_data = [
        ("world_history_database", "Complete world history spanning eras, cataclysms, golden ages, dark periods, prophecies"),
        ("factions_lore_database", "Faction lore with origins, beliefs, conflicts, alliances, heroes, betrayals, civil wars"),
        ("mythology_database", "Creation myths, pantheons, divine conflicts, mortal champions, sacred artifacts"),
        ("legends_database", "Legendary heroes, villains, battles, lost cities, cursed items, prophecies"),
        ("language_database", "Constructed languages with grammars, scripts, common phrases, naming conventions"),
        ("timeline_database", "World timeline with epochs, key events, cause/effect chains, branching alternate histories"),
    ]
    for name, desc in lore_data:
        files[f"data/{name}.ts"] = _gen_data_file(name, desc, t, g)
    files["lore/LoreEngine.ts"] = _gen_logic_aaa("LoreEngine", "Dynamic lore engine with discovery tracking, codex unlocking, ambient storytelling, NPC knowledge", t, g)
    files["lore/CodexManager.ts"] = _gen_logic_aaa("CodexManager", "In-game codex with categories, search, bookmarks, progress tracking, illustrations, voice narration", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: GAMEPLAY SYSTEMS — Core gameplay loops, progression, economy
# ═══════════════════════════════════════════════════════════════════════
def _phase_gameplay(build, t, g):
    files = {}
    gameplay = [
        ("questEngine", "Quest engine with chains, branches, dynamic objectives, timers, fail states, party quests"),
        ("craftingSystem", "Crafting with recipes, discovery, quality tiers, station requirements, experimentation"),
        ("reputationSystem", "Reputation system with factions, tiers, rewards, decay, exclusive content, diplomacy"),
        ("achievementSystem", "Achievement system with tracking, chains, secret achievements, point rewards, badges"),
        ("dailyChallenge", "Daily challenge system with rotation, difficulty scaling, streak bonuses, leaderboards"),
        ("seasonalContent", "Seasonal content with events, limited items, battle pass, holiday themes, world changes"),
        ("guildSystem", "Guild system with ranks, permissions, bank, quests, raids, wars, alliances, perks"),
        ("auctionHouse", "Player auction house with bidding, buyout, search, history, taxes, anti-manipulation"),
    ]
    for name, desc in gameplay:
        files[f"gameplay/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: ENVIRONMENT & ECOLOGY — Biomes, wildlife, day/night, weather
# ═══════════════════════════════════════════════════════════════════════
def _phase_environment(build, t, g):
    files = {}
    env_systems = [
        ("biomeManager", "Biome management with transitions, layered vegetation, temperature, humidity, elevation"),
        ("weatherSystem", "Dynamic weather with precipitation, wind, storms, lightning, fog, seasonal patterns"),
        ("dayNightCycle", "Day/night cycle with sun/moon positioning, lighting transitions, NPC schedules, time dilation"),
        ("wildlifeEcosystem", "Wildlife ecosystem with food chains, breeding, migration, territorial behavior, extinction"),
        ("vegetationSystem", "Vegetation system with growth, seasons, interaction, harvesting, procedural placement"),
        ("waterSystem", "Water system with rivers, lakes, oceans, tides, currents, underwater zones, erosion"),
        ("ecologySimulation", "Ecology simulation with population dynamics, resource competition, biome evolution"),
    ]
    for name, desc in env_systems:
        files[f"environment/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    files["data/biome_definitions_database.ts"] = _gen_data_file("biome_definitions_database", "All biome definitions with flora, fauna, resources, hazards, ambient sounds", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: PLOT & INTRIGUE — Story arcs, conspiracies, political drama
# ═══════════════════════════════════════════════════════════════════════
def _phase_plot_intrigue(build, t, g):
    files = {}
    plot_systems = [
        ("plotEngine", "Plot engine with branching story arcs, consequence chains, character motivations, dramatic tension curves, climax timing"),
        ("intrigueManager", "Intrigue manager with conspiracy networks, secret alliances, betrayal triggers, double agents, trust mechanics"),
        ("politicalSystem", "Political system with factions, power struggles, elections, coups, territory control, diplomacy, treaties"),
        ("espionageSystem", "Espionage with spy networks, intelligence gathering, sabotage missions, counter-intelligence, dead drops"),
        ("rumorMill", "Rumor propagation with truth decay, misinformation, NPC gossip networks, reputation manipulation, propaganda"),
        ("plotTwistEngine", "Plot twist engine with foreshadowing detection, revelation timing, red herrings, subverted expectations, dramatic irony"),
        ("allianceSystem", "Alliance system with marriage politics, hostage exchanges, tribute, mutual defense pacts, trade agreements, betrayal paths"),
        ("courtIntrigue", "Court intrigue with noble houses, succession crises, poison plots, blackmail, scandal, favor trading"),
        ("warCampaign", "War campaign with strategic planning, siege mechanics, supply lines, morale, desertion, peace negotiations"),
        ("mysterySolver", "Mystery system with clue collection, deduction logic, red herrings, witness interviews, evidence chains, case files"),
    ]
    for name, desc in plot_systems:
        files[f"plot/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    files["data/plot_templates_database.ts"] = _gen_data_file("plot_templates_database", "Plot templates with story beats, character archetypes, conflict types, resolution patterns, pacing guides", t, g)
    files["data/intrigue_scenarios_database.ts"] = _gen_data_file("intrigue_scenarios_database", "Intrigue scenarios with conspiracies, betrayals, power plays, secret societies, hidden agendas", t, g)
    # ★ 2026-02 — Bolt the Story & Style pack onto this phase so every
    # questionnaire pick (storyline archetype, tone, pace, difficulty,
    # perspective, combat, progression, visual style, audio mood) emits
    # real files into the build tree. This runs once per build in batch 1.
    try:
        files.update(_phase_story_style_pack(build, t, g))
    except Exception as _spk_err:
        print(f"[GALAXY] story_style pack skipped: {_spk_err}")
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: VISUAL EFFECTS — Particle systems, post-processing, FX
# ═══════════════════════════════════════════════════════════════════════
def _phase_vfx(build, t, g):
    files = {}
    vfx_systems = [
        ("particleSystem", "GPU particle system with emitters, forces, collisions, sub-emitters, trails, ribbons"),
        ("decalSystem", "Decal system with projection, blending, pooling, atlas, fading, normal blending"),
        ("screenEffects", "Screen effects with chromatic aberration, film grain, scan lines, barrel distortion"),
        ("lightingEffects", "Dynamic lighting with area lights, IES profiles, light cookies, volumetric, caustics"),
        ("weatherVFX", "Weather VFX with rain streaks, snow accumulation, lightning, puddles, wet surfaces"),
        ("combatVFX", "Combat VFX with impact sparks, blood, magic effects, elemental auras, death dissolve"),
        ("environmentVFX", "Environment VFX with dust motes, fireflies, embers, leaves, fog, water splashes"),
    ]
    for name, desc in vfx_systems:
        files[f"vfx/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    vfx_shaders = [
        ("distortion_wave", "Screen distortion with radial waves, heat haze, shockwave, underwater warp"),
        ("magic_circle", "Magic circle with rotating glyphs, energy pulse, summoning effect, particle trails"),
        ("portal_vortex", "Portal effect with vortex swirl, dimensional tear, energy crackling, color shift"),
    ]
    for name, desc in vfx_shaders:
        files[f"shaders/{name}.glsl"] = _gen_shader_code(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: SOUND EFFECTS — SFX systems, foley, impact sounds
# ═══════════════════════════════════════════════════════════════════════
def _phase_sfx(build, t, g):
    files = {}
    sfx_systems = [
        ("sfxManager", "SFX manager with pooling, priority, 3D positioning, attenuation, occlusion, ducking"),
        ("footstepSystem", "Footstep system with surface detection, speed variation, material layers, wetness"),
        ("impactSFX", "Impact sound system with material pairing, velocity scaling, reverb, debris sounds"),
        ("ambientSFX", "Ambient SFX with zone-based layers, random triggers, day/night variation, weather"),
        ("uiSFX", "UI sound effects with button clicks, transitions, notifications, feedback, confirmations"),
        ("combatSFX", "Combat SFX with weapon swings, hit/block/parry, magic casting, death sounds, crowd"),
    ]
    for name, desc in sfx_systems:
        files[f"audio/sfx/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    files["data/sfx_library_database.ts"] = _gen_data_file("sfx_library_database", "SFX library with categories, variants, conditions, mixing rules, fallbacks", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: SOUND ENGINE — Audio pipeline, mixing, spatialization
# ═══════════════════════════════════════════════════════════════════════
def _phase_sound(build, t, g):
    files = {}
    sound = [
        ("audioMixer", "Audio mixer with bus hierarchy, sends, inserts, side-chain, automation, snapshots"),
        ("spatialAudio", "Spatial audio with HRTF, distance attenuation, doppler, reverb zones, propagation"),
        ("audioStreamer", "Audio streaming with buffer management, format decode, seamless looping, crossfade"),
        ("dspEffects", "DSP effects chain with EQ, compression, reverb, delay, chorus, distortion, limiter"),
        ("voiceManager", "Voice management with prioritization, stealing, ducking, virtual voices, instancing"),
        ("audioProfiler", "Audio profiler with CPU/memory tracking, voice count, bus meters, latency monitoring"),
    ]
    for name, desc in sound:
        files[f"audio/engine/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: MUSIC & SOUNDTRACK — Adaptive music, composition, layers
# ═══════════════════════════════════════════════════════════════════════
def _phase_music(build, t, g):
    files = {}
    music = [
        ("musicDirector", "Music director with context awareness, intensity tracking, transition rules, silence management"),
        ("adaptiveMusic", "Adaptive music with horizontal/vertical layers, stingers, crossfades, beat-synced transitions"),
        ("musicSequencer", "Music sequencer with pattern playback, instrument layers, tempo sync, measure-aligned changes"),
        ("combatMusic", "Combat music with threat escalation, boss themes, victory/defeat stings, phase transitions"),
        ("explorationMusic", "Exploration music with biome themes, discovery stings, ambient layers, time-of-day variation"),
        ("menuMusic", "Menu music with thematic layers, selection sounds, transition crescendos, idle variations"),
    ]
    for name, desc in music:
        files[f"audio/music/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    files["data/music_cue_database.ts"] = _gen_data_file("music_cue_database", "Music cues with triggers, layers, transitions, tempo, key, instrument sets", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: AMBIANCE & ATMOSPHERE — Environmental audio, mood, tension
# ═══════════════════════════════════════════════════════════════════════
def _phase_ambiance(build, t, g):
    files = {}
    ambiance = [
        ("ambianceEngine", "Ambiance engine with layered soundscapes, distance-based blending, transitions, weather integration"),
        ("moodSystem", "Mood system with tension curves, dynamic soundtrack mixing, lighting adaptation, NPC behavior"),
        ("environmentAudio", "Environmental audio with reverb mapping, material response, wind simulation, echo modeling"),
        ("reverbZoneManager", "Reverb zone manager with room modeling, transition blending, occlusion, early reflections"),
        ("tensionManager", "Tension manager with escalation curves, player proximity detection, audio/visual sync, jumpscares"),
    ]
    for name, desc in ambiance:
        files[f"audio/ambiance/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    files["data/ambiance_profiles_database.ts"] = _gen_data_file("ambiance_profiles_database", "Ambiance profiles per biome/zone with sound layers, mixing rules, time-of-day variation", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: CINEMATICS & CAMERA — Camera systems, cutscene framework
# ═══════════════════════════════════════════════════════════════════════
def _phase_cinematics(build, t, g):
    files = {}
    cinematics = [
        ("cameraSystem", "Camera system with modes (orbit, follow, free, fixed), transitions, constraints, shake"),
        ("cinematicDirector", "Cinematic director with timeline, keyframes, camera rails, focus pulls, letterbox"),
        ("replaySystem", "Replay system with recording, playback, camera angles, slow-mo, highlight detection"),
        ("photoMode", "Photo mode with free camera, filters, depth of field, poses, stickers, sharing"),
        ("screenShake", "Screen shake with trauma system, perlin noise, spring-damper, directional, decay curves"),
        ("cameraCollision", "Camera collision with volume testing, push-forward, smoothing, clip plane, occlusion fade"),
    ]
    for name, desc in cinematics:
        files[f"camera/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: CUTSCENES & DIALOGUE — Narrative delivery, voice, choices
# ═══════════════════════════════════════════════════════════════════════
def _phase_cutscenes(build, t, g):
    files = {}
    cutscenes = [
        ("cutscenePlayer", "Cutscene player with scripted sequences, camera control, actor choreography, skip handling"),
        ("dialogueEngine", "Dialogue engine with branching trees, conditions, variables, emotional tags, voice sync"),
        ("narrativeDirector", "Narrative director with story arcs, pacing, foreshadowing, dramatic irony, player impact"),
        ("subtitleSystem", "Subtitle system with localization, timing, speaker colors, positioning, accessibility"),
        ("voiceOverManager", "Voice-over manager with lip sync, emotion detection, interruption, queue management"),
        ("choiceSystem", "Choice system with consequences, delayed effects, reputation impact, moral alignment, branches"),
    ]
    for name, desc in cutscenes:
        files[f"narrative/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    files["data/dialogue_trees_database.ts"] = _gen_data_file("dialogue_trees_database", "Dialogue trees with NPC conversations, branching paths, conditions, emotion tags", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: TUTORIAL & ONBOARDING — Player guidance, tooltips, help
# ═══════════════════════════════════════════════════════════════════════
def _phase_tutorial(build, t, g):
    files = {}
    tutorial = [
        ("tutorialManager", "Tutorial manager with step sequences, skip detection, adaptive pacing, completion tracking"),
        ("tooltipSystem", "Tooltip system with context-aware hints, positioning, dismissal, frequency control"),
        ("onboardingFlow", "Onboarding flow with progressive disclosure, gated features, milestone celebrations"),
        ("hintSystem", "Dynamic hint system with player behavior analysis, frustration detection, adaptive help"),
        ("controlGuide", "Control guide with interactive overlays, button prompts, practice areas, rebind display"),
    ]
    for name, desc in tutorial:
        files[f"tutorial/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: MENU SYSTEM — Main menu, pause, HUD navigation
# ═══════════════════════════════════════════════════════════════════════
def _phase_menu(build, t, g):
    files = {}
    menus = [
        ("mainMenuController", "Main menu with animated background, button navigation, version display, news ticker"),
        ("pauseMenuController", "Pause menu with resume, settings, save/load, quit confirm, background blur"),
        ("hudNavigator", "HUD navigation with radial menus, quick access, context actions, drag-reorder"),
        ("inventoryUI", "Inventory UI with grid/list views, sorting, filtering, comparison, tooltips, drag-drop"),
        ("mapOverlay", "Map overlay with zoom, pan, markers, waypoints, fog of war, fast travel, legend"),
        ("journalUI", "Journal UI with quest log, bestiary, codex, notes, bookmarks, search, tabs"),
        ("socialMenuUI", "Social menu with friends, party, guild, chat, block, report, recent players"),
    ]
    for name, desc in menus:
        files[f"ui/menus/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    menu_screens = ["MainMenuScreen", "PauseMenuScreen", "SaveLoadScreen", "WorldMapScreen"]
    for s in menu_screens:
        files[f"screens/{s}.tsx"] = _gen_screen_aaa(s, t, g)
    build["_all_screens"] = build.get("_all_screens", []) + menu_screens
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: SETTINGS & CONFIG — User preferences, keybinds, accessibility
# ═══════════════════════════════════════════════════════════════════════
def _phase_settings(build, t, g):
    files = {}
    settings = [
        ("settingsManager", "Settings manager with categories, presets, per-profile, import/export, cloud sync"),
        ("keybindManager", "Keybind manager with action mapping, rebinding, conflict detection, gamepad support"),
        ("graphicsSettings", "Graphics settings with quality presets, individual toggles, resolution, VSync, FPS cap"),
        ("audioSettings", "Audio settings with master/music/sfx/voice sliders, device selection, spatial toggle"),
        ("accessibilitySettings", "Accessibility with colorblind modes, text size, screen reader, subtitles, input assist"),
        ("gameplaySettings", "Gameplay settings with difficulty, auto-aim, camera sensitivity, HUD customization"),
        ("localizationManager", "Localization with language selection, font swap, RTL support, pluralization, date/number format"),
    ]
    for name, desc in settings:
        files[f"settings/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    files["data/default_settings_database.ts"] = _gen_data_file("default_settings_database", "Default settings profiles with recommended values per platform and quality tier", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: BACKEND SYSTEMS — Server logic, API, database, auth
# ═══════════════════════════════════════════════════════════════════════
def _phase_backend(build, t, g):
    files = {}
    backend = [
        ("apiRouter", "API router with versioning, rate limiting, authentication, request validation, response shaping"),
        ("databaseService", "Database service with connection pooling, migration, seeding, query builder, transactions"),
        ("authenticationService", "Auth service with JWT, OAuth2, MFA, session management, password hashing, RBAC"),
        ("playerDataService", "Player data service with save/load, sync, conflict resolution, compression, backup"),
        ("leaderboardService", "Leaderboard service with real-time ranking, seasonal resets, anti-cheat, pagination"),
        ("matchmakingService", "Matchmaking service with skill-based matching, queue management, region routing"),
        ("analyticsService", "Analytics service with event tracking, cohort analysis, funnel tracking, A/B testing"),
        ("pushNotificationService", "Push notification service with targeting, scheduling, rate limiting, deep links"),
        ("contentDeliveryService", "CDN integration with asset versioning, delta updates, preloading, fallbacks"),
    ]
    for name, desc in backend:
        files[f"backend/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    files["backend/serverConfig.ts"] = _gen_logic_aaa("serverConfig", "Server configuration with environment detection, secrets management, feature flags, scaling rules", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: MIDDLEWARE LAYER — Request processing, transforms, validation
# ═══════════════════════════════════════════════════════════════════════
def _phase_middleware(build, t, g):
    files = {}
    mw = [
        ("corsMiddleware", "CORS middleware with origin whitelist, credentials, preflight, dynamic policy"),
        ("rateLimitMiddleware", "Rate limit middleware with sliding window, token bucket, per-route, IP/user tracking"),
        ("compressionMiddleware", "Compression middleware with gzip/brotli, threshold, content-type filtering"),
        ("cachingMiddleware", "Caching middleware with ETag, conditional GET, stale-while-revalidate, purge"),
        ("loggingMiddleware", "Request logging with structured output, timing, sanitization, correlation IDs"),
        ("errorHandlerMiddleware", "Error handler with categorization, stack sanitization, retry hints, user messages"),
        ("authorizationMiddleware", "Authorization middleware with role/permission checks, resource ownership, scoping"),
        ("inputSanitizer", "Input sanitizer with XSS prevention, SQL injection defense, schema validation, type coercion"),
        ("requestTransformer", "Request transformer with versioned API mapping, field aliasing, default injection"),
    ]
    for name, desc in mw:
        files[f"middleware/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: FRONTEND UI — User interface components, layouts, themes
# ═══════════════════════════════════════════════════════════════════════
def _phase_frontend(build, t, g):
    files = {}
    frontend = [
        ("ThemeProvider", "Theme provider with dark/light modes, custom palettes, dynamic switching, animations"),
        ("LayoutManager", "Layout manager with responsive breakpoints, orientation, safe areas, split views"),
        ("NavigationController", "Navigation with stack/tab/drawer, deep linking, history, transitions, guards"),
        ("FormBuilder", "Form builder with validation, dynamic fields, error display, submission, auto-save"),
        ("DataTable", "Data table with sorting, filtering, pagination, selection, export, virtual scrolling"),
        ("ChartLibrary", "Chart library with line, bar, pie, radar, scatter, real-time updates, tooltips"),
        ("AnimationLibrary", "Animation library with entrance/exit, spring, keyframe, gesture-driven, shared element"),
        ("NotificationCenter", "Notification center with inbox, badges, grouping, actions, swipe gestures, filters"),
    ]
    for name, desc in frontend:
        files[f"ui/components/{name}.tsx"] = _gen_component_aaa(name, desc, t, g)
    ui_screens = ["NotificationScreen", "ThemePreviewScreen", "ComponentGalleryScreen"]
    for s in ui_screens:
        files[f"screens/{s}.tsx"] = _gen_screen_aaa(s, t, g)
    build["_all_screens"] = build.get("_all_screens", []) + ui_screens
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: COMPLEXITY & DEPTH — Deep systems, meta-game, endgame
# ═══════════════════════════════════════════════════════════════════════
def _phase_complexity(build, t, g):
    files = {}
    complexity = [
        ("metaGameEngine", "Meta-game engine with prestige systems, cross-run upgrades, unlockables, legacy bonuses"),
        ("endgameContent", "Endgame content with raid tiers, mythic modes, leaderboards, seasonal challenges"),
        ("buildCrafting", "Build crafting with stat synergies, gear sets, talent combos, theorycrafting tools"),
        ("economyDepth", "Deep economy with player trading, market speculation, supply/demand, price history"),
        ("socialSystems", "Social systems with guilds, alliances, rivalries, mentoring, events, reputation"),
        ("proceduralChallenge", "Procedural challenge with rifts, modifiers, time trials, score multipliers, leaderboards"),
        ("newGamePlus", "New Game+ with scaling, new content, remixed encounters, additional story, harder bosses"),
    ]
    for name, desc in complexity:
        files[f"logic/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: INTRICACY & DETAIL — Micro-details, polish, interactables
# ═══════════════════════════════════════════════════════════════════════
def _phase_intricacy(build, t, g):
    files = {}
    intricacy = [
        ("microInteractions", "Micro-interactions with hover states, button depress, scroll momentum, haptic feedback"),
        ("environmentDetail", "Environment detail with cloth physics, paper scatter, liquid sloshing, dust particles"),
        ("characterDetail", "Character detail with breathing animation, idle fidgets, contextual reactions, eye tracking"),
        ("weatherDetail", "Weather detail with rain puddles, snow footprints, wind-blown objects, condensation"),
        ("lightingDetail", "Lighting detail with candle flicker, neon buzz, sunbeam dust motes, rainbow refraction"),
        ("audioDetail", "Audio detail with material footsteps, armor clinks, breathing intensity, heartbeat under stress"),
    ]
    for name, desc in intricacy:
        files[f"detail/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: EASTER EGGS & SECRETS — Hidden content, secrets, references
# ═══════════════════════════════════════════════════════════════════════
def _phase_easter_eggs(build, t, g):
    files = {}
    eggs = [
        ("secretManager", "Secret manager with trigger conditions, unlock tracking, hint system, achievement links"),
        ("hiddenRooms", "Hidden room system with entrance detection, puzzle locks, reward tables, atmosphere"),
        ("konami", "Konami code and button combos with activation effects, secret modes, debug access"),
        ("developerRoom", "Developer room with credits, commentary, art gallery, music player, stats display"),
        ("secretBossSystem", "Secret boss system with trigger conditions, unique AI, exclusive loot, lore reveals"),
    ]
    for name, desc in eggs:
        files[f"secrets/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    files["data/easter_eggs_database.ts"] = _gen_data_file("easter_eggs_database", "Easter egg definitions with triggers, rewards, hints, rarity, discovery conditions", t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: ADVANCED IMMERSION — Haptics, sensory, environmental response
# ═══════════════════════════════════════════════════════════════════════
def _phase_immersion(build, t, g):
    files = {}
    immersion = [
        ("hapticEngine", "Haptic feedback with contextual vibration patterns, intensity curves, device-specific profiles"),
        ("dynamicWeather", "Dynamic weather response with player gear effects, visibility, movement speed, shelter mechanic"),
        ("environmentalStorytelling", "Environmental storytelling with scene setups, item placement, visual narratives, clue chains"),
        ("npcRealism", "NPC realism with daily schedules, relationship memory, mood, age progression, gossip networks"),
        ("worldReactivity", "World reactivity with consequence propagation, faction territory shifts, economy ripples"),
        ("senseSimulation", "Sense simulation with smell zones, taste UI, touch feedback, temperature, pain indicators"),
    ]
    for name, desc in immersion:
        files[f"immersion/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: ADVANCED PSYCHOLOGY — Player engagement, flow, motivation
# ═══════════════════════════════════════════════════════════════════════
def _phase_psychology(build, t, g):
    files = {}
    psych = [
        ("flowManager", "Flow state manager with challenge/skill balance, zone detection, difficulty micro-adjustment"),
        ("engagementTracker", "Engagement tracker with session analysis, churn prediction, re-engagement hooks"),
        ("rewardPsychology", "Reward psychology with variable ratio schedules, surprise mechanics, anticipation building"),
        ("frustrationDetector", "Frustration detector with input analysis, death frequency, rage quit prediction, intervention"),
        ("socialMotivation", "Social motivation with competition, cooperation, social comparison, group identity"),
        ("narrativeHooks", "Narrative hooks with cliffhangers, mystery threads, curiosity gaps, revelation pacing"),
        ("playerProfiling", "Player profiling with Bartle types, play style, preference learning, personalized content"),
    ]
    for name, desc in psych:
        files[f"psychology/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE: FINE TUNING — Final pass optimization, config, runtime tweaks
# ═══════════════════════════════════════════════════════════════════════
def _phase_fine_tuning(build, t, g):
    files = {}
    tuning = [
        ("performanceTuner", "Performance tuner with frame budget, draw call reduction, texture streaming, LOD bias"),
        ("memoryOptimizer", "Memory optimizer with allocation tracking, leak detection, pool tuning, GC scheduling"),
        ("networkOptimizer", "Network optimizer with packet batching, compression tuning, prediction adjustment, buffer sizing"),
        ("loadTimeTuner", "Load time tuner with asset prioritization, streaming order, preload hints, background loading"),
        ("batteryOptimizer", "Battery optimizer with thermal throttling, background task management, GPS/sensor duty cycling"),
        ("startupOptimizer", "Startup optimizer with cold/warm launch profiling, lazy initialization, splash screen management"),
        ("finalConfigTuner", "Final config tuner with per-device profiles, dynamic quality, regression testing, golden masters"),
    ]
    for name, desc in tuning:
        files[f"tuning/{name}.ts"] = _gen_logic_aaa(name, desc, t, g)
    # Final build manifest
    files["BUILD_MANIFEST.md"] = f"# {t} — Build Manifest\n\n## Build Complete\n- Genre: {g}\n- Total Phases: 100\n- Total Batches: 10\n- Architecture: 10-Batch Hyper-granular staggered generation\n- Quality: AAA-grade with 15-minute deep generation\n\n## Batch Summary\n" + "\n".join(f"- Batch {b}: {_gs.BATCH_NAMES.get(b, '')} ({len(_gs.BUILD_BATCHES.get(b, []))} phases)" for b in range(1, 11)) + "\n\n## Phase Summary\n" + "\n".join(f"- Phase {i+1}: {p['name']} (Batch {p['batch']}, {p['agents']} agents)" for i, p in enumerate(_gs.BUILD_PHASES)) + "\n"
    return files


def _phase_generic(build, t, g, phase_info):
    """Generic phase generator for phases without dedicated functions.
    Uses _expand_massive() to generate substantial code files for any phase."""
    files = {}
    phase_id = phase_info["id"]
    phase_name = phase_info["name"]
    agents = phase_info["agents"]
    batch = phase_info["batch"]
    
    # Generate contextual file names based on the phase
    module_names = [
        (f"{phase_id}Core", f"Core engine for {phase_name} — {agents} agents generating {t} ({g})"),
        (f"{phase_id}Manager", f"Manager system for {phase_name} — orchestrating subsystems for {t}"),
        (f"{phase_id}Controller", f"Controller layer for {phase_name} — input/output management for {t}"),
        (f"{phase_id}System", f"System implementation for {phase_name} — deep logic layer for {t}"),
        (f"{phase_id}Utils", f"Utility functions for {phase_name} — helpers, validators, formatters for {t}"),
        (f"{phase_id}Data", f"Data structures and configurations for {phase_name} in {t} ({g})"),
        (f"{phase_id}Events", f"Event system for {phase_name} — pub/sub, callbacks, observers for {t}"),
        (f"{phase_id}Config", f"Configuration and constants for {phase_name} in {t}"),
    ]
    
    folder = phase_id.replace("_", "/")
    for name, desc in module_names:
        files[f"{folder}/{name}.ts"] = _expand_massive(name, desc, t, g, phase_id)
    
    # Add a phase README with Knowledge Applied section (No Lazy Agents)
    gk_ctx = build.get("_gk_context") or {}
    gk_keys = gk_ctx.get("topic_keys") or []
    # Deterministic per-phase topic slice so each phase cites a different 3
    import hashlib as _hl
    slice_start = int(_hl.md5(phase_id.encode()).hexdigest(), 16) % max(len(gk_keys), 1) if gk_keys else 0
    cited = [gk_keys[(slice_start + i) % len(gk_keys)] for i in range(3)] if gk_keys else []
    knowledge_section = (
        "\n### Knowledge Applied (from 500-DB Game Knowledge Vault)\n"
        + "\n".join(f"- `{k}`" for k in cited)
        + (f"\n- Variation axes considered: {', '.join(gk_ctx.get('axes', [])[:4])}\n"
           if gk_ctx.get("axes") else "\n")
        + "- See `docs/GAME_KNOWLEDGE_VAULT.md` for the canonical seeds.\n"
    ) if cited else ""

    files[f"{folder}/README.md"] = (
        f"# {t} — {phase_name}\n\n"
        f"## Batch {batch} | Phase: {phase_id}\n"
        f"## Agents: {agents:,}\n"
        f"## Genre: {g}\n\n"
        f"### Files Generated\n"
        + "\n".join(f"- `{name}.ts` — {desc}" for name, desc in module_names)
        + "\n"
        + knowledge_section
    )
    return files


# ═══════════════════════════════════════════════════════════════════════
# PHASE FUNCTION DISPATCH MAP — Maps phase_id to its generator function
# Phases without dedicated functions use _phase_generic
# ═══════════════════════════════════════════════════════════════════════
_PHASE_FUNC_MAP = {
    # Batch 1: Foundation
    "vision": "_phase_vision",
    "system": "_phase_system",
    "framework": "_phase_framework",
    "engine": "_phase_engine",
    "architecture": "_phase_architecture",
    "lore": "_phase_lore",
    "plot_intrigue": "_phase_plot_intrigue",
    # Batch 2: Core Mechanics
    "mechanics": "_phase_mechanics",
    "gameplay": "_phase_gameplay",
    # Batch 3: World & Environment
    "world_gen": "_phase_world_gen",
    "environment": "_phase_environment",
    # Batch 4: Audio & Visual
    "graphics": "_phase_graphics",
    "vfx": "_phase_vfx",
    "animations": "_phase_animations_pack",
    "cinematics": "_phase_cinematics",
    "sound": "_phase_sound",
    "sfx": "_phase_sfx",
    "music": "_phase_music",
    "ambiance": "_phase_ambiance",
    # Batch 5: AI & Behavior
    "ai_behavior": "_phase_ai_behavior",
    # Batch 6: Systems & Network
    "networking": "_phase_networking",
    "backend_phase": "_phase_backend",
    "middleware": "_phase_middleware",
    "frontend_phase": "_phase_frontend",
    "menu": "_phase_menu",
    "settings": "_phase_settings",
    # Batch 7: Content & Depth
    "cutscenes": "_phase_cutscenes",
    "tutorial": "_phase_tutorial",
    "easter_eggs": "_phase_easter_eggs",
    # Batch 8: Polish & Quality
    "balancing": "_phase_balancing",
    "complexity": "_phase_complexity",
    "intricacy": "_phase_intricacy",
    "permutations": "_phase_permutations",
    "enhancement": "_phase_enhancement",
    "sota": "_phase_sota",
    "immersion": "_phase_immersion",
    "psychology": "_phase_psychology",
    # Batch 9: Testing & Security
    "testing": "_phase_testing",
    # Batch 10: Final Assembly
    "compilation": "_phase_compilation",
    "fine_tuning": "_phase_fine_tuning",
}
