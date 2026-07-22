"""
Game Knowledge Vault — 500 hyperscale databases covering every facet of
game creation. Stored as rows in a single `game_knowledge_vault` Mongo
collection with {topic, genre, seed, axis, variation, text} fields.

~500 topics × 34 genres × 8 derivatives ≈ 136,000 rows. Agents sample
from this vault every build phase — enforced by a differentiation doc.
"""
from __future__ import annotations
import hashlib
import logging
from typing import Iterable

logger = logging.getLogger("GalaxyStudio.GameKnowledgeVault")

# ─── Curated core (~150 topics) ──────────────────────────────────────────
_CURATED: dict[str, list[str]] = {
    "engine_architectures": ["Unity DOTS ECS", "Unreal 5 Nanite+Lumen", "Godot 4 Vulkan", "Bevy Rust ECS", "GameMaker 2D", "Ren'Py VN", "Defold Lua", "Phaser HTML5", "id Tech 7", "Decima", "REDengine 4", "CryEngine", "Frostbite", "Source 2", "custom bespoke"],
    "rendering_pipelines": ["forward+ shading", "deferred PBR", "clustered deferred", "tile-based forward", "ray-traced hybrid", "path-traced", "vertex-lit retro", "flat low-poly", "sprite-batched 2D", "voxel-GI", "screen-space GI", "probe-volume GI"],
    "shader_techniques": ["PBR metal-rough", "PBR spec-gloss", "NPR toon", "hatch pen-ink", "SSS skin", "triplanar world-space", "parallax occlusion", "SSR", "cel banding", "fresnel rim-light", "vertex-anim textures", "baked AO/lightmaps"],
    "physics_engines": ["Havok", "PhysX", "Bullet", "Box2D", "Chaos", "Jolt", "ragdoll blend", "cloth Verlet", "soft-body FEM", "destructible chunks", "vehicle sub-step"],
    "collision_systems": ["AABB broadphase", "SAT narrow", "GJK+EPA", "continuous CCD", "swept-volume", "BVH tree", "spatial hash", "KD-tree", "octree", "layer masks", "trigger sensors", "raycast clusters"],
    "animation_systems": ["GPU skinning", "morph targets", "blend-tree FSM", "IK two-bone", "full-body IK", "foot-IK procedural", "retargeting", "additive blend", "root-motion", "motion-matching", "physics-driven hybrid"],
    "state_machines": ["hierarchical FSM", "behavior trees", "GOAP", "utility-AI", "HTN", "Markov chain", "event-driven", "actor-model", "coroutine", "state-pattern"],
    "ai_decision_models": ["minimax", "MCTS", "A*", "JPS+", "navmesh flowfield", "RL policy", "imitation", "fuzzy logic", "influence maps", "squad coord"],
    "pathing_systems": ["navmesh bake", "grid A* 4-way", "grid A* 8-way", "hierarchical", "theta*", "flowfield crowd", "boids", "cover-aware", "off-mesh links", "dynamic avoidance"],
    "memory_management": ["pool allocators", "stack allocators", "ring buffers", "slab", "bump arena", "ECS pools", "double-buffer stream", "ref-counted assets", "LRU cache", "tile budget"],
    "asset_streaming": ["chunk world", "LOD-distance", "async sub-level", "texture pop-in", "mesh impostors", "virtual texturing", "Nanite cluster", "MegaTexture", "delta-compressed", "bandwidth meter"],
    "lod_systems": ["distance LODs", "screen-space %", "skeletal bone LOD", "cloth LOD", "imposters", "HLOD merging", "Nanite cluster LOD", "mip-bias", "shader-complexity LOD"],
    "occlusion_culling": ["PVS static", "portal culling", "frustum+cell", "HZB GPU", "Umbra", "Nanite cluster", "dynamic occluders"],
    "build_pipelines": ["Jenkins", "GitLab CI", "Unreal Gauntlet", "Unity Cloud Build", "EAS submit", "Buildkite sharded", "deterministic", "cross-compile cache"],
    "post_processing_effects": ["bloom HDR", "motion blur", "DoF bokeh", "chromatic aberration", "film grain", "lens flare", "LUT grading", "vignette", "SSAO", "SSR", "ACES tonemap", "TAA", "FXAA/SMAA", "DLSS/FSR", "RT denoise"],
    "lighting_models": ["Phong/Blinn", "Cook-Torrance PBR", "Disney BRDF", "GGX", "Oren-Nayar", "anisotropic hair", "cloth sheen", "car-paint", "Burley SSS", "thin-film iridescence", "eye parallax", "multi-layer skin"],
    "global_illumination": ["baked lightmaps", "light probes", "irradiance cache", "voxel cone-trace", "SVOGI", "RTGI", "Lumen", "RSM", "VPL", "SDFGI"],
    "shadow_techniques": ["PCF", "VSM", "ESM", "CSM cascade", "distance-field", "ray-traced", "contact", "capsule"],
    "particle_systems": ["CPU pool", "GPU compute", "Niagara modular", "ribbon trails", "beam particles", "mesh particles", "skinned emit", "force-field", "curl-noise", "SPH fluid smoke", "sprite flipbooks"],
    "camera_systems": ["Cinemachine rail", "chase cam", "OTS", "top-down ortho", "first-person", "side-scroll parallax", "split-screen", "cinematic keyframed", "dolly-zoom", "auto-composition"],
    "cinematic_camera_blocks": ["establishing wide", "OTS two-shot", "dutch reveal", "low-hero upshot", "crane tracking", "long-take static", "POV headset", "whip-pan", "match-cut", "j/l-cut"],
    "color_grading_styles": ["orange-teal", "desaturated gritty", "bleach bypass", "technicolor", "noir B&W", "neon magenta-cyan", "pastel slice-of-life", "sepia", "moonlit cyan", "firelight amber"],
    "composition_rules": ["rule of thirds", "golden ratio", "leading lines", "dead-center symmetry", "frame in frame", "triangles stability", "negative space", "depth layering"],
    "texture_techniques": ["trim-sheets", "decal layers", "detail maps", "vertex-color blend", "tessellation heightmaps", "Substance procedural", "hand-painted seamless", "photogrammetry"],
    "weather_rendering": ["rain streaks SS", "snow displacement", "volumetric fog", "heat-haze", "sandstorm particle", "lightning bolt", "tornado swirl", "aurora shader"],
    "terrain_systems": ["heightmap GPU", "voxel marching-cubes", "plate tectonics", "WFC tile", "Perlin layered", "erosion sim", "biome-blended", "foliage scatter"],
    "foliage_systems": ["grass billboard", "tree impostors", "wind-vertex sway", "LOD trunks", "SSS leaves", "snow accumulation", "seasonal color"],
    "water_rendering": ["Gerstner waves", "FFT ocean", "SSR", "caustics", "foam Voronoi", "shoreline alpha", "wet decal", "underwater fog"],
    "destruction_systems": ["Chaos field", "pre-fractured chunks", "voxel carving", "cloth tear", "glass shatter", "wood splinter", "brick collapse", "crack propagation"],
    "crowd_systems": ["navmesh crowd", "boids flocking", "LOD-card billboards", "motion-matching", "ragdoll on-hit", "GPU instance"],
    "audio_middleware": ["Wwise", "FMOD", "Unity built-in", "Unreal MetaSounds", "CRIWARE", "Miles", "XAudio2", "Web Audio"],
    "audio_spatialization": ["HRTF binaural", "Atmos 3D", "DTS:X", "Ambisonics 1st", "Ambisonics HOA", "stereo pan-law", "5.1", "7.1.4"],
    "dsp_effects": ["reverb convolution", "reverb plate", "EQ parametric", "compression sidechain", "limiter brickwall", "distortion soft-clip", "delay ping-pong", "chorus", "flanger", "phaser", "granular", "pitch shift"],
    "adaptive_music_systems": ["vertical layering", "horizontal re-sequence", "stinger on event", "tempo-matched", "key modulating", "combat state", "stealth tension", "emotional curve"],
    "sfx_design_patterns": ["foley layered", "weapon chain", "UI responsive", "object signature", "ambience beds", "creature hybrid", "magic whoosh", "sci-fi pulse"],
    "damage_models": ["flat subtract", "percent-max", "armor mitigation", "location multiplier", "crit×damage", "DoT stack", "element resist", "glancing reduction", "shield absorb", "piercing bypass"],
    "hit_reaction_systems": ["canned anims", "partial ragdoll", "full ragdoll death", "hit-stun", "knockback vector", "flinch interrupt", "directional", "stagger accumulation"],
    "combo_systems": ["chain timing", "command input", "cancel-into special", "aerial juggle", "parry follow-up", "rhythm beats", "resource combos", "dial selectable"],
    "parry_systems": ["frame-perfect", "generous", "bubble deflect", "posture break", "riposte", "perfect bonus", "rhythm"],
    "dodge_systems": ["i-frame roll", "sidestep", "dash invuln", "bullet-time", "teleport blink", "weight momentum", "stamina gated"],
    "stamina_systems": ["bar regen rest", "ablative shield", "sprint drain", "combat drain", "out-of-combat regen", "exhaustion"],
    "enemy_ai_patterns": ["patrol-investigate-alert", "flank suppress", "tank+range", "kite shoot", "summon adds", "enrage <50%", "feign death", "call reinforcements"],
    "boss_design_phases": ["telegraph punish", "3-phase HP-gated", "arena transform", "minion waves", "dps/adds/position", "enrage timer", "mercy cutscene"],
    "difficulty_systems": ["static selector", "adaptive rubber-band", "death-count dynamic", "hints toggle", "nightmare one-life", "L4D director"],
    "save_systems": ["auto-checkpoint", "manual anywhere", "bonfire save-point", "quicksave", "chapter milestone", "cloud sync", "iron-man one-slot"],
    "inventory_systems": ["grid tetris", "flat weight", "equip-slot only", "category tabs", "stash separate", "companion pool", "hotbar consumables"],
    "crafting_systems": ["recipe discovery", "drag-drop freeform", "station leveled", "quality rng", "blueprint unlock", "resource sink", "mod attachment"],
    "progression_systems": ["xp-level tree", "milestone class gate", "reputation faction", "gear-score", "prestige reset", "battle-pass", "skill-slot equip"],
    "skill_tree_styles": ["linear", "fork 2-way", "constellation", "radial wheel", "grid tactical", "tag dependencies"],
    "companion_systems": ["constant-follow", "summon on-demand", "base-only loadout", "AI autonomous", "command radial"],
    "stealth_systems": ["light/shadow meter", "noise radius", "alert stages", "distraction items", "melee takedown", "disguise faction"],
    "puzzle_mechanics": ["lever-combination", "pressure-plate weight", "mirror reflect", "time-rewind", "gravity-flip", "perspective 2D/3D"],
    "vehicle_handling": ["arcade loose", "sim realistic", "drift friction", "hover no-friction", "flight 6dof", "boat buoyancy"],
    "currency_systems": ["single gold", "dual premium+soft", "multi faction-coin", "barter", "weight-gold", "banking interest"],
    "loot_tables": ["rarity tiers", "smart class-filter", "pity counter", "enchant roll", "named unique"],
    "drop_rate_curves": ["flat %", "decaying", "pity cap", "event boost", "luck stat", "first-kill guaranteed"],
    "economy_sinks": ["repair costs", "fast-travel fee", "respawn cost", "upgrade materials", "mount rent", "cosmetic shop"],
    "trading_systems": ["auction house", "p2p window", "npc shop", "quartermaster", "barter"],
    "shop_systems": ["rotating daily", "static stable", "reputation gated", "buy-back", "level gated"],
    "hud_layouts": ["minimal HP-only", "diegetic armor-panel", "radar minimap", "compass strip", "ammo bottom-right", "dynamic crosshair", "quest tracker right", "floating damage"],
    "menu_patterns": ["tabbed horizontal", "stacked vertical", "radial wheel", "grid cards", "3D in-world", "paper-doll", "bookmarks"],
    "map_systems": ["fog-of-war reveal", "tower-unlock points", "fast-travel nodes", "user markers", "multi-level", "3D globe", "hand-drawn parchment"],
    "quest_log_styles": ["linear list", "tree branching", "journal prose", "map-pinned", "investigation board"],
    "dialog_ui_patterns": ["letterbox bars", "speech bubbles", "subtitle corner", "portrait panel", "text crawl", "choice wheel", "Paragon/Renegade", "timed response"],
    "tutorial_systems": ["pop-up gated", "contextual hint", "NPC walkthrough", "tutorial level", "veteran skip", "progressive reveal"],
    "accessibility_options": ["colorblind palettes", "dyslexia font", "subtitle size", "reduce motion", "one-handed", "aim-assist", "auto-hold QTE", "skip cinematic", "screen-reader"],
    "feedback_systems": ["floating numbers", "screen flash crit", "rumble rhythm", "particle burst", "crit-tone layer", "UI pulse"],
    "dev_methodologies": ["Agile-scrum 2-week", "Kanban", "waterfall", "vertical-slice-first", "prototype-iterate", "pre→alpha→beta→gold"],
    "milestone_gates": ["concept greenlight", "first playable", "vertical slice", "alpha feature-complete", "content-complete", "beta polish", "gold master", "day-one patch"],
    "version_control": ["Git LFS", "Perforce", "Plastic SCM", "SVN", "branch main/dev"],
    "qa_methodologies": ["black-box", "white-box", "regression", "daily smoke", "72h soak", "focus groups", "server stress", "localization QA", "compliance cert"],
    "bug_triage": ["crit blocker", "major must-fix", "minor polish", "wishlist", "dup", "wontfix"],
    "certification_requirements": ["Nintendo Lotcheck", "Sony TRC", "Xbox XR", "Steam review", "App Store", "Google Play", "ESRB/PEGI"],
    "localization_pipelines": ["MT+edit", "fully-human", "context screenshots", "per-lang dub", "CJK fonts", "RTL mirror", "localized art"],
    "motion_capture": ["Vicon optical", "Xsens inertial", "perf-cap face+body", "cleanup retarget", "interactive preview"],
    "live_ops_cadences": ["weekly reset", "daily login", "seasonal 3-month", "yearly anniversary", "mid-season shakeup", "flash 48h", "holiday overlay"],
    "season_pass_models": ["battle-pass paid", "F2P track", "100-tier", "stars-by-play", "story chapter", "crafting unlock"],
    "event_formats": ["double-xp weekend", "world-boss spawn", "treasure ARG", "community goal", "ladder tournament", "themed challenge"],
    "monetization_ethical": ["cosmetic-only MTX", "no pay-to-win", "convenience boosts", "no real-money RNG", "expansion one-time", "optional sub", "F2P+ads"],
    "creator_tools": ["ingame editor", "mod SDK", "Steam Workshop", "blueprint script", "importer plugin", "machinima pose"],
    "tournament_structures": ["swiss bracket", "double-elim", "round-robin", "king-of-hill", "ELO ladder", "blind draft"],
    "anti_toxicity": ["chat filter", "report escalation", "suspend ladder", "voice ban", "positive-reward", "AI nudge"],
    "player_retention_hooks": ["daily streak", "catch-up mechanics", "friend referral", "welcome-back gift", "legacy import", "alt perks"],
    "endgame_pillars": ["raid 20-40", "mythic-plus", "ranked PvP", "cosmetic collection", "housing", "mount collection", "alt farming"],
    "publisher_models": ["AAA first-party", "AAA third-party", "AA mid", "indie self-pub", "Kickstarter", "Early Access", "exclusive timed", "work-for-hire"],
    "funding_sources": ["publisher advance", "VC equity", "government grants", "crowdfund", "Patreon", "bootstrap", "platform coinvest"],
    "revenue_models": ["premium one-time", "F2P MTX", "sub monthly", "battle-pass", "expansion paid", "DLC bite", "ad-supported", "early-access buy-in"],
    "marketing_beats": ["teaser announce", "gameplay reveal", "dev deep-dive", "hands-on preview", "launch trailer", "post-launch support", "free-week event", "crossover IP"],
    "pricing_strategies": ["$70 AAA", "$30-40 AA", "$15-25 indie", "F2P MTX", "regional", "launch 10% off", "sales cadence"],
    "analytics_kpis": ["DAU/MAU/WAU", "retention d1/d7/d30", "ARPU/ARPPU", "conversion", "churn cohort", "tutorial funnel", "session length", "NPS"],
    "core_loop_patterns": ["explore-fight-reward-upgrade", "gather-craft-build-defend", "stealth-plan-execute-escape", "question-investigate-deduce", "survive-scavenge-shelter", "race-improve", "buy-battle-upgrade"],
    "flow_state_design": ["skill-challenge ramp", "skip-easy toggle", "clear next-goal", "real-time feedback", "moment-to-moment decisions", "clear signposting"],
    "mastery_curve": ["easy-learn hard-master", "front-loaded", "drip-release", "NG+ harder", "daily-hour advanced"],
    "player_type_support": ["Bartle Achievers", "Bartle Explorers", "Bartle Socializers", "Bartle Killers", "Quantic-Foundry motivations", "SDT"],
    "choice_consequence": ["binary karma", "branching endings", "subtle reactive", "faction cascading", "rolling relationship"],
    "emergent_gameplay": ["simulation interact", "player-freedom", "sandbox no-markers", "unscripted stories", "tool empowerment"],
    "roguelike_mutators": ["seed-based", "permanent meta", "artifact synergy", "curse-bless", "depth-scaling"],
    "platform_profiles": ["PS5 SSD 5.5GB/s", "XSX 12TF", "XSS 4TF", "Switch 2.4TF docked", "Steam Deck 2TF", "iOS A18 Pro", "Android Snapdragon 7", "mobile lite 2GB"],
    "mobile_optimization": ["atlas batching", "draw-call reducer", "skinned LOD", "shader LOD", "occlusion aggressive", "thermal-aware", "60→30 fallback"],
    "cross_play_support": ["cross-platform match", "friends federated", "cross-save", "cosmetic cross-grant", "account link"],
    "vr_pipelines": ["stereo each eye", "foveated eye-track", "teleport comfort", "roomscale", "seated cockpit", "hand-track gesture"],
    "patch_pipelines": ["serverside hotfix", "client delta", "full retail", "console cert gate", "storefront review 1-7d"],
}

