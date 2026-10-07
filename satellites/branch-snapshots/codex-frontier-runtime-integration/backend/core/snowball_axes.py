"""
╔════════════════════════════════════════════════════════════════════════╗
║  SNOWBALL AXES — the genuine, spec-aware advanced-choice catalog.        ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Every advanced choice in the snowball is defined here as an AXIS with   ║
║  a list of GENUINE, distinct OPTIONS. Each option carries:               ║
║                                                                        ║
║    • effect  → the concrete forge directive it applies (NOT a label).    ║
║                These keys are folded into every item skin / asset /       ║
║                gamefile so the choice produces an ACTUAL change and the   ║
║                choice-gate can prove it on every snowball step.           ║
║    • spec    → which spec the option pertains to (dimension / genre /     ║
║                era). The resolver only ever offers options that fit the   ║
║                current spec — the snowball is fully crosswired.           ║
║    • tier    → "advanced" | "core" | "basic". Every axis carries MORE     ║
║                advanced options than basic ones.                          ║
║    • unlock  → minimum snowball stage index at which the option unlocks   ║
║                (the flow escalates — richer options appear as it grows).  ║
║                                                                        ║
║  Deterministic + hand-authored (no synthetic loops). An optional LLM     ║
║  flavour pass can enrich descriptions on top, never replace the data.     ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from typing import Any

# Canonical spec vocab used by the filters below.
DIMENSIONS = ["2d", "2.5d", "3d"]
GENRE_FAMILIES = [
    "arcade", "puzzle", "platformer", "shooter", "runner", "strategy", "rpg",
    "rhythm", "action_rpg", "soulslike", "mmo", "tactics", "tycoon",
    "city_builder", "survival", "horror", "racing", "fighting", "sandbox",
    "metroidvania", "roguelike", "sim",
]


def _o(oid: str, label: str, tier: str, effect: dict,
       spec: dict | None = None, unlock: int = 0, blurb: str = "") -> dict:
    """Author one genuine option. `effect` is the real forge directive set."""
    return {"id": oid, "label": label, "tier": tier, "effect": effect,
            "spec": spec or {}, "unlock": unlock, "blurb": blurb}


# ──────────────────────────────────────────────────────────────────────────
# THE AXES.  group → for UI sectioning.  kind: style|slider|flag.
# target → which forge output the axis shapes (visual/geometry/audio/...).
# Each `options` list is advanced-heavy and ~10× the original thin set.
# ──────────────────────────────────────────────────────────────────────────
AXES: list[dict] = [
    # ===================== VISUAL ========================================
    {"key": "graphic_style", "label": "Graphic Style", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("flat_minimal", "Flat Minimal", "basic", {"shader": "unlit", "palette_bias": "flat", "linework": "none"}),
        _o("pixel_8bit", "Pixel · 8-bit", "basic", {"shader": "unlit", "palette_bias": "indexed_16", "pixelate": 1}, {"dim": ["2d"]}),
        _o("pixel_16bit", "Pixel · 16-bit", "core", {"shader": "unlit", "palette_bias": "indexed_64", "pixelate": 1, "dither": 1}, {"dim": ["2d", "2.5d"]}),
        _o("hd2d_diorama", "HD-2D Diorama", "advanced", {"shader": "pbr_lite", "pixelate": 1, "depth_of_field": 1, "tilt_shift": 1}, {"dim": ["2.5d"]}),
        _o("cel_toon", "Cel / Toon", "core", {"shader": "toon_ramp", "outline": "ink", "palette_bias": "saturated"}),
        _o("painterly", "Painterly", "advanced", {"shader": "painterly", "brushwork": "visible", "palette_bias": "warm"}),
        _o("pbr_stylized", "Stylized PBR", "advanced", {"shader": "pbr_metalrough", "palette_bias": "hand_tuned", "roughness_bias": "mid"}, {"dim": ["2.5d", "3d"]}),
        _o("pbr_photoreal", "Photoreal PBR", "advanced", {"shader": "pbr_metalrough", "palette_bias": "neutral", "micro_detail": 1, "roughness_bias": "measured"}, {"dim": ["3d"]}, unlock=2),
        _o("voxel", "Voxel", "core", {"shader": "voxel_flat", "topology": "cubic", "ao_baked": 1}),
        _o("low_poly_facet", "Low-Poly Faceted", "core", {"shader": "flat_shaded", "topology": "facet", "palette_bias": "duotone"}),
        _o("noir_highcontrast", "Noir High-Contrast", "advanced", {"shader": "toon_ramp", "palette_bias": "monochrome", "rim_light": 1, "grain": 1}),
        _o("retro_psx", "Retro PS1", "advanced", {"shader": "vertex_lit", "affine_warp": 1, "low_res_tex": 1, "dither": 1}, {"dim": ["3d"]}),
     ]},
    {"key": "render_pipeline", "label": "Render Pipeline", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("sprite_2d", "2D Sprite", "basic", {"pipeline": "sprite", "lighting": "none"}, {"dim": ["2d"]}),
        _o("forward", "Forward", "core", {"pipeline": "forward", "msaa": 4}),
        _o("forward_plus", "Forward+", "advanced", {"pipeline": "forward_plus", "clustered_lights": 1, "msaa": 4}, {"dim": ["3d"]}, unlock=1),
        _o("deferred", "Deferred", "advanced", {"pipeline": "deferred", "gbuffer": 1, "many_lights": 1}, {"dim": ["3d"]}, unlock=1),
        _o("deferred_clustered", "Deferred Clustered", "advanced", {"pipeline": "deferred_clustered", "gbuffer": 1, "tiled_lights": 1}, {"dim": ["3d"]}, unlock=2),
        _o("visibility_buffer", "Visibility Buffer", "advanced", {"pipeline": "vis_buffer", "micropoly": 1, "gpu_driven": 1}, {"dim": ["3d"]}, unlock=3),
        _o("raster_rt_hybrid", "Raster+RT Hybrid", "advanced", {"pipeline": "hybrid_rt", "rt_reflections": 1, "rt_shadows": 1}, {"dim": ["3d"]}, unlock=3),
     ]},
    {"key": "lighting_model", "label": "Lighting Model", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("flat_ambient", "Flat Ambient", "basic", {"gi": "none", "shadows": "none"}),
        _o("baked_lightmaps", "Baked Lightmaps", "core", {"gi": "baked", "shadows": "baked", "lightprobes": 1}),
        _o("ddgi", "Dynamic DDGI", "advanced", {"gi": "ddgi", "shadows": "dynamic", "probes": "irradiance"}, {"dim": ["3d"]}, unlock=2),
        _o("voxel_gi", "Voxel GI", "advanced", {"gi": "voxel_cone", "shadows": "dynamic"}, {"dim": ["3d"]}, unlock=2),
        _o("rt_gi", "Ray-Traced GI", "advanced", {"gi": "rtgi", "shadows": "rt", "reflections": "rt"}, {"dim": ["3d"]}, unlock=3),
        _o("twod_normalmap", "2D Normal-Mapped", "advanced", {"gi": "fake_normal", "shadows": "blob", "rim_light": 1}, {"dim": ["2d", "2.5d"]}),
        _o("volumetric", "Volumetric Atmospherics", "advanced", {"gi": "baked", "volumetrics": 1, "god_rays": 1, "fog": "height"}, unlock=2),
     ]},
    {"key": "post_processing", "label": "Post-Processing Stack", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("clean", "Clean / None", "basic", {"post": []}),
        _o("filmic", "Filmic", "core", {"post": ["tonemap_aces", "bloom", "vignette"]}),
        _o("cinematic", "Cinematic", "advanced", {"post": ["tonemap_aces", "bloom", "dof", "motion_blur", "chromatic_ab", "film_grain"]}, unlock=1),
        _o("retro_crt", "Retro CRT", "advanced", {"post": ["scanlines", "curvature", "bloom", "ghosting"]}, {"dim": ["2d", "2.5d"]}),
        _o("dreamlike", "Dreamlike Soft", "advanced", {"post": ["bloom_heavy", "diffusion", "halation", "soft_focus"]}),
        _o("clinical_sharp", "Clinical Sharp", "advanced", {"post": ["tonemap_neutral", "sharpen", "no_grain"]}),
        _o("comic_halftone", "Comic Halftone", "advanced", {"post": ["halftone", "ink_outline", "posterize"]}),
     ]},
    {"key": "color_grading", "label": "Color Grading", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("neutral", "Neutral", "basic", {"lut": "neutral", "contrast": "mid"}),
        _o("warm_golden", "Warm Golden", "core", {"lut": "warm", "contrast": "soft", "temp": "+"}),
        _o("cool_teal", "Cool Teal", "core", {"lut": "cool", "contrast": "mid", "temp": "-"}),
        _o("teal_orange", "Teal & Orange", "advanced", {"lut": "split_complement", "contrast": "high", "skin_warm": 1}),
        _o("bleach_bypass", "Bleach Bypass", "advanced", {"lut": "desaturate_highcontrast", "silver": 1}),
        _o("infrared_dream", "Infrared Dream", "advanced", {"lut": "channel_swap", "foliage": "magenta"}),
        _o("duotone", "Duotone", "advanced", {"lut": "duotone", "contrast": "high"}),
        _o("hdr_vivid", "HDR Vivid", "advanced", {"lut": "wide_gamut", "saturation": "+", "highlight_rolloff": 1}, unlock=1),
     ]},
    {"key": "materials_pbr", "label": "Material / Surface Model", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("solid_color", "Solid Color", "basic", {"mat": "albedo_only"}),
        _o("textured_diffuse", "Textured Diffuse", "core", {"mat": "albedo_tex", "tiling": 1}),
        _o("metal_rough_pbr", "Metal-Rough PBR", "advanced", {"mat": "pbr_metalrough", "normal": 1, "ao": 1}, {"dim": ["2.5d", "3d"]}, unlock=1),
        _o("spec_gloss_pbr", "Spec-Gloss PBR", "advanced", {"mat": "pbr_specgloss", "normal": 1}, {"dim": ["3d"]}, unlock=1),
        _o("subsurface", "Subsurface Scatter", "advanced", {"mat": "pbr_metalrough", "sss": 1}, {"dim": ["3d"]}, unlock=2),
        _o("clearcoat", "Clearcoat / Car Paint", "advanced", {"mat": "pbr_metalrough", "clearcoat": 1, "flakes": 1}, {"dim": ["3d"]}, unlock=2),
        _o("parallax_pom", "Parallax Occlusion", "advanced", {"mat": "pbr_metalrough", "pom": 1, "height": 1}, {"dim": ["3d"]}, unlock=2),
        _o("triplanar", "Triplanar Procedural", "advanced", {"mat": "triplanar", "noise_blend": 1}, {"dim": ["3d"]}, unlock=2),
     ]},
    {"key": "vfx_style", "label": "VFX / Particle Style", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("none", "Minimal", "basic", {"vfx": "sparse"}),
        _o("grounded", "Grounded Realistic", "advanced", {"vfx": "sim_particles", "smoke": "fluid", "sparks": "physical"}, unlock=1),
        _o("anime_burst", "Anime Burst", "advanced", {"vfx": "shaped_flipbook", "speed_lines": 1, "impact_frames": 1}),
        _o("arcane_glow", "Arcane Glow", "advanced", {"vfx": "emissive_ribbons", "bloom": 1, "trails": 1}),
        _o("gpu_simulated", "GPU-Simulated", "advanced", {"vfx": "gpu_particles", "millions": 1, "collisions": 1}, {"dim": ["3d"]}, unlock=3),
        _o("retro_sprite_fx", "Retro Sprite FX", "core", {"vfx": "sprite_flipbook", "limited_palette": 1}, {"dim": ["2d", "2.5d"]}),
     ]},
    {"key": "dimension", "label": "Dimension", "group": "Geometry",
     "kind": "style", "target": "geometry", "options": [
        _o("2d", "2D", "basic", {"dim": "2d", "engine_path": "sprite2d"}),
        _o("2.5d", "2.5D", "core", {"dim": "2.5d", "engine_path": "ortho_depth"}),
        _o("3d", "3D", "advanced", {"dim": "3d", "engine_path": "scene3d"}),
        _o("iso_2.5d", "Isometric 2.5D", "advanced", {"dim": "2.5d", "engine_path": "iso", "tile_grid": 1}),
        _o("billboard_3d", "Billboard 3D (Doom-like)", "advanced", {"dim": "3d", "engine_path": "billboard_sprites"}),
     ]},
    {"key": "level_of_detail", "label": "LOD Strategy", "group": "Geometry",
     "kind": "style", "target": "geometry", "options": [
        _o("single", "Single Mesh", "basic", {"lod": "none"}),
        _o("discrete_lod", "Discrete LODs", "core", {"lod": "discrete", "levels": 3}),
        _o("continuous_lod", "Continuous LOD", "advanced", {"lod": "continuous", "morph": 1}, {"dim": ["3d"]}, unlock=2),
        _o("nanite_micropoly", "Virtualized Micropoly", "advanced", {"lod": "virtualized", "auto": 1}, {"dim": ["3d"]}, unlock=3),
        _o("impostor_billboards", "Impostor Billboards", "advanced", {"lod": "impostor", "distant_cards": 1}, {"dim": ["3d"]}, unlock=2),
     ]},
    # ===================== MODEL / ANIMATION =============================
    {"key": "model_style", "label": "Model Style", "group": "Model",
     "kind": "style", "target": "geometry", "options": [
        _o("chibi", "Chibi", "core", {"proportion": "2head", "limb": "stubby"}),
        _o("heroic", "Heroic 8-Head", "advanced", {"proportion": "8head", "limb": "idealized"}),
        _o("realistic", "Realistic", "advanced", {"proportion": "7.5head", "anatomy": "measured"}, {"dim": ["3d"]}, unlock=1),
        _o("stylized_exagger", "Stylized Exaggerated", "advanced", {"proportion": "varied", "silhouette": "readable", "hands": "large"}),
        _o("noodle_squash", "Noodle / Squash", "advanced", {"proportion": "flex", "bones": "soft", "squash_stretch": 1}),
        _o("mecha_hard", "Hard-Surface Mecha", "advanced", {"proportion": "mech", "paneling": 1, "kitbash": 1}, {"dim": ["2.5d", "3d"]}),
        _o("blocky_avatar", "Blocky Avatar", "basic", {"proportion": "block", "limb": "cuboid"}),
     ]},
    {"key": "topology_density", "label": "Topology Density", "group": "Model",
     "kind": "slider", "target": "geometry", "options": [
        _o("ultralow", "Ultra-Low (≤500 tri)", "basic", {"tri_budget": 500, "topo": "ngon_ok"}),
        _o("low", "Low (~2k)", "core", {"tri_budget": 2000, "topo": "quad_pref"}),
        _o("mid", "Mid (~10k)", "core", {"tri_budget": 10000, "topo": "quad"}),
        _o("high", "High (~50k)", "advanced", {"tri_budget": 50000, "topo": "quad", "edge_loops": 1}, {"dim": ["3d"]}, unlock=2),
        _o("cinematic", "Cinematic (~200k)", "advanced", {"tri_budget": 200000, "topo": "subd", "displacement": 1}, {"dim": ["3d"]}, unlock=3),
        _o("micropoly", "Micropoly (millions)", "advanced", {"tri_budget": -1, "topo": "virtualized"}, {"dim": ["3d"]}, unlock=3),
     ]},
    {"key": "rig_complexity", "label": "Rig Complexity", "group": "Model",
     "kind": "style", "target": "geometry", "options": [
        _o("static", "Static (no rig)", "basic", {"rig": "none"}),
        _o("simple_skeleton", "Simple Skeleton", "core", {"rig": "skeleton", "bones": "low"}),
        _o("ik_rig", "IK + FK", "advanced", {"rig": "ikfk", "ik_chains": 1}, unlock=1),
        _o("facial_blendshapes", "Facial Blendshapes", "advanced", {"rig": "ikfk", "blendshapes": 1, "visemes": 1}, {"dim": ["3d"]}, unlock=2),
        _o("muscle_secondary", "Muscle + Secondary", "advanced", {"rig": "ikfk", "muscle": 1, "jiggle": 1}, {"dim": ["3d"]}, unlock=3),
        _o("procedural_rig", "Procedural / Spline", "advanced", {"rig": "procedural", "spline": 1}, unlock=2),
     ]},
    {"key": "animation_style", "label": "Animation Style", "group": "Model",
     "kind": "style", "target": "geometry", "options": [
        _o("frame_static", "Static Poses", "basic", {"anim": "pose_swap"}),
        _o("sprite_frames", "Sprite Frames", "core", {"anim": "spritesheet", "fps": 12}, {"dim": ["2d", "2.5d"]}),
        _o("keyframed", "Keyframed", "core", {"anim": "keyframe", "curves": "ease"}),
        _o("mocap_realistic", "Mocap Realistic", "advanced", {"anim": "mocap", "rootmotion": 1}, {"dim": ["3d"]}, unlock=2),
        _o("anime_snappy", "Anime Snappy", "advanced", {"anim": "keyframe", "holds": 1, "smear_frames": 1}),
        _o("physics_blend", "Physics-Blended", "advanced", {"anim": "blend", "ragdoll_blend": 1, "active_ragdoll": 1}, {"dim": ["3d"]}, unlock=3),
        _o("procedural_locomotion", "Procedural Locomotion", "advanced", {"anim": "procedural", "foot_ik": 1, "motion_matching": 1}, {"dim": ["3d"]}, unlock=3),
     ]},
    {"key": "destruction_model", "label": "Destruction Model", "group": "Simulation",
     "kind": "style", "target": "geometry", "options": [
        _o("indestructible", "Indestructible", "basic", {"destruct": "none"}),
        _o("swap_damaged", "Swap to Damaged", "core", {"destruct": "state_swap", "states": 2}),
        _o("prefractured", "Pre-Fractured", "advanced", {"destruct": "prefracture", "chunks": 1}, {"dim": ["3d"]}, unlock=2),
        _o("dynamic_fracture", "Dynamic Fracture", "advanced", {"destruct": "voronoi_runtime", "debris": 1}, {"dim": ["3d"]}, unlock=3),
        _o("voxel_destruct", "Voxel Destruction", "advanced", {"destruct": "voxel_carve", "fully_destructible": 1}, unlock=2),
        _o("soft_deform", "Soft-Body Deform", "advanced", {"destruct": "softbody", "dent": 1}, {"dim": ["3d"]}, unlock=3),
     ]},
    {"key": "world_scale", "label": "World Scale", "group": "Simulation",
     "kind": "style", "target": "geometry", "options": [
        _o("single_screen", "Single Screen", "basic", {"scale": "screen"}),
        _o("handcrafted_levels", "Handcrafted Levels", "core", {"scale": "levels", "streaming": "none"}),
        _o("open_zone", "Open Zone", "advanced", {"scale": "zone", "streaming": "cells"}, unlock=2),
        _o("open_world", "Open World", "advanced", {"scale": "open_world", "streaming": "async", "origin_rebase": 1}, {"dim": ["2.5d", "3d"]}, unlock=3),
        _o("planetary", "Planetary / Galactic", "advanced", {"scale": "planetary", "lod_chunks": 1, "double_precision": 1}, {"dim": ["3d"]}, unlock=3),
     ]},
    # ===================== CAMERA / FEEL =================================
    {"key": "camera_system", "label": "Camera System", "group": "Feel",
     "kind": "style", "target": "meta", "options": [
        _o("fixed_2d", "Fixed 2D", "basic", {"cam": "fixed", "follow": "lerp"}, {"dim": ["2d"]}),
        _o("side_scroller", "Side-Scroller", "core", {"cam": "side", "deadzone": 1}, {"dim": ["2d", "2.5d"]}),
        _o("topdown", "Top-Down", "core", {"cam": "topdown", "screenshake": 1}),
        _o("isometric", "Isometric", "core", {"cam": "iso", "edge_pan": 1}),
        _o("third_person", "Third-Person Orbit", "advanced", {"cam": "tp_orbit", "collision": 1, "framing": "rule_of_thirds"}, {"dim": ["3d"]}, unlock=1),
        _o("first_person", "First-Person", "advanced", {"cam": "fp", "headbob": 1, "fov_kick": 1}, {"dim": ["3d"]}, unlock=1),
        _o("cinematic_rails", "Cinematic Rails", "advanced", {"cam": "rails", "splines": 1, "lens_breathing": 1}, unlock=2),
        _o("free_director", "Free Director (RTS)", "advanced", {"cam": "free", "edge_scroll": 1, "zoom_tiers": 1}),
     ]},
    {"key": "locomotion", "label": "Locomotion Model", "group": "Feel",
     "kind": "style", "target": "gameplay", "options": [
        _o("grid_step", "Grid Step", "core", {"move": "grid", "snap": 1}),
        _o("8way", "8-Way", "basic", {"move": "8way"}),
        _o("platformer_physics", "Platformer Physics", "advanced", {"move": "platformer", "coyote_time": 1, "jump_buffer": 1, "var_jump": 1}, {"dim": ["2d", "2.5d"]}),
        _o("twin_stick", "Twin-Stick", "core", {"move": "twin_stick", "strafe": 1}),
        _o("momentum_3d", "Momentum 3D", "advanced", {"move": "momentum", "accel_curve": 1, "air_control": 1}, {"dim": ["3d"]}, unlock=2),
        _o("vehicular", "Vehicular", "advanced", {"move": "vehicle", "traction": 1, "drift": 1}, unlock=2),
        _o("climb_traverse", "Climb / Traverse", "advanced", {"move": "parkour", "ledge_grab": 1, "vault": 1}, {"dim": ["3d"]}, unlock=3),
     ]},
    {"key": "input_scheme", "label": "Input Scheme", "group": "Feel",
     "kind": "style", "target": "gameplay", "options": [
        _o("one_button", "One-Button", "basic", {"input": "single"}),
        _o("touch_gestures", "Touch Gestures", "core", {"input": "touch", "swipe": 1, "tap": 1}),
        _o("virtual_pad", "Virtual D-Pad", "core", {"input": "vpad"}),
        _o("gamepad_full", "Full Gamepad", "advanced", {"input": "gamepad", "analog": 1, "triggers": 1}, unlock=1),
        _o("gyro_aim", "Gyro Aim", "advanced", {"input": "gamepad", "gyro": 1}, unlock=2),
        _o("kbm_precision", "KB+M Precision", "advanced", {"input": "kbm", "raw_input": 1}),
     ]},
    {"key": "haptics_feedback", "label": "Haptics & Feedback", "group": "Feel",
     "kind": "style", "target": "gameplay", "options": [
        _o("none", "None", "basic", {"haptic": "off"}),
        _o("basic_rumble", "Basic Rumble", "core", {"haptic": "rumble"}),
        _o("contextual", "Contextual Haptics", "advanced", {"haptic": "contextual", "per_event": 1}, unlock=1),
        _o("adaptive_triggers", "Adaptive Triggers", "advanced", {"haptic": "adaptive_triggers", "resistance": 1}, unlock=2),
        _o("audio_haptic_sync", "Audio-Synced Haptics", "advanced", {"haptic": "audio_synced", "waveform": 1}, unlock=2),
     ]},
    {"key": "game_feel_juice", "label": "Game Feel / Juice", "group": "Feel",
     "kind": "slider", "target": "gameplay", "options": [
        _o("dry", "Dry / Functional", "basic", {"juice": "minimal"}),
        _o("readable", "Readable", "core", {"juice": "tweens", "hit_flash": 1}),
        _o("punchy", "Punchy", "advanced", {"juice": "screenshake", "hitstop": 1, "knockback": 1, "particles": 1}, unlock=1),
        _o("maximal_juice", "Maximal Juice", "advanced", {"juice": "all", "screenshake": 1, "hitstop": 1, "chromatic_punch": 1, "freeze_frames": 1, "squash": 1}, unlock=2),
        _o("tactile_minimal", "Tactile-Minimal", "advanced", {"juice": "micro", "subframe_tween": 1, "no_shake": 1}),
     ]},
    # ===================== AUDIO =========================================
    {"key": "sound_style", "label": "Sound Style", "group": "Audio",
     "kind": "style", "target": "audio", "options": [
        _o("chiptune_sfx", "Chiptune SFX", "basic", {"sfx": "synth_chip", "bit": "low"}),
        _o("synth_modern", "Modern Synth", "core", {"sfx": "synth", "layers": 2}),
        _o("foley_recorded", "Recorded Foley", "advanced", {"sfx": "foley", "variations": 1, "round_robin": 1}, unlock=1),
        _o("hyperreal", "Hyperreal Designed", "advanced", {"sfx": "designed", "layered_transients": 1, "sweeteners": 1}, unlock=2),
        _o("granular_proc", "Granular Procedural", "advanced", {"sfx": "granular", "runtime_synth": 1}, unlock=2),
        _o("organic_mouth", "Mouth / Organic", "advanced", {"sfx": "vocal_foley", "characterful": 1}),
     ]},
    {"key": "music_style", "label": "Music Style", "group": "Audio",
     "kind": "style", "target": "audio", "options": [
        _o("chiptune", "Chiptune", "basic", {"music": "chip", "channels": 4}),
        _o("synthwave", "Synthwave", "core", {"music": "synthwave", "arp": 1}),
        _o("orchestral", "Orchestral", "advanced", {"music": "orchestral", "sections": "full", "live_feel": 1}, unlock=1),
        _o("hybrid_orch_synth", "Hybrid Orch+Synth", "advanced", {"music": "hybrid", "braams": 1, "pulses": 1}, unlock=2),
        _o("jazz_improv", "Jazz / Improv", "advanced", {"music": "jazz", "swing": 1, "improv": 1}),
        _o("ambient_drone", "Ambient Drone", "advanced", {"music": "ambient", "evolving_pads": 1, "field_recordings": 1}),
        _o("ethnic_world", "World / Ethnic", "advanced", {"music": "world", "regional_instruments": 1}),
     ]},
    {"key": "adaptive_audio", "label": "Adaptive Music Model", "group": "Audio",
     "kind": "style", "target": "audio", "options": [
        _o("looped", "Looped Tracks", "basic", {"adaptive": "loop"}),
        _o("layered", "Vertical Layers", "advanced", {"adaptive": "vertical", "stems": 1, "intensity_mapped": 1}, unlock=1),
        _o("resequenced", "Horizontal Resequence", "advanced", {"adaptive": "horizontal", "transition_cells": 1}, unlock=2),
        _o("generative", "Generative", "advanced", {"adaptive": "generative", "rules": 1, "player_state": 1}, unlock=3),
        _o("stinger_driven", "Stinger-Driven", "core", {"adaptive": "stingers", "events": 1}),
     ]},
    {"key": "mix_spatialization", "label": "Mix & Spatialization", "group": "Audio",
     "kind": "style", "target": "audio", "options": [
        _o("mono", "Mono", "basic", {"mix": "mono"}),
        _o("stereo_pan", "Stereo Pan", "core", {"mix": "stereo", "pan_by_pos": 1}),
        _o("surround", "Surround", "advanced", {"mix": "surround", "5_1": 1}, unlock=1),
        _o("hrtf_binaural", "HRTF Binaural", "advanced", {"mix": "binaural", "hrtf": 1, "occlusion": 1}, {"dim": ["3d"]}, unlock=2),
        _o("ducked_dynamic", "Dynamic Ducking", "advanced", {"mix": "dynamic", "sidechain": 1, "priority_buses": 1}, unlock=1),
     ]},
    {"key": "voice_acting_depth", "label": "Voice-Acting Depth", "group": "Audio",
     "kind": "slider", "target": "audio", "options": [
        _o("text_only", "Text Only", "basic", {"vo": "none"}),
        _o("barks", "Bark System", "core", {"vo": "barks", "round_robin": 1}),
        _o("key_scenes", "Key Scenes VO", "advanced", {"vo": "partial", "cinematics": 1}, unlock=1),
        _o("full_vo", "Full VO", "advanced", {"vo": "full", "all_dialogue": 1}, unlock=2),
        _o("performance_capture", "Performance Capture", "advanced", {"vo": "full", "facial_sync": 1, "perf_capture": 1}, {"dim": ["3d"]}, unlock=3),
        _o("procedural_tts", "Procedural TTS", "advanced", {"vo": "tts", "runtime": 1}),
     ]},
    # ===================== DESIGN / META =================================
    {"key": "design_style", "label": "Design Style", "group": "Design",
     "kind": "style", "target": "visual", "options": [
        _o("clean_flat", "Clean Flat UI", "basic", {"ui": "flat", "grid": 8}),
        _o("skeuomorphic", "Skeuomorphic", "core", {"ui": "skeuo", "texture": 1, "depth": 1}),
        _o("neumorphic", "Neumorphic", "advanced", {"ui": "neumorphic", "soft_shadow": 1}),
        _o("glassmorphism", "Glassmorphism", "advanced", {"ui": "glass", "blur": 1, "translucency": 1}),
        _o("brutalist", "Brutalist", "advanced", {"ui": "brutalist", "mono_type": 1, "raw_grid": 1}),
        _o("diegetic", "Diegetic In-World", "advanced", {"ui": "diegetic", "no_hud": 1, "in_world_panels": 1}, {"dim": ["3d"]}, unlock=2),
        _o("retro_terminal", "Retro Terminal", "advanced", {"ui": "terminal", "scanline": 1, "mono_type": 1}),
     ]},
    {"key": "cinematic_style", "label": "Cinematic Style", "group": "Design",
     "kind": "style", "target": "visual", "options": [
        _o("none", "No Cutscenes", "basic", {"cine": "none"}),
        _o("in_engine", "In-Engine", "core", {"cine": "in_engine", "letterbox": 1}),
        _o("storyboard_panels", "Storyboard Panels", "core", {"cine": "panels"}, {"dim": ["2d", "2.5d"]}),
        _o("dynamic_camera", "Dynamic Camera", "advanced", {"cine": "dynamic", "handheld": 1, "depth_cuts": 1}, unlock=1),
        _o("oner_longtake", "One-Shot Long Take", "advanced", {"cine": "oner", "seamless": 1}, unlock=3),
        _o("match_cuts", "Match-Cut Montage", "advanced", {"cine": "montage", "match_cuts": 1, "rhythm_edit": 1}, unlock=2),
     ]},
    {"key": "director_style", "label": "Director Style (Auteur)", "group": "Design",
     "kind": "style", "target": "meta", "options": [
        _o("neutral", "Neutral", "basic", {"director": "neutral"}),
        _o("kojima_metatextual", "Metatextual Auteur", "advanced", {"director": "metatextual", "fourth_wall": 1, "long_codecs": 1}, unlock=2),
        _o("miyamoto_playfirst", "Play-First", "advanced", {"director": "play_first", "verb_clarity": 1, "toybox": 1}),
        _o("fromsoft_obtuse", "Obtuse / Earned", "advanced", {"director": "earned_mastery", "cryptic_lore": 1, "no_handholding": 1}, unlock=2),
        _o("supergiant_voiced", "Reactive-Narrated", "advanced", {"director": "narrated", "reactive_vo": 1, "warm_tone": 1}),
        _o("thatgamecompany_wordless", "Wordless Emotive", "advanced", {"director": "wordless", "emotion_arc": 1, "no_text": 1}),
        _o("arcade_pure", "Arcade Pure", "core", {"director": "arcade", "instant_restart": 1, "score_chase": 1}),
     ]},
    {"key": "ui_design_language", "label": "UI Information Density", "group": "Design",
     "kind": "slider", "target": "visual", "options": [
        _o("minimal_hud", "Minimal HUD", "core", {"hud": "minimal", "fade_when_idle": 1}),
        _o("standard", "Standard", "basic", {"hud": "standard"}),
        _o("rich_sim", "Rich Sim Dashboard", "advanced", {"hud": "dense", "panels": 1, "tooltips": 1}, {"genre": ["strategy", "tycoon", "sim", "city_builder", "tactics"]}, unlock=1),
        _o("contextual_radial", "Contextual Radial", "advanced", {"hud": "radial", "context_only": 1}, unlock=1),
        _o("zero_ui", "Zero-UI Diegetic", "advanced", {"hud": "none", "diegetic_only": 1}, {"dim": ["3d"]}, unlock=2),
     ]},
    {"key": "accessibility_suite", "label": "Accessibility Suite", "group": "Design",
     "kind": "style", "target": "gameplay", "options": [
        _o("basic", "Basic", "basic", {"a11y": ["subtitles"]}),
        _o("standard", "Standard", "core", {"a11y": ["subtitles", "remap", "colorblind"]}),
        _o("comprehensive", "Comprehensive", "advanced", {"a11y": ["subtitles", "remap", "colorblind", "ui_scale", "difficulty_separated", "motion_reduce"]}, unlock=1),
        _o("aaa_full", "AAA Full Suite", "advanced", {"a11y": ["subtitles_styled", "remap", "colorblind", "ui_scale", "difficulty_separated", "motion_reduce", "tts", "aim_assist", "screen_narration", "haptic_cues"]}, unlock=2),
     ]},
    # ===================== SIMULATION / TECH =============================
    {"key": "physics_fidelity", "label": "Physics Fidelity", "group": "Simulation",
     "kind": "slider", "target": "gameplay", "options": [
        _o("none", "None / Scripted", "basic", {"phys": "scripted"}),
        _o("arcade", "Arcade", "core", {"phys": "arcade", "simple_collision": 1}),
        _o("rigidbody", "Rigidbody", "advanced", {"phys": "rigidbody", "joints": 1, "stacking": 1}, unlock=1),
        _o("continuous_ccd", "Continuous (CCD)", "advanced", {"phys": "rigidbody", "ccd": 1, "high_speed": 1}, unlock=2),
        _o("soft_cloth_fluid", "Soft/Cloth/Fluid", "advanced", {"phys": "advanced", "cloth": 1, "fluid": 1, "softbody": 1}, {"dim": ["3d"]}, unlock=3),
        _o("deterministic_lockstep", "Deterministic Lockstep", "advanced", {"phys": "fixed_point", "deterministic": 1}, {"genre": ["fighting", "strategy", "tactics"]}, unlock=2),
     ]},
    {"key": "ai_director_intensity", "label": "AI Director Intensity", "group": "Simulation",
     "kind": "slider", "target": "gameplay", "options": [
        _o("none", "Static", "basic", {"director_ai": "none"}),
        _o("scripted_waves", "Scripted Waves", "core", {"director_ai": "scripted"}),
        _o("reactive_pacing", "Reactive Pacing", "advanced", {"director_ai": "reactive", "tension_curve": 1}, unlock=1),
        _o("flow_adaptive", "Flow-Adaptive", "advanced", {"director_ai": "flow", "skill_estimate": 1, "spawn_budget": 1}, unlock=2),
        _o("narrative_director", "Narrative Director", "advanced", {"director_ai": "narrative", "beat_aware": 1, "drama_manager": 1}, unlock=3),
     ]},
    {"key": "netcode_model", "label": "Netcode Model", "group": "Simulation",
     "kind": "style", "target": "gameplay", "options": [
        _o("offline", "Offline", "basic", {"net": "none"}),
        _o("async_leaderboard", "Async / Leaderboard", "core", {"net": "async", "ghosts": 1}),
        _o("client_server", "Client-Server", "advanced", {"net": "cs", "authoritative": 1, "interp": 1}, unlock=1),
        _o("rollback", "Rollback", "advanced", {"net": "rollback", "prediction": 1}, {"genre": ["fighting", "shooter", "arcade"]}, unlock=2),
        _o("lockstep", "Deterministic Lockstep", "advanced", {"net": "lockstep", "command_sync": 1}, {"genre": ["strategy", "tactics", "rpg"]}, unlock=2),
        _o("relay_mesh", "Relay / Mesh", "advanced", {"net": "relay", "p2p": 1, "nat_punch": 1}, unlock=2),
     ]},
    {"key": "weather_sim", "label": "Weather Simulation", "group": "Simulation",
     "kind": "style", "target": "visual", "options": [
        _o("none", "None", "basic", {"weather": "none"}),
        _o("cosmetic", "Cosmetic Overlays", "core", {"weather": "overlay", "rain_snow": 1}),
        _o("dynamic_transitions", "Dynamic Transitions", "advanced", {"weather": "dynamic", "fronts": 1, "wet_surfaces": 1}, unlock=1),
        _o("gameplay_coupled", "Gameplay-Coupled", "advanced", {"weather": "coupled", "visibility": 1, "traction": 1, "ai_impact": 1}, unlock=2),
        _o("simulated_climate", "Simulated Climate", "advanced", {"weather": "climate_sim", "zones": 1, "seasons": 1}, unlock=3),
     ]},
    {"key": "time_of_day", "label": "Time of Day", "group": "Simulation",
     "kind": "style", "target": "visual", "options": [
        _o("fixed", "Fixed", "basic", {"tod": "fixed"}),
        _o("baked_variants", "Baked Variants", "core", {"tod": "variants", "presets": 1}),
        _o("dynamic_cycle", "Dynamic Cycle", "advanced", {"tod": "dynamic", "sun_moon": 1, "shadow_sweep": 1}, {"dim": ["3d"]}, unlock=1),
        _o("gameplay_clock", "Gameplay Clock", "advanced", {"tod": "clock", "npc_schedules": 1, "shop_hours": 1}, unlock=2),
     ]},
    {"key": "procedural_density", "label": "Procedural Generation", "group": "Simulation",
     "kind": "slider", "target": "geometry", "options": [
        _o("authored", "Hand-Authored", "basic", {"procgen": "none"}),
        _o("seeded_layout", "Seeded Layouts", "core", {"procgen": "layout", "seed": 1}),
        _o("wfc_tiles", "Wave-Function Collapse", "advanced", {"procgen": "wfc", "constraints": 1}, unlock=1),
        _o("noise_terrain", "Noise Terrain", "advanced", {"procgen": "noise", "fbm": 1, "erosion": 1}, {"dim": ["2.5d", "3d"]}, unlock=2),
        _o("grammar_dungeon", "Grammar Dungeons", "advanced", {"procgen": "grammar", "rooms_graph": 1, "lock_key": 1}, {"genre": ["roguelike", "rpg", "action_rpg", "metroidvania"]}, unlock=2),
        _o("full_procedural", "Fully Procedural", "advanced", {"procgen": "full", "everything": 1, "deterministic_seed": 1}, unlock=3),
     ]},
    {"key": "difficulty_curve", "label": "Difficulty Curve", "group": "Gameplay",
     "kind": "style", "target": "gameplay", "options": [
        _o("gentle", "Gentle", "basic", {"diff": "gentle", "ramp": "shallow"}),
        _o("classic_ramp", "Classic Ramp", "core", {"diff": "classic", "ramp": "linear"}),
        _o("elastic_dda", "Elastic DDA", "advanced", {"diff": "dda", "rubber_band": 1, "skill_track": 1}, unlock=1),
        _o("brutal_fair", "Brutal-but-Fair", "advanced", {"diff": "brutal", "telegraphed": 1, "fast_retry": 1}, unlock=2),
        _o("mastery_layers", "Mastery Layers", "advanced", {"diff": "mastery", "optional_hard": 1, "skill_ceiling": 1}, unlock=2),
        _o("difficulty_modifiers", "Player Modifiers", "advanced", {"diff": "modifiers", "toggles": 1, "assist_menu": 1}, unlock=1),
     ]},
    # ===================== RENDER / GEOMETRY FIDELITY (advanced-heavy) =====
    {"key": "texture_resolution", "label": "Texture Resolution", "group": "Visual",
     "kind": "slider", "target": "visual", "options": [
        _o("res_128", "128px", "basic", {"tex_px": 128}), _o("res_256", "256px", "basic", {"tex_px": 256}),
        _o("res_512", "512px", "core", {"tex_px": 512}), _o("res_1k", "1024px", "core", {"tex_px": 1024}),
        _o("res_2k", "2K", "advanced", {"tex_px": 2048}, {"dim": ["3d"]}, unlock=1),
        _o("res_4k", "4K", "advanced", {"tex_px": 4096, "streaming": 1}, {"dim": ["3d"]}, unlock=2),
        _o("res_virtual", "Virtual Texturing", "advanced", {"tex_px": -1, "virtual": 1}, {"dim": ["3d"]}, unlock=3),
        _o("res_8k_decals", "8K Hero Decals", "advanced", {"tex_px": 8192, "hero_only": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "anti_aliasing", "label": "Anti-Aliasing", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("none", "None", "basic", {"aa": "off"}), _o("fxaa", "FXAA", "core", {"aa": "fxaa"}),
        _o("msaa", "MSAA", "advanced", {"aa": "msaa", "samples": 4}, {"dim": ["3d"]}, unlock=1),
        _o("taa", "TAA", "advanced", {"aa": "taa", "motion_vectors": 1}, {"dim": ["3d"]}, unlock=2),
        _o("smaa", "SMAA", "advanced", {"aa": "smaa"}, unlock=1),
        _o("dlaa", "DLAA / ML-AA", "advanced", {"aa": "dlaa", "ml": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "ambient_occlusion", "label": "Ambient Occlusion", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("none", "None", "basic", {"ao": "off"}), _o("baked_ao", "Baked AO", "core", {"ao": "baked"}),
        _o("ssao", "SSAO", "advanced", {"ao": "ssao"}, {"dim": ["3d"]}, unlock=1),
        _o("hbao", "HBAO+", "advanced", {"ao": "hbao"}, {"dim": ["3d"]}, unlock=2),
        _o("gtao", "GTAO", "advanced", {"ao": "gtao"}, {"dim": ["3d"]}, unlock=2),
        _o("rtao", "Ray-Traced AO", "advanced", {"ao": "rtao", "rt": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "reflection_model", "label": "Reflections", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("none", "None", "basic", {"refl": "off"}), _o("cubemap", "Static Cubemap", "core", {"refl": "cubemap"}),
        _o("planar", "Planar", "advanced", {"refl": "planar"}, {"dim": ["3d"]}, unlock=1),
        _o("ssr", "Screen-Space", "advanced", {"refl": "ssr"}, {"dim": ["3d"]}, unlock=2),
        _o("probes", "Reflection Probes", "advanced", {"refl": "probes"}, {"dim": ["3d"]}, unlock=2),
        _o("rt_refl", "Ray-Traced", "advanced", {"refl": "rt", "rt": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "water_rendering", "label": "Water Rendering", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("none", "None", "basic", {"water": "off"}), _o("flat_texture", "Flat Texture", "basic", {"water": "flat"}),
        _o("scrolling", "Scrolling Normals", "core", {"water": "scroll"}),
        _o("gerstner", "Gerstner Waves", "advanced", {"water": "gerstner", "displacement": 1}, {"dim": ["3d"]}, unlock=2),
        _o("fft_ocean", "FFT Ocean", "advanced", {"water": "fft", "spectral": 1}, {"dim": ["3d"]}, unlock=3),
        _o("fluid_sim_water", "Fluid Sim", "advanced", {"water": "fluid_sim", "interactive": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "foliage_system", "label": "Foliage & Vegetation", "group": "Visual",
     "kind": "style", "target": "geometry", "options": [
        _o("none", "None", "basic", {"foliage": "off"}), _o("billboards", "Billboards", "core", {"foliage": "billboard"}),
        _o("instanced_meshes", "Instanced Meshes", "advanced", {"foliage": "instanced", "wind": 1}, {"dim": ["3d"]}, unlock=1),
        _o("gpu_scattered", "GPU Scattered", "advanced", {"foliage": "gpu_scatter", "density_maps": 1}, {"dim": ["3d"]}, unlock=2),
        _o("interactive_bend", "Interactive Bend", "advanced", {"foliage": "interactive", "trample": 1}, {"dim": ["3d"]}, unlock=3),
        _o("procedural_ecosystem", "Procedural Ecosystem", "advanced", {"foliage": "ecosystem", "growth_sim": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "terrain_system", "label": "Terrain System", "group": "Geometry",
     "kind": "style", "target": "geometry", "options": [
        _o("none", "None", "basic", {"terrain": "off"}), _o("tilemap", "Tilemap", "core", {"terrain": "tilemap"}, {"dim": ["2d", "2.5d"]}),
        _o("heightmap", "Heightmap", "advanced", {"terrain": "heightmap", "splat_layers": 1}, {"dim": ["3d"]}, unlock=1),
        _o("clipmaps", "Geometry Clipmaps", "advanced", {"terrain": "clipmaps", "streaming": 1}, {"dim": ["3d"]}, unlock=2),
        _o("voxel_terrain", "Voxel Terrain", "advanced", {"terrain": "voxel", "deformable": 1}, unlock=2),
        _o("procedural_terrain", "Procedural + Erosion", "advanced", {"terrain": "procedural", "erosion": 1, "biomes": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "cloth_simulation", "label": "Cloth Simulation", "group": "Simulation",
     "kind": "style", "target": "geometry", "options": [
        _o("none", "None", "basic", {"cloth": "off"}), _o("baked_anim", "Baked Animation", "core", {"cloth": "baked"}),
        _o("bone_chains", "Bone Chains", "advanced", {"cloth": "bones", "jiggle": 1}, {"dim": ["3d"]}, unlock=1),
        _o("verlet_cloth", "Verlet Cloth", "advanced", {"cloth": "verlet", "collisions": 1}, {"dim": ["3d"]}, unlock=2),
        _o("gpu_cloth", "GPU Cloth", "advanced", {"cloth": "gpu", "self_collision": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "hair_fur_system", "label": "Hair & Fur", "group": "Simulation",
     "kind": "style", "target": "geometry", "options": [
        _o("none", "None", "basic", {"hair": "off"}), _o("mesh_cards", "Mesh Cards", "core", {"hair": "cards"}),
        _o("alpha_planes", "Alpha Planes", "core", {"hair": "planes"}, {"dim": ["3d"]}),
        _o("strand_groom", "Strand Groom", "advanced", {"hair": "strands", "physics": 1}, {"dim": ["3d"]}, unlock=2),
        _o("gpu_fur_shell", "GPU Fur Shells", "advanced", {"hair": "shells"}, {"dim": ["3d"]}, unlock=2),
        _o("simulated_strands", "Simulated Strands", "advanced", {"hair": "sim_strands", "wind": 1, "collision": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "facial_animation", "label": "Facial Animation", "group": "Model",
     "kind": "style", "target": "geometry", "options": [
        _o("none", "None", "basic", {"face": "off"}), _o("texture_swap", "Texture Swap", "basic", {"face": "tex_swap"}, {"dim": ["2d", "2.5d"]}),
        _o("blendshapes", "Blendshapes", "advanced", {"face": "blendshapes"}, {"dim": ["3d"]}, unlock=1),
        _o("facs", "FACS Rig", "advanced", {"face": "facs", "muscle": 1}, {"dim": ["3d"]}, unlock=2),
        _o("ml_capture", "ML Capture", "advanced", {"face": "ml_capture", "audio_driven": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "lipsync_model", "label": "Lip-Sync", "group": "Audio",
     "kind": "style", "target": "geometry", "options": [
        _o("none", "None", "basic", {"lipsync": "off"}), _o("flapping", "Jaw Flap", "basic", {"lipsync": "flap"}),
        _o("viseme_table", "Viseme Table", "core", {"lipsync": "visemes"}),
        _o("phoneme_driven", "Phoneme-Driven", "advanced", {"lipsync": "phoneme", "coarticulation": 1}, unlock=1),
        _o("audio_ml_lipsync", "Audio ML", "advanced", {"lipsync": "ml", "multilingual": 1}, {"dim": ["3d"]}, unlock=2)]},
    {"key": "upscaling_tech", "label": "Upscaling / Reconstruction", "group": "Performance",
     "kind": "style", "target": "visual", "options": [
        _o("native", "Native", "core", {"upscale": "off"}), _o("bilinear", "Bilinear", "basic", {"upscale": "bilinear"}),
        _o("temporal_upsample", "Temporal Upsample", "advanced", {"upscale": "tsr", "history": 1}, {"dim": ["3d"]}, unlock=1),
        _o("ml_upscale", "ML Upscaler", "advanced", {"upscale": "ml", "dlss_fsr_like": 1}, {"dim": ["3d"]}, unlock=2),
        _o("checkerboard", "Checkerboard", "advanced", {"upscale": "checkerboard"}, {"dim": ["3d"]}, unlock=2)]},
    {"key": "thermal_profile", "label": "Thermal & Power Profile", "group": "Performance",
     "kind": "slider", "target": "meta", "options": [
        _o("cool_safe", "Cool / Safe (default floor)", "advanced", {"thermal": "cool", "fps_cap": 30, "res_scale": 0.7, "battery": "saver"}),
        _o("balanced", "Balanced", "advanced", {"thermal": "balanced", "fps_cap": 45, "res_scale": 0.85}, unlock=1),
        _o("performance", "Performance", "advanced", {"thermal": "perf", "fps_cap": 60, "res_scale": 1.0}, unlock=2),
        _o("unlocked", "Unlocked (warm)", "advanced", {"thermal": "unlocked", "fps_cap": 120}, unlock=3)]},
    {"key": "memory_budget", "label": "Memory Budget Profile", "group": "Performance",
     "kind": "slider", "target": "meta", "options": [
        _o("ultra_lean_2gb", "Ultra-Lean ≤2GB", "advanced", {"mem_mb": 1536, "streaming": "aggressive", "lod_bias": 2}),
        _o("lean_4gb", "Lean ~4GB (S20 floor)", "advanced", {"mem_mb": 3072, "streaming": "on", "lod_bias": 1}),
        _o("standard_6gb", "Standard ~6GB", "advanced", {"mem_mb": 5120, "streaming": "on"}, unlock=1),
        _o("high_8gb", "High ~8GB", "advanced", {"mem_mb": 7168}, unlock=2),
        _o("uncapped", "Uncapped (desktop)", "advanced", {"mem_mb": -1}, unlock=3)]},
    {"key": "shadow_technique", "label": "Shadow Technique", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("none", "None", "basic", {"shadow": "off"}), _o("blob", "Blob Shadows", "basic", {"shadow": "blob"}),
        _o("baked", "Baked", "core", {"shadow": "baked"}),
        _o("shadowmap", "Shadow Maps", "advanced", {"shadow": "shadowmap", "pcf": 1}, {"dim": ["3d"]}, unlock=1),
        _o("cascaded", "Cascaded (CSM)", "advanced", {"shadow": "csm", "cascades": 4}, {"dim": ["3d"]}, unlock=2),
        _o("rt_shadows", "Ray-Traced", "advanced", {"shadow": "rt", "rt": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "volumetric_quality", "label": "Volumetrics", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("none", "None", "basic", {"vol": "off"}), _o("billboard_fog", "Billboard Fog", "core", {"vol": "billboard"}),
        _o("height_fog", "Height Fog", "advanced", {"vol": "height_fog"}, unlock=1),
        _o("volumetric_lights", "Volumetric Lights", "advanced", {"vol": "froxel", "god_rays": 1}, {"dim": ["3d"]}, unlock=2),
        _o("cloud_sim", "Volumetric Clouds", "advanced", {"vol": "clouds", "raymarch": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "particle_budget", "label": "Particle Budget", "group": "Visual",
     "kind": "slider", "target": "visual", "options": [
        _o("minimal_64", "Minimal ≤64", "basic", {"particles": 64}), _o("low_256", "Low ~256", "core", {"particles": 256}),
        _o("mid_1k", "Mid ~1k", "core", {"particles": 1000}),
        _o("high_8k", "High ~8k", "advanced", {"particles": 8000}, unlock=1),
        _o("gpu_100k", "GPU ~100k", "advanced", {"particles": 100000, "gpu": 1}, {"dim": ["3d"]}, unlock=2),
        _o("gpu_millions", "GPU Millions", "advanced", {"particles": -1, "gpu": 1, "collisions": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "streaming_strategy", "label": "Asset Streaming", "group": "Performance",
     "kind": "style", "target": "meta", "options": [
        _o("preload_all", "Preload All", "basic", {"stream": "preload"}),
        _o("level_load", "Per-Level Load", "core", {"stream": "level"}),
        _o("async_cells", "Async Cells", "advanced", {"stream": "cells", "async": 1}, unlock=1),
        _o("virtual_streaming", "Virtual Streaming", "advanced", {"stream": "virtual", "on_demand": 1}, {"dim": ["3d"]}, unlock=2),
        _o("predictive_stream", "Predictive", "advanced", {"stream": "predictive", "prefetch": 1}, unlock=3)]},
    {"key": "occlusion_culling", "label": "Occlusion Culling", "group": "Performance",
     "kind": "style", "target": "meta", "options": [
        _o("none", "Frustum Only", "basic", {"cull": "frustum"}),
        _o("portals", "Portals / Cells", "core", {"cull": "portals"}),
        _o("hzb", "Hi-Z Buffer", "advanced", {"cull": "hzb", "gpu": 1}, {"dim": ["3d"]}, unlock=2),
        _o("software_occlusion", "Software Occlusion", "advanced", {"cull": "software"}, {"dim": ["3d"]}, unlock=2),
        _o("gpu_driven_cull", "GPU-Driven", "advanced", {"cull": "gpu_driven", "indirect": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "crowd_rendering", "label": "Crowd Rendering", "group": "Performance",
     "kind": "style", "target": "geometry", "options": [
        _o("none", "None", "basic", {"crowd": "off"}), _o("few_unique", "Few Unique", "core", {"crowd": "unique"}),
        _o("instanced_crowd", "Instanced", "advanced", {"crowd": "instanced", "variation": 1}, unlock=1),
        _o("impostor_crowd", "Impostors", "advanced", {"crowd": "impostors", "lod": 1}, {"dim": ["3d"]}, unlock=2),
        _o("gpu_crowd_sim", "GPU Crowd Sim", "advanced", {"crowd": "gpu_sim", "thousands": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "color_pipeline", "label": "Color Pipeline & HDR", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("srgb_8bit", "sRGB 8-bit", "basic", {"color": "srgb8"}),
        _o("linear_workflow", "Linear Workflow", "core", {"color": "linear"}),
        _o("hdr10", "HDR10", "advanced", {"color": "hdr10", "wide_gamut": 1}, unlock=2),
        _o("dolby_vision_like", "Dynamic HDR", "advanced", {"color": "hdr_dynamic", "tone_curve": 1}, unlock=3),
        _o("aces_full", "ACES Full", "advanced", {"color": "aces", "ocio": 1}, unlock=2)]},
    {"key": "tessellation_displacement", "label": "Tessellation & Displacement", "group": "Geometry",
     "kind": "style", "target": "geometry", "options": [
        _o("none", "None", "basic", {"tess": "off"}), _o("normal_map_fake", "Normal-Map Fake", "core", {"tess": "normal"}),
        _o("parallax", "Parallax Occlusion", "advanced", {"tess": "pom"}, {"dim": ["3d"]}, unlock=1),
        _o("hardware_tess", "Hardware Tessellation", "advanced", {"tess": "hardware", "displacement": 1}, {"dim": ["3d"]}, unlock=2),
        _o("adaptive_tess", "Adaptive / Micropoly", "advanced", {"tess": "adaptive", "micropoly": 1}, {"dim": ["3d"]}, unlock=3)]},
    {"key": "decal_system", "label": "Decals", "group": "Visual",
     "kind": "style", "target": "visual", "options": [
        _o("none", "None", "basic", {"decal": "off"}), _o("texture_quads", "Texture Quads", "core", {"decal": "quads"}),
        _o("projected", "Projected Decals", "advanced", {"decal": "projected"}, {"dim": ["3d"]}, unlock=1),
        _o("deferred_decals", "Deferred Decals", "advanced", {"decal": "deferred", "blend": 1}, {"dim": ["3d"]}, unlock=2),
        _o("mesh_decals", "Mesh Decals + Wear", "advanced", {"decal": "mesh", "dynamic_wear": 1}, {"dim": ["3d"]}, unlock=3)]},
]

AXIS_BY_KEY: dict[str, dict] = {a["key"]: a for a in AXES}
_SLIDER_RANK = {"ultralow": 0, "low": 1, "basic": 1, "core": 2, "mid": 2,
                "high": 3, "advanced": 3, "cinematic": 4, "micropoly": 5}


# ──────────────────────────────────────────────────────────────────────────
# SPEC MATCHING — only options that pertain to the spec are available.
# ──────────────────────────────────────────────────────────────────────────
def _spec_get(spec: dict, key: str) -> str:
    return str((spec or {}).get(key, "") or "").lower()


def option_fits_spec(opt: dict, spec: dict) -> bool:
    """An option is offered only if it pertains to the current spec."""
    f = opt.get("spec") or {}
    dim = _spec_get(spec, "dimension") or _spec_get(spec, "dim")
    genre = _spec_get(spec, "genre")
    era = _spec_get(spec, "era")
    if f.get("dim") and dim and dim not in [d.lower() for d in f["dim"]]:
        return False
    if f.get("genre") and genre and genre not in [g.lower() for g in f["genre"]]:
        return False
    if f.get("genre_not") and genre and genre in [g.lower() for g in f["genre_not"]]:
        return False
    if f.get("era") and era and era not in [e.lower() for e in f["era"]]:
        return False
    return True


def available_options(axis_key: str, spec: dict, stage_index: int = 99) -> list[dict]:
    """Return only the options for `axis_key` that pertain to the spec AND
    have unlocked at the given snowball stage (escalation)."""
    axis = AXIS_BY_KEY.get(axis_key)
    if not axis:
        return []
    return [o for o in axis["options"]
            if option_fits_spec(o, spec) and o.get("unlock", 0) <= stage_index]


def resolve(spec: dict, stage_index: int = 99, advanced_only: bool = False) -> dict:
    """Full spec-aware catalog for the questionnaire/UI: every axis with only
    its spec-relevant, stage-unlocked options."""
    out_axes = []
    for axis in AXES:
        opts = available_options(axis["key"], spec, stage_index)
        if advanced_only:
            opts = [o for o in opts if o["tier"] == "advanced"] or opts
        if not opts:
            continue
        adv = sum(1 for o in opts if o["tier"] == "advanced")
        out_axes.append({
            "key": axis["key"], "label": axis["label"], "group": axis["group"],
            "kind": axis["kind"], "target": axis["target"],
            "options": [{"id": o["id"], "label": o["label"], "tier": o["tier"],
                         "unlock": o["unlock"], "blurb": o.get("blurb", "")} for o in opts],
            "advanced_count": adv, "total": len(opts),
            "advanced_majority": adv > (len(opts) - adv),
        })
    return {
        "spec": {"genre": _spec_get(spec, "genre"), "era": _spec_get(spec, "era"),
                 "dimension": _spec_get(spec, "dimension") or _spec_get(spec, "dim")},
        "stage_index": stage_index, "axes": out_axes,
        "axis_count": len(out_axes),
        "total_options": sum(a["total"] for a in out_axes),
        "advanced_options": sum(a["advanced_count"] for a in out_axes),
    }


# ──────────────────────────────────────────────────────────────────────────
# EFFECTS — every chosen option contributes its REAL forge directive set.
# This is what makes each choice an "actual change" (not just a stamp).
# ──────────────────────────────────────────────────────────────────────────
def find_option(axis_key: str, option_id: str) -> dict | None:
    axis = AXIS_BY_KEY.get(axis_key)
    if not axis:
        return None
    for o in axis["options"]:
        if o["id"] == option_id:
            return o
    return None


def apply_effects(selections: dict, spec: dict | None = None,
                  stage_index: int = 99) -> dict:
    """Fold every selected option's `effect` into one flat 'forge directives'
    dict — the concrete, applied changes the snowball builds against.

    `selections` = {axis_key: option_id}. Invalid / spec-mismatched / not-yet
    unlocked selections are dropped (and reported) so the build stays coherent.
    """
    spec = spec or {}
    directives: dict[str, Any] = {}
    applied: dict[str, str] = {}
    dropped: list[dict] = []
    advanced_picked = 0
    for axis_key, option_id in (selections or {}).items():
        opt = find_option(axis_key, option_id)
        if not opt:
            dropped.append({"axis": axis_key, "option": option_id, "why": "unknown"})
            continue
        if not option_fits_spec(opt, spec):
            dropped.append({"axis": axis_key, "option": option_id, "why": "off_spec"})
            continue
        if opt.get("unlock", 0) > stage_index:
            dropped.append({"axis": axis_key, "option": option_id, "why": "locked",
                            "unlocks_at": opt["unlock"]})
            continue
        applied[axis_key] = option_id
        if opt["tier"] == "advanced":
            advanced_picked += 1
        for k, v in (opt.get("effect") or {}).items():
            # namespaced so two axes can't silently clobber, but keep the raw
            # effect too for easy gate checks.
            directives[f"{axis_key}.{k}"] = v
            directives.setdefault(k, v)
    return {
        "applied": applied, "directives": directives, "dropped": dropped,
        "applied_count": len(applied), "advanced_count": advanced_picked,
        "dropped_count": len(dropped),
    }


def stamp_for(selections: dict, spec: dict | None = None,
              stage_index: int = 99) -> dict[str, str]:
    """The per-item/asset 'applied_choices' stamp (string-valued) used by the
    choice-gate to prove every choice is reflected on every step."""
    res = apply_effects(selections, spec, stage_index)
    return {ax: oid for ax, oid in res["applied"].items()}


def catalog_stats() -> dict:
    total = sum(len(a["options"]) for a in AXES)
    adv = sum(1 for a in AXES for o in a["options"] if o["tier"] == "advanced")
    tg = len(ADVANCED_TOGGLES)
    return {"axes": len(AXES), "total_options": total, "advanced_options": adv,
            "advanced_majority": adv > (total - adv),
            "avg_options_per_axis": round(total / max(1, len(AXES)), 1),
            "advanced_toggles": tg,
            "total_choice_points": total + tg,
            "advanced_choice_points": adv + tg,
            "advanced_majority_overall": (adv + tg) > (total - adv)}


# ──────────────────────────────────────────────────────────────────────────
# ADVANCED TOGGLES — a massive set of genuine on/off advanced feature flags.
# Every toggle is a REAL capability with its own forge directive + spec filter
# (advanced tier by definition), so advanced choice-points OUT-NUMBER the
# regular per-axis options. Toggles fold into the same directive map + gates.
# ──────────────────────────────────────────────────────────────────────────
def _tg(tid: str, label: str, effect: dict, spec: dict | None = None,
        unlock: int = 0) -> dict:
    return {"id": tid, "label": label, "tier": "advanced",
            "effect": effect, "spec": spec or {}, "unlock": unlock}


_D3 = {"dim": ["3d"]}
ADVANCED_TOGGLES: list[dict] = [
    _tg("rt_global_illumination", "Ray-Traced GI", {"rtgi": 1}, _D3, 3),
    _tg("rt_reflections", "Ray-Traced Reflections", {"rt_refl": 1}, _D3, 3),
    _tg("rt_shadows", "Ray-Traced Shadows", {"rt_shadows": 1}, _D3, 3),
    _tg("rt_ambient_occlusion", "Ray-Traced AO", {"rtao": 1}, _D3, 3),
    _tg("contact_shadows", "Contact Shadows", {"contact_shadows": 1}, _D3, 2),
    _tg("screen_space_gi", "Screen-Space GI", {"ssgi": 1}, _D3, 2),
    _tg("screen_space_reflections", "Screen-Space Reflections", {"ssr": 1}, _D3, 2),
    _tg("temporal_aa", "Temporal AA", {"taa": 1}, _D3, 2),
    _tg("motion_vectors", "Motion Vectors", {"motion_vectors": 1}, _D3, 2),
    _tg("mesh_shaders", "Mesh Shaders", {"mesh_shaders": 1}, _D3, 3),
    _tg("gpu_skinning", "GPU Skinning", {"gpu_skinning": 1}, _D3, 1),
    _tg("gpu_instancing", "GPU Instancing", {"instancing": 1}, _D3, 1),
    _tg("async_compute", "Async Compute", {"async_compute": 1}, _D3, 2),
    _tg("variable_rate_shading", "Variable-Rate Shading", {"vrs": 1}, _D3, 3),
    _tg("frame_generation", "Frame Generation", {"frame_gen": 1}, _D3, 3),
    _tg("dynamic_resolution", "Dynamic Resolution", {"dynamic_res": 1}, None, 1),
    _tg("hdr_output", "HDR Output", {"hdr": 1}, None, 2),
    _tg("wide_color_gamut", "Wide Color Gamut", {"wcg": 1}, None, 2),
    _tg("bloom", "Bloom", {"bloom": 1}),
    _tg("lens_flare", "Lens Flare", {"lens_flare": 1}, None, 1),
    _tg("chromatic_aberration", "Chromatic Aberration", {"chromatic": 1}, None, 1),
    _tg("film_grain", "Film Grain", {"grain": 1}),
    _tg("depth_of_field", "Depth of Field", {"dof": 1}, None, 1),
    _tg("motion_blur", "Motion Blur", {"motion_blur": 1}, None, 1),
    _tg("vignette", "Vignette", {"vignette": 1}),
    _tg("subsurface_scattering", "Subsurface Scattering", {"sss": 1}, _D3, 2),
    _tg("parallax_occlusion", "Parallax Occlusion", {"pom": 1}, _D3, 2),
    _tg("anisotropic_filtering", "Anisotropic Filtering", {"aniso": 16}, _D3, 1),
    _tg("soft_particles", "Soft Particles", {"soft_particles": 1}, _D3, 1),
    _tg("gpu_particles", "GPU Particles", {"gpu_particles": 1}, _D3, 2),
    _tg("destructible_environment", "Destructible Environment", {"destructible": 1}, None, 2),
    _tg("ragdoll_physics", "Ragdoll Physics", {"ragdoll": 1}, _D3, 1),
    _tg("active_ragdoll", "Active Ragdoll", {"active_ragdoll": 1}, _D3, 3),
    _tg("inverse_kinematics", "Full-Body IK", {"fbik": 1}, _D3, 2),
    _tg("foot_placement_ik", "Foot Placement IK", {"foot_ik": 1}, _D3, 2),
    _tg("motion_matching", "Motion Matching", {"motion_matching": 1}, _D3, 3),
    _tg("procedural_animation", "Procedural Animation", {"proc_anim": 1}, None, 2),
    _tg("dynamic_music", "Dynamic / Adaptive Music", {"adaptive_music": 1}, None, 1),
    _tg("spatial_audio", "3D Spatial Audio", {"spatial_audio": 1}, _D3, 1),
    _tg("audio_occlusion", "Audio Occlusion", {"audio_occlusion": 1}, _D3, 2),
    _tg("reverb_zones", "Reverb Zones", {"reverb_zones": 1}, None, 1),
    _tg("haptic_feedback", "Rich Haptics", {"haptics": 1}, None, 1),
    _tg("photo_mode", "Photo Mode", {"photo_mode": 1}, None, 1),
    _tg("replay_system", "Replay System", {"replay": 1}, None, 2),
    _tg("cloud_saves", "Cloud Saves", {"cloud_save": 1}, None, 1),
    _tg("cross_platform_play", "Cross-Platform Play", {"crossplay": 1}, None, 2),
    _tg("cross_progression", "Cross-Progression", {"cross_progress": 1}, None, 2),
    _tg("mod_support", "Mod Support", {"mods": 1}, None, 2),
    _tg("ugc_tools", "UGC Creation Tools", {"ugc": 1}, None, 3),
    _tg("colorblind_modes", "Colorblind Modes", {"colorblind": 1}),
    _tg("subtitles_styled", "Styled Subtitles", {"subtitles": 1}),
    _tg("full_remap", "Full Input Remap", {"remap": 1}),
    _tg("aim_assist", "Aim Assist", {"aim_assist": 1}, None, 1),
    _tg("difficulty_assist", "Difficulty Assist Menu", {"assist_menu": 1}),
    _tg("anti_cheat", "Anti-Cheat", {"anti_cheat": 1}, None, 2),
    _tg("server_authoritative", "Server-Authoritative", {"authoritative": 1}, None, 2),
    _tg("client_prediction", "Client Prediction", {"prediction": 1}, None, 2),
    _tg("lag_compensation", "Lag Compensation", {"lag_comp": 1}, None, 2),
    _tg("seamless_world", "Seamless Open World", {"seamless": 1}, None, 3),
    _tg("level_streaming", "Level Streaming", {"streaming": 1}, None, 2),
    _tg("dynamic_weather_tog", "Dynamic Weather", {"weather": 1}, None, 1),
    _tg("day_night_tog", "Day/Night Cycle", {"day_night": 1}, None, 1),
    _tg("interactive_water", "Interactive Water", {"interactive_water": 1}, _D3, 2),
    _tg("volumetric_clouds", "Volumetric Clouds", {"vol_clouds": 1}, _D3, 3),
    _tg("global_fog", "Global Volumetric Fog", {"vol_fog": 1}, _D3, 2),
]
_TOGGLE_BY_ID = {t["id"]: t for t in ADVANCED_TOGGLES}


def find_toggle(tid: str) -> dict | None:
    return _TOGGLE_BY_ID.get(tid)


def toggle_catalog(spec: dict, stage_index: int = 99) -> list[dict]:
    """Only the advanced toggles that pertain to the spec + stage."""
    out = []
    for t in ADVANCED_TOGGLES:
        if option_fits_spec(t, spec) and t.get("unlock", 0) <= stage_index:
            out.append({"id": t["id"], "label": t["label"], "tier": "advanced",
                        "unlock": t["unlock"]})
    return out


def apply_toggles(enabled: list, spec: dict | None = None,
                  stage_index: int = 99) -> dict:
    """Fold enabled advanced toggles into a directive map (dropping off-spec /
    locked / unknown ones)."""
    spec = spec or {}
    directives: dict = {}
    applied: list = []
    dropped: list = []
    for tid in (enabled or []):
        t = find_toggle(tid)
        if not t:
            dropped.append({"toggle": tid, "why": "unknown"}); continue
        if not option_fits_spec(t, spec):
            dropped.append({"toggle": tid, "why": "off_spec"}); continue
        if t.get("unlock", 0) > stage_index:
            dropped.append({"toggle": tid, "why": "locked", "unlocks_at": t["unlock"]}); continue
        applied.append(tid)
        for k, v in t["effect"].items():
            directives[f"toggle.{tid}.{k}"] = v
            directives.setdefault(k, v)
    return {"applied": applied, "directives": directives, "dropped": dropped,
            "applied_count": len(applied), "dropped_count": len(dropped)}


def defaults(spec: dict, stage_index: int = 99, floor: str = "highest") -> dict:
    """'Standard set to highest (as minimum)': for every axis pick the HIGHEST
    available (most advanced, highest-unlock) spec-valid option as the default
    selection. Returns {axis_key: option_id}."""
    out: dict = {}
    for axis in AXES:
        opts = available_options(axis["key"], spec, stage_index)
        if not opts:
            continue
        if floor == "highest":
            # prefer advanced tier, then highest unlock, then last authored.
            adv = [o for o in opts if o["tier"] == "advanced"] or opts
            pick = sorted(adv, key=lambda o: o.get("unlock", 0))[-1]
        else:
            pick = opts[0]
        out[axis["key"]] = pick["id"]
    return out


def full_catalog(spec: dict, stage_index: int = 99) -> dict:
    """Everything the questionnaire needs: spec-filtered axes + advanced toggles
    + the highest-as-minimum default selections + combined stats."""
    base = resolve(spec, stage_index=stage_index)
    base["toggles"] = toggle_catalog(spec, stage_index)
    base["toggle_count"] = len(base["toggles"])
    base["defaults"] = defaults(spec, stage_index, floor="highest")
    base["standard_floor"] = "highest"
    base["combined_choice_points"] = base["total_options"] + base["toggle_count"]
    return base
