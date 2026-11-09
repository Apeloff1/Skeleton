"""
HYPERSCALE DOMAIN REGISTRY v25.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
300 DOMAINS × 8 SPECIALISTS = 2,400 AGENTS
Covers EVERY nuance of game creation across 10 mega-categories.
Every domain has 8 specialists with 8 expertise points + deep knowledge.
Auto-generated synergy web with 1000+ cross-domain connections.
Jeeves is the focal orchestrator of all synergy.
"""

from fastapi import APIRouter, HTTPException
from routes.hyperscale_seeds import generate_extended_domains, SEEDS

router = APIRouter(prefix="/api/hyperscale", tags=["hyperscale"])

# ═══════════════════════════════════════════════════════════════════════
# DOMAIN DEFINITIONS — 10 MEGA-CATEGORIES × 30 DOMAINS × 8 SPECIALISTS
# ═══════════════════════════════════════════════════════════════════════

# Compact format: (domain_id, name, icon, color, desc, [specialist_tuples], [synergy_domain_ids])
# specialist_tuple: (id, name, title, [8 expertise strings], {deep_knowledge})

def _cat(name, icon, color, domains):
    return {"name": name, "icon": icon, "color": color, "domains": domains}

# ─────────────────────────────────────────────────────────────────────
# CATEGORY 1: CORE GAME DESIGN (30 domains)
# ─────────────────────────────────────────────────────────────────────
CAT_CORE_DESIGN = _cat("Core Game Design", "bulb", "#8B5CF6", {
    "game_feel": {"name": "GameFeel", "color": "#8B5CF6", "desc": "Juice, responsiveness, input latency, screen shake, hit stop, haptic feedback", "specs": [
        ("input_response", "InputResponse", "Input Latency Specialist", ["Sub-frame input polling", "Input buffering windows", "Coyote time implementation", "Pre-jump buffering", "Ghost input prevention", "Platform-specific latency", "Wireless controller compensation", "Display pipeline latency"]),
        ("juice_master", "JuiceMaster", "Game Juice Architect", ["Screen shake profiles", "Hit stop/freeze frame", "Squash and stretch", "Particle burst timing", "Camera punch", "Chromatic aberration pulses", "Time dilation effects", "Impact flash design"]),
        ("haptic_designer", "HapticDesigner", "Haptic Feedback Designer", ["DualSense adaptive triggers", "HD rumble patterns", "Contextual vibration", "Terrain haptic profiles", "Combat impact haptics", "UI confirmation haptics", "Environmental haptics", "Accessibility haptic options"]),
        ("animation_feel", "AnimationFeel", "Animation Feel Specialist", ["Anticipation frames", "Follow-through curves", "Blend time optimization", "Root motion tuning", "Additive hit reactions", "Weight/momentum feel", "Recovery frame design", "Procedural secondary motion"]),
        ("audio_feel", "AudioFeel", "Audio Feedback Designer", ["Impact sound layering", "UI click satisfaction", "Footstep weight variation", "Weapon impact sweeteners", "Collection sound design", "Achievement fanfare design", "Ambient tactile audio", "Dynamic volume ducking"]),
        ("visual_feedback", "VisualFeedback", "Visual Feedback Architect", ["Damage number design", "Health bar feedback", "Combo counter animation", "Critical hit indicators", "Status effect overlays", "Directional damage indicators", "Kill confirmation design", "Reward visual celebration"]),
        ("movement_feel", "MovementFeel", "Movement Feel Specialist", ["Acceleration curves", "Deceleration friction", "Air control tuning", "Turn rate smoothing", "Slope handling", "Step-up height tuning", "Dash/dodge feel", "Swimming/flying feel"]),
        ("weight_physics", "WeightPhysics", "Weight & Physics Feel Designer", ["Object weight differentiation", "Throw physics tuning", "Push/pull feel", "Grapple swing feel", "Vehicle weight feel", "Weapon swing weight", "Shield impact weight", "Gravity manipulation feel"]),
    ], "synergy": ["combat_forge", "animation_studio", "audio_sphere", "input_matrix"]},
    "difficulty_design": {"name": "DifficultyDesign", "color": "#7C3AED", "desc": "Difficulty curves, adaptive challenge, assist modes, rubber-banding, player skill modeling", "specs": [
        ("curve_architect", "CurveArchitect", "Difficulty Curve Designer", ["S-curve difficulty progression", "Spike/valley pacing", "Zone of proximal development", "Challenge ramp rates", "Plateau detection", "Difficulty reset points", "NG+ scaling formulas", "Endgame difficulty spiral"]),
        ("adaptive_difficulty", "AdaptiveDifficulty", "Adaptive Difficulty Engineer", ["Invisible DDA systems", "Player skill profiling", "Real-time adjustment algorithms", "Defeat count tracking", "Success rate calibration", "Rubber-band prevention", "A/B difficulty testing", "Difficulty telemetry"]),
        ("assist_mode_designer", "AssistModeDesigner", "Assist Mode Designer", ["God mode implementation", "Slow motion toggle", "Aim assist calibration", "Skip encounter options", "Guided mode design", "Puzzle solution hints", "Navigation assistance", "One-hit kill options"]),
        ("enemy_scaling", "EnemyScaling", "Enemy Scaling Specialist", ["Level scaling formulas", "Stat curve per difficulty", "AI behavior per difficulty", "Attack pattern variation", "Health pool scaling", "Damage output scaling", "Reward scaling", "Elite/boss scaling"]),
        ("player_modeling", "PlayerModeling", "Player Skill Modeling Specialist", ["Kill/death analysis", "Completion time tracking", "Resource usage patterns", "Retry frequency analysis", "Item usage patterns", "Path choice analysis", "Combat style profiling", "Engagement metrics"]),
        ("accessibility_difficulty", "AccessDifficulty", "Accessibility Difficulty Designer", ["Motor impairment options", "Cognitive load reduction", "Visual clarity modes", "Audio-only play support", "One-handed control schemes", "Timing window expansion", "Auto-combo options", "Subtitle/caption options"]),
        ("reward_balance", "RewardBalance", "Difficulty-Reward Balance Designer", ["Risk/reward calibration", "Difficulty bonus rewards", "Challenge mode rewards", "No-damage bonuses", "Speed run incentives", "Style point scoring", "Difficulty achievement design", "Prestige reward tiers"]),
        ("onramp_designer", "OnrampDesigner", "Onramp & Tutorial Difficulty Designer", ["First 10 minutes pacing", "Tutorial combat difficulty", "Practice room design", "Difficulty recommendation quiz", "Genre familiarity detection", "Gradual mechanic introduction", "Safe failure spaces", "Contextual help triggers"]),
    ], "synergy": ["ai_director", "emotion_engine", "tutorial_architect", "analytics_nexus"]},
    "progression_systems": {"name": "ProgressionSystems", "color": "#6D28D9", "desc": "XP curves, leveling, prestige, mastery, unlock systems, power scaling", "specs": [
        ("xp_curve_designer", "XPCurveDesigner", "XP Curve Mathematician", ["Polynomial XP curves", "Logarithmic scaling", "Piecewise level functions", "XP source balancing", "Rest XP systems", "Group XP sharing", "Kill XP vs quest XP ratio", "Level cap design"]),
        ("prestige_architect", "PrestigeArchitect", "Prestige System Architect", ["Prestige reset design", "Prestige reward tiers", "Cosmetic prestige rewards", "Prestige stat bonuses", "Infinite prestige scaling", "Prestige leaderboards", "Seasonal prestige", "Cross-character prestige"]),
        ("mastery_designer", "MasteryDesigner", "Mastery System Designer", ["Weapon mastery tracks", "Skill mastery trees", "Class mastery paths", "Achievement mastery", "Collection mastery", "Challenge mastery", "Season mastery", "Legacy mastery"]),
        ("unlock_architect", "UnlockArchitect", "Unlock System Architect", ["Sequential unlocks", "Branch unlocks", "Achievement unlocks", "Collection unlocks", "Story unlocks", "Challenge unlocks", "Purchase unlocks", "Random unlock pools"]),
        ("power_curve_designer", "PowerCurveDesigner", "Power Curve Designer", ["Linear power growth", "Exponential power scaling", "Logarithmic power curve", "Power plateau design", "Catch-up mechanics", "Power ceiling management", "Horizontal power growth", "Vertical power growth"]),
        ("milestone_designer", "MilestoneDesigner", "Milestone & Celebration Designer", ["Level-up celebrations", "Achievement pop-ups", "Milestone reward screens", "Progress summary screens", "Completion percentages", "Journal/log updates", "Social share moments", "Rare milestone fanfares"]),
        ("parallel_progress", "ParallelProgress", "Parallel Progression Designer", ["Character level + gear level", "Account level + character level", "Seasonal + permanent", "PvE rank + PvP rank", "Story progress + side content", "Main class + alt class", "Guild progress + personal", "Reputation + skill"]),
        ("anti_grind", "AntiGrind", "Anti-Grind & Pacing Designer", ["Daily caps", "Weekly limits", "Rest bonuses", "Catch-up mechanics", "Alternative XP paths", "Exploration XP", "Achievement XP grants", "Story XP boosts"]),
    ], "synergy": ["metagame_ops", "character_architect", "economy_engine", "quest_engine"]},
    "reward_psychology": {"name": "RewardPsychology", "color": "#5B21B6", "desc": "Variable ratio reinforcement, dopamine loops, anticipation, loss aversion, FOMO management", "specs": [
        ("dopamine_architect", "DopamineArchitect", "Dopamine Loop Designer", ["Variable ratio schedules", "Near-miss design", "Anticipation building", "Surprise reward timing", "Streak reward systems", "First-time bonuses", "Return player rewards", "Random jackpot moments"]),
        ("loss_aversion_mgr", "LossAversionMgr", "Loss Aversion Manager", ["Penalty calibration", "Death penalty design", "Durability loss tuning", "Resource loss prevention", "Insurance mechanics", "Recovery systems", "Soft fail states", "Progress protection"]),
        ("collection_psychologist", "CollectionPsychologist", "Collection Psychology Designer", ["Completion percentage drive", "Set collection bonuses", "Rare item chase design", "Display case/trophy room", "Progress visualization", "Missing piece highlighting", "Trading card psychology", "Stamp/sticker collections"]),
        ("fomo_manager", "FOMOManager", "FOMO & Scarcity Designer", ["Ethical FOMO design", "Limited-time content planning", "Exclusive reward rotation", "Return event scheduling", "Archive/catch-up systems", "FOMO reduction strategies", "Player-first scarcity", "Transparency in exclusivity"]),
        ("social_reward", "SocialReward", "Social Reward Designer", ["Guild achievement rewards", "Team completion bonuses", "Social milestone rewards", "Mentorship rewards", "Community goal rewards", "Referral rewards", "Social showcase rewards", "Cooperative bonus multipliers"]),
        ("intrinsic_motivator", "IntrinsicMotivator", "Intrinsic Motivation Designer", ["Mastery satisfaction", "Autonomy in choices", "Purpose/narrative meaning", "Curiosity-driven rewards", "Self-expression rewards", "Competence feedback", "Relatedness rewards", "Creative expression rewards"]),
        ("surprise_delight", "SurpriseDelight", "Surprise & Delight Designer", ["Hidden rewards", "Easter egg rewards", "Random acts of generosity", "Seasonal surprise rewards", "Achievement secret tiers", "Dev room rewards", "Community event surprises", "Anniversary surprises"]),
        ("economy_psychology", "EconomyPsychology", "Economic Psychology Designer", ["Anchoring price effects", "Decoy pricing", "Bundle value perception", "Currency abstraction", "Sunk cost management", "Endowment effect design", "Scarcity value perception", "Social proof pricing"]),
    ], "synergy": ["emotion_engine", "monetization_lab", "analytics_nexus", "metagame_ops"]},
    "meta_game_design": {"name": "MetaGameDesign", "color": "#4C1D95", "desc": "Endgame, daily/weekly/seasonal loops, long-term engagement, content cadence", "specs": [
        ("daily_loop", "DailyLoop", "Daily Loop Architect", ["Daily quest rotation", "Daily login rewards", "Daily challenge design", "Daily shop rotation", "Daily dungeon/raid reset", "Daily bonus windows", "Daily crafting limits", "Daily social objectives"]),
        ("weekly_loop", "WeeklyLoop", "Weekly Loop Architect", ["Weekly quest chains", "Weekly bounties", "Weekly raid lockouts", "Weekly PvP seasons", "Weekly content releases", "Weekly shop rotation", "Weekly challenge modes", "Weekly community events"]),
        ("seasonal_architect", "SeasonalArchitect", "Seasonal Content Architect", ["Season theme design", "Battle pass structure", "Seasonal narrative arc", "Seasonal reward track", "Mid-season updates", "Season finale events", "Off-season content", "Year-end retrospectives"]),
        ("endgame_designer", "EndgameDesigner", "Endgame Systems Designer", ["Endgame gear grind", "Mythic+ difficulty scaling", "Endgame crafting depth", "Endgame PvP ranks", "Endgame exploration content", "Endgame social features", "Endgame challenge modes", "Endgame leaderboards"]),
        ("content_cadence", "ContentCadence", "Content Cadence Planner", ["Update frequency planning", "Content drought prevention", "Hype cycle management", "Patch size expectations", "Content preview strategy", "Beta/test realm timing", "Anniversary content", "Expansion cycle planning"]),
        ("retention_loop", "RetentionLoop", "Retention Loop Designer", ["7-day retention loop", "30-day retention loop", "90-day retention arc", "Return player re-hook", "Lapsed player revival", "Content discovery pacing", "Social retention hooks", "Collection retention drives"]),
        ("live_event", "LiveEvent", "Live Event Designer", ["World event design", "Limited-time modes", "Community challenge events", "Holiday event design", "Crossover event planning", "Raid race events", "Treasure hunt events", "PvP tournament events"]),
        ("engagement_metrics", "EngagementMetrics", "Engagement Metrics Designer", ["DAU/MAU tracking design", "Session length optimization", "Session frequency design", "Feature engagement funnels", "Content completion metrics", "Social engagement metrics", "Monetization engagement", "Churn risk indicators"]),
    ], "synergy": ["live_ops", "analytics_nexus", "economy_engine", "community_forge"]},
    "balance_philosophy": {"name": "BalancePhilosophy", "color": "#7E22CE", "desc": "Asymmetric balance, rock-paper-scissors, meta shifts, patch philosophy, power budgets", "specs": [
        ("asymmetric_balance", "AsymmetricBalance", "Asymmetric Balance Architect", ["Faction asymmetry", "Class role asymmetry", "Map asymmetry", "Weapon archetype balance", "Asymmetric objectives", "Hero/champion balance", "Vehicle balance", "Ability kit balance"]),
        ("counter_system", "CounterSystem", "Counter System Designer", ["Rock-paper-scissors design", "Soft counters vs hard counters", "Counter-play accessibility", "Counter information clarity", "Counter item design", "Counter ability design", "Counter strategy depth", "Counter adaptation pacing"]),
        ("meta_shift_mgr", "MetaShiftMgr", "Meta Shift Manager", ["Patch cadence planning", "Power creep management", "Nerf philosophy", "Buff philosophy", "Rework criteria", "Meta diversity goals", "Pro play vs casual balance", "Ban/pick data analysis"]),
        ("power_budget", "PowerBudget", "Power Budget Mathematician", ["Character power budgets", "Item power budgets", "Ability power budgets", "Talent/skill budgets", "Rune/enchant budgets", "Set bonus budgets", "Consumable budgets", "Event reward budgets"]),
        ("math_modeler", "MathModeler", "Combat Math Modeler", ["DPS calculation models", "TTK/TBK analysis", "Effective HP modeling", "Burst vs sustained DPS", "Crowd control duration", "Cooldown efficiency", "Resource efficiency", "Stat interaction modeling"]),
        ("pvp_balancer", "PvPBalancer", "PvP Balance Specialist", ["Ranked mode balance", "Casual mode balance", "Tournament balance patches", "Matchmaking fairness", "Win rate targets", "Pick rate analysis", "Ban rate interpretation", "Community sentiment analysis"]),
        ("pve_balancer", "PvEBalancer", "PvE Balance Specialist", ["Dungeon tuning", "Raid encounter tuning", "World content tuning", "Solo vs group balance", "Scaling formula tuning", "Boss health pools", "Add wave tuning", "Loot drop calibration"]),
        ("economy_balance", "EconomyBalance", "Economy Balance Designer", ["Currency inflation modeling", "Gold sink tuning", "Crafting cost balancing", "Repair cost calibration", "Vendor price curves", "Auction house fees", "Tax rate optimization", "Currency velocity management"]),
    ], "synergy": ["combat_forge", "character_architect", "analytics_nexus", "community_forge"]},
    "player_motivation": {"name": "PlayerMotivation", "color": "#9333EA", "desc": "SDT framework, Bartle types, player personas, motivation modeling, engagement drivers", "specs": [
        ("sdt_architect", "SDTArchitect", "Self-Determination Theory Architect", ["Autonomy support design", "Competence feedback loops", "Relatedness feature design", "Intrinsic motivation fostering", "Extrinsic motivation calibration", "Autonomy-supportive UI", "Competence visualization", "Social connection features"]),
        ("bartle_profiler", "BartleProfiler", "Player Type Profiler", ["Achiever content design", "Explorer content design", "Socializer feature design", "Killer/competitor design", "Hybrid type support", "Type detection algorithms", "Content recommendation per type", "Type-balanced content mix"]),
        ("engagement_driver", "EngagementDriver", "Engagement Driver Designer", ["Novelty introduction pacing", "Challenge escalation", "Social pressure calibration", "Collection motivation", "Story motivation", "Creative motivation", "Competitive motivation", "Cooperative motivation"]),
        ("churn_preventer", "ChurnPreventer", "Churn Prevention Specialist", ["Churn signal detection", "Re-engagement campaigns", "Exit survey design", "Win-back offers", "Content gap analysis", "Frustration point mitigation", "Social tether design", "Sunk cost leveraging (ethical)"]),
        ("persona_designer", "PersonaDesigner", "Player Persona Designer", ["Casual player persona", "Hardcore player persona", "Social player persona", "Competitive player persona", "Creative player persona", "Completionist persona", "Story-driven persona", "Whale persona (ethical)"]),
        ("goal_architect", "GoalArchitect", "Player Goal Architect", ["Short-term goal design", "Medium-term goal chains", "Long-term aspirational goals", "Personal goal tracking", "Shared goal systems", "Competing goal priorities", "Goal visibility design", "Goal achievement celebration"]),
        ("habit_designer", "HabitDesigner", "Habit Formation Designer", ["Cue-routine-reward loops", "Variable reward schedules", "Habit stacking mechanics", "Streak reward systems", "Notification timing", "Session start rituals", "Session end hooks", "Cross-session continuity"]),
        ("meaning_architect", "MeaningArchitect", "Meaningful Play Designer", ["Narrative meaning", "Social meaning", "Creative meaning", "Competitive meaning", "Collection meaning", "Discovery meaning", "Mastery meaning", "Legacy meaning"]),
    ], "synergy": ["emotion_engine", "analytics_nexus", "tutorial_architect", "community_forge"]},
    "emergent_gameplay": {"name": "EmergentGameplay", "color": "#A855F7", "desc": "System interaction, emergent narratives, player-driven content, sandbox mechanics", "specs": [
        ("system_interaction", "SystemInteraction", "System Interaction Designer", ["Fire + wind = firestorm", "Water + electricity = chain lightning", "Stealth + environment = distractions", "Physics + combat = environmental kills", "Weather + terrain = hazards", "AI + AI = faction wars", "Economy + crafting = player markets", "Social + combat = bounty systems"]),
        ("emergent_narrative", "EmergentNarrative", "Emergent Narrative Designer", ["Player-driven stories", "Faction war outcomes", "Dynamic world events", "NPC relationship emergence", "Economic narrative emergence", "Territory control stories", "Player legacy systems", "Historical record generation"]),
        ("sandbox_architect", "SandboxArchitect", "Sandbox Mechanics Architect", ["Building freedom", "Destruction freedom", "Terrain modification", "Object interaction depth", "Fluid simulation sandbox", "Electrical/mechanical systems", "Automation systems", "Creativity tool depth"]),
        ("simulation_depth", "SimulationDepth", "Simulation Depth Designer", ["Weather system depth", "Ecosystem simulation", "Economic simulation", "Political simulation", "Cultural simulation", "Technological simulation", "Geological simulation", "Astronomical simulation"]),
        ("player_expression", "PlayerExpression", "Player Expression Designer", ["Build diversity expression", "Visual customization expression", "Playstyle expression", "Housing/base expression", "Social expression", "Creative mode expression", "Performance expression", "Storytelling expression"]),
        ("unintended_play", "UnintendedPlay", "Unintended Play Embracer", ["Speedrun enablement", "Sequence break tolerance", "Exploit-to-feature conversion", "Community strategy recognition", "Glitch preservation", "Unintended combo celebration", "Out-of-bounds exploration rewards", "Meta-strategy support"]),
        ("dynamic_world", "DynamicWorld", "Dynamic World State Designer", ["Persistent world changes", "Player action consequences", "Resource depletion/renewal", "NPC memory systems", "Building/destruction persistence", "Season/time progression", "Faction territory shifts", "Price/market fluctuations"]),
        ("mod_emergence", "ModEmergence", "Modding & User Creation Designer", ["Modding API design", "Level editor access", "Script hook design", "Asset import pipeline", "Workshop/marketplace", "Featured mods system", "Mod compatibility management", "Official mod recognition"]),
    ], "synergy": ["physics_vault", "ai_director", "social_fabric", "procedural_genesis"]},
    "competitive_design": {"name": "CompetitiveDesign", "color": "#C084FC", "desc": "Ranked modes, elo systems, tournament design, esports features, spectator tools", "specs": [
        ("ranked_architect", "RankedArchitect", "Ranked System Architect", ["Rank tier design", "Placement match system", "Decay/inactivity rules", "Season reset calibration", "Rank floor protection", "Demotion shield design", "Promotion series", "Rank distribution goals"]),
        ("elo_mathematician", "EloMathematician", "Rating System Mathematician", ["Elo implementation", "Glicko-2 implementation", "TrueSkill implementation", "MMR vs display rank", "Uncertainty modeling", "Team MMR averaging", "Smurf detection", "Matchmaking queue optimization"]),
        ("tournament_designer", "TournamentDesigner", "Tournament System Designer", ["Single elimination", "Double elimination", "Swiss system", "Round robin", "Group stage design", "Bracket seeding", "Tiebreaker rules", "Prize distribution"]),
        ("esports_architect", "EsportsArchitect", "Esports Features Architect", ["Observer mode", "Caster tools", "Player cams", "Stats overlay", "Pick/ban phase", "Map veto system", "Team management", "League infrastructure"]),
        ("spectator_designer", "SpectatorDesigner", "Spectator Mode Designer", ["Free camera controls", "Player follow mode", "Replay timeline", "Slow motion replay", "Multi-view layout", "Stats HUD overlay", "Commentary integration", "Stream integration"]),
        ("anti_toxicity", "AntiToxicity", "Anti-Toxicity System Designer", ["Chat filter systems", "Voice chat moderation", "Behavior scoring", "Rehabilitation systems", "Positive reinforcement", "Honor/endorsement systems", "Report confidence scoring", "Tribunal/review systems"]),
        ("competitive_integrity", "CompetitiveIntegrity", "Competitive Integrity Specialist", ["Anti-cheat integration", "Input device fairness", "Cross-play balance", "Network advantage prevention", "Exploit rapid response", "Bug abuse policy", "Match fixing detection", "Account security"]),
        ("season_design", "SeasonDesign", "Competitive Season Designer", ["Season duration", "Rank reward tiers", "Season transition", "Placement reevaluation", "Off-season content", "Preseason changes", "Mid-season adjustments", "End-of-season events"]),
    ], "synergy": ["multiplayer_mesh", "analytics_nexus", "community_forge", "balance_philosophy"]},
    "cooperative_design": {"name": "CooperativeDesign", "color": "#D8B4FE", "desc": "Co-op mechanics, shared experiences, raid design, party systems, social bonds", "specs": [
        ("coop_mechanics", "CoopMechanics", "Cooperative Mechanics Designer", ["Shared objectives", "Role specialization", "Combo systems", "Revive mechanics", "Shared resources", "Split paths rejoining", "Asymmetric co-op roles", "Communication tools"]),
        ("raid_architect", "RaidArchitect", "Raid & Dungeon Co-op Architect", ["Encounter role requirements", "Mechanics communication", "DPS check calibration", "Heal check calibration", "Tank check calibration", "Puzzle collaboration", "Phase transitions", "Loot distribution"]),
        ("party_designer", "PartyDesigner", "Party System Designer", ["Party formation", "LFG/LFR systems", "Party size scaling", "Cross-realm parties", "Party chat", "Ready checks", "Party buffs", "Party composition guidance"]),
        ("social_bond", "SocialBond", "Social Bond Designer", ["Friendship XP systems", "Duo bonuses", "Guild cooperation rewards", "Mentor/mentee systems", "Wedding/partnership systems", "Shared housing", "Gift systems", "Legacy bonds"]),
        ("scaling_designer", "ScalingDesigner", "Co-op Scaling Designer", ["Enemy health scaling", "Reward scaling", "Difficulty adjustment", "Level sync systems", "Gear normalization", "Area level scaling", "Dynamic encounter scaling", "Solo to group transitions"]),
        ("communication_designer", "CommDesigner", "In-Game Communication Designer", ["Ping system design", "Emote wheels", "Quick chat presets", "Marking systems", "Minimap pings", "Voice line callouts", "Drawing tools", "Strategic planning tools"]),
        ("shared_world", "SharedWorld", "Shared World Designer", ["Seamless co-op transition", "Drop-in/drop-out design", "Session continuity", "World state synchronization", "Progress sharing rules", "Item sharing rules", "Territory co-ownership", "Base co-building"]),
        ("competitive_coop", "CompetitiveCoop", "Competitive Co-op Designer", ["Team vs team PvPvE", "Score attack co-op", "Timed challenge co-op", "Leaderboard teams", "Guild vs guild events", "Alliance warfare", "Competitive raid racing", "Co-op achievements"]),
    ], "synergy": ["multiplayer_mesh", "social_fabric", "combat_forge", "emotion_engine"]},
    "sandbox_design": {"name": "SandboxDesign", "color": "#E9D5FF", "desc": "Open-ended play, building, creation tools, player agency, world manipulation", "specs": [
        ("building_system", "BuildingSystem", "Building System Architect", ["Grid-based building", "Free-form building", "Snap points", "Structural integrity", "Material types", "Blueprint saving", "Building permissions", "Collaborative building"]),
        ("terrain_editing", "TerrainEditing", "Terrain Editing Designer", ["Raise/lower terrain", "Paint textures", "Plant vegetation", "Place water", "Erosion simulation", "Flatten tools", "Tunnel/cave creation", "Biome painting"]),
        ("automation_architect", "AutomationArchitect", "Automation System Designer", ["Conveyor belt systems", "Logic gate systems", "Redstone-style circuits", "Factory chains", "Farming automation", "Defense automation", "Resource routing", "Programming interfaces"]),
        ("creation_tools", "CreationTools", "Creation Tools Designer", ["Character creator depth", "Vehicle builder", "Weapon crafting visual", "Music composer tool", "Story editor", "Quest creator", "Map editor", "Scripting sandbox"]),
        ("physics_sandbox", "PhysicsSandbox", "Physics Sandbox Designer", ["Ragdoll sandbox", "Destruction sandbox", "Vehicle physics sandbox", "Fluid simulation sandbox", "Rope/chain physics", "Catapult/launcher design", "Zero gravity sandbox", "Time manipulation sandbox"]),
        ("world_rules", "WorldRules", "World Rules Designer", ["Day/night cycle control", "Weather control", "Gravity settings", "Speed settings", "Spawn rate control", "Difficulty sliders", "Game rule toggles", "Custom game modes"]),
        ("sharing_platform", "SharingPlatform", "Creation Sharing Designer", ["Upload system", "Download/subscribe", "Rating system", "Featured creations", "Category browsing", "Search/filter", "Version management", "Creator credits"]),
        ("sandbox_progression", "SandboxProgression", "Sandbox Progression Designer", ["Tool unlocks", "Material unlocks", "Area unlocks", "Capability unlocks", "Blueprint discovery", "Tech tree progression", "Creative mode access", "Mastery rewards"]),
    ], "synergy": ["procedural_genesis", "physics_vault", "community_forge", "puzzle_matrix"]},
})

