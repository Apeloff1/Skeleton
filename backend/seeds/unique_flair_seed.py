"""
Galaxy Studio — Unique Flair Database
A database of 50,000 distinctive, memorable, creative elements that make
games unforgettable. Each flair entry is a "signature moment" concept that
agents can pull when generating a game to give it a unique identity.

Categories:
  - signature_mechanics     (a mechanic no one's seen before)
  - iconic_moments          (set-piece moments worth remembering)
  - memorable_villains      (antagonist archetypes with twist)
  - unique_weapons          (weird, creative weapon concepts)
  - quirky_npc_personalities (offbeat NPC character traits)
  - hidden_easter_eggs      (secret discoveries)
  - environmental_storytelling (lore through level design)
  - musical_leitmotifs      (sound signatures)
  - visual_trademarks       (signature art touches)
  - subverted_tropes        (genre tropes flipped on their head)
"""
from __future__ import annotations
import asyncio
import hashlib
import uuid
from datetime import datetime
import logging

log = logging.getLogger("GalaxyStudio.FlairSeeder")

FLAIR_CATEGORIES = [
    "signature_mechanics", "iconic_moments", "memorable_villains",
    "unique_weapons", "quirky_npc_personalities", "hidden_easter_eggs",
    "environmental_storytelling", "musical_leitmotifs",
    "visual_trademarks", "subverted_tropes",
]

TOTAL_FLAIR = 50000
COLLECTION_NAME = "unique_flair"

ADJECTIVES = [
    "Ethereal", "Shattered", "Whispering", "Crimson", "Frozen", "Burning",
    "Ancient", "Glitched", "Haunted", "Radiant", "Rusted", "Verdant",
    "Crystalline", "Shadowed", "Luminous", "Dissonant", "Echoing", "Fractured",
    "Gilded", "Obsidian", "Quantum", "Neon", "Hollow", "Sacred", "Cursed",
    "Paradoxical", "Inverted", "Recursive", "Spectral", "Bioluminescent",
]

NOUNS = {
    "signature_mechanics": ["echo-rewind", "gravity-swap", "time-stitch", "memory-weave", "shadow-meld", "pulse-harvest", "dream-fracture", "soul-anchor", "tide-shift", "chord-bind"],
    "iconic_moments": ["first-sight", "betrayal", "sacrifice", "ascension", "reunion", "fall", "awakening", "choice", "revelation", "echo"],
    "memorable_villains": ["Warden", "Architect", "Mirror", "Curator", "Sovereign", "Whisperer", "Puppeteer", "Herald", "Shepherd", "Cartographer"],
    "unique_weapons": ["soundstaff", "gravity-chain", "memory-blade", "shadow-bow", "pulse-gauntlet", "prism-spear", "rift-pistol", "chord-hammer", "mirror-dagger", "echo-bow"],
    "quirky_npc_personalities": ["the-philosopher-merchant", "the-paranoid-farmer", "the-cheerful-gravedigger", "the-singing-guard", "the-dancing-monk", "the-stoic-jester", "the-reluctant-hero", "the-retired-villain", "the-amnesiac-sage", "the-polite-bandit"],
    "hidden_easter_eggs": ["dev-room", "secret-ending", "cameo-character", "meta-reference", "fourth-wall-break", "lore-deep-cut", "speedrun-reward", "100-percent-bonus", "hidden-boss", "time-traveler"],
    "environmental_storytelling": ["abandoned-camp", "frozen-battlefield", "childs-toy", "graffiti-message", "scorched-tree", "bloodstain-trail", "empty-throne", "broken-statue", "unsent-letter", "scratched-wall"],
    "musical_leitmotifs": ["heros-theme", "villains-march", "lovers-refrain", "city-pulse", "forest-chant", "storm-rhythm", "silence-motif", "victory-cascade", "loss-coda", "dream-sequence"],
    "visual_trademarks": ["neon-rain", "bloom-over-everything", "chromatic-edges", "pixel-perfect-shadows", "cel-shaded-highlights", "volumetric-dust", "impact-freezeframe", "color-grade-teal-orange", "film-grain-heavy", "sun-lens-flare"],
    "subverted_tropes": ["princess-rescues-you", "villain-was-right", "dungeon-is-home", "final-boss-is-tutorial", "chosen-one-chose-wrong", "peace-was-a-lie", "happy-ending-is-sad", "tutorial-is-the-twist", "weakest-link-is-strongest", "dead-characters-remember"],
}

