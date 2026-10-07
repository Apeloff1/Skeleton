"""
EXTRAORDINARY KNOWLEDGE ENGINE — Deep Domain Knowledge for Every Agent
Applies extraordinary-level knowledge bases to ALL agents in the system (~25,994).

Each agent receives:
  - A deep knowledge base tailored to their specialty (50+ knowledge domains)
  - Cross-disciplinary synthesis frameworks
  - Historical mastery references (legendary practitioners in each field)
  - Cutting-edge research awareness (2024-2026 breakthroughs)
  - Meta-cognitive frameworks for knowledge application
  - Knowledge depth levels (Surface → Practitioner → Scholar → Sage → Oracle)

Philosophy: "Knowledge is not merely information — it is the capacity to transform
information into wisdom through context, experience, and synthesis. An extraordinary
agent doesn't just know things; it understands WHY things are the way they are,
HOW they connect to everything else, and WHAT comes next."
"""

from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


# =============================================================================
# KNOWLEDGE DEPTH LEVELS
# =============================================================================

KNOWLEDGE_DEPTHS = [
    {"level": 0, "name": "Surface", "description": "Awareness of key concepts and terminology"},
    {"level": 1, "name": "Practitioner", "description": "Can apply knowledge to solve standard problems"},
    {"level": 2, "name": "Scholar", "description": "Deep understanding of theory, history, and edge cases"},
    {"level": 3, "name": "Sage", "description": "Can teach, innovate, and push boundaries of the field"},
    {"level": 4, "name": "Oracle", "description": "Transcendent mastery — synthesizes across all domains, predicts future directions"},
]


# =============================================================================
# 50 EXTRAORDINARY KNOWLEDGE DOMAINS
# =============================================================================

