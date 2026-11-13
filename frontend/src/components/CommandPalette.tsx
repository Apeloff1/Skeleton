/**
 * Command Palette v11.3.0
 * Unified access to all CodeDock features with clean, organized UI
 */

import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, Dimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

interface CommandPaletteProps {
  visible: boolean;
  onClose: () => void;
  onSelectAction: (action: string) => void;
  colors: any;
}

interface FeatureCategory {
  id: string;
  name: string;
  icon: string;
  color: string;
  features: Feature[];
}

interface Feature {
  id: string;
  name: string;
  icon: string;
  description: string;
  shortcut?: string;
}

const FEATURE_CATEGORIES: FeatureCategory[] = [
  {
    id: 'code',
    name: 'Code',
    icon: 'code-slash',
    color: '#3B82F6',
    features: [
      // Core Execution
      { id: 'run', name: 'Run Code', icon: 'play-circle', description: 'Execute • Instant output • Multi-language', shortcut: '⌘R' },
      { id: 'compile', name: 'Compile', icon: 'hammer', description: 'Build • Error check • Optimization', shortcut: '⌘B' },
      { id: 'debug_mode', name: 'Debug Mode', icon: 'bug', description: 'Breakpoints • Step-through • Watch vars', shortcut: '⌘D' },
      { id: 'terminal', name: 'Terminal', icon: 'terminal', description: 'Shell access • Commands • Scripts', shortcut: '⌘T' },
      // Code Quality
      { id: 'format', name: 'Format Code', icon: 'code-working', description: 'Prettier • Black • Auto-indent', shortcut: '⇧⌘F' },
      { id: 'lint', name: 'Lint Code', icon: 'checkmark-circle', description: 'ESLint • Pylint • RuboCop', shortcut: '⌘L' },
      { id: 'type_check', name: 'Type Check', icon: 'shield-checkmark', description: 'TypeScript • MyPy • Flow', shortcut: '⌘T' },
      { id: 'spell_check', name: 'Spell Check', icon: 'text', description: 'Comments • Strings • Variables' },
      // Navigation & Search
      { id: 'goto_line', name: 'Go to Line', icon: 'locate', description: 'Jump • Navigate • Quick access', shortcut: '⌘G' },
      { id: 'goto_symbol', name: 'Go to Symbol', icon: 'bookmark', description: 'Functions • Classes • Methods', shortcut: '⌘⇧O' },
      { id: 'find_replace', name: 'Find & Replace', icon: 'search', description: 'Regex • Case-sensitive • Whole word', shortcut: '⌘F' },
      { id: 'find_all', name: 'Find in Files', icon: 'folder-open', description: 'Project-wide • Multi-file • Filters', shortcut: '⇧⌘F' },
      { id: 'references', name: 'Find References', icon: 'git-network', description: 'Usages • Dependencies • Callers', shortcut: '⇧F12' },
      // Code Structure
      { id: 'fold_all', name: 'Fold All', icon: 'chevron-collapse', description: 'Collapse • Overview • Clean view', shortcut: '⌘K⌘0' },
      { id: 'unfold_all', name: 'Unfold All', icon: 'chevron-expand', description: 'Expand • Full view • Details', shortcut: '⌘K⌘J' },
      { id: 'outline', name: 'Code Outline', icon: 'list', description: 'Structure • Symbols • Navigation' },
      { id: 'minimap', name: 'Toggle Minimap', icon: 'map', description: 'Preview • Overview • Quick nav' },
      // Project Management
      { id: 'template', name: 'New Project', icon: 'add-circle', description: 'Templates • Boilerplate • Quick start' },
      { id: 'language', name: 'Language', icon: 'globe', description: 'Syntax • Highlighting • Runtime' },
      { id: 'new_file', name: 'New File', icon: 'document-attach', description: 'Create • Name • Initialize', shortcut: '⌘N' },
      { id: 'save_file', name: 'Save File', icon: 'save', description: 'Persist • Backup • Sync', shortcut: '⌘S' },
      { id: 'save_all', name: 'Save All', icon: 'albums', description: 'Batch save • All tabs • Quick', shortcut: '⌘⇧S' },
      // Editor Features
      { id: 'multi_cursor', name: 'Multi-Cursor', icon: 'ellipsis-vertical', description: 'Multiple edits • Parallel • Efficient', shortcut: '⌥⌘↓' },
      { id: 'column_select', name: 'Column Select', icon: 'reorder-four', description: 'Rectangle • Block • Vertical', shortcut: '⇧⌥' },
      { id: 'duplicate_line', name: 'Duplicate Line', icon: 'copy', description: 'Clone • Up/down • Quick copy', shortcut: '⇧⌥↓' },
      { id: 'move_line', name: 'Move Line', icon: 'swap-vertical', description: 'Reorder • Drag • Reorganize', shortcut: '⌥↑' },
      { id: 'comment_toggle', name: 'Toggle Comment', icon: 'chatbox-ellipses', description: 'Comment • Uncomment • Block', shortcut: '⌘/' },
      { id: 'bracket_match', name: 'Match Bracket', icon: 'code', description: 'Pairs • Jump • Highlight', shortcut: '⌘⇧\\' },
      // Snippets & Templates
      { id: 'snippets', name: 'Snippets Library', icon: 'layers', description: '500+ snippets • Custom • Shortcuts' },
      { id: 'emmet', name: 'Emmet Expand', icon: 'flash', description: 'HTML • CSS • Abbreviations', shortcut: 'Tab' },
      { id: 'live_templates', name: 'Live Templates', icon: 'create', description: 'Dynamic • Variables • Tabstops' },
      // Diff & History
      { id: 'diff_view', name: 'Diff View', icon: 'git-compare', description: 'Compare • Changes • Side-by-side' },
      { id: 'local_history', name: 'Local History', icon: 'time', description: 'Timeline • Restore • Versions' },
      { id: 'undo_history', name: 'Undo History', icon: 'arrow-undo-circle', description: 'Branches • Tree • Recovery' },
      // Advanced
      { id: 'refactor_rename', name: 'Rename Symbol', icon: 'pencil', description: 'Global • Safe • References', shortcut: 'F2' },
      { id: 'extract_method', name: 'Extract Method', icon: 'git-pull-request', description: 'Function • Reuse • Clean' },
      { id: 'inline_variable', name: 'Inline Variable', icon: 'enter', description: 'Simplify • Merge • Optimize' },
      { id: 'zen_mode', name: 'Zen Mode', icon: 'eye-off', description: 'Focus • Distraction-free • Full screen', shortcut: '⌘K Z' },
      { id: 'split_editor', name: 'Split Editor', icon: 'tablet-landscape', description: 'Side-by-side • Compare • Multi-file' },
    ]
  },
  {
    id: 'ai',
    name: 'Game Pipelines',
    icon: 'sparkles',
    color: '#8B5CF6',
    features: [
      // Game Creation Pipelines (AI assistant + build tools moved to the Jeeves Hub)
      { id: 'npc_pipeline', name: 'NPC Generator', icon: 'person-circle', description: 'Characters • Dialogue • Personalities' },
      { id: 'world_pipeline', name: 'World Builder', icon: 'earth', description: 'Terrain • Regions • Environments' },
      { id: 'combat_pipeline', name: 'Combat Designer', icon: 'flash-outline', description: 'Systems • Balance • Mechanics' },
      { id: 'narrative_pipeline', name: 'Story Writer', icon: 'book', description: 'Quests • Branching • Lore' },
      { id: 'animation_pipeline', name: 'Animation Studio', icon: 'film', description: 'Keyframes • Rigs • Blending' },
      { id: 'vfx_pipeline', name: 'VFX Creator', icon: 'color-wand', description: 'Particles • Shaders • Effects' },
      { id: 'economy_pipeline', name: 'Economy Designer', icon: 'cash', description: 'Currency • Balance • Monetization' },
      { id: 'bot_pipeline', name: 'Bot Personas', icon: 'hardware-chip', description: 'AI companions • Behavior • Memory' },
      { id: 'testing_pipeline', name: 'QA Generator', icon: 'flask', description: 'Test cases • Automation • Coverage' },
      { id: 'director_pipeline', name: 'AI Director', icon: 'videocam', description: 'Pacing • Tension • Cinematics' },
      { id: 'neural_pipeline', name: 'Neural Rendering', icon: 'scan', description: 'NeRF • DLSS • Ray tracing' },
      { id: 'hardware_pipeline', name: 'Optimizer', icon: 'speedometer', description: 'Performance • FPS • Memory' },
      { id: 'systems_pipeline', name: 'Game Systems', icon: 'cog', description: 'Save/Load • Achievements • Progression' },
      { id: 'procedural_pipeline', name: 'Procedural Gen', icon: 'infinite', description: 'Infinite • Dungeons • Randomization' },
      { id: 'physics_pipeline', name: 'Physics Engine', icon: 'magnet', description: 'Ragdoll • Destruction • Fluids' },
      { id: 'shader_pipeline', name: 'Shader Lab', icon: 'color-palette', description: 'GLSL • Materials • Post-process' },
      { id: 'ui_ux_pipeline', name: 'UI/UX Designer', icon: 'tablet-portrait', description: 'Menus • HUD • Accessibility' },
      { id: 'localization_pipeline', name: 'Localization', icon: 'language', description: '50+ langs • Cultural • TTS' },
      { id: 'analytics_pipeline', name: 'Game Analytics', icon: 'analytics', description: 'Heatmaps • Funnels • Retention' },
      { id: 'matchmaking_pipeline', name: 'Matchmaking', icon: 'people-circle', description: 'Skill-based • Ranked • Queues' },
      { id: 'anticheat_pipeline', name: 'Anti-Cheat', icon: 'shield-checkmark', description: 'Detection • Prevention • Bans' },
      { id: 'modding_pipeline', name: 'Mod Support', icon: 'extension-puzzle', description: 'Workshop • SDK • Community' },
      { id: 'replay_pipeline', name: 'Replay System', icon: 'refresh-circle', description: 'Recordings • Highlights • Share' },
      { id: 'leaderboard_pipeline', name: 'Leaderboards', icon: 'podium', description: 'Rankings • Seasons • Rewards' },
      { id: 'social_pipeline', name: 'Social Features', icon: 'share-social', description: 'Friends • Clans • Chat' },
      { id: 'mobile_pipeline', name: 'Mobile Adapt', icon: 'phone-portrait', description: 'Touch • Gyro • Optimization' },
      { id: 'vr_ar_pipeline', name: 'VR/AR Builder', icon: 'glasses', description: 'Immersive • Tracking • Haptics' },
      { id: 'crossplay_pipeline', name: 'Cross-Play', icon: 'link', description: 'Platform sync • Progression • Cloud' },
      // Additional Pipelines
      { id: 'inventory_pipeline', name: 'Inventory System', icon: 'grid', description: 'Items • Crafting • Trading' },
    ]
  },
  {
    id: 'academy',
    name: 'Academy',
    icon: 'school',
    color: '#EC4899',
    features: [
      // Core Learning Systems
      { id: 'immersive_tutor', name: 'Immersive Tutor', icon: 'school', description: 'Jeeves Synergy • Gamification • ZPD' },
      { id: 'learning_hub', name: 'Learning Hub', icon: 'rocket', description: '6-layer learning • 1320hrs • Mastery' },
      { id: 'jeeves', name: 'Jeeves AI Tutor', icon: 'chatbubbles', description: '1255hr tutoring • Adaptive • Personal' },
      { id: 'jeeves_eq', name: 'Jeeves EQ', icon: 'heart', description: 'Emotional IQ • Wellbeing • Balance' },
      { id: 'adaptive_learning', name: 'Adaptive Learning', icon: 'trending-up', description: 'AI curriculum • Personalized • Dynamic' },
      // Knowledge Bibles
      { id: 'ai_bible', name: 'AI Game Bible', icon: 'book', description: 'Game dev • Complete • 500hrs' },
      { id: 'curriculum', name: 'CS Curriculum', icon: 'library', description: 'Foundations • Theory • Practice' },
      { id: 'bible', name: 'Code Bible', icon: 'document-text', description: 'Programming • Patterns • Best practices' },
      { id: 'system_design_bible', name: 'System Design Bible', icon: 'git-branch', description: 'Architecture • Scale • 180hrs' },
      { id: 'ml_bible', name: 'ML/AI Bible', icon: 'hardware-chip', description: 'Neural nets • Deep learning • 400hrs' },
      { id: 'security_bible', name: 'Security Bible', icon: 'shield', description: 'Cybersec • Pentesting • 220hrs' },
      { id: 'devops_bible', name: 'DevOps Bible', icon: 'cloud', description: 'CI/CD • K8s • Docker • 280hrs' },
      { id: 'frontend_bible', name: 'Frontend Bible', icon: 'tablet-portrait', description: 'React • Vue • Angular • 350hrs' },
      { id: 'backend_bible', name: 'Backend Bible', icon: 'server', description: 'Node • Python • Go • 420hrs' },
      { id: 'database_bible', name: 'Database Bible', icon: 'file-tray-stacked', description: 'SQL • NoSQL • Graph • 200hrs' },
      // Learning Resources
      { id: 'reading_corner', name: 'Reading Corner', icon: 'library', description: '1600+ hrs • Articles • Books' },
      { id: 'masterclass', name: 'Masterclass', icon: 'trophy', description: '2860+ hrs • Expert • Premium' },
      { id: 'education', name: 'Challenges', icon: 'game-controller', description: 'Interactive • Practice • XP' },
      { id: 'code_golf', name: 'Code Golf', icon: 'flag', description: 'Shortest code • Competition • Fun' },
      { id: 'daily_challenge', name: 'Daily Challenge', icon: 'calendar', description: 'New daily • Streaks • Rewards' },
      { id: 'interview_prep', name: 'Interview Prep', icon: 'briefcase', description: 'FAANG • 500+ problems • Mock' },
      // Subject Academies
      { id: 'physics_academy', name: 'Physics Academy', icon: 'planet', description: '315hrs • Mechanics • Collisions' },
      { id: 'math_academy', name: 'Math Academy', icon: 'calculator', description: '340hrs • Linear algebra • Calculus' },
      { id: 'cs_academy', name: 'CS Academy', icon: 'code-slash', description: '600hrs • DSA • Algorithms' },
      { id: 'graphics_academy', name: 'Graphics Academy', icon: 'color-palette', description: '280hrs • OpenGL • Shaders' },
      { id: 'networking_academy', name: 'Networking Academy', icon: 'wifi', description: '200hrs • TCP/IP • Sockets' },
      { id: 'game_academy', name: 'Game Dev Academy', icon: 'game-controller', description: '500hrs • Unity • Unreal' },
      { id: 'mobile_academy', name: 'Mobile Academy', icon: 'phone-portrait', description: '320hrs • iOS • Android' },
      { id: 'web_academy', name: 'Web Dev Academy', icon: 'globe', description: '450hrs • Full-stack • Modern' },
      { id: 'cloud_academy', name: 'Cloud Academy', icon: 'cloud', description: '380hrs • AWS • GCP • Azure' },
      { id: 'blockchain_academy', name: 'Blockchain Academy', icon: 'link', description: '180hrs • Web3 • Smart contracts' },
      // Camera Coding Academy
      { id: 'camera_academy', name: 'Camera Coding', icon: 'camera', description: '500hrs • OpenCV • WebRTC • AI Vision' },
      { id: 'opencv_track', name: 'OpenCV Mastery', icon: 'eye', description: '120hrs • Computer vision • Detection' },
      { id: 'mediapipe_track', name: 'MediaPipe AI', icon: 'body', description: '60hrs • Face • Hand • Pose tracking' },
      { id: 'ffmpeg_track', name: 'FFmpeg Mastery', icon: 'film', description: '50hrs • Video processing • Streaming' },
      { id: 'webrtc_track', name: 'WebRTC Real-Time', icon: 'videocam', description: '70hrs • Video calls • P2P' },
      { id: 'dl_vision_track', name: 'Deep Learning Vision', icon: 'hardware-chip', description: '80hrs • YOLO • CNNs • Tracking' },
      // Language Tracks
      { id: 'python_track', name: 'Python Track', icon: 'logo-python', description: '200hrs • Beginner to expert' },
      { id: 'javascript_track', name: 'JavaScript Track', icon: 'logo-javascript', description: '250hrs • ES6+ • Node • React' },
      { id: 'typescript_track', name: 'TypeScript Track', icon: 'code-slash', description: '180hrs • Types • Generics • Advanced' },
      { id: 'rust_track', name: 'Rust Track', icon: 'construct', description: '180hrs • Systems • Memory safe' },
      { id: 'go_track', name: 'Go Track', icon: 'rocket', description: '150hrs • Concurrency • Cloud native' },
      { id: 'cpp_track', name: 'C++ Track', icon: 'code', description: '300hrs • Engines • Performance' },
      { id: 'c_track', name: 'C Track', icon: 'terminal', description: '200hrs • Systems • Embedded' },
      { id: 'java_track', name: 'Java Track', icon: 'cafe', description: '280hrs • Enterprise • JVM' },
      { id: 'kotlin_track', name: 'Kotlin Track', icon: 'phone-portrait', description: '150hrs • Android • Coroutines' },
      { id: 'swift_track', name: 'Swift Track', icon: 'logo-apple', description: '170hrs • iOS • SwiftUI' },
      { id: 'csharp_track', name: 'C# Track', icon: 'game-controller', description: '250hrs • Unity • .NET' },
      { id: 'ruby_track', name: 'Ruby Track', icon: 'diamond', description: '130hrs • Rails • Metaprogramming' },
      { id: 'php_track', name: 'PHP Track', icon: 'globe', description: '120hrs • Laravel • Modern PHP' },
      { id: 'dart_track', name: 'Dart Track', icon: 'apps', description: '140hrs • Flutter • Cross-platform' },
      { id: 'scala_track', name: 'Scala Track', icon: 'layers', description: '160hrs • FP + OOP • Spark' },
      { id: 'haskell_track', name: 'Haskell Track', icon: 'infinite', description: '200hrs • Pure FP • Monads' },
      { id: 'elixir_track', name: 'Elixir Track', icon: 'flask', description: '130hrs • Phoenix • OTP' },
      { id: 'sql_track', name: 'SQL Track', icon: 'file-tray-stacked', description: '100hrs • Queries • Optimization' },
      { id: 'solidity_track', name: 'Solidity Track', icon: 'link', description: '120hrs • Web3 • Smart contracts' },
      { id: 'lua_track', name: 'Lua Track', icon: 'game-controller', description: '80hrs • Scripting • Games' },
      { id: 'r_track', name: 'R Track', icon: 'analytics', description: '140hrs • Statistics • Data viz' },
      { id: 'bash_track', name: 'Bash Track', icon: 'terminal', description: '70hrs • Shell • Automation' },
      { id: 'assembly_track', name: 'Assembly Track', icon: 'hardware-chip', description: '160hrs • x86 • ARM' },
      // Repeat Class & Achievements
      { id: 'repeat_class', name: 'Repeat Class', icon: 'refresh-circle', description: 'Redo any class • Track scores • Master it' },
      { id: 'achievements', name: 'Achievements', icon: 'trophy', description: '10,000 achievements • 5 rarity tiers • 61 categories' },
      { id: 'code_playground', name: 'Code Playground', icon: 'code-slash', description: '7 languages • Python • Go • Rust • C/C++ • Live exec' },
      { id: 'knowledge_databases', name: 'Knowledge Databases', icon: 'library', description: '16 domains • CS • Physics • Rendering • 176 entries' },
      { id: 'interactive_quizzes', name: 'Interactive Quizzes', icon: 'help-circle', description: '15,000+ quizzes • 15 domains • Adaptive difficulty' },
      { id: 'reading_library', name: 'Reading Library', icon: 'book', description: '507 books • 19 categories • AI voice reader' },
      { id: 'study_paths', name: 'Study Paths', icon: 'map', description: '20+ curated learning journeys' },
      { id: 'daily_challenges', name: 'Daily Challenges', icon: 'flash', description: 'Daily 10Q challenge • Streak system • 7 tiers' },
      { id: 'bugfix_library', name: 'Bug/Fix Encyclopedia', icon: 'bug', description: '1,931 bug/fixes • 73 workarounds • Searchable' },
      { id: 'reference_hub', name: 'Reference Hub', icon: 'documents', description: 'Cheat sheets • Snippets • Flashcards • Interview prep' },
      { id: 'gamification', name: 'Gamification', icon: 'game-controller', description: 'XP • Levels • Skill Trees • 9 ranks • RPG progression' },
      { id: 'language_academy', name: 'Language Academy', icon: 'globe', description: '451+ languages • Mainstream • Niche • Esoteric • Classes' },
      { id: 'offline_sync', name: 'Offline Mode', icon: 'cloud-download', description: 'Download 28K+ docs • Study anywhere • No internet needed' },
      { id: 'coding_dictionary', name: 'Coding Dictionary', icon: 'book', description: '353+ entries • Syntax refs • Patterns • Algorithms • AI Prompts • Courses' },
      { id: 'rosetta_playground', name: 'Rosetta Playground', icon: 'code', description: '6,795 entries • 453 languages • 15 concepts • Execute inline' },
      { id: 'challenge_arena', name: 'Challenge Arena', icon: 'trophy', description: 'Translate code between languages • Auto-graded • XP rewards' },
      { id: 'my_progress', name: 'My Progress', icon: 'stats-chart', description: 'Overview • Scores • Streaks • Level' },
      { id: 'leaderboard', name: 'Leaderboard', icon: 'podium', description: 'Rankings • Top learners • Compete' },
      { id: 'language_recommend', name: 'Language Quiz', icon: 'help-circle', description: 'Jeeves picks your next language' },
      // Creator's Studio & Group Chat
      { id: 'group_chat', name: "Creator's Studio", icon: 'chatbubbles', description: 'Agent group chat \u2022 All pipelines connected' },
      { id: 'pipeline_agents', name: 'Pipeline Agents', icon: 'people', description: '14 specialized agents \u2022 AAA studio team' },
      { id: 'quality_control', name: 'Quality Control', icon: 'shield', description: 'Sentinel \u2022 AAA standards enforcement' },
      // Galaxy Studio Factory — Unified Game Creation Engine (merged: Game Factory + Builder + Domains + Master Build + Deploy)
      { id: 'game_factory', name: 'Galaxy Studio Factory', icon: 'planet', description: '28,894 agents \u2022 52 genres \u2022 199 sub-genres \u2022 196 files \u2022 Zero size limits \u2022 Deploy APK' },
      // v18.0 System Fortress (merged: Thermal + Performance + Resilience + Sentinel + Knowledge)
      { id: 'thermal_monitor', name: 'System Fortress', icon: 'shield-checkmark', description: 'Thermal \u2022 Performance Armor \u2022 Resilience \u2022 Sentinel \u2022 Knowledge — unified monitoring' },
      // Jeeves Level & Vault (v17.2)
      { id: 'jeeves_level', name: 'Jeeves Level System', icon: 'trending-up', description: 'XP tracker \u2022 1,000,000 level cap \u2022 Matrix stats' },
      { id: 'code_vault', name: 'Code Vault', icon: 'lock-closed', description: 'Browse all agent interactions \u2022 Codeblocks \u2022 Learning data' },
      // STEM Academy
      { id: 'math_academy_full', name: 'STEM Academy', icon: 'calculator', description: 'Math \u2022 Physics \u2022 CS \u2022 2000+ hours' },
      { id: 'algebra_class', name: 'Algebra', icon: 'calculator', description: '120hrs \u2022 Equations \u2022 Functions' },
      { id: 'linear_algebra_class', name: 'Linear Algebra', icon: 'grid', description: '160hrs \u2022 Matrices \u2022 Transforms \u2022 Graphics' },
      { id: 'geometry_class', name: 'Geometry', icon: 'shapes', description: '100hrs \u2022 Shapes \u2022 Proofs \u2022 3D' },
      { id: 'precalculus_class', name: 'Pre-Calculus', icon: 'trending-up', description: '100hrs \u2022 Trig \u2022 Polar \u2022 Limits' },
      { id: 'calculus_class', name: 'Calculus', icon: 'pulse', description: '180hrs \u2022 Derivatives \u2022 Integrals' },
      { id: 'multivariable_class', name: 'Multivariable Calculus', icon: 'cube', description: '200hrs \u2022 3D \u2022 Vector fields' },
      // Additional Learning
      { id: 'immersive_learning', name: 'Immersive Learning', icon: 'glasses', description: 'Deep-dive • Focus • Retention' },
      { id: 'tutorials', name: 'Tutorials', icon: 'list', description: 'Step-by-step • Visual • Guided' },
      { id: 'documentation', name: 'Documentation', icon: 'document', description: 'API refs • Manuals • Examples' },
      { id: 'video_library', name: 'Video Library', icon: 'videocam', description: '3000+ videos • HD • Captions' },
      { id: 'podcast_hub', name: 'Podcast Hub', icon: 'mic', description: 'Tech talks • Interviews • News' },
      { id: 'cheat_sheets', name: 'Cheat Sheets', icon: 'newspaper', description: '100+ refs • PDF • Printable' },
      // Career & Certification
      { id: 'certifications', name: 'Certifications', icon: 'ribbon', description: 'Industry • Verified • Portfolio' },
      { id: 'career_paths', name: 'Career Paths', icon: 'trending-up', description: 'Role-based • Roadmaps • Goals' },
      { id: 'portfolio_builder', name: 'Portfolio Builder', icon: 'briefcase', description: 'Showcase • Projects • Resume' },
      { id: 'mentorship', name: 'Mentorship', icon: 'people', description: '1-on-1 • Expert • Guidance' },
    ]
  },
  {
    id: 'tools',
    name: 'Pro Tools',
    icon: 'construct',
    color: '#10B981',
    features: [
      // Core Tools
      { id: 'advanced', name: 'Advanced Tools', icon: 'analytics', description: 'Benchmark • Verify • Starlog' },
      { id: 'vault', name: 'Vault', icon: 'file-tray-full', description: 'Save code • Assets • Secure' },
      { id: 'sorting_vault', name: 'Sorting Vault', icon: 'layers', description: 'Central hub • Connect all • Organize' },
      { id: 'export_github', name: 'Export & GitHub', icon: 'git-branch', description: 'PDF • Push • Pull' },
      { id: 'collab', name: 'Live Collab', icon: 'people-circle', description: 'Pair program • Real-time • Share' },
      { id: 'dashboard', name: 'Dashboard', icon: 'stats-chart', description: 'Analytics • Progress • Goals' },
      { id: 'ai_interactions_log', name: 'AI Log', icon: 'document-text', description: 'History • Export • Search' },
      { id: 'settings', name: 'Settings', icon: 'settings', description: 'Config • Theme • Preferences' },
      { id: 'hub', name: 'CodeHub', icon: 'cloud', description: 'Library • Templates • Community' },
      // Version Control
      { id: 'git_init', name: 'Git Init', icon: 'git-branch', description: 'Initialize • Repository • Setup' },
      { id: 'git_commit', name: 'Git Commit', icon: 'git-commit', description: 'Save • Message • History' },
      { id: 'git_push', name: 'Git Push', icon: 'cloud-upload', description: 'Upload • Remote • Sync' },
      { id: 'git_pull', name: 'Git Pull', icon: 'cloud-download', description: 'Download • Update • Merge' },
      { id: 'git_branch', name: 'Git Branch', icon: 'git-network', description: 'Create • Switch • Delete' },
      { id: 'git_merge', name: 'Git Merge', icon: 'git-merge', description: 'Combine • Resolve • Complete' },
      { id: 'git_stash', name: 'Git Stash', icon: 'archive', description: 'Save • Restore • Clean' },
      // Deployment
      { id: 'deploy_vercel', name: 'Deploy Vercel', icon: 'triangle', description: 'One-click • Preview • Production' },
      { id: 'deploy_netlify', name: 'Deploy Netlify', icon: 'cloud-circle', description: 'JAMstack • Edge • CDN' },
      { id: 'deploy_railway', name: 'Deploy Railway', icon: 'train', description: 'Backend • Database • Scale' },
      { id: 'deploy_docker', name: 'Docker Build', icon: 'cube', description: 'Container • Image • Deploy' },
      // Package Management
      { id: 'npm_manager', name: 'NPM Manager', icon: 'logo-npm', description: 'Install • Update • Audit' },
      { id: 'pip_manager', name: 'PIP Manager', icon: 'logo-python', description: 'Packages • Venv • Requirements' },
      { id: 'dependency_graph', name: 'Dependency Graph', icon: 'git-network', description: 'Visualize • Analyze • Optimize' },
      // Testing & CI
      { id: 'test_runner', name: 'Test Runner', icon: 'flask', description: 'Run • Watch • Coverage' },
      { id: 'coverage_report', name: 'Coverage Report', icon: 'pie-chart', description: 'Lines • Branches • Functions' },
      { id: 'ci_pipeline', name: 'CI Pipeline', icon: 'git-compare', description: 'Actions • Workflows • Deploy' },
      // Productivity
      { id: 'pomodoro', name: 'Pomodoro Timer', icon: 'timer', description: 'Focus • Breaks • Stats' },
      { id: 'todo_list', name: 'Task List', icon: 'checkbox', description: 'Tasks • Priority • Done' },
      { id: 'notes', name: 'Quick Notes', icon: 'create', description: 'Scratch • Markdown • Save' },
      { id: 'keyboard_shortcuts', name: 'Shortcuts', icon: 'keypad', description: 'All keys • Custom • Help' },
    ]
  },
];

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  visible, onClose, onSelectAction, colors
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [filteredFeatures, setFilteredFeatures] = useState<Feature[]>([]);

  useEffect(() => {
    if (searchQuery.trim()) {
      const allFeatures = FEATURE_CATEGORIES.flatMap(cat => 
        cat.features.map(f => ({ ...f, categoryColor: cat.color }))
      );
      const filtered = allFeatures.filter(f => 
        f.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        f.description.toLowerCase().includes(searchQuery.toLowerCase())
      );
      setFilteredFeatures(filtered);
      setSelectedCategory(null);
    } else {
      setFilteredFeatures([]);
    }
  }, [searchQuery]);

  const handleFeatureSelect = (featureId: string) => {
    onSelectAction(featureId);
    setSearchQuery('');
    setSelectedCategory(null);
  };

  const renderCategories = () => (
    <View style={styles.categoriesGrid}>
      {FEATURE_CATEGORIES.map(category => (
        <TouchableOpacity
          key={category.id}
          style={[styles.categoryCard, { backgroundColor: category.color + '15' }]}
          onPress={() => setSelectedCategory(category.id)}
        >
          <View style={[styles.categoryIcon, { backgroundColor: category.color + '25' }]}>
            <Ionicons name={category.icon as any} size={28} color={category.color} />
          </View>
          <Text style={[styles.categoryName, { color: colors.text }]}>{category.name}</Text>
          <Text style={[styles.categoryCount, { color: colors.textMuted }]}>
            {category.features.length} features
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );

  const renderCategoryFeatures = () => {
    const category = FEATURE_CATEGORIES.find(c => c.id === selectedCategory);
    if (!category) return null;

    return (
      <View style={styles.featuresList}>
        <TouchableOpacity 
          style={styles.backButton}
          onPress={() => setSelectedCategory(null)}
        >
          <Ionicons name="arrow-back" size={32} color={colors.text} />
          <Text style={[styles.backText, { color: colors.text }]}>Back</Text>
        </TouchableOpacity>
        
        <View style={[styles.categoryHeader, { backgroundColor: category.color + '15' }]}>
          <Ionicons name={category.icon as any} size={32} color={category.color} />
          <Text style={[styles.categoryTitle, { color: colors.text }]}>{category.name}</Text>
        </View>

        {category.features.map(feature => (
          <TouchableOpacity
            key={feature.id}
            style={[styles.featureRow, { backgroundColor: colors.surfaceAlt }]}
            onPress={() => handleFeatureSelect(feature.id)}
          >
            <View style={[styles.featureIcon, { backgroundColor: category.color + '20' }]}>
              <Ionicons name={feature.icon as any} size={32} color={category.color} />
            </View>
            <View style={styles.featureInfo}>
              <Text style={[styles.featureName, { color: colors.text }]}>{feature.name}</Text>
              <Text style={[styles.featureDesc, { color: colors.textMuted }]}>{feature.description}</Text>
            </View>
            {feature.shortcut && (
              <View style={[styles.shortcutBadge, { backgroundColor: colors.surface }]}>
                <Text style={[styles.shortcutText, { color: colors.textMuted }]}>{feature.shortcut}</Text>
              </View>
            )}
          </TouchableOpacity>
        ))}
      </View>
    );
  };

  const renderSearchResults = () => (
    <View style={styles.searchResults}>
      <Text style={[styles.searchResultsTitle, { color: colors.textMuted }]}>
        {filteredFeatures.length} result{filteredFeatures.length !== 1 ? 's' : ''}
      </Text>
      {filteredFeatures.map((feature: any) => (
        <TouchableOpacity
          key={feature.id}
          style={[styles.featureRow, { backgroundColor: colors.surfaceAlt }]}
          onPress={() => handleFeatureSelect(feature.id)}
        >
          <View style={[styles.featureIcon, { backgroundColor: (feature.categoryColor || colors.primary) + '20' }]}>
            <Ionicons name={feature.icon as any} size={32} color={feature.categoryColor || colors.primary} />
          </View>
          <View style={styles.featureInfo}>
            <Text style={[styles.featureName, { color: colors.text }]}>{feature.name}</Text>
            <Text style={[styles.featureDesc, { color: colors.textMuted }]}>{feature.description}</Text>
          </View>
        </TouchableOpacity>
      ))}
    </View>
  );

  return (
    <Modal
      visible={visible}
      animationType="fade"
      transparent
      onRequestClose={onClose}
    >
      <TouchableOpacity 
        style={styles.overlay} 
        activeOpacity={1} 
        onPress={onClose}
      >
        <TouchableOpacity 
          activeOpacity={1} 
          style={[styles.palette, { backgroundColor: colors.surface }]}
        >
          {/* Search Bar */}
          <View style={[styles.searchContainer, { borderBottomColor: colors.border }]}>
            <Ionicons name="search" size={32} color={colors.textMuted} />
            <TextInput
              style={[styles.searchInput, { color: colors.text }]}
              placeholder="Search features..."
              placeholderTextColor={colors.textMuted}
              value={searchQuery}
              onChangeText={setSearchQuery}
              autoFocus
            />
            {searchQuery ? (
              <TouchableOpacity onPress={() => setSearchQuery('')}>
                <Ionicons name="close-circle" size={32} color={colors.textMuted} />
              </TouchableOpacity>
            ) : null}
          </View>

          {/* Content */}
          <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
            {searchQuery.trim() ? (
              renderSearchResults()
            ) : selectedCategory ? (
              renderCategoryFeatures()
            ) : (
              renderCategories()
            )}
          </ScrollView>

          {/* Footer */}
          <View style={[styles.footer, { borderTopColor: colors.border }]}>
            <Text style={[styles.footerText, { color: colors.textMuted }]}>
              Press ESC to close • Type to search
            </Text>
          </View>
        </TouchableOpacity>
      </TouchableOpacity>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 8,
  },
palette: {
    width: '100%',
    maxWidth: Math.min(650, SCREEN_WIDTH - 32),
    height: '85%',
    maxHeight: '85%',
    borderRadius: 20,
    overflow: 'hidden',
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    gap: 12,
  },
  searchInput: {
    flex: 1,
    fontSize: 20,
    padding: 0,
  },
  content: {
    flex: 1,
    padding: 16,
  },
  categoriesGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
categoryCard: {
    width: '48%',
    padding: 20,
    borderRadius: 16,
    alignItems: 'center',
    marginBottom: 16,
  },
  categoryIcon: {
    width: 56,
    height: 56,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
  },
  categoryName: {
    fontSize: 16,
    fontWeight: '700',
  },
  categoryCount: {
    fontSize: 14,
    marginTop: 4,
  },
  featuresList: {
    gap: 8,
  },
  backButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 8,
    marginBottom: 8,
  },
  backText: {
    fontSize: 15,
    fontWeight: '600',
  },
  categoryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
  },
  categoryTitle: {
    fontSize: 24,
    fontWeight: '800',
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 12,
    gap: 12,
    marginBottom: 6,
    minHeight: 64,
  },
  featureIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  featureInfo: {
    flex: 1,
  },
  featureName: {
    fontSize: 17,
    fontWeight: '700',
  },
  featureDesc: {
    fontSize: 14,
    marginTop: 2,
    lineHeight: 20,
  },
  shortcutBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  shortcutText: {
    fontSize: 14,
    fontFamily: 'monospace',
  },
  searchResults: {
    gap: 8,
  },
  searchResultsTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
    textTransform: 'uppercase',
  },
  footer: {
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderTopWidth: 1,
    alignItems: 'center',
  },
  footerText: {
    fontSize: 14,
  },
});