# Generate remaining 20 categories with 30 domains each using compact format
# (Defining the remaining 270 domains across 9 more categories)

_DOMAIN_REGISTRY_RAW = {
    "art_visual": _cat("Art & Visual", "color-palette", "#EC4899", {
        "concept_art": {"name": "ConceptArt", "color": "#EC4899", "desc": "Visual development, mood exploration, character concepts, environment concepts", "specs": [("vis_dev", "VisDev", "Visual Development Lead", ["Silhouette design", "Color key painting", "Prop sheet creation", "Character turnarounds", "Environment callouts", "Material studies", "Scale reference sheets", "Style guide creation"]), ("mood_artist", "MoodArtist", "Mood & Atmosphere Artist", ["Color mood boards", "Lighting studies", "Time-of-day exploration", "Weather atmosphere", "Interior ambiance", "Biome color palettes", "Emotional color theory", "Cinematic mood frames"]), ("creature_concept", "CreatureConcept", "Creature Concept Artist", ["Anatomy variation design", "Creature silhouette exploration", "Scale comparison sheets", "Behavioral pose studies", "Evolutionary design logic", "Mythological creature adaptation", "Creature color language", "Creature expression sheets"]), ("vehicle_concept", "VehicleConcept", "Vehicle Concept Artist", ["Mechanical design language", "Vehicle silhouette variety", "Interior dashboard design", "Damage state concepts", "Customization variations", "Historical reference adaptation", "Sci-fi vehicle logic", "Fantasy mount concepts"]), ("weapon_concept", "WeaponConcept", "Weapon & Equipment Concept Artist", ["Weapon silhouette clarity", "Equipment tier visual progression", "Material differentiation", "Cultural weapon design", "Sci-fi weapon logic", "Fantasy weapon charm", "Consumable/potion design", "Tool/gadget concepts"]), ("ui_concept", "UIConcept", "UI Concept & Motion Artist", ["HUD layout exploration", "Menu flow concepts", "Icon design systems", "Font selection/pairing", "Color system design", "Animation concept storyboards", "Interactive element design", "Responsive layout concepts"]), ("marketing_art", "MarketingArt", "Marketing Art Director", ["Key art composition", "Store page asset creation", "Trailer storyboard art", "Social media asset design", "Press kit imagery", "Merchandise design concepts", "Event booth visual design", "Collector edition art"]), ("style_director", "StyleDirector", "Art Style Director", ["Style consistency enforcement", "Cross-team art reviews", "Outsource quality standards", "Art bible maintenance", "Style evolution guidelines", "Platform art adaptation", "Accessibility visual standards", "Cultural sensitivity review"])], "synergy": ["character_architect", "render_pipeline", "cinematic_studio"]},
        "environment_art": {"name": "EnvironmentArt", "color": "#DB2777", "desc": "World building visual, biome art, architectural styles, prop density, atmosphere", "specs": [("biome_artist", "BiomeArtist", "Biome Art Director", ["Desert biome visual language", "Forest biome variety", "Arctic/tundra atmosphere", "Volcanic/lava environments", "Underwater visual design", "Sky/cloud realm aesthetics", "Urban environment density", "Rural/pastoral warmth"]), ("arch_designer", "ArchDesigner", "Architectural Style Designer", ["Medieval castle architecture", "Sci-fi habitat design", "Fantasy tower design", "Ancient ruins authenticity", "Modern urban architecture", "Alien architecture logic", "Underground cavern design", "Floating island construction"]), ("prop_artist", "PropArtist", "Prop & Clutter Artist", ["Hero prop design", "Background prop density", "Interactive prop clarity", "Destruction state props", "Cultural prop authenticity", "Sci-fi prop functionality", "Natural debris/clutter", "Interior decoration props"]), ("terrain_artist", "TerrainArtist", "Terrain Art Specialist", ["Terrain texture blending", "Cliff face detailing", "Path/road texturing", "Water edge treatment", "Snow accumulation art", "Grass/foliage cards", "Rock formation variety", "Mud/dirt variation"]), ("lighting_artist", "LightingArtist", "Lighting Artist", ["Global illumination setup", "Time-of-day lighting", "Interior lighting moods", "Volumetric fog/god rays", "Neon/emissive lighting", "Candlelight/firelight", "Moonlight ambiance", "Dramatic shadow composition"]), ("skybox_artist", "SkyboxArtist", "Skybox & Celestial Artist", ["Cloud painting", "Sunset/sunrise gradients", "Star field composition", "Planet/moon placement", "Aurora design", "Storm cloud drama", "Night sky depth", "Alien sky design"]), ("foliage_artist", "FoliageArtist", "Foliage & Vegetation Artist", ["Tree variety design", "Bush/shrub cards", "Flower/plant detail", "Moss/lichen coverage", "Vine/ivy growth", "Crop/farm vegetation", "Alien flora design", "Seasonal foliage variation"]), ("material_artist", "MaterialArtist", "Material & Texture Artist", ["PBR material authoring", "Substance Designer workflows", "Trim sheet design", "Material layering", "Wear/damage materials", "Organic material creation", "Sci-fi panel materials", "Stylized material techniques"])], "synergy": ["render_pipeline", "weather_climate", "procedural_genesis"]},
        "character_art_3d": {"name": "CharacterArt3D", "color": "#F472B6", "desc": "3D character modeling, sculpting, texturing, rigging, hair/cloth art", "specs": [("char_modeler", "CharModeler", "Character 3D Modeler", ["High-poly sculpting", "Low-poly retopology", "UV unwrapping efficiency", "Texture baking workflows", "LOD model creation", "Blend shape modeling", "Accessory modeling", "Armor/clothing modeling"]), ("texture_painter", "TexturePainter", "Character Texture Painter", ["Skin texturing", "Clothing material painting", "Metal/leather texturing", "Hair card texturing", "Face detail painting", "Tattoo/scar overlays", "Emissive texture design", "Stylized paint techniques"]), ("hair_artist", "HairArtist", "Hair & Fur Artist", ["Hair card placement", "Hair simulation setup", "Beard/facial hair", "Fur/animal hair", "Fantasy hair design", "Physics hair tuning", "LOD hair reduction", "Hair color variation"]), ("cloth_artist", "ClothArtist", "Cloth & Fabric Artist", ["Cloth simulation setup", "Armor cloth underlay", "Cape/cloak design", "Dress/robe dynamics", "Belt/strap physics", "Flag/banner cloth", "Tent/sail fabric", "Damaged cloth tearring"]), ("rig_artist", "RigArtist", "Character Rig Artist", ["Skeleton hierarchy design", "Weight painting", "Facial rig setup", "Hand/finger rigging", "Tail/wing rigging", "Mechanical rig design", "Deformation correctives", "Rig optimization"]), ("vfx_char_artist", "VFXCharArtist", "Character VFX Artist", ["Aura/glow effects", "Transformation VFX", "Damage/status VFX", "Weapon trail effects", "Magic casting VFX", "Shield/barrier VFX", "Healing/buff VFX", "Death/dissolve VFX"]), ("tech_char_artist", "TechCharArtist", "Technical Character Artist", ["Shader setup per character", "Material instance management", "Skin subsurface scattering", "Eye shader setup", "Vertex animation", "Morph target management", "Performance budgeting", "Cross-platform char optimization"]), ("outsource_lead", "OutsourceLead", "Character Art Outsource Lead", ["Brief document creation", "Reference package assembly", "Quality gate definition", "Feedback iteration management", "Style guide communication", "Batch production planning", "Cost estimation", "Timeline management"])], "synergy": ["animation_studio", "character_architect", "render_pipeline"]},
    }),
    "audio_music": _cat("Audio & Music", "musical-notes", "#F59E0B", {
        "sound_design": {"name": "SoundDesign", "color": "#F59E0B", "desc": "SFX creation, foley, impact sounds, UI sounds, environmental audio", "specs": [("combat_sfx", "CombatSFX", "Combat Sound Designer", ["Sword clash layering", "Gun shot design", "Magic spell sounds", "Impact/hit sweeteners", "Shield block sounds", "Arrow/projectile whizz", "Explosion design", "Critical hit emphasis"]), ("env_sfx", "EnvSFX", "Environmental Sound Designer", ["Ambient bed design", "Water sounds variety", "Wind through foliage", "Cave reverb ambience", "City soundscape", "Forest life sounds", "Industrial machinery", "Weather sound layers"]), ("foley_artist", "FoleyArtist", "Foley Sound Artist", ["Footstep variation", "Cloth movement", "Armor/equipment clinks", "Door/gate sounds", "Item pickup sounds", "Food/eating sounds", "Writing/paper sounds", "Chain/rope sounds"]), ("ui_sfx", "UISFX", "UI Sound Designer", ["Button click satisfaction", "Menu transition swoosh", "Error/denial sounds", "Success/confirmation sounds", "Navigation sounds", "Tooltip sounds", "Loading sounds", "Achievement unlock fanfare"]), ("creature_sfx", "CreatureSFX", "Creature Sound Designer", ["Creature vocalization", "Monster roar design", "Insect/arachnid sounds", "Dragon breath sound", "Undead/ghost sounds", "Mechanical creature sounds", "Pet/companion sounds", "Boss intro sounds"]), ("vehicle_sfx", "VehicleSFX", "Vehicle Sound Designer", ["Engine loop design", "Tire/surface sounds", "Transmission shifts", "Horn/warning sounds", "Crash/collision sounds", "Wind at speed", "Hover/flight sounds", "Boat/water vehicle sounds"]), ("destruction_sfx", "DestructionSFX", "Destruction Sound Designer", ["Wood breaking layers", "Stone crumbling", "Metal deformation", "Glass shattering", "Fabric tearing", "Chain breaking", "Building collapse", "Explosion debris"]), ("spatial_audio_eng", "SpatialAudioEng", "Spatial Audio Engineer", ["HRTF positioning", "Reverb zone design", "Occlusion modeling", "Distance attenuation", "Height channels", "Doppler effect setup", "Reflection modeling", "Ambisonics mixing"])], "synergy": ["audio_sphere", "emotion_engine", "cinematic_studio"]},
        "music_composition": {"name": "MusicComposition", "color": "#D97706", "desc": "Original score, adaptive music, stems, orchestration, thematic development", "specs": [("composer", "Composer", "Lead Composer", ["Main theme composition", "Area-specific themes", "Boss battle music", "Exploration themes", "Menu/title music", "Victory fanfare", "Defeat/game over theme", "Credit roll composition"]), ("adaptive_music", "AdaptiveMusic", "Adaptive Music Systems Designer", ["Horizontal re-sequencing", "Vertical layering", "Stinger system", "Transition smoothing", "Combat intensity layers", "Stealth tension layers", "Exploration discovery cues", "Emotional state response"]), ("orchestrator", "Orchestrator", "Orchestration Specialist", ["String section writing", "Brass arrangement", "Woodwind coloring", "Percussion scoring", "Choir arrangement", "Solo instrument features", "Full orchestra balance", "Chamber ensemble writing"]), ("electronic_composer", "ElectronicComposer", "Electronic/Synth Composer", ["Synthesizer sound design", "Beat production", "Ambient texture creation", "Glitch/experimental sounds", "Retro/chiptune", "Dubstep/bass design", "Lo-fi hip-hop", "Cyberpunk soundscape"]), ("leitmotif_designer", "LeitmotifDesigner", "Leitmotif Designer", ["Character themes", "Location themes", "Faction themes", "Item/artifact themes", "Emotional leitmotifs", "Theme variation/development", "Thematic callbacks", "Subtle foreshadowing cues"]), ("world_music_advisor", "WorldMusicAdvisor", "World Music Cultural Advisor", ["East Asian instrumentation", "Middle Eastern scales/modes", "African rhythm patterns", "Celtic/Nordic folk", "Latin American rhythms", "Indian classical elements", "Southeast Asian gamelan", "Indigenous music respect"]), ("audio_director", "AudioDirector", "Audio Director", ["Audio vision document", "Music budget planning", "Recording session direction", "Mix supervision", "Implementation review", "Audio team coordination", "External composer management", "Audio milestone planning"]), ("mix_master", "MixMaster", "Mixing & Mastering Engineer", ["Dialog/music/SFX balance", "Dynamic range management", "Platform-specific mastering", "Loudness normalization", "Spatial mix positioning", "Bus routing/submixing", "Compression/limiting", "Final delivery formats"])], "synergy": ["audio_sphere", "emotion_engine", "cinematic_studio", "localization_hub"]},
    }),
    "programming_eng": _cat("Programming & Engineering", "code-slash", "#3B82F6", {
        "engine_architecture": {"name": "EngineArchitecture", "color": "#3B82F6", "desc": "Game engine design, ECS, rendering pipeline, asset pipeline, plugin systems", "specs": [("ecs_architect", "ECSArchitect", "Entity Component System Architect", ["Archetype-based storage", "Component query optimization", "System scheduling/ordering", "Parallel system execution", "Component change detection", "Entity lifecycle management", "Relationship components", "Singleton components"]), ("render_arch", "RenderArch", "Rendering Architecture Specialist", ["Deferred rendering pipeline", "Forward+ rendering", "Clustered lighting", "Render graph design", "GPU-driven rendering", "Bindless texture system", "Virtual texturing", "Frame graph optimization"]), ("asset_pipeline_eng", "AssetPipelineEng", "Asset Pipeline Engineer", ["Import pipeline design", "Cook/build system", "Hot reload implementation", "Asset reference tracking", "Streaming system design", "Bundle/pack system", "Version migration", "Dependency resolution"]), ("scripting_eng", "ScriptingEng", "Scripting System Engineer", ["Lua integration", "C# scripting", "Visual scripting graph", "Hot script reloading", "Sandbox security", "Performance profiling", "Debug/breakpoint support", "API documentation generation"]), ("plugin_architect", "PluginArchitect", "Plugin System Architect", ["Plugin API design", "Version compatibility", "Dependency management", "Hot load/unload", "Plugin marketplace", "Security sandboxing", "Performance isolation", "Documentation standards"]), ("build_system_eng", "BuildSystemEng", "Build System Engineer", ["Incremental compilation", "Distributed builds", "Platform cross-compilation", "Shader compilation", "Asset cooking pipeline", "Build caching strategy", "CI/CD integration", "Build time optimization"]), ("debug_tools_eng", "DebugToolsEng", "Debug & Tools Engineer", ["In-game console", "Visual debugger", "Performance profiler", "Memory debugger", "Network debugger", "AI debugger/visualizer", "Physics debug draw", "Replay system tools"]), ("platform_layer", "PlatformLayer", "Platform Abstraction Engineer", ["Graphics API abstraction", "Input API abstraction", "File system abstraction", "Network abstraction", "Audio API abstraction", "Thread abstraction", "Memory allocator abstraction", "Window management"])], "synergy": ["performance_forge", "render_pipeline", "physics_vault"]},
    }),
    "production_mgmt": _cat("Production & Management", "people", "#10B981", {
        "project_management": {"name": "ProjectManagement", "color": "#10B981", "desc": "Sprint planning, milestone management, resource allocation, risk management", "specs": [("sprint_planner", "SprintPlanner", "Sprint Planning Specialist", ["Sprint goal definition", "Story point estimation", "Capacity planning", "Sprint backlog curation", "Velocity tracking", "Burndown chart analysis", "Sprint retrospective facilitation", "Continuous improvement"]), ("milestone_planner", "MilestonePlanner", "Milestone Planning Specialist", ["Milestone definition", "Feature scope per milestone", "Demo preparation", "Milestone risk assessment", "Cross-team dependency mapping", "Go/no-go criteria", "Milestone review process", "Post-milestone analysis"]), ("risk_manager", "RiskManager", "Risk Management Specialist", ["Risk identification workshops", "Probability/impact assessment", "Mitigation strategy design", "Risk register maintenance", "Early warning indicators", "Contingency planning", "Risk communication", "Risk retrospectives"]), ("resource_planner", "ResourcePlanner", "Resource Planning Specialist", ["Team capacity modeling", "Skill gap identification", "Cross-training plans", "Contractor integration", "Peak load planning", "Vacation/leave management", "Knowledge transfer planning", "Succession planning"]), ("budget_manager", "BudgetManager", "Budget Management Specialist", ["Development cost tracking", "ROI forecasting", "Vendor cost management", "Tool license management", "Marketing budget allocation", "QA budget planning", "Localization cost planning", "Post-launch budget"]), ("stakeholder_mgr", "StakeholderMgr", "Stakeholder Management Specialist", ["Stakeholder mapping", "Communication plan design", "Executive reporting", "Publisher updates", "Board presentations", "Investor relations", "Press relationship management", "Community stakeholder engagement"]), ("outsource_mgr", "OutsourceMgr", "Outsource Management Specialist", ["Vendor evaluation", "Statement of work creation", "Quality benchmark definition", "Feedback loop design", "Cultural communication", "IP protection measures", "Cost negotiation", "Timeline coordination"]), ("agile_coach", "AgileCoach", "Agile Process Coach", ["Scrum implementation", "Kanban optimization", "Hybrid methodology design", "Team velocity improvement", "Impediment removal", "Cross-team coordination", "Process documentation", "Continuous improvement culture"])], "synergy": ["analytics_nexus", "community_forge", "live_ops"]},
    }),
    "qa_testing": _cat("QA & Testing", "shield-checkmark", "#14B8A6", {
        "functional_testing": {"name": "FunctionalTesting", "color": "#14B8A6", "desc": "Functional QA, regression testing, test case design, bug triage, playtesting", "specs": [("test_planner", "TestPlanner", "Test Planning Specialist", ["Test strategy document", "Test case prioritization", "Coverage matrix design", "Risk-based testing", "Regression test selection", "Test environment management", "Device matrix planning", "Platform-specific test plans"]), ("bug_hunter", "BugHunter", "Bug Hunter & Triage Specialist", ["Bug reproduction skills", "Severity classification", "Priority assessment", "Root cause hypothesis", "Regression identification", "Environment-specific bugs", "Intermittent bug tracking", "Bug fix verification"]), ("automation_eng", "AutomationEng", "Test Automation Engineer", ["UI automation frameworks", "API test automation", "Performance test automation", "CI/CD test integration", "Test data management", "Parallel test execution", "Flaky test management", "Test reporting dashboards"]), ("perf_tester", "PerfTester", "Performance Testing Specialist", ["Frame rate profiling", "Memory leak detection", "Load time measurement", "Network stress testing", "CPU/GPU profiling", "Heat/thermal testing", "Battery drain testing", "Storage I/O testing"]), ("compat_tester", "CompatTester", "Compatibility Testing Specialist", ["Device compatibility matrix", "OS version testing", "Graphics driver testing", "Peripheral compatibility", "Network condition testing", "Region-specific testing", "Accessibility compliance testing", "Store compliance verification"]), ("playtest_director", "PlaytestDirector", "Playtesting Director", ["Playtest session planning", "Player recruitment", "Session facilitation", "Observation techniques", "Feedback collection", "Data analysis", "Actionable recommendation generation", "Follow-up testing design"]), ("security_tester", "SecurityTester", "Security Testing Specialist", ["Penetration testing", "Vulnerability scanning", "Cheat detection testing", "API security testing", "Data privacy verification", "Encryption validation", "Input sanitization testing", "Network security testing"]), ("localization_qa", "LocalizationQA", "Localization QA Specialist", ["Linguistic accuracy", "Cultural appropriateness", "Text truncation detection", "Font rendering verification", "Audio sync verification", "RTL layout testing", "Placeholder validation", "Regional regulation compliance"])], "synergy": ["deployment_forge", "analytics_nexus", "security_vault"]},
    }),
    "marketing_community": _cat("Marketing & Community", "megaphone", "#F43F5E", {
        "brand_marketing": {"name": "BrandMarketing", "color": "#F43F5E", "desc": "Brand identity, trailer production, store optimization, influencer strategy", "specs": [("brand_architect", "BrandArchitect", "Brand Identity Architect", ["Logo design direction", "Color palette system", "Typography selection", "Voice & tone guidelines", "Brand messaging", "Visual identity system", "Brand asset library", "Brand consistency auditing"]), ("trailer_producer", "TrailerProducer", "Trailer & Video Producer", ["Announce trailer", "Gameplay trailer", "Launch trailer", "Update/patch trailer", "Character reveal trailer", "Story trailer", "Accolades trailer", "Community highlight reel"]), ("store_optimizer", "StoreOptimizer", "Store Page Optimizer", ["Screenshot selection", "Key art optimization", "Description copywriting", "Feature list curation", "Video placement strategy", "Rating/review management", "Localized store pages", "A/B test store elements"]), ("influencer_mgr", "InfluencerMgr", "Influencer Relations Manager", ["Creator identification", "Outreach strategy", "Key distribution", "Content guidelines", "Embargo management", "Relationship nurturing", "Performance tracking", "Creator event planning"]), ("social_media_mgr", "SocialMediaMgr", "Social Media Manager", ["Platform strategy per network", "Content calendar", "Community engagement", "Meme/viral content", "Crisis management", "Analytics reporting", "Paid social campaigns", "Influencer amplification"]), ("pr_specialist", "PRSpecialist", "Public Relations Specialist", ["Press release writing", "Media outreach", "Review copy management", "Press event planning", "Interview preparation", "Media training", "Embargo coordination", "Crisis communication"]), ("user_acquisition", "UserAcquisition", "User Acquisition Specialist", ["Ad creative design", "Target audience definition", "Campaign optimization", "CPI/CPA management", "Retargeting campaigns", "Cross-promotion", "Organic growth strategies", "Attribution modeling"]), ("community_builder", "CommunityBuilder", "Community Builder", ["Discord server management", "Forum moderation", "Community events", "Fan art programs", "Content creator programs", "Beta tester community", "Feedback collection systems", "Community health monitoring"])], "synergy": ["community_forge", "analytics_nexus", "monetization_lab"]},
    }),
    "narrative_writing": _cat("Narrative & Writing", "book", "#A855F7", {
        "world_building": {"name": "WorldBuilding", "color": "#A855F7", "desc": "World lore, cultural systems, history, geography, religions, political structures", "specs": [("world_architect", "WorldArchitect", "World Architecture Lead", ["Continental design", "Climate system design", "Geological history", "Ocean current influence", "Magical system geography", "Resource distribution", "Trade route design", "Border/frontier design"]), ("culture_designer", "CultureDesigner", "Cultural Systems Designer", ["Social hierarchy design", "Religious system creation", "Festival/tradition design", "Art/music culture", "Food/cuisine culture", "Architecture style per culture", "Language/dialect variation", "Clothing/fashion per culture"]), ("political_architect", "PoliticalArchitect", "Political Systems Architect", ["Government type design", "Power structure modeling", "Diplomacy systems", "War/peace dynamics", "Revolution mechanics", "Law/justice systems", "Economic policy design", "Propaganda systems"]), ("religion_designer", "ReligionDesigner", "Religious Systems Designer", ["Pantheon design", "Creation myth", "Afterlife concepts", "Religious practices", "Holy site design", "Heresy/schism design", "Prophecy systems", "Religious artifact lore"]), ("economics_lore", "EconomicsLore", "Economic Lore Designer", ["Trade good origins", "Currency history", "Guild/merchant systems", "Black market lore", "Resource scarcity narratives", "Economic collapse events", "Technological economic impact", "Inter-faction trade lore"]), ("military_lore", "MilitaryLore", "Military History Designer", ["Army structure/composition", "Famous battle design", "Military technology evolution", "Naval warfare history", "Siege warfare design", "Special forces lore", "War crime/atrocity sensitivity", "Peace treaty design"]), ("technology_lore", "TechnologyLore", "Technology Progression Designer", ["Tech tree narrative", "Invention origin stories", "Lost technology mysteries", "Forbidden technology", "Magitech fusion design", "Industrial revolution events", "Space age technology", "Post-apocalyptic tech"]), ("ecology_lore", "EcologyLore", "Ecological Lore Designer", ["Ecosystem relationships", "Extinction event lore", "Conservation narratives", "Magical ecosystem design", "Pollution/corruption lore", "Natural disaster history", "Symbiotic species lore", "Apex predator mythology"])], "synergy": ["lore_vault", "procedural_genesis", "narrative_loom"]},
    }),
    "multiplayer_social": _cat("Multiplayer & Social", "people-circle", "#06B6D4", {
        "social_systems": {"name": "SocialSystems", "color": "#06B6D4", "desc": "Social features, guilds, friends, chat, emotes, social spaces, relationships", "specs": [("guild_architect", "GuildArchitect", "Guild System Architect", ["Guild creation", "Rank/permission system", "Guild bank/storage", "Guild quests", "Guild leveling", "Guild achievements", "Alliance system", "Guild wars/territory"]), ("friend_system", "FriendSystem", "Friend System Designer", ["Friend request flow", "Best friend system", "Block/mute system", "Privacy controls", "Activity feed", "Online status", "Join game feature", "Cross-platform friends"]), ("chat_architect", "ChatArchitect", "Chat System Architect", ["Global chat channels", "Local/proximity chat", "Party/guild chat", "Whisper/DM system", "Chat moderation tools", "Chat filter system", "Emote/sticker system", "Chat history/logging"]), ("emote_designer", "EmoteDesigner", "Emote & Expression Designer", ["Universal emotes", "Purchasable emotes", "Context-triggered emotes", "Combo emotes", "Group emotes", "Seasonal emotes", "Achievement emotes", "Emote wheel design"]), ("social_space_designer", "SocialSpaceDesigner", "Social Space Architect", ["Hub/town design", "Player housing neighborhoods", "Guild halls", "Arena/colosseum", "Market/bazaar", "Tavern/inn social space", "Training grounds", "Seasonal event spaces"]), ("reputation_designer", "ReputationDesigner", "Reputation System Designer", ["Player karma system", "Trade reputation", "PvP reputation", "Community contribution", "Helper reputation", "Content creator reputation", "Mentor reputation", "Negative reputation consequences"]), ("matchmaking_social", "MatchmakingSocial", "Social Matchmaking Designer", ["LFG board system", "Activity finder", "Mentor matching", "Language-based matching", "Timezone matching", "Playstyle matching", "Skill-based team building", "Social recommendation engine"]), ("event_social", "EventSocial", "Social Event Designer", ["In-game concerts", "Dance parties", "Fashion shows", "Trivia events", "Scavenger hunts", "Community building projects", "Charity events", "Anniversary celebrations"])], "synergy": ["social_fabric", "multiplayer_mesh", "community_forge"]},
    }),
    "platform_distrib": _cat("Platform & Distribution", "cloud-upload", "#7C3AED", {
        "store_distribution": {"name": "StoreDistribution", "color": "#7C3AED", "desc": "Store submission, certification, regional distribution, pricing, launch logistics", "specs": [("steam_specialist", "SteamSpecialist", "Steam Distribution Specialist", ["Steamworks integration", "Store page optimization", "Community hub setup", "Workshop implementation", "Trading card design", "Achievement showcase", "Demo/beta configuration", "Sale event participation"]), ("console_submission", "ConsoleSubmission", "Console Submission Specialist", ["Sony submission process", "Microsoft submission process", "Nintendo submission process", "TRC/XR/Lotcheck compliance", "First-party feature integration", "Platform-specific optimization", "Certification issue resolution", "Patch submission workflow"]), ("mobile_distribution", "MobileDistribution", "Mobile Distribution Specialist", ["App Store optimization", "Google Play optimization", "Samsung Galaxy Store", "App review compliance", "In-app purchase setup", "Subscription management", "Push notification setup", "Deep link configuration"]), ("regional_launch", "RegionalLaunch", "Regional Launch Specialist", ["Launch timing per region", "Regional content compliance", "Local payment methods", "Regional marketing sync", "Language support per region", "Regional age rating", "Cultural launch events", "Regional community management"]), ("pricing_specialist", "PricingSpecialist", "Pricing Strategy Specialist", ["Launch pricing strategy", "Regional pricing parity", "Sale pricing tiers", "Bundle pricing", "DLC pricing", "Season pass pricing", "Free-to-play pricing", "Price increase communication"]), ("launch_coordinator", "LaunchCoordinator", "Launch Day Coordinator", ["Server capacity planning", "Press embargo timing", "Social media countdown", "Streamer/influencer sync", "Day-one patch readiness", "Monitoring dashboard setup", "Incident response team", "Post-launch hotfix readiness"]), ("digital_rights", "DigitalRights", "Digital Rights Manager", ["DRM strategy selection", "Always-online policy", "Offline mode design", "License management", "Family sharing setup", "Refund policy alignment", "Key distribution management", "Piracy impact assessment"]), ("physical_distribution", "PhysicalDistribution", "Physical Distribution Specialist", ["Disc manufacturing", "Collector edition contents", "Retail partnership", "Pre-order fulfillment", "Regional packaging", "Age rating stickers", "Manual/insert design", "Warehouse logistics"])], "synergy": ["deployment_forge", "legal_compliance", "monetization_lab"]},
    }),
}