KNOWLEDGE_DOMAINS = [
    # ---- GAME DESIGN (10 domains) ----
    {
        "id": "game_mechanics_theory",
        "name": "Game Mechanics Theory",
        "category": "game_design",
        "depth": "Oracle",
        "core_knowledge": [
            "MDA Framework (Mechanics-Dynamics-Aesthetics) — Hunicke, LeBlanc, Zubek",
            "Bartle's Player Types — Achievers, Explorers, Socializers, Killers + expanded 8-type model",
            "Flow Theory — Csikszentmihalyi: optimal challenge-skill balance",
            "Self-Determination Theory — Ryan & Deci: autonomy, competence, relatedness",
            "Operant Conditioning — Skinner: variable ratio schedules in reward systems",
            "Prospect Theory — Kahneman & Tversky: loss aversion in game economies",
            "Nash Equilibrium — game-theoretic balance in multiplayer systems",
            "Emergent Gameplay — complex behaviors from simple rule interactions",
            "Procedural Rhetoric — Bogost: games as persuasive expression",
            "Meaningful Choices — Sid Meier's 'interesting decisions' doctrine",
        ],
        "legendary_practitioners": ["Shigeru Miyamoto", "Sid Meier", "Will Wright", "Hideo Kojima", "Todd Howard"],
        "cutting_edge": ["AI-driven adaptive difficulty (2025)", "Neuromorphic game balancing", "Quantum game theory applications"],
    },
    {
        "id": "level_design_mastery",
        "name": "Level Design Mastery",
        "category": "game_design",
        "depth": "Oracle",
        "core_knowledge": [
            "Nintendo's 'Kishōtenketsu' — 4-act level structure (intro → develop → twist → conclude)",
            "Valve's 'Environmental Storytelling' — Half-Life 2 design principles",
            "Dark Souls spatial design — interconnected worlds with purpose",
            "Metric-based design — jump distances, sight lines, cover spacing",
            "Pacing curves — tension/release rhythm in level progression",
            "Sight-line composition — guiding player attention through architecture",
            "Negative space and breathing room — the art of nothing",
            "Verticality design — exploiting Y-axis for gameplay variety",
            "Gating mechanics — knowledge gates vs. key gates vs. ability gates",
            "Playtesting methodology — A/B testing, heat maps, eye tracking",
        ],
        "legendary_practitioners": ["Hidemaro Fujibayashi", "Clint Hocking", "Kim Swift", "Steve Gaynor"],
        "cutting_edge": ["ML-generated level layouts (2025)", "PCG with quality guarantees", "VR spatial design paradigms"],
    },
    {
        "id": "narrative_design",
        "name": "Narrative Design & Interactive Storytelling",
        "category": "game_design",
        "depth": "Oracle",
        "core_knowledge": [
            "Campbell's Monomyth — Hero's Journey with game-specific adaptations",
            "Branching Narrative Architecture — state machines, ink scripting, dialogue trees",
            "Environmental Narrative — Gone Home, BioShock methodology",
            "Ludonarrative Harmony — aligning gameplay with story (vs. dissonance)",
            "Character Arc Integration — character growth through mechanics, not cutscenes",
            "Procedural Narrative — Dwarf Fortress emergent storytelling",
            "Dramatic Irony in Games — player knowledge vs. character knowledge",
            "Multiple Perspectives — Rashomon-style interactive narratives",
            "Save/Load as Narrative Mechanic — Undertale, Nier: Automata",
            "Player Agency Spectrum — illusion of choice vs. true consequence",
        ],
        "legendary_practitioners": ["Amy Hennig", "Neil Druckmann", "Yoko Taro", "Sam Barlow", "Toby Fox"],
        "cutting_edge": ["LLM-driven dynamic narrative (2025)", "Emotional AI NPCs", "Infinite story generation"],
    },
    {
        "id": "game_economy_design",
        "name": "Game Economy & Monetization Design",
        "category": "game_design",
        "depth": "Sage",
        "core_knowledge": [
            "Sink-Faucet Economy Model — controlling resource flow",
            "Inflationary vs. Deflationary Economies — EVE Online case study",
            "Player-Driven Markets — auction houses, trading, real money trading",
            "Gacha Mechanics — probability disclosure, pity systems, ethical design",
            "Battle Pass Design — FOMO mitigation and engagement curves",
            "Virtual Currency Psychology — multiple currencies to obscure value",
            "Price Anchoring & Bundling — behavioral economics in game stores",
            "Pay-to-Progress vs. Pay-to-Win — ethical monetization spectrum",
            "Live Service Economics — content cadence and retention investment",
            "Regulatory Landscape — EU, Belgium, Japan loot box laws",
        ],
        "legendary_practitioners": ["CCP Games (EVE economists)", "Ramin Shokrizade", "Nicholas Lovell"],
        "cutting_edge": ["Blockchain-free digital ownership (2025)", "AI economic balancing", "Dynamic pricing models"],
    },
    {
        "id": "ux_game_design",
        "name": "Game UX & Accessibility",
        "category": "game_design",
        "depth": "Oracle",
        "core_knowledge": [
            "Fitts's Law — target size and distance optimization",
            "Hick's Law — reducing decision complexity",
            "Miller's Law — 7±2 information chunks limit",
            "WCAG 2.1 AA/AAA — web content accessibility guidelines",
            "Xbox Accessibility Guidelines (XAGs) — 23 categories",
            "Color Blindness Design — deuteranopia, protanopia, tritanopia safe palettes",
            "Motor Accessibility — one-handed play, remapping, auto-aim assist",
            "Cognitive Accessibility — reading level, UI complexity, information density",
            "Subtitle Best Practices — size, contrast, speaker identification, captions",
            "Haptic Feedback Design — rumble patterns, adaptive triggers",
        ],
        "legendary_practitioners": ["Celia Hodent", "Ian Hamilton", "Cherry Thompson"],
        "cutting_edge": ["Brain-computer interfaces (2025)", "AI-adaptive accessibility", "Eye-tracking UX"],
    },
    {
        "id": "multiplayer_design",
        "name": "Multiplayer & Social Design",
        "category": "game_design",
        "depth": "Sage",
        "core_knowledge": [
            "Netcode Fundamentals — client prediction, server reconciliation, rollback",
            "Matchmaking Algorithms — ELO, Glicko-2, TrueSkill, skill-based matchmaking",
            "Anti-Cheat Architecture — server-authoritative, kernel-level, behavioral analysis",
            "Social Mechanics — guilds, clans, mentoring, social contracts",
            "Toxicity Mitigation — behavior scoring, muting, tribunal systems",
            "Asynchronous Multiplayer — Dark Souls messages, time-shifted play",
            "Co-op Design Patterns — shared objectives, complementary abilities",
            "Spectator Design — camera systems, instant replay, broadcast tools",
            "Cross-Platform Play — unified accounts, input fairness, certification",
            "Server Architecture — dedicated vs P2P, region selection, scalability",
        ],
        "legendary_practitioners": ["John Carmack", "Tim Sweeney", "Riot's Netcode Team"],
        "cutting_edge": ["Cloud-native game servers (2025)", "AI-driven anti-cheat", "Real-time translation in multiplayer"],
    },
    {
        "id": "audio_design",
        "name": "Game Audio & Music Design",
        "category": "game_design",
        "depth": "Sage",
        "core_knowledge": [
            "Adaptive Music Systems — horizontal re-sequencing, vertical layering",
            "Wwise & FMOD — middleware architecture and event-driven audio",
            "Psychoacoustics — perception of sound, masking, spatialization",
            "Foley & Sound Design — layered recording, synthesis, granular techniques",
            "Dynamic Mix — ducking, priority systems, context-aware volumes",
            "Spatial Audio — HRTF, ambisonics, binaural, Dolby Atmos for Games",
            "Procedural Audio — real-time synthesis of wind, water, crowds",
            "Leitmotif in Games — character and location musical themes",
            "Music Theory for Games — modes, tension/resolution, adaptive harmony",
            "Accessibility Audio — audio descriptions, visual indicators for deaf players",
        ],
        "legendary_practitioners": ["Koji Kondo", "Martin O'Donnell", "Mick Gordon", "Austin Wintory"],
        "cutting_edge": ["AI-composed adaptive soundtracks (2025)", "Neural audio synthesis", "Haptic-audio integration"],
    },
    {
        "id": "ai_game_design",
        "name": "Game AI & Behavior Systems",
        "category": "game_design",
        "depth": "Oracle",
        "core_knowledge": [
            "Finite State Machines — state transitions for NPC behavior",
            "Behavior Trees — modular, hierarchical AI decision making",
            "GOAP — Goal-Oriented Action Planning (F.E.A.R. system)",
            "Utility AI — scoring-based decision making with curves",
            "Pathfinding — A*, NavMesh, flow fields, hierarchical pathfinding",
            "Steering Behaviors — Reynolds: seek, flee, wander, flocking, formation",
            "Machine Learning in Games — neural networks for adaptive NPC behavior",
            "Director AI — Left 4 Dead's dynamic pacing system",
            "Emergence — complex behavior from simple interacting systems",
            "Planning Under Uncertainty — Monte Carlo Tree Search, minimax",
        ],
        "legendary_practitioners": ["Jeff Orkin", "Alex Champandard", "Dave Mark", "Tommy Thompson"],
        "cutting_edge": ["LLM-powered NPCs (2025)", "Reinforcement learning game agents", "Theory of Mind in game AI"],
    },
    {
        "id": "vr_ar_design",
        "name": "VR/AR/XR Design",
        "category": "game_design",
        "depth": "Sage",
        "core_knowledge": [
            "Vestibular System — motion sickness prevention, comfort ratings",
            "Room-Scale Design — Guardian systems, play space optimization",
            "Hand Tracking — gesture recognition, haptic feedback integration",
            "Locomotion Methods — teleport, smooth, arm-swing, vehicle-based",
            "UI in VR — diegetic interfaces, spatial menus, gaze-based interaction",
            "Social VR — avatar embodiment, personal space, harassment prevention",
            "Mixed Reality — passthrough, spatial anchors, real-world integration",
            "Foveated Rendering — eye-tracked GPU optimization",
            "Haptic Design — gloves, suits, ultrasonic mid-air haptics",
            "Accessibility in XR — seated modes, one-handed, cognitive load reduction",
        ],
        "legendary_practitioners": ["John Carmack", "Palmer Luckey", "Jesse Schell"],
        "cutting_edge": ["Neural interfaces (2025)", "Holographic displays", "Full-body haptic suits"],
    },
    {
        "id": "game_physics",
        "name": "Game Physics & Simulation",
        "category": "game_design",
        "depth": "Oracle",
        "core_knowledge": [
            "Rigid Body Dynamics — collision detection, impulse resolution",
            "Verlet Integration — stable numerical integration for cloth/rope",
            "Spatial Partitioning — octrees, BSP, broad/narrow phase collision",
            "Soft Body Physics — deformable meshes, mass-spring systems",
            "Fluid Simulation — SPH, Eulerian grids, shallow water equations",
            "Destruction Systems — Voronoi fracture, pre-computed destruction",
            "Vehicle Physics — tire models (Pacejka), suspension, aerodynamics",
            "Character Controller Physics — capsule colliders, ground detection, slopes",
            "Ragdoll & Procedural Animation — active ragdoll, IK blending",
            "Deterministic Physics — fixed-point math for synchronized multiplayer",
        ],
        "legendary_practitioners": ["Erin Catto (Box2D)", "Havok team", "NVIDIA PhysX team"],
        "cutting_edge": ["GPU-accelerated physics (2025)", "Neural physics approximation", "Quantum computing for simulation"],
    },

    # ---- ENGINEERING (10 domains) ----
    {
        "id": "rendering_graphics",
        "name": "Real-Time Rendering & Graphics Programming",
        "category": "engineering",
        "depth": "Oracle",
        "core_knowledge": [
            "Rendering Pipeline — vertex, tessellation, geometry, fragment stages",
            "PBR — Physically Based Rendering (Cook-Torrance BRDF, GGX distribution)",
            "Ray Tracing — BVH acceleration, denoising, hybrid rendering",
            "Global Illumination — light probes, irradiance volumes, DDGI, Lumen",
            "Shadow Techniques — cascade shadow maps, PCSS, ray-traced shadows",
            "Post-Processing — bloom, DOF, motion blur, TAA, FXAA, DLSS/FSR/XeSS",
            "GPU Programming — compute shaders, wave intrinsics, async compute",
            "Shader Programming — HLSL, GLSL, Metal Shading Language, SPIR-V",
            "LOD Systems — mesh simplification, HLOD, Nanite-style virtualized geometry",
            "Memory Management — texture streaming, virtual texturing, GPU memory pools",
        ],
        "legendary_practitioners": ["John Carmack", "Tim Sweeney", "Natalya Tatarchuk", "Sébastien Hillaire"],
        "cutting_edge": ["Neural radiance fields in games (2025)", "Path tracing at 60fps", "ML-based super resolution"],
    },
    {
        "id": "engine_architecture",
        "name": "Game Engine Architecture",
        "category": "engineering",
        "depth": "Oracle",
        "core_knowledge": [
            "Entity-Component-System (ECS) — data-oriented design for performance",
            "Job System — multi-threaded task scheduling and dependency graphs",
            "Memory Allocators — pool, stack, buddy, TLSF allocators",
            "Asset Pipeline — import, process, cook, package, hot-reload",
            "Scripting Integration — Lua, C#, visual scripting, hot-reloading",
            "Scene Management — spatial hashing, octrees, scene graphs",
            "Serialization — binary formats, versioning, schema evolution",
            "Plugin Architecture — modular extension systems",
            "Build Systems — incremental builds, distributed compilation, caching",
            "Profiling & Optimization — CPU/GPU profilers, memory tracking, frame budgets",
        ],
        "legendary_practitioners": ["Tim Sweeney (Unreal)", "Unity Architecture Team", "id Software"],
        "cutting_edge": ["Rust game engines (2025)", "Data-oriented everything", "Cloud-streaming engine architectures"],
    },
    {
        "id": "networking_backend",
        "name": "Game Networking & Backend Systems",
        "category": "engineering",
        "depth": "Sage",
        "core_knowledge": [
            "Client-Server Architecture — authoritative server, client prediction",
            "Rollback Netcode — GGPO, input delay vs rollback trade-offs",
            "State Synchronization — snapshot interpolation, delta compression",
            "Matchmaking Services — queue management, skill brackets, region routing",
            "Dedicated Server Orchestration — Kubernetes, Agones, scaling policies",
            "Database Design — player profiles, leaderboards, inventory systems",
            "CDN & Asset Delivery — patch distribution, differential updates",
            "Analytics Pipeline — event tracking, funnel analysis, A/B testing",
            "LiveOps Tools — feature flags, remote config, server-side updates",
            "Security — packet encryption, server validation, DDoS mitigation",
        ],
        "legendary_practitioners": ["Glenn Fiedler", "Riot Games Networking Team", "Epic Online Services"],
        "cutting_edge": ["Edge computing for games (2025)", "WebTransport for web games", "AI-driven server scaling"],
    },
    {
        "id": "optimization_performance",
        "name": "Performance Optimization",
        "category": "engineering",
        "depth": "Oracle",
        "core_knowledge": [
            "CPU Optimization — cache coherence, SIMD, branch prediction, prefetching",
            "GPU Optimization — occupancy, bandwidth, ALU/TEX balance, wave management",
            "Memory Optimization — allocation patterns, fragmentation, virtual memory",
            "Draw Call Optimization — instancing, batching, indirect drawing, GPU-driven",
            "Loading Optimization — async loading, streaming, priority queues",
            "Frame Budgeting — 16.67ms (60fps), 33.33ms (30fps) breakdown",
            "Profiling Methodology — capture, analyze, hypothesis, optimize, validate",
            "Platform-Specific — console cert requirements, mobile thermal throttling",
            "Algorithmic Optimization — amortized costs, spatial structures, approximations",
            "Compile-Time Optimization — templates, constexpr, link-time optimization",
        ],
        "legendary_practitioners": ["Mike Acton", "Andreas Fredriksson", "Fabian Giesen"],
        "cutting_edge": ["ML-guided optimization (2025)", "Auto-LOD with neural networks", "Shader occupancy AI"],
    },
    {
        "id": "procedural_generation",
        "name": "Procedural Content Generation",
        "category": "engineering",
        "depth": "Sage",
        "core_knowledge": [
            "Noise Functions — Perlin, Simplex, Worley, value noise, domain warping",
            "Wave Function Collapse — constraint-based tile generation",
            "L-Systems — Lindenmayer systems for plant/architecture generation",
            "Grammar-Based Generation — shape grammars, story grammars",
            "Cellular Automata — cave generation, terrain erosion",
            "BSP Trees — dungeon generation via binary space partitioning",
            "Genetic Algorithms — evolutionary content optimization",
            "Machine Learning PCG — GANs, VAEs, diffusion models for assets",
            "Quality Metrics — playability verification, aesthetic evaluation",
            "Seed Systems — reproducible generation, shareable worlds",
        ],
        "legendary_practitioners": ["Tarn Adams (Dwarf Fortress)", "Hello Games (No Man's Sky)", "Edmund McMillen"],
        "cutting_edge": ["Diffusion model level generation (2025)", "LLM quest generation", "Neural terrain synthesis"],
    },
    {
        "id": "tools_pipeline",
        "name": "Tools & Pipeline Engineering",
        "category": "engineering",
        "depth": "Sage",
        "core_knowledge": [
            "Editor Architecture — undo/redo, multi-viewport, property systems",
            "Asset Pipeline — import, validation, processing, cooking, deployment",
            "Version Control for Games — LFS, Perforce, plastic SCM patterns",
            "Build Automation — CI/CD for games, cook pipelines, automated testing",
            "Content Validation — automated testing of game content integrity",
            "Live Editing — hot-reload, in-game tweaking, remote tuning",
            "Data-Driven Workflows — spreadsheet integration, data tables, configs",
            "Scripting Tools — visual scripting, debug visualization, profiling UI",
            "Collaboration Tools — multi-user editing, change tracking, review flows",
            "Platform Deployment — console submission, store requirements, patches",
        ],
        "legendary_practitioners": ["Naughty Dog Tools Team", "Insomniac Games Pipeline Team"],
        "cutting_edge": ["AI-assisted content creation (2025)", "Cloud-based dev environments", "Real-time collaboration"],
    },
    {
        "id": "animation_systems",
        "name": "Animation Systems & Character Tech",
        "category": "engineering",
        "depth": "Sage",
        "core_knowledge": [
            "Skeletal Animation — bone hierarchies, skinning, animation blending",
            "State Machines — animation state graphs, transitions, layers",
            "Inverse Kinematics — CCD, FABRIK, analytical IK for feet/hands",
            "Motion Matching — database-driven animation selection (Ubisoft)",
            "Procedural Animation — physics-based, IK-driven, additive layers",
            "Facial Animation — blend shapes, FACS, performance capture",
            "Root Motion — character movement driven by animation data",
            "Animation Compression — curve fitting, quantization, streaming",
            "Crowd Animation — LOD animation, shared skeletons, instanced crowds",
            "Motion Capture Pipeline — cleanup, retargeting, solving",
        ],
        "legendary_practitioners": ["Naughty Dog Animation Team", "Simon Clavet (Ubisoft)", "Daniel Holden"],
        "cutting_edge": ["Neural motion synthesis (2025)", "Real-time style transfer", "AI-driven lip sync"],
    },
    {
        "id": "security_anticheat",
        "name": "Game Security & Anti-Cheat",
        "category": "engineering",
        "depth": "Sage",
        "core_knowledge": [
            "Server-Authoritative Design — never trust the client",
            "Packet Encryption — TLS, custom protocols, replay attack prevention",
            "Memory Protection — obfuscation, encryption, integrity checking",
            "Behavioral Analysis — statistical anomaly detection in player actions",
            "Kernel-Level Anti-Cheat — driver-based protection, hypervisor monitoring",
            "Speed Hack Detection — server-side time validation",
            "Aim Bot Detection — input pattern analysis, kill-cam review",
            "Economy Exploitation — duplication bugs, market manipulation detection",
            "DDoS Mitigation — traffic scrubbing, anycast, rate limiting",
            "Responsible Disclosure — bug bounty programs, vulnerability management",
        ],
        "legendary_practitioners": ["Riot Vanguard Team", "EasyAntiCheat", "BattlEye"],
        "cutting_edge": ["ML-based cheat detection (2025)", "Behavioral biometrics", "Trusted execution environments"],
    },
    {
        "id": "cross_platform",
        "name": "Cross-Platform Development",
        "category": "engineering",
        "depth": "Sage",
        "core_knowledge": [
            "Platform Abstraction Layers — HAL design for render, input, audio, networking",
            "Console Development — PS5, Xbox Series X|S, Switch certification",
            "Mobile Optimization — thermal throttling, battery, memory constraints",
            "PC Configuration — scalability settings, min/recommended specs",
            "Cloud Gaming — Stadia/xCloud/Luna architecture, latency compensation",
            "Web Games — WebGPU, WebAssembly, WebGL2, progressive loading",
            "Input Handling — controller, keyboard/mouse, touch, gyroscope, VR controllers",
            "Compliance — ESRB, PEGI, age gates, regional requirements",
            "Save Systems — cross-platform progression, cloud saves",
            "Certification — first-party requirements, submission process, waivers",
        ],
        "legendary_practitioners": ["Epic Games (Fortnite)", "Digital Foundry Analysis Team"],
        "cutting_edge": ["WebGPU native games (2025)", "ARM-based gaming PCs", "Cloud-native game development"],
    },
    {
        "id": "testing_qa",
        "name": "Game Testing & Quality Assurance",
        "category": "engineering",
        "depth": "Oracle",
        "core_knowledge": [
            "Test Pyramid — unit, integration, system, acceptance testing for games",
            "Automated Testing — screenshot comparison, replay systems, monkey testing",
            "Performance Testing — frame rate profiling, memory leak detection",
            "Regression Testing — build verification, smoke tests, critical paths",
            "Compatibility Testing — hardware matrices, driver versions, OS variants",
            "Localization Testing — text overflow, cultural sensitivity, bi-directional text",
            "Accessibility Testing — CVAA compliance, screen reader, colorblind modes",
            "Network Testing — latency simulation, packet loss, disconnection handling",
            "Load Testing — server capacity, matchmaking under load, economy stress",
            "Certification Testing — first-party requirements, submission checklists",
        ],
        "legendary_practitioners": ["Nintendo Quality Assurance", "Bethesda QA (post-reformation)"],
        "cutting_edge": ["AI-driven test generation (2025)", "Self-healing test suites", "Automated visual regression"],
    },

    # ---- ART & VISUAL (10 domains) ----
    {
        "id": "concept_art",
        "name": "Concept Art & Visual Development",
        "category": "art",
        "depth": "Sage",
        "core_knowledge": [
            "Thumbnail Iteration — rapid ideation through small-scale sketches",
            "Color Theory — HSV relationships, temperature, atmospheric perspective",
            "Composition — rule of thirds, golden ratio, leading lines, tangent avoidance",
            "Mood & Atmosphere — value structure, lighting direction, color scripts",
            "Character Design — silhouette readability, cultural semiotics, personality expression",
            "Environment Design — biome logic, architectural style, historical reference",
            "Prop Design — functionality communication, scale indication, material language",
            "Style Guides — art bibles, reference sheets, brand consistency",
            "Visual Storytelling — sequential art, key frames, narrative illustration",
            "Iterative Feedback — critique methodology, stakeholder alignment",
        ],
        "legendary_practitioners": ["Feng Zhu", "Craig Mullins", "Sparth (Nicolas Bouvier)", "Syd Mead"],
        "cutting_edge": ["AI-assisted concept iteration (2025)", "3D concept art workflows", "Neural style development"],
    },
    {
        "id": "3d_modeling",
        "name": "3D Modeling & Sculpting",
        "category": "art",
        "depth": "Sage",
        "core_knowledge": [
            "Topology — edge flow for animation, quad dominance, pole management",
            "Retopology — high-to-low poly workflows, auto-retopology tools",
            "UV Mapping — texel density, seam placement, UDIM workflows",
            "Sculpting — ZBrush/Blender workflows, anatomy, hard-surface techniques",
            "LOD Creation — mesh simplification, proxy geometry, imposters",
            "Material Assignment — material IDs, vertex colors, masking",
            "Modular Workflows — kit-bashing, trim sheets, atlas textures",
            "Technical Constraints — triangle budgets, draw call awareness, memory limits",
            "Validation — watertight meshes, normal direction, scale consistency",
            "Pipeline Integration — naming conventions, export settings, scene hierarchy",
        ],
        "legendary_practitioners": ["Tor Frick", "Vitaly Bulgarov", "Paul Shortino"],
        "cutting_edge": ["AI-generated 3D meshes (2025)", "Neural implicit surfaces", "Gaussian splatting for games"],
    },
    {
        "id": "texturing_materials",
        "name": "Texturing & Material Creation",
        "category": "art",
        "depth": "Sage",
        "core_knowledge": [
            "PBR Workflows — metalness/roughness, specular/glossiness, energy conservation",
            "Substance Designer — procedural material graphs, noise functions",
            "Substance Painter — projection painting, smart materials, generators",
            "Texture Maps — albedo, normal, roughness, metalness, AO, height, emissive",
            "Trim Sheets & Atlases — shared texture space optimization",
            "Tiling Techniques — seamless textures, histogram-matched blending",
            "Weathering & Aging — procedural dirt, wear, rust, moss accumulation",
            "Material Layering — runtime material blending, vertex-painted layers",
            "Texture Streaming — virtual texturing, mip-map management",
            "Style Consistency — art direction adherence across teams",
        ],
        "legendary_practitioners": ["Wes McDermott", "Sebastian Zapata", "Allegorithmic/Adobe Team"],
        "cutting_edge": ["Neural material synthesis (2025)", "AI texture upscaling", "Physically-accurate material scan"],
    },
    {
        "id": "vfx_particles",
        "name": "Visual Effects & Particle Systems",
        "category": "art",
        "depth": "Sage",
        "core_knowledge": [
            "Particle Systems — emitters, forces, collisions, sub-emitters",
            "GPU Particles — compute shader particles, millions of instances",
            "Shader Effects — dissolve, hologram, shield, portal, force field",
            "Post-Processing VFX — screen-space effects, distortion, color grading",
            "Flipbook Animation — sprite sheet creation, timing, blending",
            "Mesh Effects — vertex animation textures (VAT), morphing",
            "Physics-Based VFX — fluid sim, smoke, fire, destruction debris",
            "Optimization — overdraw reduction, fill rate, particle LOD",
            "Stylized VFX — anime-style, painterly, pixel art effects",
            "Readability — gameplay-first VFX, visual noise management, color coding",
        ],
        "legendary_practitioners": ["Jason Keyser", "Gabriel Aguiar", "Riot VFX Team"],
        "cutting_edge": ["Neural VFX synthesis (2025)", "Real-time fluid rendering", "AI particle behavior"],
    },
    {
        "id": "ui_art",
        "name": "UI Art & Interface Design",
        "category": "art",
        "depth": "Sage",
        "core_knowledge": [
            "HUD Design — minimal, contextual, diegetic, spatial, meta",
            "Menu Design — navigation hierarchy, information architecture",
            "Typography — readability at distance, screen-safe fonts, dynamic sizing",
            "Icon Design — recognition, consistency, cultural universality",
            "Color Systems — semantic color, accessibility, dark/light modes",
            "Animation — micro-interactions, transitions, loading states, juice",
            "Responsive Design — multi-resolution, aspect ratio, safe zones",
            "Accessibility — high contrast, scalable UI, screen reader support",
            "Localization — text expansion, RTL support, CJK typography",
            "Platform Conventions — console, PC, mobile UI paradigms",
        ],
        "legendary_practitioners": ["Ash Thorp", "Territory Studio", "Bungie UI Team"],
        "cutting_edge": ["Spatial UI for XR (2025)", "AI-adaptive interfaces", "Neural typography"],
    },
    {
        "id": "lighting_art",
        "name": "Lighting Art & Cinematography",
        "category": "art",
        "depth": "Oracle",
        "core_knowledge": [
            "Three-Point Lighting — key, fill, rim light fundamentals",
            "Color Temperature — warm/cool balance, time-of-day progressions",
            "Volumetric Lighting — god rays, fog, atmospheric scattering",
            "Indirect Lighting — bounced light, color bleeding, ambient occlusion",
            "Dynamic vs Baked — light map resolution, probe placement, hybrid approaches",
            "Cinematic Lighting — film techniques adapted for interactive media",
            "Mood & Emotion — psychological impact of color and shadow",
            "Performance Budget — shadow resolution, light count, culling",
            "HDR & Tone Mapping — exposure control, bloom thresholds",
            "Time of Day Systems — sky models, sun position, moonlight",
        ],
        "legendary_practitioners": ["Roger Deakins (film influence)", "Naughty Dog Lighting Team", "CD Projekt RED"],
        "cutting_edge": ["Real-time path-traced lighting (2025)", "AI light placement", "Spectral rendering"],
    },
    {
        "id": "tech_art",
        "name": "Technical Art",
        "category": "art",
        "depth": "Oracle",
        "core_knowledge": [
            "Shader Programming — vertex, fragment, compute, tessellation, geometry",
            "Material Functions — reusable shader networks, parameter systems",
            "Rigging — skeleton setup, constraints, deformation, facial rigs",
            "Cloth Simulation — constraint-based, Verlet, wind interaction",
            "Hair Systems — strand-based, card-based, simulation methods",
            "LOD Systems — screen-size transitions, imposters, proxy meshes",
            "Rendering Debugging — frame analysis, shader profiling, overdraw",
            "Tool Development — Maya/Blender Python, engine editor scripting",
            "Pipeline Optimization — batch processing, validation, automation",
            "Cross-Discipline Bridge — translating art intent to technical implementation",
        ],
        "legendary_practitioners": ["Ryan Manning", "Ben Cloward", "Daniel Ilett"],
        "cutting_edge": ["ML shader optimization (2025)", "Neural rigging", "AI-driven pipeline automation"],
    },
    {
        "id": "environment_art",
        "name": "Environment Art",
        "category": "art",
        "depth": "Sage",
        "core_knowledge": [
            "World Building — biome logic, geological consistency, ecosystem design",
            "Modular Construction — kit pieces, snapping, procedural placement",
            "Terrain — heightmap sculpting, splatmap painting, erosion simulation",
            "Vegetation — SpeedTree, billboard LODs, wind animation, density",
            "Architecture — historical accuracy, structural plausibility, scale",
            "Set Dressing — prop placement, storytelling through detail",
            "Weather Systems — rain, snow, fog, wet surface shaders",
            "Destruction — pre-fractured meshes, real-time damage visualization",
            "Optimization — occlusion culling, streaming, instancing, HLOD",
            "Art Direction Consistency — style guides, reference boards, review process",
        ],
        "legendary_practitioners": ["Naughty Dog Environment Team", "FromSoftware World Design"],
        "cutting_edge": ["AI scene generation (2025)", "Photogrammetry-to-game pipelines", "Neural terrain generation"],
    },
    {
        "id": "character_art",
        "name": "Character Art",
        "category": "art",
        "depth": "Sage",
        "core_knowledge": [
            "Anatomy — muscular system, skeletal structure, proportion ratios",
            "Likeness — portrait sculpting, facial proportions, uncanny valley avoidance",
            "Clothing — fabric simulation, wrinkle patterns, material types",
            "Armor & Equipment — functional design, material hierarchy, silhouette",
            "Hair — card-based, strand-based, stylized approaches",
            "Skin Rendering — subsurface scattering, micro-detail, pore structure",
            "Expression — facial action coding system (FACS), emotion conveying",
            "Customization Systems — modular characters, material variations",
            "Performance — texture atlas, shared materials, LOD chains",
            "Cultural Sensitivity — diverse representation, respectful design, research",
        ],
        "legendary_practitioners": ["Hossein Diba", "Rafael Grassetti", "Yuri Shwedoff"],
        "cutting_edge": ["MetaHuman technology (2025)", "AI-generated characters", "Real-time hair simulation"],
    },
    {
        "id": "pixel_2d_art",
        "name": "2D & Pixel Art",
        "category": "art",
        "depth": "Sage",
        "core_knowledge": [
            "Pixel Art Fundamentals — limited palettes, dithering, anti-aliasing by hand",
            "Sprite Animation — frame timing, squash & stretch, anticipation",
            "Tile Design — seamless patterns, transitions, auto-tiling",
            "Parallax Scrolling — depth layers, speed ratios, atmospheric perspective",
            "UI Elements — pixel-perfect icons, fonts, nine-slice scaling",
            "Character Design — readability at small sizes, color coding, personality",
            "Resolution Strategy — target resolution, upscaling methods, subpixel rendering",
            "Color Palette Design — ramp creation, hue shifting, limited palette strategies",
            "Background Art — establishing shots, parallax layers, mood setting",
            "Modern Pixel Art — HD pixel art, mixed-resolution techniques, shader effects",
        ],
        "legendary_practitioners": ["eBoy", "Paul Robertson", "Konjak", "Studio MDHR (Cuphead)"],
        "cutting_edge": ["AI-assisted pixel art (2025)", "Procedural sprite generation", "Neural upscaling for retro"],
    },

    # ---- PRODUCTION & MANAGEMENT (10 domains) ----
    {
        "id": "project_management",
        "name": "Game Project Management",
        "category": "production",
        "depth": "Sage",
        "core_knowledge": [
            "Agile/Scrum for Games — sprint planning, daily standups, retrospectives",
            "Kanban — WIP limits, flow optimization, visual management",
            "Milestone Planning — vertical slice, alpha, beta, gold master, day-one patch",
            "Risk Management — risk registers, mitigation strategies, contingency plans",
            "Resource Allocation — skill matrices, capacity planning, load balancing",
            "Scope Management — feature creep prevention, MoSCoW prioritization",
            "Dependency Tracking — critical path method, Gantt charts, PERT",
            "Stakeholder Management — publisher relations, exec reporting, community",
            "Post-Mortem Culture — blameless retrospectives, knowledge capture",
            "Crunch Prevention — sustainable pace, buffer planning, overtime policies",
        ],
        "legendary_practitioners": ["Mark Cerny (Method)", "Jason Schreier (investigative)", "Agile Game Dev community"],
        "cutting_edge": ["AI project forecasting (2025)", "Predictive resource planning", "Automated sprint planning"],
    },
    {
        "id": "game_business",
        "name": "Game Business & Publishing",
        "category": "production",
        "depth": "Sage",
        "core_knowledge": [
            "Business Models — premium, F2P, subscription, hybrid, ad-supported",
            "Publishing Deals — revenue splits, advances, milestones, IP ownership",
            "Market Analysis — TAM/SAM/SOM, competitive landscape, timing",
            "User Acquisition — CPI, LTV, ROAS, organic vs paid, virality",
            "Live Operations — content cadence, events, season design, engagement",
            "Analytics — KPI frameworks (DAU, MAU, D1/D7/D30, ARPDAU, session length)",
            "Community Management — social media, Discord, content creators, esports",
            "Localization Strategy — tier-1/2/3 markets, EFIGS+CJK, cultural adaptation",
            "Platform Strategy — exclusivity, timed exclusives, cross-platform",
            "Legal — EULA, ToS, privacy policy, COPPA, GDPR, age ratings",
        ],
        "legendary_practitioners": ["Phil Spencer", "Reggie Fils-Aimé", "Devolver Digital"],
        "cutting_edge": ["AI market prediction (2025)", "Player behavior forecasting", "Dynamic content scheduling"],
    },

    # ---- META-COGNITIVE (10 domains) ----
    {
        "id": "systems_thinking",
        "name": "Systems Thinking",
        "category": "meta",
        "depth": "Oracle",
        "core_knowledge": [
            "Feedback Loops — reinforcing and balancing loops in game systems",
            "Emergence — complex behavior from simple interacting rules",
            "Leverage Points — Donella Meadows' 12 places to intervene",
            "Stock and Flow — resource pools and rates of change",
            "Nonlinear Dynamics — butterfly effects, phase transitions, tipping points",
            "Causal Loop Diagrams — mapping system structure and behavior",
            "Archetypes — fixes that fail, shifting the burden, tragedy of the commons",
            "Mental Models — Senge's discipline of challenging assumptions",
            "Boundary Critique — what's included/excluded in system definition",
            "Resilience — adaptive capacity, redundancy, diversity in system design",
        ],
        "legendary_practitioners": ["Donella Meadows", "Peter Senge", "Jay Forrester", "Nassim Taleb"],
        "cutting_edge": ["AI system modeling (2025)", "Digital twin game economies", "Complex adaptive system simulation"],
    },
    {
        "id": "design_patterns",
        "name": "Software Design Patterns for Games",
        "category": "meta",
        "depth": "Oracle",
        "core_knowledge": [
            "Game Programming Patterns — Robert Nystrom's catalog",
            "Command Pattern — input abstraction, undo/redo, replay",
            "Observer Pattern — event systems, decoupled communication",
            "State Pattern — character states, animation states, game states",
            "Object Pool — particle reuse, projectile recycling, NPC spawning",
            "Flyweight — shared data for tile types, tree species, enemy variants",
            "Component — composition over inheritance for game entities",
            "Spatial Partition — octree, quadtree, grid for efficient queries",
            "Double Buffer — frame buffer, state buffer, command buffer",
            "Service Locator — decoupled service access for audio, physics, input",
        ],
        "legendary_practitioners": ["Robert Nystrom", "Gang of Four", "Martin Fowler", "Eric Evans"],
        "cutting_edge": ["Reactive patterns for games (2025)", "Actor model game servers", "ECS pattern evolution"],
    },
    {
        "id": "mathematics",
        "name": "Game Mathematics",
        "category": "meta",
        "depth": "Oracle",
        "core_knowledge": [
            "Linear Algebra — vectors, matrices, transformations, quaternions",
            "Calculus — derivatives for physics, integrals for accumulation, curves",
            "Trigonometry — angles, rotations, wave functions, circle math",
            "Probability — random distributions, weighted selection, Markov chains",
            "Geometry — intersection tests, distance functions, signed distance fields",
            "Interpolation — linear, cubic, Hermite, Catmull-Rom, Bezier curves",
            "Number Theory — hash functions, random seeds, modular arithmetic",
            "Numerical Methods — Euler, RK4, Verlet integration, Newton-Raphson",
            "Graph Theory — pathfinding, navigation meshes, dependency resolution",
            "Optimization — gradient descent, simulated annealing, genetic algorithms",
        ],
        "legendary_practitioners": ["Eric Lengyel (3D Math Primer)", "Fletcher Dunn", "Ken Perlin"],
        "cutting_edge": ["Differentiable rendering (2025)", "Neural implicit math", "Quantum algorithms for games"],
    },
    {
        "id": "psychology",
        "name": "Player Psychology & Behavioral Science",
        "category": "meta",
        "depth": "Oracle",
        "core_knowledge": [
            "Flow Theory — Csikszentmihalyi's optimal experience zone",
            "Self-Determination Theory — autonomy, competence, relatedness needs",
            "Cognitive Load Theory — intrinsic, extraneous, germane load management",
            "Behavioral Economics — loss aversion, anchoring, endowment effect",
            "Habit Formation — Hook Model (trigger → action → variable reward → investment)",
            "Social Psychology — social proof, FOMO, belonging, status seeking",
            "Attention Economics — scarce attention allocation in game interfaces",
            "Emotion Design — Plutchik's wheel, emotional arcs, catharsis",
            "Motivation Theory — intrinsic vs extrinsic, overjustification effect",
            "Dark Patterns — ethical boundaries, manipulation awareness, player advocacy",
        ],
        "legendary_practitioners": ["Celia Hodent", "Raph Koster", "Jesse Schell", "Daniel Kahneman"],
        "cutting_edge": ["Affective computing in games (2025)", "Neurogaming", "Biometric-adaptive gameplay"],
    },
    {
        "id": "history_of_games",
        "name": "History of Video Games",
        "category": "meta",
        "depth": "Scholar",
        "core_knowledge": [
            "Golden Age — Atari, arcade era, home console revolution",
            "Console Wars — Nintendo vs Sega, PlayStation vs Xbox",
            "PC Gaming Evolution — DOS, Windows, Steam, digital distribution",
            "MMO Era — Ultima Online, EverQuest, WoW, player-created economies",
            "Indie Revolution — braid, Minecraft, Undertale, democratization",
            "Mobile Gaming — iPhone App Store, F2P model, casual audience expansion",
            "Esports — StarCraft Korea, LoL, Fortnite, billion-dollar industry",
            "VR Generations — Virtual Boy, Oculus Rift, Quest, Apple Vision Pro",
            "Game Preservation — digital ownership, emulation, archival challenges",
            "Cultural Impact — games as art, congressional hearings, academic recognition",
        ],
        "legendary_practitioners": ["Nolan Bushnell", "Shigeru Miyamoto", "John Carmack", "Gabe Newell"],
        "cutting_edge": ["Interactive game history archives (2025)", "AI-restored classic games"],
    },
    {
        "id": "ethics_responsibility",
        "name": "Game Ethics & Social Responsibility",
        "category": "meta",
        "depth": "Sage",
        "core_knowledge": [
            "Loot Box Ethics — gambling mechanics, regulatory landscape, transparency",
            "Addiction Prevention — time limits, spending caps, parental controls",
            "Representation — diversity in characters, stories, development teams",
            "Crunch Culture — worker rights, unionization, sustainable development",
            "Environmental Impact — server energy, digital vs physical, carbon footprint",
            "Privacy — data collection, behavioral tracking, children's protection",
            "Content Moderation — toxicity, hate speech, reporting systems",
            "Cultural Sensitivity — stereotypes, appropriation, respectful portrayal",
            "Accessibility as Equity — disability representation, inclusive design",
            "AI Ethics in Games — NPC consent, player data usage, generated content ownership",
        ],
        "legendary_practitioners": ["IGDA Ethics Committee", "Fair Play Alliance", "AbleGamers"],
        "cutting_edge": ["AI ethics frameworks for games (2025)", "Environmental sustainability scoring"],
    },
    {
        "id": "competitive_analysis",
        "name": "Competitive Intelligence & Market Strategy",
        "category": "meta",
        "depth": "Sage",
        "core_knowledge": [
            "Porter's Five Forces — industry analysis framework",
            "Blue Ocean Strategy — creating uncontested market space",
            "SWOT Analysis — strengths, weaknesses, opportunities, threats",
            "Benchmarking — systematic comparison against best-in-class",
            "Market Segmentation — demographic, psychographic, behavioral",
            "Positioning — unique value proposition, differentiation strategy",
            "Trend Analysis — emerging genres, platform shifts, technology adoption",
            "Post-Launch Analysis — reviews, player feedback, sales trajectory",
            "Franchise Building — IP development, cross-media, community cultivation",
            "Platform Economics — store fees, revenue shares, feature promotion",
        ],
        "legendary_practitioners": ["Michael Porter", "Nintendo (Blue Ocean)", "Valve (Steam economics)"],
        "cutting_edge": ["AI competitive intelligence (2025)", "Real-time market sentiment analysis"],
    },
    {
        "id": "leadership",
        "name": "Creative & Technical Leadership",
        "category": "meta",
        "depth": "Sage",
        "core_knowledge": [
            "Vision Communication — articulating creative direction clearly",
            "Technical Direction — architecture decisions, technology strategy",
            "Team Building — hiring, culture, mentoring, skill development",
            "Conflict Resolution — creative disagreements, priority negotiations",
            "Decision Making — informed intuition, data-driven, consensus building",
            "Delegation — trust, accountability, growth opportunities",
            "Feedback Culture — constructive criticism, praise, review processes",
            "Cross-Functional Communication — art-engineering-design alignment",
            "Change Management — pivots, scope changes, team morale during shifts",
            "Servant Leadership — removing blockers, enabling others to do best work",
        ],
        "legendary_practitioners": ["Shigeru Miyamoto", "Amy Hennig", "Todd Howard", "Phil Spencer"],
        "cutting_edge": ["AI-augmented leadership (2025)", "Remote-first studio management"],
    },
    {
        "id": "machine_learning_games",
        "name": "Machine Learning for Games",
        "category": "meta",
        "depth": "Oracle",
        "core_knowledge": [
            "Reinforcement Learning — Q-learning, policy gradients, PPO for game agents",
            "Supervised Learning — player behavior prediction, content recommendation",
            "Generative Models — GANs, VAEs, diffusion models for asset generation",
            "Neural Networks — architecture design, training, inference optimization",
            "Natural Language Processing — LLM integration, dialogue generation",
            "Computer Vision — image recognition, style transfer, upscaling",
            "Recommendation Systems — content surfacing, matchmaking, difficulty",
            "Anomaly Detection — cheat detection, bug identification, QA automation",
            "Transfer Learning — pre-trained models adapted for game-specific tasks",
            "MLOps — model deployment, A/B testing, monitoring, retraining pipelines",
        ],
        "legendary_practitioners": ["DeepMind (AlphaGo/Star)", "OpenAI Five", "Nvidia GameWorks AI"],
        "cutting_edge": ["Foundation models for games (2025)", "Real-time neural rendering", "Autonomous game testing"],
    },
]