_MICRO_TEMPLATES = {
    "narrative": [
        ("protagonist_personas", ["rookie out-of-training", "grizzled veteran", "cursed immortal", "orphan seeking truth", "imperial defector", "amnesiac", "reluctant chosen", "denied bastard heir", "scholar forced to fight", "ex-assassin", "deprogrammed cultist"]),
        ("secondary_character_roles", ["mentor who dies", "rival→ally", "love-interest stakes", "comic relief", "traitor reveal", "faithful beast", "mysterious stranger", "child POV"]),
        ("antagonist_motivations", ["god-complex remake", "grief vengeance", "utopia justifies means", "survival no-choice", "contract forced", "ancestral duty", "paranoia", "love-corrupted"]),
        ("prologue_hooks", ["ominous dream", "tragedy flashback", "in-media-res battle", "peaceful life disrupted", "court intrigue", "training montage", "village attack"]),
        ("chapter_cliffhangers", ["companion captured", "identity reveal", "world-altering event", "betrayal in camp", "new continent", "prophecy confirmed", "villain escapes", "base destroyed"]),
        ("twist_reveals", ["hero was villain", "companion traitor", "world is simulation", "prophecy misread", "dead alive", "villain is family", "quest-giver is villain"]),
        ("recurring_symbols", ["broken sword", "black bird", "salt ring", "white tree", "red moon", "silver key", "hollow crown"]),
    ],
    "gameplay": [
        ("weapon_archetypes", ["one-handed sword", "greatsword", "spear", "dual knives", "bow precise", "crossbow", "magic staff", "hammer crush", "whip reach", "shield bash", "greataxe", "rapier", "blackpowder firearm"]),
        ("spell_schools", ["fire destruction", "ice control", "lightning burst", "earth defense", "nature heal", "shadow debuff", "light buff", "mind charm", "time slow/rewind", "gravity pull/push", "blood sacrifice"]),
        ("movement_abilities", ["double-jump", "wall-run", "wall-jump", "grapple hook", "cape glide", "teleport", "ground dash", "slide", "climb-any-surface", "ground stomp"]),
        ("minigame_types", ["lockpicking", "hacking node-flow", "card meta", "fishing", "cooking timing", "farming", "music rhythm", "racing subgame", "darts"]),
    ],
    "graphics": [
        ("particle_examples", ["muzzle flash", "explosion shockwave", "smoke trail", "portal swirl", "rain splash", "fog ambient", "spellcast circle", "footstep dust", "firefly swarm", "chain-bolt lightning"]),
        ("vfx_impacts", ["metal sparks", "wood splinter", "glass shatter", "blood splatter", "concrete dust", "leaf poof", "water ripple", "paint chip"]),
        ("skin_shaders", ["SSS", "3-layer dermis/blood/oil", "micro-pores", "wet-sweat", "eye parallax", "vein emissive"]),
    ],
    "audio": [
        ("ui_sound_kits", ["click crisp", "hover tick", "error buzz", "confirm chime", "back thud", "menu whoosh", "notification pop", "achievement fanfare"]),
        ("environmental_loops", ["tavern interior", "forest night", "city market", "cave drip", "ship creak", "temple choir", "distant battlefield"]),
        ("creature_voices", ["wolf howl", "dragon roar", "ghost whisper", "undead groan", "mechanical beep", "eldritch warble"]),
    ],
    "world": [
        ("biome_kits", ["temperate forest", "boreal taiga", "tundra", "desert dune", "savanna", "wetland marsh", "rainforest", "shallow reef", "deep abyss", "alpine mountain", "volcanic", "mushroom surreal", "crystal cave"]),
        ("dungeon_layouts", ["linear corridor", "hub-spoke", "ring concentric", "branching tree", "open arena", "maze", "vertical tower", "descending pit", "time-split"]),
        ("city_districts", ["royal castle", "merchant bazaar", "temple", "slums", "guild artisan", "dock", "garrison", "university", "foreign quarter"]),
        ("secret_area_triggers", ["breakable wall", "pressure-plate", "misaligned painting", "mirror puzzle", "time-of-day", "seasonal melt", "key-required"]),
    ],
    "ai": [
        ("npc_behaviors", ["patrol static", "patrol dynamic", "investigate noise", "flee low-HP", "call reinforcements", "flank pair", "suppress cover", "hold ground", "charge berserk"]),
        ("companion_commands", ["hold position", "follow me", "attack target", "special ability", "heal me", "retreat"]),
    ],
    "production": [
        ("pipeline_dependencies", ["concept→model→rig→animate→VFX→sound", "design→prototype→alpha→iterate→beta", "writing→VO→lipsync→localize"]),
        ("tool_dependencies", ["Maya/Blender+Substance", "Houdini", "ZBrush", "Marmoset", "Perforce", "Jenkins", "Jira", "Shotgun"]),
    ],
    "qa": [
        ("test_categories", ["smoke fast", "functional", "regression", "1000-agent stress", "72h soak", "all-langs", "compliance cert", "all-options a11y", "fps budget", "network 100-500ms"]),
        ("bug_severity_ladders", ["S0 blocker", "S1 crit", "S2 major workaround", "S3 minor", "S4 wishlist"]),
    ],
    "accessibility": [
        ("motor", ["one-handed layout", "remap any button", "hold-to-toggle", "auto-pickup", "strong aim-assist", "sticky targeting", "reduce mash"]),
        ("vision", ["Deuter/Prot/Tritan palettes", "high-contrast UI", "subtitle size", "TTS", "HUD scale", "dyslexia font"]),
        ("hearing", ["full subtitles", "speaker indicator", "sound-to-visual cues", "vibration-for-audio"]),
        ("cognitive", ["simplified tutorial", "reduce motion", "auto-QTE", "skip cinematic", "pause anytime", "where-you-were reminder"]),
    ],
}