# Merge all into the core design category and the raw registry
_ALL_RAW = {"core_design": CAT_CORE_DESIGN}
_ALL_RAW.update(_DOMAIN_REGISTRY_RAW)

# ═══════════════════════════════════════════════════════════════════════
# BUILD THE FULL DOMAIN MAP
# ═══════════════════════════════════════════════════════════════════════

HYPERSCALE_DOMAINS = {}
HYPERSCALE_CATEGORIES = {}
SYNERGY_WEB = {}

for cat_id, cat_data in _ALL_RAW.items():
    domain_ids = []
    for did, ddef in cat_data["domains"].items():
        specialists = {}
        for spec_tuple in ddef.get("specs", []):
            sid = spec_tuple[0]
            specialists[sid] = {
                "id": sid, "name": spec_tuple[1], "title": spec_tuple[2],
                "expertise": spec_tuple[3] if len(spec_tuple) > 3 else [],
                "deep_knowledge": spec_tuple[4] if len(spec_tuple) > 4 else {},
                "synergy_links": ddef.get("synergy", []),
            }
        HYPERSCALE_DOMAINS[did] = {
            "name": ddef["name"], "version": "v25.0",
            "icon": cat_data.get("icon", "cube"), "color": ddef.get("color", cat_data.get("color", "#666")),
            "description": ddef.get("desc", ""), "category": cat_id,
            "specialists": specialists,
        }
        SYNERGY_WEB[did] = ddef.get("synergy", [])
        domain_ids.append(did)

    HYPERSCALE_CATEGORIES[cat_id] = {
        "name": cat_data["name"], "icon": cat_data["icon"], "color": cat_data["color"],
        "domain_ids": domain_ids, "domain_count": len(domain_ids),
    }

