"""Evidence-based standalone game-studio gap inventory, not a completion claim.

The presence of an API, model interface, feature module or reference simulator
never establishes the independently observed release acceptance stated here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

SCHEMA = "skeleton.jeeves.game_production_gaps.v1"
# Area, gap, independent acceptance condition, existing source foundation.
ROWS = (
("production","full_game_pipeline","author, build, install and finish an original complete game","game production workbench"),
("production","autonomous_recovery","resume real long projects after crashes with zero source loss","hash-chained production ledger"),
("production","retry_all_quality_gates","repair and independently recheck failures until satisfactory","bounded source/boot repair"),
("production","parallel_workflows","coordinate all content dependencies and cross-editor jobs","existing orchestration plane"),
("production","signed_installers","real first install, update, uninstall and recovery across platforms","App Assembly CI"),
("production","game_release_builds","proven reproducible signed playable game binaries","Godot source packaging"),
("production","complete_end_to_end_play","real full win/fail/alternate playthrough evidence","bounded headless boot"),
("story","full_longform_authoring","complete chapters, acts, scenes, all branches and endings","story canon fabric"),
("story","character_psychology_arcs","unique believable flaws, drives, earned transformation and endings","narrative scene authoring"),
("story","literary_prose_voice","blind expert literary evaluations, distinct voices and no imitation","book-level source story structure"),
("story","setup_payoff_closure","close all consequential authored plot threads and red herrings","chapter highlight continuity"),
("story","branch_consequence_logic","prove every critical choice has sustained game-state effects","narrative action reference runtime"),
("story","quest_solvable_variants","execute all quest detours, dead ends, creative solutions and retries","quest director and solver"),
("story","dialogue_subtext_depth","test originality, acting subtext, contextual variations and voice fit","canonical scene dialogue"),
("story","visual_voice_continuity","real rendered face, outfit and spoken-acoustic identity proof","immutable story continuity contract"),
("direction","shot_storyboard_coverage","review every authored scene through canonical shotboard validator","cinematic source QC"),
("direction","cinematic_camera_blocking","execute, not merely describe, camera positions, cuts and motion","shot/camera plan"),
("direction","performance_acting","real acting direction, facial animation and vocal emotion QA","cinematic director notes"),
("direction","cinematic_light_and_grade","render and independently compare all authored lighting/grade cues","regional palette contract"),
("direction","dramatic_emotional_impact","blind audience evaluation and plot/pacing improvement loop","chapter tension verifier"),
("direction","interactive_cutscene_runtime","play, skip, pause, branch and restore shot continuity in game","logical-clock cinematic runtime"),
("direction","audio_shot_synchronization","actual audio/voice/subtitle alignment to frame timeline","shotboard dialogue mapping"),
("gameplay","npc_living_behaviors","fully integrated NPC memory, schedules, world economy and player response","storyworld NPC modules"),
("gameplay","all_mechanics_playable","combat, physics, items, tools, survival, vehicles and game rules","gameplay subsystem candidates"),
("gameplay","all_path_alternatives","verify transport, water, air, shortcuts and nonlinear navigation","world navigation authoring"),
("gameplay","balanced_progression","blind player difficulty, reward, encounter and economy QA","simulation frameworks"),
("gameplay","endings_replayable","real repeatable alternative endings and canon continuity","narrative branches"),
("gameplay","all_controller_mappings","all intended hardware/controller inputs and latency tested","emulator console registry"),
("gameplay","save_restore_migration","real corrupted-save recovery and long-term continuity","state topology"),
("assets","all_assets_provenance","every visual/audio artifact traced to legal original source","asset hash inventory"),
("assets","retro_2d_render","historically accurate palettes/tile limits/pixel look","console codecs and Scale2x"),
("assets","static_to_animated_quality","full stable believable motion for upscaled static sprites","sprite-strip animator"),
("assets","animation_rigs_shadow","skeletal deformation, secondary motion, shadow and temporal QA","bounded detail/shadow pass"),
("assets","vivid_world_and_biomes","full executable scene dressing, environment and procedural richness","stage detail generator"),
("assets","pbr_textures_shaders","real source-faithful PBR, normals, roughness and shader review","reference render"),
("assets","3d_geometry_lod","high-quality original meshes, occlusion, UV/LOD and collision","reference triangle raster"),
("assets","global_illumination","actual lighting, reflection, materials and volumetric QA","render graph evidence"),
("assets","weather_water_foliage","real runtime particles, foliage, weather, water and interaction","biome dressing metadata"),
("assets","camera_2_9d_3d_execution","actual mesh-aware 2.5D/2.9D/3D rotation and occlusion","billboard camera preview"),
("audio","original_music_composition","original themes, motifs, score arrangement and expert music review","PCM DSP remaster"),
("audio","adaptive_music_transitions","adaptive cue execution by world states with legal stems","source WAV ambience mix"),
("audio","spatial_sfx_foley","real spatial soundstage, environmental cues and mastering","audio asset processing"),
("audio","voice_localization","full voice casting and independently verified localized performances","voice IDs in canon"),
("platforms","console_renderer_completeness","real era-native 2D/2.5D/3D render for every requested platform","console target inventory"),
("platforms","emulator_port_fidelity","game execution, legal porting, input and native hardware compatibility","reference emulator targets"),
("platforms","retro_hd_authenticity","blind original-display vs modern upscale parity evaluations","integer pixel aspect"),
("platforms","native_sdk_deployment","licensed SDK packages, signed native builds and first-boot receipts","not qualified"),
("platforms","modern_gpu_quality","full advanced geometry, ray tracing, animation, PBR, HDR and frame pacing","render graph drafts"),
("platforms","mobile_offline_parity","offline/battery/RAM/thermal phone operation for intended eras","resource plans"),
("platforms","sustained_performance","real frame time, memory, power and thermal on all supported hardware","reference performance contracts"),
("experience","exposed_editors","Academy, Galaxy, Snowball and Jeeves cockpit all functionally wired","new CLI only"),
("experience","accessibility","blind user accessibility/subtitle/contrast/input/navigation QA","UI contracts"),
("experience","playtester_engagement","representative players complete games and report satisfaction","not validated"),
("experience","internationalization","all target language/font/voice and UI localization quality","localization specs"),
("research","top_sales_rank_sources","independent title sales/source measurement from target eras","operator quality benchmark"),
("research","critical_quality_anchors","verified review methodology, title/version/console comparability","critic-score gate"),
("research","copyright_and_licenses","permission for every source asset, emulator and training example","provenance contracts"),
("research","anti_plagiarism","expert textual/visual/audio similarity and originality review","local review assertions"),
("ai","model_training_real_checkpoints","real training/inference with loaded production weights and reproducible results","governed provider gateway"),
("ai","adversarial_llm_improvement","trained challenger/reviewer with held-out validation gains","mirror/review contracts"),
("ai","upscale_quality_model_gains","measured held-out asset restoration/animation upgrades and approved promotion","upscale priority candidate queue"),
("ai","legally_sourced_multimedia_learning","actual licensed public media comparisons and provenance","Dragon research architecture"),
("ai","multispectral_training_saturation","repeat live simulations until no novel improvement with receipts","multisim contracts"),
("ai","dataset_governance","rights, privacy, duplicates, held-out leakage checks and opt-outs","training governance"),
("assurance","per_asset_per_scene_review","professional human and machine evaluation of every delivered artifact","source hash/shotboard QA"),
("assurance","production_ci_and_e2e","all release checks and end-to-end test matrix on exact head","GitHub workflows"),
("assurance","runtime_security_and_mods","safe user content, imported assets, mods, secrets and sandboxing","security scanner contracts"),
("assurance","release_recovery_and_rollback","signed releases, backups and reliable operational rollback","local immutable receipts"),
("assurance","true_player_business_metrics","completion, retention, enjoyment and real user ratings","no measured live product data"),
)


def gaps(root: Path) -> dict[str,Any]:
    from skeleton.developer.game_cli import _load
    from skeleton.developer.jeeves_game_upscale import fidelity_matrix
    _load(root)
    sections:dict[str,int]={}
    items=[]
    for section,key,acceptance,foundation in ROWS:
        sections[section]=sections.get(section,0)+1
        items.append({
            "gap_id":key,"area":section,"required_release_evidence":acceptance,
            "existing_foundation":foundation,
            "qualification":"not_independently_proven",
            "source_implementation_is_not_end_to_end_proof":True,
        })
    measured={}
    from skeleton.developer.jeeves_game_production import status
    try:
        s=status(root)
        measured["production_policy_present"]=True
        measured["passed_technical_gates"]=s["passed_gates"]
        measured["total_quality_gates"]=len(s["gates"])
        measured["production_complete"]=s["project_complete"]
    except (OSError,ValueError):
        measured["production_policy_present"]=False
        measured["passed_technical_gates"]=None
        measured["production_complete"]=False
    from skeleton.developer.jeeves_game_direction import audit
    try:
        d=audit(root)
        measured["canonical_story_history_validated"]=d["canonical_source_replay_passed"]
        measured["cinematic_scene_coverage"]=d["cinematic_scene_coverage"]
        measured["artistic_panel_independently_authenticated"]=False
    except (OSError,ValueError):
        measured["canonical_story_history_validated"]=False
        measured["cinematic_scene_coverage"]=None
        measured["artistic_panel_independently_authenticated"]=False
    matrix=fidelity_matrix()
    measured["registered_console_targets"]=matrix["declared_console_targets"]
    measured["native_game_renderers_certified_by_workbench"]=0
    return {
        "ok":True,"action":"production-gap-matrix","schema":SCHEMA,
        "scope":"complete_standalone_game_studio",
        "gap_count":len(items),"areas":sections,"gaps":items,
        "live_project_evidence":measured,
        "gaps_are_missing_release_proof_not_proof_of_no_source_code":True,
        "catalog_guaranteed_complete_for_every_possible_game_genre":False,
        "standalone_studio_qualified":False,
    }