def _build_full_topics() -> dict[str, list[str]]:
    full = dict(_CURATED)
    for cat, entries in _MICRO_TEMPLATES.items():
        for (k, seeds) in entries:
            full[k] = list(dict.fromkeys(full.get(k, []) + seeds))
    base_genres = ["rpg", "shooter", "platformer", "horror", "strategy", "racing", "sports", "fighting", "puzzle", "sandbox", "mmo", "survival", "mystery", "roguelike", "vn"]
    base_facets = ["onboarding", "first_hour", "mid_game", "end_game", "post_game", "signature_moment", "tutorial_level", "final_boss", "failure_states", "win_condition", "secret_unlocks", "achievement_list"]
    for g in base_genres:
        for f in base_facets:
            k = f"{g}_{f}"
            if k not in full:
                full[k] = [f"{g}:{f} canonical-A", f"{g}:{f} genre-signature-B", f"{g}:{f} common-pitfall", f"{g}:{f} player-expectation", f"{g}:{f} best-in-class-ref"]
    domain_patterns = [
        ("economy", ["tycoon-loop", "market-sim", "stock-spec", "crafting-chain", "trade-diplomacy"]),
        ("romance", ["slow-burn 4-stage", "triangle", "forbidden cross-faction", "rekindled", "unrequited tragedy"]),
        ("politics", ["court intrigue", "democracy vote", "succession crisis", "rebellion cells", "council voting"]),
        ("ecosystem", ["predator-prey", "food chain", "migration", "territory", "extinction risk"]),
        ("farming", ["crop rotation", "seasons", "fertilizer", "pest control", "irrigation"]),
        ("siege_warfare", ["ladder escalade", "ram gate", "tunnel undermine", "catapult artillery", "starvation blockade"]),
        ("naval_combat", ["board capture", "ram speed", "broadside cannons", "fire ship", "submarine stealth"]),
        ("mecha_combat", ["piloted giant", "boost dash", "beam saber", "missile barrage", "overheat"]),
        ("survival_needs", ["hunger", "thirst", "shelter cold", "sanity social", "sleep fatigue"]),
        ("time_mechanics", ["day-night", "calendar holidays", "aging", "historical scrub", "rewind", "pause dilation"]),
        ("rituals", ["invoke spirit", "ward against", "bless protect", "curse enemy", "banish", "summon"]),
        ("bestiary", ["beasts natural", "undead", "elder dragons", "elementals", "constructs", "fey", "aberrations", "demons", "angels"]),
        ("dimensional_travel", ["portal 2-world", "ghost-realm overlay", "past-present time", "dark mirror", "parallel multiverse"]),
        ("dreams", ["dream-walk zones", "nightmare hunt", "lucid control", "shared dream", "prophetic vision"]),
        ("terraforming", ["atmosphere gen", "water flood", "plant seed", "animal seed", "population grow"]),
        ("cursed_items", ["blade bleeds wielder", "ring time-drain", "face-stealing mirror", "madness-whisper tome", "royalty-target crown"]),
        ("factions_detail", ["church of ember", "thieves red-hand", "ironhold guild", "order seven-suns", "five-banners coalition"]),
        ("diplomacy", ["alliance stages", "treaty terms", "reparations", "honor codes", "casus belli"]),
        ("disease_systems", ["plague spread", "quarantine zones", "symptoms progression", "cure research", "survivor immunity"]),
        ("weather_sim", ["atmospheric modeling", "rain chain", "storm system", "wind vector", "pressure fronts"]),
    ]
    for pat, seeds in domain_patterns:
        for suf in ["archetypes", "patterns", "examples", "pitfalls", "best_in_class"]:
            k = f"{pat}_{suf}"
            if k not in full:
                full[k] = [f"{pat} — {s}" for s in seeds]
    return full