# ═══════════════════════════════════════════════════════════════════════
# MERGE EXTENDED DOMAINS FROM SEEDS (277 additional domains)
# ═══════════════════════════════════════════════════════════════════════

_CAT_META = {
    "core_design":        ("Core Game Design",       "bulb",           "#8B5CF6"),
    "art_visual":         ("Art & Visual",           "color-palette",  "#EC4899"),
    "audio_music":        ("Audio & Music",          "musical-notes",  "#F59E0B"),
    "programming_eng":    ("Programming & Engineering", "code-slash",  "#3B82F6"),
    "production_mgmt":    ("Production & Management", "people",        "#10B981"),
    "qa_testing":         ("QA & Testing",           "shield-checkmark", "#14B8A6"),
    "marketing_community":("Marketing & Community",  "megaphone",      "#F43F5E"),
    "narrative_writing":  ("Narrative & Writing",    "book",           "#A855F7"),
    "multiplayer_social": ("Multiplayer & Social",   "people-circle",  "#06B6D4"),
    "platform_distrib":   ("Platform & Distribution","cloud-upload",   "#7C3AED"),
}

for cat_id, (cat_name, cat_icon, cat_color) in _CAT_META.items():
    ext_domains = generate_extended_domains(cat_id, cat_icon, cat_color)
    for did, ddata in ext_domains.items():
        if did not in HYPERSCALE_DOMAINS:  # avoid overwriting hand-crafted domains
            HYPERSCALE_DOMAINS[did] = ddata
            SYNERGY_WEB[did] = list({s for spec in ddata["specialists"].values() for s in spec.get("synergy_links", [])})
            if cat_id in HYPERSCALE_CATEGORIES:
                HYPERSCALE_CATEGORIES[cat_id]["domain_ids"].append(did)

