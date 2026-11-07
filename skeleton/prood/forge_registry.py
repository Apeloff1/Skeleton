"""
Forge registry — the roadmap of specialized forges.

The Item Foundry / snowball already ships the generic item forge. The list
below is the DEFERRED backlog of specialized forges requested for future
builds. They are tracked (not yet implemented) so the roadmap stays visible.
"""
from __future__ import annotations

import re

# ACTIVE forges already implemented in the platform.
ACTIVE_FORGES: list[str] = [
    "Item Foundry", "Vault GDD", "Asset Forge (10×, era-aware)",
    "Snowball Escalation", "Quality Gates",
]

# DEFERRED specialized forges (verbatim backlog — not yet built).
_DEFERRED_RAW: list[str] = [
    "clothing", "hair and colour", "tattoo", "jewelry", "accessories", "plant",
    "bush", "tree", "water", "stone", "ore", "fire", "wind", "critter",
    "bestiary", "vehicle", "ambiance", "mountain", "insect", "fish", "bird",
    "husbandry", "housing", "road", "settlement", "village", "farm", "city",
    "mega city", "port", "airport", "spaceport", "metalwork", "woodwork",
    "berry", "fruit", "food", "baking", "bank", "hospital", "library",
    "railway", "monorail", "ski elevator", "boat", "airplane", "spaceship",
    "rocketship", "backpack", "campfire", "camping", "fishing", "farming",
    "hunting", "leatherwork", "enchantment", "castle", "temple", "religion",
    "politik", "police", "military", "healthcare", "maintenance",
    "road development", "electricity", "radio", "tv", "satellite", "internet",
    "navigation", "traffic", "non-interactable npcs", "interactable npcs",
    "storyline npc", "environmental npcs", "customization", "skin", "skinning",
    "reskinning", "equipment", "electronic", "mechanical", "tools", "gardening",
    "monuments", "sign", "smoke", "consumables", "snacks", "store", "mall",
    "general store", "village store", "internet shop",
    "electronic equipment store", "sawmill", "concrete", "asphalt", "fence",
    "guardrail", "growth", "artwork", "utensil", "papermill", "coal processing",
    "copper processing", "iron processing", "steel processing",
    "silver processing", "gold processing", "titanium processing",
    "graphite processing", "cobalt processing", "battery processing",
    "lithium processing", "fantasy", "magic", "elemental", "biology", "science",
    "research", "upgrade", "tech", "polish", "makeup", "hairdresser", "drink",
    "sand", "beach", "wave", "fjord", "archipelago", "strait", "swamp",
    "forest", "cave", "tunnel", "hideout", "secrets", "secret items",
    "easter egg", "seasonal", "summer", "fall", "winter", "spring",
    "secret events", "events", "encounter", "random encounter",
    "wanderer encounter", "wandering vendor", "location", "location event",
    "interactable", "vice", "character", "player", "placement randomizer",
    "placement storyline", "specific placement location", "normal item",
    "rare item", "epic item", "legendary item", "uncommon item", "common item",
    "crowd npc", "nurturing", "meat processing plant", "interaction", "speech",
    "weapons", "gun", "archery", "poison", "potion", "clock", "calendar",
    "event by date", "randomizer",
    # ── batch 2 ──
    "galaxy", "country", "globus", "map", "sea", "sky", "planet", "moon",
    "sun", "cloud", "storm", "rain", "thunder and lightning", "sound",
    "ambiance", "nature sound", "tool sound", "equipment sound", "window",
    "glass", "rubber", "mechanical sound", "water sound", "wind sound",
    "voice sound", "engine sound", "plastic sound", "plastic", "ball",
    "ball sound", "dirty look", "clean look", "worn out look", "new look",
    # ── batch 3 — +110 categories activating new archetype families ──
    # furniture
    "chair", "table", "bed", "sofa", "desk", "shelf", "wardrobe", "dresser",
    "stool", "bench", "cabinet", "throne", "bookcase", "counter", "crib",
    # weapon
    "sword", "axe", "mace", "spear", "dagger", "bow", "crossbow", "halberd",
    "warhammer", "katana", "rapier", "flail", "scythe", "glaive", "rifle",
    "pistol", "shotgun", "cannon", "blaster", "laser weapon",
    # container
    "chest", "barrel", "crate", "sack", "basket", "pot", "vase", "urn", "jar",
    "bucket", "cauldron", "crucible", "coffer", "strongbox",
    # machine
    "robot", "mech", "turret", "generator", "reactor", "drone", "android",
    "conveyor", "crane", "pump", "engine block", "gear assembly", "antenna array",
    # instrument
    "drum", "guitar", "lute", "harp", "flute", "horn instrument", "piano",
    "violin", "bell instrument", "gong", "lyre",
    # food dish
    "bread", "cake", "pie", "apple", "cheese", "meat cut", "soup bowl",
    "fish dish", "stew", "roast", "pizza", "sandwich",
    # ui / interface
    "icon", "badge", "banner ui", "emblem", "crest", "button ui", "cursor",
    "healthbar", "minimap", "waypoint marker",
    # avatar / effigy
    "bust", "portrait", "mannequin", "statue figure", "idol", "totem",
    # terrain feature
    "boulder", "cliff", "crater", "geyser", "hot spring", "stalagmite",
    "dune crest", "ravine", "plateau", "ridge",
]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def catalog() -> dict:
    # de-dupe while preserving order
    seen: set[str] = set()
    deferred = []
    for name in _DEFERRED_RAW:
        key = _slug(name)
        if key in seen:
            continue
        seen.add(key)
        deferred.append({"key": key, "label": name.title() + " Forge",
                         "status": "deferred"})
    return {
        "active": [{"key": _slug(n), "label": n, "status": "active"} for n in ACTIVE_FORGES],
        "deferred": deferred,
        "active_count": len(ACTIVE_FORGES),
        "deferred_count": len(deferred),
        "total": len(ACTIVE_FORGES) + len(deferred),
    }
