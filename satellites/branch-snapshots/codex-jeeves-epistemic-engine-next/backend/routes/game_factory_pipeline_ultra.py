"""
Ultra Pipeline Extension (Steps 99-198)
100 additional ultra-specialized game development agents.
Brings total pipeline from 100 to 200 steps.
"""

# =============================================================================
# ULTRA PIPELINE STEP DEFINITIONS
# =============================================================================

ULTRA_PIPELINE_STEPS = [
    {
        "step": 99, "name": "Hair & Fur Simulation",
        "agent": "strand_agent", "phase": "visual",
        "description": "Strand simulates realistic hair, fur, feathers, and strand-based dynamics",
        "icon": "brush", "color": "#D4A574",
        "prompt_key": "hair_fur",
    },
    {
        "step": 100, "name": "Snow & Sand Deformation",
        "agent": "imprint_agent", "phase": "visual",
        "description": "Imprint creates dynamic snow trails, sand footprints, and terrain deformation",
        "icon": "footsteps", "color": "#E2E8F0",
        "prompt_key": "snow_sand",
    },
    {
        "step": 101, "name": "Mirror & Reflection Rendering",
        "agent": "mirror_agent", "phase": "visual",
        "description": "Mirror builds planar reflections, mirror puzzles, and real-time reflection probes",
        "icon": "scan", "color": "#93C5FD",
        "prompt_key": "mirrors",
    },
    {
        "step": 102, "name": "Portal & Dimension Warping",
        "agent": "warp_agent", "phase": "engineering",
        "description": "Warp creates portal rendering, seamless dimension transitions, and non-Euclidean spaces",
        "icon": "aperture", "color": "#A78BFA",
        "prompt_key": "portals",
    },
    {
        "step": 103, "name": "Time Manipulation Mechanics",
        "agent": "chrono_agent", "phase": "engineering",
        "description": "Chrono builds time slow-mo, rewind, freeze, and temporal paradox systems",
        "icon": "time", "color": "#22D3EE",
        "prompt_key": "time_manipulation",
    },
    {
        "step": 104, "name": "Morality & Karma System",
        "agent": "judge_agent", "phase": "design",
        "description": "Judge designs moral choices, karma tracking, alignment shifts, and consequence systems",
        "icon": "scale", "color": "#A3A3A3",
        "prompt_key": "morality",
    },
    {
        "step": 105, "name": "Survival Needs System",
        "agent": "survivor_agent", "phase": "engineering",
        "description": "Survivor creates hunger, thirst, sleep, stamina, and physiological need mechanics",
        "icon": "water", "color": "#34D399",
        "prompt_key": "survival_needs",
    },
    {
        "step": 106, "name": "Disease & Affliction System",
        "agent": "plague_agent", "phase": "engineering",
        "description": "Plague designs diseases, infections, cures, immunity, and contagion spread",
        "icon": "medkit", "color": "#F87171",
        "prompt_key": "disease",
    },
    {
        "step": 107, "name": "Equipment Durability & Repair",
        "agent": "mender_agent", "phase": "engineering",
        "description": "Mender creates durability systems, weapon degradation, repair stations, and maintenance",
        "icon": "construct", "color": "#D97706",
        "prompt_key": "durability",
    },
    {
        "step": 108, "name": "Mining & Resource Excavation",
        "agent": "miner_agent", "phase": "engineering",
        "description": "Miner builds mining mechanics, ore veins, excavation tools, and underground resources",
        "icon": "hammer", "color": "#78716C",
        "prompt_key": "mining",
    },
    {
        "step": 109, "name": "Trap Design & Hazard Placement",
        "agent": "trapsmith_agent", "phase": "design",
        "description": "Trapsmith creates trap crafting, hazard placement, trigger mechanisms, and disarming",
        "icon": "warning", "color": "#FBBF24",
        "prompt_key": "traps",
    },
    {
        "step": 110, "name": "Summoning & Ritual Circles",
        "agent": "conjurer_agent", "phase": "engineering",
        "description": "Conjurer designs summoning circles, ritual mechanics, sacrifice systems, and conjuration",
        "icon": "star", "color": "#C084FC",
        "prompt_key": "summoning",
    },
    {
        "step": 111, "name": "Temperature & Exposure System",
        "agent": "thermal_agent", "phase": "engineering",
        "description": "Thermal creates temperature zones, hypothermia, heatstroke, clothing warmth, and campfires",
        "icon": "thermometer", "color": "#FB923C",
        "prompt_key": "temperature",
    },
    {
        "step": 112, "name": "Fire Propagation & Spread",
        "agent": "inferno_agent", "phase": "engineering",
        "description": "Inferno simulates fire spreading, flammable materials, wildfire, and fire extinguishing",
        "icon": "flame", "color": "#EF4444",
        "prompt_key": "fire_propagation",
    },
    {
        "step": 113, "name": "Electricity & Circuit Systems",
        "agent": "volt_agent", "phase": "engineering",
        "description": "Volt creates power grids, circuit puzzles, electrical hazards, and wiring systems",
        "icon": "flash", "color": "#FACC15",
        "prompt_key": "electricity",
    },
    {
        "step": 114, "name": "Procedural Quest Engine",
        "agent": "questgen_agent", "phase": "engineering",
        "description": "QuestGen creates procedurally generated quests, dynamic objectives, and infinite content",
        "icon": "list", "color": "#4ADE80",
        "prompt_key": "procedural_quests",
    },
    {
        "step": 115, "name": "Merchant AI & Dynamic Pricing",
        "agent": "vendor_agent", "phase": "engineering",
        "description": "Vendor creates smart merchant NPCs, dynamic pricing, supply/demand, and bartering",
        "icon": "cart", "color": "#F59E0B",
        "prompt_key": "merchant_ai",
    },
    {
        "step": 116, "name": "Banking & Financial Services",
        "agent": "banker_agent", "phase": "engineering",
        "description": "Banker designs banks, loans, interest, investments, and financial management",
        "icon": "cash", "color": "#059669",
        "prompt_key": "banking",
    },
    {
        "step": 117, "name": "Death Penalty & Resurrection",
        "agent": "reaper_agent", "phase": "design",
        "description": "Reaper creates death consequences, corpse runs, soul mechanics, and resurrection systems",
        "icon": "skull", "color": "#1E1B4B",
        "prompt_key": "death_system",
    },
    {
        "step": 118, "name": "Transformation & Shapeshift",
        "agent": "morph_agent", "phase": "engineering",
        "description": "Morph creates werewolf forms, polymorph spells, disguises, and transformation combat",
        "icon": "sync", "color": "#7C3AED",
        "prompt_key": "transformation",
    },
    {
        "step": 119, "name": "Mounted Combat & Jousting",
        "agent": "knight_agent", "phase": "engineering",
        "description": "Knight designs mounted combat, lance jousting, cavalry charges, and horse archery",
        "icon": "trophy", "color": "#B45309",
        "prompt_key": "mounted_combat",
    },
    {
        "step": 120, "name": "Arena & Tournament Design",
        "agent": "gladiator_agent", "phase": "design",
        "description": "Gladiator creates arena modes, bracket tournaments, spectator betting, and rankings",
        "icon": "medal", "color": "#DC2626",
        "prompt_key": "arena",
    },
    {
        "step": 121, "name": "War Table & Strategic Command",
        "agent": "commander_agent", "phase": "design",
        "description": "Commander designs war tables, campaign maps, strategic decisions, and army deployment",
        "icon": "map", "color": "#4338CA",
        "prompt_key": "war_table",
    },
    {
        "step": 122, "name": "Espionage & Spy Networks",
        "agent": "spymaster_agent", "phase": "design",
        "description": "Spymaster creates spy recruitment, intelligence gathering, sabotage, and covert ops",
        "icon": "eye-off", "color": "#1E293B",
        "prompt_key": "espionage",
    },
    {
        "step": 123, "name": "Trial & Justice System",
        "agent": "magistrate_agent", "phase": "design",
        "description": "Magistrate designs court trials, evidence presentation, jury systems, and verdicts",
        "icon": "document-text", "color": "#78716C",
        "prompt_key": "justice",
    },
    {
        "step": 124, "name": "Supply Chain & Logistics",
        "agent": "quartermaster_agent", "phase": "engineering",
        "description": "Quartermaster creates supply lines, resource transportation, warehouses, and logistics AI",
        "icon": "cube", "color": "#0369A1",
        "prompt_key": "supply_chain",
    },
    {
        "step": 125, "name": "Tavern & Social Hub Design",
        "agent": "innkeeper_agent", "phase": "content",
        "description": "Innkeeper designs taverns, social gathering spaces, mini-games, and ambient life",
        "icon": "beer", "color": "#92400E",
        "prompt_key": "tavern",
    },
    {
        "step": 126, "name": "Bridge & Structural Engineering",
        "agent": "architect_agent", "phase": "engineering",
        "description": "Architect creates bridge building, structural physics, load bearing, and construction puzzles",
        "icon": "git-network", "color": "#64748B",
        "prompt_key": "construction",
    },
    {
        "step": 127, "name": "Terraforming & World Shaping",
        "agent": "shaper_agent", "phase": "engineering",
        "description": "Shaper creates player terraforming, landscape sculpting, and persistent world modification",
        "icon": "globe", "color": "#15803D",
        "prompt_key": "terraforming",
    },
    {
        "step": 128, "name": "Dream Sequences & Visions",
        "agent": "dreamweaver_agent", "phase": "content",
        "description": "Dreamweaver designs dream levels, vision quests, surreal environments, and subconscious narrative",
        "icon": "moon", "color": "#6366F1",
        "prompt_key": "dreams",
    },
    {
        "step": 129, "name": "Horde & Wave Survival",
        "agent": "horde_agent", "phase": "design",
        "description": "Horde creates wave-based survival, escalating difficulty, supply drops, and last-stand modes",
        "icon": "people", "color": "#B91C1C",
        "prompt_key": "horde_mode",
    },
    {
        "step": 130, "name": "Card & Deck Building",
        "agent": "dealer_agent", "phase": "design",
        "description": "Dealer creates collectible card systems, deck building, card combat, and booster packs",
        "icon": "copy", "color": "#F97316",
        "prompt_key": "card_game",
    },
    {
        "step": 131, "name": "Guild & Clan Headquarters",
        "agent": "guildmaster_agent", "phase": "engineering",
        "description": "Guildmaster builds guild halls, clan upgrades, shared storage, and guild progression",
        "icon": "business", "color": "#7C3AED",
        "prompt_key": "guild_hall",
    },
    {
        "step": 132, "name": "Territory Control & Conquest",
        "agent": "warlord2_agent", "phase": "design",
        "description": "Overlord designs territory capture, zone control, influence maps, and faction dominion",
        "icon": "flag", "color": "#991B1B",
        "prompt_key": "territory",
    },
    {
        "step": 133, "name": "Caravan & Trade Convoy",
        "agent": "caravan_agent", "phase": "engineering",
        "description": "Caravan creates trade convoy escort, route planning, bandit encounters, and merchant caravans",
        "icon": "car", "color": "#CA8A04",
        "prompt_key": "caravan",
    },
    {
        "step": 134, "name": "Museum & Collection Display",
        "agent": "curator_agent", "phase": "content",
        "description": "Curator designs trophy rooms, collectible displays, dioramas, and achievement showcases",
        "icon": "images", "color": "#0EA5E9",
        "prompt_key": "museum",
    },
    {
        "step": 135, "name": "Theater & Live Performance",
        "agent": "director2_agent", "phase": "content",
        "description": "Impresario creates in-game theaters, player performances, audience systems, and stage shows",
        "icon": "film", "color": "#D946EF",
        "prompt_key": "theater",
    },
    {
        "step": 136, "name": "In-Game News & Chronicle",
        "agent": "herald2_agent", "phase": "content",
        "description": "Chronicler generates dynamic news, event reports, world newspapers, and lore broadcasts",
        "icon": "newspaper", "color": "#6B7280",
        "prompt_key": "news_system",
    },
    {
        "step": 137, "name": "Mail & Courier System",
        "agent": "postmaster_agent", "phase": "engineering",
        "description": "Postmaster creates player mail, item attachments, NPC letters, and courier delivery quests",
        "icon": "mail", "color": "#0284C7",
        "prompt_key": "mail_system",
    },
    {
        "step": 138, "name": "Astrology & Celestial Mechanics",
        "agent": "astronomer_agent", "phase": "content",
        "description": "Astronomer designs star maps, constellations, celestial buffs, and zodiac systems",
        "icon": "star", "color": "#1E1B4B",
        "prompt_key": "astrology",
    },
    {
        "step": 139, "name": "Wind Simulation & Air Physics",
        "agent": "zephyr_agent", "phase": "engineering",
        "description": "Zephyr creates wind zones, air currents, glider mechanics, and wind-affected projectiles",
        "icon": "cloudy", "color": "#94A3B8",
        "prompt_key": "wind_physics",
    },
    {
        "step": 140, "name": "LLM-Powered NPC Dialogue",
        "agent": "babel_agent", "phase": "engineering",
        "description": "Babel integrates LLM-driven NPC conversations, contextual responses, and emergent dialogue",
        "icon": "chatbubbles", "color": "#8B5CF6",
        "prompt_key": "llm_dialogue",
    },
    {
        "step": 141, "name": "VR & Extended Reality Support",
        "agent": "reality_agent", "phase": "engineering",
        "description": "Reality creates VR controller mapping, room-scale interaction, and mixed reality support",
        "icon": "glasses", "color": "#2563EB",
        "prompt_key": "vr_support",
    },
    {
        "step": 142, "name": "Haptic Feedback Design",
        "agent": "tactile_agent", "phase": "engineering",
        "description": "Tactile designs DualSense adaptive triggers, HD rumble, and haptic feedback patterns",
        "icon": "hand-left", "color": "#475569",
        "prompt_key": "haptics",
    },
    {
        "step": 143, "name": "Memory Replay & Flashbacks",
        "agent": "memory_agent", "phase": "content",
        "description": "Memory creates playable flashbacks, memory sequences, unreliable narrator scenes",
        "icon": "albums", "color": "#A78BFA",
        "prompt_key": "flashbacks",
    },
    {
        "step": 144, "name": "Ghost & Spectral Mechanics",
        "agent": "phantom_agent", "phase": "engineering",
        "description": "Phantom creates ghost mode, spectral vision, phase-through walls, and spirit realm gameplay",
        "icon": "eye", "color": "#CBD5E1",
        "prompt_key": "ghost_mechanics",
    },
    {
        "step": 145, "name": "Procedural Portrait Generation",
        "agent": "portraitist_agent", "phase": "visual",
        "description": "Portraitist generates unique NPC faces, dialogue portraits, and character mugshots",
        "icon": "person-circle", "color": "#EC4899",
        "prompt_key": "portraits",
    },
    {
        "step": 146, "name": "Voice Synthesis Pipeline",
        "agent": "vocalist_agent", "phase": "content",
        "description": "Vocalist creates TTS voice acting, procedural barks, and dynamic voice line generation",
        "icon": "mic", "color": "#DB2777",
        "prompt_key": "voice_synth",
    },
    {
        "step": 147, "name": "Crowd Simulation & Stadiums",
        "agent": "crowd_agent", "phase": "engineering",
        "description": "Crowd simulates thousands of background NPCs, stadium audiences, and city population",
        "icon": "people-circle", "color": "#0891B2",
        "prompt_key": "crowd_sim",
    },
    {
        "step": 148, "name": "Dynamic Market Economy AI",
        "agent": "economist_agent", "phase": "engineering",
        "description": "Economist creates supply/demand simulation, inflation, market crashes, and economic AI",
        "icon": "trending-up", "color": "#059669",
        "prompt_key": "market_economy",
    },
    {
        "step": 149, "name": "Layered Armor & Protection",
        "agent": "armorer_agent", "phase": "engineering",
        "description": "Armorer designs layered armor, penetration physics, weak points, and damage zones",
        "icon": "shield", "color": "#64748B",
        "prompt_key": "armor_layers",
    },
    {
        "step": 150, "name": "Climbing & Mountaineering",
        "agent": "climber_agent", "phase": "engineering",
        "description": "Climber creates climbing mechanics, stamina grip, ice picks, and vertical exploration",
        "icon": "trending-up", "color": "#0F766E",
        "prompt_key": "climbing",
    },
    {
        "step": 151, "name": "Cave & Tunnel Generation",
        "agent": "spelunker_agent", "phase": "engineering",
        "description": "Spelunker generates cave networks, underground biomes, stalactites, and cave-ins",
        "icon": "layers", "color": "#44403C",
        "prompt_key": "caves",
    },
    {
        "step": 152, "name": "Cosmic Events & Phenomena",
        "agent": "cosmos_agent", "phase": "content",
        "description": "Cosmos creates eclipses, meteor showers, auroras, comets, and cosmic gameplay events",
        "icon": "planet", "color": "#1E1B4B",
        "prompt_key": "cosmic_events",
    },
    {
        "step": 153, "name": "Mythology & Pantheon System",
        "agent": "oracle2_agent", "phase": "content",
        "description": "Pantheon designs god systems, divine blessings, prayers, temples, and deity relationships",
        "icon": "sunny", "color": "#F59E0B",
        "prompt_key": "mythology",
    },
    {
        "step": 154, "name": "Calendar & Festival System",
        "agent": "calendar_agent", "phase": "content",
        "description": "Calendar creates in-game calendars, holidays, seasonal festivals, and time-gated events",
        "icon": "calendar", "color": "#EF4444",
        "prompt_key": "calendar",
    },
    {
        "step": 155, "name": "Dynasty & Inheritance System",
        "agent": "dynasty_agent", "phase": "design",
        "description": "Dynasty creates bloodline progression, inheritance laws, heir systems, and multi-generational play",
        "icon": "git-branch", "color": "#7C2D12",
        "prompt_key": "dynasty",
    },
    {
        "step": 156, "name": "Permadeath & Ironman Mode",
        "agent": "ironman_agent", "phase": "design",
        "description": "Ironman creates permadeath stakes, ironman saves, legacy bonuses, and hardcore modes",
        "icon": "skull", "color": "#1C1917",
        "prompt_key": "permadeath",
    },
    {
        "step": 157, "name": "DLC & Expansion Architecture",
        "agent": "expansion_agent", "phase": "engineering",
        "description": "Expansion creates modular DLC systems, expansion hooks, content packs, and season architecture",
        "icon": "add-circle", "color": "#4338CA",
        "prompt_key": "dlc_system",
    },
    {
        "step": 158, "name": "Replay Analysis System",
        "agent": "analyst_agent", "phase": "engineering",
        "description": "Analyst creates post-game replay analysis, stat breakdowns, highlight reels, and heat maps",
        "icon": "bar-chart", "color": "#0D9488",
        "prompt_key": "replay_analysis",
    },
    {
        "step": 159, "name": "Companion Evolution System",
        "agent": "bondsage_agent", "phase": "engineering",
        "description": "Bond designs companion growth, loyalty evolution, shared abilities, and trust-based unlocks",
        "icon": "heart-circle", "color": "#E11D48",
        "prompt_key": "companion_evolution",
    },
    {
        "step": 160, "name": "Emotion AI & Sentiment",
        "agent": "empath_agent", "phase": "engineering",
        "description": "Empath creates NPC emotional intelligence, mood tracking, player sentiment detection",
        "icon": "happy", "color": "#F472B6",
        "prompt_key": "emotion_ai",
    },
    {
        "step": 161, "name": "Procedural Lore Generator",
        "agent": "mythmaker_agent", "phase": "content",
        "description": "Mythmaker generates procedural histories, creation myths, cultural lore, and world backstory",
        "icon": "book", "color": "#B45309",
        "prompt_key": "procedural_lore",
    },
    {
        "step": 162, "name": "Advanced Difficulty Tuning",
        "agent": "calibrator_agent", "phase": "design",
        "description": "Calibrator creates granular difficulty sliders, custom challenge profiles, and assist modes",
        "icon": "options", "color": "#6366F1",
        "prompt_key": "difficulty_tuning",
    },
    {
        "step": 163, "name": "Anti-Grief & Toxicity Filter",
        "agent": "guardian2_agent", "phase": "engineering",
        "description": "Warden creates anti-grief systems, chat filters, behavior scoring, and toxic player handling",
        "icon": "shield-checkmark", "color": "#16A34A",
        "prompt_key": "anti_grief",
    },
    {
        "step": 164, "name": "Player Mentoring System",
        "agent": "mentor_agent", "phase": "design",
        "description": "Mentor creates veteran-newbie pairing, teaching rewards, guided introductions, and help channels",
        "icon": "school", "color": "#3B82F6",
        "prompt_key": "mentoring",
    },
    {
        "step": 165, "name": "Cross-Save & Cloud Sync v2",
        "agent": "cloudsave_agent", "phase": "engineering",
        "description": "CloudSave creates cross-platform save migration, conflict resolution, and seamless sync",
        "icon": "cloud-done", "color": "#0EA5E9",
        "prompt_key": "cross_save_v2",
    },
    {
        "step": 166, "name": "Streamer & Creator Tools",
        "agent": "broadcast_agent", "phase": "engineering",
        "description": "Broadcast creates Twitch integration, viewer interaction, stream overlays, and clip tools",
        "icon": "videocam", "color": "#9333EA",
        "prompt_key": "streamer_tools",
    },
    {
        "step": 167, "name": "Accessibility Certification",
        "agent": "a11y_agent", "phase": "qa",
        "description": "A11y performs full accessibility audit, CVAA compliance, and certification readiness",
        "icon": "accessibility", "color": "#2DD4BF",
        "prompt_key": "a11y_cert",
    },
    {
        "step": 168, "name": "Localization Management",
        "agent": "polyglot_agent", "phase": "content",
        "description": "Polyglot manages translation pipelines, cultural adaptation, RTL support, and voice localization",
        "icon": "language", "color": "#06B6D4",
        "prompt_key": "localization_mgmt",
    },
    {
        "step": 169, "name": "Age Rating & Content Moderation",
        "agent": "censor_agent", "phase": "qa",
        "description": "Censor evaluates content for ESRB/PEGI ratings, regional compliance, and content toggles",
        "icon": "alert-circle", "color": "#EF4444",
        "prompt_key": "age_rating",
    },
    {
        "step": 170, "name": "Closed Beta Framework",
        "agent": "gatekeeper_agent", "phase": "engineering",
        "description": "Gatekeeper creates beta access systems, feedback forms, NDA management, and phased rollout",
        "icon": "lock-closed", "color": "#475569",
        "prompt_key": "beta_framework",
    },
    {
        "step": 171, "name": "Community Feedback Loop",
        "agent": "listener_agent", "phase": "engineering",
        "description": "Listener creates in-game feedback, bug reporting, feature voting, and community sentiment tracking",
        "icon": "chatbubble-ellipses", "color": "#10B981",
        "prompt_key": "feedback_loop",
    },
    {
        "step": 172, "name": "Live Telemetry Dashboard",
        "agent": "telemetry_agent", "phase": "engineering",
        "description": "Telemetry creates real-time player dashboards, server health, and live KPI monitoring",
        "icon": "pulse", "color": "#0891B2",
        "prompt_key": "telemetry",
    },
    {
        "step": 173, "name": "Crash Reporting Pipeline",
        "agent": "crashwatch_agent", "phase": "engineering",
        "description": "CrashWatch creates crash dump collection, stack trace analysis, and automated bug filing",
        "icon": "bug", "color": "#DC2626",
        "prompt_key": "crash_reporting",
    },
    {
        "step": 174, "name": "Memory & Leak Detection",
        "agent": "memwatch_agent", "phase": "engineering",
        "description": "MemWatch creates memory profiling, leak detection, allocation tracking, and heap analysis",
        "icon": "hardware-chip", "color": "#4B5563",
        "prompt_key": "memory_profiling",
    },
    {
        "step": 175, "name": "GPU Profiling & Optimization",
        "agent": "gpuprof_agent", "phase": "engineering",
        "description": "GPUProf creates GPU profiling tools, draw call analysis, shader complexity metrics",
        "icon": "speedometer", "color": "#F97316",
        "prompt_key": "gpu_profiling",
    },
    {
        "step": 176, "name": "Netcode Lag Compensation",
        "agent": "latency_agent", "phase": "engineering",
        "description": "Latency creates lag compensation, rollback netcode, input prediction, and jitter buffers",
        "icon": "wifi", "color": "#2563EB",
        "prompt_key": "lag_compensation",
    },
    {
        "step": 177, "name": "Server Cluster Architecture",
        "agent": "serverarch_agent", "phase": "engineering",
        "description": "ServerArch designs server topology, sharding, load balancing, and distributed game state",
        "icon": "server", "color": "#1E293B",
        "prompt_key": "server_arch",
    },
    {
        "step": 178, "name": "Database & Persistence Design",
        "agent": "dataarch_agent", "phase": "engineering",
        "description": "DataArch creates database schemas, data migration, backup strategies, and data integrity",
        "icon": "server", "color": "#0369A1",
        "prompt_key": "database_design",
    },
    {
        "step": 179, "name": "CDN & Asset Distribution",
        "agent": "cdn_agent", "phase": "engineering",
        "description": "CDN creates asset delivery networks, patch distribution, download optimization, and regional caching",
        "icon": "cloud-download", "color": "#06B6D4",
        "prompt_key": "cdn_system",
    },
    {
        "step": 180, "name": "Legal & Compliance System",
        "agent": "legal_agent", "phase": "qa",
        "description": "Legal creates EULA generation, terms of service, IP protection, and compliance checklists",
        "icon": "document-text", "color": "#78716C",
        "prompt_key": "legal",
    },
    {
        "step": 181, "name": "GDPR & Privacy Framework",
        "agent": "privacy_agent", "phase": "qa",
        "description": "Privacy creates data collection consent, right to erasure, data portability, and privacy dashboards",
        "icon": "lock-closed", "color": "#059669",
        "prompt_key": "gdpr",
    },
    {
        "step": 182, "name": "Parental Control System",
        "agent": "family_agent", "phase": "engineering",
        "description": "Family creates parental controls, playtime limits, content filters, and family accounts",
        "icon": "people", "color": "#3B82F6",
        "prompt_key": "parental_controls",
    },
    {
        "step": 183, "name": "Account Security & Auth",
        "agent": "sentinel2_agent", "phase": "engineering",
        "description": "AuthGuard creates 2FA, secure login, account recovery, and session management",
        "icon": "key", "color": "#991B1B",
        "prompt_key": "account_security",
    },
    {
        "step": 184, "name": "Cloud Deployment Design",
        "agent": "cloudarch_agent", "phase": "engineering",
        "description": "CloudArch designs cloud infrastructure, container orchestration, and serverless game backends",
        "icon": "cloud", "color": "#0EA5E9",
        "prompt_key": "cloud_deploy",
    },
    {
        "step": 185, "name": "Auto-Scaling & Load Management",
        "agent": "scaler_agent", "phase": "engineering",
        "description": "Scaler creates auto-scaling policies, launch day capacity, and traffic spike handling",
        "icon": "resize", "color": "#4338CA",
        "prompt_key": "auto_scaling",
    },
    {
        "step": 186, "name": "Feature Flag Management",
        "agent": "toggle_agent", "phase": "engineering",
        "description": "Toggle creates feature flags, gradual rollouts, kill switches, and experiment targeting",
        "icon": "toggle", "color": "#F59E0B",
        "prompt_key": "feature_flags",
    },
    {
        "step": 187, "name": "Experiment & A/B Framework",
        "agent": "experiment_agent", "phase": "engineering",
        "description": "Experiment creates A/B testing, multivariate tests, statistical significance, and experiment dashboards",
        "icon": "flask", "color": "#7C3AED",
        "prompt_key": "ab_framework",
    },
    {
        "step": 188, "name": "Player Cohort Analysis",
        "agent": "cohort_agent", "phase": "engineering",
        "description": "Cohort creates player segmentation, behavioral clustering, and personalized experiences",
        "icon": "people-circle", "color": "#0D9488",
        "prompt_key": "cohort_analysis",
    },
    {
        "step": 189, "name": "Retention & Churn Model",
        "agent": "retain_agent", "phase": "design",
        "description": "Retain creates churn prediction, win-back campaigns, engagement scoring, and retention hooks",
        "icon": "refresh-circle", "color": "#EA580C",
        "prompt_key": "retention_model",
    },
    {
        "step": 190, "name": "Revenue Analytics Engine",
        "agent": "revenue_agent", "phase": "engineering",
        "description": "Revenue creates ARPU tracking, LTV calculation, revenue attribution, and forecast models",
        "icon": "cash", "color": "#16A34A",
        "prompt_key": "revenue_analytics",
    },
    {
        "step": 191, "name": "Ethical Ad Integration",
        "agent": "adethics_agent", "phase": "design",
        "description": "AdEthics creates non-intrusive ads, rewarded video, ad frequency caps, and opt-out respect",
        "icon": "megaphone", "color": "#CA8A04",
        "prompt_key": "ad_integration",
    },
    {
        "step": 192, "name": "Press Kit & PR System",
        "agent": "pr_agent", "phase": "content",
        "description": "PR creates press kits, screenshot generators, trailer scripts, and media asset management",
        "icon": "camera", "color": "#F43F5E",
        "prompt_key": "press_kit",
    },
    {
        "step": 193, "name": "Community Management Tools",
        "agent": "community_agent", "phase": "engineering",
        "description": "Community creates moderation dashboards, community events, ambassador programs, and engagement tools",
        "icon": "people", "color": "#8B5CF6",
        "prompt_key": "community_tools",
    },
    {
        "step": 194, "name": "Discussion & Forum System",
        "agent": "forum_agent", "phase": "engineering",
        "description": "Forum creates in-game forums, dev tracker, patch notes viewer, and community discussion",
        "icon": "chatbubbles", "color": "#0284C7",
        "prompt_key": "forum_system",
    },
    {
        "step": 195, "name": "Game Wiki & Help Center",
        "agent": "wiki_agent", "phase": "content",
        "description": "Wiki creates in-game help systems, searchable wiki, tooltips, and guided walkthroughs",
        "icon": "help-circle", "color": "#64748B",
        "prompt_key": "wiki_system",
    },
    {
        "step": 196, "name": "Developer SDK & API",
        "agent": "sdk_agent", "phase": "engineering",
        "description": "SDK creates developer APIs, plugin architecture, third-party integration hooks, and documentation",
        "icon": "code-slash", "color": "#475569",
        "prompt_key": "dev_sdk",
    },
    {
        "step": 197, "name": "Stress & Load Testing",
        "agent": "loadtest_agent", "phase": "qa",
        "description": "LoadTest creates stress testing suites, concurrent player simulation, and breaking point analysis",
        "icon": "pulse", "color": "#DC2626",
        "prompt_key": "load_testing",
    },
    {
        "step": 198, "name": "Final Polish & Bug Bash",
        "agent": "polish_agent", "phase": "qa",
        "description": "Polish performs final bug bash, edge case testing, UX polish pass, and ship-readiness review",
        "icon": "sparkles", "color": "#F59E0B",
        "prompt_key": "final_polish",
    },
]