# Recalculate domain counts
for cat_id in HYPERSCALE_CATEGORIES:
    HYPERSCALE_CATEGORIES[cat_id]["domain_count"] = len(HYPERSCALE_CATEGORIES[cat_id]["domain_ids"])


# ═══════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/status")
async def hyperscale_status():
    total_specs = sum(len(d["specialists"]) for d in HYPERSCALE_DOMAINS.values())
    total_expertise = sum(sum(len(s["expertise"]) for s in d["specialists"].values()) for d in HYPERSCALE_DOMAINS.values())
    total_synergy = sum(len(v) for v in SYNERGY_WEB.values())
    return {
        "system": "Hyperscale Domain Registry v25.0",
        "status": "FULLY_OPERATIONAL",
        "total_domains": len(HYPERSCALE_DOMAINS),
        "total_specialists": total_specs,
        "total_expertise_points": total_expertise,
        "total_synergy_connections": total_synergy,
        "categories": HYPERSCALE_CATEGORIES,
        "jeeves_synergy_focal": True,
        "domains": {
            did: {
                "name": d["name"], "color": d["color"], "category": d["category"],
                "specialist_count": len(d["specialists"]),
                "synergy_count": len(SYNERGY_WEB.get(did, [])),
            }
            for did, d in HYPERSCALE_DOMAINS.items()
        },
    }

