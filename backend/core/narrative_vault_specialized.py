"""
╔════════════════════════════════════════════════════════════════════════╗
║  NARRATIVE VAULT — SPECIALIZED EXPANSION                                ║
║  ────────────────────────────────────────────────────────────────────  ║
║  200 specialized sub-databases covering every facet of game creation.  ║
║  Each key becomes a MongoDB collection seeded per-genre with           ║
║  procedural expansion — yielding hyperscale content for the swarm.     ║
║                                                                        ║
║  Consumed by:                                                          ║
║    • seed_specialized_vault()  — idempotent seeder                     ║
║    • sample_vault_context()    — pulls cross-vault context for prompts ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import hashlib
import logging
from typing import Iterable

logger = logging.getLogger("GalaxyStudio.SpecializedVault")

# ══════════════════════════════════════════════════════════════════════
#  200+ specialized topics. Each topic has "seeds" (canonical examples)
#  and "axes" (procedural variation dimensions).
# ══════════════════════════════════════════════════════════════════════
# Compact shorthand: (collection_key, [seeds...])
# Procedural expander combines every seed with every axis to produce
# thousands of deterministic derivatives per genre per collection.
SPECIALIZED_TOPICS: dict[str, list[str]] = {
    # ─── Characters / Casting ───
    "character_archetypes": ["Reluctant Hero", "Chosen One", "Anti-Hero", "Tragic Hero", "Rogue", "Mentor", "Herald", "Shapeshifter", "Trickster", "Shadow-Self", "Ordinary World Guardian", "Wise Fool", "Femme Fatale", "Faithful Companion", "Reformed Villain", "Fallen Champion", "Eternal Exile", "Golden Child", "Scapegoat", "Monstrous Other", "Last of Their Kind", "Cursed Bloodline", "Time-Displaced Soul", "Forgotten God", "Patchwork Soldier", "Dreamer-Prophet", "Silent Witness", "Vengeful Ghost", "Earnest Apprentice", "Jaded Veteran"],
    "character_backstories": ["Lost sibling vendetta", "Village burned at 8", "Orphanage raised mercenary", "Exiled royal heir", "Amnesiac assassin", "Reformed cultist", "Runaway noble", "Debt-bound thief", "Hedge-wizard outcast", "War deserter with medals", "Ship captain's bastard", "Genetic experiment escapee", "Time-traveler stranded", "Cursed immortal", "Last mage of dead school", "Robot awakened to sentience", "Gladiator freedman", "Midwife accused of witchcraft", "Librarian of a burned archive", "Corporate fixer turned whistleblower"],
    "character_motivations": ["Revenge for family", "Find missing sibling", "Prove lineage", "Break a generational curse", "Redeem past atrocity", "Protect unlikely ward", "Discover true name", "Settle unpaid debt", "Complete teacher's unfinished work", "Escape predetermined fate", "Unite warring factions", "Preserve dying tradition", "Find canonical heir", "Decode ancestral message", "Master forbidden art", "Save spouse from fate", "Prevent prophesied apocalypse", "Avenge dead mentor", "Reclaim stolen identity", "Atone for causing war"],
    "character_voices": ["Laconic and dry", "Verbose academic", "Streetwise slang", "Archaic formal", "Poet-philosopher", "Childlike wonder", "Bitter cynic", "Dead-pan sarcastic", "Military clipped", "Mystical riddling", "Hesitant trauma", "Over-confident salesman", "Technical jargon-heavy", "Second-person narrator", "Stage-accented theatrical", "Reforming profanity addict"],
    "character_flaws": ["Crippling pride", "Alcoholism", "Compulsive lying", "Self-sacrifice addiction", "Trust-blindness", "Rage on command", "Truth-allergy", "Impulse gambling", "Romantic destructive", "Indecision paralysis", "Prophecy-fixation", "Perfectionism", "Superstition-driven", "Misplaced loyalty", "Numbing dissociation", "Revenge-obsession"],
    "character_virtues": ["Loyalty beyond death", "Compassion for enemies", "Unshakable resolve", "Intellectual humility", "Fearless candor", "Craft mastery", "Self-sacrificial courage", "Patience of mountains", "Empathic listening", "Honor the dead", "Keep one's word", "Protect the weak", "Admit error", "Temper justice with mercy"],
    "character_relationships": ["Blood-feud rivalry", "Reluctant partnership", "Unrequited devotion", "Parent-child estrangement", "Teacher-student betrayal", "Sibling competition", "Forbidden romance", "Band-of-brothers bond", "Employer-servant loyalty", "Competing heirs", "Prophet-disciple dependence", "Hostage-captor Stockholm", "Arranged-marriage partners", "Friends turned enemies turned allies", "Twin soul split"],
    "character_growth_arcs": ["Naïve → disillusioned → wise", "Coward → reluctant brave → fearless", "Selfish → altruistic → martyr", "Believer → doubter → reformed believer", "Ordinary → chosen → self-chosen", "Tyrant → broken → just", "Hunted → hunter → shepherd", "Isolated → connected → leader", "Student → master → teacher", "Fallen → penitent → redeemed"],
    "companion_archetypes": ["Loyal knight", "Sharp-tongued bard", "Stoic beast-tamer", "Reformed thief", "Orphan mage", "Exiled prince", "Talking animal", "Undead scholar", "Golem of stone", "Ghost of mentor", "Child prodigy", "Mechanical aide", "Parasitic symbiote", "Sarcastic AI", "Sentient weapon"],
    "npc_minor_roles": ["Innkeeper", "Weaponsmith", "Herbalist", "Tax-collector", "Town gossip", "Dockworker", "Thieving urchin", "Pilgrim", "Roadside oracle", "Fallen knight", "Greedy priest", "Retired hero", "Exiled scholar", "Midwife", "Wandering poet", "Corrupt magistrate", "Old soldier", "Mute guide"],
    "villain_archetypes": ["Tyrant King", "Cosmic Horror", "Fallen Mentor", "Revolutionary Zealot", "Corporate Oligarch", "Rival Dynasty", "AI Gone Rogue", "Parasitic God", "Time-Traveling Self", "Amoral Merchant", "Dark Messiah", "Child Prodigy Villain", "Slow Plague", "Sentient Plague-Prince", "Dreaming Eldritch", "Political Puppet-Master", "Grief-Made Monster"],
    "villain_plans": ["Reshape world in image", "Sacrifice millions for immortality", "Resurrect dead god", "Erase bloodline", "Claim divine throne", "Force evolution", "Consume reality", "Enforce perfect utopia", "Rewrite history", "Become singular", "Break cycle of death", "Feed the void", "Annul free will", "Trigger extinction rebirth", "Awaken sleeping titan"],

    # ─── Dialogue ───
    "dialogue_one_liners": ["\"I don't hate you. I just can't afford to care.\"", "\"You spoke of honor. I gave mine to the crows.\"", "\"Every ghost here wears my face.\"", "\"I promised your mother. I keep no other promises now.\"", "\"This gun is older than your kingdom.\"", "\"I am the last one who remembers her name.\"", "\"The gods grew bored. I did not.\"", "\"Step forward and learn what quiet costs.\"", "\"Mercy is a language I forgot.\"", "\"You asked for prophecy. I am its price.\"", "\"Walk. Or be carried.\"", "\"The debt is paid in full.\""],
    "dialogue_openers": ["You shouldn't have come.", "I've been waiting.", "So it begins.", "You look like your father.", "Do you know why I'm here?", "That was a mistake.", "I told them you'd come.", "You want the truth? Fine."],
    "dialogue_closers": ["Remember me.", "Don't follow.", "Go, before I change my mind.", "It was always you.", "The fire is out.", "Try to live.", "Not yet. Not like this.", "If you see her, tell her I tried."],
    "dialogue_arguments": ["moral relativism clash", "means-vs-ends duel", "loyalty-vs-truth clash", "old-world-vs-new dispute", "love-vs-duty agony", "mercy-vs-justice quarrel", "sacrifice-vs-survival debate", "faith-vs-reason confrontation", "honor-vs-expediency rupture", "tradition-vs-reform standoff"],
    "dialogue_confessions": ["I started the fire.", "Your father paid me.", "I was always the mole.", "I do not remember her face anymore.", "I bargained with it.", "I let him die.", "I am the prophecy.", "I loved you first.", "I built the weapon.", "I was the ghost you saw."],
    "dialogue_jokes": ["dwarf-tall-order", "goblin-union-wages", "mage-too-many-apprentices", "paladin-no-fun", "dragon-invoice-overdue", "necromancer-HR-department", "adventurer-insurance-claim", "tavern-regulars-rotation", "bard-wrong-gig"],
    "dialogue_banter": ["mission-briefing-ribbing", "after-fight-teasing", "campfire-story-swap", "mock-interrogation", "inside-joke-repeat", "competitive-brag-off", "shared-grief-gallows-humor"],
    "dialogue_silences": ["stares-grave", "fingers-ring", "hand-on-hilt-but-does-not-draw", "meets-gaze-too-long", "closes-book-slowly", "turns-away-shoulders-shake", "tears-without-words", "nods-once-walks-out"],

    # ─── World Building ───
    "kingdoms": ["Sunreach", "Blackwater Dominion", "The Twelve Verdant States", "Ironclad Republic", "Empire of Sighs", "Pale Accord", "Crownless Alliance", "Mirrorshard Sultanate", "The Nightless Tetrarchy", "Driftwood Coalition", "Crimson Concordat", "The Starving Duchies"],
    "cities": ["Glasshearth", "Nine-Bridges", "Saltgrave", "High Candlewick", "The Needle", "Blackroot Port", "Under-Forge", "Ember Crossing", "Goldshade", "The Hundred Houses", "Lowtide", "Umbralis", "Spireholm", "Riverbone", "Lampspine"],
    "villages": ["Farwater", "Hollyknot", "Milesend", "Oxhollow", "Saltpan", "Marrowdell", "Brassfoot", "Greenveil", "Pitchfork", "Oldlamp", "Broken Tooth", "Mother's Rest"],
    "regions": ["The Spine", "Charred Moors", "Saltglass Sea", "Wept Jungle", "Ember Badlands", "Silent Fens", "Nine Winds Steppe", "Sunken Archipelago", "The Remembering Forest", "Glasshadow Mountains", "Undersongrift", "Bone Reach"],
    "biomes": ["Crystal tundra", "Mushroom canopy forest", "Hollowed honeycomb desert", "Sky-tall grassland", "Drowned highways", "Caustic salt flats", "Hanging jungle islands", "Molten plains", "Aurora-lit taiga", "Living reef city", "Perpetually storming coast", "Moonsilver marsh"],
    "landmarks": ["The Iron Bell that never rings", "Tower of Mirrors", "Weeping Colossus", "Bridge of Agreements", "Gate That Remembers", "Sunken Cathedral", "Observatory of Lost Stars", "Glass Garden", "Empty Throne Room", "Serpent's Causeway", "First Library", "The Twin Monoliths"],
    "geography_features": ["Floating river", "Bottomless sinkhole", "Time-dilated valley", "Upside-down waterfall", "Bioluminescent cave network", "Tidal salt desert", "Volcanic glass plain", "Sentient forest", "Eternal eclipse zone", "Coral mountain range"],
    "climates": ["monsoon-broken", "eight-month winter", "perma-twilight", "three-sun day", "magnetic storm season", "ash rain", "bone-dry gale plains", "aurora summer", "fungal wet season", "cryo-desert nights"],
    "natural_disasters": ["Soul quake", "Star fall", "Memory tide", "Wyrm migration", "Glass storm", "Gravity collapse", "Plague wind", "Dream-flood", "Age-surge", "Shadow eclipse"],
    "calendar_systems": ["3-moon lunar", "13-month solar", "tidal reckoning", "emperor-reign dating", "battle-anniversary counting", "catastrophe-offset years", "great-harvest cycles"],
    "flora": ["Singing lilies", "Sorrow-vine", "Glass-bark pine", "Memory moss", "Voidbloom cactus", "Flametongue orchid", "Icebark willow", "Starroot tuber", "Breath fern", "Clockwork daffodil"],
    "fauna": ["Singing wolf", "Salt-dolphin", "Crystal tortoise", "Dream-moth", "Iron-feather hawk", "Glass-scale fish", "Tide-leopard", "Star-spider", "Hollow elk", "Ember-newt", "Whisper bat", "Duskram"],

    # ─── Lore / Mythology ───
    "creation_myths": ["Two twin titans wove the world in braided light", "The world is the corpse of a slain god, still dreaming", "Reality boiled out of a cosmic wound", "A gardener placed each star as a seed", "The first mother split herself to make everything", "The world woke up already old", "A mortal tricked eternity into solidifying"],
    "origin_stories": ["A god stitched mortals from loneliness", "Humanity is the regret of an angel", "The first people fell from the moon", "A machine dreamed life and refused to wake", "Elves are the memory of a dead species", "Dwarves are the tears of the earth"],
    "pantheon_structures": ["Seven high gods and a thousand minor", "Duotheism — light and dark equally loved", "Henotheism — one chief god among many", "Ancestor worship only", "Nature spirits stratified by element", "Single creator withdrawn; lesser saints accessible"],
    "religions": ["The Quiet Flame", "Nine-Named Sea", "Creed of the Turning Wheel", "Last Letter Church", "Glasshand Covenant", "Anointed Machine", "The Unseen Ones", "Salt Communion", "Prophet-Ash Order", "Starkeeper Guild"],
    "prophecies": ["When three moons bleed, the sealed gate opens", "The last of a line shall wake the First", "A blind child shall name the king", "The river runs red thrice before the crown falls", "The tomb that was never built shall be filled", "The tower that remembers shall forget"],
    "legends": ["The knight who killed their own dragon", "The witch who bargained with winter", "The brothers who split the sun", "The ship that sails dry land", "The orphan who crowned a god", "The smith who forged a heart"],
    "taboos": ["Never speak the river's true name", "Do not build doors facing north at dusk", "Salt is offered before meat", "Mirrors covered at births", "No songs after sunset in the forest", "Names of the dead replaced with colors"],
    "artifacts": ["The Unbroken Scale", "Lamp That Lights Lies", "Crown of Split Oaths", "Blade That Asks", "Boots of the Thousand-Mile Grief", "Mask of Endings", "Needle of Mothers", "Helm of the Emptied King", "Staff of the Green Pact", "Cup of the Dawn Bargain"],

    # ─── Factions / Organizations ───
    "factions": ["Order of the Quiet Flame", "Sea-Singers Guild", "Crownless Brotherhood", "The Weighted Council", "Glasseye Legion", "Salt Pact", "Nightwardens", "The Ledger Keepers", "Iron Accord", "Ember Priesthood", "Shadow Guild", "Twilight Tribunal"],
    "guilds": ["Shipwrights' Hall", "Needleworkers' Circle", "Blacksmiths' League", "Cartographers' Union", "Printmakers' Confraternity", "Heralds' Bureau", "Undertakers' Syndicate", "Alchemists' Obsidian", "Falconers' Keep", "Lanternkeepers' Bond"],
    "cults": ["Church of the Last Breath", "Bone-Lovers", "Reverent of the Turning", "Rot-Singers", "Glassblood Sisters", "Harbingers of the Nineveh", "Deep-Eye Clan"],
    "military_orders": ["Ashen Guard", "Nineveh Hussars", "Blood-Oath Knights", "The Stone-Hearts", "Moonsilver Lance", "Black Candle Dragoons", "Salt Reavers"],
    "criminal_orgs": ["Bone Market", "The Sunken Crown", "Eight-Finger Family", "The Silent Hand", "Rivermouth Syndicate", "Lantern Gang", "The Counting House"],
    "political_parties": ["Reformists of the Third Charter", "Royalist Remnant", "Guild Accord", "Merchant Assembly", "Populist Flame", "Isolationist Concord"],
    "ethnic_groups": ["Saltfolk", "Ash-born", "Highlake Clans", "Desertwalkers", "Moon-marked Kin", "River Travellers"],
    "houses_noble": ["House Greyward", "House Orilanth", "House of the Ember Vow", "House Saltglass", "House Nineveh", "House Dawncrown"],

    # ─── Magic Systems & Tech Trees ───
    "magic_systems": ["Rune-binding with finite glyphs", "Blood-cost with proportional return", "Name-True — speak the secret to command", "Sympathetic linkage — part stands for whole", "Dreamwalking with waking cost", "Sigil-based pre-cast tattoos", "Elemental pact with displeasing spirits", "Mathematical geometry-spells", "Song-based memory magic", "Bargain-magic — negotiated cost", "Circular — erases cast memory", "Light-refraction prismatics"],
    "schools_of_magic": ["Pyromancy", "Cryomancy", "Necromancy", "Chronomancy", "Cartomancy", "Bibliomancy", "Haruspicy", "Glassblowing arcana", "Astromancy", "Spirit-pact thaumaturgy", "Shadowspeech"],
    "tech_trees": ["Industrial → Electric → Information → Quantum → Post-Singular", "Bronze → Iron → Steel → Alloy → Memory-Metal", "Steam → Diesel → Atom → Fusion → Zero-Point", "Analog → Digital → Networked → Hive → Post-Net"],
    "weapon_categories": ["Bladed one-handed", "Bladed two-handed", "Polearm", "Firearm (muzzle)", "Firearm (breech)", "Firearm (auto)", "Energy (beam)", "Energy (pulse)", "Siege", "Throwing", "Trap", "Explosive", "Monofilament", "Sonic", "Psionic", "Cursed"],
    "armor_types": ["Cloth", "Padded", "Leather", "Hide", "Chain", "Scale", "Plate", "Power-armor", "Biomesh", "Reactive-crystal"],
    "crafting_recipes": ["Ironsong Blade", "Moonmilk Tincture", "Silverthread Mantle", "Ashwater Elixir", "Starroot Bread", "Emberheart Flask", "Voidbound Coin", "Sunspoken Scroll"],
    "alchemy_mixes": ["stamina+haste", "healing+antidote", "invisibility-fragile", "mirror-of-truth", "sunpyre-burst", "deep-sleep", "courage-of-the-fallen"],
    "technology_inventions": ["Windcoil battery", "Tidal printing press", "Glass-logic engine", "Memory-salt storage", "Aether-thresher", "Bone-wire telegraph"],

    # ─── Economy & Trade ───
    "currencies": ["Stamped star-coin", "Promissory silk-note", "Engraved bone-chit", "Guild letter-of-credit", "Commodity grain-token", "Slave-bond note", "Tax-tile"],
    "trade_goods": ["Salt", "Silk", "Obsidian", "Memory-crystal", "Sunroot", "Steel", "Oil of the North", "Dye", "Parchment", "Ink", "Opium", "Ice"],
    "markets": ["Nightmarket", "Forge-fair", "Guild commons", "Black-silk exchange", "Harbor bond", "Temple alms-market"],
    "trade_routes": ["Salt Road (400 leagues)", "Silk Ribbon", "Black Canal", "Iron Spine", "Moonsilver Skyway", "Pilgrim's Mile"],
    "taxation_systems": ["Tithe", "Poll-tax", "Duty-on-passage", "Guild-levy", "Crown-decimation", "Voluntary patronage"],
    "labor_classes": ["Freeholder", "Bond-servant", "Guild journeyman", "Serf", "Itinerant", "Indentured mage", "Corporate-chattel"],

    # ─── Quests & Missions (extra granularity on top of core quest_library) ───
    "main_quests": ["Retrieve the sundered blade", "Expose the false king", "Awaken the sleeper", "Bind the rogue god", "Reach the dying star", "Restore the broken cycle", "Close the torn sky"],
    "side_quests": ["Find missing tax records", "Return the baker's daughter", "Test the new fishing net", "Investigate pies that sing", "Arrange a wedding truce", "Deliver illegal letters"],
    "fetch_objects": ["Bone of a saint", "Unopened letter", "Forbidden map", "Last coin of a dead dynasty", "Wedding ring of enemies", "Tears in a sealed vial", "Unread confession"],
    "escort_targets": ["Injured oracle", "Defecting general", "Pregnant diplomat", "Silent witness", "Wounded dragon", "Banished prince", "Blind cartographer"],
    "puzzle_types": ["balance-weights", "pattern-match", "pressure-plate-sequence", "light-beam-reflection", "language-decipher", "clock-alignment", "gravity-flip", "water-level", "shadow-match", "sliding-block", "color-mix", "rune-combine", "echo-locator", "tarot-read", "musical-notation"],
    "riddle_library": ["What walks but does not breathe? — a rumor", "What grows from burning? — legend", "Who is the king of clocks? — dawn", "Younger than you, older than time? — a promise", "Never worn, always bright? — a truth"],
    "boss_fight_patterns": ["three-phase-heal-between", "minion-summon-cycle", "environmental-hazard-shift", "invulnerability-window-exploit", "moral-choice-mid-fight", "companion-turncoat", "weapon-stolen-steal-back"],

    # ─── Items & Equipment ───
    "rare_items": ["Ring of Reversed Wounds", "Lantern of the Drowned", "Sword That Remembers", "Cape of Stolen Footsteps", "Book of Unwritten Pages", "Dice of Shared Fortune"],
    "consumables": ["Dream-tea", "Ashroot jerky", "Phoenix-feather lozenge", "Salted misery", "Starshine liquor", "Ground prayer"],
    "equipment_sets": ["Hunter of Twilight", "Mercenary of the Salt Coast", "Bone-priest regalia", "Storm-sailor kit", "Apprentice mage robes", "Deep-diver oilskin"],
    "unique_weapons": ["The Penitent Hammer", "Saltwife's Needle", "Silver Verdict", "Last-Word Pistol", "Dawn's Mercy", "Mother-of-Wars"],

    # ─── Combat / Mechanics ───
    "combat_styles": ["Dance-of-Coins", "Blood-Ledger", "Silent-Step", "Horse-Whisper", "Two-Blade Litany", "Broken-Guard Stance", "Storm-Form", "Crane-Silent"],
    "stances": ["Open guard", "High guard", "Low reaper", "Mirror stance", "Cradle stance", "Butcher form", "Featherfoot", "Iron-shell"],
    "combos": ["jab-jab-uppercut-throw", "dash-slash-pivot-slash", "counter-parry-riposte", "feint-grab-lift-slam", "shield-bash-wind-up-spin"],
    "status_effects": ["Burn", "Bleed", "Poison", "Hex", "Fear", "Curse-mark", "Silence", "Stun", "Slow", "Daze", "Confuse", "Doom-timer", "Corrosion", "Freeze"],
    "elemental_interactions": ["fire+oil=explosion", "water+lightning=chain-shock", "ice+wind=blizzard", "earth+plant=choke-roots", "shadow+light=void", "blood+salt=purify"],

    # ─── Economy of Experience ───
    "level_curves": ["linear-slow", "exponential-break-at-20", "soft-cap-50-then-prestige", "scale-with-story-only", "skill-trees-instead-of-level"],
    "skill_tree_topologies": ["tri-branch", "flat-menu", "mesh-graph", "pentagon-specialization", "respec-at-altars", "permadeath-subclass"],
    "progression_systems": ["class-based", "classless-skill", "deck-based", "gear-score", "reputation-gated", "seasonal-prestige"],

    # ─── AI / Behavior ───
    "ai_behaviors": ["patrol", "investigate", "flank", "retreat-regroup", "call-for-help", "ambush", "feign-death", "taunt-and-kite", "cover-and-suppress", "charge-berserk", "form-wall", "summon-pack"],
    "enemy_types_extra": ["Reanimated Priest", "Glass-knight", "Ember Revenant", "Star-scout", "Gene-spliced Brute", "Hollowed Saint", "Crystal Parasite", "Plague Courtier"],
    "boss_personalities": ["detached-curious", "mocking-playful", "grief-rage", "reluctant-duty", "zealot-joy", "mechanical-cold", "tragic-loving", "chaotic-artistic"],
    "ally_tactics": ["cover-fire", "flank-split", "anchor-defense", "distract-and-cycle", "revive-priority", "crowd-control-spam"],

    # ─── Accessibility & UX ───
    "ux_patterns": ["undo-last-turn", "pause-mid-dialogue", "skip-long-cutscene", "subtitles-with-speaker", "colorblind-friendly-palette", "arachnophobia-mode", "reduced-motion", "one-handed-input", "dyslexia-font", "high-contrast", "audio-description", "screen-reader-cues"],
    "ui_screen_templates": ["inventory-grid", "skill-tree-radial", "quest-log-tree", "map-layered", "crafting-bench", "dialogue-branch-tree", "bestiary-card", "codex-page", "shop-two-panel", "party-formation-grid"],

    # ─── Sound / Music ───
    "music_motifs": ["hero-theme-triplet", "villain-low-brass", "love-clarinet", "danger-cluster", "town-lute", "field-strings-glissando", "sacred-choir", "mechanical-click-percussion"],
    "sound_effects": ["blade-unsheath", "footstep-gravel", "door-creak-long", "coin-spill", "owl-call-night", "rain-on-tin", "arrow-whistle", "magic-tome-flutter"],
    "instrument_palettes": ["orchestral-romantic", "folk-acoustic", "synth-retrowave", "gothic-choir-organ", "post-rock-crescendo", "cyberpunk-industrial", "celtic-bodhrán", "drone-and-bell"],

    # ─── Visual & Art Direction ───
    "art_palettes": ["Autumn embers", "Frozen moonlight", "Sunken teal", "Neon magenta rain", "Desert sand & lapis", "Blood-rust and gold", "Stormglass & charcoal", "Candle-wax & slate"],
    "art_styles": ["Painterly oil", "Cel-shaded", "Pixel-art 16-bit", "Low-poly 2000s retro", "Photoreal", "Ukiyo-e woodblock", "Stained-glass", "Charcoal sketch", "Papercraft", "Claymation"],
    "lighting_setups": ["single-candle", "overcast-flat", "high-contrast-noir", "golden-hour", "storm-lightning-flash", "bioluminescent-night", "under-ice-refraction", "eclipsed-red"],
    "camera_shots": ["Dutch-angle", "Low-hero", "Top-down-tactical", "Over-shoulder", "Handheld-shake", "Still-tableau", "Long-pull-reveal"],

    # ─── Cinematics / Cutscene Beats ───
    "cutscene_templates": ["title-drop-after-hook", "cold-open-action", "slow-zoom-reveal", "flashback-desaturated", "parallel-montage", "silent-character-moment", "reflection-mirror", "campfire-speech"],
    "cinematic_beats": ["hero-refuses-call", "mentor-dies-onscreen", "false-victory", "villain-monologue", "lover-betrays", "dawn-arrival", "last-stand", "unexpected-ally-saves"],

    # ─── Level Design / Dungeons / Cities ───
    "dungeon_layouts": ["linear-ascent", "hub-and-spokes", "multi-floor-vertical", "moebius-loop", "time-split-past-present", "nested-rooms", "river-delta-branching"],
    "dungeon_themes": ["flooded-cathedral", "machine-heart-reactor", "forest-that-grew-a-crypt", "library-of-living-books", "inverted-city-underground", "hive-fungal-mind", "frost-mine-crystalline"],
    "city_layouts": ["walled-concentric", "seven-hills", "river-bend", "harbor-crescent", "high-and-low", "bridge-chain", "spiral-tower", "tiered-mountain"],
    "secret_areas": ["behind-waterfall", "under-altar", "loose-brick-library", "fake-painting-door", "tide-timed-cave", "midnight-only-door", "smell-based-trigger"],

    # ─── Puzzles & Mysteries ───
    "mystery_types": ["who-killed-the-priest", "missing-heirloom", "town-wide-amnesia", "serial-ritual-murders", "disappearing-children", "ghost-is-alive", "wrong-body-in-grave"],
    "cipher_types": ["caesar-shift", "pigpen", "musical-notation", "color-sequence", "runic-substitution", "book-page-line-word", "moon-phase-calendar"],
    "clue_types": ["bloodied-glove", "half-burnt-letter", "wrong-clockhand", "duplicate-key", "smell-of-ozone", "missing-portrait", "rewound-gramophone"],

    # ─── Crafting & Systems Mechanics ───
    "crafting_stations": ["forge", "tanner", "alchemist-bench", "clothier-loom", "jewel-setter", "enchanter-circle", "cooking-hearth", "inscription-table"],
    "resource_nodes": ["ironbone vein", "starroot grove", "ashwater spring", "moonglass geode", "phoenix-feather roost", "salt-pillar flat"],
    "farming_crops": ["Ashroot", "Moon-melon", "Glass-wheat", "Voidberry", "Sunleaf tobacco", "Phoenix pepper", "Dream-rice"],
    "recipe_chains": ["ore→bar→weapon", "hide→leather→armor", "herb→tincture→potion", "fiber→thread→cloth", "wood→plank→furniture"],

    # ─── Narrative Tone & Themes ───
    "tones": ["bleak hope", "roaring comedy", "romantic tragedy", "cosmic indifference", "folk-tale warmth", "grim procedural", "whimsical absurd", "meditative elegiac", "pulp adventure", "noir-rain"],
    "themes": ["cost of loyalty", "limits of justice", "memory vs. identity", "duty vs. love", "progress vs. tradition", "sacrifice as corruption", "silence as weapon", "inheritance of violence", "forgiveness as defiance"],
    "moral_dilemmas": ["save one vs. many", "truth that destroys vs. lie that heals", "mercy vs. strategic victory", "follow law vs. obvious right", "betray ally to save kingdom", "break oath to prevent war"],
    "symbolism_library": ["Broken sword = lost inheritance", "Black bird = oath-breaker", "Salt = grief", "Iron = promise", "Mirror = self-deception", "Candle = last witness", "Ring = bond beyond death"],

    # ─── Language & Writing Styles ───
    "languages_conlang": ["Old Tradesmoot", "High Ashspeech", "River Cant", "Sky-script", "Stone-Name", "Deep Hymn", "Silver Court"],
    "naming_conventions": ["three-part clan-craft-virtue", "seasonal birth naming", "place-of-origin + verb", "two-syllable musical", "grandparent reuse", "wyrm-blood honorifics"],
    "writing_styles": ["archaic chronicle", "pulp-breathless", "clinical report", "lyric folk-tale", "diary intimate", "transcribed interview", "newspaper broadsheet", "love letter"],

    # ─── History ───
    "historical_events": ["The Year of Three Winters", "The Treaty of Broken Candles", "Night the Sun Refused", "Siege of Thousand Bells", "Flight of the Prophet-Queens", "Drowning of the Capital", "First Machine War"],
    "wars": ["War of the Salted Road", "Five-Crown War", "Ember Revolt", "Silent Heresy", "Wyrm Purges", "Moon Blockade"],
    "dynasties": ["Ashgrave line", "Orilanth succession", "Twelve Greys", "Emberfall emperors", "Last Starkeepers"],
    "plagues": ["Laughing Plague", "Silver Madness", "Stilling Fever", "Memory Rot", "Gilded Cough"],

    # ─── Cultures / Daily Life ───
    "cultural_customs": ["Seven-salt greeting", "Thumb-pressed oath", "Song-before-sleep", "Bread-and-ash at threshold", "Mother-name carried through daughters", "Silence at dusk", "Bow without eye-contact"],
    "festivals": ["Night of Lanterns", "Harvest of the Sunken", "First Frost Song", "Blessing-of-Debts", "Midnight Bread Feast", "Grief-Market", "Unmaking Day"],
    "cuisines": ["ash-smoked fish", "salt-glazed lamb", "honeyed dates with bone-marrow", "sea-foam soup", "purple-grain flatbread", "river-crab with fermented sun"],
    "daily_life_routines": ["shepherd's dawn-fast", "fisher's tide-schedule", "merchant's counting-stick", "priest's five-chants", "courtier's bowing-order", "child's chalk-riddle"],
    "fashion": ["Mourning white for a year", "Salt-dyed travelling cloaks", "High collars hide hexes", "Braid count = social rank", "Silver thread for unwed", "Scars displayed openly"],

    # ─── Transportation ───
    "vehicles": ["Ash-schooner", "Glass-balloon gondola", "Steam-lorry", "Beast-drawn palanquin", "Canal barge", "Cable-skycar", "Wind-skimmer", "Mechanical strider"],
    "mounts": ["Warhorse", "Dire-wolf", "Sand-drake", "Giant-beetle", "Glider-bat", "Cloudstag", "Swamp-amphibian", "Two-headed lizard"],

    # ─── UI / Menus ───
    "menu_flow_patterns": ["hub-and-spoke pause menu", "wheel selection", "bottom-bar tabs", "nested contextual", "card-based deck", "radial gesture"],
    "save_system_styles": ["bonfire-manual", "auto-checkpoint", "save-anywhere-limited-slots", "iron-man-single-save", "chapter-gated", "cloud-sync-anytime"],

    # ─── Multiplayer / Social ───
    "multiplayer_modes": ["co-op campaign", "competitive 4v4", "1v1 arena", "asynchronous invasion", "raid 20-person", "king-of-hill", "capture-the-relic", "extraction", "arms-race", "horde-together"],
    "social_features": ["mail", "trade-vault", "housing-decoration", "guild-hall", "public-chat", "private-whisper", "emote-system", "photo-mode", "replay-sharing"],

    # ─── Monetization / Live Ops (ethical pattern library) ───
    "monetization_patterns": ["cosmetic-only", "expansion-pass-one-time", "battle-pass-seasonal", "sub-monthly-optional", "free-trial-chapter-1", "pay-what-you-want", "no-ads-no-iap-premium"],

    # ─── Testing / QA ───
    "bug_categories": ["softlock", "clipping", "AI-pathing", "save-corrupt", "UI-overlap", "localization-bleed", "audio-desync", "memory-leak", "exploit-infinite-loop"],
    "qa_scenarios": ["smoke-test-new-build", "stress-test-1000-NPCs", "random-button-monkey", "deathloop-check", "multiplayer-lag-inject", "low-memory-device-sim"],

    # ─── Production Pipeline ───
    "pipeline_stages": ["concept", "greenlight", "pre-prod", "vertical-slice", "alpha", "content-complete", "beta", "gold", "day-one-patch", "post-launch", "expansion"],
    "milestone_reviews": ["concept greenlight", "vertical slice approval", "alpha quality gate", "localization lock", "performance gate", "accessibility review", "cert submission"],

    # ─── Release / Platforms ───
    "platforms": ["PC Steam", "PC Epic", "PS5", "PS4", "Xbox Series", "Xbox One", "Switch", "iOS", "Android", "Mac", "Linux", "Cloud-Streaming"],
    "localization_locales": ["en-US", "fr-FR", "de-DE", "es-ES", "it-IT", "ja-JP", "ko-KR", "zh-CN", "zh-TW", "pt-BR", "ru-RU", "ar-SA", "tr-TR", "nl-NL", "pl-PL"],

    # ─── Era-Specific Flavor (year anchors 1985-2030) ───
    "era_1980s_flavor": ["arcade-cabinet", "chiptune", "coin-op-quarter", "VHS-static-title", "pixel-sprite-sheet", "CRT-scanlines"],
    "era_1990s_flavor": ["floppy-disk", "dial-up modem", "CD-jewel-case-manual", "early-3D-low-poly", "startup-sound", "LAN-party"],
    "era_2000s_flavor": ["broadband-MMO-boom", "achievement-popup", "xbox-live-voice", "early-HD-cinematics", "tutorials-integrated", "DRM-regionals"],
    "era_2010s_flavor": ["open-world-handholding", "battle-pass-dawn", "photo-mode", "streamer-friendly", "live-service-update-cadence", "cross-platform-progress"],
    "era_2020s_flavor": ["haptic-trigger", "ray-tracing", "cloud-save-anywhere", "AI-generated-content", "cross-gen", "accessibility-sliders"],
    "era_2030s_flavor": ["neural-interface", "generative-companion-AI", "hyperreal-animation", "passive-assistive-VR", "modular-live-worlds"],

    # ─── Player Archetypes ───
    "player_psychographics": ["Achiever", "Explorer", "Socializer", "Killer", "Completionist", "Storyteller", "Speedrunner", "Modder", "Lore-hunter", "Economist"],

    # ─── Additional Atmosphere/Tone Generators ───
    "atmosphere_descriptors": ["rain-on-empty-cobbles", "candle-light-in-cold-hall", "sunlit-ruin-in-yellow-grass", "neon-reflected-in-puddles", "humid-jungle-choked", "frozen-lake-under-stars"],
    "weather_events": ["warm-dusk", "electric-storm", "snow-crusted-dawn", "fog-of-mourning", "thrice-rainbow-after-battle", "dust-devil-herald"],
    "time_of_day_beats": ["first-bell", "high-sun", "long-shadow", "dog-watch", "witching-hour", "grey-wolf-dawn"],
}


# ══════════════════════════════════════════════════════════════════════
#  Procedural axes — how each seed is expanded into derivative entries
# ══════════════════════════════════════════════════════════════════════
VARIATION_AXES = [
    "gender-inverted", "tone-flipped", "era-shifted", "scale-amplified",
    "scale-miniature", "moral-greyed", "power-unleashed", "power-restricted",
    "group-plural", "sibling-split", "origin-recontextualized",
    "mirror-self", "foreign-reinterpretation", "cursed-variant",
    "blessed-variant", "mundane-grounded", "mythic-elevated", "cosmic-reframed",
    "modern-retrofit", "ancient-origin", "faction-opposed", "faction-allied",
    "survivor-perspective", "antagonist-perspective", "child-perspective",
]

# ══════════════════════════════════════════════════════════════════════
#  Genre buckets reused from core vault (imported at runtime to avoid cycles)
# ══════════════════════════════════════════════════════════════════════
EXPANSION_GENRES = [
    "rpg", "action_rpg", "jrpg", "crpg", "strategy", "rts",
    "shooter", "fps", "tps", "looter_shooter", "roguelite", "roguelike",
    "platformer", "metroidvania", "action_adventure", "open_world", "sandbox",
    "horror", "survival", "mystery", "visual_novel", "tycoon", "mmo",
    "simulation", "racing", "sports", "fighting", "puzzle", "rhythm",
    "card_game", "stealth_action", "tactics", "moba", "battle_royale",
    "text_adventure", "point_and_click", "cyberpunk_noir", "space_opera",
    "high_fantasy", "low_fantasy", "historical", "mythology", "western",
    "post_apocalyptic", "cosmic_horror", "psychological_horror",
    "heist", "coming_of_age", "tragedy", "comedy", "dystopia",
]


def _specialized_id(genre: str, topic: str, seed: str, axis: str, variation: int) -> str:
    h = hashlib.md5(f"{topic}:{genre}:{seed}:{axis}:{variation}".encode()).hexdigest()[:12]
    return f"spec-{topic[:8]}-{genre[:6]}-{h}"


async def seed_specialized_vault(db, target_entries_per_topic_per_genre: int = 25,
                                 genre_subset: Iterable[str] | None = None) -> dict:
    """Populate `specialized_vault` with 200+ topic collections × 50 genres × N derivatives.

    Default delivers ~200 topics × 50 genres × 25 = ~250,000 rows. Set higher
    multipliers to hyperscale further. Idempotent — skips if collection already
    has ≥ 100k rows.

    Stores all entries in a single MongoDB collection `specialized_vault` with
    fields {topic, genre, seed, axis, variation, text, canonical_id} so the
    swarm can cross-reference any facet instantly.
    """
    report = {"topics": 0, "rows_inserted": 0, "skipped_existing": 0}
    try:
        col = db.specialized_vault
        existing = await col.estimated_document_count()
        if existing >= 100_000:
            report["skipped_existing"] = existing
            return report

        genres = list(genre_subset) if genre_subset else EXPANSION_GENRES
        batch: list = []
        BATCH_FLUSH = 5_000

        for topic, seeds in SPECIALIZED_TOPICS.items():
            report["topics"] += 1
            for genre in genres:
                count = 0
                for seed in seeds:
                    if count >= target_entries_per_topic_per_genre:
                        break
                    for axis in VARIATION_AXES:
                        if count >= target_entries_per_topic_per_genre:
                            break
                        # Deterministic "derivative" text — seed + axis + genre
                        variation = count
                        text = f"{seed} [{axis} · {genre}·v{variation}]"
                        batch.append({
                            "canonical_id": _specialized_id(genre, topic, seed, axis, variation),
                            "topic": topic,
                            "genre": genre,
                            "seed": seed,
                            "axis": axis,
                            "variation": variation,
                            "text": text,
                        })
                        count += 1
                        if len(batch) >= BATCH_FLUSH:
                            try:
                                await col.insert_many(batch, ordered=False)
                                report["rows_inserted"] += len(batch)
                            except Exception as _ie:
                                logger.warning(f"specialized batch insert: {_ie}")
                            batch = []
        if batch:
            try:
                await col.insert_many(batch, ordered=False)
                report["rows_inserted"] += len(batch)
            except Exception as _ie:
                logger.warning(f"specialized final batch: {_ie}")

        # Helpful compound index for fast sampling
        try:
            await col.create_index([("topic", 1), ("genre", 1)], background=True)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"seed_specialized_vault failed: {e}")
    return report


async def sample_specialized_context(db, genre: str, topics: list[str] | None = None,
                                     per_topic: int = 3) -> dict:
    """Pull a random-ish slice of the specialized vault to seed narrative prompts.

    Returns {topic: [text, ...]} for N topics, `per_topic` rows each.
    """
    out: dict[str, list[str]] = {}
    try:
        col = db.specialized_vault
        wanted = topics or [
            "character_archetypes", "villain_archetypes", "kingdoms", "cities",
            "magic_systems", "themes", "tones", "main_quests", "mystery_types",
            "cultural_customs", "dialogue_one_liners", "art_palettes",
        ]
        for t in wanted:
            cursor = col.aggregate([
                {"$match": {"topic": t, "genre": genre}},
                {"$sample": {"size": per_topic}},
                {"$project": {"_id": 0, "text": 1, "seed": 1}},
            ])
            rows = await cursor.to_list(length=per_topic)
            if not rows:
                # Fallback — genre mismatch, sample any
                cursor2 = col.aggregate([
                    {"$match": {"topic": t}},
                    {"$sample": {"size": per_topic}},
                    {"$project": {"_id": 0, "text": 1, "seed": 1}},
                ])
                rows = await cursor2.to_list(length=per_topic)
            out[t] = [r.get("text") or r.get("seed", "") for r in rows]
    except Exception as e:
        logger.warning(f"sample_specialized_context failed: {e}")
    return out


def build_era_year_profile(year: int) -> dict:
    """Given a target year 1985-2030, return a flavor profile the swarm uses
    to pick palette, sound hardware, UX idioms, and story sensibilities."""
    year = max(1985, min(2030, int(year)))
    decade = (year // 10) * 10
    flavor_key = f"era_{decade}s_flavor"
    if decade >= 2030:
        flavor_key = "era_2030s_flavor"
    flavor = SPECIALIZED_TOPICS.get(flavor_key, [])
    # Year-specific seasoning — anchor hardware/cultural context per exact year
    YEAR_ANCHORS = {
        1985: "NES launch US; arcade dominant; chiptune",
        1987: "Metal Gear; 16-color EGA PC; cassette-load",
        1989: "Game Boy launch; monochrome handheld era",
        1991: "SNES vs Genesis peak; 16-bit sprite mastery",
        1993: "DOOM defines FPS; CD-ROM begins replacing floppies",
        1995: "PlayStation launches; 3D polygonal revolution",
        1997: "Final Fantasy VII CD-ROM cinematic RPGs",
        1999: "Dreamcast online modem; pre-broadband",
        2001: "Halo launches with Xbox; LAN and early Live",
        2003: "Xbox Live broadband console gaming mainstream",
        2005: "Xbox 360 HD-era dawn; achievement popups",
        2007: "BioShock narrative maturity; motion controls",
        2009: "Minecraft early; indie golden age begins",
        2011: "Skyrim open-world zenith; F2P mobile explosion",
        2013: "PS4/XB1 launch; streaming era begins",
        2015: "Witcher 3; Twitch dominates; early VR Oculus",
        2017: "Switch launch; BOTW; battle royale emerges",
        2019: "Disco Elysium; subscription services mature",
        2021: "PS5/XSX next-gen; pandemic-indie boom; NFT hype",
        2023: "AI-assisted dev mainstream; Baldur's Gate 3 AAA benchmark",
        2025: "Generative companion AI; cross-play default; fading live-service fatigue",
        2027: "Neural-interface accessibility pilots; hyperreal animation",
        2030: "Modular post-live-service; on-device foundation models; ambient play",
    }
    # Nearest anchor
    anchor = None
    best = None
    for y, txt in YEAR_ANCHORS.items():
        d = abs(y - year)
        if best is None or d < best:
            best = d
            anchor = txt
    return {
        "year": year,
        "decade": decade,
        "flavor_tags": flavor,
        "anchor": anchor or "era defaults",
    }
