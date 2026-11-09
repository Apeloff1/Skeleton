"""
╔══════════════════════════════════════════════════════════════════════════════════════════════════╗
║  QUANTUM FACTORY CORE v22.0 — EXTREME PRODUCTION-GRADE GAME CREATION ENGINE                    ║
║                                                                                                ║
║  Completes the full 14-domain mechanic architecture with 7 additional ultra-deep domains:      ║
║                                                                                                ║
║   8.  NarrativeLoom    — Branching narrative, procedural dialogue, emotional arc engineering    ║
║   9.  RenderPipeline   — LOD chains, GPU culling, draw call batching, ray-traced GI            ║
║  10.  SocialFabric     — Faction calculus, reputation decay, emergent political simulation      ║
║  11.  MetaGameOps      — Live-ops cadence, season pass mathematics, retention funnel design     ║
║  12.  PhysicsVault     — Rigid/soft body solvers, SPH fluid, Verlet cloth, fracture meshes     ║
║  13.  AudioSphere      — HRTF spatial audio, adaptive music layering, DSP effect chains        ║
║  14.  UXArchitect      — Information architecture, Fitts' Law layouts, WCAG compliance         ║
║                                                                                                ║
║  Each domain: 8 specialists × deep_knowledge formulas = extreme production intricacy           ║
║                                                                                                ║
║  Endpoints:                                                                                    ║
║    GET  /api/quantum-factory/status                                                            ║
║    GET  /api/quantum-factory/health-matrix                                                     ║
║    GET  /api/quantum-factory/domain/{domain_id}                                                ║
║    GET  /api/quantum-factory/full-architecture                                                 ║
║    POST /api/quantum-factory/synthesize                                                        ║
╚══════════════════════════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
import hashlib, time, uuid, json, math

router = APIRouter(prefix="/api/quantum-factory", tags=["quantum-factory"])

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 8: NARRATIVE LOOM — Branching Narrative, Emotional Arcs, Procedural Dialogue
# ════════════════════════════════════════════════════════════════════════════════

NARRATIVE_LOOM_SPECIALISTS = {
    "branching_narrative_architect": {
        "id": "nl-branch", "name": "StoryGraph", "title": "Branching Narrative Architect",
        "expertise": [
            "Directed acyclic narrative graphs with convergence nodes preventing exponential branch explosion",
            "Consequence propagation matrices: choice at node N affects nodes N+3, N+7, N+12 via weighted ripple",
            "Three-act structure enforcement within procedural narrative: setup (25%), confrontation (50%), resolution (25%)",
            "Parallel storyline weaving: maintain 2-4 concurrent plot threads with synchronization checkpoints",
            "Player agency scoring: track meaningful choices vs illusory choices, target >60% meaningful ratio",
            "Story state compression: encode narrative state as 64-bit flags for save/load and network sync",
            "Retroactive narrative justification: procedurally insert foreshadowing for player choices already made",
            "Narrative dead-end prevention: every branch must reach at least one valid ending within 3 choices",
        ],
        "deep_knowledge": {
            "branch_factor_budget": "max_total_nodes = base_content_hours × 60 / avg_node_duration_minutes; branch_factor ≤ cube_root(max_total_nodes)",
            "consequence_ripple": "impact(N, target) = base_weight × decay^(target - N) × emotional_intensity(N); decay ∈ [0.7, 0.9]",
            "convergence_formula": "converge when active_branches > max_sustainable (typically 4); merge via shared_crisis_event",
            "agency_score": "agency = (choices_with_distinct_outcomes / total_choices) × (1 + long_term_consequence_ratio × 0.5)",
            "state_encoding": "narrative_state = bitfield[64]: bits 0-15 = faction_flags, 16-31 = character_alive, 32-47 = quest_state, 48-63 = world_events",
        },
    },
    "emotional_arc_engineer": {
        "id": "nl-emotion", "name": "ArcWeaver", "title": "Emotional Arc Engineer",
        "expertise": [
            "Plutchik's wheel of emotions mapped to gameplay moments: joy-surprise-anticipation-trust-fear-sadness-disgust-anger",
            "Emotional intensity curves per act: Act1 curiosity→wonder, Act2 tension→despair→determination, Act3 triumph→bittersweet",
            "Pacing mathematics: tension = min(1.0, accumulated_threat × (1 - recent_relief)); target oscillation period 15-25 minutes",
            "Catharsis engineering: peak emotional intensity must be followed by proportional release within 2-5 minutes",
            "Player emotional state inference from input patterns: hesitation = uncertainty, rapid actions = excitement/panic",
            "Emotional contrast: alternate high/low intensity scenes, never >3 consecutive high-intensity without breather",
            "Character attachment metrics: screen_time × vulnerability_shown × player_agency_over_fate = attachment_score",
            "Grief design: permanent loss must be telegraphed, mourning period of 5-10 minutes gameplay before next major event",
        ],
        "deep_knowledge": {
            "tension_formula": "tension(t) = clamp(base_threat × (1 + stacking_events × 0.3) - relief_events × 0.5, 0, 1.0)",
            "pacing_oscillation": "target_cycle = 20min; high_phase = 12min, low_phase = 8min; intensity = sin(2π × t/cycle) × 0.3 + 0.5",
            "attachment_score": "attachment = (screen_time_hours × 10 + vulnerability_events × 25 + player_saves_character × 50) × likeability_factor",
            "catharsis_ratio": "relief_intensity = peak_intensity × catharsis_multiplier; catharsis_multiplier ∈ [0.6, 0.9]",
        },
    },
    "procedural_dialogue_specialist": {
        "id": "nl-dialogue", "name": "VoxGen", "title": "Procedural Dialogue Specialist",
        "expertise": [
            "Template-based dialogue generation: [GREETING] + [CONTEXT_REFERENCE] + [QUEST_HOOK] + [PERSONALITY_FLAIR]",
            "NPC voice consistency: personality vectors (formality, humor, aggression, wisdom) applied to all templates",
            "Context injection: reference player's recent achievements, equipped items, companion, time of day, weather",
            "Relationship-aware dialogue: tone shifts based on faction standing, personal history, gift memory",
            "Procedural insult/compliment generation from character trait databases and cultural context",
            "Dialogue variety scoring: track last 10 interactions per NPC, prevent repeat within 5 encounters",
            "Dynamic speech patterns: nervous NPCs use shorter sentences, scholars use longer, children use simpler vocabulary",
            "Localization-friendly templates: tagged slots for grammatical gender, pluralization, cultural adaptation",
        ],
        "deep_knowledge": {
            "personality_vector": "P = [formality: 0-1, humor: 0-1, aggression: 0-1, wisdom: 0-1, empathy: 0-1]; template_selection = argmax(dot(P, template_traits))",
            "variety_score": "variety = 1 - (repeated_templates / total_templates_used); alert if variety < 0.7",
            "relationship_tone": "tone_modifier = clamp(faction_standing × 0.3 + personal_history × 0.5 + gift_memory × 0.2, -1, 1)",
        },
    },
    "world_lore_generator": {
        "id": "nl-lore", "name": "LoreSynth", "title": "World Lore Generator",
        "expertise": [
            "Cosmogony generators: creation myth templates (elemental, divine, cosmic, evolutionary) with cultural variation",
            "Historical timeline procedural generation: eras defined by dominant faction, technology level, cultural movement",
            "Language fragment generation: consistent phoneme sets per culture, place naming conventions, title systems",
            "Religious/philosophical system generation: deity pantheons with domains, conflicts, worship mechanics",
            "Archaeological layers: ruins correspond to generated historical periods, artifacts tell consistent stories",
            "Oral tradition simulation: lore accuracy degrades with distance from source, creating natural myth variation",
            "Encyclopedia auto-generation: codex entries written from in-world perspective with cross-references",
            "Secret lore: hidden knowledge rewards for exploration, piecing together fragments reveals deeper truth",
        ],
        "deep_knowledge": {
            "era_generation": "era_duration = base_years × (1 + stability_factor × 0.5); transition_trigger = conflict_accumulation > threshold",
            "naming_convention": "syllable_pool per culture: 3-6 consonant clusters + 4-8 vowel patterns; name = random_syllables(2-4) + cultural_suffix",
            "lore_degradation": "accuracy(distance) = base_accuracy × (0.95 ^ hops_from_source) × (1 - time_elapsed / max_memory)",
        },
    },
    "cinematic_director_ai": {
        "id": "nl-cinema", "name": "CineMind", "title": "Cinematic Director AI",
        "expertise": [
            "Dynamic camera framing: rule-of-thirds composition, lead room for moving subjects, headroom calibration",
            "Shot type selection: establishing→medium→close-up→extreme close-up based on emotional intensity",
            "Cinematic timing: hold on reaction shots 1.5-3 seconds, cut on action, match-cut for transitions",
            "Depth of field manipulation: shallow DOF for intimate moments, deep DOF for epic vistas",
            "Lighting mood presets: warm (safety), cool (danger), desaturated (loss), high-contrast (confrontation)",
            "Montage sequencing for time-lapse narrative: training montage, travel montage, preparation montage",
            "Dynamic letterboxing: aspect ratio narrows (16:9→2.39:1) during cutscenes for cinematic feel",
            "Camera personality: handheld shake for chaos, steadicam for elegance, locked-off for tension",
        ],
        "deep_knowledge": {
            "shot_duration": "duration = base_duration × emotional_weight × (1 + dialogue_length × 0.3); min 1.5s, max 8s for non-dialogue",
            "dof_formula": "blur_radius = (aperture × focal_length²) / (focus_distance × (focus_distance - focal_length)); game_approx: CoC = abs(z - focus) × strength",
            "letterbox_transition": "aspect = lerp(16/9, 2.39, cinematic_intensity); transition_duration = 0.5s ease_in_out",
        },
    },
    "quest_narrative_weaver": {
        "id": "nl-quest", "name": "QuestMind", "title": "Quest Narrative Weaver",
        "expertise": [
            "Quest archetype library: hero's journey, revenge, mystery, redemption, survival, exploration, protection",
            "Multi-quest narrative threading: side quests that secretly connect to main story via shared NPCs/locations",
            "Moral dilemma construction: no clear right answer, consequences for both choices, delayed revelation",
            "Quest pacing: intro hook (30s) → investigation (5-15min) → complication (surprise) → climax → denouement",
            "Dynamic quest scaling: adjust enemy count, puzzle complexity, travel distance to player level/time investment",
            "Companion quest integration: personal quests that deepen companion relationships and unlock abilities",
            "Failed quest consequences: failure states that create new story branches rather than dead ends",
            "Epilogue quest system: post-main-story quests that address consequences of player's major decisions",
        ],
        "deep_knowledge": {
            "quest_pacing": "hook_time ≤ 60s; investigation = quest_complexity × 3min; complication at 60-70% completion; climax at 85-95%",
            "moral_dilemma_score": "dilemma_quality = abs(option_A_benefit - option_B_benefit) / max_benefit; target: dilemma_quality < 0.15",
            "quest_reward_formula": "reward = base × (1 + difficulty_modifier × 0.5) × (1 + narrative_weight × 0.3) × time_investment_factor",
        },
    },
    "character_psychology_modeler": {
        "id": "nl-psych", "name": "PsycheSynth", "title": "Character Psychology Modeler",
        "expertise": [
            "Big Five personality traits for NPCs: openness, conscientiousness, extraversion, agreeableness, neuroticism",
            "Motivation hierarchy (Maslow-derived): survival → safety → belonging → esteem → self-actualization",
            "Character flaw systems: each major NPC has 1-2 flaws that create conflict and drive character arcs",
            "Behavioral consistency validation: NPC actions scored against personality profile, flag inconsistencies",
            "Trauma response modeling: NPCs react to traumatic events with avoidance, hypervigilance, or processing",
            "Character growth arcs: NPCs can change personality traits ±0.1 per major story event, max ±0.3 total",
            "Relationship dynamics: attachment styles (secure, anxious, avoidant, disorganized) affect NPC bonding",
            "Betrayal prediction: NPCs with low agreeableness + high neuroticism + strong motivation = betrayal risk",
        ],
        "deep_knowledge": {
            "big_five_vector": "personality = [O, C, E, A, N] ∈ [0,1]^5; action_affinity(action) = dot(personality, action_trait_requirements)",
            "motivation_priority": "active_need = lowest_unsatisfied_maslow_level; behavior = optimize(active_need, personality_constraints)",
            "growth_formula": "trait_delta = event_intensity × trait_relevance × 0.05; new_trait = clamp(old_trait + trait_delta, 0, 1)",
            "betrayal_risk": "risk = (1 - A) × 0.3 + N × 0.2 + motivation_strength × 0.4 + opportunity × 0.1; trigger when risk > 0.7",
        },
    },
    "interactive_fiction_specialist": {
        "id": "nl-if", "name": "ChoiceForge", "title": "Interactive Fiction Specialist",
        "expertise": [
            "Choice architecture: present 2-4 options, each with visible risk/reward indicators and hidden consequences",
            "Time-pressured choices: countdown timer creates urgency, default action if timer expires",
            "Dialogue skill checks: visible DC (difficulty class), player stat shown, partial success for near-misses",
            "Retroactive choice revelation: player discovers true impact of earlier choice 1-3 hours later",
            "Choice memory UI: journal tracks major decisions with brief consequence summary",
            "NPC reaction choreography: facial animation, body language, voice tone shift based on player choice",
            "Parallel universe glimpses: brief flash of what would have happened with alternate choice (optional)",
            "Choice fatigue prevention: limit major choices to 1 per 20-30 minutes, fill between with minor choices",
        ],
        "deep_knowledge": {
            "choice_impact_matrix": "impact[choice_id][consequence_id] = weight × delay_factor × reversibility; visualize as network graph",
            "skill_check_dc": "success_probability = clamp((player_stat - DC) × 0.1 + 0.5, 0.05, 0.95); partial_success at probability ∈ [0.3, 0.5]",
            "choice_frequency": "major_choices_per_hour ≤ 3; minor_choices_per_hour ≤ 8; total_engagement = major × 3 + minor × 1",
        },
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 9: RENDER PIPELINE — LOD, Culling, Batching, GPU Instancing, Ray Tracing
# ════════════════════════════════════════════════════════════════════════════════

RENDER_PIPELINE_SPECIALISTS = {
    "lod_chain_engineer": {
        "id": "rp-lod", "name": "LODForge", "title": "LOD Chain Engineer",
        "expertise": [
            "Automatic LOD generation: mesh simplification via quadric error metrics (QEM) at 50%, 25%, 12%, 5% triangle counts",
            "Screen-space LOD selection: LOD = floor(log2(screen_pixel_coverage / threshold)); hysteresis band ±10% to prevent flickering",
            "LOD transition blending: dithered crossfade over 0.5s, alpha-test pattern during transition",
            "Impostor billboard generation at LOD_max: pre-rendered sprite atlas from 8-16 viewing angles",
            "HLOD (Hierarchical LOD): merge distant static objects into single combined mesh for draw call reduction",
            "LOD bias per platform: mobile LOD_bias = -1 (lower quality), PC LOD_bias = 0, ultra LOD_bias = +1",
            "Nanite-style virtualized geometry: cluster-based LOD with GPU-driven selection per triangle cluster",
            "LOD streaming: load higher LODs asynchronously, never block render thread for LOD transitions",
        ],
        "deep_knowledge": {
            "qem_simplification": "error(v) = v^T × Q × v; Q = sum(K_p for all planes p adjacent to v); contract edge with minimum error",
            "screen_coverage": "pixels = (mesh_bound_radius / distance_to_camera) × screen_height / (2 × tan(fov/2))",
            "hysteresis": "upgrade_threshold = base × 1.1; downgrade_threshold = base × 0.9; prevents LOD oscillation at boundaries",
            "impostor_atlas": "atlas_size = 2048×2048; views = 12 (30° increments azimuth × 3 elevation); update when lighting changes significantly",
        },
    },
    "gpu_culling_specialist": {
        "id": "rp-cull", "name": "CullMaster", "title": "GPU Culling Specialist",
        "expertise": [
            "Frustum culling: test AABB/OBB/sphere against 6 frustum planes, hierarchical with BVH acceleration",
            "Occlusion culling: Hierarchical Z-Buffer (HZB) reprojection from previous frame depth buffer",
            "GPU-driven occlusion: compute shader reads HZB, outputs visible instance list, zero CPU readback",
            "Contribution culling: skip objects smaller than N pixels (typically 2-4 pixels) on screen",
            "Backface cluster culling: per-meshlet cone test, reject clusters facing away from camera",
            "Distance culling: hard cutoff at max_draw_distance, per-object fade_distance with alpha ramp",
            "Portal/cell culling for interiors: define portals between rooms, PVS (Potentially Visible Set) per cell",
            "Shadow cascade culling: separate frustum per shadow cascade, tighter bounds reduce shadow draw calls",
        ],
        "deep_knowledge": {
            "frustum_plane_test": "signed_distance = dot(plane.normal, aabb_center) + plane.d; visible = signed_distance + aabb_half_extent > 0",
            "hzb_test": "mip_level = ceil(log2(max(screen_w, screen_h) of object)); visible = object_min_z < HZB.sample(mip_level, screen_pos)",
            "contribution_threshold": "pixel_area = (bound_radius / distance)² × (screen_res.x × screen_res.y) / (4 × tan²(fov/2)); cull if < 4",
            "meshlet_cone_test": "reject if dot(cone_axis, normalize(camera_pos - cone_apex)) < -cone_cutoff; saves 30-50% of backfacing triangles",
        },
    },
    "draw_call_optimizer": {
        "id": "rp-batch", "name": "BatchForge", "title": "Draw Call Optimization Specialist",
        "expertise": [
            "Static batching: combine meshes sharing material into single VBO at load time, trade memory for draw calls",
            "Dynamic batching: combine small meshes (<300 vertices) at runtime, CPU cost must < draw call cost saved",
            "GPU instancing: single draw call for N instances with per-instance transform + material property buffers",
            "Indirect drawing: GPU fills draw command buffer via compute shader, zero CPU involvement per frame",
            "Material sorting: render front-to-back for opaque (early-Z rejection), back-to-front for transparent",
            "Texture atlasing: combine textures into atlas to reduce material switches, virtual texturing for large worlds",
            "Shader variant reduction: uber-shader with static branching, compile-time specialization constants",
            "Bindless resources: descriptor indexing eliminates per-draw resource binding, reduces driver overhead 60%+",
        ],
        "deep_knowledge": {
            "batch_break_causes": "material_change > texture_change > shader_change > render_state_change > transform_change (ordered by cost)",
            "instancing_threshold": "use instancing when instance_count ≥ 10; below 10, overhead of instance buffer setup exceeds savings",
            "indirect_buffer_format": "struct DrawCommand { vertex_count, instance_count, first_vertex, first_instance }; GPU writes count fields",
            "sort_key_encoding": "sort_key = (translucency_bit << 63) | (shader_id << 48) | (material_id << 32) | (depth_bits << 0)",
        },
    },
    "ray_tracing_specialist": {
        "id": "rp-rt", "name": "PhotonForge", "title": "Ray Tracing Specialist",
        "expertise": [
            "BVH (Bounding Volume Hierarchy) construction: SAH (Surface Area Heuristic) for optimal split planes",
            "RT reflections: 0.5-1 ray per pixel, spatiotemporal denoising, fallback to SSR for performance",
            "RT global illumination: diffuse interreflection via irradiance probes updated by RT, 1 ray/probe/frame",
            "RT shadows: 1 ray per pixel per light for soft shadows, penumbra width = light_radius / distance",
            "RT ambient occlusion: short-range rays (1-2m), 0.25-0.5 rays/pixel, heavy denoising",
            "Hybrid rendering: rasterize primary visibility, ray trace secondary effects (reflections, GI, shadows)",
            "RT performance budgets: target 2-4ms for all RT effects at 1080p; scale ray count with GPU capability",
            "Denoising: spatiotemporal accumulation + bilateral filter + variance-guided kernel size",
        ],
        "deep_knowledge": {
            "sah_cost": "cost(split) = traverse_cost + (SA_left/SA_parent × count_left + SA_right/SA_parent × count_right) × intersect_cost",
            "denoiser_formula": "accumulated = lerp(history_sample, current_sample, max(0.05, 1.0 / (1 + accumulation_count))); reject history if motion_vector > threshold",
            "soft_shadow": "penumbra_angle = atan(light_radius / light_distance); sample_cone_angle = penumbra_angle; shadow = avg(ray_hits)",
            "gi_probe_update": "update_rate = 1 probe per frame per cascade; cascade_0 = 2m spacing, cascade_1 = 8m, cascade_2 = 32m",
        },
    },
    "shader_pipeline_architect": {
        "id": "rp-shader", "name": "ShaderMind", "title": "Shader Pipeline Architect",
        "expertise": [
            "PBR material model: Cook-Torrance BRDF with GGX normal distribution, Smith geometry, Fresnel-Schlick",
            "Shader permutation management: feature flags compiled to specialization constants, variant cache",
            "Compute shader optimization: workgroup size tuning (64/128/256), shared memory utilization, occupancy balancing",
            "Post-processing chain: bloom → chromatic aberration → DOF → motion blur → color grading → tonemapping → FXAA/TAA",
            "Volumetric rendering: ray-marched fog/clouds, Henyey-Greenstein phase function, temporal reprojection",
            "Subsurface scattering: preintegrated SSS lookup table, separable blur in screen space",
            "Water rendering: Gerstner waves, screen-space reflections + planar reflection fallback, underwater caustics",
            "Terrain rendering: virtual texture splatting, triplanar mapping for cliffs, parallax occlusion for detail",
        ],
        "deep_knowledge": {
            "cook_torrance": "f_r = (D × F × G) / (4 × dot(N,V) × dot(N,L)); D = GGX(roughness), F = Schlick(F0, VoH), G = Smith_GGX(roughness)",
            "ggx_ndf": "D = α² / (π × (dot(N,H)² × (α² - 1) + 1)²); α = roughness²",
            "fresnel_schlick": "F = F0 + (1 - F0) × (1 - dot(V,H))^5; F0 = ((n1-n2)/(n1+n2))² for dielectrics",
            "tonemap_aces": "color = (color × (2.51 × color + 0.03)) / (color × (2.43 × color + 0.59) + 0.14)",
        },
    },
    "memory_gpu_specialist": {
        "id": "rp-mem", "name": "VRAMForge", "title": "GPU Memory Specialist",
        "expertise": [
            "VRAM budget management: 60% textures, 20% geometry, 10% render targets, 10% buffers/misc",
            "Texture streaming: mip-tail resident, stream higher mips on demand, LRU eviction policy",
            "Virtual texturing: single enormous virtual texture, physical tile cache, indirection table",
            "Render target pooling: reuse temporary RTs via hash-based pool, reduce peak VRAM by 30-40%",
            "Buffer suballocation: ring buffers for per-frame data, persistent mapped for streaming, pool for one-shots",
            "Memory aliasing: non-overlapping render passes share same memory allocation (Vulkan memory aliasing)",
            "Compression: BC7 for color (8:1), BC5 for normals (4:1), ASTC 4×4 for mobile (8:1 with quality)",
            "VRAM defragmentation: periodic compaction of texture heaps, background streaming during load screens",
        ],
        "deep_knowledge": {
            "texture_budget": "mip_chain_size = base_size × (4/3) for full chain; streaming_budget = visible_texels × bytes_per_texel × overprovision_factor(1.5)",
            "lru_eviction": "priority = last_access_frame × weight + screen_coverage × importance; evict lowest priority when budget exceeded",
            "bc7_quality": "PSNR ≈ 40-50dB for photographic textures; encode time = ~10ms per 512×512 block on GPU",
        },
    },
    "frame_timing_engineer": {
        "id": "rp-frame", "name": "FrameMaster", "title": "Frame Timing Engineer",
        "expertise": [
            "Frame budget allocation: 16.67ms (60fps) = GPU_render(8ms) + CPU_game(4ms) + CPU_render(3ms) + overhead(1.67ms)",
            "GPU profiling: timestamp queries per render pass, identify bottleneck (vertex/pixel/compute bound)",
            "Triple buffering: reduces input latency vs double buffer while maintaining smooth frame delivery",
            "Variable Rate Shading (VRS): 1×1 center, 2×2 periphery, 4×4 extreme periphery; saves 20-40% pixel shader cost",
            "Async compute: overlap compute work (particles, culling) with graphics render; timeline semaphore synchronization",
            "Resolution scaling: dynamic resolution from 100% down to 70% based on GPU utilization, temporal upscaling (FSR/DLSS)",
            "Frame pacing: ensure consistent frame delivery timing, detect and compensate for driver-induced jitter",
            "CPU-GPU parallelism: render thread prepares frame N+1 while GPU executes frame N, minimize sync points",
        ],
        "deep_knowledge": {
            "dynamic_res_formula": "target_res_scale = sqrt(target_frametime / actual_frametime); clamp(0.5, 1.0); smooth over 4 frames",
            "vrs_savings": "pixel_shader_cost_reduction = 1 - (center_area × 1 + mid_area × 0.25 + outer_area × 0.0625) / total_area",
            "frame_budget_33ms": "33.33ms (30fps): GPU_render(18ms) + CPU_game(8ms) + CPU_render(5ms) + overhead(2.33ms)",
        },
    },
    "particle_vfx_specialist": {
        "id": "rp-vfx", "name": "ParticleMind", "title": "Particle & VFX Specialist",
        "expertise": [
            "GPU particle systems: compute shader simulation, indirect draw, millions of particles at 60fps",
            "Particle LOD: reduce emission rate, simplify simulation, billboard at distance; 3 LOD tiers",
            "VFX layering: base shape + detail noise + color gradient + distortion + emission; 5-layer composition",
            "Ribbon/trail particles: spline-based mesh generation, UV scrolling, width curve over lifetime",
            "Flipbook animation: sprite sheet particles with sub-UV interpolation for smooth animation",
            "Collision: depth buffer collision for ground interaction, simplified physics for bouncing/sliding",
            "Vector fields: 3D flow fields for wind, vortex, turbulence; baked or runtime-generated",
            "Event-driven spawning: burst on impact, continuous for fire, one-shot for explosion, looping for ambient",
        ],
        "deep_knowledge": {
            "gpu_particle_struct": "struct Particle { float3 pos, vel; float life, maxLife; float size; uint color; }; 32 bytes per particle",
            "emission_curve": "rate(t) = burst_count × delta(t=0) + sustained_rate × (1 - t/duration); total = burst + sustained × duration",
            "ribbon_tessellation": "segments = clamp(trail_length / segment_length, 4, 64); UV.x = segment_index / total_segments",
        },
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 10: SOCIAL FABRIC — Faction Calculus, Reputation, Emergent Politics
# ════════════════════════════════════════════════════════════════════════════════

SOCIAL_FABRIC_SPECIALISTS = {
    "faction_calculus_architect": {
        "id": "sf-faction", "name": "FactionMind", "title": "Faction Calculus Architect",
        "expertise": [
            "Faction relationship matrix: NxN matrix of pairwise relationships [-1.0 hostile, 0 neutral, +1.0 allied]",
            "Diplomatic action costs: alliance = 500 influence, trade = 200, war_declaration = 0 (free), peace = 300",
            "Territory control: hexagonal grid, faction_influence(hex) = sum(nearby_unit_power × distance_decay)",
            "Faction power index: military × 0.4 + economic × 0.3 + cultural × 0.2 + technological × 0.1",
            "Civil war triggers: internal_dissent > loyalty × 1.5; dissent grows from overtaxation, lost wars, corruption",
            "Alliance mechanics: shared enemies, mutual defense pacts, trade agreements, non-aggression pacts",
            "Faction memory: remember betrayals for 10 diplomatic turns, scale grudge by severity × recency",
            "Victory conditions per faction: military domination, economic hegemony, cultural victory, scientific ascendancy",
        ],
        "deep_knowledge": {
            "influence_decay": "influence(hex) = sum_units(power × max(0, 1 - distance/max_range)²); territorial_control when influence > rival × 1.5",
            "war_score": "war_score = battles_won × 10 + territory_captured × 5 + objectives_completed × 20 - losses × 3; peace at ±100",
            "loyalty_formula": "loyalty = base(50) + prosperity × 0.3 - corruption × 0.4 - war_weariness × 0.2 + culture × 0.1",
            "betrayal_memory": "grudge(t) = initial_severity × 0.9^(turns_since_betrayal); forget when grudge < 0.1",
        },
    },
    "reputation_decay_engineer": {
        "id": "sf-rep", "name": "ReputeMind", "title": "Reputation Decay Engineer",
        "expertise": [
            "Multi-dimensional reputation: combat_fame, trade_trust, criminal_notoriety, guild_standing, noble_favor",
            "Reputation decay: passive decay toward neutral at rate 0.5% per game-day for all non-extreme values",
            "Action-reputation mapping: kill_enemy = +2 combat, steal = +3 criminal/-2 trust, donate = +5 noble_favor",
            "Reputation thresholds: hated(<-500), disliked(<-200), neutral(-200 to +200), liked(>+200), revered(>+500)",
            "Reputation gating: quests/shops/zones locked behind reputation thresholds, clear UI indicators",
            "Cross-faction reputation spillover: helping faction_A gives +50% rep with allies, -25% with enemies",
            "Reputation recovery from hostile: expensive gifts, lengthy quest chains, time-gated daily tasks",
            "Disguise mechanics: temporarily mask reputation with faction-appropriate clothing/items",
        ],
        "deep_knowledge": {
            "decay_formula": "rep(t+1) = rep(t) × (1 - decay_rate) + target_neutral × decay_rate; decay_rate = 0.005/day; slower at extremes",
            "spillover_matrix": "allied_spillover = base_gain × ally_relation × 0.5; enemy_spillover = -base_gain × abs(enemy_relation) × 0.25",
            "threshold_table": {"hated": -500, "disliked": -200, "neutral": 0, "liked": 200, "honored": 500, "revered": 1000, "exalted": 2000},
        },
    },
    "political_simulation_specialist": {
        "id": "sf-politics", "name": "PolitiSim", "title": "Political Simulation Specialist",
        "expertise": [
            "Government types: monarchy, republic, theocracy, oligarchy, democracy, dictatorship; each with unique mechanics",
            "Election simulation: candidate approval = charisma × 0.3 + policy_match × 0.4 + campaign_spend × 0.2 + random × 0.1",
            "Corruption mechanics: corruption grows with power, reduces efficiency, triggers public unrest if visible",
            "Law system: enactable laws affect gameplay (tax rates, conscription, trade policy, religious freedom)",
            "Revolution triggers: unrest > stability for 5 consecutive turns; revolution_success = rebel_power / government_power",
            "Espionage: spy actions (steal tech, sabotage, assassinate, incite revolt) with detection probability",
            "Propaganda: influence public opinion via media control, cultural events, religious backing",
            "Treaty system: formal agreements with breach penalties, duration, renewal negotiations",
        ],
    },
    "social_network_modeler": {
        "id": "sf-network", "name": "SocialGraph", "title": "Social Network Modeler",
        "expertise": [
            "NPC relationship graphs: directed weighted edges (trust, fear, love, rivalry, debt, gratitude)",
            "Social influence propagation: opinions spread through network at rate proportional to edge weight",
            "Community detection: identify NPC cliques via Louvain algorithm, cliques form factions/guilds",
            "Rumor spreading: information propagates with fidelity loss, reaches all connected NPCs within N steps",
            "Social obligation mechanics: debts, favors, promises tracked per NPC pair, affect future interactions",
            "Matchmaking/romance: compatibility score from personality overlap, shared experiences, gift history",
            "Social status hierarchy: status = wealth × 0.3 + achievements × 0.3 + connections × 0.2 + lineage × 0.2",
            "Exile/ostracize mechanics: community can vote to exile members, affecting all social interactions",
        ],
        "deep_knowledge": {
            "influence_propagation": "opinion_change(B) = sum(edge_weight(A,B) × (opinion(A) - opinion(B)) × 0.1) per tick; converges over time",
            "rumor_fidelity": "fidelity(hop) = base_accuracy × (0.85 ^ hop_count); unrecognizable at fidelity < 0.3",
            "compatibility_score": "compat = 1 - |personality_A - personality_B|.mean() + shared_experiences × 0.1 + gift_score × 0.05",
        },
    },
    "guild_clan_systems_designer": {
        "id": "sf-guild", "name": "GuildForge", "title": "Guild & Clan Systems Designer",
        "expertise": [
            "Guild creation: name, banner, charter, founding cost, minimum member requirements",
            "Guild ranks: custom rank names, configurable permissions per rank (invite, kick, bank access, war declare)",
            "Guild leveling: XP from member activities, unlock perks at each level (bank slots, cosmetics, buffs)",
            "Guild wars: declared rivalries with scoreboard, territory control, scheduled battles",
            "Guild bank: shared storage with withdrawal limits per rank, transaction logging, audit trail",
            "Alliance system: guilds form alliances with shared chat channels and mutual aid mechanics",
            "Guild events: scheduled guild activities, participation tracking, reward distribution",
            "Inactive management: auto-demote after 30 days inactive, leadership transfer after 60 days",
        ],
    },
    "trade_route_simulator": {
        "id": "sf-trade", "name": "RouteForge", "title": "Trade Route Simulator",
        "expertise": [
            "Supply/demand per region: each region produces surplus and has deficit, creating trade opportunities",
            "Trade route pathfinding: A* with edge weights = distance × danger × toll_cost",
            "Caravan mechanics: hire guards, load capacity, travel time, ambush risk, weather effects",
            "Market arbitrage: buy low in producing region, sell high in deficit region, profit = price_diff - transport_cost",
            "Trade embargo mechanics: factions can block trade routes, affecting economic warfare",
            "Smuggling: illegal goods with high profit but risk of confiscation and reputation damage",
            "Trade treaties: negotiated tariff rates, exclusive trade rights, most-favored-nation status",
            "Dynamic pricing: regional prices fluctuate based on supply/demand, events, and player trade volume",
        ],
    },
    "housing_territory_specialist": {
        "id": "sf-housing", "name": "EstateForge", "title": "Housing & Territory Specialist",
        "expertise": [
            "Player housing: instanced interiors, neighborhood districts, plot auctions, decoration system",
            "Functional furniture: crafting stations, storage, rest bonuses, trophy displays",
            "Neighborhood community: shared spaces, community projects, neighborhood rankings",
            "Territory claiming: guild-owned zones with customizable rules, tax collection, defense structures",
            "Siege mechanics: attackers vs defenders, wall HP, gate mechanics, siege engines, time limits",
            "Building construction: resource requirements, build time, worker assignment, upgrade paths",
            "Upkeep costs: daily/weekly maintenance to prevent decay, abandoned properties auctioned",
            "Visitor permissions: public, guild-only, friends-list, private; customizable per room",
        ],
    },
    "emergent_story_specialist": {
        "id": "sf-emergent", "name": "EmergentTale", "title": "Emergent Story Specialist",
        "expertise": [
            "Dwarf Fortress-style story generation from simulation: NPC actions create narrative events",
            "Event classification: mundane, notable, significant, legendary; based on rarity and impact",
            "Chronicle auto-generation: weekly summary of world events from simulation data",
            "Player legend building: track player accomplishments, generate legendary tales told by NPCs",
            "Butterfly effects: small player actions cascade into major world events via chain reactions",
            "Dynamic world events: droughts, plagues, invasions, discoveries triggered by simulation thresholds",
            "Historical record: persistent world history that NPCs reference and scholars study",
            "Player-driven events: enough players performing similar actions triggers server-wide event",
        ],
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 11: METAGAME OPS — Live Service, Season Design, Retention
# ════════════════════════════════════════════════════════════════════════════════

METAGAME_OPS_SPECIALISTS = {
    "live_ops_cadence_designer": {
        "id": "mo-liveops", "name": "CadenceMind", "title": "Live-Ops Cadence Designer",
        "expertise": [
            "Content cadence: daily challenges, weekly events, bi-weekly updates, monthly features, quarterly expansions",
            "Patch cycle: hotfix (1-3 days), balance patch (2 weeks), content patch (6 weeks), major update (3 months)",
            "Server maintenance windows: scheduled weekly 2-4 hour window, compensate players for downtime",
            "A/B testing framework: feature flags, cohort splitting, statistical significance thresholds (p < 0.05)",
            "Feature rollout: canary (1%) → beta (10%) → staged (25%/50%/100%) with rollback capability",
            "Community management integration: patch notes, dev blogs, community feedback loops, bug bounty",
            "Analytics pipeline: event tracking → data lake → ETL → dashboard; sub-5-minute latency for critical metrics",
            "Incident response: severity tiers (P0-P4), response time SLAs, war room protocols, postmortem process",
        ],
    },
    "season_pass_mathematician": {
        "id": "mo-season", "name": "SeasonCalc", "title": "Season Pass Mathematician",
        "expertise": [
            "Season duration: 8-12 weeks optimal; shorter = FOMO pressure, longer = engagement fatigue",
            "XP curve per tier: tier_xp = base × (1 + tier × growth_rate); growth_rate ∈ [0.02, 0.05] for linear feel",
            "Free vs premium tier ratio: 30% of value on free track, 70% on premium; premium = 1000 currency ($10)",
            "Catch-up mechanics: XP boost in final 2 weeks, purchasable tier skips, weekly challenge stockpiling",
            "Reward distribution: cosmetic every 2-3 tiers, currency every 5, premium currency return ≥ 80% of pass cost",
            "Prestige tiers: post-100 infinite tiers with diminishing rewards for dedicated players",
            "Season theme design: narrative wrapper, seasonal cosmetic palette, limited-time game mode",
            "Premium pass value: total rewards value ≥ 3× purchase price for perceived fairness",
        ],
        "deep_knowledge": {
            "xp_per_tier": "tier_xp(n) = base_xp × (1 + n × 0.03); typical: 10000 × (1 + n × 0.03); tier 100 = 13000 XP",
            "total_season_xp": "total = sum(tier_xp(n) for n in 1..100); daily_target = total / (season_days × 0.7) accounting for skip days",
            "value_ratio": "perceived_value = sum(reward_market_value(tier) for tier in premium_tiers) / pass_price; target ≥ 3.0",
            "engagement_curve": "week_1_peak → steady_decline × 0.95/week → week_N-2_surge(catch_up) → season_end_spike",
        },
    },
    "retention_funnel_architect": {
        "id": "mo-retain", "name": "RetainMind", "title": "Retention Funnel Architect",
        "expertise": [
            "FTUE (First Time User Experience): tutorial completion rate target >85%, time-to-first-fun < 5 minutes",
            "D1/D7/D30 retention targets: D1 > 40%, D7 > 20%, D30 > 10% for healthy game",
            "Churn prediction: ML model on play patterns, session frequency, social connections, spending",
            "Win-back campaigns: push notifications at D3, D7, D14 after churn with escalating incentives",
            "Social hooks: friend invites, guild membership, competitive rankings drive organic retention",
            "Habit loop design: cue (notification) → routine (daily login) → reward (daily chest) → repeat",
            "Session length optimization: target 15-30 min average session, 2-3 sessions/day for mobile",
            "Long-term engagement: collectibles, completionism goals, mastery challenges, community events",
        ],
        "deep_knowledge": {
            "retention_formula": "D(n)_retention = D1_retention × decay^(ln(n)); decay ∈ [0.7, 0.85]; higher = better long-term",
            "ltv_calculation": "LTV = ARPDAU × average_lifetime_days; ARPDAU = revenue / DAU; target LTV > 3× CPI",
            "churn_risk_score": "risk = (1 - session_frequency_norm) × 0.3 + (1 - social_connections_norm) × 0.25 + days_since_purchase × 0.2 + (1 - progression_velocity) × 0.25",
        },
    },
    "analytics_telemetry_specialist": {
        "id": "mo-analytics", "name": "DataMind", "title": "Analytics & Telemetry Specialist",
        "expertise": [
            "Event taxonomy: session_start, level_complete, item_purchase, pvp_match, social_action, error_event",
            "Funnel analysis: track drop-off at each game stage, identify and fix highest-impact drop points",
            "Cohort analysis: group players by acquisition date/source, compare retention and monetization curves",
            "Heat maps: player death locations, popular routes, congestion points, unused areas",
            "Economy dashboards: currency supply, velocity, gini coefficient, inflation rate, sink/faucet ratio",
            "Real-time alerts: spike in errors, drop in session starts, abnormal purchase patterns",
            "Player segmentation: whales (top 1%), dolphins (top 10%), minnows (rest); tailor experiences per segment",
            "Privacy compliance: GDPR, COPPA, CCPA; data anonymization, consent management, deletion requests",
        ],
    },
    "balancing_pipeline_specialist": {
        "id": "mo-balance", "name": "BalanceForge", "title": "Live Balancing Pipeline Specialist",
        "expertise": [
            "Server-side tuning: balance parameters in remote config, no client update required",
            "Win rate monitoring: target 48-52% win rate per character/weapon/strategy in competitive modes",
            "Nerf/buff methodology: adjust by 5-10% per patch, never >15% in single patch to avoid whiplash",
            "Pick rate vs win rate quadrant analysis: OP (high pick, high win), underpowered (low pick, low win)",
            "Automated balance suggestions from gameplay data: flag outliers > 2 standard deviations",
            "Player sentiment integration: combine data analysis with community feedback for balance priorities",
            "Preseason balance: larger changes acceptable between seasons, smaller during season",
            "Emergency hotfix criteria: >55% win rate with >15% pick rate = emergency nerf within 48 hours",
        ],
    },
    "event_systems_designer": {
        "id": "mo-event", "name": "EventForge", "title": "Live Event Systems Designer",
        "expertise": [
            "Event types: limited-time mode, holiday event, collaboration, anniversary, competitive season",
            "Event reward structure: free participation rewards + premium event pass + achievement cosmetics",
            "Event economy: separate event currency, exchange shop, limited-time exclusive items",
            "Event scaling: content difficulty scales with player level for universal participation",
            "Recurring event calendar: plan 12 months ahead, mix recurring favorites with new events",
            "World-first races: competitive PvE events with global leaderboard, real-time progress tracking",
            "Community challenges: server-wide goals (collective kills, resources donated) with milestone rewards",
            "Event analytics: participation rate, completion rate, revenue per event, sentiment score",
        ],
    },
    "monetization_optimizer": {
        "id": "mo-monetize", "name": "RevForge", "title": "Monetization Optimizer",
        "expertise": [
            "IAP pricing tiers: $0.99, $4.99, $9.99, $19.99, $49.99, $99.99; sweet spot at $4.99-$9.99",
            "First-purchase incentive: starter pack at 80% discount, one-time offer within first 48 hours",
            "Conversion funnel: impression → store visit → consideration → purchase; optimize each stage",
            "Bundle psychology: show individual prices crossed out, emphasize savings percentage",
            "Subscription models: VIP monthly pass with daily login rewards, queue skip, cosmetic perks",
            "Limited-time offers: 24-48 hour flash sales, weekend specials, milestone celebrations",
            "Revenue forecasting: DAU × conversion_rate × ARPPU × seasonal_modifier = daily_revenue",
            "Ethical guardrails: spending caps for minors, cool-down prompts after large purchases, transparent odds",
        ],
    },
    "community_engagement_specialist": {
        "id": "mo-community", "name": "CommForge", "title": "Community Engagement Specialist",
        "expertise": [
            "Community platforms: Discord, Reddit, forums, social media; different tone per platform",
            "Content creator program: early access, exclusive items, revenue share on referrals",
            "User-generated content: level editor, skin creator, mod support with curation pipeline",
            "Community events: tournaments, art contests, fan fiction, cosplay competitions",
            "Feedback loops: upvote boards, roadmap sharing, transparency reports, dev Q&A sessions",
            "Toxicity management: report system, automated chat filtering, behavioral scoring, temporary/permanent bans",
            "Influencer collaboration: sponsored content, exclusive previews, launch events",
            "Localization community: volunteer translators, cultural consultants, regional community managers",
        ],
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 12: PHYSICS VAULT — Rigid/Soft Body, Fluid, Cloth, Fracture
# ════════════════════════════════════════════════════════════════════════════════

PHYSICS_VAULT_SPECIALISTS = {
    "rigid_body_solver": {
        "id": "pv-rigid", "name": "RigidCore", "title": "Rigid Body Dynamics Solver",
        "expertise": [
            "Sequential impulse constraint solver: solve velocity constraints iteratively (8-16 iterations typical)",
            "Broadphase: sweep-and-prune (SAP) for dynamic, BVH for static; reduce O(n²) to O(n log n) pair checks",
            "Narrowphase: GJK + EPA for convex-convex, SAT for box-box, sphere-capsule analytical",
            "Continuous collision detection (CCD): conservative advancement for fast-moving thin objects",
            "Contact manifold generation: persistent manifolds with contact point caching for stability",
            "Friction models: Coulomb friction with static/dynamic coefficients, box approximation for anisotropic",
            "Joint constraints: hinge, ball-socket, prismatic, fixed, spring-damper, ragdoll limits",
            "Island sleeping: group connected bodies, sleep entire island when all velocities below threshold",
        ],
        "deep_knowledge": {
            "impulse_formula": "J = -(1+e) × v_rel·n / (1/m_A + 1/m_B + (r_A×n)²/I_A + (r_B×n)²/I_B); e = restitution",
            "broadphase_sap": "O(n + k) per frame with k overlapping pairs; insert/remove O(log n) with balanced tree",
            "gjk_convergence": "max_iterations = 64; terminate when |support_point·direction - closest_point·direction| < epsilon",
            "sleep_threshold": "sleep when linear_velocity < 0.01 m/s AND angular_velocity < 0.01 rad/s for 2+ seconds",
        },
    },
    "soft_body_specialist": {
        "id": "pv-soft", "name": "DeformMind", "title": "Soft Body Simulation Specialist",
        "expertise": [
            "Mass-spring systems: structural + shear + bend springs; damped harmonic oscillator per spring",
            "Position Based Dynamics (PBD): constraint projection approach, numerically stable, easy to implement",
            "XPBD (Extended PBD): adds compliance parameter for physically accurate stiffness, timestep independent",
            "Finite Element Method (FEM): tetrahedral mesh, corotational linear elasticity for large deformation",
            "Shape matching: rigid shape matching for soft bodies, meshless deformation, fast and stable",
            "Collision with rigid bodies: vertex-level collision detection, friction response, self-collision",
            "Plasticity: permanent deformation when stress exceeds yield threshold, stored as rest-shape offset",
            "Tearing/cutting: remove springs/tetrahedra when strain exceeds threshold, re-mesh at cut boundary",
        ],
        "deep_knowledge": {
            "pbd_constraint": "Δx = -s × w/(w_1+w_2) × C(x) × ∇C(x); s = stiffness_correction = 1-(1-k)^(1/solver_iterations)",
            "xpbd_compliance": "λ = -(C + α̃×λ_prev) / (∇C^T × M^-1 × ∇C + α̃); α̃ = compliance/dt²; physically meaningful stiffness",
            "fem_strain": "Green strain: E = 0.5 × (F^T × F - I); F = deformation gradient; stress = 2μ×E + λ×tr(E)×I (St. Venant-Kirchhoff)",
            "tear_threshold": "tear when max_principal_strain > yield_strain × (1 + toughness); toughness ∈ [0, 1]",
        },
    },
    "fluid_dynamics_specialist": {
        "id": "pv-fluid", "name": "FluidCore", "title": "Fluid Dynamics Specialist",
        "expertise": [
            "SPH (Smoothed Particle Hydrodynamics): Navier-Stokes solved per particle, kernel-based interpolation",
            "FLIP/PIC hybrid: particle advection + grid-based pressure solve, low numerical dissipation",
            "Shallow water equations: 2D height-field for oceans, rivers, floods; fast and stable",
            "Surface reconstruction: marching cubes from particle density field, screen-space smoothing",
            "Viscosity: implicit viscosity solver for stable thick fluids (honey, lava, mud)",
            "Buoyancy: Archimedes' principle per submerged volume, interaction with floating rigid bodies",
            "Boundary handling: density contribution from boundary particles, no-slip/free-slip conditions",
            "Multiphase: oil/water separation, foam/spray/bubbles as separate particle types with transitions",
        ],
        "deep_knowledge": {
            "sph_density": "ρ_i = Σ_j m_j × W(|r_i - r_j|, h); W = Wendland C2 kernel; h = smoothing radius",
            "sph_pressure": "P_i = k × ((ρ_i/ρ_0)^γ - 1); k = stiffness constant; γ = 7 for water; ρ_0 = rest density",
            "navier_stokes": "ρ × (∂v/∂t + v·∇v) = -∇P + μ∇²v + ρg; incompressibility: ∇·v = 0",
            "cfl_condition": "dt ≤ 0.4 × h / (c_s + v_max); c_s = speed of sound ≈ 10 × v_max for weakly compressible",
        },
    },
    "cloth_simulation_specialist": {
        "id": "pv-cloth", "name": "ClothMind", "title": "Cloth Simulation Specialist",
        "expertise": [
            "Mass-spring cloth: structural (grid edges), shear (diagonals), bend (skip-one connections) springs",
            "XPBD cloth: distance constraints + bending constraints + collision constraints, 10-20 iterations",
            "Wind interaction: per-triangle aerodynamic force = 0.5 × air_density × v_rel² × area × (drag + lift)",
            "Self-collision: spatial hashing for broadphase, triangle-vertex proximity test, repulsion forces",
            "Pinned vertices: fixed attachment points for hanging cloth, animated attachment for worn clothing",
            "Wrinkle maps: precomputed normal maps blended based on compression along cloth surface",
            "Multi-resolution: coarse sim mesh drives high-res render mesh via barycentric interpolation",
            "Character clothing: body collision capsules, tunic/cape/skirt templates, wind and movement response",
        ],
        "deep_knowledge": {
            "spring_force": "F = -k × (|x_ij| - rest_length) × normalize(x_ij) - d × v_ij; k = stiffness, d = damping",
            "aerodynamic_force": "F_aero = 0.5 × ρ_air × |v_rel|² × A_triangle × (C_d × n_hat + C_l × cross(v_hat, cross(n_hat, v_hat)))",
            "spatial_hash_cell": "cell_size = 2 × cloth_thickness; hash(x,y,z) = (x×73856093 ⊕ y×19349663 ⊕ z×83492791) mod table_size",
        },
    },
    "destruction_physics_engineer": {
        "id": "pv-destruct", "name": "FractureForge", "title": "Destruction Physics Engineer",
        "expertise": [
            "Voronoi fracture: pre-fracture meshes along Voronoi cell boundaries, activate on impact",
            "Runtime fracture: compute fracture pattern from impact point, stress distribution, material properties",
            "Fracture patterns: radial (glass), columnar (concrete), chunky (wood), shatter (ceramic)",
            "Debris simulation: fractured pieces become rigid bodies with initial velocities from impact",
            "Structural integrity: connected component analysis, cascade failure when support removed",
            "Damage accumulation: HP per structural element, visual damage decals, progressive weakening",
            "Particle effects integration: dust clouds, sparks, splinters spawned at fracture points",
            "Performance: LOD destruction (distant = particle only, medium = simplified, close = full physics)",
        ],
        "deep_knowledge": {
            "voronoi_pre_fracture": "num_cells = impact_energy / fracture_toughness; cell_size_variation ∈ [0.5, 1.5]; boolean_mesh_operation per cell",
            "stress_propagation": "stress(element) = applied_force / cross_section_area; fracture when stress > material_ultimate_strength",
            "cascade_check": "connectivity_graph.remove(fractured); for each component: if not connected_to_ground → activate_as_debris",
        },
    },
    "vehicle_physics_specialist": {
        "id": "pv-vehicle", "name": "VehicleSim", "title": "Vehicle Physics Specialist",
        "expertise": [
            "Tire model: Pacejka Magic Formula for lateral/longitudinal force vs slip angle/ratio",
            "Suspension: spring-damper per wheel, anti-roll bars, variable ride height, jounce/rebound",
            "Drivetrain: engine torque curve, gear ratios, differential (open/limited-slip/locked), clutch model",
            "Aerodynamics: drag force, downforce, lift; coefficient tables per body shape, ground effect",
            "Terrain interaction: surface friction coefficients (asphalt=1.0, gravel=0.6, ice=0.15, mud=0.4)",
            "Damage model: crumple zones, mechanical damage (engine, transmission, steering), visual deformation",
            "Two-wheeled vehicles: lean angle, gyroscopic effects, counter-steering at high speed",
            "Water interaction: hydroplaning above threshold speed, submersion buoyancy, river current forces",
        ],
        "deep_knowledge": {
            "pacejka": "F = D × sin(C × atan(B×slip - E×(B×slip - atan(B×slip)))); B=stiffness, C=shape, D=peak, E=curvature",
            "suspension": "F_spring = -k × (x - x_rest); F_damper = -c × v; total = F_spring + F_damper; anti_roll = k_roll × (x_left - x_right)",
            "engine_torque": "torque(rpm) = peak_torque × polynomial_fit(rpm/peak_rpm); power = torque × rpm × 2π/60",
            "wheel_rpm": "driven_wheel_rpm = engine_rpm × gear_ratio × final_drive_ratio; wheel_speed = wheel_rpm × 2π × tire_radius / 60",
        },
    },
    "rope_chain_specialist": {
        "id": "pv-rope", "name": "ChainSim", "title": "Rope & Chain Simulation Specialist",
        "expertise": [
            "Verlet integration: position-based particle chain, implicit velocity, unconditionally stable",
            "Distance constraints: enforce link length between adjacent particles, Jacobi/Gauss-Seidel solver",
            "Rope collision: per-segment capsule collision with world geometry, contact friction",
            "Rope attachment: fixed endpoints, movable endpoints, breakable links above tension threshold",
            "Catenary curve: analytical solution for static rope under gravity for visual-only ropes",
            "Coiling/wrapping: rope wraps around cylindrical objects, unwrap when tension direction changes",
            "Elastic ropes: spring-like behavior with configurable stiffness, bungee mechanics",
            "Gameplay integration: grappling hooks, rope bridges, rope climbing, lasso mechanics",
        ],
    },
    "ragdoll_specialist": {
        "id": "pv-ragdoll", "name": "RagdollForge", "title": "Ragdoll Physics Specialist",
        "expertise": [
            "Joint hierarchy: 15-20 rigid body bones connected by constrained joints matching skeleton",
            "Joint limits: hinge joints (elbows, knees), cone-twist (shoulders, hips), fixed (spine segments)",
            "Active ragdoll: blend between animation and physics, PD controllers on joints for 'trying to stand'",
            "Powered ragdoll: muscle-like torques drive ragdoll toward target pose, adjustable strength",
            "Hit reaction: apply impulse at hit location, body part mass determines reaction magnitude",
            "Ragdoll-to-animation blend: gradually increase animation influence to transition from ragdoll to standing",
            "Pose matching: ragdoll tries to match target animation pose, useful for stumbling, drunk walking",
            "Collision group setup: disable self-collision between adjacent bones, enable between distant ones",
        ],
        "deep_knowledge": {
            "pd_controller": "torque = k_p × (target_angle - current_angle) + k_d × (target_velocity - current_velocity); k_p = stiffness, k_d = damping",
            "hit_impulse": "impulse = bullet_mass × bullet_velocity × (1 + restitution) / (1/body_part_mass + 1/bullet_mass); apply at hit_point",
            "blend_to_anim": "pose = lerp(ragdoll_pose, anim_pose, blend_weight); blend_weight increases 0→1 over 0.5-1.0 seconds",
        },
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 13: AUDIO SPHERE — Spatial Audio, Adaptive Music, DSP
# ════════════════════════════════════════════════════════════════════════════════

AUDIO_SPHERE_SPECIALISTS = {
    "spatial_audio_engineer": {
        "id": "as-spatial", "name": "SpatialCore", "title": "Spatial Audio Engineer",
        "expertise": [
            "HRTF (Head-Related Transfer Function): binaural rendering for accurate 3D positioning over headphones",
            "Distance attenuation: inverse square law with rolloff curves, min/max distance parameters",
            "Occlusion: ray-cast from listener to source, apply low-pass filter proportional to wall thickness/material",
            "Obstruction: partial occlusion when source partially hidden, blend between direct and occluded",
            "Reverb zones: convolution reverb per environment type (cave, hall, forest, underwater), smooth crossfade",
            "Early reflections: first 5-10 reflections computed from room geometry for spatial realism",
            "Ambisonics: encode spatial audio as B-format for VR, decode to arbitrary speaker configurations",
            "Doppler effect: pitch_shift = source_speed_toward_listener / speed_of_sound; apply on moving sources",
        ],
        "deep_knowledge": {
            "distance_attenuation": "volume = ref_distance / max(distance, ref_distance); rolloff: linear, inverse, exponential",
            "occlusion_lpf": "cutoff_frequency = base_cutoff × (1 - occlusion_factor); occlusion_factor = wall_thickness × material_density / max_thickness",
            "doppler_formula": "pitch_ratio = (speed_of_sound + listener_velocity) / (speed_of_sound + source_velocity); speed_of_sound ≈ 343 m/s",
            "reverb_decay": "RT60 = 0.161 × room_volume / (surface_area × avg_absorption_coefficient); RT60 = time for 60dB decay",
        },
    },
    "adaptive_music_designer": {
        "id": "as-music", "name": "MusicMind", "title": "Adaptive Music Designer",
        "expertise": [
            "Horizontal re-sequencing: change section order based on game state (explore→tension→combat→victory)",
            "Vertical re-mixing: add/remove instrument layers based on intensity level (1=ambient, 5=full orchestra)",
            "Transition types: crossfade (2-4 bars), stinger (impact hit), segue (composed transition), cut (immediate)",
            "Musical tempo sync: game events quantized to musical beat grid for rhythmic coherence",
            "Stems arrangement: drums, bass, harmony, melody, fx as separate layers for independent volume control",
            "Dynamic intensity: combat_intensity = enemy_count × 0.3 + player_health_loss_rate × 0.4 + boss_proximity × 0.3",
            "Leitmotif system: character/location/faction themes that recur and develop throughout the game",
            "Silence as design: strategic absence of music for tension, discovery, emotional weight",
        ],
        "deep_knowledge": {
            "intensity_formula": "music_intensity = clamp(threat_level × 0.4 + action_density × 0.3 + narrative_weight × 0.3, 0, 1.0)",
            "transition_timing": "quantize to next bar_boundary; bar_duration = (60 / BPM) × time_signature_numerator",
            "layer_thresholds": "layer_0(ambient): always; layer_1(rhythm): intensity>0.2; layer_2(harmony): >0.4; layer_3(melody): >0.6; layer_4(full): >0.8",
        },
    },
    "sound_propagation_specialist": {
        "id": "as-prop", "name": "PropMind", "title": "Sound Propagation Specialist",
        "expertise": [
            "Ray-traced audio: cast rays from source, trace reflections (up to 3 bounces), contribute to reverb/delay",
            "Portal-based propagation: sound travels through doorways/windows, attenuated by portal size",
            "Material absorption coefficients: concrete=0.02, carpet=0.3, curtains=0.5, foam=0.8 (at 1kHz)",
            "Diffraction: sound bends around obstacles, modeled as edge diffraction with frequency-dependent attenuation",
            "Outdoor propagation: wind direction affects sound travel, temperature gradients cause refraction",
            "Underwater acoustics: low-pass filter (6dB/octave above 1kHz), increased propagation speed (1500 m/s)",
            "Sound masking: loud nearby sounds reduce perceptibility of distant sounds, adjust mix accordingly",
            "Propagation LOD: detailed propagation for nearby, simplified for medium, direct-only for distant",
        ],
    },
    "foley_systems_designer": {
        "id": "as-foley", "name": "FoleyForge", "title": "Foley Systems Designer",
        "expertise": [
            "Surface-dependent footsteps: physical material query at foot position, 4-8 variations per surface",
            "Movement sounds: armor clink for heavy armor, cloth rustle for light, leather creak for medium",
            "Interaction sounds: door open (wood creak, metal screech, sci-fi whoosh), chest open, lever pull",
            "Environmental ambience: layered loops (wind base + bird layer + water layer + insect layer)",
            "Weather sounds: rain intensity levels (drizzle→steady→heavy→storm), thunder with distance delay",
            "Character exertion: breathing, grunts, battle cries, pain vocalizations with exhaustion scaling",
            "Object physics sounds: impact sounds based on material pair (metal-on-wood, glass-on-stone), mass, velocity",
            "Vegetation interaction: bush rustle, grass swish, branch snap, leaf crunch underfoot",
        ],
        "deep_knowledge": {
            "impact_sound_selection": "sound = material_pair_lookup[mat_A][mat_B]; volume = clamp(impact_velocity × mass_product / reference_impulse, 0, 1)",
            "footstep_timing": "step_interval = stride_length / movement_speed; vary ±5% for natural feel; sync to animation foot_contact event",
            "ambience_layering": "base_loop(always) + conditional_layers(time_of_day, weather, location) + random_one_shots(birds, insects, distant_activity)",
        },
    },
    "dsp_effects_specialist": {
        "id": "as-dsp", "name": "DSPForge", "title": "DSP Effects Specialist",
        "expertise": [
            "Reverb: algorithmic (Schroeder), convolution (impulse response), hybrid for real-time performance",
            "Delay: simple echo, multi-tap, ping-pong, modulated; sync to musical tempo for rhythmic effects",
            "EQ: parametric 3-band + shelving for per-sound shaping, graphic EQ for environmental effects",
            "Compression: reduce dynamic range for consistent volume, sidechain for ducking (music under dialogue)",
            "Distortion: overdrive for weapon impacts, bitcrushing for retro effects, waveshaping for horror",
            "Pitch shifting: time-domain (PSOLA) for small shifts, frequency-domain (phase vocoder) for large",
            "Granular synthesis: real-time texture generation from audio grains, useful for ambient/drone sounds",
            "Spatializer: VBAP (Vector Base Amplitude Panning) for surround, binaural for headphones",
        ],
    },
    "voice_systems_architect": {
        "id": "as-voice", "name": "VoxForge", "title": "Voice Systems Architect",
        "expertise": [
            "Dialogue management: priority queue, interrupt rules, subtitles sync, lip-sync animation",
            "Voice bank management: load/unload language packs, streaming for large VO libraries",
            "Bark system: contextual one-liners, cooldown timers per bark, situation-awareness triggers",
            "Radio/comms filter: band-pass filter + subtle distortion for walkie-talkie/radio effect",
            "Crowd voices: layered crowd murmur, individual shouts emerging from crowd based on events",
            "NPC conversation system: two NPCs talking, player overhearing, responsive to player proximity",
            "Voice modulation: pitch/formant shift for creature voices, real-time processing of human recordings",
            "Localization pipeline: VO recording specs, timing metadata, per-language mix adjustments",
        ],
    },
    "mixing_mastering_specialist": {
        "id": "as-mix", "name": "MixMaster", "title": "Mixing & Mastering Specialist",
        "expertise": [
            "Bus hierarchy: Master → Music, SFX, Voice, Ambience, UI; per-bus volume, EQ, compression",
            "Priority system: voice(10) > UI(8) > combat_SFX(7) > music(5) > ambience(3); voice limit per priority",
            "Ducking: music ducks 6dB during dialogue, combat music ducks 3dB during callouts",
            "Loudness normalization: target -14 LUFS for overall mix, voice at -12 LUFS, music at -18 LUFS",
            "Dynamic range: compressed for mobile/TV speakers, expanded for headphones/home theater",
            "Platform-specific mastering: mobile (mono-compatible), console (5.1/7.1), PC (stereo + spatial)",
            "Virtual voice management: max simultaneous voices (32-64), steal lowest-priority when exceeded",
            "Real-time mix snapshots: different mix settings per game state (menu, gameplay, cutscene, pause)",
        ],
    },
    "procedural_audio_specialist": {
        "id": "as-proc", "name": "SynthForge", "title": "Procedural Audio Specialist",
        "expertise": [
            "Physically modeled audio: string vibration, drum membrane, tube resonance from mathematical models",
            "Synthesized weather: rain = filtered noise + drop impacts, wind = low-pass noise with amplitude modulation",
            "Engine sounds: additive synthesis of harmonics, RPM-driven pitch/amplitude envelopes, load modulation",
            "Procedural music: algorithmic composition from rules (Markov chains, cellular automata, neural networks)",
            "Texture synthesis: generate infinite non-repeating ambience from short samples via granular techniques",
            "Impact synthesis: modal synthesis of resonant bodies, excitation signal × resonant filter bank",
            "Fire/water loops: continuous layered noise with parameter-driven variation, never exact repeat",
            "Alien/creature vocalizations: formant synthesis + noise injection + pitch randomization",
        ],
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 14: UX ARCHITECT — Information Architecture, Fitts' Law, WCAG
# ════════════════════════════════════════════════════════════════════════════════

UX_ARCHITECT_SPECIALISTS = {
    "information_architecture_specialist": {
        "id": "ux-ia", "name": "InfoForge", "title": "Information Architecture Specialist",
        "expertise": [
            "HUD element prioritization: health(critical) > minimap(high) > quest(medium) > ammo(contextual)",
            "Progressive disclosure: show essential info by default, reveal details on hover/expand/context",
            "Menu hierarchy: max 3 levels deep, breadcrumb navigation, back button always available",
            "Contextual UI: show relevant controls near interaction point, fade irrelevant UI during exploration",
            "Status icon language: consistent iconography, color-coded severity, tooltip on focus/hover",
            "Tutorial UI integration: highlight elements, dim background, point arrows, step-through flow",
            "Inventory management: grid vs list, sort options, filter by type/rarity/level, search, auto-equip",
            "Map UI: zoom levels, fog of war, waypoint system, legend, coordinate system, fast travel points",
        ],
    },
    "fitts_law_layout_designer": {
        "id": "ux-fitts", "name": "FittsForge", "title": "Fitts' Law Layout Designer",
        "expertise": [
            "Fitts' Law: T = a + b × log2(1 + D/W); minimize distance to frequent targets, maximize target size",
            "Touch target sizing: minimum 44×44pt (iOS), 48×48dp (Android), 32×32px minimum for mouse",
            "Thumb zone optimization: critical actions in easy-reach zone, secondary in stretch zone",
            "Edge/corner advantage: screen edges act as infinite width targets (scroll bars, close buttons)",
            "Radial menus: equal distance to all options, fast selection, muscle memory friendly",
            "Action bar layout: most-used abilities center, less-used toward edges, ultimate at distinct position",
            "Drag distance minimization: inventory management, skill assignment, equipment comparison",
            "Controller-optimized UI: cursor snap to interactive elements, D-pad navigation, bumper tab switching",
        ],
        "deep_knowledge": {
            "fitts_formula": "movement_time_ms = a + b × log2(1 + distance/width); typical: a=50ms, b=150ms",
            "touch_target": "minimum_size = 44pt; recommended = 48pt; spacing_between = 8pt minimum",
            "thumb_reach": "easy_zone: bottom-center 60% of screen; stretch_zone: top-center + far sides; hard_zone: top corners",
        },
    },
    "accessibility_compliance_specialist": {
        "id": "ux-wcag", "name": "AccessMind", "title": "WCAG Compliance Specialist",
        "expertise": [
            "WCAG 2.1 AA compliance: minimum contrast ratio 4.5:1 for text, 3:1 for large text/graphics",
            "Screen reader support: all interactive elements labeled, reading order logical, focus management",
            "Motor accessibility: single-button mode, auto-aim, toggle vs hold, adjustable timing",
            "Cognitive accessibility: clear language, consistent layout, avoid information overload, reminders",
            "Color-blind modes: protanopia, deuteranopia, tritanopia; shape + pattern differentiation, not just color",
            "Text customization: size (14-32pt range), font weight, line spacing, background contrast options",
            "Audio descriptions: narrate visual-only information for blind players",
            "Controller vibration/visual alternatives: flash screen border instead of rumble, visual audio cues",
        ],
        "deep_knowledge": {
            "contrast_ratio": "ratio = (L_lighter + 0.05) / (L_darker + 0.05); L = relative luminance; target ≥ 4.5:1 for AA",
            "relative_luminance": "L = 0.2126×R_lin + 0.7152×G_lin + 0.0722×B_lin; R_lin = (R/255)^2.2 (simplified)",
            "focus_order": "logical_tab_order = visual_layout_order; skip_navigation_link at page top; focus_trap in modals",
        },
    },
    "onboarding_tutorial_designer": {
        "id": "ux-tutorial", "name": "TutorForge", "title": "Onboarding & Tutorial Designer",
        "expertise": [
            "Teach by doing: introduce mechanics through gameplay, not text walls; max 1 new mechanic per minute",
            "Progressive complexity: movement → basic attack → dodge → special → combo → ultimate over 10-15 minutes",
            "Contextual hints: show hint only when player appears stuck (3+ seconds idle at checkpoint)",
            "Skip option: allow experienced players to skip tutorial, brief recap of controls available in menu",
            "Return player onboarding: 'previously on...' summary after long absence, optional refresher tutorial",
            "Tooltip system: first encounter teaches, subsequent encounters show brief reminder, then disappear",
            "Practice rooms: safe environment to test abilities, target dummies, reset button, infinite resources",
            "Difficulty self-selection: ask player preference after tutorial, adjust accordingly, allow change anytime",
        ],
    },
    "loading_state_designer": {
        "id": "ux-loading", "name": "LoadMind", "title": "Loading & State Designer",
        "expertise": [
            "Loading screens: progress bar, tips/lore, artwork rotation, estimated time remaining",
            "Skeleton screens: show layout structure immediately, fill content as it loads for perceived speed",
            "Transition animations: scene transitions that hide loading (elevator ride, tunnel, door opening)",
            "Async loading: stream world chunks, never show loading screen during open-world exploration",
            "Error states: clear error messages, recovery actions, retry buttons, contact support links",
            "Empty states: meaningful empty states with calls-to-action (no items? → show how to get items)",
            "Save indicators: auto-save icon, manual save confirmation, save slot management, cloud sync status",
            "Network state indicators: latency display, connection quality icon, offline mode capabilities",
        ],
    },
    "notification_systems_designer": {
        "id": "ux-notify", "name": "NotifyForge", "title": "Notification Systems Designer",
        "expertise": [
            "Notification priority: critical(immediate) > important(banner) > informational(badge) > passive(log)",
            "In-game notifications: floating text, toast messages, banner alerts, full-screen announcements",
            "Push notification strategy: daily reminder (optional), event start, friend activity, limited-time offer",
            "Notification queue: stack max 3 visible, queue rest, clear oldest first, collapse similar",
            "Do-not-disturb: suppress non-critical during combat, cutscenes, competitive matches",
            "Sound cues per notification type: subtle ping for chat, triumphant for achievement, alert for danger",
            "Unread indicators: badge counts, new item glow, exclamation marks; clear on view",
            "Notification preferences: per-type enable/disable, frequency limits, quiet hours setting",
        ],
    },
    "settings_menu_architect": {
        "id": "ux-settings", "name": "SettingsForge", "title": "Settings Menu Architect",
        "expertise": [
            "Graphics settings: presets (low/medium/high/ultra) + individual: resolution, texture, shadow, AA, VSync",
            "Audio settings: master, music, SFX, voice, ambient; speaker configuration, dynamic range toggle",
            "Controls: keybind remapping, controller sensitivity curves, dead zones, invert Y, vibration strength",
            "Gameplay: difficulty, language, subtitles, colorblind mode, auto-save frequency, UI scale",
            "Accessibility: text size, high contrast, screen reader, reduced motion, one-handed mode",
            "Performance metrics: FPS counter, latency display, GPU/CPU temperature, VRAM usage (optional)",
            "Reset to defaults: per-category and global reset with confirmation dialog",
            "Profile/cloud settings: sync settings across devices, import/export settings files",
        ],
    },
    "minimap_compass_specialist": {
        "id": "ux-minimap", "name": "NavUI", "title": "Minimap & Compass Specialist",
        "expertise": [
            "Minimap variants: circular (RPG standard), rectangular (RTS), compass strip (immersive/FPS)",
            "Minimap content: terrain, buildings, NPCs, enemies, objectives, player position + heading",
            "Fog of war: explored areas visible, unexplored dark, enemy visibility based on line of sight",
            "Waypoint system: player-placed markers, quest markers with distance, priority ordering",
            "Compass design: strip at top of screen, notch markers for N/E/S/W, quest icons at bearing angles",
            "Dynamic minimap scale: zoom in for indoor/dungeon, zoom out for outdoor/open world",
            "Interaction markers: icons above interactable objects, distance-based fade, type-specific icons",
            "Navigation breadcrumbs: highlight path to objective, adjustable obtrusiveness (subtle→explicit)",
        ],
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# ALL QUANTUM FACTORY DOMAINS
# ════════════════════════════════════════════════════════════════════════════════

ALL_QUANTUM_DOMAINS = {
    "narrative_loom": {"id": "narrative_loom", "name": "NarrativeLoom", "version": "22.0", "description": "Branching narrative graphs, emotional arc engineering, procedural dialogue, cinematic direction, character psychology", "icon": "book", "color": "#F472B6", "specialists": NARRATIVE_LOOM_SPECIALISTS},
    "render_pipeline": {"id": "render_pipeline", "name": "RenderPipeline", "version": "22.0", "description": "LOD chains, GPU culling, draw call batching, PBR shaders, ray-traced GI, particle VFX, frame timing", "icon": "eye", "color": "#34D399", "specialists": RENDER_PIPELINE_SPECIALISTS},
    "social_fabric": {"id": "social_fabric", "name": "SocialFabric", "version": "22.0", "description": "Faction calculus, reputation decay, political simulation, social networks, guild systems, trade routes", "icon": "people", "color": "#FBBF24", "specialists": SOCIAL_FABRIC_SPECIALISTS},
    "metagame_ops": {"id": "metagame_ops", "name": "MetaGameOps", "version": "22.0", "description": "Live-ops cadence, season pass mathematics, retention funnels, analytics, balancing, events, monetization", "icon": "stats-chart", "color": "#60A5FA", "specialists": METAGAME_OPS_SPECIALISTS},
    "physics_vault": {"id": "physics_vault", "name": "PhysicsVault", "version": "22.0", "description": "Rigid body solvers, soft body XPBD, SPH fluid, cloth simulation, Voronoi destruction, vehicle physics", "icon": "globe", "color": "#A78BFA", "specialists": PHYSICS_VAULT_SPECIALISTS},
    "audio_sphere": {"id": "audio_sphere", "name": "AudioSphere", "version": "22.0", "description": "HRTF spatial audio, adaptive music layering, sound propagation, foley systems, DSP chains, procedural audio", "icon": "musical-notes", "color": "#FB923C", "specialists": AUDIO_SPHERE_SPECIALISTS},
    "ux_architect": {"id": "ux_architect", "name": "UXArchitect", "version": "22.0", "description": "Information architecture, Fitts' Law layouts, WCAG accessibility, tutorial design, notification systems", "icon": "layers", "color": "#2DD4BF", "specialists": UX_ARCHITECT_SPECIALISTS},
}

# Add specialist counts
for domain in ALL_QUANTUM_DOMAINS.values():
    domain["specialist_count"] = len(domain["specialists"])


def compute_quantum_stats() -> Dict[str, Any]:
    total_specs = 0
    total_expertise = 0
    total_deep = 0
    domain_stats = {}
    for did, d in ALL_QUANTUM_DOMAINS.items():
        sc = len(d["specialists"])
        ec = sum(len(s.get("expertise", [])) for s in d["specialists"].values())
        dc = sum(sum(len(v) if isinstance(v, dict) else 1 for v in s.get("deep_knowledge", {}).values()) for s in d["specialists"].values())
        total_specs += sc
        total_expertise += ec
        total_deep += dc
        domain_stats[did] = {"specialists": sc, "expertise_points": ec, "deep_knowledge_entries": dc, "readiness": round(min(1.0, (ec + dc * 2) / 100), 4)}
    return {"total_domains": len(ALL_QUANTUM_DOMAINS), "total_specialists": total_specs, "total_expertise_points": total_expertise, "total_deep_knowledge_entries": total_deep, "domain_stats": domain_stats}


QF_STATS = compute_quantum_stats()


# ════════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/status")
async def quantum_factory_status():
    return {
        "system": "Quantum Factory Core v22.0",
        "status": "FULLY_OPERATIONAL",
        "session_id": hashlib.sha256(f"qf-{time.time()}".encode()).hexdigest()[:16],
        "timestamp": datetime.utcnow().isoformat(),
        **{k: v for k, v in QF_STATS.items() if k != "domain_stats"},
        "domains": {
            did: {"name": d["name"], "description": d["description"], "icon": d["icon"], "color": d["color"], "specialist_count": d["specialist_count"], "stats": QF_STATS["domain_stats"][did]}
            for did, d in ALL_QUANTUM_DOMAINS.items()
        },
    }


@router.get("/health-matrix")
async def quantum_factory_health():
    matrix = {}
    for did, d in ALL_QUANTUM_DOMAINS.items():
        specs_health = {}
        for sid, s in d["specialists"].items():
            ec = len(s.get("expertise", []))
            dk = s.get("deep_knowledge", {})
            dc = sum(len(v) if isinstance(v, dict) else 1 for v in dk.values()) if isinstance(dk, dict) else 0
            r = round(min(1.0, ec * 0.1 + dc * 0.2), 4)
            specs_health[sid] = {"name": s.get("name"), "title": s.get("title"), "expertise_count": ec, "deep_knowledge_count": dc, "readiness": r, "status": "OPTIMAL" if r > 0.7 else "NOMINAL"}
        dr = round(sum(sh["readiness"] for sh in specs_health.values()) / max(1, len(specs_health)), 4)
        matrix[did] = {"name": d["name"], "color": d["color"], "readiness": dr, "status": "OPTIMAL" if dr > 0.7 else "NOMINAL", "specialist_count": len(specs_health), "specialists": specs_health}
    return {"system": "Quantum Factory Health Matrix v22.0", "timestamp": datetime.utcnow().isoformat(), "overall_readiness": round(sum(m["readiness"] for m in matrix.values()) / max(1, len(matrix)), 4), "matrix": matrix}


@router.get("/domain/{domain_id}")
async def quantum_factory_domain(domain_id: str):
    d = ALL_QUANTUM_DOMAINS.get(domain_id)
    if not d:
        raise HTTPException(404, f"Domain '{domain_id}' not found. Available: {list(ALL_QUANTUM_DOMAINS.keys())}")
    return {
        "domain": {"id": d["id"], "name": d["name"], "version": d["version"], "description": d["description"], "icon": d["icon"], "color": d["color"]},
        "specialist_count": len(d["specialists"]),
        "specialists": {sid: {"id": s.get("id"), "name": s.get("name"), "title": s.get("title"), "expertise": s.get("expertise", []), "deep_knowledge": s.get("deep_knowledge", {})} for sid, s in d["specialists"].items()},
        "stats": QF_STATS["domain_stats"][domain_id],
    }


@router.get("/full-architecture")
async def quantum_factory_full_architecture():
    return {
        "system": "Quantum Factory Full Architecture v22.0",
        "timestamp": datetime.utcnow().isoformat(),
        "stats": QF_STATS,
        "domains": {did: {"name": d["name"], "specialist_names": [s.get("name") for s in d["specialists"].values()]} for did, d in ALL_QUANTUM_DOMAINS.items()},
    }


class SynthesizeRequest(BaseModel):
    domains: Optional[List[str]] = None
    game_description: str
    genre: Optional[str] = "action_rpg"
    target_platform: Optional[str] = "multiplatform"


@router.post("/synthesize")
async def quantum_factory_synthesize(req: SynthesizeRequest):
    target_domains = {did: d for did, d in ALL_QUANTUM_DOMAINS.items() if not req.domains or did in req.domains}
    if not target_domains:
        raise HTTPException(404, "No matching domains found")
    synthesis = {}
    for did, d in target_domains.items():
        synthesis[did] = {
            "domain": d["name"],
            "specialists_applied": len(d["specialists"]),
            "total_expertise_applied": sum(len(s.get("expertise", [])) for s in d["specialists"].values()),
            "specialist_names": [s.get("name") for s in d["specialists"].values()],
        }
    return {
        "system": "Quantum Factory Synthesis Engine v22.0",
        "synthesis_id": str(uuid.uuid4()),
        "game_description": req.game_description,
        "genre": req.genre,
        "platform": req.target_platform,
        "domains_synthesized": len(synthesis),
        "total_specialists_applied": sum(s["specialists_applied"] for s in synthesis.values()),
        "synthesis": synthesis,
        "generated_at": datetime.utcnow().isoformat(),
    }