@router.get("/category/{cat_id}")
async def get_hyperscale_category(cat_id: str):
    cat = HYPERSCALE_CATEGORIES.get(cat_id)
    if not cat:
        raise HTTPException(404, f"Category '{cat_id}' not found")
    domains = {did: {
        "name": HYPERSCALE_DOMAINS[did]["name"],
        "color": HYPERSCALE_DOMAINS[did]["color"],
        "description": HYPERSCALE_DOMAINS[did]["description"],
        "specialist_count": len(HYPERSCALE_DOMAINS[did]["specialists"]),
        "specialist_names": [s["name"] for s in HYPERSCALE_DOMAINS[did]["specialists"].values()],
    } for did in cat["domain_ids"] if did in HYPERSCALE_DOMAINS}
    return {"category": cat, "domains": domains}

@router.get("/domain/{domain_id}")
async def get_hyperscale_domain(domain_id: str):
    d = HYPERSCALE_DOMAINS.get(domain_id)
    if not d:
        raise HTTPException(404, f"Domain '{domain_id}' not found")
    return {
        "domain": {"id": domain_id, "name": d["name"], "version": d["version"], "color": d["color"], "description": d["description"], "category": d["category"]},
        "specialist_count": len(d["specialists"]),
        "specialists": d["specialists"],
        "synergy_links": SYNERGY_WEB.get(domain_id, []),
    }

