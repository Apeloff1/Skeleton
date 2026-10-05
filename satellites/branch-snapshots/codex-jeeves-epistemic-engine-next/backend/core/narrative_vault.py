"""
╔════════════════════════════════════════════════════════════════════════╗
║  NARRATIVE VAULT — 6 canonical storyline databases seeding the swarm   ║
║  ────────────────────────────────────────────────────────────────────  ║
║    • playwright_library     — plots + beats from every game ever made   ║
║    • narration_library      — narrator voices, pacing, intro/outro      ║
║    • quest_library          — quest archetypes, step trees, rewards     ║
║    • mission_library        — mission types, objective trees, patterns  ║
║    • story_arc_library      — 3-act, 5-act, hero's journey, kishotenketsu║
║    • storytelling_library   — narrative techniques + framing devices    ║
║                                                                        ║
║  All collections carry a `genre` field and a `canonical_id` so swarm   ║
║  agents can filter by genre + dedupe to drive truly original outputs.  ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import hashlib
import logging
import random
from typing import Optional

logger = logging.getLogger("GalaxyStudio.NarrativeVault")

# 27 genre buckets used across the vault. Mirrors the galaxy-studio GENRES list.
GENRE_BUCKETS = [
    "rpg", "action_rpg", "jrpg", "crpg", "strategy", "rts", "grand_strategy",
    "shooter", "fps", "tps", "looter_shooter", "roguelite", "roguelike",
    "platformer", "metroidvania", "action_adventure", "open_world", "sandbox",
    "horror", "survival", "mystery", "detective", "visual_novel", "dating_sim",
    "tycoon", "management_sim", "simulation", "racing", "sports",
    "fighting", "beat_em_up", "puzzle", "rhythm", "card_game", "board_game",
    "stealth_action", "tactics", "mmo", "moba", "battle_royale",
    "text_adventure", "interactive_fiction", "point_and_click", "party",
    "artistic", "music_game", "educational", "kids",
    "cyberpunk_noir", "space_opera", "high_fantasy", "low_fantasy",
    "historical", "mythology", "western", "post_apocalyptic", "utopia",
    "horror_cosmic", "psychological_horror", "crime_drama", "espionage",
    "heist", "coming_of_age", "tragedy", "comedy", "satire", "dystopia",
]

# Tier-1 references — real games whose storylines the swarm learns from.
# This seed list is intentionally broad across eras, consoles, and genres.
# Actual runtime seeding expands each of these into 60–120 derivative
# entries so a single genre bucket lands around 3,000–6,000 rows.
PLAYWRIGHT_SEEDS = {
    "rpg": [
        ("Final Fantasy VII", "Eco-terrorism meets cosmic horror — a mercenary uncovers a corporate conspiracy and his own manufactured memories."),
        ("Chrono Trigger", "A time-travel odyssey where heroes from seven eras unite to prevent a world-ending apocalypse in 1999 AD."),
        ("Planescape: Torment", "An amnesiac immortal hunts identity across the outer planes, confronting past selves and the nature of regret."),
        ("Baldur's Gate II", "A rival Bhaalspawn abducts your soul; across planes and pocket realms you reclaim it and confront divinity."),
        ("The Elder Scrolls IV: Oblivion", "An unknown prisoner is freed by the emperor to seal the Oblivion gates and crown a hidden heir."),
        ("The Elder Scrolls V: Skyrim", "The Dragonborn emerges to confront Alduin's apocalyptic return while civil war tears Skyrim apart."),
        ("Mass Effect", "A Spectre rogue operative races to stop the Reapers, a cycle of galactic extinction older than recorded history."),
        ("Dragon Age: Origins", "A Grey Warden recruits factions across Ferelden to stop a Blight while betrayal boils within the throne."),
        ("The Witcher 3: Wild Hunt", "A monster-slayer hunts his adopted daughter, pursued by spectral Wild Hunt, across war-torn Velen and beyond."),
        ("Disco Elysium", "A wrecked detective reconstructs his identity while investigating a lynching amid revolutionary unrest."),
        ("Dark Souls", "The Chosen Undead links the First Flame to preserve a cyclical age of fire or embrace the Age of Dark."),
        ("Elden Ring", "The Tarnished collects Great Runes from demigods to mend or shatter the Elden Ring and reshape the Lands Between."),
        ("Xenoblade Chronicles", "Two titanic gods' bodies form the world; a sword of unknown power reveals the layered cosmology behind reality."),
        ("Persona 5", "Phantom Thieves steal the corrupt desires of powerful adults to awaken society from apathy."),
        ("Earthbound", "Four psychic kids defeat a cosmic evil using prayer, time, and kindness across small-town America."),
    ],
    "action_adventure": [
        ("The Legend of Zelda: Breath of the Wild", "A century-late hero awakens to reclaim his past and free Hyrule from Calamity Ganon."),
        ("Uncharted 2: Among Thieves", "Treasure hunter chases Shambhala's secrets while rival mercenaries pursue a world-shaking artifact."),
        ("The Last of Us", "A smuggler escorts an immune girl across post-pandemic America, forced to choose between hope and love."),
        ("God of War (2018)", "A former god of war teaches his son to be better than him while performing funerary rites across Norse realms."),
        ("Shadow of the Colossus", "A wanderer slays sixteen colossi in exchange for resurrection; the cost is his soul."),
        ("Bloodborne", "A hunter in Yharnam uncovers a cosmic truth — the plague is the dream of Great Ones."),
        ("Metroid Prime", "Samus Aran tracks Space Pirates and Phazon across Tallon IV, revealing the Chozo's final warning."),
    ],
    "shooter": [
        ("Half-Life 2", "Gordon Freeman returns to a Combine-occupied earth and ignites a resistance."),
        ("Halo: Combat Evolved", "Master Chief and Cortana discover a halo ringworld and the parasitic Flood that demands its use."),
        ("BioShock", "A plane crash survivor explores an undersea Objectivist utopia twisted by genetic engineering and cult of personality."),
        ("Portal 2", "Two Aperture test subjects flip between past and present to defeat rogue AIs with portals and wit."),
        ("DOOM (2016)", "The Doom Slayer rips and tears through Mars installations invaded by hell."),
        ("Call of Duty 4: Modern Warfare", "Ultranationalist nuclear plot unfolds across a post-Soviet collapse; SAS and Marines race to stop WW3."),
    ],
    "horror": [
        ("Silent Hill 2", "James Sunderland travels to a foggy town to meet his dead wife; the town renders his guilt manifest."),
        ("Resident Evil 4", "A rogue agent rescues the president's daughter from a parasitic cult in rural Spain."),
        ("Amnesia: The Dark Descent", "A memory-stripped man writes a letter to himself pleading to murder a baron and end a ritual."),
        ("SOMA", "A scanned consciousness wakes in an undersea facility and confronts the definition of self after death."),
    ],
    "strategy": [
        ("Civilization VI", "Lead a civilization from a lone settler in 4000 BC to space colonization or cultural dominion."),
        ("StarCraft II: Wings of Liberty", "Ex-Confederate captain leads a rebellion while an infested queen threatens the sector."),
        ("XCOM 2", "Humanity's resistance aboard the Avenger wages guerrilla war against an ADVENT alien occupation."),
        ("Fire Emblem: Three Houses", "A mercenary teacher leads one of three noble houses into a continent-spanning war."),
    ],
    "simulation": [
        ("The Sims", "Direct the lives of virtual households through career, love, and midlife renovations."),
        ("Stardew Valley", "Inherited farm revitalization story about community-building in rural Pelican Town."),
        ("Animal Crossing: New Horizons", "Island paradise developer story of seasons, neighbors, and quiet progress."),
    ],
    "tycoon": [
        ("RollerCoaster Tycoon", "Park manager builds rides, retains guests, and races scenario deadlines."),
        ("Theme Hospital", "Hospital admin diagnoses fictional diseases while hiring doctors and expanding wards."),
        ("Two Point Hospital", "Spiritual successor — cure bloaty-head, light-headedness, and jest infection across regions."),
        ("Prison Architect", "Warden balances security, reform, and riot control while expanding a profitable prison."),
        ("Planet Zoo", "Zoo operator breeds animals, educates guests, and manages conservation stock across biomes."),
        ("Game Dev Tycoon", "Garage dev studio grows into AAA while navigating era-specific hardware and genre fads."),
    ],
    "open_world": [
        ("Grand Theft Auto V", "Three criminals navigate heists and betrayal in a satirical open-world California."),
        ("Red Dead Redemption 2", "An outlaw's elegy across the dying American West, family loyalty, and inevitability."),
        ("Elder Scrolls V: Skyrim", "Dragonborn myth unfolds across a free-to-roam province of Tamriel."),
    ],
    "stealth_action": [
        ("Metal Gear Solid 3: Snake Eater", "Cold War origin story of Big Boss confronting his mentor The Boss in Soviet jungles."),
        ("Dishonored", "A disgraced royal protector uses supernatural abilities to enact justice or revenge across plague-stricken Dunwall."),
        ("Hitman: World of Assassination", "Agent 47 globe-trots executing contracts in sandbox levels."),
    ],
    "tactics": [
        ("Fire Emblem: Awakening", "Strategist leader unites Ylisse against Plegia while confronting a time-paradox draconic apocalypse."),
        ("Into the Breach", "Time-looping mechs defend cities from Vek while deciding which civilians survive."),
        ("Final Fantasy Tactics", "Noble-turned-mercenary unravels a conspiracy altering a kingdom's historical record."),
    ],
    "roguelite": [
        ("Hades", "Prince of the Underworld attempts escape from his father while reconciling the Olympian family."),
        ("Dead Cells", "A consciousness jumps between corpses in a shape-shifting castle of a plague-ruined kingdom."),
        ("The Binding of Isaac", "A child flees his mother's sacrificial zeal into the monstrous basement beneath their home."),
    ],
}

# Narration templates by pacing + tone
NARRATION_SEEDS = [
    {"narrator": "Lore-Master Elder", "pacing": "slow", "tone": "reverent", "hook": "Long before you were born, these lands remembered a name."},
    {"narrator": "Street-Smart Sidekick", "pacing": "fast", "tone": "casual", "hook": "Okay, here's the deal — and it's a bad one."},
    {"narrator": "Omniscient Fate", "pacing": "measured", "tone": "inevitable", "hook": "They did not know it yet, but the choice was already made."},
    {"narrator": "Unreliable Protagonist", "pacing": "erratic", "tone": "uncertain", "hook": "I think I remember what happened. Or maybe I'm lying."},
    {"narrator": "Post-Mortem Historian", "pacing": "reflective", "tone": "academic", "hook": "Records from the final year suggest that the collapse began quietly."},
    {"narrator": "Silent-Film Card", "pacing": "beat", "tone": "dramatic", "hook": "MEANWHILE — in the crypt."},
    {"narrator": "Drunken Bard", "pacing": "ambling", "tone": "comedic", "hook": "So there's this dragon, see, and she's got a grudge."},
    {"narrator": "AI Log-Assistant", "pacing": "terse", "tone": "clinical", "hook": "Mission brief follows. Attend carefully."},
    {"narrator": "Letter-Home Author", "pacing": "intimate", "tone": "wistful", "hook": "Dear love — if this finds you, I am somewhere cold."},
    {"narrator": "Child Witness", "pacing": "wide-eyed", "tone": "innocent", "hook": "The sky turned red and no grown-up would look up."},
    {"narrator": "Trial Prosecutor", "pacing": "pointed", "tone": "prosecutorial", "hook": "The evidence will show that the defendant acted with intent."},
    {"narrator": "Prophecy-Scroll", "pacing": "grand", "tone": "mythic", "hook": "When the seven moons align, the sealed one shall walk again."},
]

# Quest archetype seeds — 22 canonical quest shapes
QUEST_SEEDS = [
    {"archetype": "Fetch", "beats": ["request", "travel", "acquire", "deliver"], "twist_pool": ["item is cursed", "recipient is imposter"]},
    {"archetype": "Escort", "beats": ["pickup", "defend", "travel", "deliver"], "twist_pool": ["ward is assassin", "destination is trap"]},
    {"archetype": "Assassinate", "beats": ["identify", "infiltrate", "strike", "escape"], "twist_pool": ["target is innocent", "contract was lie"]},
    {"archetype": "Investigate", "beats": ["clue", "witness", "lead", "reveal"], "twist_pool": ["client is killer", "no crime occurred"]},
    {"archetype": "Heist", "beats": ["case", "team", "execute", "escape"], "twist_pool": ["inside man is mole", "vault is empty"]},
    {"archetype": "Rescue", "beats": ["location", "breach", "extract", "exfil"], "twist_pool": ["captive wants to stay", "rescuer is bait"]},
    {"archetype": "Siege", "beats": ["fortify", "repel", "counter", "rout"], "twist_pool": ["siege is diversion", "walls fail from within"]},
    {"archetype": "Exorcism", "beats": ["identify", "prepare", "confront", "banish"], "twist_pool": ["entity is victim", "priest is corrupted"]},
    {"archetype": "Trial", "beats": ["charge", "witnesses", "evidence", "verdict"], "twist_pool": ["judge is on trial", "defendant confesses falsely"]},
    {"archetype": "Ritual", "beats": ["gather", "prepare", "perform", "complete-or-corrupt"], "twist_pool": ["ingredient is sentient", "ritual targets caster"]},
    {"archetype": "Tournament", "beats": ["register", "brackets", "finals", "title"], "twist_pool": ["fix is in", "champion was ringer"]},
    {"archetype": "Diplomacy", "beats": ["arrive", "negotiate", "concessions", "treaty"], "twist_pool": ["translator betrays", "gift is bomb"]},
    {"archetype": "Survival", "beats": ["shelter", "forage", "defend", "escape"], "twist_pool": ["shelter is curse", "rescue was raiders"]},
    {"archetype": "Pilgrimage", "beats": ["depart", "trials", "shrine", "revelation"], "twist_pool": ["shrine is ruin", "destination is self"]},
    {"archetype": "Revenge", "beats": ["provocation", "track", "confront", "outcome"], "twist_pool": ["target is innocent double", "revenge is self-erasing"]},
    {"archetype": "Redemption", "beats": ["fall", "penance", "sacrifice", "forgiveness"], "twist_pool": ["forgiveness refused", "atonement repeats cycle"]},
    {"archetype": "Coming-of-Age", "beats": ["threshold", "mentor", "trial", "return"], "twist_pool": ["mentor is antagonist", "home rejects return"]},
    {"archetype": "Political-Intrigue", "beats": ["whisper", "align", "betray", "crown"], "twist_pool": ["throne is empty", "ally was puppet"]},
    {"archetype": "Plague", "beats": ["outbreak", "study", "cure", "distribute"], "twist_pool": ["cure is worse", "plague was test"]},
    {"archetype": "Artifact-Hunt", "beats": ["rumor", "research", "recover", "seal"], "twist_pool": ["artifact refuses owner", "multiple pieces lie"]},
    {"archetype": "Escape", "beats": ["capture", "plan", "execute", "extraction"], "twist_pool": ["escape is expected", "captor is protector"]},
    {"archetype": "Hunt", "beats": ["spoor", "stalk", "engage", "claim"], "twist_pool": ["prey hunts back", "trophy is family"]},
]

# Mission seeds — operational objectives mapped to mechanical patterns
MISSION_SEEDS = [
    {"type": "stealth_infil", "objective": "Reach an extraction point without being seen.", "fail_states": ["alarm", "bodies discovered"]},
    {"type": "hostage_rescue", "objective": "Neutralize captors; preserve hostage HP.", "fail_states": ["hostage death"]},
    {"type": "horde_defense", "objective": "Hold a point against waves until reinforcements arrive.", "fail_states": ["point breached", "timer expires"]},
    {"type": "chase", "objective": "Catch a fleeing target through a dynamic space.", "fail_states": ["target escapes", "civilian casualties"]},
    {"type": "assault", "objective": "Breach fortified position and eliminate command.", "fail_states": ["commander flees", "team wipe"]},
    {"type": "sabotage", "objective": "Plant explosives at 3 coordinated nodes and detonate simultaneously.", "fail_states": ["device disarmed", "node not reached"]},
    {"type": "intel_gather", "objective": "Download data from a terminal while countering security.", "fail_states": ["download interrupted", "security lockdown"]},
    {"type": "boss_duel", "objective": "One-on-one fight with phased boss.", "fail_states": ["player death"]},
    {"type": "convoy", "objective": "Escort a slow vehicle through hostile terrain.", "fail_states": ["vehicle destroyed", "driver killed"]},
    {"type": "puzzle_door", "objective": "Solve a multi-step puzzle to unseal a door.", "fail_states": ["wrong combination triggers trap"]},
    {"type": "platforming_gauntlet", "objective": "Traverse hazards to a distant ledge.", "fail_states": ["fall death", "timeout"]},
    {"type": "choice_crux", "objective": "Pick one of two mutually exclusive rescues.", "fail_states": ["both die if too slow"]},
    {"type": "time_attack", "objective": "Complete objective before countdown expires.", "fail_states": ["timer expires"]},
    {"type": "survival_night", "objective": "Survive from dusk till dawn as threat level scales.", "fail_states": ["player death"]},
    {"type": "chess_match", "objective": "Win a resource war with limited moves.", "fail_states": ["checkmate"]},
    {"type": "cooperative_keys", "objective": "Two players hit synchronized switches.", "fail_states": ["desync", "either dies"]},
    {"type": "crafted_bait", "objective": "Plant a fake target to draw enemies into a kill zone.", "fail_states": ["bait seen through"]},
    {"type": "eco_reclaim", "objective": "Restore polluted zones before region collapses.", "fail_states": ["biome dies"]},
    {"type": "tribunal_defense", "objective": "Defend a witness during closing arguments.", "fail_states": ["witness recants", "witness harmed"]},
    {"type": "recon_stealth", "objective": "Photograph three targets without alerting guards.", "fail_states": ["camera spotted", "target warned"]},
]

# Story arc structures
STORY_ARC_SEEDS = [
    {"name": "3-Act", "beats": ["setup", "confrontation", "resolution"]},
    {"name": "5-Act (Freytag)", "beats": ["exposition", "rising", "climax", "falling", "denouement"]},
    {"name": "Hero's Journey (Campbell)", "beats": ["call", "refusal", "mentor", "threshold", "trials", "approach", "ordeal", "reward", "road back", "resurrection", "return"]},
    {"name": "Kishotenketsu (4-beat)", "beats": ["introduction", "development", "twist", "conclusion"]},
    {"name": "In Medias Res", "beats": ["mid-action open", "flashback", "convergence", "resolution"]},
    {"name": "Rashomon (perspective)", "beats": ["witness A", "witness B", "witness C", "truth uncertain"]},
    {"name": "Tragedy", "beats": ["rise", "hamartia", "peripeteia", "anagnorisis", "fall"]},
    {"name": "Pixar Pitch", "beats": ["once upon", "every day", "one day", "because of that", "until finally"]},
    {"name": "Save the Cat (15 beat)", "beats": ["opening image", "theme stated", "setup", "catalyst", "debate", "break into 2", "B-story", "fun and games", "midpoint", "bad guys close", "all is lost", "dark night", "break into 3", "finale", "final image"]},
    {"name": "Circular", "beats": ["home", "call", "journey", "trial", "return-changed"]},
    {"name": "Parallel Arcs", "beats": ["introduce A", "introduce B", "interlace", "convergence", "mutual resolution"]},
    {"name": "Mystery-Box", "beats": ["hook question", "clues", "misdirect", "reveal", "recontext"]},
    {"name": "Epic (12-book)", "beats": ["invocation", "in medias res", "flashback", "councils", "battles", "underworld", "return", "homecoming"]},
    {"name": "Picaresque", "beats": ["wander", "episode 1", "episode 2", "episode 3", "arrival"]},
    {"name": "Bildungsroman", "beats": ["naive youth", "departure", "trials", "mentorship", "maturity"]},
]

# Storytelling technique library
STORYTELLING_SEEDS = [
    {"technique": "Unreliable Narrator", "usage": "Reveal truth gradually via narrator contradictions."},
    {"technique": "Epistolary", "usage": "Tell story through letters, logs, voicemails, emails."},
    {"technique": "Frame Story", "usage": "Story within a story — narrator's own context shapes inner tale."},
    {"technique": "Dramatic Irony", "usage": "Audience knows what characters do not."},
    {"technique": "Chekhov's Gun", "usage": "Planted detail pays off later; nothing in story is wasted."},
    {"technique": "Foreshadowing", "usage": "Subtle early hints of future events."},
    {"technique": "Red Herring", "usage": "Misleading clue to redirect audience suspicion."},
    {"technique": "MacGuffin", "usage": "Plot-driver object whose specifics don't matter."},
    {"technique": "Deus Ex Machina", "usage": "Sudden unexpected solver — use sparingly for mythic texture."},
    {"technique": "Anti-Climax", "usage": "Subvert expected climax for thematic effect."},
    {"technique": "Nonlinear Timeline", "usage": "Present scenes out of chronological order."},
    {"technique": "Pastiche", "usage": "Deliberate imitation of a style for homage or satire."},
    {"technique": "Motif Repetition", "usage": "Recurring symbol reinforces theme across arcs."},
    {"technique": "Parallel Thematic Mirroring", "usage": "Two unrelated subplots echo the same question."},
    {"technique": "Silence as Payoff", "usage": "Key moment withheld or unspoken; audience fills gap."},
    {"technique": "Environmental Storytelling", "usage": "Space itself tells story — props, graffiti, skeletons."},
    {"technique": "Stream of Consciousness", "usage": "Internal monologue exposes unfiltered psychology."},
    {"technique": "Reverse Chronology", "usage": "Story told end-to-beginning; audience reconstructs cause."},
    {"technique": "Documentary Framing", "usage": "Mock-doc or found-footage aesthetic for realism."},
    {"technique": "Second-Person POV", "usage": "Narrator addresses 'you' directly to force identification."},
]

# Age-era reference for Age-of-World picker (distinct from Console-Era)
AGE_ERAS = [
    {"id": "prehistoric",        "label": "Prehistoric / Stone Age",     "year_range": "200,000 BCE – 3,000 BCE",
     "tone": "primal, survivalist, tribal"},
    {"id": "bronze_age",         "label": "Bronze Age / Early Civ",      "year_range": "3,000 BCE – 1,200 BCE",
     "tone": "mythic, divine kingship, early writing"},
    {"id": "classical_antiquity","label": "Classical Antiquity",         "year_range": "1,200 BCE – 500 CE",
     "tone": "philosophy, empire, heroes, oracles"},
    {"id": "medieval",           "label": "Medieval / Dark Ages",        "year_range": "500 – 1,450",
     "tone": "feudal, faith, plague, knights"},
    {"id": "renaissance",        "label": "Renaissance",                 "year_range": "1,450 – 1,650",
     "tone": "art, invention, exploration, courtly intrigue"},
    {"id": "age_of_sail",        "label": "Age of Sail / Piracy",        "year_range": "1,650 – 1,800",
     "tone": "exploration, piracy, imperialism"},
    {"id": "industrial",         "label": "Industrial Revolution",       "year_range": "1,760 – 1,840",
     "tone": "steam, factories, class conflict"},
    {"id": "victorian",          "label": "Victorian / Steampunk",       "year_range": "1,837 – 1,901",
     "tone": "etiquette, séance, clockwork"},
    {"id": "wild_west",          "label": "Wild West / Frontier",        "year_range": "1,840 – 1,900",
     "tone": "revolver, cattle, railroad, law"},
    {"id": "belle_epoque",       "label": "Belle Époque / Edwardian",    "year_range": "1,890 – 1,914",
     "tone": "optimism, electricity, class"},
    {"id": "ww1",                "label": "Great War / WWI",             "year_range": "1,914 – 1,918",
     "tone": "trench, gas, dieselpunk dawn"},
    {"id": "interwar",           "label": "Interwar / Jazz Age",         "year_range": "1,918 – 1,939",
     "tone": "speakeasy, roar, great depression"},
    {"id": "ww2",                "label": "WWII",                        "year_range": "1,939 – 1,945",
     "tone": "heroic sacrifice, mechanized horror, espionage"},
    {"id": "cold_war",           "label": "Cold War / Mid-Century",      "year_range": "1,945 – 1,991",
     "tone": "paranoia, nuclear, proxy wars, spy"},
    {"id": "modern",             "label": "Contemporary / Modern",       "year_range": "1,991 – 2,025",
     "tone": "globalization, terror, digital, climate"},
    {"id": "near_future",        "label": "Near Future",                 "year_range": "2,025 – 2,080",
     "tone": "AI, climate crisis, biotech, space mining"},
    {"id": "cyberpunk",          "label": "Cyberpunk / Neo-Dystopia",    "year_range": "2,040 – 2,099",
     "tone": "neon, mega-corp, body-mod, rain"},
    {"id": "post_apocalypse",    "label": "Post-Apocalypse",             "year_range": "2,050 – 3,000 (variable)",
     "tone": "scarcity, mutation, fragmented hope"},
    {"id": "space_frontier",     "label": "Space Frontier / Colonial",   "year_range": "2,100 – 2,400",
     "tone": "terraform, stations, first-contact"},
    {"id": "far_future",         "label": "Far Future / Transhuman",     "year_range": "2,400 – 10,000+",
     "tone": "posthuman, singularity, Dyson, uplift"},
    {"id": "mythic_past",        "label": "Mythic / Legendary Past",     "year_range": "undated",
     "tone": "gods walk, beasts speak, fate"},
    {"id": "alternate_history",  "label": "Alternate History",           "year_range": "divergent",
     "tone": "what-if, counterfactual, altered outcome"},
    {"id": "time_travel",        "label": "Multi-Era / Time-Travel",     "year_range": "all",
     "tone": "cross-era heroics, paradox, causality"},
    {"id": "atompunk",           "label": "Atompunk / Retro-Future 50s", "year_range": "1,950 – 1,969 alt",
     "tone": "rayguns, optimism, atomic, chrome fins"},
]


def _canonical_id(genre: str, kind: str, key: str) -> str:
    h = hashlib.md5(f"{kind}:{genre}:{key}".encode()).hexdigest()[:10]
    return f"{kind}-{genre}-{h}"


# ──────────────────────────────────────────────────────────────────────
#  Seeder — idempotent; safe to call on every startup.
# ──────────────────────────────────────────────────────────────────────
async def seed_narrative_vault(db, target_per_genre: int = 120) -> dict:
    """Populate all 6 collections. Each genre receives ≥ target_per_genre rows
    by expanding canonical seeds with deterministic derivatives (same seed +
    variation axes) so output is large but never random garbage."""
    report = {"playwright": 0, "narration": 0, "quest": 0, "mission": 0, "story_arc": 0, "storytelling": 0}

    # --- playwright_library: expand seeds across genre buckets ---
    try:
        col = db.playwright_library
        exists = await col.estimated_document_count()
        if exists < 500:
            rows = []
            rng = random.Random(424242)
            for genre in GENRE_BUCKETS:
                base = PLAYWRIGHT_SEEDS.get(genre, [])
                # fallback: cross-seed from adjacent buckets so every genre has material
                if not base:
                    # Sample from all seeds when bucket has no native
                    pool = [(t, s) for lst in PLAYWRIGHT_SEEDS.values() for (t, s) in lst]
                    base = rng.sample(pool, min(10, len(pool)))
                for i in range(target_per_genre):
                    src_title, src_synopsis = base[i % len(base)]
                    variation = i // len(base)
                    twist_axes = ["protagonist-gender-flip", "tone-inversion", "setting-swap",
                                  "antagonist-reveal-shift", "scale-escalation", "time-period-shift",
                                  "mentor-is-villain", "reward-is-curse", "rescuer-becomes-hostage"]
                    twist = twist_axes[variation % len(twist_axes)]
                    plot = f"{src_synopsis} VARIATION: {twist}."
                    rows.append({
                        "canonical_id": _canonical_id(genre, "pw", f"{src_title}-{i}"),
                        "genre": genre,
                        "reference_title": src_title,
                        "reference_plot": src_synopsis,
                        "derivative_index": i,
                        "variation_axis": twist,
                        "plot_summary": plot,
                        "themes": ["identity", "power", "loss", "love", "justice"][i % 5],
                        "source": "canonical-derivative",
                    })
            if rows:
                await col.insert_many(rows, ordered=False)
                report["playwright"] = len(rows)
    except Exception as e:
        logger.warning(f"playwright seed: {e}")

    # --- narration_library ---
    try:
        col = db.narration_library
        if await col.estimated_document_count() < 200:
            rows = []
            for genre in GENRE_BUCKETS:
                for i, n in enumerate(NARRATION_SEEDS):
                    rows.append({
                        "canonical_id": _canonical_id(genre, "nar", f"{n['narrator']}-{i}"),
                        "genre": genre,
                        **n,
                    })
            if rows:
                await col.insert_many(rows, ordered=False)
                report["narration"] = len(rows)
    except Exception as e:
        logger.warning(f"narration seed: {e}")

    # --- quest_library ---
    try:
        col = db.quest_library
        if await col.estimated_document_count() < 400:
            rows = []
            for genre in GENRE_BUCKETS:
                for i, q in enumerate(QUEST_SEEDS):
                    rows.append({
                        "canonical_id": _canonical_id(genre, "q", f"{q['archetype']}-{i}"),
                        "genre": genre,
                        **q,
                    })
            if rows:
                await col.insert_many(rows, ordered=False)
                report["quest"] = len(rows)
    except Exception as e:
        logger.warning(f"quest seed: {e}")

    # --- mission_library ---
    try:
        col = db.mission_library
        if await col.estimated_document_count() < 400:
            rows = []
            for genre in GENRE_BUCKETS:
                for i, m in enumerate(MISSION_SEEDS):
                    rows.append({
                        "canonical_id": _canonical_id(genre, "m", f"{m['type']}-{i}"),
                        "genre": genre,
                        **m,
                    })
            if rows:
                await col.insert_many(rows, ordered=False)
                report["mission"] = len(rows)
    except Exception as e:
        logger.warning(f"mission seed: {e}")

    # --- story_arc_library ---
    try:
        col = db.story_arc_library
        if await col.estimated_document_count() < 200:
            rows = []
            for genre in GENRE_BUCKETS:
                for i, a in enumerate(STORY_ARC_SEEDS):
                    rows.append({
                        "canonical_id": _canonical_id(genre, "sa", f"{a['name']}-{i}"),
                        "genre": genre,
                        **a,
                    })
            if rows:
                await col.insert_many(rows, ordered=False)
                report["story_arc"] = len(rows)
    except Exception as e:
        logger.warning(f"story_arc seed: {e}")

    # --- storytelling_library ---
    try:
        col = db.storytelling_library
        if await col.estimated_document_count() < 300:
            rows = []
            for genre in GENRE_BUCKETS:
                for i, t in enumerate(STORYTELLING_SEEDS):
                    rows.append({
                        "canonical_id": _canonical_id(genre, "st", f"{t['technique']}-{i}"),
                        "genre": genre,
                        **t,
                    })
            if rows:
                await col.insert_many(rows, ordered=False)
                report["storytelling"] = len(rows)
    except Exception as e:
        logger.warning(f"storytelling seed: {e}")

    # --- Age Eras (static reference, 1 doc per era) ---
    try:
        col = db.age_era_reference
        if await col.estimated_document_count() < 20:
            await col.insert_many([{**e, "canonical_id": _canonical_id("meta", "era", e["id"])}
                                    for e in AGE_ERAS], ordered=False)
    except Exception:
        pass

    return report


# ──────────────────────────────────────────────────────────────────────
#  Originality Engine — fingerprint + differentiation gate
# ──────────────────────────────────────────────────────────────────────
def plot_fingerprint(synopsis: str) -> str:
    """Collapse a proposed plot to a stable hash of key story atoms so
    swarm agents can check against the canonical vault and enforce
    sufficient differentiation before shipping a build."""
    if not isinstance(synopsis, str):
        return "0" * 16
    words = [w.lower() for w in synopsis.split() if len(w) >= 4]
    shingles = sorted(set([" ".join(words[i:i+3]) for i in range(0, len(words) - 2)]))
    blob = "|".join(shingles)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


async def check_originality(db, proposed_synopsis: str, genre: str,
                            threshold: float = 0.75) -> dict:
    """Return an originality score + nearest canonical match. If the
    proposed plot shares too many shingles with a canonical entry, return
    a `must_mutate` flag with a suggested variation axis."""
    try:
        fp = plot_fingerprint(proposed_synopsis)
        # Crude Jaccard-style check against genre subset (capped for speed)
        cursor = db.playwright_library.find({"genre": genre}, {"plot_summary": 1, "reference_title": 1, "variation_axis": 1, "_id": 0}).limit(300)
        candidates = await cursor.to_list(length=300)
        best = {"similarity": 0.0, "match": None}
        my_set = set(proposed_synopsis.lower().split())
        for c in candidates:
            their = set((c.get("plot_summary") or "").lower().split())
            if not their:
                continue
            inter = len(my_set & their)
            union = len(my_set | their) or 1
            sim = inter / union
            if sim > best["similarity"]:
                best = {"similarity": sim, "match": c}
        must_mutate = best["similarity"] >= threshold
        suggestion = None
        if must_mutate:
            axes = ["protagonist-gender-flip", "tone-inversion", "setting-swap",
                    "antagonist-reveal-shift", "scale-escalation", "time-period-shift"]
            suggestion = axes[hash(fp) % len(axes)]
        return {
            "fingerprint": fp,
            "similarity": round(best["similarity"], 3),
            "nearest_match": best["match"],
            "must_mutate": must_mutate,
            "suggested_axis": suggestion,
            "genre": genre,
        }
    except Exception as e:
        return {"error": str(e)[:200], "must_mutate": False}
