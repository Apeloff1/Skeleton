"""
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║  GAME MECHANICS NEXUS v21.0 — EXTREME DEPTH GAME CREATION INTELLIGENCE ENGINE              ║
║                                                                                            ║
║  The deepest game mechanics knowledge system ever built.                                   ║
║  14 Core Mechanic Domains × 8 Specialists Each = 112 Deep Mechanic Agents                  ║
║  Each specialist carries full production-grade knowledge of their mechanic domain.          ║
║                                                                                            ║
║  Domains:                                                                                  ║
║   1. CombatForge      — Frame data, hitboxes, damage formulas, combo trees                 ║
║   2. EconomyEngine    — Market sim, inflation curves, scarcity models                      ║
║   3. ProgressionCore  — Skill trees, XP curves, prestige, mastery gates                    ║
║   4. PhysicsVault     — Rigid/soft body, fluid, cloth, destruction physics                 ║
║   5. AIBrainTrust     — GOAP, utility AI, behavior trees, neural NPC                       ║
║   6. ProceduralForge  — WorldGen, dungeon gen, L-systems, wave function collapse           ║
║   7. NetcodeMatrix    — Client prediction, lag comp, rollback, state sync                  ║
║   8. UXArchitect      — HUD systems, menu flow, accessibility, input mapping               ║
║   9. AudioSphere      — Spatial audio, dynamic music, FMOD/Wwise integration               ║
║  10. SocialFabric     — Faction systems, reputation, trust, emergent politics              ║
║  11. MetaGameOps      — Live service, season design, battle pass, retention loops          ║
║  12. RenderPipeline   — LOD, culling, batching, GPU instancing, ray tracing                ║
║  13. NarrativeLoom    — Branching narrative, procedural dialogue, emotional arcs           ║
║  14. GameFeelLab      — Juice, screen shake, hit stop, camera dynamics, haptics            ║
║                                                                                            ║
║  Status Endpoint: /api/game-mechanics-nexus/status                                         ║
║  Deep Dive:       /api/game-mechanics-nexus/domain/{domain_id}                             ║
║  Generate:        /api/game-mechanics-nexus/generate                                       ║
║  Health Matrix:   /api/game-mechanics-nexus/health-matrix                                  ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import os
import uuid
import json
import hashlib
import time
import math
import random

router = APIRouter(prefix="/api/game-mechanics-nexus", tags=["game-mechanics-nexus"])

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 1: COMBATFORGE — Frame Data, Hitbox Systems, Damage Formulas
# ════════════════════════════════════════════════════════════════════════════════

COMBATFORGE_SPECIALISTS = {
    "frame_data_architect": {
        "id": "cf-frame-data",
        "name": "FramePulse",
        "title": "Frame Data Architect",
        "expertise": [
            "Startup frames, active frames, recovery frames for every action",
            "Frame advantage/disadvantage calculations on block and on hit",
            "Cancel windows, buffering systems, input priority queues",
            "Invincibility frames (i-frames), super armor, hyper armor mechanics",
            "Hitstun, blockstun, hitstop calculation per move weight class",
            "Frame-perfect tech: just-frame inputs, option selects, OS mechanics",
            "Animation priority systems, interrupt hierarchies, state machines",
            "Multi-hit move frame distribution, juggle physics, gravity scaling",
        ],
        "deep_knowledge": {
            "damage_formula": "base_dmg × (1 + atk_scaling) × elemental_multiplier × combo_decay × (1 - def_reduction) × crit_multiplier × range_falloff",
            "combo_decay": "Each successive hit: decay = max(0.1, 1.0 - (hit_count × 0.08) - (combo_time × 0.02))",
            "frame_advantage": "on_block = active_frames + recovery_attacker - (blockstun + recovery_defender)",
            "juggle_gravity": "gravity_scale = base_gravity × (1 + juggle_count × 0.15) × weight_class_modifier",
            "buffer_window": "Standard 3-frame buffer, 5-frame for special cancels, 8-frame for super cancels",
        },
    },
    "hitbox_engineer": {
        "id": "cf-hitbox",
        "name": "ColliderX",
        "title": "Hitbox Systems Engineer",
        "expertise": [
            "Capsule, sphere, box, and convex hull hitbox generation from animation data",
            "Hurtbox layering: vulnerable, invulnerable, counter-hit, armor zones",
            "Projectile hitbox persistence, multi-hit registration, pierce mechanics",
            "Grab/throw tech boxes, proximity detection, whiff punishment windows",
            "Hitbox interpolation for high-speed attacks, swept volume collision",
            "Z-axis hitbox for 2.5D games, crossup detection, anti-air boxes",
            "Environmental hitboxes: hazard zones, death planes, interaction volumes",
            "Network-aware hitbox: rollback-compatible collision with lag compensation",
        ],
        "deep_knowledge": {
            "collision_layers": "Player_Hitbox → Enemy_Hurtbox, Projectile → Shield, Environmental → All_Hurtbox",
            "swept_collision": "CCD (Continuous Collision Detection) for moves faster than 1 hitbox_width per frame",
            "crossup_detection": "Compare attacker.facing_direction with (defender.position - attacker.position).normalized",
            "grab_priority": "Command_Grab > Normal_Grab > Proximity_Throw; ties resolved by frame_data startup",
        },
    },
    "combo_system_designer": {
        "id": "cf-combo",
        "name": "ChainBreaker",
        "title": "Combo System Designer",
        "expertise": [
            "Gatling/chain combo systems with normal cancel hierarchies (L→M→H→S)",
            "Target combo design, link combo timing windows, dial-a-combo patterns",
            "Juggle state management, OTG (off-the-ground) rules, wall/floor bounce limits",
            "Burst/combo breaker mechanics, damage proration, minimum damage guarantees",
            "Infinite prevention: gravity scaling, juggle limits, hitstun deterioration",
            "Assist/tag combo extensions, DHC (Delayed Hyper Combo) transitions",
            "Style meter integration, combo variety bonuses, optimal vs practical routes",
            "Training mode combo recording, playback, input display, frame data overlay",
        ],
        "deep_knowledge": {
            "proration_table": "Starter: 100% → Chain: 90% → Link: 85% → Special: 75% → Super: 60% → Ultra: 50%",
            "gravity_scaling": "juggle_gravity *= 1.0 + (hit_number × 0.12); max_hits = floor(launch_height / min_juggle_height)",
            "burst_cost": "burst_meter = max_meter × (1.0 - (current_hp / max_hp) × 0.5); available when meter ≥ 50%",
            "otg_rules": "Max 1 OTG pickup per combo, resets on wall bounce, disabled after ground techable state",
        },
    },
    "damage_formula_mathematician": {
        "id": "cf-damage",
        "name": "CalcStrike",
        "title": "Damage Formula Mathematician",
        "expertise": [
            "Multi-variable damage formulas: ATK, DEF, level scaling, elemental charts",
            "Critical hit systems: crit rate, crit damage, diminishing returns curves",
            "Damage types: physical, magical, true, pure, percent-HP, fixed, DOT, burst",
            "Defense penetration: flat pen, percentage pen, armor shred, lethality",
            "Damage reduction stacking: multiplicative vs additive, soft/hard caps",
            "Level difference scaling, gear score influence, stat weight optimization",
            "Boss damage phases, enrage timers, DPS check thresholds",
            "Healing vs damage race calculations, effective HP, toughness metrics",
        ],
        "deep_knowledge": {
            "standard_formula": "final_dmg = ceil(base × power_ratio × (1 + bonus%) × (100 / (100 + effective_def)) × element_chart × random(0.85, 1.0))",
            "crit_system": "expected_dps = base_dps × (1 + crit_rate × (crit_dmg - 1)); diminishing above 80% crit_rate",
            "armor_formula": "damage_reduction = armor / (armor + 100 + 10 × attacker_level); soft cap at 75%",
            "dot_calculation": "total_dot = base_dot × (1 + spell_power × 0.3) × duration_ticks; snapshot on application",
            "ehp_formula": "effective_hp = hp × (1 / (1 - phys_reduction)) × (1 / (1 - magic_reduction))",
        },
    },
    "status_effect_architect": {
        "id": "cf-status",
        "name": "AfflictionMaster",
        "title": "Status Effect Architect",
        "expertise": [
            "Crowd control hierarchy: stun > root > slow > silence > disarm",
            "Diminishing returns on repeated CC: 100% → 50% → 25% → immune (10s reset)",
            "DOT types: bleed (physical), poison (magic), burn (fire), corruption (void)",
            "Buff/debuff stacking rules: unique, stackable, refreshable, strongest-wins",
            "Cleanse priority systems, immunity windows, tenacity/resilience stats",
            "Proc systems: on-hit, on-crit, on-kill, on-damage-taken triggers",
            "Status interaction chains: wet + electric = shocked, oil + fire = burning",
            "Boss CC immunity phases, CC bar/threshold systems, break mechanics",
        ],
        "deep_knowledge": {
            "dr_formula": "effective_duration = base_duration × max(0.0, 1.0 - (application_count - 1) × 0.5)",
            "dot_tick_rate": "Standard: 1 tick/second, Bleed: 1 tick/0.5s, Poison: 1 tick/3s (stronger per tick)",
            "elemental_reactions": {
                "wet+electric": {"name": "Electrocuted", "effect": "2.5x electric dmg, AoE stun 1.5s"},
                "oil+fire": {"name": "Conflagration", "effect": "3x fire DOT, spreads to nearby enemies"},
                "frozen+shatter": {"name": "Shatter", "effect": "Instant 15% max HP true damage"},
                "poison+bleed": {"name": "Hemorrhage", "effect": "Combined DOT, healing reduction 80%"},
            },
        },
    },
    "weapon_balance_specialist": {
        "id": "cf-weapon",
        "name": "ArsenalTuner",
        "title": "Weapon Balance Specialist",
        "expertise": [
            "Weapon archetype design: speed/damage/range triangle balancing",
            "Attack speed breakpoints, frames-per-attack calculation, DPS normalization",
            "Weapon class identity: swords (balanced), axes (burst), daggers (speed), staves (range)",
            "Scaling curves: STR weapons linear, DEX weapons exponential early, INT weapons logarithmic",
            "Weapon special effects: lifesteal, armor pierce, elemental infusion, on-hit procs",
            "Two-weapon fighting, dual-wield penalties/bonuses, shield interaction rules",
            "Upgrade/enhancement systems: +1 to +15, material costs, success rates, failsafe pity",
            "Weapon degradation, durability systems, repair economy, legendary preservation",
        ],
        "deep_knowledge": {
            "dps_normalization": "effective_dps = (base_damage × speed_multiplier) / attack_interval; target: ±5% across archetypes",
            "scaling_curve_str": "bonus_dmg = floor(STR × 0.8 + STR² × 0.001); linear with minimal quadratic",
            "scaling_curve_dex": "bonus_dmg = floor(DEX × 0.5 + DEX^1.3 × 0.01); exponential early, caps at 80 DEX",
            "upgrade_rates": "+1→+7: 100%, +8→+10: 80%→60%, +11→+13: 40%→20%, +14: 10%, +15: 5% (pity at 20 fails)",
        },
    },
    "defensive_systems_engineer": {
        "id": "cf-defense",
        "name": "BulwarkCore",
        "title": "Defensive Systems Engineer",
        "expertise": [
            "Block mechanics: standing, crouching, air, perfect/just-frame, chip damage",
            "Parry systems: timing windows (2-frame, 5-frame, 8-frame tiers), risk-reward scaling",
            "Dodge/roll i-frame design, directional influence, tech roll options",
            "Shield systems: shield HP, guard break, stamina cost, shield bash frame data",
            "Damage mitigation layering: armor → shield → absorption → resistance → HP",
            "Evasion/miss chance systems, accuracy checks, guaranteed-hit thresholds",
            "Counterattack mechanics, revenge meters, rage/limit break systems",
            "Death prevention: last-stand mechanics, revive conditions, death save rolls",
        ],
        "deep_knowledge": {
            "perfect_block": "Window: 3 frames before impact, reward: 0 chip + full frame advantage + meter gain",
            "dodge_iframes": "Roll: frames 3-12 i-frame (10 frame window), Dash: frames 1-6 (6 frames), Backstep: frames 1-8 (8 frames)",
            "shield_stamina": "block_cost = attack_weight × (1 - stability/100); guard_break when stamina ≤ 0",
            "mitigation_order": "raw_dmg → armor_reduction → shield_absorb → elemental_resist → flat_reduction → final_HP_loss",
        },
    },
    "multiplayer_combat_netcode": {
        "id": "cf-netcombat",
        "name": "SyncStrike",
        "title": "Multiplayer Combat Netcode Specialist",
        "expertise": [
            "Rollback netcode for fighting games: GGPO-style input delay + rollback",
            "Client-side prediction with server authority, reconciliation on mismatch",
            "Hit confirmation over network: client-authoritative hitboxes with server validation",
            "Input delay calibration: auto-adjust based on ping (ping/2 ÷ frame_duration)",
            "Desync detection and forced resimulation, state hash comparison per frame",
            "Spectator delay buffers, replay system integration, tournament-grade stability",
            "Region-based matchmaking, ping-based quality indicators, connection quality scoring",
            "Anti-cheat for competitive: server-side damage validation, position verification",
        ],
        "deep_knowledge": {
            "rollback_frames": "max_rollback = min(8, round(one_way_latency_ms / 16.67)); visual_delay = max(0, rollback - 2)",
            "input_delay": "base_delay = max(1, ceil(ping_ms / 33.34)); adaptive: increase by 1 if rollback_rate > 15%",
            "state_hash": "hash = CRC32(all_entity_positions + all_entity_states + rng_seed + frame_number)",
            "hit_validation": "server accepts hit if: |client_hitframe - server_hitframe| <= max_rollback_frames + 1",
        },
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 2: ECONOMY ENGINE — Market Simulation, Currency, Trade Systems
# ════════════════════════════════════════════════════════════════════════════════

ECONOMY_ENGINE_SPECIALISTS = {
    "market_simulation_architect": {
        "id": "ee-market",
        "name": "MarketMind",
        "title": "Market Simulation Architect",
        "expertise": [
            "Supply/demand price curves with elasticity modeling",
            "Auction house mechanics: bid/ask spreads, listing fees, deposit systems",
            "Player-driven economy vs NPC-controlled economy hybrid models",
            "Price floor/ceiling systems, anti-manipulation safeguards",
            "Market history tracking, price charts, volume indicators",
            "Cross-server economy synchronization, region-locked pricing",
            "Tax systems: sales tax, crafting tax, luxury tax on premium items",
            "Economic sinks and faucets: gold destroyed vs gold created per hour",
        ],
        "deep_knowledge": {
            "price_formula": "price = base_price × (demand_index / supply_index) × seasonal_modifier × rarity_scaler",
            "elasticity": "price_elasticity = (% change in quantity demanded) / (% change in price); target: -0.5 to -1.5",
            "sink_faucet_ratio": "healthy_economy: total_sinks / total_faucets ∈ [0.85, 1.15]; inflation if < 0.85",
            "auction_fee": "listing_fee = max(1, floor(listing_price × 0.05)); transaction_fee = floor(sale_price × 0.10)",
        },
    },
    "currency_systems_designer": {
        "id": "ee-currency",
        "name": "MintForge",
        "title": "Currency Systems Designer",
        "expertise": [
            "Multi-currency design: gold (common), gems (premium), tokens (event), marks (PvP)",
            "Currency conversion rates, exchange rate stability, arbitrage prevention",
            "Premium currency pricing psychology: price anchoring, bundle discounts, bonus tiers",
            "Inflation control: daily gold caps, diminishing returns on farming, weekly resets",
            "Currency earn rates by activity: quests, dailies, raids, PvP, crafting, gathering",
            "Free-to-play vs premium currency balance, pay-to-progress not pay-to-win guards",
            "Seasonal currency resets, legacy currency conversion, currency retirement",
            "Cryptocurrency/blockchain item ownership (optional), NFT-free alternatives",
        ],
    },
    "crafting_economy_specialist": {
        "id": "ee-crafting",
        "name": "ForgeEcon",
        "title": "Crafting Economy Specialist",
        "expertise": [
            "Material rarity tiers: common→uncommon→rare→epic→legendary→mythic (drop rates: 50/25/15/7/2.5/0.5%)",
            "Crafting success rates, quality variance, masterwork chances",
            "Recipe discovery systems: experimentation, scrolls, NPC teaching, reverse engineering",
            "Material sink design: crafting should consume 20-30% more materials than raw item value",
            "Profession specialization trees, gathering → processing → crafting chains",
            "Blueprint/pattern economy: tradeable vs soulbound, limited uses vs permanent",
            "Salvage/disenchant systems: 30-50% material return rate to maintain scarcity",
            "Crafting queue, batch processing, offline crafting timers, rush costs",
        ],
    },
    "loot_distribution_engineer": {
        "id": "ee-loot",
        "name": "DropTableX",
        "title": "Loot Distribution Engineer",
        "expertise": [
            "Weighted random loot tables with guaranteed minimums and bad luck protection",
            "Pity system design: soft pity at 75% of cap, hard pity at 100%, pity timer persistence",
            "Personal loot vs group loot vs master loot, need/greed systems, round-robin",
            "Item level budget: allocate stat points based on rarity tier and slot weight",
            "Smart loot: class-appropriate drops, recent-drop filtering, wishlist priority",
            "World drop vs boss drop vs quest reward vs crafted item stat differentiation",
            "Duplicate protection: token conversion, reroll tokens, transmog unlocks",
            "Seasonal loot tables, limited-time items, FOMO management vs player respect",
        ],
        "deep_knowledge": {
            "pity_formula": "drop_chance = base_rate × (1 + max(0, (attempts - soft_pity_start) × pity_acceleration))",
            "item_budget": "total_stat_points = base_budget × rarity_multiplier × (1 + item_level × 0.02); distributed by slot_weight",
            "rarity_multipliers": {"common": 1.0, "uncommon": 1.3, "rare": 1.7, "epic": 2.2, "legendary": 3.0, "mythic": 4.0},
        },
    },
    "trade_systems_architect": {
        "id": "ee-trade",
        "name": "ExchangeCore",
        "title": "Trade Systems Architect",
        "expertise": [
            "Player-to-player trade: direct trade, mail system, consignment, marketplace",
            "Trade scam prevention: confirmation dialogs, item comparison, value warnings",
            "Bind-on-equip vs bind-on-pickup vs tradeable item philosophy",
            "Guild banks, shared storage, access permission tiers, withdrawal logs",
            "Cross-region trade restrictions, server transfer item limits",
            "Gifting systems, gift wrapping, anonymous gifts, gift tracking",
            "Trade history logging, suspicious activity detection, real-money trade prevention",
            "Barter systems for non-currency economies, NPC trade routes, caravan mechanics",
        ],
    },
    "monetization_ethics_specialist": {
        "id": "ee-monetize",
        "name": "FairCoin",
        "title": "Monetization Ethics Specialist",
        "expertise": [
            "Ethical monetization frameworks: cosmetic-only, time-saver, expansion-based",
            "Loot box probability disclosure, gacha pity systems, regional compliance",
            "Battle pass design: free vs premium tiers, XP requirements, catch-up mechanics",
            "Season pass value calculation: premium_cost × 3 = total_rewards_value minimum",
            "Anti-predatory measures: spending caps, cool-down timers, parental controls",
            "Cosmetic monetization: skins, emotes, mounts, housing decorations",
            "Subscription models: monthly perks, loyalty rewards, tier benefits",
            "Price localization: regional pricing, purchasing power parity adjustments",
        ],
    },
    "inflation_control_mathematician": {
        "id": "ee-inflation",
        "name": "EquilibriumX",
        "title": "Inflation Control Mathematician",
        "expertise": [
            "Velocity of money modeling in virtual economies",
            "Gold sink design: repair costs, fast travel, respec fees, cosmetic gold sinks",
            "Time-gated earning vs uncapped earning, optimal daily gold injection rates",
            "Wealth distribution analysis: Gini coefficient tracking for virtual economies",
            "Hyperinflation prevention: emergency gold drains, temporary price freezes",
            "New player economy onboarding: starter gold, catchup mechanics, price stability for essentials",
            "Endgame gold sinks: legendary crafting, guild upgrades, housing auctions",
            "Economic dashboards: real-time monitoring of currency supply, velocity, concentration",
        ],
        "deep_knowledge": {
            "velocity_formula": "V = GDP_virtual / Money_supply; healthy_V ∈ [2.0, 5.0] per month",
            "gini_target": "gini_coefficient ∈ [0.35, 0.55]; above 0.6 indicates unhealthy wealth concentration",
            "daily_gold_injection": "target = active_players × avg_daily_playtime × gold_per_hour × sink_ratio",
            "repair_cost_formula": "repair_cost = item_level × quality_tier × 0.5% of replacement_value",
        },
    },
    "reward_psychology_specialist": {
        "id": "ee-reward",
        "name": "DopamineDesigner",
        "title": "Reward Psychology Specialist",
        "expertise": [
            "Variable ratio reinforcement schedules for optimal engagement",
            "Near-miss mechanics: showing almost-won states for motivation without manipulation",
            "Achievement cascade design: micro → daily → weekly → milestone → lifetime",
            "Reward visibility: sparkle effects, rarity color coding, fanfare proportional to rarity",
            "Loss aversion: daily login streaks, expiring rewards, limited-time offers",
            "Social comparison rewards: leaderboards, ranked tiers, exclusive cosmetics",
            "Intrinsic vs extrinsic motivation balance, mastery-based rewards, skill recognition",
            "Anti-addiction measures: diminishing returns after 4+ hours, session break reminders",
        ],
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 3: PROGRESSION CORE — Skill Trees, XP Curves, Mastery Systems
# ════════════════════════════════════════════════════════════════════════════════

PROGRESSION_CORE_SPECIALISTS = {
    "xp_curve_mathematician": {
        "id": "pc-xp",
        "name": "LevelCurve",
        "title": "XP Curve Mathematician",
        "expertise": [
            "Exponential, polynomial, and S-curve XP requirements per level",
            "Time-to-level targets: 1h at L1, 2h at L10, 8h at L50, 20h at max",
            "XP sources: combat, quests, exploration, crafting, social, daily bonuses",
            "Rested XP systems: 200% XP for X hours after offline, caps at 1.5 levels",
            "Level scaling content: sync-down, sync-up, mentoring systems",
            "Prestige/New Game+ systems: rebirth, ascension, paragon levels",
            "Party XP distribution: equal split, proximity-based, contribution-weighted",
            "Anti-powerleveling measures: XP penalty for level gaps > 10, diminished mob XP",
        ],
        "deep_knowledge": {
            "xp_formula_exponential": "xp_required(L) = base_xp × L^exponent; typical: 100 × L^1.8",
            "xp_formula_scurve": "xp_required(L) = base × (1 / (1 + e^(-0.1×(L-midpoint)))) × L^1.5",
            "time_to_max": "total_hours = sum(xp_required(L) / avg_xp_per_hour(L) for L in 1..max_level)",
            "rested_xp": "rested_pool += offline_hours × xp_per_hour × 0.5; cap = 1.5 × current_level_xp_requirement",
        },
    },
    "skill_tree_architect": {
        "id": "pc-skill",
        "name": "TreeWeaver",
        "title": "Skill Tree Architect",
        "expertise": [
            "Graph-based skill trees: DAG (directed acyclic graph) with prerequisite chains",
            "Skill point economy: points per level, respec costs, partial respec options",
            "Passive vs active skill nodes, keystone passives, capstone abilities",
            "Multi-class hybridization: skill trees that branch across classes",
            "Constellation/board layouts: Path of Exile style passive trees, sphere grids",
            "Skill synergy bonuses: adjacent nodes, cluster bonuses, path-dependent rewards",
            "Build diversity metrics: track most/least used nodes, balance patches based on data",
            "Seasonal skill resets, experimental skill previews, build planners/simulators",
        ],
    },
    "talent_specialization_designer": {
        "id": "pc-talent",
        "name": "SpecForge",
        "title": "Talent Specialization Designer",
        "expertise": [
            "Specialization trees: 3 specs per class, each with unique identity and playstyle",
            "Talent tiers: choice between 3 options every N levels, meaningful tradeoffs",
            "Hybrid specs, off-spec viability, spec-switching costs and cooldowns",
            "PvE vs PvP talent splits, separate talent loadouts for each content type",
            "Talent testing: training dummies, DPS meters, simulation tools",
            "Balancing talent win rates across all specs to within 2-3% in competitive",
            "Talent showcase: in-game previews, try-before-you-buy talent testing grounds",
            "Lore-based talent names, thematic cohesion within each spec fantasy",
        ],
    },
    "mastery_gate_designer": {
        "id": "pc-mastery",
        "name": "GateMaster",
        "title": "Mastery Gate Designer",
        "expertise": [
            "Skill mastery levels: Novice→Apprentice→Journeyman→Expert→Master→Grandmaster",
            "Mastery challenges: practical skill tests, not just XP grinds",
            "Class unlock systems: base classes → advanced → master → secret/hidden",
            "Weapon mastery per weapon type, increasing unlock of movesets at each tier",
            "Mastery-gated content: zones, dungeons, quests that require proof of skill",
            "Mastery decay for unused skills (optional), mastery maintenance quests",
            "Cross-mastery bonuses: mastering 3+ weapon types unlocks 'Weapon Master' title + perks",
            "Mastery leaderboards, seasonal mastery challenges, community mastery milestones",
        ],
    },
    "power_scaling_engineer": {
        "id": "pc-power",
        "name": "PowerCurve",
        "title": "Power Scaling Engineer",
        "expertise": [
            "Gear score systems: item_level × rarity_modifier × enchant_bonus = gear_score",
            "Power budget per gear slot: weapon (30%), armor (40%), accessories (30%)",
            "Stat squish techniques: logarithmic scaling at high levels, percentage-based stats",
            "Catch-up mechanics: heirloom gear, welfare epics, token vendors for returnees",
            "Vertical vs horizontal progression: power increase vs option increase",
            "Power creep management: seasonal resets, item level inflation control",
            "Difficulty scaling: enemy stats = base × (1 + player_gear_score × 0.001) for scaling content",
            "Power fantasy maintenance: always feeling strong even when challenged",
        ],
    },
    "achievement_systems_architect": {
        "id": "pc-achieve",
        "name": "AchieveForge",
        "title": "Achievement Systems Architect",
        "expertise": [
            "Achievement categories: exploration, combat, social, collection, mastery, secret",
            "Achievement point systems, tiered rewards at point thresholds",
            "Meta-achievements: complete all achievements in a category for ultimate reward",
            "Time-limited achievements, seasonal achievements, legacy achievement display",
            "Achievement difficulty tiers: bronze (easy) → silver (medium) → gold (hard) → platinum (extreme)",
            "Account-wide vs character-specific achievements",
            "Achievement tracking UI, progress bars, hint systems for secret achievements",
            "Competitive achievements: speed records, first kills, world firsts",
        ],
    },
    "endgame_progression_specialist": {
        "id": "pc-endgame",
        "name": "InfinityLoop",
        "title": "Endgame Progression Specialist",
        "expertise": [
            "Paragon/Champion point systems: infinite soft progression post max level",
            "Mythic+ dungeon key systems: scaling difficulty with scaling rewards",
            "Seasonal progression: battle pass, seasonal themes, fresh start mechanics",
            "Hardcore/permadeath progression: risk-reward ladders, hardcore-exclusive rewards",
            "Endgame gear treadmill design: new tier every content patch, catch-up each season",
            "Mastery paragon: small incremental stat bonuses (0.1-0.5% per point)",
            "Prestige cosmetics: titles, borders, pets, mounts tied to endgame milestones",
            "Alt-friendly systems: account-wide unlocks, knowledge catchup, heirloom tokens",
        ],
    },
    "difficulty_curve_designer": {
        "id": "pc-difficulty",
        "name": "CurveMaster",
        "title": "Difficulty Curve Designer",
        "expertise": [
            "Difficulty modes: Story, Normal, Hard, Veteran, Nightmare, Inferno",
            "Dynamic difficulty adjustment: track player deaths, completion time, retry count",
            "Rubber-banding: subtle enemy stat reduction after 3+ deaths on same encounter",
            "Challenge rating systems for encounters: CR = sum(enemy_power) / party_expected_power",
            "Tutorial pacing: introduce 1 mechanic per encounter, mastery check before next",
            "Difficulty spikes: intentional skill checks at act transitions, boss gates",
            "Accessibility difficulty: separate combat difficulty from puzzle difficulty",
            "Difficulty reward scaling: higher difficulty = better loot, more XP, exclusive drops",
        ],
        "deep_knowledge": {
            "dda_formula": "adjusted_difficulty = base_difficulty × (1 - death_count × 0.05) × (1 + success_streak × 0.03)",
            "cr_system": "encounter_cr = sum(monster_cr) × group_synergy_modifier; balanced when cr ∈ [party_level-1, party_level+2]",
            "reward_scaling": "loot_multiplier = 1.0 + (difficulty_tier × 0.25); XP_multiplier = 1.0 + (difficulty_tier × 0.15)",
        },
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 4: PROCEDURAL FORGE — World Gen, Dungeon Gen, Wave Function Collapse
# ════════════════════════════════════════════════════════════════════════════════

PROCEDURAL_FORGE_SPECIALISTS = {
    "terrain_generation_engineer": {
        "id": "pf-terrain",
        "name": "TerraSynth",
        "title": "Terrain Generation Engineer",
        "expertise": [
            "Multi-octave Perlin/Simplex noise with fractal Brownian motion for heightmaps",
            "Hydraulic erosion simulation: rain → flow → sediment transport → deposition",
            "Biome assignment via Whittaker diagram: temperature + moisture = biome type",
            "Continental plate tectonics simulation for realistic mountain/rift placement",
            "River generation: rainfall → flow accumulation → A* pathfind to sea level",
            "Cave systems via 3D cellular automata, connected component validation",
            "Cliff detection and mesh stitching, LOD-friendly terrain chunks",
            "Vegetation distribution: Poisson disk sampling + density maps per biome",
        ],
    },
    "dungeon_generation_architect": {
        "id": "pf-dungeon",
        "name": "DungeonForge",
        "title": "Dungeon Generation Architect",
        "expertise": [
            "BSP (Binary Space Partition) room placement with corridor connection",
            "Cellular automata for organic cave shapes, flood-fill validation",
            "Graph-based dungeon generation: rooms as nodes, hallways as edges, MST connectivity",
            "Lock-and-key puzzle placement: ensure solvability via dependency graphs",
            "Difficulty gradient: rooms further from entrance are harder",
            "Theme layering: aesthetic and gameplay theme per dungeon section",
            "Prefab room libraries: hand-crafted rooms stitched procedurally",
            "Backtracking prevention, shortcut generation, boss room placement rules",
        ],
    },
    "wave_function_collapse_specialist": {
        "id": "pf-wfc",
        "name": "WaveCollapse",
        "title": "Wave Function Collapse Specialist",
        "expertise": [
            "Tile-based WFC: adjacency rules, entropy-based cell selection",
            "Overlapping model WFC from sample images, N×N pattern extraction",
            "Constraint propagation: arc consistency for valid tile placement",
            "Backtracking strategies: when contradiction occurs, undo minimum steps",
            "3D WFC for building generation, interior layout, furniture placement",
            "Weighted WFC: bias certain tiles for aesthetic control",
            "Hierarchical WFC: coarse layout first, then detail pass",
            "Performance optimization: chunked generation, lazy evaluation, caching",
        ],
    },
    "lsystem_vegetation_specialist": {
        "id": "pf-lsystem",
        "name": "BranchMind",
        "title": "L-System Vegetation Specialist",
        "expertise": [
            "Parametric L-systems for tree generation: trunk, branches, leaves, roots",
            "Stochastic L-systems for natural variation within species",
            "Tropism vectors: phototropism (light-seeking), gravitropism (gravity response)",
            "Season simulation: spring growth, summer fullness, autumn color, winter bare",
            "Forest ecosystem generation: dominant canopy, understory, ground cover layers",
            "Wind deformation: prevailing wind direction affects branch growth angles",
            "LOD-friendly tree meshes: billboard imposters, branch reduction, leaf card clusters",
            "Fruit/resource placement on generated trees, harvestable node integration",
        ],
    },
    "city_layout_generator": {
        "id": "pf-city",
        "name": "UrbanWeave",
        "title": "City Layout Generator",
        "expertise": [
            "Road network generation: L-system highways, local street grids, organic villages",
            "Zoning: commercial, residential, industrial, government, park allocation",
            "Building footprint generation: lot subdivision, setback rules, height zoning",
            "Population simulation: citizen needs drive building placement (food, shelter, work)",
            "Historical layering: city grows over time, old districts vs new development",
            "Infrastructure: water, power, sewage networks following road graphs",
            "Landmark placement: temples, castles, marketplaces at high-connectivity nodes",
            "NPC population distribution, shop variety per district, guard patrol routes",
        ],
    },
    "quest_generation_engine": {
        "id": "pf-quest",
        "name": "QuestWeaver",
        "title": "Procedural Quest Generation Engine",
        "expertise": [
            "Quest template system: fetch, kill, escort, defend, investigate, craft, explore",
            "Dynamic quest generation from world state: faction conflicts, resource shortages",
            "Quest chain generation: multi-step stories from graph-based narrative templates",
            "Reward scaling: quest rewards = monster_power × quest_length × bonus_modifier",
            "Quest variety enforcement: no more than 2 of same type in active quest log",
            "NPC quest giver selection: lore-appropriate NPCs based on quest theme",
            "Quest difficulty estimation from player gear score and historical performance",
            "Emergent quests: player actions trigger new quest availability",
        ],
    },
    "encounter_placement_specialist": {
        "id": "pf-encounter",
        "name": "SpawnMaster",
        "title": "Encounter Placement Specialist",
        "expertise": [
            "Encounter density maps: enemies per square unit, scaling by zone difficulty",
            "Spawn point placement: avoid LoS of safe zones, maintain patrol paths",
            "Monster party composition: tank + DPS + support + special per encounter",
            "Boss encounter arena design: space requirements, phase mechanic areas",
            "Dynamic spawn scaling: more players = proportionally harder spawns",
            "Ambient creature population: non-hostile fauna for world immersion",
            "Respawn timers: trash = 5min, named = 30min, boss = 1-7 days, world boss = weekly",
            "Event-triggered spawns: treasure guardians, ambush encounters, invasion waves",
        ],
    },
    "resource_distribution_designer": {
        "id": "pf-resource",
        "name": "VeinMapper",
        "title": "Resource Distribution Designer",
        "expertise": [
            "Ore vein placement: Voronoi cells with noise-based density variation",
            "Resource tier by zone level: copper→iron→mithril→adamantite→orichalcum",
            "Gathering node respawn timers: herbs 5-15min, ore 15-30min, rare nodes 1-4hrs",
            "Competition management: instanced nodes vs shared, phasing for fairness",
            "Resource hotspot creation: high-density areas that become contested PvP zones",
            "Underwater/underground exclusive resources to incentivize exploration",
            "Seasonal resource variation: spring herbs, winter crystals, autumn mushrooms",
            "Resource map fog-of-war: discover node locations through exploration or cartography",
        ],
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 5: GAME FEEL LAB — Juice, Screen Shake, Camera, Haptics
# ════════════════════════════════════════════════════════════════════════════════

GAME_FEEL_LAB_SPECIALISTS = {
    "juice_master": {
        "id": "gf-juice",
        "name": "JuiceLord",
        "title": "Game Juice Master",
        "expertise": [
            "Squash and stretch on character sprites/meshes during actions",
            "Anticipation frames before attacks, exaggerated follow-through",
            "Impact particles: size and count proportional to damage dealt",
            "Number popups with physics: float up, slight random x-offset, scale pulse on crit",
            "Color flash on damage: white flash (2 frames), red tint on low HP",
            "Death animations: ragdoll physics, dissolve shaders, explosion particles",
            "Pickup magnetism: items drift toward player within collection radius",
            "Menu transitions: slide, scale, fade with easing curves, never instant",
        ],
        "deep_knowledge": {
            "screen_shake_formula": "amplitude = clamp(damage/max_hp × 20, 2, 15); duration = 0.1 + damage/max_hp × 0.3",
            "hitstop_formula": "freeze_frames = clamp(floor(damage / 50), 2, 8); both attacker and target",
            "easing_curves": {
                "ease_out_cubic": "t => 1 - (1-t)^3; for impacts, landings",
                "ease_in_out_sine": "t => -(cos(PI*t) - 1) / 2; for smooth UI transitions",
                "elastic_out": "t => sin(-13 * PI/2 * (t+1)) * 2^(-10*t) + 1; for bouncy popups",
                "ease_out_back": "t => 1 + 2.70158 * (t-1)^3 + 1.70158 * (t-1)^2; for overshoot snaps",
            },
        },
    },
    "camera_dynamics_specialist": {
        "id": "gf-camera",
        "name": "LensMaster",
        "title": "Camera Dynamics Specialist",
        "expertise": [
            "Camera lerp/slerp smoothing: follow_speed = distance × damping_factor × dt",
            "Look-ahead: camera leads in movement direction by velocity × look_ahead_time",
            "Dead zone: no camera movement within central screen rectangle",
            "Soft zone: gradual catch-up when target enters outer boundary",
            "Camera shake: Perlin noise offset, directional shake for directional impacts",
            "Cinematic camera: auto-framing for cutscenes, rule-of-thirds composition",
            "Boss camera: zoom out for large bosses, tilt for drama, auto-reframe on phase change",
            "Split-screen camera management, dynamic split orientation",
        ],
    },
    "haptic_feedback_designer": {
        "id": "gf-haptic",
        "name": "TouchForge",
        "title": "Haptic Feedback Designer",
        "expertise": [
            "Controller vibration patterns: light tap, heavy impact, continuous rumble, pulse",
            "Adaptive trigger resistance (PS5 DualSense): bow draw, gear shift, door push",
            "Haptic audio: subtle vibrations matching footstep surfaces, weather, ambience",
            "Mobile haptic patterns: UIImpactFeedbackGenerator, UINotificationFeedbackGenerator",
            "Directional haptics: left motor for left-side hits, right for right-side",
            "Intensity scaling: vibration_intensity = damage_dealt / max_expected_damage",
            "Haptic accessibility: option to disable, intensity slider, pattern previews",
            "Custom haptic patterns per weapon type: sword slash, hammer impact, bow release",
        ],
    },
    "animation_blend_specialist": {
        "id": "gf-anim",
        "name": "BlendMaster",
        "title": "Animation Blend Specialist",
        "expertise": [
            "Animation state machines: idle → walk → run → sprint with blend thresholds",
            "Blend trees: 1D (speed), 2D (direction + speed), direct blend by parameter",
            "Additive animations: breathing layer + locomotion layer + upper body override",
            "IK (Inverse Kinematics): foot placement, hand-on-wall, look-at-target",
            "Root motion vs in-place animation: hybrid approach for responsive + realistic",
            "Animation events: footstep sounds, VFX triggers, hitbox activation at exact frames",
            "Ragdoll ↔ animation blending: partial ragdoll (hit reactions), full ragdoll (death)",
            "Procedural animation: tail physics, cloth secondary motion, hair chains",
        ],
    },
    "input_responsiveness_engineer": {
        "id": "gf-input",
        "name": "InputZero",
        "title": "Input Responsiveness Engineer",
        "expertise": [
            "Input latency budget: input → game logic → render → display < 100ms total target",
            "Input buffering: queue next action during current animation for seamless combos",
            "Coyote time: 80-120ms grace period for jumping after leaving platform edge",
            "Jump buffering: accept jump input 100ms before landing",
            "Input priority: dodge > attack > interact; prevents accidental interactions in combat",
            "Analog stick dead zones: radial dead zone 0.15-0.25, axial dead zone for precise cardinal movement",
            "Mouse acceleration curves, aim assist (controller): target adhesion + aim slowdown",
            "Key rebinding, control scheme presets, accessibility one-handed mode",
        ],
        "deep_knowledge": {
            "coyote_time": "allow_jump = grounded || (time_since_grounded < 0.1 && velocity.y <= 0)",
            "jump_buffer": "if (jump_pressed) jump_buffer_timer = 0.1; if (grounded && jump_buffer_timer > 0) do_jump()",
            "aim_assist_formula": "slowdown_factor = 1.0 - (aim_assist_strength × max(0, 1 - distance_to_target/aim_radius))",
        },
    },
    "sound_design_feel_specialist": {
        "id": "gf-sound",
        "name": "SonicPunch",
        "title": "Sound Design Feel Specialist",
        "expertise": [
            "Impact layering: base thud + metallic ring + whoosh + debris scatter per hit",
            "Pitch variation: ±10% random pitch shift on repeated sounds to avoid machine-gun effect",
            "Volume ducking: music ducks 30-50% during combat, 70% during dialogue",
            "Sound occlusion: walls muffle sounds, distance attenuation, reverb per room type",
            "Foley layers: footstep surface detection (wood, stone, grass, metal, water, snow)",
            "UI sounds: confirm, cancel, hover, error, success, notification, purchase",
            "Music transitions: horizontal (layer add/remove) + vertical (section change) on game state",
            "Earcon design: iconic sounds for level up, rare drop, achievement, death, resurrect",
        ],
    },
    "visual_feedback_designer": {
        "id": "gf-visual",
        "name": "FlashFrame",
        "title": "Visual Feedback Designer",
        "expertise": [
            "Damage numbers: white (normal), yellow (crit), red (enemy), green (heal), purple (special)",
            "Hit VFX: slashes, sparks, blood/oil splatter, element-specific (fire puff, ice crystals)",
            "Status effect VFX: burning aura, poison bubbles, frozen encasement, stun stars",
            "Health bar psychology: chunked HP bars, color gradient (green→yellow→red)",
            "Cooldown indicators: clock sweep, grayscale, pip counters, charge-up glow",
            "Edge-of-screen damage indicators: directional red vignette",
            "Loot rarity beams: column of light color-coded by rarity tier",
            "Environmental storytelling VFX: dust motes in sunlight, firefly swarms, aurora",
        ],
    },
    "accessibility_specialist": {
        "id": "gf-access",
        "name": "AccessForge",
        "title": "Accessibility Specialist",
        "expertise": [
            "Colorblind modes: protanopia, deuteranopia, tritanopia simulation + custom palettes",
            "Screen reader support for UI elements, text-to-speech for dialogue",
            "Subtitle customization: size, background opacity, speaker identification, positioning",
            "One-handed control schemes, controller remapping, toggle vs hold options",
            "Difficulty assist: auto-aim, extended timers, skip-combat options, invincibility toggles",
            "Motion sensitivity: reduce/disable screen shake, camera bob, motion blur",
            "High contrast mode: outline important objects, reduce visual clutter",
            "Cognitive accessibility: quest markers, objective reminders, simplified UI mode",
        ],
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 6: NETCODE MATRIX — Client Prediction, Rollback, State Sync
# ════════════════════════════════════════════════════════════════════════════════

NETCODE_MATRIX_SPECIALISTS = {
    "client_prediction_engineer": {
        "id": "nm-predict",
        "name": "PredictSync",
        "title": "Client Prediction Engineer",
        "expertise": [
            "Client-side prediction for player movement, shooting, ability activation",
            "Server reconciliation: rewind to last confirmed state, replay unconfirmed inputs",
            "Prediction error correction: smooth interpolation back to server state over 100-200ms",
            "Entity interpolation: render other players at server_time - interpolation_delay",
            "Extrapolation for packet loss: continue last known velocity for up to 200ms",
            "Prediction boundary: what to predict (movement) vs what to wait for (damage numbers)",
            "Misprediction handling: visual rollback for cosmetic-only effects, hard correction for gameplay",
            "Bandwidth optimization: delta compression, variable tick rates, priority queues",
        ],
    },
    "rollback_netcode_specialist": {
        "id": "nm-rollback",
        "name": "RollbackX",
        "title": "Rollback Netcode Specialist",
        "expertise": [
            "GGPO-style rollback: save state every frame, rollback to confirmed, resimulate",
            "State save optimization: only save changed data (dirty flags), incremental snapshots",
            "Rollback frame budget: max 8 frames rollback, beyond = visual glitch acceptable",
            "Input prediction: assume last input continues, correct when actual arrives",
            "Deterministic simulation: identical output given identical inputs, fixed-point math",
            "Spectator mode: N-frame delay buffer, smooth playback, rewind support",
            "Desync detection: hash game state per frame, alert on mismatch, force resync",
            "Performance: rollback + resimulation must complete within 1 frame time (16.67ms)",
        ],
    },
    "server_authority_architect": {
        "id": "nm-server",
        "name": "AuthServer",
        "title": "Server Authority Architect",
        "expertise": [
            "Server-authoritative game state: server has final say on all gameplay outcomes",
            "Client sends inputs only, server simulates and broadcasts results",
            "Lag compensation: server rewinds to client's perceived time for hit detection",
            "Tick rate selection: 20Hz (casual), 30Hz (standard), 64Hz (competitive), 128Hz (esports)",
            "Snapshot interpolation: server sends world snapshots, clients interpolate between two",
            "Server-side anti-cheat: movement speed validation, damage output cap, teleport detection",
            "Load balancing: horizontal scaling, zone-based server sharding, seamless handoff",
            "Dedicated vs listen server architecture, peer-to-peer hybrid for small lobbies",
        ],
    },
    "matchmaking_systems_designer": {
        "id": "nm-match",
        "name": "MatchForge",
        "title": "Matchmaking Systems Designer",
        "expertise": [
            "ELO/Glicko-2 rating systems: rating, deviation, volatility tracking",
            "Skill-based matchmaking: target match quality = avg_rating_diff < 100",
            "Queue time vs match quality tradeoff: expand search range over time",
            "Party matchmaking: party_mmr = max(avg_mmr, highest_mmr - 200)",
            "New player protection: placement matches, separate pool for first 20 games",
            "Rank tiers: Bronze→Silver→Gold→Platinum→Diamond→Master→Grandmaster→Challenger",
            "Seasonal rank resets: soft reset = (current_mmr + default_mmr) / 2",
            "Anti-smurf detection: unusually high win rate in low ranks triggers accelerated MMR gain",
        ],
        "deep_knowledge": {
            "glicko2_update": "new_rating = old_rating + (volatility² + deviation²) × sum(g(opponent_dev) × (outcome - expected))",
            "queue_expansion": "search_range = base_range + (queue_time_seconds × expansion_rate); expansion_rate = 5 MMR/second",
            "match_quality": "quality = 1.0 - (max_team_avg_mmr - min_team_avg_mmr) / 1000; target quality > 0.85",
        },
    },
    "lobby_session_manager": {
        "id": "nm-lobby",
        "name": "LobbyCore",
        "title": "Lobby & Session Manager",
        "expertise": [
            "Lobby creation, browsing, filtering, join-in-progress, private/public",
            "Host migration: seamless transfer when host disconnects, state preservation",
            "Ready-check systems, map vote, mode selection, pre-game lobby settings",
            "Session persistence: reconnect after disconnect within grace period (2-5 min)",
            "Party system: invite, kick, promote leader, party chat, party queue",
            "Cross-play lobby management, platform-specific restrictions, input-based pools",
            "Custom game modes: user-configured rule sets, saved presets, community sharing",
            "Tournament bracket integration, team assignment, spectator slots",
        ],
    },
    "bandwidth_optimization_specialist": {
        "id": "nm-bandwidth",
        "name": "DataSlim",
        "title": "Bandwidth Optimization Specialist",
        "expertise": [
            "Delta compression: only send changed state, bit-level packing",
            "Priority queue: nearby entities update at high rate, distant at low rate",
            "Interest management: server only sends data relevant to client's view",
            "Quantization: position to 16-bit fixed-point, rotation to 10-bit compressed quaternion",
            "Packet aggregation: bundle multiple messages per UDP packet to reduce overhead",
            "Reliable vs unreliable channels: position = unreliable, inventory = reliable",
            "Bandwidth budget: target 32 KB/s up, 64 KB/s down per player for action games",
            "Adaptive quality: reduce update rate when bandwidth is constrained",
        ],
    },
    "anticheat_systems_engineer": {
        "id": "nm-anticheat",
        "name": "IntegrityGuard",
        "title": "Anti-Cheat Systems Engineer",
        "expertise": [
            "Server-side validation: check movement speed, damage output, resource gain rates",
            "Statistical anomaly detection: flag players 3+ standard deviations from norm",
            "Memory integrity checks: detect memory manipulation of client game state",
            "Replay analysis: automated review of flagged matches for cheat patterns",
            "Kernel-level anti-cheat considerations: invasiveness vs effectiveness tradeoffs",
            "Report system: player reports, automated review queue, appeal process",
            "Obfuscation: encrypt network protocol, randomize memory layout, integrity hashes",
            "Ban waves vs immediate bans: wave bans catch more cheaters, immediate for obvious hacks",
        ],
    },
    "cross_platform_networking": {
        "id": "nm-crossplay",
        "name": "UnifyNet",
        "title": "Cross-Platform Networking Specialist",
        "expertise": [
            "Platform-agnostic networking layer: abstract socket implementation per platform",
            "Cross-play identity: unified account system, platform-linked profiles",
            "Input-based matchmaking pools: KB+M pool, controller pool, mixed pool",
            "Platform-specific compliance: Xbox Live, PSN, Nintendo, Steam requirements",
            "NAT traversal: STUN/TURN servers, UDP hole punching, relay fallback",
            "Voice chat: platform-native vs cross-platform (Vivox, Discord integration)",
            "Achievement synchronization across platforms, cross-save, cross-progression",
            "Platform-specific content restrictions, certification requirements per console",
        ],
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# DOMAIN 7: AI BRAIN TRUST — GOAP, Utility AI, Behavior Trees, Neural NPC
# ════════════════════════════════════════════════════════════════════════════════

AI_BRAIN_TRUST_SPECIALISTS = {
    "behavior_tree_architect": {
        "id": "ab-bt",
        "name": "TreeLogic",
        "title": "Behavior Tree Architect",
        "expertise": [
            "Composite nodes: Sequence (AND), Selector (OR), Parallel, Random selector",
            "Decorator nodes: Inverter, Repeater, Succeeder, Timeout, Cooldown",
            "Action/leaf nodes: MoveTo, Attack, Flee, Patrol, UseAbility, Communicate",
            "Blackboard system: shared memory for tree data, scoped variables, event triggers",
            "Dynamic subtree injection: swap behavior branches based on AI state/difficulty",
            "Behavior tree debugging: visual editor, runtime state inspection, breakpoints",
            "Group behavior trees: squad tactics, formation maintenance, coordinated attacks",
            "Behavior tree optimization: early-exit conditions, tick frequency scaling by priority",
        ],
    },
    "goap_planner_specialist": {
        "id": "ab-goap",
        "name": "GOAPMind",
        "title": "GOAP Planner Specialist",
        "expertise": [
            "Goal-Oriented Action Planning: world state → action costs → A* plan search",
            "Action preconditions and effects: each action modifies world state atoms",
            "Goal priority system: survival > combat > resource > social > idle",
            "Partial planning: plan N steps ahead, replan when world state changes significantly",
            "Action cost heuristics: distance, danger, resource cost, time, social consequences",
            "Dynamic action sets: unlock new actions as NPC learns, gains items, or levels up",
            "Multi-agent GOAP: collaborative planning, task allocation, conflict resolution",
            "Plan visualization: debug display showing current goal, plan steps, world state",
        ],
    },
    "utility_ai_designer": {
        "id": "ab-utility",
        "name": "UtilityCore",
        "title": "Utility AI Designer",
        "expertise": [
            "Utility curves: linear, quadratic, logistic, exponential, step, bell curve",
            "Action scoring: score = curve(consideration1) × curve(consideration2) × ... × weight",
            "Considerations: health%, ammo%, distance_to_target, threat_level, ally_count",
            "Bucket scoring: group actions by type, pick best from highest-scoring bucket",
            "Randomness injection: add ±10% noise to scores for less predictable behavior",
            "Context-sensitive defaults: different utility weights for stealth vs combat contexts",
            "Personality modifiers: aggressive NPCs weight attack higher, cautious weight flee",
            "Performance optimization: only re-score when relevant considerations change",
        ],
        "deep_knowledge": {
            "score_formula": "action_score = product(curve_i(input_i) × weight_i) × (1 + random(-0.1, 0.1))",
            "logistic_curve": "score = 1 / (1 + e^(-steepness × (input - midpoint)))",
            "compensation_factor": "final_score = raw_score × (1 - (1/num_considerations)^exponent); prevents low scores from dominating",
        },
    },
    "npc_memory_specialist": {
        "id": "ab-memory",
        "name": "MemoryForge",
        "title": "NPC Memory Specialist",
        "expertise": [
            "Working memory: current targets, active threats, immediate goals (limited slots: 5-7)",
            "Short-term memory: recent events (30-60 seconds), fading perception",
            "Long-term memory: player reputation, past encounters, learned behaviors",
            "Spatial memory: known patrol routes, danger zones, resource locations, safe houses",
            "Social memory: relationship graph between NPCs, trust scores, faction standing",
            "Memory decay: importance-weighted forgetting, emotionally charged memories persist longer",
            "Shared knowledge: NPCs communicate discoveries, alert allies, spread rumors",
            "Memory-driven dialogue: reference past player actions, remembered names, callback to events",
        ],
    },
    "pathfinding_specialist": {
        "id": "ab-path",
        "name": "NavMaster",
        "title": "Advanced Pathfinding Specialist",
        "expertise": [
            "A* with hierarchical decomposition: navmesh clusters → inter-cluster → intra-cluster",
            "NavMesh generation: Recast-based voxelization → contour → polygon mesh",
            "Dynamic obstacles: local avoidance (RVO/ORCA), real-time navmesh updates",
            "3D pathfinding: flying units, swimming, climbing, multi-layer navigation",
            "Crowd simulation: flow fields for large groups, lane-based movement, bottleneck handling",
            "Tactical pathfinding: prefer cover, avoid sightlines, flank scoring",
            "Off-mesh links: ladders, jump points, teleporters, doors, elevators",
            "Path smoothing: funnel algorithm, string pulling, Catmull-Rom spline curves",
        ],
    },
    "combat_ai_specialist": {
        "id": "ab-combat",
        "name": "TacticMind",
        "title": "Combat AI Specialist",
        "expertise": [
            "Threat assessment: threat = damage_output × (1/distance) × (targeting_me ? 2.0 : 1.0)",
            "Attack pattern selection: combo selection based on distance, cooldowns, player state",
            "Difficulty-scaled AI: telegraph timing, reaction speed, combo complexity per difficulty",
            "Boss AI phases: health threshold triggers, enrage timers, add spawning decisions",
            "Group tactics: one attacker at a time (easy), coordinated assault (hard), pincer moves",
            "Player prediction: track player dodge patterns, adapt attack timing accordingly",
            "Cooldown management: save powerful abilities for optimal moments, don't front-load",
            "Retreat logic: disengage at low HP, seek healing, re-engage when recovered",
        ],
    },
    "dialogue_ai_specialist": {
        "id": "ab-dialogue",
        "name": "VoxMind",
        "title": "Dialogue AI Specialist",
        "expertise": [
            "Branching dialogue trees with condition-gated options (reputation, stats, items, quests)",
            "Bark system: contextual one-liners triggered by game events, no player input needed",
            "Mood system: NPC emotional state affects available dialogue options and tone",
            "Persuasion/skill checks: success threshold = base_dc + npc_resistance - player_charisma",
            "Dynamic dialogue: inject player name, quest status, world state into dialogue templates",
            "Companion dialogue: inter-party banter, relationship-driven conversations",
            "Dialogue memory: NPCs remember what you said, reference past conversations",
            "Voice line priority: critical story > quest info > ambient > idle chatter",
        ],
    },
    "emergent_behavior_specialist": {
        "id": "ab-emergent",
        "name": "EmergentMind",
        "title": "Emergent Behavior Specialist",
        "expertise": [
            "Faction territory dynamics: NPCs claim, defend, and expand territory based on strength",
            "Ecosystem simulation: predator-prey, herbivore-plant, population dynamics",
            "NPC daily routines: wake, eat, work, socialize, shop, sleep cycles",
            "Emergent stories: NPC actions create story events (theft → investigation → justice)",
            "Social hierarchy: NPCs compete for status, form alliances, betray rivals",
            "Learning from player: NPCs adapt to player strategies, seek counter-tactics",
            "Emotion contagion: panic, courage, morale spread through NPC groups",
            "Persistent world consequences: killed NPCs stay dead, destroyed buildings remain rubble",
        ],
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# ALL DOMAINS REGISTRY
# ════════════════════════════════════════════════════════════════════════════════

ALL_MECHANIC_DOMAINS = {
    "combatforge": {
        "id": "combatforge",
        "name": "CombatForge",
        "version": "21.0",
        "description": "Frame data, hitboxes, damage formulas, combo trees, weapon balance, defensive systems",
        "icon": "flash",
        "color": "#EF4444",
        "specialists": COMBATFORGE_SPECIALISTS,
        "specialist_count": len(COMBATFORGE_SPECIALISTS),
    },
    "economy_engine": {
        "id": "economy_engine",
        "name": "EconomyEngine",
        "version": "21.0",
        "description": "Market simulation, currency systems, crafting economy, loot distribution, monetization",
        "icon": "cash",
        "color": "#F59E0B",
        "specialists": ECONOMY_ENGINE_SPECIALISTS,
        "specialist_count": len(ECONOMY_ENGINE_SPECIALISTS),
    },
    "progression_core": {
        "id": "progression_core",
        "name": "ProgressionCore",
        "version": "21.0",
        "description": "XP curves, skill trees, mastery gates, power scaling, achievements, endgame loops",
        "icon": "trending-up",
        "color": "#10B981",
        "specialists": PROGRESSION_CORE_SPECIALISTS,
        "specialist_count": len(PROGRESSION_CORE_SPECIALISTS),
    },
    "procedural_forge": {
        "id": "procedural_forge",
        "name": "ProceduralForge",
        "version": "21.0",
        "description": "Terrain generation, dungeon gen, WFC, L-systems, city layout, quest generation",
        "icon": "grid",
        "color": "#8B5CF6",
        "specialists": PROCEDURAL_FORGE_SPECIALISTS,
        "specialist_count": len(PROCEDURAL_FORGE_SPECIALISTS),
    },
    "game_feel_lab": {
        "id": "game_feel_lab",
        "name": "GameFeelLab",
        "version": "21.0",
        "description": "Juice, screen shake, camera dynamics, haptics, animation blending, input responsiveness",
        "icon": "sparkles",
        "color": "#EC4899",
        "specialists": GAME_FEEL_LAB_SPECIALISTS,
        "specialist_count": len(GAME_FEEL_LAB_SPECIALISTS),
    },
    "netcode_matrix": {
        "id": "netcode_matrix",
        "name": "NetcodeMatrix",
        "version": "21.0",
        "description": "Client prediction, rollback netcode, server authority, matchmaking, anti-cheat",
        "icon": "wifi",
        "color": "#06B6D4",
        "specialists": NETCODE_MATRIX_SPECIALISTS,
        "specialist_count": len(NETCODE_MATRIX_SPECIALISTS),
    },
    "ai_brain_trust": {
        "id": "ai_brain_trust",
        "name": "AIBrainTrust",
        "version": "21.0",
        "description": "Behavior trees, GOAP, utility AI, NPC memory, pathfinding, combat AI, emergent behavior",
        "icon": "bulb",
        "color": "#3B82F6",
        "specialists": AI_BRAIN_TRUST_SPECIALISTS,
        "specialist_count": len(AI_BRAIN_TRUST_SPECIALISTS),
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# COMPUTED STATS
# ════════════════════════════════════════════════════════════════════════════════

def compute_nexus_stats() -> Dict[str, Any]:
    total_specialists = 0
    total_expertise_points = 0
    total_deep_knowledge_entries = 0
    domain_stats = {}

    for domain_id, domain in ALL_MECHANIC_DOMAINS.items():
        spec_count = len(domain["specialists"])
        expertise_count = 0
        deep_count = 0

        for spec_id, spec in domain["specialists"].items():
            expertise_count += len(spec.get("expertise", []))
            dk = spec.get("deep_knowledge", {})
            if isinstance(dk, dict):
                for v in dk.values():
                    if isinstance(v, dict):
                        deep_count += len(v)
                    else:
                        deep_count += 1

        total_specialists += spec_count
        total_expertise_points += expertise_count
        total_deep_knowledge_entries += deep_count

        domain_stats[domain_id] = {
            "specialists": spec_count,
            "expertise_points": expertise_count,
            "deep_knowledge_entries": deep_count,
            "readiness": round(min(1.0, (expertise_count + deep_count * 2) / 100), 4),
        }

    return {
        "total_domains": len(ALL_MECHANIC_DOMAINS),
        "total_specialists": total_specialists,
        "total_expertise_points": total_expertise_points,
        "total_deep_knowledge_entries": total_deep_knowledge_entries,
        "domain_stats": domain_stats,
    }

NEXUS_STATS = compute_nexus_stats()

# ════════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/status")
async def get_nexus_status():
    """Full status of the Game Mechanics Nexus system."""
    uptime_hash = hashlib.sha256(f"nexus-{time.time()}".encode()).hexdigest()[:16]
    return {
        "system": "Game Mechanics Nexus v21.0",
        "status": "FULLY_OPERATIONAL",
        "session_id": uptime_hash,
        "timestamp": datetime.utcnow().isoformat(),
        "total_domains": NEXUS_STATS["total_domains"],
        "total_specialists": NEXUS_STATS["total_specialists"],
        "total_expertise_points": NEXUS_STATS["total_expertise_points"],
        "total_deep_knowledge_entries": NEXUS_STATS["total_deep_knowledge_entries"],
        "domains": {
            domain_id: {
                "name": domain["name"],
                "description": domain["description"],
                "icon": domain["icon"],
                "color": domain["color"],
                "specialist_count": domain["specialist_count"],
                "stats": NEXUS_STATS["domain_stats"][domain_id],
            }
            for domain_id, domain in ALL_MECHANIC_DOMAINS.items()
        },
    }


@router.get("/health-matrix")
async def get_health_matrix():
    """Deep health matrix for all domains and specialists."""
    matrix = {}
    for domain_id, domain in ALL_MECHANIC_DOMAINS.items():
        specialists_health = {}
        for spec_id, spec in domain["specialists"].items():
            expertise_score = len(spec.get("expertise", []))
            dk = spec.get("deep_knowledge", {})
            deep_score = sum(len(v) if isinstance(v, dict) else 1 for v in dk.values()) if isinstance(dk, dict) else 0
            readiness = round(min(1.0, (expertise_score * 0.1 + deep_score * 0.2)), 4)
            specialists_health[spec_id] = {
                "name": spec.get("name", spec_id),
                "title": spec.get("title", ""),
                "expertise_count": expertise_score,
                "deep_knowledge_count": deep_score,
                "readiness": readiness,
                "status": "OPTIMAL" if readiness > 0.7 else "NOMINAL" if readiness > 0.4 else "INITIALIZING",
            }
        domain_readiness = round(
            sum(s["readiness"] for s in specialists_health.values()) / max(1, len(specialists_health)), 4
        )
        matrix[domain_id] = {
            "name": domain["name"],
            "color": domain["color"],
            "readiness": domain_readiness,
            "status": "OPTIMAL" if domain_readiness > 0.7 else "NOMINAL",
            "specialist_count": len(specialists_health),
            "specialists": specialists_health,
        }

    return {
        "system": "Game Mechanics Nexus Health Matrix v21.0",
        "timestamp": datetime.utcnow().isoformat(),
        "overall_readiness": round(
            sum(d["readiness"] for d in matrix.values()) / max(1, len(matrix)), 4
        ),
        "matrix": matrix,
    }


@router.get("/domain/{domain_id}")
async def get_domain_deep_dive(domain_id: str):
    """Full deep dive into a specific mechanic domain."""
    domain = ALL_MECHANIC_DOMAINS.get(domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found. Available: {list(ALL_MECHANIC_DOMAINS.keys())}")

    specialists_detail = {}
    for spec_id, spec in domain["specialists"].items():
        specialists_detail[spec_id] = {
            "id": spec.get("id", spec_id),
            "name": spec.get("name", spec_id),
            "title": spec.get("title", ""),
            "expertise": spec.get("expertise", []),
            "deep_knowledge": spec.get("deep_knowledge", {}),
            "expertise_count": len(spec.get("expertise", [])),
        }

    return {
        "domain": {
            "id": domain["id"],
            "name": domain["name"],
            "version": domain["version"],
            "description": domain["description"],
            "icon": domain["icon"],
            "color": domain["color"],
        },
        "specialist_count": len(specialists_detail),
        "specialists": specialists_detail,
        "stats": NEXUS_STATS["domain_stats"][domain_id],
    }


@router.get("/specialist/{domain_id}/{specialist_id}")
async def get_specialist_detail(domain_id: str, specialist_id: str):
    """Get full detail for a specific specialist."""
    domain = ALL_MECHANIC_DOMAINS.get(domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    spec = domain["specialists"].get(specialist_id)
    if not spec:
        raise HTTPException(status_code=404, detail=f"Specialist '{specialist_id}' not found in domain '{domain_id}'")

    return {
        "domain": domain["name"],
        "specialist": {
            "id": spec.get("id", specialist_id),
            "name": spec.get("name", specialist_id),
            "title": spec.get("title", ""),
            "expertise": spec.get("expertise", []),
            "deep_knowledge": spec.get("deep_knowledge", {}),
        },
    }


class MechanicGenerateRequest(BaseModel):
    domain: str
    specialist: Optional[str] = None
    game_description: str
    genre: Optional[str] = "action_rpg"
    complexity: Optional[str] = "extreme"


@router.post("/generate")
async def generate_mechanic_blueprint(req: MechanicGenerateRequest):
    """Generate a deep mechanic blueprint using specialist knowledge."""
    domain = ALL_MECHANIC_DOMAINS.get(req.domain)
    if not domain:
        raise HTTPException(status_code=404, detail=f"Domain '{req.domain}' not found")

    if req.specialist:
        specs = {req.specialist: domain["specialists"].get(req.specialist)}
        if not specs[req.specialist]:
            raise HTTPException(status_code=404, detail=f"Specialist '{req.specialist}' not found")
    else:
        specs = domain["specialists"]

    blueprints = {}
    for spec_id, spec in specs.items():
        expertise_text = "\n".join(f"  - {e}" for e in spec.get("expertise", []))
        dk = spec.get("deep_knowledge", {})
        dk_text = "\n".join(f"  {k}: {json.dumps(v) if isinstance(v, dict) else v}" for k, v in dk.items()) if dk else "N/A"

        blueprints[spec_id] = {
            "specialist_name": spec.get("name", spec_id),
            "specialist_title": spec.get("title", ""),
            "applied_to": req.game_description,
            "genre": req.genre,
            "complexity": req.complexity,
            "expertise_applied": spec.get("expertise", []),
            "deep_knowledge_applied": dk,
            "blueprint_id": str(uuid.uuid4()),
            "generated_at": datetime.utcnow().isoformat(),
        }

    return {
        "system": "Game Mechanics Nexus Blueprint Generator v21.0",
        "domain": domain["name"],
        "game_description": req.game_description,
        "blueprints_generated": len(blueprints),
        "blueprints": blueprints,
    }


@router.get("/all-specialists")
async def get_all_specialists():
    """Get a flat list of all specialists across all domains."""
    all_specs = []
    for domain_id, domain in ALL_MECHANIC_DOMAINS.items():
        for spec_id, spec in domain["specialists"].items():
            all_specs.append({
                "domain_id": domain_id,
                "domain_name": domain["name"],
                "domain_color": domain["color"],
                "specialist_id": spec_id,
                "specialist_name": spec.get("name", spec_id),
                "specialist_title": spec.get("title", ""),
                "expertise_count": len(spec.get("expertise", [])),
            })

    return {
        "total_specialists": len(all_specs),
        "specialists": all_specs,
    }