@router.get("/synergy-web")
async def get_hyperscale_synergy():
    return {
        "system": "Hyperscale Synergy Web v25.0",
        "total_domains": len(HYPERSCALE_DOMAINS),
        "total_connections": sum(len(v) for v in SYNERGY_WEB.values()),
        "jeeves_is_focal_orchestrator": True,
        "web": {did: {"name": HYPERSCALE_DOMAINS[did]["name"], "connections": links, "count": len(links)} for did, links in SYNERGY_WEB.items()},
    }

@router.get("/jeeves-synergy")
async def get_jeeves_synergy():
    """Jeeves as the focal point — shows how all domains flow through Jeeves."""
    domains_by_cat = {}
    for cat_id, cat in HYPERSCALE_CATEGORIES.items():
        domains_by_cat[cat_id] = {
            "category": cat["name"],
            "domain_count": cat["domain_count"],
            "domains": [{"id": did, "name": HYPERSCALE_DOMAINS[did]["name"], "specialists": len(HYPERSCALE_DOMAINS[did]["specialists"])} for did in cat["domain_ids"] if did in HYPERSCALE_DOMAINS],
        }
    total_specs = sum(len(d["specialists"]) for d in HYPERSCALE_DOMAINS.values())
    return {
        "orchestrator": "Jeeves v25.0",
        "role": "Focal Synergy Orchestrator",
        "doctrine": "AAA Quality — Excruciating Detail — SOTA Mechanics — Maximal Retention — Exceptional Complexity",
        "total_domains_orchestrated": len(HYPERSCALE_DOMAINS),
        "total_specialists_commanded": total_specs,
        "synergy_web_connections": sum(len(v) for v in SYNERGY_WEB.values()),
        "categories_managed": domains_by_cat,
        "flow": "User → Jeeves → Domain Selection → Specialist Deployment → Cross-Domain Synergy → Build → Deploy → Ship",
    }