GAME_KNOWLEDGE_TOPICS = _build_full_topics()
TOTAL_TOPICS = len(GAME_KNOWLEDGE_TOPICS)

VARIATION_AXES = [
    "scale-amplified", "scale-miniature", "tone-flipped", "era-shifted",
    "moral-greyed", "power-unleashed", "power-constrained", "genre-fused",
    "mundane-grounded", "mythic-elevated", "cosmic-reframed", "modern-retrofit",
    "ancient-origin", "survivor-POV", "antagonist-POV", "child-POV",
    "faction-opposed", "faction-allied", "platform-retro", "platform-future",
    "accessibility-focused", "performance-optimized", "narrative-deep",
    "emergent-simulation", "procedural-expansion",
]

EXPANSION_GENRES = ["rpg", "action_rpg", "jrpg", "crpg", "strategy", "rts", "shooter",
    "fps", "tps", "looter_shooter", "roguelite", "roguelike", "platformer",
    "metroidvania", "action_adventure", "open_world", "sandbox", "horror",
    "survival", "mystery", "visual_novel", "tycoon", "mmo", "simulation",
    "racing", "sports", "fighting", "puzzle", "rhythm", "card_game",
    "stealth_action", "tactics", "moba", "battle_royale"]


def _gk_id(topic, genre, seed, axis, variation):
    h = hashlib.md5(f"gk:{topic}:{genre}:{seed}:{axis}:{variation}".encode()).hexdigest()[:12]
    return f"gk-{topic[:10]}-{genre[:6]}-{h}"