MOODS = ["triumphant", "bittersweet", "eerie", "playful", "solemn", "frantic", "serene", "dread", "hopeful", "melancholic"]

ERAS = ["pong_1972", "atari_1977", "nes_1985", "snes_1990", "ps1_1995",
        "ps2_2000", "xbox360_2005", "ps4_2013", "ps5_2020", "singularity"]

GENRES = ["rpg", "shooter", "platformer", "horror", "simulation",
          "action", "puzzle", "sports", "strategy", "moba"]

AGENT_SWARMS = ["galaxy", "jeeves", "vee", "outcall", "vault", "compiler"]


def _h(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest()[:8], 16)


def _build_flair(i: int) -> dict:
    seed = _h(f"flair-{i}")
    category = FLAIR_CATEGORIES[seed % len(FLAIR_CATEGORIES)]
    noun = NOUNS[category][(seed >> 3) % len(NOUNS[category])]
    adj = ADJECTIVES[(seed >> 5) % len(ADJECTIVES)]
    mood = MOODS[(seed >> 7) % len(MOODS)]
    era = ERAS[(seed >> 9) % len(ERAS)]
    genre = GENRES[(seed >> 11) % len(GENRES)]
    rarity = ["common", "uncommon", "rare", "epic", "legendary", "mythic", "unique"][(seed >> 13) % 7]
    agents = [f"{AGENT_SWARMS[(seed + k) % len(AGENT_SWARMS)]}-agent-{(seed + k * 37) % 100000}" for k in range(3 + (seed % 5))]
    title = f"{adj} {noun.replace('-', ' ').title()}"
    signature_phrase = f"'{adj} {noun}' — a {mood} {category.replace('_', ' ')} moment"
    description = (
        f"A {mood}, {rarity} flair for {genre} ({era}): "
        f"the '{title}' concept drops into the scene when context matches. "
        f"Signature: {signature_phrase}."
    )
    tags = [category, mood, era, genre, rarity, noun, adj.lower()]
    return {
        "id": f"flair-{uuid.uuid5(uuid.NAMESPACE_OID, f'flair:{i}').hex[:14]}",
        "flair_index": i,
        "title": title,
        "category": category,
        "rarity": rarity,
        "mood": mood,
        "era": era,
        "genre": genre,
        "signature_phrase": signature_phrase,
        "description": description,
        "tags": tags,
        "keywords": [noun, adj.lower(), category, mood, genre],
        "agent_ids": agents,
        "popularity_score": (seed % 1000),
        "memorability_index": 50 + (seed % 50),  # 50-99
        "created_at": datetime.utcnow().isoformat(),
    }


async def seed_unique_flair(db, force: bool = False) -> dict:
    """Seed the `unique_flair` collection with 50,000 distinctive game elements."""
    try:
        existing = await db[COLLECTION_NAME].count_documents({})
    except Exception as e:
        log.warning(f"count failed: {e}")
        existing = 0

    if existing >= TOTAL_FLAIR and not force:
        return {"status": "already_full", "docs": existing}

    # Indexes
    try:
        await db[COLLECTION_NAME].create_index("id", unique=True)
        await db[COLLECTION_NAME].create_index("category")
        await db[COLLECTION_NAME].create_index("rarity")
        await db[COLLECTION_NAME].create_index("era")
        await db[COLLECTION_NAME].create_index("genre")
        await db[COLLECTION_NAME].create_index([("tags", 1)])
        await db[COLLECTION_NAME].create_index([("keywords", 1)])
        await db[COLLECTION_NAME].create_index([("agent_ids", 1)])
    except Exception:
        pass

    BATCH = 1000
    buffer = []
    inserted = 0
    for i in range(existing, TOTAL_FLAIR):
        buffer.append(_build_flair(i))
        if len(buffer) >= BATCH:
            try:
                await db[COLLECTION_NAME].insert_many(buffer, ordered=False)
                inserted += len(buffer)
            except Exception:
                inserted += len(buffer)
            buffer = []
    if buffer:
        try:
            await db[COLLECTION_NAME].insert_many(buffer, ordered=False)
            inserted += len(buffer)
        except Exception:
            pass

    log.info(f"unique_flair seeded/topped-up: {inserted} added, total now ~{existing + inserted}")
    return {"status": "seeded", "docs_added": inserted, "total": existing + inserted}