# =============================================================================
# KNOWLEDGE APPLICATION
# =============================================================================

def _get_relevant_domains(agent: dict) -> list:
    """Determine which knowledge domains are most relevant to an agent."""
    role = agent.get("role", "").lower()
    category = agent.get("category", "").lower()
    specialty = agent.get("specialty", "").lower()

    relevant = []
    for domain in KNOWLEDGE_DOMAINS:
        relevance = 0.3  # Base relevance for all domains (cross-disciplinary)

        # Category matching
        if domain["category"] in category:
            relevance += 0.4
        if domain["category"] == "meta":
            relevance += 0.2  # Meta-knowledge always relevant

        # Role-specific boosts
        if "design" in role and domain["category"] == "game_design":
            relevance += 0.3
        if "engineer" in role and domain["category"] == "engineering":
            relevance += 0.3
        if "art" in role and domain["category"] == "art":
            relevance += 0.3
        if "lead" in role or "director" in role:
            if domain["id"] in ["leadership", "project_management"]:
                relevance += 0.4
        if "ai" in specialty or "ai" in role:
            if domain["id"] in ["ai_game_design", "machine_learning_games"]:
                relevance += 0.5
        if "physics" in specialty:
            if domain["id"] in ["game_physics", "mathematics"]:
                relevance += 0.5
        if "audio" in specialty or "sound" in specialty:
            if domain["id"] == "audio_design":
                relevance += 0.5
        if "render" in specialty or "graphics" in specialty:
            if domain["id"] in ["rendering_graphics", "lighting_art"]:
                relevance += 0.5
        if "narrative" in specialty or "story" in specialty:
            if domain["id"] == "narrative_design":
                relevance += 0.5
        if "ux" in specialty or "ui" in specialty:
            if domain["id"] in ["ux_game_design", "ui_art"]:
                relevance += 0.5
        if "network" in specialty or "multiplayer" in specialty:
            if domain["id"] in ["multiplayer_design", "networking_backend"]:
                relevance += 0.5
        if "accuracy" in category or "qa" in category:
            if domain["id"] in ["testing_qa", "ethics_responsibility"]:
                relevance += 0.4
        if "ghost" in category or "methodology" in role:
            if domain["id"] in ["design_patterns", "systems_thinking"]:
                relevance += 0.4
        if "angel" in category or "complexity" in role:
            if domain["id"] in ["optimization_performance", "systems_thinking"]:
                relevance += 0.4
        if "seraphim" in category:
            if domain["id"] in ["testing_qa", "mathematics"]:
                relevance += 0.4
        if "cherubim" in category:
            if domain["id"] in ["project_management", "testing_qa", "ethics_responsibility"]:
                relevance += 0.4
        if "pantheon" in category:
            relevance += 0.3  # Pantheon agents are domain experts — all knowledge relevant

        relevant.append({
            "domain": domain,
            "relevance": min(1.0, relevance),
            "depth": domain["depth"],
        })

    # Sort by relevance
    relevant.sort(key=lambda x: x["relevance"], reverse=True)
    return relevant