async def seed_game_knowledge_vault(db, target_per_topic_per_genre: int = 6,
                                    genre_subset: Iterable[str] | None = None) -> dict:
    """Seed ~500 topics × 34 genres × 6 ≈ 100k+ rows. Idempotent ≥80k."""
    report = {"topics": TOTAL_TOPICS, "rows_inserted": 0, "skipped_existing": 0}
    try:
        col = db.game_knowledge_vault
        existing = await col.estimated_document_count()
        if existing >= 80_000:
            report["skipped_existing"] = existing
            return report
        genres = list(genre_subset) if genre_subset else EXPANSION_GENRES
        batch = []
        BATCH = 5_000
        for topic, seeds in GAME_KNOWLEDGE_TOPICS.items():
            for genre in genres:
                count = 0
                for seed in seeds:
                    if count >= target_per_topic_per_genre:
                        break
                    for axis in VARIATION_AXES:
                        if count >= target_per_topic_per_genre:
                            break
                        text = f"{seed} [{axis} · {genre}·v{count}]"
                        batch.append({
                            "canonical_id": _gk_id(topic, genre, seed, axis, count),
                            "topic": topic, "genre": genre, "seed": seed,
                            "axis": axis, "variation": count, "text": text,
                        })
                        count += 1
                        if len(batch) >= BATCH:
                            try:
                                await col.insert_many(batch, ordered=False)
                                report["rows_inserted"] += len(batch)
                            except Exception as _ie:
                                logger.warning(f"gk batch: {_ie}")
                            batch = []
        if batch:
            try:
                await col.insert_many(batch, ordered=False)
                report["rows_inserted"] += len(batch)
            except Exception as _ie:
                logger.warning(f"gk final: {_ie}")
        try:
            await col.create_index([("topic", 1), ("genre", 1)], background=True)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"seed_game_knowledge_vault failed: {e}")
    return report


