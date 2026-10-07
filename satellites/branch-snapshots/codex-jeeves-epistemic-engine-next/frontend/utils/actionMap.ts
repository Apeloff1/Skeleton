/**
 * Command Palette Action Map v16.0
 * Replaces the massive switch statement with a declarative lookup table.
 * Each action defines its type and target, eliminating 200+ switch cases.
 */

export type ActionType = 'modal' | 'code' | 'git' | 'pro' | 'exec';

export interface ActionEntry {
  type: ActionType;
  target: string;                // modal name, code action, git action, etc.
  data?: Record<string, any>;   // optional data to pass (e.g., language for tracks)
}

/**
 * Master action map: actionId → { type, target, data? }
 * Organized by command palette category for readability.
 */
export const ACTION_MAP: Record<string, ActionEntry> = {
  // ═══════════════════════════════════════════════════════════════
  // CODE ACTIONS
  // ═══════════════════════════════════════════════════════════════

  // Core Execution
  run:              { type: 'exec', target: 'executeCode' },
  compile:          { type: 'modal', target: 'compiler' },
  debug_mode:       { type: 'modal', target: 'debugger' },
  terminal:         { type: 'modal', target: 'terminal' },

  // Code Quality
  format:           { type: 'code', target: 'format' },
  lint:             { type: 'code', target: 'lint' },
  type_check:       { type: 'code', target: 'typeCheck' },
  spell_check:      { type: 'code', target: 'spellCheck' },

  // Navigation & Search
  goto_line:        { type: 'modal', target: 'gotoLine' },
  goto_symbol:      { type: 'modal', target: 'gotoSymbol' },
  find_replace:     { type: 'modal', target: 'findReplace' },
  find_all:         { type: 'modal', target: 'findAll' },
  references:       { type: 'code', target: 'findReferences' },

  // Code Structure
  fold_all:         { type: 'code', target: 'foldAll' },
  unfold_all:       { type: 'code', target: 'unfoldAll' },
  outline:          { type: 'modal', target: 'codeOutline' },
  minimap:          { type: 'code', target: 'toggleMinimap' },

  // Project Management
  template:         { type: 'modal', target: 'template' },
  language:         { type: 'modal', target: 'language' },
  new_file:         { type: 'code', target: 'newFile' },
  save_file:        { type: 'code', target: 'saveFile' },
  save_all:         { type: 'code', target: 'saveAll' },

  // Editor Features
  multi_cursor:     { type: 'code', target: 'multiCursor' },
  column_select:    { type: 'code', target: 'columnSelect' },
  duplicate_line:   { type: 'code', target: 'duplicateLine' },
  move_line:        { type: 'code', target: 'moveLine' },
  comment_toggle:   { type: 'code', target: 'toggleComment' },
  bracket_match:    { type: 'code', target: 'matchBracket' },

  // Snippets & Templates
  snippets:         { type: 'modal', target: 'snippets' },
  emmet:            { type: 'code', target: 'emmetExpand' },
  live_templates:   { type: 'modal', target: 'liveTemplates' },

  // Diff & History
  diff_view:        { type: 'modal', target: 'diffView' },
  local_history:    { type: 'modal', target: 'localHistory' },
  undo_history:     { type: 'modal', target: 'undoHistory' },

  // Advanced Refactoring
  refactor_rename:  { type: 'modal', target: 'refactorRename' },
  extract_method:   { type: 'code', target: 'extractMethod' },
  inline_variable:  { type: 'code', target: 'inlineVariable' },
  zen_mode:         { type: 'code', target: 'toggleZenMode' },
  split_editor:     { type: 'code', target: 'splitEditor' },

  // ═══════════════════════════════════════════════════════════════
  // AI TOOLS
  // ═══════════════════════════════════════════════════════════════

  // Core AI
  ai_assistant:     { type: 'modal', target: 'ai' },
  ai_pipeline:      { type: 'modal', target: 'aiPipeline' },
  debugger:         { type: 'modal', target: 'debugger' },
  code_to_app:      { type: 'modal', target: 'codeToApp' },
  imagine:          { type: 'modal', target: 'imagine' },
  multi_agent:      { type: 'modal', target: 'multiAgent' },
  intelligence:     { type: 'modal', target: 'codeIntelligence' },
  copilot:          { type: 'modal', target: 'aiCopilot' },
  ai_review:        { type: 'modal', target: 'aiReview' },
  ai_security:      { type: 'modal', target: 'aiSecurity' },

  // Game Pipelines
  npc_pipeline:         { type: 'modal', target: 'aiGameGenerator' },
  world_pipeline:       { type: 'modal', target: 'aiGameGenerator' },
  combat_pipeline:      { type: 'modal', target: 'aiGameGenerator' },
  narrative_pipeline:   { type: 'modal', target: 'aiGameGenerator' },
  animation_pipeline:   { type: 'modal', target: 'aiGameGenerator' },
  vfx_pipeline:         { type: 'modal', target: 'aiGameGenerator' },
  economy_pipeline:     { type: 'modal', target: 'aiGameGenerator' },
  bot_pipeline:         { type: 'modal', target: 'aiGameGenerator' },
  testing_pipeline:     { type: 'modal', target: 'aiGameGenerator' },
  director_pipeline:    { type: 'modal', target: 'aiGameGenerator' },
  server_pipeline:      { type: 'modal', target: 'aiGameGenerator' },
  neural_pipeline:      { type: 'modal', target: 'aiGameGenerator' },
  hardware_pipeline:    { type: 'modal', target: 'aiGameGenerator' },
  behavior_pipeline:    { type: 'modal', target: 'aiGameGenerator' },
  action_pipeline:      { type: 'modal', target: 'aiGameGenerator' },
  systems_pipeline:     { type: 'modal', target: 'aiGameGenerator' },
  music_pipeline:       { type: 'modal', target: 'musicPipeline' },
  world_models_pipeline:{ type: 'modal', target: 'aiGameGenerator' },
  procedural_pipeline:  { type: 'modal', target: 'aiGameGenerator' },
  physics_pipeline:     { type: 'modal', target: 'aiGameGenerator' },
  shader_pipeline:      { type: 'modal', target: 'aiGameGenerator' },
  ui_ux_pipeline:       { type: 'modal', target: 'aiGameGenerator' },
  localization_pipeline:{ type: 'modal', target: 'aiGameGenerator' },
  analytics_pipeline:   { type: 'modal', target: 'aiGameGenerator' },
  matchmaking_pipeline: { type: 'modal', target: 'aiGameGenerator' },
  anticheat_pipeline:   { type: 'modal', target: 'aiGameGenerator' },
  modding_pipeline:     { type: 'modal', target: 'aiGameGenerator' },
  replay_pipeline:      { type: 'modal', target: 'aiGameGenerator' },
  leaderboard_pipeline: { type: 'modal', target: 'aiGameGenerator' },
  social_pipeline:      { type: 'modal', target: 'aiGameGenerator' },
  mobile_pipeline:      { type: 'modal', target: 'aiGameGenerator' },
  vr_ar_pipeline:       { type: 'modal', target: 'aiGameGenerator' },
  crossplay_pipeline:   { type: 'modal', target: 'aiGameGenerator' },

  // ═══════════════════════════════════════════════════════════════
  // ACADEMY
  // ═══════════════════════════════════════════════════════════════

  // Learning Systems
  immersive_tutor:    { type: 'modal', target: 'immersiveTutor' },
  learning_hub:       { type: 'modal', target: 'learningHub' },
  jeeves:             { type: 'modal', target: 'jeeves' },
  jeeves_eq:          { type: 'modal', target: 'jeevesEQ' },
  adaptive_learning:  { type: 'modal', target: 'adaptiveLearning' },

  // Knowledge Bibles
  ai_bible:           { type: 'modal', target: 'bible' },
  curriculum:         { type: 'modal', target: 'curriculum' },
  bible:              { type: 'modal', target: 'bible' },
  system_design_bible:{ type: 'modal', target: 'bible', data: { topic: 'system_design' } },
  ml_bible:           { type: 'modal', target: 'bible', data: { topic: 'ml_ai' } },
  security_bible:     { type: 'modal', target: 'bible', data: { topic: 'security' } },
  devops_bible:       { type: 'modal', target: 'bible', data: { topic: 'devops' } },
  frontend_bible:     { type: 'modal', target: 'bible', data: { topic: 'frontend' } },
  backend_bible:      { type: 'modal', target: 'bible', data: { topic: 'backend' } },
  database_bible:     { type: 'modal', target: 'bible', data: { topic: 'database' } },

  // Learning Resources
  reading_corner:     { type: 'modal', target: 'readingLibrary' },
  masterclass:        { type: 'modal', target: 'megaAcademy' },
  education:          { type: 'modal', target: 'megaAcademy' },
  code_golf:          { type: 'modal', target: 'codeGolf' },
  daily_challenge:    { type: 'modal', target: 'dailyChallenge' },
  interview_prep:     { type: 'modal', target: 'interviewPrep' },

  // Subject Academies
  physics_academy:    { type: 'modal', target: 'megaAcademy', data: { initialSearch: 'Physics' } },
  math_academy:       { type: 'modal', target: 'megaAcademy', data: { initialSearch: 'Mathematics' } },
  cs_academy:         { type: 'modal', target: 'megaAcademy', data: { initialSearch: 'Computer Science' } },
  graphics_academy:   { type: 'modal', target: 'bible', data: { topic: 'graphics' } },
  networking_academy: { type: 'modal', target: 'bible', data: { topic: 'networking' } },
  game_academy:       { type: 'modal', target: 'bible', data: { topic: 'game_dev' } },
  mobile_academy:     { type: 'modal', target: 'bible', data: { topic: 'mobile' } },
  web_academy:        { type: 'modal', target: 'bible', data: { topic: 'web' } },
  cloud_academy:      { type: 'modal', target: 'bible', data: { topic: 'cloud' } },
  blockchain_academy: { type: 'modal', target: 'bible', data: { topic: 'blockchain' } },

  // Language Tracks (all 23)
  python_track:     { type: 'modal', target: 'languageTrack', data: { language: 'python' } },
  javascript_track: { type: 'modal', target: 'languageTrack', data: { language: 'javascript' } },
  typescript_track: { type: 'modal', target: 'languageTrack', data: { language: 'typescript' } },
  rust_track:       { type: 'modal', target: 'languageTrack', data: { language: 'rust' } },
  go_track:         { type: 'modal', target: 'languageTrack', data: { language: 'go' } },
  cpp_track:        { type: 'modal', target: 'languageTrack', data: { language: 'cpp' } },
  c_track:          { type: 'modal', target: 'languageTrack', data: { language: 'c' } },
  java_track:       { type: 'modal', target: 'languageTrack', data: { language: 'java' } },
  kotlin_track:     { type: 'modal', target: 'languageTrack', data: { language: 'kotlin' } },
  swift_track:      { type: 'modal', target: 'languageTrack', data: { language: 'swift' } },
  csharp_track:     { type: 'modal', target: 'languageTrack', data: { language: 'csharp' } },
  ruby_track:       { type: 'modal', target: 'languageTrack', data: { language: 'ruby' } },
  php_track:        { type: 'modal', target: 'languageTrack', data: { language: 'php' } },
  dart_track:       { type: 'modal', target: 'languageTrack', data: { language: 'dart' } },
  scala_track:      { type: 'modal', target: 'languageTrack', data: { language: 'scala' } },
  haskell_track:    { type: 'modal', target: 'languageTrack', data: { language: 'haskell' } },
  elixir_track:     { type: 'modal', target: 'languageTrack', data: { language: 'elixir' } },
  sql_track:        { type: 'modal', target: 'languageTrack', data: { language: 'sql' } },
  solidity_track:   { type: 'modal', target: 'languageTrack', data: { language: 'solidity' } },
  lua_track:        { type: 'modal', target: 'languageTrack', data: { language: 'lua' } },
  r_track:          { type: 'modal', target: 'languageTrack', data: { language: 'r' } },
  bash_track:       { type: 'modal', target: 'languageTrack', data: { language: 'bash' } },
  assembly_track:   { type: 'modal', target: 'languageTrack', data: { language: 'assembly' } },

  // Repeat Class & Achievements
  repeat_class:        { type: 'modal', target: 'repeatClass' },
  achievements:        { type: 'modal', target: 'achievements' },
  my_progress:         { type: 'modal', target: 'myProgress' },
  leaderboard:         { type: 'modal', target: 'leaderboard' },
  language_recommend:  { type: 'modal', target: 'languageRecommend' },

  // Creator's Studio & Group Chat (v16.5)
  group_chat:          { type: 'modal', target: 'groupChat' },
  pipeline_agents:     { type: 'modal', target: 'groupChat' },
  quality_control:     { type: 'modal', target: 'qualityControl' },

  // Game Factory — Full Game Creation + Compile Mode (v17.0)
  game_factory:        { type: 'modal', target: 'gameFactory' },
  build_game:          { type: 'modal', target: 'gameFactory' },
  create_game:         { type: 'modal', target: 'gameFactory' },
  compile_game:        { type: 'modal', target: 'gameFactory' },
  game_compiler:       { type: 'modal', target: 'gameFactory' },
  jeeves_compile:      { type: 'modal', target: 'gameFactory' },
  competitor_mode:     { type: 'modal', target: 'gameFactory' },
  beat_game:           { type: 'modal', target: 'gameFactory' },
  oracle:              { type: 'modal', target: 'gameFactory' },

  // Jeeves Level & Vault (v17.2)
  jeeves_level:        { type: 'modal', target: 'jeevesLevel' },
  jeeves_xp:           { type: 'modal', target: 'jeevesLevel' },
  level_system:        { type: 'modal', target: 'jeevesLevel' },
  code_vault:          { type: 'modal', target: 'vaultBrowser' },
  vault_browse:        { type: 'modal', target: 'vaultBrowser' },
  vault_browser:       { type: 'modal', target: 'vaultBrowser' },

  // v18.0 Overheat Mitigation System
  thermal_monitor:     { type: 'modal', target: 'thermalMonitor' },
  overheat:            { type: 'modal', target: 'thermalMonitor' },
  thermal:             { type: 'modal', target: 'thermalMonitor' },
  heat_monitor:        { type: 'modal', target: 'thermalMonitor' },
  cooldown:            { type: 'modal', target: 'thermalMonitor' },
  standby_pool:        { type: 'modal', target: 'thermalMonitor' },
  redundancy:          { type: 'modal', target: 'thermalMonitor' },

  // v18.5 Performance Armor (13 Subsystem Fortress)
  performance_armor:   { type: 'modal', target: 'thermalMonitor' },
  battery_barrier:     { type: 'modal', target: 'performanceArmor' },
  render_ranger:       { type: 'modal', target: 'performanceArmor' },
  gesture_glider:      { type: 'modal', target: 'performanceArmor' },
  network_nexus:       { type: 'modal', target: 'performanceArmor' },
  a11y_armor:          { type: 'modal', target: 'performanceArmor' },
  error_embrace:       { type: 'modal', target: 'performanceArmor' },
  memory_mender:       { type: 'modal', target: 'performanceArmor' },
  heap_hopper:         { type: 'modal', target: 'performanceArmor' },
  async_armor:         { type: 'modal', target: 'performanceArmor' },
  throttle_throne:     { type: 'modal', target: 'performanceArmor' },
  cache_modal:         { type: 'modal', target: 'performanceArmor' },
  cache_guard:         { type: 'modal', target: 'performanceArmor' },
  cache_blade:         { type: 'modal', target: 'performanceArmor' },
  fortress:            { type: 'modal', target: 'performanceArmor' },

  // v19.0 Resilience Forge (8 Subsystem Citadel)
  resilience_forge:    { type: 'modal', target: 'thermalMonitor' },
  resilience_root:     { type: 'modal', target: 'resilienceForge' },
  duplicate_dome:      { type: 'modal', target: 'resilienceForge' },
  mirror_mesh:         { type: 'modal', target: 'resilienceForge' },
  crash_cradle:        { type: 'modal', target: 'resilienceForge' },
  backup_beacon:       { type: 'modal', target: 'resilienceForge' },
  state_shadow:        { type: 'modal', target: 'resilienceForge' },
  failover_forge:      { type: 'modal', target: 'resilienceForge' },
  grace_guard:         { type: 'modal', target: 'resilienceForge' },
  citadel:             { type: 'modal', target: 'resilienceForge' },

  // v19.5 Knowledge Nexus Updater (22 Domain SOTA Engine)
  knowledge_nexus:     { type: 'modal', target: 'thermalMonitor' },
  knowledge_updater:   { type: 'modal', target: 'knowledgeNexus' },
  sota_updater:        { type: 'modal', target: 'knowledgeNexus' },
  sota_maintenance:    { type: 'modal', target: 'knowledgeNexus' },
  knowledge_domains:   { type: 'modal', target: 'knowledgeNexus' },
  domain_freshness:    { type: 'modal', target: 'knowledgeNexus' },
  corpus_tracker:      { type: 'modal', target: 'knowledgeNexus' },

  // v20.0 Sentinel Array (10 Advanced Subsystem Command Center)
  sentinel_array:      { type: 'modal', target: 'thermalMonitor' },
  quantum_quorum:      { type: 'modal', target: 'sentinelArray' },
  neural_nexus:        { type: 'modal', target: 'sentinelArray' },
  chrono_cache:        { type: 'modal', target: 'sentinelArray' },
  vortex_validator:    { type: 'modal', target: 'sentinelArray' },
  phalanx_proxy:       { type: 'modal', target: 'sentinelArray' },
  oracle_optimizer:    { type: 'modal', target: 'sentinelArray' },
  titan_throttle:      { type: 'modal', target: 'sentinelArray' },
  sentinel_sync:       { type: 'modal', target: 'sentinelArray' },
  abyss_analyzer:      { type: 'modal', target: 'sentinelArray' },
  zenith_zone:         { type: 'modal', target: 'sentinelArray' },

  // STEM Academy (v16.5)
  math_academy_full:       { type: 'modal', target: 'mathAcademyFull' },

  // v22.0 Quantum Factory Core (7 Ultra-Deep Domains)
  quantum_factory:         { type: 'modal', target: 'gameFactory' },
  narrative_loom:          { type: 'modal', target: 'gameFactory' },
  render_pipeline:         { type: 'modal', target: 'quantumFactory' },
  social_fabric:           { type: 'modal', target: 'quantumFactory' },
  metagame_ops:            { type: 'modal', target: 'quantumFactory' },
  physics_vault:           { type: 'modal', target: 'quantumFactory' },
  audio_sphere:            { type: 'modal', target: 'quantumFactory' },
  ux_architect:            { type: 'modal', target: 'quantumFactory' },

  // v23.0 Jeeves AAA Game Builder
  game_builder:            { type: 'modal', target: 'gameFactory' },
  build_aaa_game:          { type: 'modal', target: 'gameBuilder' },
  jeeves_build:            { type: 'modal', target: 'gameBuilder' },

  // v24.0 Deploy Forge & Mega Domains
  deploy_forge:            { type: 'modal', target: 'gameFactory' },
  deploy_game:             { type: 'modal', target: 'deployForge' },
  mega_domains:            { type: 'modal', target: 'gameFactory' },
  domain_explorer:         { type: 'modal', target: 'megaDomains' },
  synergy_web:             { type: 'modal', target: 'megaDomains' },
  hyperscale_domains:      { type: 'modal', target: 'gameFactory' },
  hyperscale:              { type: 'modal', target: 'hyperscaleDomains' },
  hyperscale_synergy:      { type: 'modal', target: 'hyperscaleDomains' },
  jeeves_master_build:     { type: 'modal', target: 'gameFactory' },
  master_build:            { type: 'modal', target: 'jeevesMasterBuild' },
  build_full_game:         { type: 'modal', target: 'jeevesMasterBuild' },
  download_apk:            { type: 'modal', target: 'jeevesMasterBuild' },
  game_code:               { type: 'modal', target: 'jeevesMasterBuild' },

  algebra_class:           { type: 'modal', target: 'mathAcademyFull' },
  linear_algebra_class:    { type: 'modal', target: 'mathAcademyFull' },
  geometry_class:          { type: 'modal', target: 'mathAcademyFull' },
  precalculus_class:       { type: 'modal', target: 'mathAcademyFull' },
  calculus_class:          { type: 'modal', target: 'mathAcademyFull' },
  multivariable_class:     { type: 'modal', target: 'mathAcademyFull' },

  // Additional Academy
  immersive_learning:  { type: 'modal', target: 'interactiveQuizzes' },
  tutorials:           { type: 'modal', target: 'studyPaths' },
  documentation:       { type: 'modal', target: 'bible' },
  video_library:       { type: 'modal', target: 'megaAcademy' },
  podcast_hub:         { type: 'modal', target: 'megaAcademy' },
  cheat_sheets:        { type: 'modal', target: 'referenceHub' },

  // v17.0 Knowledge Databases & Interactive Quizzes
  knowledge_databases:     { type: 'modal', target: 'knowledgeDatabases' },
  cs_database:             { type: 'modal', target: 'knowledgeDatabases' },
  physics_database:        { type: 'modal', target: 'knowledgeDatabases' },
  rendering_database:      { type: 'modal', target: 'knowledgeDatabases' },
  architecture_database:   { type: 'modal', target: 'knowledgeDatabases' },
  computing_history:       { type: 'modal', target: 'knowledgeDatabases' },
  interactive_quizzes:     { type: 'modal', target: 'interactiveQuizzes' },
  quiz_challenge:          { type: 'modal', target: 'interactiveQuizzes' },
  take_quiz:               { type: 'modal', target: 'interactiveQuizzes' },
  quiz_bank:               { type: 'modal', target: 'interactiveQuizzes' },

  // v17.5 Reading Library
  reading_library:         { type: 'modal', target: 'readingLibrary' },
  books:                   { type: 'modal', target: 'readingLibrary' },
  reading_classes:         { type: 'modal', target: 'readingLibrary' },
  book_collection:         { type: 'modal', target: 'readingLibrary' },
  essential_reading:       { type: 'modal', target: 'readingLibrary' },

  // v18.0 Study Paths
  study_paths:             { type: 'modal', target: 'studyPaths' },
  learning_paths:          { type: 'modal', target: 'studyPaths' },
  career_paths:            { type: 'modal', target: 'studyPaths' },
//   curriculum:              { type: 'modal', target: 'studyPaths' },
  learning_journey:        { type: 'modal', target: 'studyPaths' },

  // v19.0 Daily Challenges, Bug/Fix, Playground, Reference
//   daily_challenge:         { type: 'modal', target: 'dailyChallenges' },
  daily_quiz:              { type: 'modal', target: 'dailyChallenges' },
  streak:                  { type: 'modal', target: 'dailyChallenges' },
  bugfix_library:          { type: 'modal', target: 'bugfixLibrary' },
  bug_fix:                 { type: 'modal', target: 'bugfixLibrary' },
  debug:                   { type: 'modal', target: 'bugfixLibrary' },
  error_lookup:            { type: 'modal', target: 'bugfixLibrary' },
  workarounds:             { type: 'modal', target: 'bugfixLibrary' },
  code_playground:         { type: 'modal', target: 'codePlayground' },
  playground:              { type: 'modal', target: 'codePlayground' },
  run_code:                { type: 'modal', target: 'codePlayground' },
  execute:                 { type: 'modal', target: 'codePlayground' },
  // v20.0 Gamification, Language Academy, Offline Sync
  gamification:            { type: 'modal', target: 'gamification' },
  xp:                      { type: 'modal', target: 'gamification' },
  skill_tree:              { type: 'modal', target: 'gamification' },
  ranks:                   { type: 'modal', target: 'gamification' },
  language_academy:        { type: 'modal', target: 'languageAcademy' },
  all_languages:           { type: 'modal', target: 'languageAcademy' },
  polyglot:                { type: 'modal', target: 'languageAcademy' },
  offline_sync:            { type: 'modal', target: 'offlineSync' },
  offline_mode:            { type: 'modal', target: 'offlineSync' },
  download_data:           { type: 'modal', target: 'offlineSync' },
  coding_dictionary:       { type: 'modal', target: 'referenceHub' },
  dictionary:              { type: 'modal', target: 'referenceHub' },
  rosetta_playground:      { type: 'modal', target: 'rosettaPlayground' },
  rosetta:                 { type: 'modal', target: 'rosettaPlayground' },
  rosetta_stone:           { type: 'modal', target: 'rosettaPlayground' },
  challenge_arena:         { type: 'modal', target: 'challengeArena' },
  challenge:               { type: 'modal', target: 'challengeArena' },
  arena:                   { type: 'modal', target: 'challengeArena' },
  reference_hub:           { type: 'modal', target: 'referenceHub' },
  cheatsheets:             { type: 'modal', target: 'referenceHub' },
//   snippets:                { type: 'modal', target: 'referenceHub' },
//   interview_prep:          { type: 'modal', target: 'referenceHub' },
  flashcards:              { type: 'modal', target: 'referenceHub' },
  glossary:                { type: 'modal', target: 'referenceHub' },

  // Career
  certifications:      { type: 'modal', target: 'certifications' },
//   career_paths:        { type: 'modal', target: 'careerPaths' },
  portfolio_builder:   { type: 'modal', target: 'portfolioBuilder' },
  mentorship:          { type: 'modal', target: 'mentorship' },

  // ═══════════════════════════════════════════════════════════════
  // PRO TOOLS
  // ═══════════════════════════════════════════════════════════════

  // Core Pro Tools
  advanced:            { type: 'modal', target: 'advanced' },
  vault:               { type: 'modal', target: 'vault' },
  sorting_vault:       { type: 'modal', target: 'sortingVault' },
  export_github:       { type: 'modal', target: 'exportGitHub' },
  collab:              { type: 'modal', target: 'liveCollab' },
  dashboard:           { type: 'modal', target: 'dashboard' },
  ai_interactions_log: { type: 'modal', target: 'aiInteractionsLog' },
  settings:            { type: 'modal', target: 'settings' },
  hub:                 { type: 'modal', target: 'hub' },

  // Git Operations
  git_init:            { type: 'git', target: 'init' },
  git_commit:          { type: 'modal', target: 'gitCommit' },
  git_push:            { type: 'git', target: 'push' },
  git_pull:            { type: 'git', target: 'pull' },
  git_branch:          { type: 'modal', target: 'gitBranch' },
  git_merge:           { type: 'modal', target: 'gitMerge' },
  git_stash:           { type: 'git', target: 'stash' },

  // Deployment
  deploy_vercel:       { type: 'modal', target: 'deployVercel' },
  deploy_netlify:      { type: 'modal', target: 'deployNetlify' },
  deploy_railway:      { type: 'modal', target: 'deployRailway' },
  deploy_docker:       { type: 'modal', target: 'deployDocker' },

  // Package Management
  npm_manager:         { type: 'modal', target: 'npmManager' },
  pip_manager:         { type: 'modal', target: 'pipManager' },
  dependency_graph:    { type: 'modal', target: 'dependencyGraph' },

  // Testing & CI
  test_runner:         { type: 'pro', target: 'runTests' },
  coverage_report:     { type: 'modal', target: 'coverageReport' },
  ci_pipeline:         { type: 'modal', target: 'ciPipeline' },

  // Productivity
  pomodoro:            { type: 'modal', target: 'pomodoro' },
  todo_list:           { type: 'modal', target: 'todoList' },
  notes:               { type: 'modal', target: 'notes' },
  keyboard_shortcuts:  { type: 'modal', target: 'keyboardShortcuts' },
};

/**
 * Resolve an action ID to its entry.
 * Returns undefined if the action is not registered.
 */
export function resolveAction(actionId: string): ActionEntry | undefined {
  return ACTION_MAP[actionId];
}

/**
 * Get total registered action count.
 */
export function getActionCount(): number {
  return Object.keys(ACTION_MAP).length;
}

/**
 * Get all action IDs by type.
 */
export function getActionsByType(type: ActionType): string[] {
  return Object.entries(ACTION_MAP)
    .filter(([_, entry]) => entry.type === type)
    .map(([id]) => id);
}
