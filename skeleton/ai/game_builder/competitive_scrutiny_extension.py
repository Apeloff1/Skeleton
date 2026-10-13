"""Fifty-one additional, distinct deep scrutiny protocols (total catalog: 102).

Each probe defines a falsifiable question, matched trial, measurable output
and a destructive/control perturbation. No repeated headings or proxy score
inflation: every dimension is independently replayed, not a new name for an
existing score. Existing 51 historical IDs and script digests stay stable.
"""
EXTRA_FACETS={
 "gameplay":(
  ("save_recovery","Can a damaged or interrupted save recover play coherently?","kill process during deterministic checkpoint writes and relaunch","recovery success and lost-progress bound","partial writes and unexpected profile migrations"),
  ("economy_exploits","Can resource exchange avoid runaway inflation and infinite loops?","replay shop, loot, crafting and trade sequences","net resource conservation and exploit incidence","duplicate transactions and buy-sell arbitrage loops"),
  ("ai_counterplay","Can players infer and counter AI tactics without unfair omniscience?","blind enemy-policy perturbation across player profiles","counter-strategy diversity and perceived fairness","input-reading and hidden-knowledge opponents"),
  ("network_jitter","Do multiplayer interactions remain fair under network impairment?","replay authoritative game state with jitter and packet loss","desync rate and recovery time","reordering, burst loss and maliciously delayed packets"),
  ("physics_stability","Do world constraints remain stable at scene/clock extremes?","deterministic time-step sweeps and stacked collisions","invariant failures per replay minute","extreme frame step and object tunnelling"),
  ("procedural_validity","Does generation preserve traversability, agency and narrative rules?","generate seeded maps across adversarial parameter boundaries","valid-world fraction and distinct viable paths","unsolvable start and disconnected objective clusters"),
  ("speedrun_integrity","Can sequence breaks be supported intentionally rather than accidentally?","expert route mutation and checkpoint-skip replay","intended shortcut coverage and lock bypass count","out-of-bounds collision and save warp"),
  ("haptic_feedback","Do vibration and adaptive input cues provide useful optional information?","matched cue-on, cue-off and simplified controller sessions","comprehension benefit without forced haptics","missing vibration device and excessive stimulation"),
  ("camera_ownership","Does the player retain legible viewpoint control under stress?","camera obstruction, tight spaces and chase transitions","target visibility and agency retention","forced snap, occluded boss and motion sickness"),
  ("loading_continuity","Does loading preserve player context without destroying pacing?","transition across dense streaming zones on real hardware","interactive availability and continuity","shader stutter and long black-frame pause"),
  ("social_simulation","Do factions and companions respond consistently to evolving reputation?","branch historical faction loyalty and witnessed betrayal","stable social-state response and propagation delay","cross-faction information leakage"),
  ("crafting_depth","Does crafting reward insight instead of rote recipe grind?","matched novice/expert crafting and resource constraints","viable strategy diversity and experimentation reward","single dominant recipe and invalid crafting state"),
  ("difficulty_adaptation","Does adaptation respect player consent, fairness and mastery?","compare manual and adaptive mode over skill transitions","failure distribution and control transparency","hidden rubberbanding and skill punishment"),
  ("offline_resilience","Can single-player and homebrew game functions survive service loss?","disable network, clock and account dependencies","playable feature and recoverable-state fraction","offline launch refusal and revoked license cache"),
 ),
 "graphics":(
  ("frame_pacing","Are frame-time tails consistent even when mean FPS looks good?","trace real-hardware camera and effect stress paths","99th percentile frame interval and stutter rate","shader compile spikes and asset upload stalls"),
  ("resolution_scaling","Do upscaling and dynamic resolution preserve informational clarity?","sweep native and reconstructed pixels across GPU tiers","small-target legibility and temporal alias error","thin-line shimmer and HUD degradation"),
  ("shader_correctness","Do materials render consistently through pipeline permutations?","compile and render all supported feature/platform variants","artifact and compilation failure incidence","undefined precision and driver-dependent branches"),
  ("occlusion_culling","Does geometry pruning save cost without popping visible objects?","camera traversal with rapid turns and portals","missing-visible geometry time and saved render cost","culling lag and close-wall clipping"),
  ("material_language","Can visual surfaces communicate game physics reliably?","blind classify friction, hazards and interactivity from materials","semantic material recognition agreement","misleading hazard shine and invisible traversal affordance"),
  ("face_expression","Are expressions and lip motion synchronized with narrative intent?","sample emotional dialogue across viewpoints and languages","recognition and temporal alignment","viseme mismatch and expression snapping"),
  ("environment_density","Does decorative richness preserve player wayfinding?","vary procedural prop density under equal gameplay seed","navigation completion and clutter cost","critical-item camouflage at density extremes"),
  ("fov_comfort","Can camera/FOV adapt to different viewing distances and impairments?","handheld, monitor and VR comfort trials with FOV controls","discomfort incidents and spatial awareness","forced shake, tunnel vision and fixed motion blur"),
  ("animation_interrupts","Do interrupted actions preserve readable state and collisions?","cancel, stagger and reverse animations at every frame","transition invariant failures and anticipation delay","contact teleport and noncancelable input lag"),
  ("transparency_order","Do layered effects, particles and UI compose coherently?","stress alpha stacks at multiple view angles","visibility score and sorting artifacts","depth sorting and flickering translucent surfaces"),
  ("capture_consistency","Does captured gameplay represent actual rendered play reliably?","compare in-game rendered state to approved screenshots/video","frame content parity and nondisclosure rate","photo-mode-only quality and misleading captures"),
  ("visual_memory_budget","Do large original worlds remain stable within platform VRAM?","stream many biomes and teleport stress on target device","peak memory, eviction stalls and fallback quality","out-of-memory and silent texture-resolution collapse"),
 ),
 "sound":(
  ("audio_occlusion","Does environmental sound attenuate consistently with material and geometry?","repeat footsteps and hazards behind walls and doors","acoustic occlusion agreement and danger detection","sound through solid walls and missing cave reverb"),
  ("subtitle_timing","Are subtitle timings and speaker labels accurate across latency modes?","time-code dialogue and system load while captions remain enabled","caption time offset and character attribution","desynced localization and overlapping labels"),
  ("speech_fatigue","Does extended dialogue preserve listening comfort and focus?","multi-hour equivalent dialogue chapter sessions","comprehension, replay frequency and fatigue","continuous exposition without pauses"),
  ("music_branch_logic","Do musical stems obey branching quest state rather than arbitrary triggers?","replay mutually exclusive narrative states","theme-state coherence and incorrect reuse","victory theme during loss and unresolved combat loops"),
  ("acoustic_priority","Are life-saving cues audible despite maximum concurrency?","stack boss, NPC, weather, UI, inventory and crowd cues","critical cue detection under saturation","ducking collapse and all-voices-priority"),
  ("audio_memory_budget","Do large audio banks stream without clicks or stale cues?","hot-swap biomes, music layers and localized speech banks","underrun and peak streaming memory","buffer thrash and abrupt discontinuity"),
  ("voice_variation","Can repeated NPC cues avoid audible robotic repetition?","repeat identical context and nearby NPC encounters","perceived variation without semantic drift","identical bark loops and random emotional mismatch"),
  ("reverb_consistency","Do acoustic spaces match room size and materials?","traverse outdoor, tunnel, chamber, vehicle and cave","blind room-type and distance accuracy","reverb tails across teleport and implausible wetness"),
  ("controller_audio_haptics","Are sounds and haptic accents synchronized without forcing feedback?","replay action cues with vibration toggled","crossmodal timing and selectable comfort","out-of-sync rumble and forced tactile cues"),
  ("language_mix_parity","Do translated vocals preserve intelligibility with original score?","matched multi-language dialogue loudness calibration","word recognition and semantic emphasis","overmasked low-volume translated speech"),
  ("audio_fallback","Does the game degrade gracefully without premium audio support?","simulate mono, Bluetooth delay and absent spatial renderer","task success and cue equivalence","vanishing directional clues in mono"),
 ),
 "storyline":(
  ("quest_deadlock","Can chained optional quests resolve when NPCs die or worlds change?","kill, relocate or delay every key witness in branch replay","reachable resolution and alternative path completeness","irreversible missing actor and orphan objective"),
  ("rumor_epistemics","Do NPC reports separate observed facts from mistaken social inference?","inject contradictory rumor with controlled witness visibility","credibility calibration and narrative causality","all rumors instantly become world truth"),
  ("unreliable_narration","Are unreliable perspectives signposted without deceiving unfairly?","compare evidence from conflicting narrators at fixed story beats","fair inference and clue recoverability","forced hidden retcon without prior evidence"),
  ("relationship_dynamics","Do companions evolve trust through decisions and memory?","run support, betrayal and neutral branches with same cast","trust transition validity and agency awareness","instant amnesia or unavoidable affection"),
  ("lore_retrievability","Can players reconnect with prior world lore after long breaks?","resume story after time gap and seek optional journal clues","correct recap and clue find rate","mandatory obscure lore and broken journal links"),
  ("time_paradox","Do time travel and rewind stories preserve their chosen causal model?","branch/replay histories under temporal interventions","timeline invariants and paradox clarity","contradictory irreversible and reversible events"),
  ("nonlinear_recap","Can non-linear scenes still preserve comprehension and agency?","play time-shifted chapter order variants","causal reconstruction and emotional stakes","chronology as random puzzle without narrative payoff"),
  ("procedural_story_authorship","Can generated quests remain coherent and avoid repeated generic plots?","produce broad seeded NPC goals and quest chains","originality, causal coherence and repetition rate","identical quest templates and broken character knowledge"),
  ("dialogue_interruptions","Can conversations recover after action, save, damage or language switch?","interrupt line and scene playback at every narrative node","dialogue context and decision preservation","double rewards and lost meaningful choices"),
  ("postgame_consequence","Do completed arcs affect an ongoing playable world consistently?","reenter regions after each ending/major choice","persistence and meaningful acknowledgement","world resets while NPCs claim otherwise"),
  ("ethical_agency","Can ethically difficult choices preserve player understanding and consent?","blind weigh morally ambiguous paths and consequences","informed choice and thematic consequence validity","unannounced irreversible harm presented as trivial"),
  ("story_accessibility","Can story and choice information be consumed with assistive modes?","screen reader, narration pace, subtitles and simplified language","comprehension parity and branching reachability","key narrative choice only in audio or tiny text"),
  ("long_horizon_consistency","Are facts and emotional arcs consistent over many hours and seeds?","100-event bounded narrative memory/replay chain","contradiction rate and character state retention","plot device memory wipe and latent relationship reversal"),
  ("emergent_world_history","Does sandbox history emerge meaningfully without a scripted victory?","run idle and player-changed simulations through world eras","historical causality and world-state believability","generic events with no lasting historical trace"),
 ),
}
if tuple(sorted(EXTRA_FACETS)) != ("gameplay","graphics","sound","storyline"):
    raise RuntimeError("missing expanded competitive scrutiny domain")
if tuple(map(lambda a:len(EXTRA_FACETS[a]),("gameplay","graphics","sound","storyline"))) != (14,12,11,14):
    raise RuntimeError("expanded scrutiny catalog must add exactly 51 independently testable facets")