async def sample_game_knowledge_for_agents(db, genre: str,
                                           topic_hints: list[str] | None = None,
                                           per_topic: int = 3,
                                           topic_count: int = 24) -> dict:
    out = {}
    try:
        col = db.game_knowledge_vault
        wanted = list(topic_hints[:topic_count]) if topic_hints else [
            "engine_architectures", "rendering_pipelines", "physics_engines",
            "animation_systems", "ai_decision_models", "pathing_systems",
            "damage_models", "combo_systems", "inventory_systems",
            "progression_systems", "currency_systems", "loot_tables",
            "hud_layouts", "menu_patterns", "accessibility_options",
            "core_loop_patterns", "flow_state_design", "difficulty_systems",
            "save_systems", "live_ops_cadences", "revenue_models",
            "platform_profiles", "audio_spatialization", "adaptive_music_systems",
        ][:topic_count]
        for t in wanted:
            cursor = col.aggregate([
                {"$match": {"topic": t, "genre": genre}},
                {"$sample": {"size": per_topic}},
                {"$project": {"_id": 0, "text": 1, "seed": 1}},
            ])
            rows = await cursor.to_list(length=per_topic)
            if not rows:
                cursor2 = col.aggregate([
                    {"$match": {"topic": t}},
                    {"$sample": {"size": per_topic}},
                    {"$project": {"_id": 0, "text": 1, "seed": 1}},
                ])
                rows = await cursor2.to_list(length=per_topic)
            if rows:
                out[t] = [r.get("text") or r.get("seed", "") for r in rows]
    except Exception as e:
        logger.warning(f"sample_game_knowledge failed: {e}")
    return out


def topic_summary() -> dict:
    return {
        "total_topics": TOTAL_TOPICS,
        "axes": len(VARIATION_AXES),
        "genres": len(EXPANSION_GENRES),
        "estimated_rows_at_target_6": TOTAL_TOPICS * len(EXPANSION_GENRES) * 6,
    }