def get_agent_knowledge(agent: dict) -> dict:
    """Get the extraordinary knowledge profile for a single agent."""
    agent_id = agent.get("id", "unknown")
    agent_name = agent.get("name", "Unknown")
    relevant = _get_relevant_domains(agent)

    primary_domains = [r for r in relevant if r["relevance"] >= 0.6]
    secondary_domains = [r for r in relevant if 0.4 <= r["relevance"] < 0.6]
    awareness_domains = [r for r in relevant if r["relevance"] < 0.4]

    total_knowledge_points = sum(
        len(r["domain"]["core_knowledge"]) * (1 + r["relevance"])
        for r in relevant
    )

    return {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "knowledge_profile": {
            "total_domains": len(KNOWLEDGE_DOMAINS),
            "primary_domains": len(primary_domains),
            "secondary_domains": len(secondary_domains),
            "awareness_domains": len(awareness_domains),
            "total_knowledge_points": int(total_knowledge_points),
        },
        "primary_expertise": [{
            "domain_id": r["domain"]["id"],
            "domain_name": r["domain"]["name"],
            "category": r["domain"]["category"],
            "depth": r["depth"],
            "relevance": round(r["relevance"], 2),
            "core_knowledge_count": len(r["domain"]["core_knowledge"]),
            "legendary_practitioners": r["domain"].get("legendary_practitioners", []),
            "cutting_edge": r["domain"].get("cutting_edge", []),
        } for r in primary_domains],
        "secondary_expertise": [{
            "domain_id": r["domain"]["id"],
            "domain_name": r["domain"]["name"],
            "relevance": round(r["relevance"], 2),
        } for r in secondary_domains],
        "cross_disciplinary_synthesis": {
            "enabled": True,
            "methodology": "Oracle-level knowledge synthesis across all 50 domains",
            "framework": "First Principles + Analogical Reasoning + Systems Thinking",
        },
        "meta_cognitive_framework": {
            "learning_strategy": "Deliberate Practice + Spaced Repetition + Interleaving",
            "knowledge_application": "Context-Aware Transfer + Pattern Recognition + First Principles",
            "knowledge_creation": "Synthesis + Experimentation + Cross-Domain Innovation",
        },
    }


def get_knowledge_summary_stats() -> dict:
    """Get aggregate knowledge statistics."""
    total_knowledge_items = sum(len(d["core_knowledge"]) for d in KNOWLEDGE_DOMAINS)
    total_practitioners = sum(len(d.get("legendary_practitioners", [])) for d in KNOWLEDGE_DOMAINS)
    total_cutting_edge = sum(len(d.get("cutting_edge", [])) for d in KNOWLEDGE_DOMAINS)

    categories = {}
    for d in KNOWLEDGE_DOMAINS:
        cat = d["category"]
        if cat not in categories:
            categories[cat] = {"count": 0, "domains": []}
        categories[cat]["count"] += 1
        categories[cat]["domains"].append(d["name"])

    return {
        "total_knowledge_domains": len(KNOWLEDGE_DOMAINS),
        "total_knowledge_items": total_knowledge_items,
        "total_legendary_practitioners": total_practitioners,
        "total_cutting_edge_topics": total_cutting_edge,
        "knowledge_categories": categories,
        "depth_levels": KNOWLEDGE_DEPTHS,
        "philosophy": "Knowledge is the capacity to transform information into wisdom",
    }