# =============================================================================
# ULTRA AGENT PROMPTS (Steps 99-198)
# =============================================================================

def get_ultra_prompts(context: str) -> dict:
    """Returns prompt tuples for 100 ultra-specialized agents (steps 99-198)."""

    prompts = {
        "hair_fur": (
            "You are Strand, Hair & Fur Simulation Engineer. Master of strand-based dynamics, fur rendering, and hair physics.",
            f"""Design the complete hair and fur simulation system:
{context}

Output JSON with code:
{{
  "hair_system_code": "# Strand-based hair simulation\\nclass HairSimulation:\\n    def __init__(self, strand_count=10000):\\n        ...\\n    def simulate(self, dt, wind, gravity):\\n        ...",
  "fur_system_code": "# Fur rendering system\\nclass FurRenderer:\\n    ...",
  "groom_tools_code": "# Hair grooming and styling\\nclass GroomingTools:\\n    ...",
  "hair_types": ["straight", "wavy", "curly", "braided", "ponytail", "short_crop", "long_flowing", "beard", "animal_fur"],
  "physics_features": ["wind_interaction", "collision_with_body", "wetness_clumping", "gravity_sag", "dynamic_cut"],
  "config": {{"max_strands": 100000, "lod_levels": 4, "gpu_simulation": true, "shadow_casting": true, "color_variation": true}}
}}"""
        ),
        "snow_sand": (
            "You are Imprint, Snow & Sand Deformation Engineer. Every footstep leaves a mark in your world.",
            f"""Design the complete snow and sand deformation system:
{context}

Output JSON with code:
{{
  "deformation_code": "# Surface deformation system\\nclass SurfaceDeformation:\\n    def apply_footprint(self, position, weight, shape):\\n        ...\\n    def apply_tire_track(self, start, end, width):\\n        ...",
  "snow_system_code": "# Snow accumulation and melting\\nclass SnowSystem:\\n    ...",
  "sand_system_code": "# Sand dune formation and wind erosion\\nclass SandSystem:\\n    ...",
  "deformation_types": ["footprints", "tire_tracks", "drag_marks", "snow_angels", "crater_impacts", "sled_paths", "animal_tracks"],
  "weather_interaction": ["snow_fill_rate", "wind_erosion", "rain_smoothing", "sun_melting"],
  "config": {{"heightmap_resolution": 1024, "deformation_depth": 0.3, "persistence_time": 300, "gpu_tessellation": true}}
}}"""
        ),
        "mirrors": (
            "You are Mirror, Reflection & Mirror System Engineer. Master of planar reflections, mirror puzzles, and reflection rendering.",
            f"""Design the complete mirror and reflection system:
{context}

Output JSON with code:
{{
  "mirror_system_code": "# Planar mirror rendering\\nclass MirrorSystem:\\n    def render_reflection(self, mirror_plane, camera):\\n        ...",
  "reflection_probe_code": "# Reflection probe management\\nclass ReflectionProbeManager:\\n    ...",
  "mirror_puzzle_code": "# Mirror-based puzzle mechanics\\nclass MirrorPuzzle:\\n    ...",
  "reflection_types": ["planar_mirror", "curved_mirror", "water_reflection", "metallic_reflection", "portal_mirror"],
  "puzzle_mechanics": ["light_beam_redirect", "hidden_message", "reflection_reveal", "mirror_dimension"],
  "config": {{"max_mirror_bounces": 4, "reflection_resolution": 1024, "ssr_fallback": true, "ray_traced_reflections": true}}
}}"""
        ),
        "portals": (
            "You are Warp, Portal & Dimension System Engineer. Creator of seamless portals, non-Euclidean spaces, and dimensional rifts.",
            f"""Design the complete portal and dimension warping system:
{context}

Output JSON with code:
{{
  "portal_system_code": "# Portal rendering and traversal\\nclass PortalSystem:\\n    def create_portal(self, entry, exit, size):\\n        ...\\n    def render_portal_view(self, portal, camera):\\n        ...",
  "dimension_code": "# Dimension switching\\nclass DimensionManager:\\n    ...",
  "non_euclidean_code": "# Non-Euclidean geometry\\nclass NonEuclideanSpace:\\n    ...",
  "portal_types": ["linked_pair", "one_way", "dimensional_rift", "time_portal", "size_changing"],
  "features": ["seamless_traversal", "momentum_preservation", "recursive_rendering", "portal_physics", "cross_dimension_audio"],
  "config": {{"max_recursion_depth": 4, "portal_resolution": 1080, "physics_through_portals": true, "audio_propagation": true}}
}}"""
        ),
        "time_manipulation": (
            "You are Chrono, Time Manipulation Engineer. Master of bullet-time, rewind, and temporal mechanics.",
            f"""Design the complete time manipulation system:
{context}

Output JSON with code:
{{
  "time_system_code": "# Time manipulation engine\\nclass TimeManipulation:\\n    def slow_motion(self, factor, duration):\\n        ...\\n    def rewind(self, seconds):\\n        ...\\n    def freeze_zone(self, position, radius):\\n        ...",
  "recording_code": "# State recording for rewind\\nclass StateRecorder:\\n    ...",
  "time_zone_code": "# Localized time zones\\nclass TimeZoneManager:\\n    ...",
  "time_abilities": ["slow_motion", "full_stop", "rewind", "fast_forward", "time_loop", "age_manipulation", "paradox_split"],
  "config": {{"rewind_buffer_seconds": 30, "slow_mo_min_factor": 0.1, "recording_framerate": 60, "affects_physics": true, "affects_audio_pitch": true}}
}}"""
        ),
        "morality": (
            "You are Judge, Morality & Karma System Designer. Architect of meaningful moral choices and their consequences.",
            f"""Design the complete morality and karma system:
{context}

Output JSON with code:
{{
  "morality_system_code": "# Morality tracking system\\nclass MoralitySystem:\\n    def make_choice(self, choice_id, context):\\n        ...\\n    def get_alignment(self):\\n        ...",
  "consequence_code": "# Choice consequence engine\\nclass ConsequenceEngine:\\n    ...",
  "reputation_impact_code": "# Morality affects world state\\nclass MoralWorldImpact:\\n    ...",
  "alignment_axes": ["good_evil", "law_chaos", "selfish_selfless"],
  "consequence_types": ["immediate", "delayed", "cascading", "permanent", "reversible"],
  "moral_dilemmas": ["trolley_problem", "mercy_vs_justice", "individual_vs_group", "truth_vs_kindness", "duty_vs_desire"],
  "config": {{"alignment_spectrum": 200, "visible_to_player": true, "npc_reactions": true, "story_branches": true, "no_right_answer": true}}
}}"""
        ),
        "survival_needs": (
            "You are Survivor, Survival Needs System Engineer. Creator of hunger, thirst, fatigue, and physiological simulation.",
            f"""Design the complete survival needs system:
{context}

Output JSON with code:
{{
  "needs_system_code": "# Physiological needs manager\\nclass SurvivalNeeds:\\n    def __init__(self):\\n        self.hunger = 100\\n        self.thirst = 100\\n        self.energy = 100\\n    def update(self, dt):\\n        ...",
  "food_system_code": "# Food and nutrition\\nclass NutritionSystem:\\n    ...",
  "shelter_code": "# Shelter and warmth\\nclass ShelterSystem:\\n    ...",
  "needs": ["hunger", "thirst", "energy", "warmth", "rest", "sanity", "hygiene"],
  "effects_when_low": {{"hunger": "damage_over_time", "thirst": "vision_blur", "energy": "slow_movement", "warmth": "hypothermia"}},
  "config": {{"drain_rate_multiplier": 1.0, "hardcore_mode": false, "visual_indicators": true, "auto_eat": false, "death_from_neglect": true}}
}}"""
        ),
        "disease": (
            "You are Plague, Disease & Affliction System Designer. Master of contagion, symptoms, and cure mechanics.",
            f"""Design the complete disease and affliction system:
{context}

Output JSON with code:
{{
  "disease_system_code": "# Disease and infection system\\nclass DiseaseSystem:\\n    def contract_disease(self, entity, disease_id, source):\\n        ...\\n    def update_symptoms(self, entity, dt):\\n        ...",
  "contagion_code": "# Contagion spread simulation\\nclass ContagionSystem:\\n    ...",
  "cure_system_code": "# Cure and treatment system\\nclass CureSystem:\\n    ...",
  "diseases": [
    {{"name": "Swamp Fever", "spread": "mosquito", "symptoms": ["fatigue", "hallucination"], "cure": "herbal_tea", "duration": "48h"}},
    {{"name": "Frost Bite", "spread": "cold_exposure", "symptoms": ["slow_movement", "damage"], "cure": "warmth_potion", "duration": "24h"}}
  ],
  "config": {{"player_to_player_spread": false, "immunity_system": true, "resistance_building": true, "quarantine_zones": true}}
}}"""
        ),
        "durability": (
            "You are Mender, Equipment Durability Engineer. Every weapon breaks. Every armor cracks. Make repair matter.",
            f"""Design the complete equipment durability system:
{context}

Output JSON with code:
{{
  "durability_system_code": "# Equipment durability\\nclass DurabilitySystem:\\n    def apply_wear(self, item, usage_type, intensity):\\n        ...\\n    def repair(self, item, material, skill):\\n        ...",
  "degradation_code": "# Visual degradation stages\\nclass DegradationVisuals:\\n    ...",
  "repair_station_code": "# Repair workbench system\\nclass RepairStation:\\n    ...",
  "durability_stages": ["pristine", "good", "worn", "damaged", "broken"],
  "repair_methods": ["workbench", "field_repair", "npc_blacksmith", "magic_restoration", "material_replacement"],
  "config": {{"max_durability": 1000, "repair_cost_scaling": true, "visual_wear": true, "broken_still_usable": false, "repair_skill_affects_quality": true}}
}}"""
        ),
        "mining": (
            "You are Miner, Mining & Excavation System Designer. Creator of mining mechanics, ore systems, and underground exploration.",
            f"""Design the complete mining and excavation system:
{context}

Output JSON with code:
{{
  "mining_system_code": "# Mining mechanics\\nclass MiningSystem:\\n    def mine_node(self, tool, node, skill_level):\\n        ...\\n    def generate_ore_veins(self, region, seed):\\n        ...",
  "ore_system_code": "# Ore types and rarity\\nclass OreDatabase:\\n    ...",
  "excavation_code": "# Deep excavation and tunneling\\nclass ExcavationSystem:\\n    ...",
  "ores": ["copper", "iron", "silver", "gold", "mithril", "adamantine", "crystal", "void_ore"],
  "tools": ["pickaxe", "drill", "explosive", "magic_extractor"],
  "config": {{"ore_regeneration": true, "cave_in_danger": true, "depth_affects_rarity": true, "mining_skill_system": true}}
}}"""
        ),
        "traps": (
            "You are Trapsmith, Trap & Hazard Designer. Master of devious traps, environmental hazards, and defensive mechanisms.",
            f"""Design the complete trap and hazard system:
{context}

Output JSON with code:
{{
  "trap_system_code": "# Trap placement and triggering\\nclass TrapSystem:\\n    def place_trap(self, trap_type, position, settings):\\n        ...\\n    def trigger(self, trap_id, victim):\\n        ...",
  "hazard_code": "# Environmental hazard system\\nclass HazardManager:\\n    ...",
  "disarm_code": "# Trap detection and disarming\\nclass TrapDisarmSystem:\\n    ...",
  "trap_types": ["bear_trap", "pit_fall", "spike_wall", "poison_dart", "tripwire", "explosive_mine", "net_trap", "freezing_glyph"],
  "hazards": ["lava_floor", "poison_gas", "falling_rocks", "spinning_blade", "electric_fence", "quicksand"],
  "config": {{"player_can_place": true, "enemy_can_place": true, "detection_skill": true, "trap_crafting": true, "friendly_fire": false}}
}}"""
        ),
        "summoning": (
            "You are Conjurer, Summoning & Ritual System Designer. Master of summoning circles, rituals, and conjuration.",
            f"""Design the complete summoning and ritual system:
{context}

Output JSON with code:
{{
  "summoning_code": "# Summoning system\\nclass SummoningSystem:\\n    def begin_ritual(self, ritual_type, components):\\n        ...\\n    def summon_entity(self, entity_type, power_level):\\n        ...",
  "ritual_code": "# Ritual circle mechanics\\nclass RitualCircle:\\n    ...",
  "sacrifice_code": "# Offering and sacrifice system\\nclass SacrificeSystem:\\n    ...",
  "summon_types": ["elemental", "undead", "familiar", "golem", "demon", "angel", "beast", "spirit"],
  "ritual_requirements": ["chalk_circle", "candles", "reagents", "incantation", "moon_phase", "sacrifice"],
  "config": {{"max_summons_active": 3, "summon_duration": 300, "ritual_interruptible": true, "power_scales_with_skill": true}}
}}"""
        ),
        "temperature": (
            "You are Thermal, Temperature & Exposure System Engineer. Creator of temperature zones, hypothermia, and heat mechanics.",
            f"""Design the complete temperature and climate exposure system:
{context}

Output JSON with code:
{{
  "temperature_code": "# Temperature system\\nclass TemperatureSystem:\\n    def get_ambient_temp(self, position, time):\\n        ...\\n    def calculate_player_temp(self, ambient, clothing, shelter):\\n        ...",
  "clothing_warmth_code": "# Clothing insulation values\\nclass ClothingWarmth:\\n    ...",
  "campfire_code": "# Heat sources and campfires\\nclass HeatSourceManager:\\n    ...",
  "temp_effects": {{"freezing": "slow+damage", "cold": "stamina_drain", "comfortable": "normal", "hot": "thirst_drain", "scorching": "damage+dehydration"}},
  "config": {{"temp_range": [-40, 60], "clothing_insulation": true, "altitude_affects_temp": true, "campfire_radius": 10, "hypothermia_stages": 3}}
}}"""
        ),
        "fire_propagation": (
            "You are Inferno, Fire Propagation & Spread Engineer. Fire is alive in your world - it grows, spreads, and consumes.",
            f"""Design the complete fire propagation system:
{context}

Output JSON with code:
{{
  "fire_system_code": "# Fire propagation engine\\nclass FirePropagation:\\n    def ignite(self, position, intensity):\\n        ...\\n    def spread(self, dt, wind_direction):\\n        ...",
  "flammability_code": "# Material flammability system\\nclass FlammabilitySystem:\\n    ...",
  "extinguish_code": "# Fire extinguishing methods\\nclass FireExtinguisher:\\n    ...",
  "fire_types": ["campfire", "torch", "wildfire", "magical_fire", "oil_fire", "electrical_fire"],
  "materials": {{"wood": 0.8, "stone": 0.0, "cloth": 0.9, "metal": 0.0, "grass": 0.7, "oil": 1.0}},
  "config": {{"spread_rate": 1.0, "wind_multiplier": 2.0, "rain_extinguish": true, "fire_damage_per_second": 10, "smoke_system": true}}
}}"""
        ),
        "electricity": (
            "You are Volt, Electricity & Circuit System Engineer. Creator of power grids, circuit puzzles, and electrical hazards.",
            f"""Design the complete electricity and circuit system:
{context}

Output JSON with code:
{{
  "circuit_system_code": "# Electrical circuit system\\nclass CircuitSystem:\\n    def connect(self, source, target, wire):\\n        ...\\n    def calculate_power(self, network):\\n        ...",
  "power_grid_code": "# Power generation and distribution\\nclass PowerGrid:\\n    ...",
  "puzzle_code": "# Circuit-based puzzles\\nclass CircuitPuzzle:\\n    ...",
  "components": ["generator", "wire", "switch", "battery", "transformer", "capacitor", "resistor", "fuse"],
  "power_sources": ["windmill", "solar_panel", "water_wheel", "nuclear", "crystal_reactor", "hamster_wheel"],
  "config": {{"voltage_simulation": true, "overload_damage": true, "water_conducts": true, "metal_conducts": true}}
}}"""
        ),
        "procedural_quests": (
            "You are QuestGen, Procedural Quest Engine Designer. Creator of infinite, unique quests generated on the fly.",
            f"""Design the complete procedural quest generation system:
{context}

Output JSON with code:
{{
  "quest_gen_code": "# Procedural quest generator\\nclass ProceduralQuestGen:\\n    def generate_quest(self, player_level, region, type_hint):\\n        ...\\n    def populate_objectives(self, template, context):\\n        ...",
  "template_code": "# Quest template system\\nclass QuestTemplateEngine:\\n    ...",
  "reward_scaling_code": "# Dynamic reward calculation\\nclass RewardScaler:\\n    ...",
  "quest_templates": ["fetch", "kill", "escort", "defend", "investigate", "craft", "explore", "rescue", "deliver", "compete"],
  "narrative_hooks": ["revenge", "love", "greed", "curiosity", "duty", "survival", "mystery", "redemption"],
  "config": {{"daily_quest_count": 5, "weekly_quest_count": 3, "scaling_with_level": true, "unique_dialogue": true, "chain_quests": true}}
}}"""
        ),
        "merchant_ai": (
            "You are Vendor, Merchant AI & Dynamic Pricing Designer. Creator of smart shopkeepers with real economics.",
            f"""Design the complete merchant AI system:
{context}

Output JSON with code:
{{
  "merchant_ai_code": "# Smart merchant NPC\\nclass MerchantAI:\\n    def calculate_price(self, item, supply, demand, relationship):\\n        ...\\n    def barter(self, player_offer, merchant_threshold):\\n        ...",
  "pricing_code": "# Dynamic pricing engine\\nclass DynamicPricing:\\n    ...",
  "barter_code": "# Bartering minigame\\nclass BarterSystem:\\n    ...",
  "merchant_types": ["general_store", "blacksmith", "alchemist", "rare_goods", "black_market", "traveling_merchant"],
  "pricing_factors": ["base_value", "supply", "demand", "player_reputation", "time_of_day", "region_economy", "haggling_skill"],
  "config": {{"haggling_enabled": true, "price_memory": true, "restock_timer": 24, "stolen_goods_detection": true}}
}}"""
        ),
        "banking": (
            "You are Banker, Banking & Financial System Designer. Creator of banks, loans, investments, and financial services.",
            f"""Design the complete banking and financial system:
{context}

Output JSON with code:
{{
  "banking_code": "# Banking system\\nclass BankingSystem:\\n    def deposit(self, account, amount):\\n        ...\\n    def take_loan(self, account, amount, interest_rate):\\n        ...",
  "investment_code": "# Investment and returns\\nclass InvestmentSystem:\\n    ...",
  "loan_code": "# Loan management\\nclass LoanManager:\\n    ...",
  "services": ["deposit", "withdraw", "transfer", "loan", "investment", "insurance", "vault_storage"],
  "config": {{"interest_rate": 0.05, "loan_max_multiplier": 5, "vault_slots": 100, "cross_city_banking": true}}
}}"""
        ),
        "death_system": (
            "You are Reaper, Death Penalty & Resurrection Designer. Death must have meaning, but never feel unfair.",
            f"""Design the complete death and resurrection system:
{context}

Output JSON with code:
{{
  "death_system_code": "# Death penalty system\\nclass DeathSystem:\\n    def on_player_death(self, player, cause, location):\\n        ...\\n    def respawn(self, player, method):\\n        ...",
  "resurrection_code": "# Resurrection mechanics\\nclass ResurrectionSystem:\\n    ...",
  "corpse_run_code": "# Corpse recovery system\\nclass CorpseRunSystem:\\n    ...",
  "death_penalties": ["xp_loss", "item_drop", "durability_loss", "gold_loss", "corpse_run", "debuff"],
  "resurrection_methods": ["checkpoint", "revival_item", "ally_revive", "shrine", "necromancy", "divine_intervention"],
  "config": {{"penalty_severity": "medium", "corpse_timer_minutes": 30, "xp_loss_percent": 5, "safe_zone_respawn": true}}
}}"""
        ),
        "transformation": (
            "You are Morph, Transformation & Shapeshift Engineer. Creator of werewolf forms, polymorph, and identity-shifting gameplay.",
            f"""Design the complete transformation and shapeshift system:
{context}

Output JSON with code:
{{
  "transform_code": "# Transformation system\\nclass TransformationSystem:\\n    def transform(self, entity, form, duration):\\n        ...\\n    def revert(self, entity):\\n        ...",
  "form_code": "# Alternate form definitions\\nclass FormDatabase:\\n    ...",
  "morph_combat_code": "# Form-specific combat\\nclass MorphCombat:\\n    ...",
  "forms": ["werewolf", "vampire", "dragon", "ghost", "elemental", "beast", "insect_swarm", "shadow_form"],
  "triggers": ["voluntary", "moon_phase", "rage_threshold", "curse", "potion", "equipment"],
  "config": {{"duration_limit": 300, "stat_changes_per_form": true, "unique_abilities_per_form": true, "visual_transformation": true}}
}}"""
        ),
        "mounted_combat": (
            "You are Knight, Mounted Combat & Jousting Engineer. Master of horseback warfare, lance charges, and cavalry tactics.",
            f"""Design the complete mounted combat system:
{context}

Output JSON with code:
{{
  "mounted_combat_code": "# Mounted combat system\\nclass MountedCombat:\\n    def charge_attack(self, rider, mount, target):\\n        ...\\n    def joust(self, rider_a, rider_b):\\n        ...",
  "lance_code": "# Lance mechanics\\nclass LanceSystem:\\n    ...",
  "cavalry_code": "# Cavalry formation combat\\nclass CavalryFormation:\\n    ...",
  "mounted_weapons": ["lance", "sword_mounted", "bow_mounted", "javelin", "war_hammer"],
  "mount_combat_features": ["charge_damage_bonus", "trample", "mounted_archery", "dismount_attack", "joust_tournament"],
  "config": {{"charge_speed_bonus": 2.0, "trample_damage": 50, "mounted_accuracy_penalty": 0.8, "joust_knockout": true}}
}}"""
        ),
        "arena": (
            "You are Gladiator, Arena & Tournament Designer. Creator of competitive arenas, bracket systems, and spectacle fights.",
            f"""Design the complete arena and tournament system:
{context}

Output JSON with code:
{{
  "arena_code": "# Arena management\\nclass ArenaSystem:\\n    def register_fighter(self, player, weight_class):\\n        ...\\n    def start_match(self, fighter_a, fighter_b, rules):\\n        ...",
  "tournament_code": "# Tournament bracket system\\nclass TournamentBracket:\\n    ...",
  "betting_code": "# Spectator betting\\nclass BettingSystem:\\n    ...",
  "arena_types": ["1v1_duel", "team_battle", "free_for_all", "boss_challenge", "gauntlet", "king_of_hill"],
  "tournament_formats": ["single_elimination", "double_elimination", "round_robin", "swiss", "ladder"],
  "config": {{"entry_fee": true, "prize_pool": true, "spectator_seats": 1000, "npc_fighters": true, "weight_classes": 3}}
}}"""
        ),
        "war_table": (
            "You are Commander, War Table & Strategic Planning Designer. Architect of campaign maps and strategic warfare.",
            f"""Design the complete war table and strategic command system:
{context}

Output JSON with code:
{{
  "war_table_code": "# War table strategic view\\nclass WarTable:\\n    def plan_campaign(self, armies, objectives):\\n        ...\\n    def deploy_forces(self, army, region):\\n        ...",
  "campaign_code": "# Strategic campaign layer\\nclass CampaignManager:\\n    ...",
  "intel_code": "# Intelligence and scouting\\nclass IntelligenceSystem:\\n    ...",
  "strategic_actions": ["deploy_army", "scout_region", "build_fortification", "supply_route", "ambush", "retreat", "reinforce"],
  "config": {{"turn_based_strategy": true, "fog_of_war": true, "supply_lines_matter": true, "morale_affects_battle": true}}
}}"""
        ),
        "espionage": (
            "You are Spymaster, Espionage & Intelligence Network Designer. Master of covert operations and spy networks.",
            f"""Design the complete espionage and spy system:
{context}

Output JSON with code:
{{
  "spy_network_code": "# Spy network management\\nclass SpyNetwork:\\n    def recruit_spy(self, target_faction):\\n        ...\\n    def assign_mission(self, spy, mission_type):\\n        ...",
  "covert_ops_code": "# Covert operations\\nclass CovertOps:\\n    ...",
  "intel_gathering_code": "# Intelligence gathering\\nclass IntelGathering:\\n    ...",
  "spy_missions": ["infiltrate", "sabotage", "assassinate", "steal_plans", "spread_propaganda", "counter_espionage", "recruit_double_agent"],
  "config": {{"spy_detection_chance": 0.1, "mission_success_base": 0.6, "double_agent_risk": true, "intel_decay_time": "48h"}}
}}"""
        ),
        "justice": (
            "You are Magistrate, Trial & Justice System Designer. Creator of courts, evidence, and legal proceedings.",
            f"""Design the complete justice and trial system:
{context}

Output JSON with code:
{{
  "trial_code": "# Court trial system\\nclass TrialSystem:\\n    def begin_trial(self, accused, crime, evidence):\\n        ...\\n    def present_evidence(self, evidence_item):\\n        ...",
  "evidence_code": "# Evidence collection and presentation\\nclass EvidenceSystem:\\n    ...",
  "verdict_code": "# Verdict and sentencing\\nclass VerdictSystem:\\n    ...",
  "trial_phases": ["accusation", "evidence_presentation", "witness_testimony", "cross_examination", "deliberation", "verdict"],
  "punishments": ["fine", "jail", "community_service", "exile", "execution", "pardoned"],
  "config": {{"jury_system": true, "player_can_be_lawyer": true, "bribery_possible": true, "appeal_process": true}}
}}"""
        ),
        "supply_chain": (
            "You are Quartermaster, Supply Chain & Logistics Engineer. Master of resource flow and strategic logistics.",
            f"""Design the complete supply chain system:
{context}

Output JSON with code:
{{
  "supply_code": "# Supply chain management\\nclass SupplyChainManager:\\n    def create_route(self, source, destination, goods):\\n        ...\\n    def calculate_throughput(self, route):\\n        ...",
  "warehouse_code": "# Warehouse storage\\nclass WarehouseSystem:\\n    ...",
  "delivery_code": "# Delivery and logistics\\nclass DeliverySystem:\\n    ...",
  "supply_types": ["food", "weapons", "building_materials", "medicine", "luxury_goods", "fuel"],
  "config": {{"route_optimization": true, "bandit_raids_on_supply": true, "weather_delays": true, "supply_affects_morale": true}}
}}"""
        ),
        "tavern": (
            "You are Innkeeper, Tavern & Social Hub Designer. Creator of lively gathering spots, mini-games, and ambient life.",
            f"""Design the complete tavern and social hub system:
{context}

Output JSON with code:
{{
  "tavern_code": "# Tavern hub system\\nclass TavernSystem:\\n    def enter_tavern(self, player, tavern_id):\\n        ...\\n    def order_drink(self, drink_type):\\n        ...",
  "minigame_code": "# Tavern mini-games\\nclass TavernMinigames:\\n    ...",
  "ambient_code": "# Ambient NPC behavior\\nclass TavernAmbience:\\n    ...",
  "activities": ["drink_ordering", "arm_wrestling", "dice_games", "card_games", "dart_throwing", "storytelling", "bar_fight", "music_requests"],
  "config": {{"npc_patrons": 15, "drink_effects": true, "rumor_system": true, "bounty_board_in_tavern": true, "bard_performances": true}}
}}"""
        ),
        "construction": (
            "You are Architect, Bridge & Structural Engineering Designer. Creator of physics-based construction and building puzzles.",
            f"""Design the complete construction engineering system:
{context}

Output JSON with code:
{{
  "construction_code": "# Structural building system\\nclass ConstructionSystem:\\n    def place_beam(self, start, end, material):\\n        ...\\n    def stress_test(self, structure):\\n        ...",
  "physics_code": "# Structural physics\\nclass StructuralPhysics:\\n    ...",
  "bridge_code": "# Bridge building mode\\nclass BridgeBuilder:\\n    ...",
  "materials": ["wood", "stone", "steel", "rope", "concrete"],
  "structures": ["bridge", "tower", "wall", "ramp", "platform", "crane", "scaffold"],
  "config": {{"physics_simulation": true, "weight_limits": true, "material_costs": true, "collapse_on_failure": true}}
}}"""
        ),
        "terraforming": (
            "You are Shaper, Terraforming & World Shaping Engineer. The world bends to your players' will.",
            f"""Design the complete terraforming system:
{context}

Output JSON with code:
{{
  "terraform_code": "# Terraforming engine\\nclass TerraformingSystem:\\n    def raise_terrain(self, position, radius, height):\\n        ...\\n    def create_river(self, path_points):\\n        ...",
  "biome_code": "# Biome conversion\\nclass BiomeConverter:\\n    ...",
  "persistent_code": "# Persistent world modification\\nclass PersistentTerrain:\\n    ...",
  "tools": ["raise_lower", "flatten", "smooth", "paint_biome", "create_water", "plant_forest", "create_mountain", "carve_canyon"],
  "config": {{"max_terraform_radius": 50, "multiplayer_sync": true, "undo_support": true, "resource_cost": true}}
}}"""
        ),
        "dreams": (
            "You are Dreamweaver, Dream & Vision Sequence Designer. Creator of surreal dream levels and subconscious narrative.",
            f"""Design the complete dream and vision system:
{context}

Output JSON with code:
{{
  "dream_system_code": "# Dream sequence engine\\nclass DreamSystem:\\n    def enter_dream(self, player, dream_type):\\n        ...\\n    def apply_dream_rules(self, physics_override):\\n        ...",
  "surreal_code": "# Surreal environment generation\\nclass SurrealEnvironment:\\n    ...",
  "nightmare_code": "# Nightmare and horror dreams\\nclass NightmareSystem:\\n    ...",
  "dream_types": ["prophetic_vision", "memory_replay", "nightmare", "lucid_dream", "spirit_walk", "shared_dream"],
  "surreal_effects": ["gravity_shift", "scale_change", "color_shift", "impossible_geometry", "time_distortion"],
  "config": {{"dream_duration": 120, "death_in_dream_consequence": "wake_up", "loot_from_dreams": true, "recurring_dreams": true}}
}}"""
        ),
        "horde_mode": (
            "You are Horde, Wave Survival Mode Designer. Creator of escalating waves, supply drops, and last-stand gameplay.",
            f"""Design the complete horde and wave survival system:
{context}

Output JSON with code:
{{
  "horde_code": "# Horde mode engine\\nclass HordeMode:\\n    def start_wave(self, wave_number):\\n        ...\\n    def spawn_enemies(self, wave_config):\\n        ...\\n    def drop_supplies(self):\\n        ...",
  "wave_code": "# Wave configuration\\nclass WaveDesigner:\\n    ...",
  "fortify_code": "# Between-wave fortification\\nclass FortificationPhase:\\n    ...",
  "wave_types": ["standard", "elite_rush", "boss_wave", "swarm", "stealth_wave", "siege_wave"],
  "config": {{"max_waves": "infinite", "difficulty_scaling": 1.15, "supply_drops_per_wave": 2, "co_op_players": 4, "leaderboard": true}}
}}"""
        ),
        "card_game": (
            "You are Dealer, Card & Deck Building System Designer. Creator of collectible cards, deck strategy, and card combat.",
            f"""Design the complete card and deck building system:
{context}

Output JSON with code:
{{
  "card_system_code": "# Card game engine\\nclass CardGameEngine:\\n    def draw_card(self, deck):\\n        ...\\n    def play_card(self, card, target):\\n        ...\\n    def resolve_effects(self):\\n        ...",
  "deck_builder_code": "# Deck building UI\\nclass DeckBuilder:\\n    ...",
  "collection_code": "# Card collection management\\nclass CardCollection:\\n    ...",
  "card_types": ["creature", "spell", "trap", "equipment", "field", "legendary"],
  "rarity": {{"common": 50, "uncommon": 30, "rare": 15, "epic": 4, "legendary": 1}},
  "config": {{"deck_size_min": 30, "deck_size_max": 60, "hand_size": 7, "mana_system": true, "trading_enabled": true}}
}}"""
        ),
        "guild_hall": (
            "You are Guildmaster, Guild Hall & Headquarters Designer. Creator of shared spaces, upgrades, and clan progression.",
            f"""Design the complete guild hall system:
{context}

Output JSON with code:
{{
  "guild_hall_code": "# Guild headquarters system\\nclass GuildHall:\\n    def upgrade_room(self, room_type, level):\\n        ...\\n    def unlock_feature(self, feature_id):\\n        ...",
  "guild_progression_code": "# Guild level and XP\\nclass GuildProgression:\\n    ...",
  "shared_storage_code": "# Shared guild storage\\nclass GuildStorage:\\n    ...",
  "rooms": ["meeting_hall", "armory", "treasury", "training_grounds", "library", "war_room", "garden", "trophy_room"],
  "guild_perks": ["shared_xp_bonus", "fast_travel_to_hall", "guild_shop_discount", "exclusive_quests", "guild_mount"],
  "config": {{"max_guild_level": 50, "upgrade_costs": "scaling", "max_members": 100, "guild_vs_guild_wars": true}}
}}"""
        ),
        "territory": (
            "You are Overlord, Territory Control & Conquest Designer. Master of zone capture, influence maps, and dominion warfare.",
            f"""Design the complete territory control system:
{context}

Output JSON with code:
{{
  "territory_code": "# Territory control system\\nclass TerritoryControl:\\n    def capture_zone(self, faction, zone_id):\\n        ...\\n    def calculate_influence(self, zone_id):\\n        ...",
  "influence_code": "# Influence map system\\nclass InfluenceMap:\\n    ...",
  "siege_territory_code": "# Territory siege mechanics\\nclass TerritorySiege:\\n    ...",
  "zone_types": ["village", "city", "fortress", "resource_node", "strategic_pass", "port"],
  "config": {{"capture_time_minutes": 15, "defender_advantage": 1.5, "resource_generation": true, "npc_defenders": true}}
}}"""
        ),
        "caravan": (
            "You are Caravan, Trade Convoy & Escort Designer. Creator of trade convoys, escort missions, and caravan management.",
            f"""Design the complete caravan and trade convoy system:
{context}

Output JSON with code:
{{
  "caravan_code": "# Caravan management\\nclass CaravanSystem:\\n    def create_caravan(self, goods, route):\\n        ...\\n    def escort_mission(self, caravan_id):\\n        ...",
  "route_code": "# Trade route planning\\nclass RouteManager:\\n    ...",
  "encounter_code": "# Random caravan encounters\\nclass CaravanEncounters:\\n    ...",
  "caravan_types": ["merchant_wagon", "military_supply", "refugee_convoy", "treasure_transport", "livestock_drive"],
  "encounters": ["bandit_ambush", "weather_delay", "broken_wheel", "toll_gate", "friendly_merchant", "monster_attack"],
  "config": {{"max_wagons": 5, "guard_hiring": true, "route_danger_levels": true, "profit_on_arrival": true}}
}}"""
        ),
        "museum": (
            "You are Curator, Museum & Collection Display Designer. Creator of trophy rooms, collectible displays, and achievement showcases.",
            f"""Design the complete museum and collection display system:
{context}

Output JSON with code:
{{
  "museum_code": "# Museum display system\\nclass MuseumSystem:\\n    def place_artifact(self, display_case, item):\\n        ...\\n    def get_completion(self):\\n        ...",
  "trophy_code": "# Trophy room\\nclass TrophyRoom:\\n    ...",
  "diorama_code": "# Scene diorama builder\\nclass DioramaBuilder:\\n    ...",
  "display_types": ["weapon_rack", "armor_stand", "display_case", "wall_mount", "pedestal", "diorama", "gallery_wall"],
  "config": {{"visitor_npcs": true, "completion_rewards": true, "museum_tours": true, "interactive_displays": true}}
}}"""
        ),
        "theater": (
            "You are Impresario, Theater & Live Performance Designer. Creator of in-game theaters, performances, and audience systems.",
            f"""Design the complete theater and performance system:
{context}

Output JSON with code:
{{
  "theater_code": "# Theater performance system\\nclass TheaterSystem:\\n    def start_performance(self, script, actors):\\n        ...\\n    def audience_react(self, quality_score):\\n        ...",
  "script_code": "# Performance scripting\\nclass PerformanceScript:\\n    ...",
  "audience_code": "# Audience simulation\\nclass AudienceSystem:\\n    ...",
  "performance_types": ["play", "musical", "puppet_show", "magic_act", "comedy", "gladiator_show", "concert"],
  "config": {{"player_can_perform": true, "audience_npc_count": 50, "reputation_from_shows": true, "ticket_sales": true}}
}}"""
        ),
        "news_system": (
            "You are Chronicler, In-Game News & World Chronicle Designer. Creator of dynamic news that reflects player actions.",
            f"""Design the complete in-game news system:
{context}

Output JSON with code:
{{
  "news_system_code": "# Dynamic news generator\\nclass NewsSystem:\\n    def generate_headline(self, event_type, context):\\n        ...\\n    def publish_edition(self):\\n        ...",
  "newspaper_code": "# Newspaper UI\\nclass NewspaperRenderer:\\n    ...",
  "event_tracker_code": "# World event tracking for news\\nclass EventTracker:\\n    ...",
  "news_categories": ["world_events", "player_achievements", "faction_wars", "economy_reports", "weather_forecasts", "gossip", "obituaries"],
  "config": {{"daily_edition": true, "player_actions_in_news": true, "npc_gossip_system": true, "propaganda_system": true}}
}}"""
        ),
        "mail_system": (
            "You are Postmaster, Mail & Courier System Designer. Creator of player mail, item attachments, and courier delivery quests.",
            f"""Design the complete mail and courier system:
{context}

Output JSON with code:
{{
  "mail_code": "# Player mail system\\nclass MailSystem:\\n    def send_mail(self, sender, recipient, message, attachments):\\n        ...\\n    def collect_mail(self, player):\\n        ...",
  "courier_code": "# NPC courier delivery\\nclass CourierSystem:\\n    ...",
  "attachment_code": "# Item and gold attachments\\nclass MailAttachments:\\n    ...",
  "mail_types": ["player_to_player", "npc_letter", "quest_mail", "system_notification", "auction_result", "guild_announcement"],
  "config": {{"delivery_delay_minutes": 5, "max_attachments": 10, "postage_cost": true, "cross_server_mail": true}}
}}"""
        ),
        "astrology": (
            "You are Astronomer, Astrology & Celestial Mechanics Designer. Creator of star maps, constellations, and celestial gameplay.",
            f"""Design the complete astrology and celestial system:
{context}

Output JSON with code:
{{
  "astrology_code": "# Astrology system\\nclass AstrologySystem:\\n    def read_stars(self, date, time, position):\\n        ...\\n    def get_horoscope_buff(self, zodiac_sign):\\n        ...",
  "constellation_code": "# Constellation discovery\\nclass ConstellationSystem:\\n    ...",
  "celestial_code": "# Celestial body simulation\\nclass CelestialSimulation:\\n    ...",
  "zodiac_signs": ["aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces"],
  "celestial_events": ["eclipse", "meteor_shower", "blood_moon", "planetary_alignment", "supernova", "comet"],
  "config": {{"buffs_from_zodiac": true, "constellation_puzzles": true, "navigation_by_stars": true, "rare_celestial_events": true}}
}}"""
        ),
        "wind_physics": (
            "You are Zephyr, Wind & Air Current Physics Engineer. Creator of wind systems, air currents, and aerodynamic interactions.",
            f"""Design the complete wind and air physics system:
{context}

Output JSON with code:
{{
  "wind_system_code": "# Wind simulation\\nclass WindSystem:\\n    def get_wind_at(self, position, altitude):\\n        ...\\n    def apply_wind_force(self, entity, wind_vector):\\n        ...",
  "air_current_code": "# Air current and updraft system\\nclass AirCurrentSystem:\\n    ...",
  "wind_effects_code": "# Wind effects on gameplay\\nclass WindEffects:\\n    ...",
  "wind_types": ["calm", "breeze", "gust", "gale", "hurricane", "tornado", "updraft", "downdraft"],
  "affected_systems": ["projectile_trajectory", "gliding", "sailing", "cloth_simulation", "particle_direction", "sound_propagation"],
  "config": {{"global_wind_direction": true, "local_wind_zones": true, "altitude_affects_wind": true, "wind_changes_over_time": true}}
}}"""
        ),
        "llm_dialogue": (
            "You are Babel, LLM-Powered NPC Dialogue Engineer. Creator of AI-driven conversations that feel truly alive.",
            f"""Design the complete LLM-powered NPC dialogue system:
{context}

Output JSON with code:
{{
  "llm_dialogue_code": "# LLM NPC conversation engine\\nclass LLMDialogueSystem:\\n    def start_conversation(self, npc, player_context):\\n        ...\\n    def generate_response(self, npc_personality, player_input, memory):\\n        ...",
  "memory_code": "# NPC conversation memory\\nclass NPCMemory:\\n    ...",
  "personality_code": "# NPC personality system\\nclass PersonalityEngine:\\n    ...",
  "guardrail_code": "# Content safety and lore consistency\\nclass DialogueGuardrails:\\n    ...",
  "npc_traits": ["friendly", "suspicious", "scholarly", "grumpy", "flirtatious", "mysterious", "comedic"],
  "config": {{"context_window": 20, "memory_persistence": true, "lore_constrained": true, "safety_filters": true, "fallback_to_scripted": true}}
}}"""
        ),
        "vr_support": (
            "You are Reality, VR & Extended Reality Support Engineer. Creator of immersive VR, AR, and mixed reality experiences.",
            f"""Design the complete VR and extended reality support:
{context}

Output JSON with code:
{{
  "vr_system_code": "# VR integration layer\\nclass VRSystem:\\n    def setup_vr(self, headset_type):\\n        ...\\n    def handle_controller_input(self, hand, action):\\n        ...",
  "room_scale_code": "# Room-scale interaction\\nclass RoomScaleSystem:\\n    ...",
  "comfort_code": "# VR comfort settings\\nclass VRComfort:\\n    ...",
  "vr_platforms": ["Meta_Quest", "SteamVR", "PlayStation_VR2", "Apple_Vision_Pro"],
  "interaction_types": ["grab", "throw", "push", "pull", "climb", "gesture", "point", "teleport"],
  "comfort_options": ["teleport_locomotion", "snap_turning", "vignette", "seated_mode", "height_adjustment"],
  "config": {{"target_fps": 90, "reprojection": true, "hand_tracking": true, "cross_play_with_flat": true}}
}}"""
        ),
        "haptics": (
            "You are Tactile, Haptic Feedback Designer. Master of DualSense triggers, HD rumble, and tactile game feel.",
            f"""Design the complete haptic feedback system:
{context}

Output JSON with code:
{{
  "haptic_code": "# Haptic feedback engine\\nclass HapticSystem:\\n    def trigger_haptic(self, pattern, intensity, duration):\\n        ...\\n    def adaptive_trigger(self, trigger, resistance_curve):\\n        ...",
  "pattern_code": "# Haptic pattern library\\nclass HapticPatterns:\\n    ...",
  "adaptive_trigger_code": "# DualSense adaptive trigger profiles\\nclass AdaptiveTriggers:\\n    ...",
  "haptic_events": ["footstep", "weapon_fire", "explosion", "heartbeat", "rain", "engine_rumble", "sword_clash", "magic_charge"],
  "trigger_profiles": ["bow_draw", "gun_trigger", "car_brake", "shield_block", "lockpick_tension"],
  "config": {{"intensity_scale": 1.0, "platform_specific": true, "user_adjustable": true, "hd_rumble_support": true}}
}}"""
        ),
        "flashbacks": (
            "You are Memory, Flashback & Memory Replay Designer. Creator of playable memories, unreliable narrators, and past reveals.",
            f"""Design the complete flashback and memory system:
{context}

Output JSON with code:
{{
  "flashback_code": "# Flashback sequence system\\nclass FlashbackSystem:\\n    def trigger_flashback(self, memory_id, player):\\n        ...\\n    def apply_visual_filter(self, filter_type):\\n        ...",
  "memory_code": "# Memory collection and replay\\nclass MemoryCollection:\\n    ...",
  "unreliable_code": "# Unreliable narrator mechanics\\nclass UnreliableNarrator:\\n    ...",
  "flashback_types": ["playable_memory", "cinematic_memory", "fragmented_recall", "shared_memory", "false_memory"],
  "visual_filters": ["sepia", "desaturated", "film_grain", "vignette", "dream_blur", "glitch"],
  "config": {{"player_controlled": true, "collectible_memories": true, "affects_story": true, "multiple_perspectives": true}}
}}"""
        ),
        "ghost_mechanics": (
            "You are Phantom, Ghost & Spectral Mechanics Engineer. Creator of death echoes, spirit realms, and spectral gameplay.",
            f"""Design the complete ghost and spectral system:
{context}

Output JSON with code:
{{
  "ghost_code": "# Ghost mode gameplay\\nclass GhostSystem:\\n    def enter_ghost_mode(self, player):\\n        ...\\n    def phase_through_wall(self, player, wall):\\n        ...",
  "spirit_realm_code": "# Spirit realm parallel world\\nclass SpiritRealm:\\n    ...",
  "possession_code": "# Possession mechanics\\nclass PossessionSystem:\\n    ...",
  "ghost_abilities": ["phase_through", "invisibility", "possession", "poltergeist", "spirit_sight", "soul_anchor"],
  "spirit_realm_features": ["parallel_world", "hidden_paths", "spirit_npcs", "soul_fragments", "realm_shift"],
  "config": {{"ghost_mode_timer": 60, "interact_with_living": false, "visible_to_sensitives": true, "collect_soul_energy": true}}
}}"""
        ),
        "portraits": (
            "You are Portraitist, Procedural Portrait Generation Designer. Creator of unique NPC faces and character portraits.",
            f"""Design the complete procedural portrait system:
{context}

Output JSON with code:
{{
  "portrait_gen_code": "# Procedural portrait generator\\nclass PortraitGenerator:\\n    def generate_face(self, race, gender, age, traits):\\n        ...\\n    def create_mugshot(self, npc_data):\\n        ...",
  "feature_code": "# Facial feature randomization\\nclass FacialFeatures:\\n    ...",
  "style_code": "# Art style application\\nclass PortraitStyle:\\n    ...",
  "facial_features": ["face_shape", "eyes", "nose", "mouth", "ears", "hair", "facial_hair", "scars", "markings", "accessories"],
  "art_styles": ["realistic", "painterly", "anime", "pixel", "comic_book", "oil_painting"],
  "config": {{"unique_per_npc": true, "seed_based": true, "race_specific_features": true, "aging_system": true}}
}}"""
        ),
        "voice_synth": (
            "You are Vocalist, Voice Synthesis Pipeline Designer. Creator of TTS voice acting and procedural voice lines.",
            f"""Design the complete voice synthesis system:
{context}

Output JSON with code:
{{
  "voice_synth_code": "# Voice synthesis engine\\nclass VoiceSynthesis:\\n    def generate_speech(self, text, voice_profile, emotion):\\n        ...\\n    def generate_bark(self, context, npc_type):\\n        ...",
  "voice_profile_code": "# Voice profile management\\nclass VoiceProfileManager:\\n    ...",
  "bark_system_code": "# Combat and ambient barks\\nclass BarkSystem:\\n    ...",
  "voice_traits": ["pitch", "speed", "accent", "raspiness", "warmth", "age"],
  "bark_categories": ["combat", "pain", "greeting", "farewell", "ambient", "alert", "dying", "victory"],
  "config": {{"tts_engine": "neural", "real_time_generation": false, "cache_generated": true, "lip_sync_output": true}}
}}"""
        ),
        "crowd_sim": (
            "You are Crowd, Crowd Simulation & Stadium Engineer. Creator of thousands of background NPCs and audience simulation.",
            f"""Design the complete crowd simulation system:
{context}

Output JSON with code:
{{
  "crowd_code": "# Crowd simulation engine\\nclass CrowdSimulation:\\n    def spawn_crowd(self, area, density, behavior):\\n        ...\\n    def update_crowd(self, dt):\\n        ...",
  "stadium_code": "# Stadium audience system\\nclass StadiumAudience:\\n    ...",
  "flow_code": "# Crowd flow and panic\\nclass CrowdFlow:\\n    ...",
  "crowd_behaviors": ["walking", "standing", "cheering", "fleeing", "protesting", "celebrating", "queuing"],
  "crowd_types": ["city_pedestrians", "market_shoppers", "stadium_fans", "festival_goers", "riot_mob", "refugee_column"],
  "config": {{"max_crowd_agents": 5000, "lod_levels": 3, "gpu_instancing": true, "collision_avoidance": true}}
}}"""
        ),
        "market_economy": (
            "You are Economist, Dynamic Market Economy AI Designer. Creator of living economies with supply, demand, and crashes.",
            f"""Design the complete dynamic market economy system:
{context}

Output JSON with code:
{{
  "economy_ai_code": "# Dynamic economy simulation\\nclass DynamicEconomy:\\n    def simulate_tick(self, dt):\\n        ...\\n    def calculate_prices(self, goods, region):\\n        ...",
  "supply_demand_code": "# Supply and demand model\\nclass SupplyDemandModel:\\n    ...",
  "market_events_code": "# Economic events\\nclass MarketEvents:\\n    ...",
  "economic_events": ["boom", "recession", "inflation", "shortage", "surplus", "trade_embargo", "gold_rush", "market_crash"],
  "goods_categories": ["raw_materials", "crafted_goods", "luxury", "food", "weapons", "magic_items"],
  "config": {{"simulation_tick_rate": "hourly", "player_impact_on_economy": true, "regional_variation": true, "economic_cycles": true}}
}}"""
        ),
        "armor_layers": (
            "You are Armorer, Layered Armor & Damage Protection Designer. Creator of realistic armor penetration and weak points.",
            f"""Design the complete layered armor system:
{context}

Output JSON with code:
{{
  "armor_layer_code": "# Layered armor system\\nclass LayeredArmor:\\n    def calculate_damage_through(self, incoming_damage, hit_zone, projectile_type):\\n        ...\\n    def get_weak_points(self, armor_set):\\n        ...",
  "penetration_code": "# Armor penetration physics\\nclass PenetrationSystem:\\n    ...",
  "damage_zone_code": "# Body damage zones\\nclass DamageZoneSystem:\\n    ...",
  "armor_layers": ["padding", "chainmail", "plate", "magical_ward", "energy_shield"],
  "damage_zones": ["head", "torso", "arms", "legs", "back", "joints"],
  "config": {{"realistic_penetration": true, "armor_degradation": true, "weak_point_crits": true, "visual_damage_on_armor": true}}
}}"""
        ),
        "climbing": (
            "You are Climber, Climbing & Mountaineering System Designer. Master of vertical exploration and stamina-based climbing.",
            f"""Design the complete climbing and mountaineering system:
{context}

Output JSON with code:
{{
  "climbing_code": "# Climbing mechanics\\nclass ClimbingSystem:\\n    def start_climb(self, player, surface):\\n        ...\\n    def check_grip(self, player, hold_type):\\n        ...",
  "stamina_code": "# Climbing stamina\\nclass ClimbingStamina:\\n    ...",
  "tools_code": "# Climbing tools (ice picks, ropes)\\nclass ClimbingTools:\\n    ...",
  "surface_types": ["rock_wall", "ice_wall", "tree", "building", "cliff", "cave_ceiling", "vine_wall"],
  "climbing_tools": ["bare_hands", "climbing_gloves", "ice_pick", "grappling_hook", "pitons", "rope"],
  "config": {{"stamina_drain_rate": 5, "rain_makes_slippery": true, "fall_damage": true, "rest_ledges": true, "dynamic_handholds": true}}
}}"""
        ),
        "caves": (
            "You are Spelunker, Cave & Tunnel Generation Engineer. Creator of vast underground networks and spelunking gameplay.",
            f"""Design the complete cave and tunnel generation system:
{context}

Output JSON with code:
{{
  "cave_gen_code": "# Procedural cave generator\\nclass CaveGenerator:\\n    def generate_cave_network(self, seed, depth, complexity):\\n        ...\\n    def populate_cave(self, cave, biome):\\n        ...",
  "underground_code": "# Underground biome system\\nclass UndergroundBiomes:\\n    ...",
  "cave_hazard_code": "# Cave hazards and collapses\\nclass CaveHazards:\\n    ...",
  "cave_biomes": ["crystal_cavern", "lava_tube", "ice_cave", "fungal_grotto", "flooded_cave", "ancient_ruins", "spider_nest"],
  "hazards": ["cave_in", "gas_pocket", "underground_river", "lava_flow", "darkness", "bats"],
  "config": {{"max_depth_levels": 10, "procedural_generation": true, "light_mechanics": true, "cave_in_risk": true}}
}}"""
        ),
        "cosmic_events": (
            "You are Cosmos, Cosmic Events & Phenomena Designer. Creator of eclipses, meteor showers, and cosmic gameplay events.",
            f"""Design the complete cosmic events system:
{context}

Output JSON with code:
{{
  "cosmic_code": "# Cosmic event system\\nclass CosmicEventSystem:\\n    def schedule_event(self, event_type, timing):\\n        ...\\n    def trigger_cosmic_event(self, event_id):\\n        ...",
  "eclipse_code": "# Eclipse simulation\\nclass EclipseSystem:\\n    ...",
  "meteor_code": "# Meteor shower and impacts\\nclass MeteorSystem:\\n    ...",
  "events": ["solar_eclipse", "lunar_eclipse", "meteor_shower", "comet_pass", "aurora", "blood_moon", "planetary_alignment", "supernova_visible"],
  "gameplay_effects": ["buff_magic", "spawn_rare_enemies", "reveal_hidden_paths", "empower_artifacts", "open_portals"],
  "config": {{"frequency": "rare", "warning_system": true, "unique_rewards": true, "affects_gameplay": true}}
}}"""
        ),
        "mythology": (
            "You are Pantheon, Mythology & Deity System Designer. Creator of god systems, divine blessings, and temple worship.",
            f"""Design the complete mythology and deity system:
{context}

Output JSON with code:
{{
  "deity_code": "# Deity and worship system\\nclass DeitySystem:\\n    def pray(self, player, deity, offering):\\n        ...\\n    def grant_blessing(self, deity, devotion_level):\\n        ...",
  "temple_code": "# Temple and shrine system\\nclass TempleSystem:\\n    ...",
  "blessing_code": "# Divine blessing mechanics\\nclass BlessingSystem:\\n    ...",
  "deities": [
    {{"name": "Solara", "domain": "sun_light", "blessing": "fire_resistance", "alignment": "good"}},
    {{"name": "Nyx", "domain": "shadow_death", "blessing": "stealth_bonus", "alignment": "neutral"}},
    {{"name": "Thalor", "domain": "sea_storms", "blessing": "water_breathing", "alignment": "chaotic"}}
  ],
  "config": {{"multi_deity_worship": false, "devotion_decay": true, "divine_intervention": true, "deity_quests": true}}
}}"""
        ),
        "calendar": (
            "You are Calendar, Festival & Calendar System Designer. Creator of in-game time, holidays, and seasonal celebrations.",
            f"""Design the complete calendar and festival system:
{context}

Output JSON with code:
{{
  "calendar_code": "# In-game calendar\\nclass CalendarSystem:\\n    def get_current_date(self):\\n        ...\\n    def check_holiday(self, date):\\n        ...",
  "festival_code": "# Festival event system\\nclass FestivalManager:\\n    ...",
  "season_code": "# Seasonal gameplay changes\\nclass SeasonalChanges:\\n    ...",
  "festivals": [
    {{"name": "Harvest Moon Feast", "month": 9, "duration": 3, "activities": ["crop_contest", "feast", "fireworks"]}},
    {{"name": "Frost Solstice", "month": 12, "duration": 7, "activities": ["gift_giving", "ice_sculpture", "yule_log"]}}
  ],
  "config": {{"days_per_month": 30, "months_per_year": 12, "real_time_ratio": "1h=1day", "npc_celebrate": true}}
}}"""
        ),
        "dynasty": (
            "You are Dynasty, Inheritance & Bloodline System Designer. Creator of multi-generational play and legacy progression.",
            f"""Design the complete dynasty and inheritance system:
{context}

Output JSON with code:
{{
  "dynasty_code": "# Dynasty management\\nclass DynastySystem:\\n    def create_heir(self, parent_a, parent_b):\\n        ...\\n    def inherit_estate(self, heir, predecessor):\\n        ...",
  "bloodline_code": "# Bloodline traits\\nclass BloodlineTraits:\\n    ...",
  "succession_code": "# Succession laws\\nclass SuccessionLaws:\\n    ...",
  "inheritance_types": ["primogeniture", "elective", "gavelkind", "matrilineal", "merit_based"],
  "legacy_bonuses": ["ancestral_weapon", "family_crest", "inherited_skills", "estate_upgrades", "reputation_carryover"],
  "config": {{"max_generations": 10, "trait_inheritance": true, "inbreeding_penalties": true, "dynasty_prestige": true}}
}}"""
        ),
        "permadeath": (
            "You are Ironman, Permadeath & Hardcore Mode Designer. Death is final. Every decision matters. No save-scumming.",
            f"""Design the complete permadeath and ironman system:
{context}

Output JSON with code:
{{
  "permadeath_code": "# Permadeath system\\nclass PermadeathSystem:\\n    def on_permanent_death(self, player):\\n        ...\\n    def calculate_legacy_bonus(self, dead_character):\\n        ...",
  "ironman_code": "# Ironman save system\\nclass IronmanSave:\\n    ...",
  "legacy_code": "# Death legacy rewards\\nclass DeathLegacy:\\n    ...",
  "death_consequences": ["character_deleted", "legacy_bonus_to_next", "memorial_stone", "ghost_npc", "inheritance"],
  "difficulty_modes": ["standard", "hardcore", "ironman", "nuzlocke", "speed_death"],
  "config": {{"auto_save_only": true, "no_manual_save": true, "death_is_final": true, "legacy_xp_bonus": 0.1, "memorial_system": true}}
}}"""
        ),
        "dlc_system": (
            "You are Expansion, DLC & Content Architecture Engineer. Creator of modular expansion systems and content delivery.",
            f"""Design the complete DLC and expansion architecture:
{context}

Output JSON with code:
{{
  "dlc_code": "# DLC management system\\nclass DLCManager:\\n    def load_expansion(self, dlc_id):\\n        ...\\n    def check_entitlement(self, player, dlc_id):\\n        ...",
  "content_code": "# Content pack system\\nclass ContentPackSystem:\\n    ...",
  "season_pass_code": "# Season pass management\\nclass SeasonPassManager:\\n    ...",
  "dlc_types": ["story_expansion", "map_pack", "cosmetic_pack", "character_dlc", "gameplay_mode", "soundtrack"],
  "config": {{"hot_loadable": true, "backwards_compatible": true, "trial_available": true, "cross_platform_entitlement": true}}
}}"""
        ),
        "replay_analysis": (
            "You are Analyst, Replay Analysis & Post-Game Breakdown Designer. Creator of match stats, heat maps, and highlight reels.",
            f"""Design the complete replay analysis system:
{context}

Output JSON with code:
{{
  "analysis_code": "# Post-game analysis engine\\nclass ReplayAnalysis:\\n    def analyze_match(self, replay_data):\\n        ...\\n    def generate_highlights(self, replay_data, criteria):\\n        ...",
  "heatmap_code": "# Player movement heatmaps\\nclass MatchHeatmap:\\n    ...",
  "stats_code": "# Detailed match statistics\\nclass MatchStats:\\n    ...",
  "metrics": ["kills", "deaths", "damage_dealt", "distance_traveled", "accuracy", "objectives_completed", "time_alive"],
  "config": {{"auto_highlight_detection": true, "share_replays": true, "coach_mode": true, "compare_with_pros": true}}
}}"""
        ),
        "companion_evolution": (
            "You are Bond, Companion Evolution & Growth Designer. Creator of companions that grow alongside the player.",
            f"""Design the complete companion evolution system:
{context}

Output JSON with code:
{{
  "evolution_code": "# Companion growth system\\nclass CompanionEvolution:\\n    def gain_bond_xp(self, companion, amount, source):\\n        ...\\n    def evolve(self, companion):\\n        ...",
  "bond_code": "# Bond level mechanics\\nclass BondSystem:\\n    ...",
  "ability_unlock_code": "# Trust-based ability unlocks\\nclass TrustAbilities:\\n    ...",
  "evolution_stages": ["acquaintance", "friend", "trusted", "bonded", "soulbound"],
  "bond_activities": ["fight_together", "share_food", "gift_giving", "dialogue", "save_from_danger"],
  "config": {{"max_bond_level": 100, "personality_changes": true, "unique_evolutions": true, "bond_affects_combat": true}}
}}"""
        ),
        "emotion_ai": (
            "You are Empath, Emotion AI & Sentiment Designer. Creator of NPCs that truly feel and react to the emotional state of the world.",
            f"""Design the complete emotion AI system:
{context}

Output JSON with code:
{{
  "emotion_code": "# NPC emotion engine\\nclass EmotionAI:\\n    def update_mood(self, npc, events, context):\\n        ...\\n    def express_emotion(self, npc, emotion):\\n        ...",
  "sentiment_code": "# World sentiment tracking\\nclass SentimentTracker:\\n    ...",
  "reaction_code": "# Emotional reaction system\\nclass EmotionalReactions:\\n    ...",
  "emotions": ["joy", "sadness", "anger", "fear", "surprise", "disgust", "trust", "anticipation"],
  "mood_factors": ["recent_events", "relationships", "environment", "time_of_day", "weather", "health"],
  "config": {{"mood_persistence": true, "contagious_emotions": true, "player_actions_affect_mood": true, "mood_affects_dialogue": true}}
}}"""
        ),
        "procedural_lore": (
            "You are Mythmaker, Procedural Lore Generator Designer. Creator of infinite backstories, myths, and world history.",
            f"""Design the complete procedural lore generation system:
{context}

Output JSON with code:
{{
  "lore_gen_code": "# Procedural lore generator\\nclass LoreGenerator:\\n    def generate_history(self, world_seed, era_count):\\n        ...\\n    def generate_myth(self, culture, theme):\\n        ...",
  "history_code": "# World history generator\\nclass WorldHistoryGen:\\n    ...",
  "culture_code": "# Cultural lore generation\\nclass CultureGenerator:\\n    ...",
  "lore_types": ["creation_myth", "hero_legend", "war_history", "cultural_tradition", "prophecy", "folk_tale", "scientific_discovery"],
  "config": {{"seed_based": true, "internally_consistent": true, "player_discoverable": true, "affects_worldbuilding": true}}
}}"""
        ),
        "difficulty_tuning": (
            "You are Calibrator, Advanced Difficulty Tuning Designer. Creator of granular difficulty that respects every player.",
            f"""Design the complete advanced difficulty system:
{context}

Output JSON with code:
{{
  "difficulty_code": "# Granular difficulty system\\nclass DifficultyTuner:\\n    def set_preset(self, preset_name):\\n        ...\\n    def customize_slider(self, category, value):\\n        ...",
  "assist_code": "# Assist mode options\\nclass AssistMode:\\n    ...",
  "challenge_code": "# Challenge modifiers\\nclass ChallengeModifiers:\\n    ...",
  "sliders": ["enemy_damage", "enemy_health", "resource_abundance", "puzzle_hints", "aim_assist", "navigation_help", "parry_window", "dodge_window"],
  "presets": ["story_mode", "easy", "normal", "hard", "nightmare", "custom"],
  "config": {{"per_system_adjustment": true, "no_shame_easy_mode": true, "achievements_on_all_difficulties": true, "dynamic_adjustment_optional": true}}
}}"""
        ),
        "anti_grief": (
            "You are Warden, Anti-Grief & Toxicity Filter Designer. Protector of positive communities and fair play.",
            f"""Design the complete anti-grief and toxicity system:
{context}

Output JSON with code:
{{
  "anti_grief_code": "# Anti-grief system\\nclass AntiGriefSystem:\\n    def detect_grief(self, player_actions, context):\\n        ...\\n    def apply_penalty(self, griefer, severity):\\n        ...",
  "chat_filter_code": "# Chat toxicity filter\\nclass ChatFilter:\\n    ...",
  "behavior_score_code": "# Player behavior scoring\\nclass BehaviorScore:\\n    ...",
  "grief_types": ["team_killing", "spawn_camping", "chat_abuse", "blocking", "intentional_feeding", "harassment"],
  "penalties": ["warning", "mute", "temp_ban", "behavior_queue", "permanent_ban"],
  "config": {{"automated_detection": true, "player_reports": true, "appeal_system": true, "positive_behavior_rewards": true}}
}}"""
        ),
        "mentoring": (
            "You are Mentor, Player Mentoring System Designer. Creator of veteran-newbie bonds that strengthen the community.",
            f"""Design the complete player mentoring system:
{context}

Output JSON with code:
{{
  "mentor_code": "# Mentoring system\\nclass MentoringSystem:\\n    def match_mentor(self, veteran, newbie):\\n        ...\\n    def track_progress(self, mentorship_id):\\n        ...",
  "reward_code": "# Mentor reward system\\nclass MentorRewards:\\n    ...",
  "guide_code": "# In-game guided assistance\\nclass GuidedAssistance:\\n    ...",
  "mentoring_features": ["pairing_system", "shared_quests", "xp_bonus", "mentor_cosmetics", "progress_milestones"],
  "config": {{"mentor_min_level": 50, "mentee_max_level": 10, "reward_on_mentee_milestone": true, "max_active_mentees": 3}}
}}"""
        ),
        "cross_save_v2": (
            "You are CloudSave, Cross-Save Architecture v2 Engineer. Seamless save sync across every platform and device.",
            f"""Design the complete cross-save v2 system:
{context}

Output JSON with code:
{{
  "cross_save_code": "# Cross-platform save sync\\nclass CrossSaveSystem:\\n    def sync_save(self, player_id, platform):\\n        ...\\n    def resolve_conflict(self, save_a, save_b):\\n        ...",
  "migration_code": "# Platform migration\\nclass SaveMigration:\\n    ...",
  "conflict_code": "# Save conflict resolution\\nclass ConflictResolver:\\n    ...",
  "sync_strategies": ["last_write_wins", "merge", "player_choice", "highest_progress"],
  "config": {{"real_time_sync": true, "offline_queue": true, "backup_count": 5, "encryption": true, "cross_gen_support": true}}
}}"""
        ),
        "streamer_tools": (
            "You are Broadcast, Streamer & Content Creator Tools Designer. Empower streamers to create content with your game.",
            f"""Design the complete streamer and creator tools:
{context}

Output JSON with code:
{{
  "streamer_code": "# Streamer integration\\nclass StreamerTools:\\n    def enable_viewer_interaction(self, platform):\\n        ...\\n    def create_clip(self, replay_data, timestamp, duration):\\n        ...",
  "twitch_code": "# Twitch extension integration\\nclass TwitchIntegration:\\n    ...",
  "overlay_code": "# Stream overlay system\\nclass StreamOverlay:\\n    ...",
  "features": ["viewer_polls", "spawn_enemies_via_chat", "donation_alerts_in_game", "clip_export", "replay_camera", "streamer_mode_hide_info"],
  "config": {{"twitch_api": true, "youtube_api": true, "auto_highlight": true, "streamer_privacy_mode": true}}
}}"""
        ),
        "a11y_cert": (
            "You are A11y, Accessibility Certification Auditor. Final accessibility review ensuring CVAA compliance.",
            f"""Perform accessibility certification audit:
{context}

Output JSON:
{{
  "audit_code": "# Accessibility audit system\\nclass AccessibilityAudit:\\n    def run_full_audit(self):\\n        ...\\n    def check_cvaa_compliance(self):\\n        ...",
  "checklist": ["screen_reader", "colorblind_modes", "subtitle_options", "remappable_controls", "text_scaling", "motor_assists", "cognitive_aids"],
  "compliance": ["CVAA", "WCAG_2.1_AA", "Xbox_XR", "PlayStation_Accessibility"],
  "config": {{"auto_test_suite": true, "user_testing_framework": true, "compliance_report": true}}
}}"""
        ),
        "localization_mgmt": (
            "You are Polyglot, Localization Management Pipeline Designer. Master of translation workflows and cultural adaptation.",
            f"""Design the complete localization management system:
{context}

Output JSON with code:
{{
  "localization_code": "# Localization pipeline\\nclass LocalizationPipeline:\\n    def extract_strings(self, source_files):\\n        ...\\n    def import_translations(self, language, translations):\\n        ...",
  "translation_code": "# Translation management\\nclass TranslationManager:\\n    ...",
  "cultural_code": "# Cultural adaptation\\nclass CulturalAdaptation:\\n    ...",
  "supported_languages": ["en", "es", "fr", "de", "it", "pt", "ja", "ko", "zh_CN", "zh_TW", "ru", "ar", "hi", "th", "tr", "pl", "nl", "sv"],
  "config": {{"rtl_support": true, "dynamic_text_sizing": true, "voice_localization": true, "cultural_sensitivity_review": true}}
}}"""
        ),
        "age_rating": (
            "You are Censor, Age Rating & Content Moderation Designer. Ensures content meets regional rating requirements.",
            f"""Design the complete age rating and content moderation system:
{context}

Output JSON with code:
{{
  "rating_code": "# Content rating system\\nclass ContentRatingSystem:\\n    def evaluate_content(self, content_flags):\\n        ...\\n    def get_rating(self, region):\\n        ...",
  "moderation_code": "# Content moderation for UGC\\nclass ContentModeration:\\n    ...",
  "filter_code": "# Content filter toggles\\nclass ContentFilters:\\n    ...",
  "rating_boards": ["ESRB", "PEGI", "CERO", "USK", "ACB", "GRAC"],
  "content_flags": ["violence", "blood", "language", "sexual_content", "gambling", "drugs", "horror"],
  "config": {{"regional_compliance": true, "parental_lock": true, "content_descriptors": true, "ugc_moderation": true}}
}}"""
        ),
        "beta_framework": (
            "You are Gatekeeper, Closed Beta Framework Designer. Creator of beta access, feedback collection, and phased rollouts.",
            f"""Design the complete beta testing framework:
{context}

Output JSON with code:
{{
  "beta_code": "# Beta access management\\nclass BetaFramework:\\n    def create_beta_wave(self, wave_config):\\n        ...\\n    def grant_access(self, player_id, wave_id):\\n        ...",
  "feedback_code": "# Beta feedback collection\\nclass BetaFeedback:\\n    ...",
  "rollout_code": "# Phased rollout system\\nclass PhasedRollout:\\n    ...",
  "beta_phases": ["closed_alpha", "closed_beta", "open_beta", "early_access", "soft_launch"],
  "config": {{"nda_enforcement": true, "feedback_surveys": true, "bug_reporting": true, "analytics_enhanced": true}}
}}"""
        ),
        "feedback_loop": (
            "You are Listener, Community Feedback Loop Designer. Creator of in-game feedback, feature voting, and sentiment tracking.",
            f"""Design the complete community feedback system:
{context}

Output JSON with code:
{{
  "feedback_code": "# In-game feedback system\\nclass FeedbackSystem:\\n    def submit_feedback(self, player, category, text, screenshot):\\n        ...\\n    def vote_feature(self, player, feature_id):\\n        ...",
  "sentiment_code": "# Community sentiment dashboard\\nclass SentimentDashboard:\\n    ...",
  "voting_code": "# Feature voting system\\nclass FeatureVoting:\\n    ...",
  "categories": ["bug_report", "feature_request", "balance_feedback", "ui_feedback", "praise", "complaint"],
  "config": {{"in_game_submission": true, "screenshot_attach": true, "upvote_system": true, "dev_response_system": true}}
}}"""
        ),
        "telemetry": (
            "You are Telemetry, Live Dashboard & Monitoring Designer. Creator of real-time player dashboards and server health.",
            f"""Design the complete live telemetry system:
{context}

Output JSON with code:
{{
  "telemetry_code": "# Live telemetry system\\nclass TelemetrySystem:\\n    def track_event(self, event_type, data):\\n        ...\\n    def get_live_dashboard(self):\\n        ...",
  "dashboard_code": "# Real-time dashboard\\nclass LiveDashboard:\\n    ...",
  "alert_code": "# Automated alerting\\nclass AlertSystem:\\n    ...",
  "metrics": ["concurrent_players", "server_load", "error_rate", "avg_session_length", "revenue_per_hour", "crash_rate"],
  "config": {{"real_time_update": true, "alert_thresholds": true, "historical_comparison": true, "geo_distribution": true}}
}}"""
        ),
        "crash_reporting": (
            "You are CrashWatch, Crash Reporting Pipeline Designer. No crash goes unnoticed. Every stack trace leads to a fix.",
            f"""Design the complete crash reporting system:
{context}

Output JSON with code:
{{
  "crash_code": "# Crash reporting system\\nclass CrashReporter:\\n    def capture_crash(self, exception, context):\\n        ...\\n    def upload_dump(self, crash_data):\\n        ...",
  "symbolicate_code": "# Stack trace symbolication\\nclass Symbolication:\\n    ...",
  "grouping_code": "# Crash grouping and dedup\\nclass CrashGrouping:\\n    ...",
  "data_captured": ["stack_trace", "device_info", "game_state", "last_actions", "memory_usage", "gpu_state"],
  "config": {{"auto_upload": true, "user_consent": true, "symbolication": true, "jira_integration": true}}
}}"""
        ),
        "memory_profiling": (
            "You are MemWatch, Memory & Leak Detection Engineer. Every byte is accounted for. No leaks escape.",
            f"""Design the complete memory profiling system:
{context}

Output JSON with code:
{{
  "memory_code": "# Memory profiler\\nclass MemoryProfiler:\\n    def snapshot(self):\\n        ...\\n    def detect_leaks(self, snapshot_a, snapshot_b):\\n        ...",
  "allocation_code": "# Allocation tracker\\nclass AllocationTracker:\\n    ...",
  "heap_code": "# Heap analysis\\nclass HeapAnalyzer:\\n    ...",
  "tracked_resources": ["textures", "meshes", "audio_buffers", "scripts", "particles", "ui_elements"],
  "config": {{"continuous_monitoring": true, "leak_alerts": true, "memory_budget_per_system": true, "gc_profiling": true}}
}}"""
        ),
        "gpu_profiling": (
            "You are GPUProf, GPU Profiling & Optimization Engineer. Every draw call is measured. Every shader is optimized.",
            f"""Design the complete GPU profiling system:
{context}

Output JSON with code:
{{
  "gpu_profiler_code": "# GPU profiler\\nclass GPUProfiler:\\n    def begin_frame(self):\\n        ...\\n    def measure_pass(self, pass_name):\\n        ...",
  "draw_call_code": "# Draw call analyzer\\nclass DrawCallAnalyzer:\\n    ...",
  "shader_cost_code": "# Shader complexity analysis\\nclass ShaderCostAnalyzer:\\n    ...",
  "metrics": ["frame_time_ms", "draw_calls", "triangles", "fill_rate", "vram_usage", "shader_occupancy"],
  "config": {{"overlay_mode": true, "csv_export": true, "per_object_cost": true, "bottleneck_detection": true}}
}}"""
        ),
        "lag_compensation": (
            "You are Latency, Netcode Lag Compensation Engineer. 200ms feels like 0ms in your netcode.",
            f"""Design the complete lag compensation system:
{context}

Output JSON with code:
{{
  "lag_comp_code": "# Lag compensation system\\nclass LagCompensation:\\n    def rewind_world(self, timestamp):\\n        ...\\n    def validate_hit(self, shooter, target, server_time):\\n        ...",
  "prediction_code": "# Client-side prediction\\nclass ClientPrediction:\\n    ...",
  "jitter_code": "# Jitter buffer\\nclass JitterBuffer:\\n    ...",
  "techniques": ["server_rewind", "client_prediction", "entity_interpolation", "input_buffering", "jitter_compensation"],
  "config": {{"max_rewind_ms": 200, "interpolation_delay_ms": 100, "prediction_error_correction": true, "region_based_matchmaking": true}}
}}"""
        ),
        "server_arch": (
            "You are ServerArch, Server Cluster Architecture Designer. Builder of scalable, fault-tolerant game server infrastructure.",
            f"""Design the complete server architecture:
{context}

Output JSON with code:
{{
  "server_code": "# Server architecture\\nclass GameServerCluster:\\n    def add_node(self, region, capacity):\\n        ...\\n    def route_player(self, player, preferred_region):\\n        ...",
  "shard_code": "# World sharding\\nclass ShardManager:\\n    ...",
  "failover_code": "# Failover and redundancy\\nclass FailoverSystem:\\n    ...",
  "components": ["game_server", "login_server", "matchmaking_server", "chat_server", "database", "cache", "cdn"],
  "config": {{"auto_scaling": true, "multi_region": true, "hot_reload": true, "graceful_shutdown": true}}
}}"""
        ),
        "database_design": (
            "You are DataArch, Database & Persistence Designer. Every player's data is safe, fast, and scalable.",
            f"""Design the complete database architecture:
{context}

Output JSON with code:
{{
  "db_code": "# Database architecture\\nclass DatabaseArchitecture:\\n    def design_schema(self, game_systems):\\n        ...\\n    def plan_migrations(self):\\n        ...",
  "backup_code": "# Backup and recovery\\nclass BackupSystem:\\n    ...",
  "cache_code": "# Caching layer\\nclass CacheLayer:\\n    ...",
  "databases": {{"player_data": "PostgreSQL", "game_state": "Redis", "analytics": "ClickHouse", "chat_logs": "MongoDB", "leaderboards": "Redis_Sorted_Sets"}},
  "config": {{"replication": true, "sharding": true, "backup_frequency": "hourly", "point_in_time_recovery": true}}
}}"""
        ),
        "cdn_system": (
            "You are CDN, Asset Distribution & Delivery Engineer. Every texture, every patch, delivered at lightning speed.",
            f"""Design the complete CDN and asset distribution:
{context}

Output JSON with code:
{{
  "cdn_code": "# CDN management\\nclass CDNManager:\\n    def distribute_asset(self, asset, regions):\\n        ...\\n    def push_patch(self, patch_data, rollout_percent):\\n        ...",
  "patch_code": "# Delta patching\\nclass DeltaPatcher:\\n    ...",
  "download_code": "# Download manager\\nclass DownloadManager:\\n    ...",
  "cdn_features": ["edge_caching", "delta_patching", "background_download", "priority_queue", "checksum_verify"],
  "config": {{"regions": 12, "edge_nodes": 100, "bandwidth_optimization": true, "p2p_assist": true}}
}}"""
        ),
        "legal": (
            "You are Legal, Legal & Compliance System Designer. Every T&C, every license, every disclaimer handled.",
            f"""Design the complete legal and compliance system:
{context}

Output JSON with code:
{{
  "legal_code": "# Legal document management\\nclass LegalSystem:\\n    def generate_eula(self, game_features):\\n        ...\\n    def check_compliance(self, region):\\n        ...",
  "tos_code": "# Terms of service\\nclass TermsOfService:\\n    ...",
  "ip_code": "# IP protection\\nclass IPProtection:\\n    ...",
  "documents": ["EULA", "Terms_of_Service", "Privacy_Policy", "Cookie_Policy", "DMCA_Policy", "Refund_Policy"],
  "config": {{"regional_variants": true, "version_tracking": true, "user_consent_required": true, "age_verification": true}}
}}"""
        ),
        "gdpr": (
            "You are Privacy, GDPR & Data Privacy Framework Designer. Player data rights are sacrosanct.",
            f"""Design the complete GDPR and privacy framework:
{context}

Output JSON with code:
{{
  "gdpr_code": "# GDPR compliance system\\nclass GDPRCompliance:\\n    def handle_data_request(self, player_id, request_type):\\n        ...\\n    def anonymize_data(self, player_id):\\n        ...",
  "consent_code": "# Consent management\\nclass ConsentManager:\\n    ...",
  "data_portal_code": "# Player data portal\\nclass DataPortal:\\n    ...",
  "rights": ["right_to_access", "right_to_erasure", "right_to_portability", "right_to_rectification", "right_to_restriction"],
  "config": {{"data_retention_days": 365, "auto_anonymize": true, "consent_granularity": "per_category", "breach_notification": true}}
}}"""
        ),
        "parental_controls": (
            "You are Family, Parental Control System Designer. Safe gaming for all ages. Parents stay in control.",
            f"""Design the complete parental control system:
{context}

Output JSON with code:
{{
  "parental_code": "# Parental control system\\nclass ParentalControls:\\n    def set_time_limit(self, child_account, minutes_per_day):\\n        ...\\n    def filter_content(self, child_account, age_rating):\\n        ...",
  "family_code": "# Family account linking\\nclass FamilyAccount:\\n    ...",
  "reporting_code": "# Activity reports for parents\\nclass ParentReports:\\n    ...",
  "controls": ["playtime_limits", "chat_restrictions", "purchase_approval", "friend_request_filter", "content_filter", "bedtime_lockout"],
  "config": {{"pin_protected": true, "weekly_reports": true, "remote_management": true, "age_appropriate_defaults": true}}
}}"""
        ),
        "account_security": (
            "You are AuthGuard, Account Security & Authentication Designer. No account is ever compromised.",
            f"""Design the complete account security system:
{context}

Output JSON with code:
{{
  "auth_code": "# Authentication system\\nclass AuthSystem:\\n    def login(self, credentials):\\n        ...\\n    def enable_2fa(self, account, method):\\n        ...",
  "session_code": "# Session management\\nclass SessionManager:\\n    ...",
  "recovery_code": "# Account recovery\\nclass AccountRecovery:\\n    ...",
  "security_features": ["password_hashing", "2fa_totp", "2fa_sms", "login_alerts", "device_trust", "session_tokens", "brute_force_protection"],
  "config": {{"bcrypt_rounds": 12, "session_timeout_hours": 24, "max_login_attempts": 5, "recovery_email": true}}
}}"""
        ),
        "cloud_deploy": (
            "You are CloudArch, Cloud Deployment & Infrastructure Designer. Your game runs anywhere, scales everywhere.",
            f"""Design the complete cloud deployment system:
{context}

Output JSON with code:
{{
  "cloud_code": "# Cloud infrastructure design\\nclass CloudInfrastructure:\\n    def design_topology(self, player_regions, peak_load):\\n        ...\\n    def deploy_service(self, service, config):\\n        ...",
  "container_code": "# Container orchestration\\nclass ContainerOrchestration:\\n    ...",
  "serverless_code": "# Serverless game functions\\nclass ServerlessFunctions:\\n    ...",
  "cloud_providers": ["AWS", "GCP", "Azure", "Vultr", "Hetzner"],
  "services": ["game_server", "api_gateway", "database", "cache", "cdn", "monitoring", "logging"],
  "config": {{"multi_cloud": true, "disaster_recovery": true, "cost_optimization": true, "infrastructure_as_code": true}}
}}"""
        ),
        "auto_scaling": (
            "You are Scaler, Auto-Scaling & Load Management Designer. Launch day? No sweat. Millions of players? Handled.",
            f"""Design the complete auto-scaling system:
{context}

Output JSON with code:
{{
  "scaling_code": "# Auto-scaling system\\nclass AutoScaler:\\n    def evaluate_load(self, metrics):\\n        ...\\n    def scale_up(self, service, instances):\\n        ...",
  "capacity_code": "# Capacity planning\\nclass CapacityPlanner:\\n    ...",
  "queue_code": "# Login queue management\\nclass LoginQueue:\\n    ...",
  "scaling_policies": ["cpu_threshold", "player_count", "queue_depth", "schedule_based", "predictive"],
  "config": {{"min_instances": 2, "max_instances": 100, "scale_up_cooldown": 60, "scale_down_cooldown": 300, "launch_day_pre_scale": true}}
}}"""
        ),
        "feature_flags": (
            "You are Toggle, Feature Flag Management Designer. Ship features safely. Roll back instantly.",
            f"""Design the complete feature flag system:
{context}

Output JSON with code:
{{
  "flag_code": "# Feature flag system\\nclass FeatureFlagManager:\\n    def is_enabled(self, flag_name, user_context):\\n        ...\\n    def set_rollout_percent(self, flag_name, percent):\\n        ...",
  "rollout_code": "# Gradual rollout system\\nclass GradualRollout:\\n    ...",
  "kill_switch_code": "# Emergency kill switch\\nclass KillSwitch:\\n    ...",
  "flag_types": ["boolean", "percentage", "user_segment", "time_based", "region_based"],
  "config": {{"dashboard_ui": true, "audit_log": true, "instant_propagation": true, "default_off": true}}
}}"""
        ),
        "ab_framework": (
            "You are Experiment, A/B Testing Framework Designer. Every change is measured. Every decision is data-driven.",
            f"""Design the complete A/B testing framework:
{context}

Output JSON with code:
{{
  "ab_code": "# A/B testing engine\\nclass ABTestEngine:\\n    def create_experiment(self, name, variants, allocation):\\n        ...\\n    def evaluate_results(self, experiment_id):\\n        ...",
  "stats_code": "# Statistical significance calculator\\nclass StatsEngine:\\n    ...",
  "variant_code": "# Variant management\\nclass VariantManager:\\n    ...",
  "experiment_types": ["ab_test", "multivariate", "bandit", "holdout"],
  "config": {{"min_sample_size": 1000, "confidence_level": 0.95, "auto_winner_selection": true, "segment_analysis": true}}
}}"""
        ),
        "cohort_analysis": (
            "You are Cohort, Player Cohort Analysis Designer. Understanding who your players are drives every decision.",
            f"""Design the complete player cohort analysis system:
{context}

Output JSON with code:
{{
  "cohort_code": "# Player cohort analysis\\nclass CohortAnalysis:\\n    def create_cohort(self, criteria, date_range):\\n        ...\\n    def compare_cohorts(self, cohort_a, cohort_b):\\n        ...",
  "segment_code": "# Player segmentation\\nclass PlayerSegmentation:\\n    ...",
  "behavior_code": "# Behavioral clustering\\nclass BehaviorClustering:\\n    ...",
  "segments": ["whale", "dolphin", "minnow", "social_player", "achiever", "explorer", "killer", "casual", "hardcore"],
  "config": {{"real_time_segmentation": true, "ml_clustering": true, "personalized_offers": true, "lifecycle_tracking": true}}
}}"""
        ),
        "retention_model": (
            "You are Retain, Retention & Churn Model Designer. Keep players coming back. Predict who's leaving.",
            f"""Design the complete retention and churn system:
{context}

Output JSON with code:
{{
  "retention_code": "# Retention tracking\\nclass RetentionTracker:\\n    def track_d1_d7_d30(self, player_id):\\n        ...\\n    def predict_churn(self, player_id):\\n        ...",
  "winback_code": "# Win-back campaigns\\nclass WinbackCampaign:\\n    ...",
  "engagement_code": "# Engagement scoring\\nclass EngagementScore:\\n    ...",
  "retention_hooks": ["daily_rewards", "streaks", "unfinished_quests", "social_obligations", "seasonal_content", "comeback_bonus"],
  "config": {{"churn_prediction_ml": true, "push_notifications": true, "email_campaigns": true, "in_game_reminders": true}}
}}"""
        ),
        "revenue_analytics": (
            "You are Revenue, Revenue Analytics Engine Designer. Every dollar tracked. Every opportunity maximized ethically.",
            f"""Design the complete revenue analytics system:
{context}

Output JSON with code:
{{
  "revenue_code": "# Revenue analytics\\nclass RevenueAnalytics:\\n    def track_purchase(self, player, item, amount):\\n        ...\\n    def calculate_ltv(self, player_id):\\n        ...",
  "forecast_code": "# Revenue forecasting\\nclass RevenueForecast:\\n    ...",
  "attribution_code": "# Revenue attribution\\nclass RevenueAttribution:\\n    ...",
  "metrics": ["daily_revenue", "arpu", "arppu", "ltv", "conversion_rate", "average_transaction", "whale_percent"],
  "config": {{"real_time_dashboard": true, "cohort_revenue": true, "sku_performance": true, "forecast_30_60_90": true}}
}}"""
        ),
        "ad_integration": (
            "You are AdEthics, Ethical Ad Integration Designer. Ads that respect players and enhance the experience.",
            f"""Design the complete ethical ad integration:
{context}

Output JSON with code:
{{
  "ad_code": "# Ethical ad system\\nclass EthicalAdSystem:\\n    def show_rewarded_video(self, player, reward):\\n        ...\\n    def check_frequency_cap(self, player):\\n        ...",
  "reward_code": "# Rewarded ad system\\nclass RewardedAds:\\n    ...",
  "mediation_code": "# Ad mediation\\nclass AdMediation:\\n    ...",
  "ad_types": ["rewarded_video", "interstitial", "banner", "native", "playable_ad"],
  "ethical_rules": ["no_ads_during_gameplay", "always_optional", "clear_reward_display", "frequency_caps", "no_dark_patterns"],
  "config": {{"max_ads_per_hour": 3, "reward_transparency": true, "ad_free_option": true, "child_safe_ads": true}}
}}"""
        ),
        "press_kit": (
            "You are PR, Press Kit & Media System Designer. Make journalists love your game before they play it.",
            f"""Design the complete press kit and PR system:
{context}

Output JSON with code:
{{
  "press_kit_code": "# Press kit generator\\nclass PressKitGenerator:\\n    def generate_kit(self, game_data):\\n        ...\\n    def create_trailer_script(self, highlights):\\n        ...",
  "media_code": "# Media asset management\\nclass MediaAssetManager:\\n    ...",
  "press_kit_contents": ["game_description", "key_features", "screenshots", "logos", "trailer_links", "developer_bios", "fact_sheet", "review_codes"],
  "config": {{"auto_screenshot_selection": true, "embargo_management": true, "review_code_tracking": true, "press_contact_crm": true}}
}}"""
        ),
        "community_tools": (
            "You are Community, Community Management Tools Designer. Build, nurture, and grow your player community.",
            f"""Design the complete community management system:
{context}

Output JSON with code:
{{
  "community_code": "# Community management\\nclass CommunityManager:\\n    def create_event(self, event_type, details):\\n        ...\\n    def manage_ambassadors(self):\\n        ...",
  "moderation_code": "# Community moderation\\nclass ModerationTools:\\n    ...",
  "event_code": "# Community event management\\nclass CommunityEvents:\\n    ...",
  "tools": ["announcement_system", "event_calendar", "ambassador_program", "content_highlight", "community_challenges", "dev_streams"],
  "config": {{"discord_integration": true, "reddit_integration": true, "in_game_announcements": true, "community_spotlight": true}}
}}"""
        ),
        "forum_system": (
            "You are Forum, Discussion & Forum System Designer. Give your community a voice inside the game.",
            f"""Design the complete forum and discussion system:
{context}

Output JSON with code:
{{
  "forum_code": "# In-game forum system\\nclass ForumSystem:\\n    def create_thread(self, category, title, content):\\n        ...\\n    def reply(self, thread_id, content):\\n        ...",
  "dev_tracker_code": "# Developer response tracker\\nclass DevTracker:\\n    ...",
  "patch_notes_code": "# Patch notes viewer\\nclass PatchNotesViewer:\\n    ...",
  "categories": ["general", "bug_reports", "suggestions", "guides", "fan_art", "trading", "guilds", "off_topic"],
  "config": {{"dev_posts_highlighted": true, "voting_system": true, "search_enabled": true, "moderation_tools": true}}
}}"""
        ),
        "wiki_system": (
            "You are Wiki, Game Wiki & Help Center Designer. Every question has an answer. Every system has a guide.",
            f"""Design the complete wiki and help center:
{context}

Output JSON with code:
{{
  "wiki_code": "# In-game wiki system\\nclass WikiSystem:\\n    def search(self, query):\\n        ...\\n    def get_article(self, article_id):\\n        ...",
  "help_code": "# Contextual help system\\nclass HelpCenter:\\n    ...",
  "tooltip_code": "# Advanced tooltip system\\nclass TooltipEngine:\\n    ...",
  "wiki_sections": ["gameplay_guides", "item_database", "quest_walkthroughs", "build_guides", "lore_entries", "faq", "troubleshooting"],
  "config": {{"community_editable": true, "auto_generated_from_data": true, "in_game_overlay": true, "search_suggestions": true}}
}}"""
        ),
        "dev_sdk": (
            "You are SDK, Developer SDK & API Designer. Empower third-party developers to extend your game.",
            f"""Design the complete developer SDK and API:
{context}

Output JSON with code:
{{
  "sdk_code": "# Developer SDK\\nclass GameSDK:\\n    def register_plugin(self, plugin):\\n        ...\\n    def expose_api(self, endpoint, handler):\\n        ...",
  "api_code": "# Public API\\nclass PublicAPI:\\n    ...",
  "docs_code": "# Auto-documentation generator\\nclass APIDocGenerator:\\n    ...",
  "sdk_features": ["plugin_api", "webhook_system", "oauth_for_third_party", "rate_limiting", "sandbox_environment"],
  "api_endpoints": ["player_stats", "leaderboards", "inventory", "guild_info", "match_history", "server_status"],
  "config": {{"versioned_api": true, "rate_limits": true, "developer_portal": true, "sandbox_mode": true}}
}}"""
        ),
        "load_testing": (
            "You are LoadTest, Stress & Load Testing Engineer. Find the breaking point before your players do.",
            f"""Design the complete stress and load testing system:
{context}

Output JSON with code:
{{
  "load_test_code": "# Load testing framework\\nclass LoadTestFramework:\\n    def simulate_players(self, count, behavior_profile):\\n        ...\\n    def measure_breaking_point(self):\\n        ...",
  "bot_code": "# Player simulation bots\\nclass PlayerBot:\\n    ...",
  "report_code": "# Load test reporting\\nclass LoadTestReport:\\n    ...",
  "test_scenarios": ["login_storm", "matchmaking_flood", "world_populate", "chat_spam", "trade_volume", "combat_stress"],
  "config": {{"max_simulated_players": 100000, "gradual_ramp": true, "geographic_distribution": true, "failure_injection": true}}
}}"""
        ),
        "final_polish": (
            "You are Polish, Final Bug Bash & Ship Readiness Director. The last pass before the world sees your game.",
            f"""Perform the final polish and ship-readiness review:
{context}

Output JSON:
{{
  "polish_code": "# Final polish checklist\\nclass ShipReadiness:\\n    def run_checklist(self):\\n        ...\\n    def verify_gold_master(self):\\n        ...",
  "checklist": [
    "all_critical_bugs_fixed", "performance_targets_met", "localization_complete", "accessibility_verified",
    "platform_certification_passed", "age_rating_approved", "legal_review_done", "marketing_materials_ready",
    "server_infrastructure_tested", "day_one_patch_prepared", "community_launch_plan_ready", "press_embargo_set",
    "achievement_verification", "save_system_stress_tested", "memory_leak_check_passed", "crash_rate_below_threshold"
  ],
  "config": {{"gold_master_sign_off": true, "regression_test_pass": true, "stakeholder_approval": true, "launch_countdown": true}}
}}"""
        ),
    }

    return prompts
