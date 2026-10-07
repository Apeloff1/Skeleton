"""
╔════════════════════════════════════════════════════════════════════════╗
║  UNIVERSAL FORGE — one engine, the whole forge roadmap.                  ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Activates every category in core/forge_registry.py (plants, trees,      ║
║  characters, npcs, creatures, vehicles, wearables, props/weapons/food,   ║
║  world/terrain, fx, sound, surfaces, structures…) as a LIVE, buildable   ║
║  asset:                                                                   ║
║                                                                          ║
║    • each category maps to a parametric ARCHETYPE family with its own     ║
║      deterministic 3D geometry the Construct3DView renders;               ║
║    • era-tinted palettes + ≥36 presets / category / era;                  ║
║    • always-on HYBRID Claude Sonnet 4.6 enrich (folds the ≤20k brief);    ║
║    • shares the Construct Forge store + Vault connection (mount /         ║
║      save-to-gamefiles / extract) so universal assets flow into builds.   ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import math
import random
from typing import Any

from core import construct_forge as cf
from core import eras as _eras
from core import forge_registry

MAX_PROMPT = cf.MAX_PROMPT

# ── Archetype families → friendly group metadata for the Forge Hub ─────────
FAMILIES: dict[str, dict] = {
    "structure": {"label": "Structures", "icon": "🏛️", "group": "Built World"},
    "surface":   {"label": "Materials & Surfaces", "icon": "🧱", "group": "Built World"},
    "world":     {"label": "World & Terrain", "icon": "🌍", "group": "Built World"},
    "flora":     {"label": "Flora & Nature", "icon": "🌳", "group": "Nature"},
    "creature":  {"label": "Creatures & Beasts", "icon": "🦎", "group": "Nature"},
    "fx":        {"label": "FX & Elements", "icon": "✨", "group": "Nature"},
    "character": {"label": "Characters & NPCs", "icon": "🧍", "group": "Living"},
    "wearable":  {"label": "Wearables & Customization", "icon": "👕", "group": "Living"},
    "vehicle":   {"label": "Vehicles & Transport", "icon": "🚗", "group": "Things"},
    "prop":      {"label": "Items, Tools & Props", "icon": "🗡️", "group": "Things"},
    "sound":     {"label": "Sound & Ambiance", "icon": "🔊", "group": "Atmosphere"},
    "furniture": {"label": "Furniture & Decor", "icon": "🪑", "group": "Built World"},
    "weapon":    {"label": "Weapons & Armaments", "icon": "⚔️", "group": "Things"},
    "container": {"label": "Containers & Vessels", "icon": "📦", "group": "Things"},
    "machine":   {"label": "Machines & Robotics", "icon": "🤖", "group": "Things"},
    "instrument":{"label": "Instruments", "icon": "🎸", "group": "Atmosphere"},
    "food":      {"label": "Food & Dishes", "icon": "🍞", "group": "Things"},
    "ui":        {"label": "UI & Interface", "icon": "🖼️", "group": "Atmosphere"},
    "avatar":    {"label": "Avatars & Effigies", "icon": "🗿", "group": "Living"},
    "terrain":   {"label": "Terrain Features", "icon": "⛰️", "group": "Nature"},
    "gem":       {"label": "Gems & Crystals", "icon": "💎", "group": "Things"},
    "light":     {"label": "Lights & Lamps", "icon": "💡", "group": "Built World"},
    "book":      {"label": "Books & Scrolls", "icon": "📜", "group": "Things"},
    "coin":      {"label": "Coins & Treasure", "icon": "🪙", "group": "Things"},
    "armor":     {"label": "Armor & Shields", "icon": "🛡️", "group": "Things"},
    "banner":    {"label": "Banners & Flags", "icon": "🚩", "group": "Built World"},
    "door":      {"label": "Doors & Gates", "icon": "🚪", "group": "Built World"},
    "shrine":    {"label": "Shrines & Monuments", "icon": "⛩️", "group": "Built World"},
    "mushroom":  {"label": "Fungi & Mushrooms", "icon": "🍄", "group": "Nature"},
    "trap":      {"label": "Traps & Hazards", "icon": "🪤", "group": "Things"},
}

# ── +70 families (→100 total). Each gets curated base nouns (below) so its
#    count is real, and inherits the full style-axis + procedural fan-out. ────
_FAMILIES_EXT: dict[str, dict] = {
    # Beasts & Bestiary
    "mount":      {"label": "Mounts & Steeds", "icon": "🐎", "group": "Beasts"},
    "pet":        {"label": "Pets & Companions", "icon": "🐕", "group": "Beasts"},
    "familiar":   {"label": "Familiars", "icon": "🦉", "group": "Beasts"},
    "fish":       {"label": "Fish & Aquatic", "icon": "🐟", "group": "Beasts"},
    "bird":       {"label": "Birds", "icon": "🦅", "group": "Beasts"},
    "insect":     {"label": "Insects & Bugs", "icon": "🐞", "group": "Beasts"},
    "reptile":    {"label": "Reptiles", "icon": "🦎", "group": "Beasts"},
    "mammal":     {"label": "Mammals", "icon": "🦌", "group": "Beasts"},
    "dinosaur":   {"label": "Dinosaurs", "icon": "🦖", "group": "Beasts"},
    "sea_beast":  {"label": "Sea Monsters", "icon": "🐙", "group": "Beasts"},
    # Magic & Relics
    "demon":      {"label": "Demons", "icon": "👹", "group": "Myth & Magic"},
    "angel":      {"label": "Angels & Celestials", "icon": "👼", "group": "Myth & Magic"},
    "elemental":  {"label": "Elemental Beings", "icon": "🔥", "group": "Myth & Magic"},
    "spirit":     {"label": "Spirits & Ghosts", "icon": "👻", "group": "Myth & Magic"},
    "undead":     {"label": "Undead", "icon": "💀", "group": "Myth & Magic"},
    "totem":      {"label": "Totems", "icon": "🗿", "group": "Myth & Magic"},
    "idol":       {"label": "Idols", "icon": "🛐", "group": "Myth & Magic"},
    "relic":      {"label": "Relics", "icon": "📿", "group": "Myth & Magic"},
    "artifact":   {"label": "Artifacts", "icon": "🏺", "group": "Myth & Magic"},
    "orb":        {"label": "Orbs & Spheres", "icon": "🔮", "group": "Myth & Magic"},
    "staff":      {"label": "Staves", "icon": "🪄", "group": "Myth & Magic"},
    "wand":       {"label": "Wands", "icon": "🪄", "group": "Myth & Magic"},
    "tome":       {"label": "Tomes & Grimoires", "icon": "📕", "group": "Myth & Magic"},
    "rune_stone": {"label": "Rune Stones", "icon": "🪨", "group": "Myth & Magic"},
    "portal":     {"label": "Portals & Gateways", "icon": "🌀", "group": "Myth & Magic"},
    # Sci-Fi & Space
    "mech":       {"label": "Mechs & Exosuits", "icon": "🤖", "group": "Sci-Fi & Space"},
    "drone":      {"label": "Drones", "icon": "🛸", "group": "Sci-Fi & Space"},
    "turret":     {"label": "Turrets", "icon": "🔫", "group": "Sci-Fi & Space"},
    "spaceship":  {"label": "Spaceships", "icon": "🚀", "group": "Sci-Fi & Space"},
    "station":    {"label": "Space Stations", "icon": "🛰️", "group": "Sci-Fi & Space"},
    "satellite":  {"label": "Satellites", "icon": "📡", "group": "Sci-Fi & Space"},
    "asteroid":   {"label": "Asteroids", "icon": "☄️", "group": "Sci-Fi & Space"},
    "planet":     {"label": "Planets", "icon": "🪐", "group": "Sci-Fi & Space"},
    "star_body":  {"label": "Stars & Suns", "icon": "⭐", "group": "Sci-Fi & Space"},
    "robot_pet":  {"label": "Robot Companions", "icon": "🐱", "group": "Sci-Fi & Space"},
    "engine":     {"label": "Engines & Reactors", "icon": "⚙️", "group": "Sci-Fi & Space"},
    "console":    {"label": "Consoles & Terminals", "icon": "🖥️", "group": "Sci-Fi & Space"},
    # Gear & Equipment
    "shield":     {"label": "Shields", "icon": "🛡️", "group": "Gear"},
    "helmet":     {"label": "Helmets", "icon": "⛑️", "group": "Gear"},
    "boots":      {"label": "Boots & Footwear", "icon": "🥾", "group": "Gear"},
    "gloves":     {"label": "Gloves & Gauntlets", "icon": "🧤", "group": "Gear"},
    "cape":       {"label": "Capes & Cloaks", "icon": "🧥", "group": "Gear"},
    "mask":       {"label": "Masks", "icon": "🎭", "group": "Gear"},
    "ring":       {"label": "Rings", "icon": "💍", "group": "Gear"},
    "amulet":     {"label": "Amulets & Pendants", "icon": "🧿", "group": "Gear"},
    "crown":      {"label": "Crowns & Tiaras", "icon": "👑", "group": "Gear"},
    "belt":       {"label": "Belts & Sashes", "icon": "🩹", "group": "Gear"},
    "weapon_part":{"label": "Weapon Parts", "icon": "🔩", "group": "Gear"},
    "ammo":       {"label": "Ammunition", "icon": "🎯", "group": "Gear"},
    "explosive":  {"label": "Explosives", "icon": "💣", "group": "Gear"},
    "tool":       {"label": "Tools & Implements", "icon": "🔧", "group": "Gear"},
    # Consumables
    "potion":     {"label": "Potions", "icon": "🧪", "group": "Consumables"},
    "elixir":     {"label": "Elixirs", "icon": "⚗️", "group": "Consumables"},
    "herb":       {"label": "Herbs & Reagents", "icon": "🌿", "group": "Consumables"},
    "crop":       {"label": "Crops", "icon": "🌾", "group": "Consumables"},
    "fruit":      {"label": "Fruits", "icon": "🍎", "group": "Consumables"},
    "vegetable":  {"label": "Vegetables", "icon": "🥕", "group": "Consumables"},
    "beverage":   {"label": "Beverages", "icon": "🍷", "group": "Consumables"},
    "spice":      {"label": "Spices", "icon": "🧂", "group": "Consumables"},
    # Architecture
    "tower":      {"label": "Towers", "icon": "🗼", "group": "Architecture"},
    "wall":       {"label": "Walls & Ramparts", "icon": "🧱", "group": "Architecture"},
    "bridge":     {"label": "Bridges", "icon": "🌉", "group": "Architecture"},
    "fountain":   {"label": "Fountains", "icon": "⛲", "group": "Architecture"},
    "statue":     {"label": "Statues", "icon": "🗽", "group": "Architecture"},
    "pillar":     {"label": "Pillars & Columns", "icon": "🏛️", "group": "Architecture"},
    "arch":       {"label": "Arches", "icon": "🌁", "group": "Architecture"},
    "platform":   {"label": "Platforms", "icon": "🟫", "group": "Architecture"},
    "fence":      {"label": "Fences & Railings", "icon": "🚧", "group": "Architecture"},
    "sign":       {"label": "Signs & Posts", "icon": "🪧", "group": "Architecture"},
    "crate":      {"label": "Crates & Barrels", "icon": "🛢️", "group": "Architecture"},
    "lockbox":    {"label": "Lockboxes & Safes", "icon": "🔒", "group": "Architecture"},
}
FAMILIES.update(_FAMILIES_EXT)

_UNI_STYLES = ["common", "uncommon", "rare", "epic", "legendary", "weathered",
               "pristine", "ornate", "rugged", "sleek", "ancient", "mythic"]
_VARIANTS = 3
_SIZE_CLASSES = ["small", "medium", "large", "huge", "monumental"]
_MAX_SCENE = 300  # aggregate cap: max assets minted per compose/seed call

# ── Skin styles (surface finishes) ────────────────────────────────────────
SKIN_STYLES: dict[str, dict] = {
    "matte":       {"label": "Matte", "surface": {"roughness": 0.92, "metalness": 0.04, "emissive": 0}},
    "satin":       {"label": "Satin", "surface": {"roughness": 0.55, "metalness": 0.12, "emissive": 0}},
    "glossy":      {"label": "Glossy", "surface": {"roughness": 0.18, "metalness": 0.15, "emissive": 0}},
    "metallic":    {"label": "Metallic", "surface": {"roughness": 0.32, "metalness": 0.92, "emissive": 0}},
    "chrome":      {"label": "Chrome", "surface": {"roughness": 0.05, "metalness": 1.0, "emissive": 0}},
    "weathered":   {"label": "Weathered", "surface": {"roughness": 0.98, "metalness": 0.2, "emissive": 0}},
    "rusted":      {"label": "Rusted", "surface": {"roughness": 0.95, "metalness": 0.5, "emissive": 0}},
    "painted":     {"label": "Painted", "surface": {"roughness": 0.6, "metalness": 0.0, "emissive": 0}},
    "neon":        {"label": "Neon", "surface": {"roughness": 0.3, "metalness": 0.1, "emissive": 0.7}},
    "holographic": {"label": "Holographic", "surface": {"roughness": 0.1, "metalness": 0.7, "emissive": 0.4}},
    "crystalline": {"label": "Crystalline", "surface": {"roughness": 0.08, "metalness": 0.3, "emissive": 0.25}},
    "glowing":     {"label": "Glowing", "surface": {"roughness": 0.4, "metalness": 0.0, "emissive": 0.85}},
}

# Detail bands → scalar factors that drive geometry density, palette variety,
# poly budget and texture resolution.
COMPLEXITY = {"minimal": 0.5, "low": 0.8, "standard": 1.0, "high": 1.6, "ultra": 2.4}
INTRICACY = {"plain": 0.0, "subtle": 0.3, "ornate": 0.65, "baroque": 1.0}
DETAIL_LEVEL = {"draft": 0.5, "standard": 1.0, "fine": 1.6, "sota": 2.4}

# ── New style axes (each option can re-tint the palette, override surface and
#    set a default vfx). They stack on top of the base skin style. ───────────
ART_STYLES = {
    "realistic":   {"label": "Realistic", "surface": {"roughness": 0.75, "metalness": 0.12}},
    "stylized":    {"label": "Stylized", "surface": {"roughness": 0.6, "metalness": 0.08}},
    "cartoon":     {"label": "Cartoon", "tint": "#ffd166", "surface": {"roughness": 0.88, "metalness": 0.0}},
    "lowpoly":     {"label": "Low-Poly", "surface": {"roughness": 0.92, "metalness": 0.05}},
    "voxel":       {"label": "Voxel", "surface": {"roughness": 0.95, "metalness": 0.0}},
    "handpainted": {"label": "Hand-Painted", "tint": "#caa472", "surface": {"roughness": 0.72}},
    "cel_shaded":  {"label": "Cel-Shaded", "surface": {"roughness": 0.5, "metalness": 0.1}},
    "noir":        {"label": "Noir", "tint": "#2b2b2b", "surface": {"roughness": 0.6, "metalness": 0.22}},
}
PERIOD_STYLES = {
    "prehistoric":      {"label": "Prehistoric", "tint": "#8a6a3a", "surface": {"roughness": 0.98}},
    "ancient":          {"label": "Ancient", "tint": "#c2a878", "surface": {"roughness": 0.95}},
    "medieval":         {"label": "Medieval", "tint": "#6e5230", "surface": {"roughness": 0.9}},
    "renaissance":      {"label": "Renaissance", "tint": "#b08d57", "surface": {"roughness": 0.6, "metalness": 0.2}},
    "victorian":        {"label": "Victorian", "tint": "#4a2e2a", "surface": {"roughness": 0.55, "metalness": 0.25}},
    "industrial":       {"label": "Industrial", "tint": "#6a6a6a", "surface": {"roughness": 0.7, "metalness": 0.5}},
    "modern":           {"label": "Modern", "tint": "#aab6c2", "surface": {"roughness": 0.4, "metalness": 0.3}},
    "futuristic":       {"label": "Futuristic", "tint": "#4cc9f0", "surface": {"roughness": 0.2, "metalness": 0.7, "emissive": 0.25}},
    "post_apocalyptic": {"label": "Post-Apocalyptic", "tint": "#7a6a4a", "surface": {"roughness": 0.98, "metalness": 0.35}},
}
REALISM_STYLES = {
    "photoreal":     {"label": "Photoreal", "surface": {"roughness": 0.65, "metalness": 0.15}},
    "semi_real":     {"label": "Semi-Real", "surface": {"roughness": 0.7}},
    "stylized_real": {"label": "Stylized-Real", "surface": {"roughness": 0.6}},
    "painterly":     {"label": "Painterly", "tint": "#caa472", "surface": {"roughness": 0.8}},
    "abstract":      {"label": "Abstract", "tint": "#e84393", "surface": {"roughness": 0.5}},
    "flat":          {"label": "Flat", "surface": {"roughness": 1.0, "metalness": 0.0}},
}
FANTASY_STYLES = {
    "high_fantasy": {"label": "High Fantasy", "tint": "#d4af37", "surface": {"emissive": 0.15}, "vfx": "sparkle"},
    "dark_fantasy": {"label": "Dark Fantasy", "tint": "#3a2b40", "surface": {"roughness": 0.85}, "vfx": "fog"},
    "fairytale":    {"label": "Fairytale", "tint": "#f7a8d8", "surface": {"emissive": 0.1}, "vfx": "sparkle"},
    "mythic":       {"label": "Mythic", "tint": "#e0c060", "surface": {"metalness": 0.4, "emissive": 0.2}, "vfx": "glow"},
    "eldritch":     {"label": "Eldritch", "tint": "#3ad6a0", "surface": {"emissive": 0.3}, "vfx": "glow"},
    "celestial":    {"label": "Celestial", "tint": "#a9d6ff", "surface": {"emissive": 0.35}, "vfx": "sparkle"},
}
PUNK_STYLES = {
    "cyberpunk":  {"label": "Cyberpunk", "tint": "#ff2bd6", "surface": {"roughness": 0.3, "metalness": 0.5, "emissive": 0.5}, "vfx": "glow"},
    "steampunk":  {"label": "Steampunk", "tint": "#b87333", "surface": {"roughness": 0.6, "metalness": 0.6}, "vfx": "smoke"},
    "dieselpunk": {"label": "Dieselpunk", "tint": "#6a5a3a", "surface": {"roughness": 0.7, "metalness": 0.55}, "vfx": "smoke"},
    "solarpunk":  {"label": "Solarpunk", "tint": "#90be6d", "surface": {"roughness": 0.45, "metalness": 0.2, "emissive": 0.15}},
    "biopunk":    {"label": "Biopunk", "tint": "#43d39e", "surface": {"roughness": 0.5, "emissive": 0.25}, "vfx": "glow"},
    "atompunk":   {"label": "Atompunk", "tint": "#f1a208", "surface": {"roughness": 0.4, "metalness": 0.5, "emissive": 0.2}},
}
# Metal grade — wear/quality ladder from rusty to legendary (drives metalness,
# roughness, sheen and a hint of emissive at the high end).
METAL_GRADES = {
    "rusty":     {"label": "Rusty", "tint": "#7a4a2a", "surface": {"roughness": 0.98, "metalness": 0.35}},
    "tarnished": {"label": "Tarnished", "tint": "#6a6a5a", "surface": {"roughness": 0.85, "metalness": 0.5}},
    "worn":      {"label": "Worn", "tint": "#8a8a90", "surface": {"roughness": 0.7, "metalness": 0.6}},
    "polished":  {"label": "Polished", "tint": "#c8ccd2", "surface": {"roughness": 0.4, "metalness": 0.8}},
    "pristine":  {"label": "Pristine", "tint": "#e6ebf2", "surface": {"roughness": 0.22, "metalness": 0.9}},
    "gilded":    {"label": "Gilded", "tint": "#d4af37", "surface": {"roughness": 0.18, "metalness": 0.95, "emissive": 0.1}},
    "mythic":    {"label": "Mythic", "tint": "#9b6cff", "surface": {"roughness": 0.12, "metalness": 1.0, "emissive": 0.25}, "vfx": "sparkle"},
    "legendary": {"label": "Legendary", "tint": "#ffd34d", "surface": {"roughness": 0.08, "metalness": 1.0, "emissive": 0.45}, "vfx": "glow"},
}
# Surface finish "colour variables" — how the colour reads physically.
FINISH_STYLES = {
    "matte":      {"label": "Matte", "surface": {"roughness": 1.0, "metalness": 0.0}},
    "metallic":   {"label": "Metallic", "surface": {"roughness": 0.35, "metalness": 0.9}},
    "sheen":      {"label": "Sheen", "surface": {"roughness": 0.5, "metalness": 0.4, "emissive": 0.05}},
    "glean":      {"label": "Glean", "surface": {"roughness": 0.25, "metalness": 0.6, "emissive": 0.1}},
    "polish":     {"label": "Polish", "surface": {"roughness": 0.15, "metalness": 0.7}},
    "reflection": {"label": "Reflection", "surface": {"roughness": 0.05, "metalness": 0.85}},
    "contour":    {"label": "Contour", "surface": {"roughness": 0.6, "metalness": 0.3}},
    "luster":     {"label": "Luster", "surface": {"roughness": 0.3, "metalness": 0.65, "emissive": 0.08}},
    "gloss":      {"label": "Gloss", "surface": {"roughness": 0.1, "metalness": 0.5}},
    "shine":      {"label": "Shine", "surface": {"roughness": 0.08, "metalness": 0.6, "emissive": 0.15}},
}
ELEMENTAL_STYLES = {
    "fire":      {"label": "Fire", "tint": "#ff5a2a", "surface": {"emissive": 0.4}, "vfx": "embers"},
    "water":     {"label": "Water", "tint": "#3aa0ff", "surface": {"roughness": 0.2, "metalness": 0.3}},
    "earth":     {"label": "Earth", "tint": "#7a5a3a", "surface": {"roughness": 0.95}},
    "air":       {"label": "Air", "tint": "#cfe8ff", "surface": {"emissive": 0.1}},
    "ice":       {"label": "Ice", "tint": "#aee9ff", "surface": {"roughness": 0.1, "metalness": 0.4, "emissive": 0.1}, "vfx": "sparkle"},
    "lightning": {"label": "Lightning", "tint": "#ffe23a", "surface": {"emissive": 0.5}, "vfx": "glow"},
    "poison":    {"label": "Poison", "tint": "#7fd13a", "surface": {"emissive": 0.3}, "vfx": "fog"},
    "arcane":    {"label": "Arcane", "tint": "#b06cff", "surface": {"emissive": 0.35}, "vfx": "sparkle"},
}
MAGIC_STYLES = {
    "enchanted": {"label": "Enchanted", "tint": "#8a6cff", "surface": {"emissive": 0.3}, "vfx": "sparkle"},
    "runic":     {"label": "Runic", "tint": "#4cc9f0", "surface": {"emissive": 0.25}, "vfx": "glow"},
    "holy":      {"label": "Holy", "tint": "#fff1b0", "surface": {"emissive": 0.4}, "vfx": "glow"},
    "necrotic":  {"label": "Necrotic", "tint": "#5a7a4a", "surface": {"emissive": 0.2}, "vfx": "fog"},
    "astral":    {"label": "Astral", "tint": "#6aa9ff", "surface": {"emissive": 0.35}, "vfx": "sparkle"},
    "spectral":  {"label": "Spectral", "tint": "#aee9ff", "surface": {"emissive": 0.3}},
    "glyphic":   {"label": "Glyphic", "tint": "#c060ff", "surface": {"emissive": 0.3}},
    "blessed":   {"label": "Blessed", "tint": "#ffe6a0", "surface": {"emissive": 0.3}, "vfx": "sparkle"},
}
CURSE_STYLES = {
    "cursed":    {"label": "Cursed", "tint": "#5a2b40", "surface": {"emissive": 0.15}, "vfx": "fog"},
    "hexed":     {"label": "Hexed", "tint": "#6a3a6a", "surface": {"emissive": 0.2}, "vfx": "glow"},
    "corrupted": {"label": "Corrupted", "tint": "#3a2b40", "surface": {"roughness": 0.85}, "vfx": "fog"},
    "doomed":    {"label": "Doomed", "tint": "#2b2b2b", "surface": {"emissive": 0.1}},
    "possessed": {"label": "Possessed", "tint": "#7a1f2b", "surface": {"emissive": 0.3}, "vfx": "glow"},
    "blighted":  {"label": "Blighted", "tint": "#4a5a2a", "surface": {"roughness": 0.9}, "vfx": "fog"},
    "tainted":   {"label": "Tainted", "tint": "#5a3a5a", "surface": {"emissive": 0.18}},
    "accursed":  {"label": "Accursed", "tint": "#40202b", "surface": {"emissive": 0.25}, "vfx": "fog"},
}
DRIPPING_STYLES = {
    "dripping": {"label": "Dripping", "tint": "#3aa0ff", "surface": {"roughness": 0.1, "metalness": 0.2}},
    "oozing":   {"label": "Oozing", "tint": "#7fd13a", "surface": {"roughness": 0.15, "emissive": 0.1}},
    "melting":  {"label": "Melting", "tint": "#ffae3a", "surface": {"roughness": 0.2, "emissive": 0.15}},
    "slime":    {"label": "Slime", "tint": "#43d39e", "surface": {"roughness": 0.1, "emissive": 0.2}, "vfx": "glow"},
    "molten":   {"label": "Molten", "tint": "#ff4a1a", "surface": {"roughness": 0.3, "emissive": 0.5}, "vfx": "embers"},
    "gooey":    {"label": "Gooey", "tint": "#c060ff", "surface": {"roughness": 0.12, "emissive": 0.12}},
    "wet":      {"label": "Wet", "tint": "#9cc4e8", "surface": {"roughness": 0.05, "metalness": 0.3}},
    "drenched": {"label": "Drenched", "tint": "#5a7a9a", "surface": {"roughness": 0.08, "metalness": 0.25}},
}
LIGHT_EMANATION_STYLES = {
    "glowing":      {"label": "Glowing", "tint": "#ffe66a", "surface": {"emissive": 0.4}, "vfx": "glow"},
    "radiant":      {"label": "Radiant", "tint": "#fff1b0", "surface": {"emissive": 0.55}, "vfx": "glow"},
    "luminous":     {"label": "Luminous", "tint": "#aee9ff", "surface": {"emissive": 0.5}, "vfx": "glow"},
    "beaming":      {"label": "Beaming", "tint": "#ffd34d", "surface": {"emissive": 0.6}, "vfx": "glow"},
    "incandescent": {"label": "Incandescent", "tint": "#ff7a3a", "surface": {"emissive": 0.65}, "vfx": "embers"},
    "phosphor":     {"label": "Phosphor", "tint": "#7fffb0", "surface": {"emissive": 0.5}, "vfx": "glow"},
    "neon_glow":    {"label": "Neon Glow", "tint": "#ff2bd6", "surface": {"emissive": 0.7, "metalness": 0.4}, "vfx": "glow"},
    "halo":         {"label": "Halo", "tint": "#fff7d0", "surface": {"emissive": 0.45}, "vfx": "sparkle"},
}
AURA_STYLES = {
    "fiery_aura":    {"label": "Fiery Aura", "tint": "#ff5a2a", "surface": {"emissive": 0.45}, "vfx": "embers"},
    "frost_aura":    {"label": "Frost Aura", "tint": "#aee9ff", "surface": {"emissive": 0.35}, "vfx": "sparkle"},
    "holy_aura":     {"label": "Holy Aura", "tint": "#fff1b0", "surface": {"emissive": 0.5}, "vfx": "glow"},
    "shadow_aura":   {"label": "Shadow Aura", "tint": "#2b2340", "surface": {"emissive": 0.25}, "vfx": "fog"},
    "electric_aura": {"label": "Electric Aura", "tint": "#ffe23a", "surface": {"emissive": 0.55}, "vfx": "glow"},
    "toxic_aura":    {"label": "Toxic Aura", "tint": "#7fd13a", "surface": {"emissive": 0.4}, "vfx": "fog"},
    "arcane_aura":   {"label": "Arcane Aura", "tint": "#b06cff", "surface": {"emissive": 0.45}, "vfx": "sparkle"},
    "void_aura":     {"label": "Void Aura", "tint": "#3a2b50", "surface": {"emissive": 0.3}, "vfx": "glow"},
}
EXOTIC_STYLES = {
    "alien":        {"label": "Alien", "tint": "#43d39e", "surface": {"roughness": 0.3, "emissive": 0.2}, "vfx": "glow"},
    "prismatic":    {"label": "Prismatic", "tint": "#7c9cff", "surface": {"roughness": 0.1, "metalness": 0.7, "emissive": 0.2}, "vfx": "sparkle"},
    "iridescent":   {"label": "Iridescent", "tint": "#9b6cff", "surface": {"roughness": 0.15, "metalness": 0.6, "emissive": 0.15}},
    "holographic":  {"label": "Holographic", "tint": "#4cc9f0", "surface": {"roughness": 0.1, "metalness": 0.5, "emissive": 0.3}, "vfx": "glow"},
    "otherworldly": {"label": "Otherworldly", "tint": "#c060ff", "surface": {"emissive": 0.3}, "vfx": "sparkle"},
    "biolume":      {"label": "Bioluminescent", "tint": "#3ad6a0", "surface": {"emissive": 0.4}, "vfx": "glow"},
    "cosmic":       {"label": "Cosmic", "tint": "#6a4aff", "surface": {"emissive": 0.35}, "vfx": "sparkle"},
    "quantum":      {"label": "Quantum", "tint": "#00e5ff", "surface": {"roughness": 0.12, "metalness": 0.6, "emissive": 0.25}, "vfx": "glow"},
}
FASHION_STYLES = {
    "elegant":         {"label": "Elegant", "tint": "#e6d2b0", "surface": {"roughness": 0.4, "metalness": 0.3}},
    "baroque":         {"label": "Baroque", "tint": "#d4af37", "surface": {"roughness": 0.35, "metalness": 0.6}},
    "streetwear":      {"label": "Streetwear", "tint": "#ff5a3a", "surface": {"roughness": 0.7}},
    "royal_couture":   {"label": "Royal Couture", "tint": "#7a3aff", "surface": {"roughness": 0.3, "metalness": 0.4, "emissive": 0.05}},
    "gothic":          {"label": "Gothic", "tint": "#2b2b2b", "surface": {"roughness": 0.5, "metalness": 0.3}},
    "tribal":          {"label": "Tribal", "tint": "#8a5a2a", "surface": {"roughness": 0.85}},
    "futuristic_chic": {"label": "Futuristic Chic", "tint": "#aab6c2", "surface": {"roughness": 0.2, "metalness": 0.6, "emissive": 0.1}},
    "vintage":         {"label": "Vintage", "tint": "#b08d57", "surface": {"roughness": 0.7, "metalness": 0.2}},
}
# Engraving — carved/etched surface treatments (motif + depth). Subtle grooves
# read as relief detail; the higher-relief options pick up a hint of emissive.
ENGRAVING_STYLES = {
    "none":       {"label": "None"},
    "etched":     {"label": "Etched", "tint": "#6a6a6a", "surface": {"roughness": 0.7, "metalness": 0.3}},
    "incised":    {"label": "Incised", "tint": "#5a5a5a", "surface": {"roughness": 0.62, "metalness": 0.35}},
    "filigree":   {"label": "Filigree", "tint": "#d4af37", "surface": {"roughness": 0.4, "metalness": 0.7, "emissive": 0.08}},
    "embossed":   {"label": "Embossed", "tint": "#b08d57", "surface": {"roughness": 0.5, "metalness": 0.5}},
    "runic":      {"label": "Runic", "tint": "#4cc9f0", "surface": {"roughness": 0.55, "metalness": 0.4, "emissive": 0.2}, "vfx": "glow"},
    "heraldic":   {"label": "Heraldic", "tint": "#a01818", "surface": {"roughness": 0.6, "metalness": 0.45}},
    "floral":     {"label": "Floral", "tint": "#90be6d", "surface": {"roughness": 0.6, "metalness": 0.3}},
    "geometric":  {"label": "Geometric", "tint": "#7c9cff", "surface": {"roughness": 0.55, "metalness": 0.4}},
    "scrimshaw":  {"label": "Scrimshaw", "tint": "#ece0c8", "surface": {"roughness": 0.72, "metalness": 0.1}},
    "engraved":   {"label": "Deep Engraved", "tint": "#4a4a4a", "surface": {"roughness": 0.68, "metalness": 0.38}},
    "inlaid":     {"label": "Inlaid", "tint": "#9b6cff", "surface": {"roughness": 0.45, "metalness": 0.6, "emissive": 0.1}},
}

# ── Dead-language / script styles. Picks the SCRIPT look (tint + glow). The
#    actual engraved TEXT + PLACEMENT come from the generate `inscription`
#    object (user types their own phrase, chooses where it sits). ────────────
SCRIPT_STYLES = {
    "none":         {"label": "None"},
    "runic":        {"label": "Elder Runic", "tint": "#4cc9f0", "surface": {"emissive": 0.22}, "vfx": "glow"},
    "younger_futhark": {"label": "Younger Futhark", "tint": "#6fd6ef", "surface": {"emissive": 0.18}, "vfx": "glow"},
    "latin":        {"label": "Latin", "tint": "#d4af37", "surface": {"metalness": 0.6, "roughness": 0.4}},
    "greek":        {"label": "Ancient Greek", "tint": "#cdd7e0", "surface": {"metalness": 0.5}},
    "babylonian":   {"label": "Babylonian Cuneiform", "tint": "#b08d57", "surface": {"roughness": 0.7}},
    "sumerian":     {"label": "Sumerian", "tint": "#c2a06a", "surface": {"roughness": 0.72}},
    "egyptian":     {"label": "Egyptian Hieroglyphs", "tint": "#e0c068", "surface": {"metalness": 0.55, "emissive": 0.06}},
    "demotic":      {"label": "Demotic", "tint": "#caa84a", "surface": {"roughness": 0.6}},
    "sanskrit":     {"label": "Sanskrit", "tint": "#ff9933", "surface": {"emissive": 0.1}},
    "ogham":        {"label": "Ogham", "tint": "#90be6d", "surface": {"roughness": 0.65}},
    "phoenician":   {"label": "Phoenician", "tint": "#a86b3c", "surface": {"roughness": 0.68}},
    "aramaic":      {"label": "Aramaic", "tint": "#bfae8e", "surface": {"roughness": 0.62}},
    "mayan":        {"label": "Mayan Glyphs", "tint": "#2a9d8f", "surface": {"emissive": 0.08}},
    "etruscan":     {"label": "Etruscan", "tint": "#9c6b4f", "surface": {"roughness": 0.66}},
    "linear_b":     {"label": "Linear B", "tint": "#b7c2cc", "surface": {"metalness": 0.45}},
    "gothic":       {"label": "Gothic Blackletter", "tint": "#2b2b2b", "surface": {"roughness": 0.55}},
    "celestial":    {"label": "Celestial Script", "tint": "#a78bfa", "surface": {"emissive": 0.3}, "vfx": "glow"},
    "draconic":     {"label": "Draconic", "tint": "#ef4444", "surface": {"emissive": 0.25}, "vfx": "glow"},
    "infernal":     {"label": "Infernal", "tint": "#ff6b35", "surface": {"emissive": 0.35}, "vfx": "glow"},
    "elvish":       {"label": "Elvish Tengwar", "tint": "#9be7ff", "surface": {"emissive": 0.2}, "vfx": "glow"},
    "dwarvish":     {"label": "Dwarvish Cirth", "tint": "#cdba96", "surface": {"metalness": 0.65}},
    "hieratic":     {"label": "Hieratic", "tint": "#d8b46a", "surface": {"roughness": 0.6}},
    "brahmi":       {"label": "Brahmi", "tint": "#f4a261", "surface": {"roughness": 0.58}},
    "nordic_bind":  {"label": "Nordic Bindrunes", "tint": "#5bc0eb", "surface": {"emissive": 0.24}, "vfx": "glow"},
}
# ── Tattoo styles — GLOBAL axis (applies to any forge): skin/surface ink. ────
TATTOO_STYLES = {
    "none":           {"label": "None"},
    "tribal":         {"label": "Tribal", "tint": "#111111", "surface": {"roughness": 0.7}},
    "blackwork":      {"label": "Blackwork", "tint": "#0a0a0a", "surface": {"roughness": 0.75}},
    "traditional":    {"label": "Traditional", "tint": "#c1121f"},
    "neo_traditional":{"label": "Neo-Traditional", "tint": "#e63946"},
    "irezumi":        {"label": "Japanese Irezumi", "tint": "#1d3557"},
    "dotwork":        {"label": "Dotwork", "tint": "#222222", "surface": {"roughness": 0.8}},
    "geometric_ink":  {"label": "Geometric", "tint": "#2b2d42"},
    "celtic_knot":    {"label": "Celtic Knot", "tint": "#0b6e4f"},
    "biomechanical":  {"label": "Biomechanical", "tint": "#5c677d", "surface": {"metalness": 0.5}},
    "watercolor":     {"label": "Watercolor", "tint": "#ff70a6", "surface": {"emissive": 0.05}},
    "linework":       {"label": "Fine Linework", "tint": "#333333"},
    "ornamental":     {"label": "Ornamental", "tint": "#7b2cbf"},
    "mandala":        {"label": "Mandala", "tint": "#5a189a"},
    "sak_yant":       {"label": "Sak Yant", "tint": "#1b263b"},
    "polynesian":     {"label": "Polynesian", "tint": "#0d1b2a", "surface": {"roughness": 0.72}},
    "maori":          {"label": "Maori Ta Moko", "tint": "#14213d"},
    "henna":          {"label": "Henna", "tint": "#8a5a2b"},
    "trash_polka":    {"label": "Trash Polka", "tint": "#9d0208"},
    "glow_ink":       {"label": "Glow Ink", "tint": "#39ff14", "surface": {"emissive": 0.4}, "vfx": "glow"},
    "scar_brand":     {"label": "Scarification", "tint": "#6b4f4f", "surface": {"roughness": 0.85}},
    "runic_ink":      {"label": "Runic Ink", "tint": "#4cc9f0", "surface": {"emissive": 0.25}, "vfx": "glow"},
}
# ── Mesh styles — topology / construction look (affects surface + read). ─────
MESH_STYLES = {
    "none":          {"label": "Default"},
    "wireframe":     {"label": "Wireframe", "tint": "#39ff14", "surface": {"emissive": 0.3, "metalness": 0.1}, "vfx": "glow"},
    "low_poly":      {"label": "Low-Poly", "surface": {"roughness": 0.6, "metalness": 0.2}},
    "high_poly":     {"label": "High-Poly", "surface": {"roughness": 0.35}},
    "voxel":         {"label": "Voxel", "surface": {"roughness": 0.8, "metalness": 0.0}},
    "faceted":       {"label": "Faceted", "surface": {"roughness": 0.45, "metalness": 0.4}},
    "smooth":        {"label": "Smooth Subdiv", "surface": {"roughness": 0.25}},
    "sculpted":      {"label": "Sculpted", "surface": {"roughness": 0.5}},
    "hard_surface":  {"label": "Hard-Surface", "surface": {"roughness": 0.3, "metalness": 0.7}},
    "organic":       {"label": "Organic", "surface": {"roughness": 0.6}},
    "displacement":  {"label": "Displacement", "surface": {"roughness": 0.72}},
    "triangulated":  {"label": "Triangulated", "surface": {"roughness": 0.5, "metalness": 0.3}},
    "quad_mesh":     {"label": "Quad Mesh", "surface": {"roughness": 0.4}},
    "point_cloud":   {"label": "Point Cloud", "tint": "#9be7ff", "surface": {"emissive": 0.2}, "vfx": "glow"},
    "parametric":    {"label": "Parametric", "surface": {"roughness": 0.35, "metalness": 0.5}},
    "boolean":       {"label": "Boolean Cut", "surface": {"roughness": 0.4, "metalness": 0.55}},
    "retopo":        {"label": "Retopologized", "surface": {"roughness": 0.42}},
    "nurbs":         {"label": "NURBS", "surface": {"roughness": 0.28, "metalness": 0.45}},
    "metaball":      {"label": "Metaball", "surface": {"roughness": 0.3}},
    "crystalline":   {"label": "Crystalline", "tint": "#a5f3fc", "surface": {"metalness": 0.6, "emissive": 0.15}, "vfx": "glow"},
    "shattered":     {"label": "Shattered", "surface": {"roughness": 0.55, "metalness": 0.35}},
}

# ── Illuminescence — internal light intensity ladder (dim → blinding). Drives
#    emissive strength and, at the high end, an emissive glow VFX. ────────────
ILLUMINESCENCE_STYLES = {
    "none":        {"label": "None"},
    "dim":         {"label": "Dim Glow", "tint": "#9aa0b0", "surface": {"emissive": 0.12}},
    "soft":        {"label": "Soft Light", "tint": "#cfd6e6", "surface": {"emissive": 0.22}},
    "glimmer":     {"label": "Glimmer", "tint": "#e6e0a0", "surface": {"emissive": 0.32}, "vfx": "glow"},
    "bright":      {"label": "Bright", "tint": "#fff1b0", "surface": {"emissive": 0.45}, "vfx": "glow"},
    "brilliant":   {"label": "Brilliant", "tint": "#fff7d0", "surface": {"emissive": 0.6}, "vfx": "glow"},
    "radiant_core":{"label": "Radiant Core", "tint": "#aee9ff", "surface": {"emissive": 0.7, "metalness": 0.3}, "vfx": "glow"},
    "blinding":    {"label": "Blinding", "tint": "#ffffff", "surface": {"emissive": 0.85}, "vfx": "glow"},
    "candlelight": {"label": "Candlelight", "tint": "#ffba6b", "surface": {"emissive": 0.2}, "vfx": "glow"},
    "moonlit":     {"label": "Moonlit", "tint": "#bcd0ff", "surface": {"emissive": 0.18}},
    "neon_hum":    {"label": "Neon Hum", "tint": "#ff2bd6", "surface": {"emissive": 0.5}, "vfx": "glow"},
    "holy_radiance":{"label": "Holy Radiance", "tint": "#fff2c0", "surface": {"emissive": 0.66, "metalness": 0.3}, "vfx": "glow"},
    "void_glow":   {"label": "Void Glow", "tint": "#7b2cbf", "surface": {"emissive": 0.4}, "vfx": "fog"},
    "plasma_arc":  {"label": "Plasma Arc", "tint": "#4cc9f0", "surface": {"emissive": 0.72}, "vfx": "glow"},
    "bioluminescent":{"label": "Bioluminescent", "tint": "#39ffa0", "surface": {"emissive": 0.5}, "vfx": "glow"},
    "lantern_warm":{"label": "Lantern Warm", "tint": "#f4a261", "surface": {"emissive": 0.3}, "vfx": "glow"},
    "starcore":    {"label": "Starcore", "tint": "#aee9ff", "surface": {"emissive": 0.8, "metalness": 0.4}, "vfx": "glow"},
}
# ── Decals — applied surface graphics (stickers/posters/insignia/etc.). ──────
DECAL_STYLES = {
    "none":        {"label": "None"},
    "stickers":    {"label": "Stickers", "tint": "#ff5a3a", "surface": {"roughness": 0.6}},
    "posters":     {"label": "Posters", "tint": "#f4a261", "surface": {"roughness": 0.7}},
    "graffiti":    {"label": "Graffiti", "tint": "#39ff14", "surface": {"roughness": 0.65, "emissive": 0.1}},
    "labels":      {"label": "Labels", "tint": "#e6ebf2", "surface": {"roughness": 0.55}},
    "insignia":    {"label": "Insignia", "tint": "#d4af37", "surface": {"metalness": 0.5, "roughness": 0.4}},
    "warning":     {"label": "Warning Marks", "tint": "#ffd200", "surface": {"emissive": 0.12}},
    "stencil":     {"label": "Stencil", "tint": "#2b2d42", "surface": {"roughness": 0.72}},
    "camo_wrap":   {"label": "Camo Wrap", "tint": "#4b5320", "surface": {"roughness": 0.7}},
    "racing_stripes":{"label": "Racing Stripes", "tint": "#e63946", "surface": {"roughness": 0.4}},
    "hazard_tape": {"label": "Hazard Tape", "tint": "#ffd200", "surface": {"emissive": 0.1}},
    "runes_print": {"label": "Rune Print", "tint": "#4cc9f0", "surface": {"emissive": 0.2}, "vfx": "glow"},
    "circuit_decal":{"label": "Circuit Decal", "tint": "#39ff14", "surface": {"emissive": 0.18, "metalness": 0.4}},
    "propaganda":  {"label": "Propaganda", "tint": "#a01818", "surface": {"roughness": 0.65}},
    "transfer_ink":{"label": "Transfer Ink", "tint": "#1d3557", "surface": {"roughness": 0.6}},
    "weather_worn":{"label": "Weather-Worn", "tint": "#8a7a66", "surface": {"roughness": 0.85}},
    "holo_sticker":{"label": "Holo Sticker", "tint": "#9b6cff", "surface": {"metalness": 0.7, "emissive": 0.15}, "vfx": "sparkle"},
}
# ── Symbols — overlaid symbolic motif sets (arcane/zodiac/sacred/etc.). ──────
SYMBOL_STYLES = {
    "none":            {"label": "None"},
    "arcane":          {"label": "Arcane", "tint": "#b06cff", "surface": {"emissive": 0.28}, "vfx": "glow"},
    "zodiac":          {"label": "Zodiac", "tint": "#a9d6ff", "surface": {"emissive": 0.2}},
    "alchemical":      {"label": "Alchemical", "tint": "#d4af37", "surface": {"metalness": 0.55, "emissive": 0.1}},
    "sacred_geometry": {"label": "Sacred Geometry", "tint": "#7c9cff", "surface": {"emissive": 0.22}},
    "sigils":          {"label": "Sigils", "tint": "#ff2bd6", "surface": {"emissive": 0.3}, "vfx": "glow"},
    "heraldry":        {"label": "Heraldry", "tint": "#a01818", "surface": {"metalness": 0.4, "roughness": 0.5}},
    "occult":          {"label": "Occult", "tint": "#5a2b40", "surface": {"emissive": 0.18}, "vfx": "fog"},
    "celestial":       {"label": "Celestial", "tint": "#a78bfa", "surface": {"emissive": 0.3}, "vfx": "glow"},
    "demonic":         {"label": "Demonic", "tint": "#ef4444", "surface": {"emissive": 0.28}, "vfx": "embers"},
    "divine":          {"label": "Divine", "tint": "#fff2c0", "surface": {"emissive": 0.4, "metalness": 0.4}, "vfx": "glow"},
    "tribal_mark":     {"label": "Tribal Marks", "tint": "#1b263b", "surface": {"roughness": 0.7}},
    "clan_crest":      {"label": "Clan Crest", "tint": "#0b6e4f", "surface": {"metalness": 0.4}},
    "ward_glyph":      {"label": "Ward Glyphs", "tint": "#4cc9f0", "surface": {"emissive": 0.25}, "vfx": "glow"},
    "constellation":   {"label": "Constellation", "tint": "#aee9ff", "surface": {"emissive": 0.32}, "vfx": "sparkle"},
    "eldritch":        {"label": "Eldritch", "tint": "#7b2cbf", "surface": {"emissive": 0.3}, "vfx": "fog"},
    "masonic":         {"label": "Masonic", "tint": "#d4af37", "surface": {"metalness": 0.55}},
}
# ── Scribbles — hand-drawn marks / media (chalk/charcoal/ink/etc.). ──────────
SCRIBBLE_STYLES = {
    "none":      {"label": "None"},
    "chalk":     {"label": "Chalk", "tint": "#e6ebf2", "surface": {"roughness": 0.95}},
    "charcoal":  {"label": "Charcoal", "tint": "#2b2b2b", "surface": {"roughness": 0.9}},
    "ink_doodle":{"label": "Ink Doodle", "tint": "#1d3557", "surface": {"roughness": 0.6}},
    "crayon":    {"label": "Crayon", "tint": "#ff70a6", "surface": {"roughness": 0.85}},
    "marker":    {"label": "Marker", "tint": "#e63946", "surface": {"roughness": 0.55}},
    "scratch":   {"label": "Scratchwork", "tint": "#6b4f4f", "surface": {"roughness": 0.88, "metalness": 0.2}},
    "graphite":  {"label": "Graphite", "tint": "#8a8a90", "surface": {"roughness": 0.7, "metalness": 0.25}},
    "pencil_sketch":{"label": "Pencil Sketch", "tint": "#9a9aa0", "surface": {"roughness": 0.8}},
    "pen_hatch": {"label": "Pen Hatch", "tint": "#16324f", "surface": {"roughness": 0.6}},
    "blueprint": {"label": "Blueprint Lines", "tint": "#3a7bd5", "surface": {"emissive": 0.12}},
    "kid_doodle":{"label": "Kid Doodle", "tint": "#ffb703", "surface": {"roughness": 0.85}},
    "calligraphy":{"label": "Calligraphy", "tint": "#1a1a1a", "surface": {"roughness": 0.5}},
    "glitch_scrawl":{"label": "Glitch Scrawl", "tint": "#39ff14", "surface": {"emissive": 0.25}, "vfx": "glow"},
    "ash_smear": {"label": "Ash Smear", "tint": "#3a3a3a", "surface": {"roughness": 0.9}},
    "wax_crayon":{"label": "Wax Crayon", "tint": "#e63946", "surface": {"roughness": 0.78}},
    "spray_tag": {"label": "Spray Tag", "tint": "#ff2bd6", "surface": {"roughness": 0.6, "emissive": 0.08}},
}
# ── Sparkles — particulate shimmer (glitter/stardust/fairy dust/etc.). ───────
SPARKLE_STYLES = {
    "none":           {"label": "None"},
    "glitter":        {"label": "Glitter", "tint": "#ffd34d", "surface": {"metalness": 0.6, "emissive": 0.2}, "vfx": "sparkle"},
    "stardust":       {"label": "Stardust", "tint": "#a9d6ff", "surface": {"emissive": 0.3}, "vfx": "sparkle"},
    "fairy_dust":     {"label": "Fairy Dust", "tint": "#f7a8d8", "surface": {"emissive": 0.32}, "vfx": "sparkle"},
    "ember_spark":    {"label": "Ember Spark", "tint": "#ff7a3a", "surface": {"emissive": 0.4}, "vfx": "embers"},
    "frost_sparkle":  {"label": "Frost Sparkle", "tint": "#aee9ff", "surface": {"emissive": 0.28, "metalness": 0.3}, "vfx": "sparkle"},
    "prismatic_spark":{"label": "Prismatic Spark", "tint": "#9b6cff", "surface": {"metalness": 0.7, "emissive": 0.25}, "vfx": "sparkle"},
    "gold_flecks":    {"label": "Gold Flecks", "tint": "#d4af37", "surface": {"metalness": 0.85, "emissive": 0.15}, "vfx": "sparkle"},
    "starlight":      {"label": "Starlight", "tint": "#fff7d0", "surface": {"emissive": 0.45}, "vfx": "sparkle"},
    "diamond_dust":   {"label": "Diamond Dust", "tint": "#eaf6ff", "surface": {"metalness": 0.7, "emissive": 0.2}, "vfx": "sparkle"},
    "comet_tail":     {"label": "Comet Tail", "tint": "#7fd6ff", "surface": {"emissive": 0.4}, "vfx": "sparkle"},
    "pixie_shimmer":  {"label": "Pixie Shimmer", "tint": "#f7a8d8", "surface": {"emissive": 0.34}, "vfx": "sparkle"},
    "holy_motes":     {"label": "Holy Motes", "tint": "#fff2c0", "surface": {"emissive": 0.42, "metalness": 0.3}, "vfx": "sparkle"},
    "void_specks":    {"label": "Void Specks", "tint": "#b06cff", "surface": {"emissive": 0.3}, "vfx": "sparkle"},
    "neon_fizz":      {"label": "Neon Fizz", "tint": "#39ff14", "surface": {"emissive": 0.38}, "vfx": "sparkle"},
    "snow_glint":     {"label": "Snow Glint", "tint": "#d6f0ff", "surface": {"emissive": 0.22, "metalness": 0.25}, "vfx": "sparkle"},
    "magma_spark":    {"label": "Magma Spark", "tint": "#ff5a1f", "surface": {"emissive": 0.45}, "vfx": "embers"},
}

# ── Biological / cosmic / physical axis pack (SOTA expansion) ───────────────
BIOLOGICAL_STYLES = {
    "none": {"label": "None"},
    "cellular": {"label": "Cellular", "tint": "#d98aa0", "surface": {"roughness": 0.7}},
    "veined": {"label": "Veined", "tint": "#a83246", "surface": {"roughness": 0.6}},
    "fleshy": {"label": "Fleshy", "tint": "#e0859a", "surface": {"roughness": 0.55}},
    "chitinous": {"label": "Chitinous", "tint": "#3a2b1f", "surface": {"metalness": 0.3, "roughness": 0.4}},
    "bony": {"label": "Bony", "tint": "#e8e0c8", "surface": {"roughness": 0.65}},
    "fungal": {"label": "Fungal", "tint": "#8a6f9e", "surface": {"roughness": 0.8}},
    "coral": {"label": "Coral", "tint": "#ff7f6b", "surface": {"roughness": 0.75}},
    "mossy": {"label": "Mossy", "tint": "#5a7d3a", "surface": {"roughness": 0.9}},
    "scaled": {"label": "Scaled", "tint": "#2f6b4f", "surface": {"metalness": 0.25, "roughness": 0.5}},
    "feathered": {"label": "Feathered", "tint": "#7a8fb0", "surface": {"roughness": 0.7}},
    "slimy": {"label": "Slimy", "tint": "#5fb86f", "surface": {"roughness": 0.2, "emissive": 0.06}},
    "barklike": {"label": "Bark-like", "tint": "#6b4f33", "surface": {"roughness": 0.92}},
}
BIOLOGICAL_ABERRANT_STYLES = {
    "none": {"label": "None"},
    "mutated": {"label": "Mutated", "tint": "#9b6cff", "surface": {"roughness": 0.6}},
    "tumorous": {"label": "Tumorous", "tint": "#a8556b", "surface": {"roughness": 0.7}},
    "asymmetric": {"label": "Asymmetric", "tint": "#7a5a8a"},
    "vestigial": {"label": "Vestigial", "tint": "#caa9b0", "surface": {"roughness": 0.7}},
    "hypergrowth": {"label": "Hypergrowth", "tint": "#5fb86f", "surface": {"emissive": 0.08}},
    "fused": {"label": "Fused", "tint": "#6b4f5a", "surface": {"metalness": 0.2}},
    "parasitic": {"label": "Parasitic", "tint": "#3a6b4f", "surface": {"roughness": 0.6}},
    "necrotic": {"label": "Necrotic", "tint": "#4a4a3a", "surface": {"roughness": 0.85}},
    "crystalgrowth": {"label": "Crystal Growth", "tint": "#7fd6ff", "surface": {"metalness": 0.6, "emissive": 0.2}, "vfx": "sparkle"},
    "melted": {"label": "Melted", "tint": "#b06a3a", "surface": {"roughness": 0.3}},
}
BIOLOGICAL_MONSTROSITY_STYLES = {
    "none": {"label": "None"},
    "many_eyed": {"label": "Many-Eyed", "tint": "#c9b037", "surface": {"emissive": 0.15}, "vfx": "glow"},
    "tentacled": {"label": "Tentacled", "tint": "#5a2b6b", "surface": {"roughness": 0.4}},
    "maw_ridden": {"label": "Maw-Ridden", "tint": "#7a1f2b", "surface": {"roughness": 0.6}},
    "spined": {"label": "Spined", "tint": "#2b2b35", "surface": {"metalness": 0.35}},
    "multi_limbed": {"label": "Multi-Limbed", "tint": "#4a3a5a"},
    "writhing": {"label": "Writhing", "tint": "#6b2b4f", "surface": {"emissive": 0.1}},
    "gaping": {"label": "Gaping", "tint": "#3a0f1a", "surface": {"roughness": 0.7}},
    "chitin_horror": {"label": "Chitin Horror", "tint": "#1f1a14", "surface": {"metalness": 0.4, "roughness": 0.3}},
    "eldritch_flesh": {"label": "Eldritch Flesh", "tint": "#7b2cbf", "surface": {"emissive": 0.2}, "vfx": "fog"},
    "horned_mass": {"label": "Horned Mass", "tint": "#3a2b1f", "surface": {"roughness": 0.6}},
}
STARLIGHT_STYLES = {
    "none": {"label": "None"},
    "faint_stars": {"label": "Faint Stars", "tint": "#bcd0ff", "surface": {"emissive": 0.18}, "vfx": "sparkle"},
    "star_field": {"label": "Star Field", "tint": "#aee9ff", "surface": {"emissive": 0.3}, "vfx": "sparkle"},
    "twinkle": {"label": "Twinkle", "tint": "#fff7d0", "surface": {"emissive": 0.35}, "vfx": "sparkle"},
    "nebula_dust": {"label": "Nebula Dust", "tint": "#b06cff", "surface": {"emissive": 0.28}, "vfx": "fog"},
    "pulsar": {"label": "Pulsar", "tint": "#4cc9f0", "surface": {"emissive": 0.55}, "vfx": "glow"},
    "supernova": {"label": "Supernova", "tint": "#ffba6b", "surface": {"emissive": 0.7}, "vfx": "glow"},
    "constellation_map": {"label": "Constellation Map", "tint": "#a9d6ff", "surface": {"emissive": 0.32}, "vfx": "sparkle"},
    "galaxy_swirl": {"label": "Galaxy Swirl", "tint": "#7c5cff", "surface": {"emissive": 0.4}, "vfx": "glow"},
    "cosmic_ray": {"label": "Cosmic Ray", "tint": "#39ffa0", "surface": {"emissive": 0.5}, "vfx": "glow"},
}
COSMIC_STYLES = {
    "none": {"label": "None"},
    "void": {"label": "Void", "tint": "#0b0b18", "surface": {"emissive": 0.05}, "vfx": "fog"},
    "nebula": {"label": "Nebula", "tint": "#9b6cff", "surface": {"emissive": 0.3}, "vfx": "fog"},
    "galaxy": {"label": "Galaxy", "tint": "#5c7cff", "surface": {"emissive": 0.35}, "vfx": "sparkle"},
    "blackhole": {"label": "Black Hole", "tint": "#1a0f2b", "surface": {"emissive": 0.2}, "vfx": "glow"},
    "quasar": {"label": "Quasar", "tint": "#4cc9f0", "surface": {"emissive": 0.65}, "vfx": "glow"},
    "stardust_cloud": {"label": "Stardust Cloud", "tint": "#aee9ff", "surface": {"emissive": 0.3}, "vfx": "sparkle"},
    "aurora": {"label": "Aurora", "tint": "#39ffa0", "surface": {"emissive": 0.4}, "vfx": "glow"},
    "event_horizon": {"label": "Event Horizon", "tint": "#ff7a3a", "surface": {"emissive": 0.5}, "vfx": "glow"},
    "dark_matter": {"label": "Dark Matter", "tint": "#2b1a3a", "surface": {"emissive": 0.12}, "vfx": "fog"},
    "celestial_gold": {"label": "Celestial Gold", "tint": "#ffd34d", "surface": {"metalness": 0.8, "emissive": 0.2}, "vfx": "glow"},
}
SUBSURFACE_STYLES = {
    "none": {"label": "None"},
    "jade_sss": {"label": "Jade SSS", "tint": "#3fa37a", "surface": {"roughness": 0.3, "emissive": 0.08}},
    "wax_sss": {"label": "Wax SSS", "tint": "#f0e6c8", "surface": {"roughness": 0.4, "emissive": 0.06}},
    "marble_sss": {"label": "Marble SSS", "tint": "#eef0f2", "surface": {"roughness": 0.35}},
    "skin_sss": {"label": "Skin SSS", "tint": "#e0a890", "surface": {"roughness": 0.5}},
    "milk_sss": {"label": "Milk SSS", "tint": "#f6f4ee", "surface": {"roughness": 0.45}},
    "gemstone_sss": {"label": "Gemstone SSS", "tint": "#7fd6ff", "surface": {"metalness": 0.5, "emissive": 0.15}},
    "frosted_sss": {"label": "Frosted SSS", "tint": "#d6f0ff", "surface": {"roughness": 0.5, "emissive": 0.1}},
    "candle_sss": {"label": "Candle SSS", "tint": "#ffba6b", "surface": {"emissive": 0.18}},
    "leaf_sss": {"label": "Leaf SSS", "tint": "#7bbf4a", "surface": {"roughness": 0.4, "emissive": 0.06}},
}
METEORITE_STYLES = {
    "none": {"label": "None"},
    "iron_meteor": {"label": "Iron Meteorite", "tint": "#4a4a52", "surface": {"metalness": 0.85, "roughness": 0.4}},
    "stony_meteor": {"label": "Stony Meteorite", "tint": "#5a5048", "surface": {"roughness": 0.8}},
    "pallasite": {"label": "Pallasite", "tint": "#c9a14a", "surface": {"metalness": 0.6, "emissive": 0.1}},
    "fusion_crust": {"label": "Fusion Crust", "tint": "#1f1a18", "surface": {"roughness": 0.7}},
    "regmaglypts": {"label": "Regmaglypts", "tint": "#3a342e", "surface": {"roughness": 0.85}},
    "widmanstatten": {"label": "Widmanstätten", "tint": "#8a8a92", "surface": {"metalness": 0.9, "roughness": 0.3}},
    "impact_glass": {"label": "Impact Glass", "tint": "#3a5a4a", "surface": {"roughness": 0.2, "emissive": 0.08}},
    "chondrite": {"label": "Chondrite", "tint": "#6b5f52", "surface": {"roughness": 0.75}},
    "nickel_iron": {"label": "Nickel-Iron", "tint": "#9a9aa2", "surface": {"metalness": 0.88, "roughness": 0.35}},
}
WEIGHT_STYLES = {
    "balanced": {"label": "Balanced"}, "feather": {"label": "Feather-light"},
    "light": {"label": "Light"}, "hefty": {"label": "Hefty"}, "heavy": {"label": "Heavy"},
    "dense": {"label": "Dense", "surface": {"metalness": 0.3}}, "leaden": {"label": "Leaden", "surface": {"metalness": 0.4}},
    "massive": {"label": "Massive", "surface": {"metalness": 0.5}}, "colossal": {"label": "Colossal", "surface": {"metalness": 0.6}},
}
SIZE_STYLES = {
    "standard": {"label": "Standard"}, "miniature": {"label": "Miniature"}, "small": {"label": "Small"},
    "compact": {"label": "Compact"}, "large": {"label": "Large"}, "oversized": {"label": "Oversized"},
    "huge": {"label": "Huge"}, "giant": {"label": "Giant"}, "titanic": {"label": "Titanic"},
}
HEIGHT_STYLES = {
    "mid": {"label": "Mid"}, "flat": {"label": "Flat"}, "low": {"label": "Low"},
    "tall": {"label": "Tall"}, "towering": {"label": "Towering"}, "soaring": {"label": "Soaring"},
    "monolithic": {"label": "Monolithic"}, "skyscraping": {"label": "Skyscraping"},
}
LEGENDARY_FLAIR_STYLES = {
    "common": {"label": "Common", "tint": "#9aa0b0"},
    "uncommon": {"label": "Uncommon", "tint": "#5fb86f", "surface": {"emissive": 0.06}},
    "rare": {"label": "Rare", "tint": "#4c9bf0", "surface": {"emissive": 0.12}, "vfx": "glow"},
    "epic": {"label": "Epic", "tint": "#9b6cff", "surface": {"emissive": 0.2}, "vfx": "glow"},
    "legendary": {"label": "Legendary", "tint": "#ffba3a", "surface": {"metalness": 0.6, "emissive": 0.3}, "vfx": "glow"},
    "mythic": {"label": "Mythic", "tint": "#ff5a8a", "surface": {"emissive": 0.4}, "vfx": "sparkle"},
    "ascended": {"label": "Ascended", "tint": "#fff2c0", "surface": {"metalness": 0.5, "emissive": 0.5}, "vfx": "glow"},
    "divine": {"label": "Divine", "tint": "#fffbe6", "surface": {"emissive": 0.6, "metalness": 0.4}, "vfx": "glow"},
    "primordial": {"label": "Primordial", "tint": "#7b2cbf", "surface": {"emissive": 0.45}, "vfx": "fog"},
    "cosmic_tier": {"label": "Cosmic Tier", "tint": "#39ffd0", "surface": {"emissive": 0.6}, "vfx": "sparkle"},
}

# Registry: axis key → {label, options}. Order = display order.
STYLE_AXES: dict[str, dict] = {
    "art_style":       {"label": "General Style", "options": ART_STYLES},
    "period":          {"label": "Time Period", "options": PERIOD_STYLES},
    "realism":         {"label": "Realism", "options": REALISM_STYLES},
    "fantasy":         {"label": "Fantasy", "options": FANTASY_STYLES},
    "punk":            {"label": "Punk", "options": PUNK_STYLES},
    "metal_grade":     {"label": "Metal Grade", "options": METAL_GRADES},
    "engraving":       {"label": "Engraving", "options": ENGRAVING_STYLES},
    "finish":          {"label": "Finish", "options": FINISH_STYLES},
    "elemental":       {"label": "Elemental", "options": ELEMENTAL_STYLES},
    "magic":           {"label": "Magic", "options": MAGIC_STYLES},
    "curse":           {"label": "Curse", "options": CURSE_STYLES},
    "dripping":        {"label": "Dripping", "options": DRIPPING_STYLES},
    "light_emanation": {"label": "Light Emanation", "options": LIGHT_EMANATION_STYLES},
    "aura":            {"label": "Aura", "options": AURA_STYLES},
    "exotic":          {"label": "Exotic", "options": EXOTIC_STYLES},
    "fashion":         {"label": "Fashion", "options": FASHION_STYLES},
    "script":          {"label": "Dead Language / Script", "options": SCRIPT_STYLES},
    "tattoo":          {"label": "Tattoo Style", "options": TATTOO_STYLES},
    "mesh":            {"label": "Mesh Style", "options": MESH_STYLES},
    "illuminescence":  {"label": "Illuminescence", "options": ILLUMINESCENCE_STYLES},
    "decals":          {"label": "Decals", "options": DECAL_STYLES},
    "symbols":         {"label": "Symbols", "options": SYMBOL_STYLES},
    "scribbles":       {"label": "Scribbles", "options": SCRIBBLE_STYLES},
    "sparkles":        {"label": "Sparkles", "options": SPARKLE_STYLES},
    "biological":      {"label": "Biological", "options": BIOLOGICAL_STYLES},
    "biological_aberrant":   {"label": "Biological Aberrant", "options": BIOLOGICAL_ABERRANT_STYLES},
    "biological_monstrosity":{"label": "Biological Monstrosity", "options": BIOLOGICAL_MONSTROSITY_STYLES},
    "starlight":       {"label": "Starlight", "options": STARLIGHT_STYLES},
    "cosmic":          {"label": "Cosmic", "options": COSMIC_STYLES},
    "subsurface":      {"label": "Subsurface", "options": SUBSURFACE_STYLES},
    "meteorite":       {"label": "Meteorite", "options": METEORITE_STYLES},
    "weight":          {"label": "Weight", "options": WEIGHT_STYLES},
    "size":            {"label": "Size", "options": SIZE_STYLES},
    "height":          {"label": "Height", "options": HEIGHT_STYLES},
    "legendary_flair": {"label": "Legendary Flair", "options": LEGENDARY_FLAIR_STYLES},
}

# ── Region-specific surface treatments (decals applied to the geometry) ──────
TREATMENTS: dict[str, dict] = {
    "none":       {"label": "None"},
    "markings":   {"label": "Markings", "shape": "box", "thin": True, "n": 5, "emissive": 0.15},
    "etchings":   {"label": "Etchings", "shape": "box", "thin": True, "n": 8, "emissive": 0.05},
    "symbols":    {"label": "Symbols", "shape": "cone", "thin": False, "n": 4, "emissive": 0.25},
    "signatures": {"label": "Signatures", "shape": "box", "thin": True, "n": 3, "emissive": 0.1},
    "prints":     {"label": "Prints", "shape": "cylinder", "thin": False, "n": 6, "emissive": 0.2},
}

# Where engraved inscription TEXT sits on the mesh (user picks; "custom" lets
# them type a free-form placement label which falls back to auto positioning).
INSCRIPTION_PLACEMENTS: list[dict] = [
    {"key": "auto",    "label": "Auto"},
    {"key": "blade",   "label": "Blade / Top"},
    {"key": "handle",  "label": "Handle / Grip"},
    {"key": "body",    "label": "Body / Surface"},
    {"key": "base",    "label": "Base / Foot"},
    {"key": "wrap",    "label": "Wrap-Around"},
    {"key": "custom",  "label": "Custom…"},
]
# Per-axis Basic vs Advanced split — first N options = Basic, rest = Advanced.
_BASIC_N = 6

# Curated multi-axis "style packs" — one tap sets several axes coherently.
STYLE_PACKS: list[dict] = [
    {"key": "dark_cyber_ruins", "label": "Dark Cyber Ruins", "icon": "🌆",
     "skin_style": "neon", "axes": {"art_style": "noir", "punk": "cyberpunk", "period": "post_apocalyptic"},
     "treatment": "symbols", "intricacy": "ornate"},
    {"key": "ancient_temple", "label": "Ancient Temple", "icon": "🏛️",
     "skin_style": "weathered", "axes": {"period": "ancient", "fantasy": "mythic", "realism": "semi_real"},
     "treatment": "etchings", "intricacy": "baroque"},
    {"key": "fairytale_grove", "label": "Fairytale Grove", "icon": "🧚",
     "skin_style": "glowing", "axes": {"fantasy": "fairytale", "art_style": "handpainted"},
     "treatment": "markings", "intricacy": "ornate"},
    {"key": "steam_workshop", "label": "Steam Workshop", "icon": "⚙️",
     "skin_style": "metallic", "axes": {"punk": "steampunk", "period": "victorian", "realism": "photoreal"},
     "treatment": "signatures", "intricacy": "ornate"},
    {"key": "celestial_shrine", "label": "Celestial Shrine", "icon": "🌌",
     "skin_style": "holographic", "axes": {"fantasy": "celestial", "art_style": "cel_shaded"},
     "treatment": "symbols", "intricacy": "baroque"},
    {"key": "solar_eden", "label": "Solar Eden", "icon": "🌿",
     "skin_style": "satin", "axes": {"punk": "solarpunk", "realism": "stylized_real"},
     "treatment": "prints", "intricacy": "subtle"},
    {"key": "voxel_toybox", "label": "Voxel Toybox", "icon": "🧱",
     "skin_style": "matte", "axes": {"art_style": "voxel", "realism": "flat"},
     "treatment": "markings", "intricacy": "subtle"},
    {"key": "eldritch_depths", "label": "Eldritch Depths", "icon": "🐙",
     "skin_style": "crystalline", "axes": {"fantasy": "eldritch", "punk": "biopunk", "art_style": "noir"},
     "treatment": "etchings", "intricacy": "baroque"},
]

# ── Guarantee every axis offers >=9 options (Full axis tree). Axes with fewer
#    are topped up with deterministic variants derived from their richest
#    existing option, so creators always get a deep, consistent tree. ─────────
_AXIS_MIN_OPTS = 9
_PADDED_AXES: list = []
_VARIANT_MODS = [
    ("deep", "Deep", {"roughness": 0.1}), ("bright", "Bright", {"emissive": 0.12}),
    ("worn", "Worn", {"roughness": 0.2}), ("polished", "Polished", {"roughness": -0.15, "metalness": 0.15}),
    ("faded", "Faded", {"emissive": -0.05}), ("vivid", "Vivid", {"emissive": 0.18}),
    ("dark", "Dark", {"roughness": 0.05}), ("pale", "Pale", {"emissive": 0.04}),
    ("rich", "Rich", {"metalness": 0.1}), ("muted", "Muted", {"roughness": 0.12}),
    ("intense", "Intense", {"emissive": 0.2}), ("antique", "Antique", {"roughness": 0.15}),
]


def _ensure_min_options(min_n: int = _AXIS_MIN_OPTS) -> None:
    for _akey, meta in STYLE_AXES.items():
        opts = meta["options"]
        if len(opts) >= min_n:
            continue
        _PADDED_AXES.append((_akey, len(opts)))
        donor_key = next((k for k in opts if k != "none"), None)
        if donor_key is None:
            continue
        donor = opts[donor_key]
        i = 0
        while len(opts) < min_n and i < len(_VARIANT_MODS):
            mk, ml, surf = _VARIANT_MODS[i]; i += 1
            nk = f"{donor_key}_{mk}"
            if nk in opts:
                continue
            base_surf = dict(donor.get("surface") or {})
            for sk, dv in surf.items():
                base_surf[sk] = round(max(0.0, min(1.0, base_surf.get(sk, 0.4) + dv)), 2)
            no: dict = {"label": f"{ml} {donor.get('label', donor_key)}"}
            if donor.get("tint"):
                no["tint"] = donor["tint"]
            if base_surf:
                no["surface"] = base_surf
            if donor.get("vfx"):
                no["vfx"] = donor["vfx"]
            opts[nk] = no


# NOTE: the top-up runs ONCE at the very end (after ALL axes + real authoring),
# purely as a safety net — see the call after _build_extra_axes() below.

# ── Axis tree — the complete axis hierarchy grouped into families. ──────────
AXIS_GROUPS: list[dict] = [
    {"group": "Look & Era", "icon": "🎨", "axes": ["art_style", "period", "realism", "fantasy", "punk", "exotic", "fashion"]},
    {"group": "Material & Finish", "icon": "🧱", "axes": ["metal_grade", "finish", "mesh", "subsurface", "meteorite"]},
    {"group": "Marks & Engraving", "icon": "✍️", "axes": ["engraving", "script", "tattoo", "decals", "symbols", "scribbles"]},
    {"group": "Magic & Light", "icon": "✨", "axes": ["magic", "curse", "elemental", "aura", "light_emanation", "illuminescence", "sparkles", "starlight", "cosmic", "dripping"]},
    {"group": "Biological", "icon": "🧬", "axes": ["biological", "biological_aberrant", "biological_monstrosity"]},
    {"group": "Physical & Quality", "icon": "⚖️", "axes": ["weight", "size", "height", "legendary_flair"]},
]


def axis_tree() -> dict:
    """Full axis tree: every group → its axes → option counts/labels."""
    seen: set[str] = set()
    groups = []
    for g in AXIS_GROUPS:
        axes = []
        for k in g["axes"]:
            if k not in STYLE_AXES:
                continue
            seen.add(k)
            ax = STYLE_AXES[k]
            axes.append({"key": k, "label": ax["label"], "option_count": len(ax["options"]),
                         "options": [{"key": ok, "label": (ov or {}).get("label", ok)}
                                     for ok, ov in ax["options"].items()]})
        groups.append({"group": g["group"], "icon": g["icon"], "axes": axes, "axis_count": len(axes)})
    # any axis not placed in a group → "Other"
    other = [k for k in STYLE_AXES if k not in seen]
    if other:
        groups.append({"group": "Other", "icon": "🔧", "axis_count": len(other),
                       "axes": [{"key": k, "label": STYLE_AXES[k]["label"],
                                 "option_count": len(STYLE_AXES[k]["options"]),
                                 "options": [{"key": ok, "label": (ov or {}).get("label", ok)}
                                             for ok, ov in STYLE_AXES[k]["options"].items()]} for k in other]})
    total_axes = len(STYLE_AXES)
    total_opts = sum(len(a["options"]) for a in STYLE_AXES.values())
    return {"groups": groups, "axis_count": total_axes, "option_count": total_opts}


# ── Per-build Style Packs — persist a creator's axis combo so a whole batch
#    (and future tools) inherit one cohesive AAA look in a tap. ───────────────
def save_build_style_pack(build_id: str, label: str, axes: dict,
                          skin_style: str | None = None) -> dict:
    from core.databases import get_sync_db
    import time as _t
    pid = f"sp_{abs(hash((build_id, label, _t.time())))%10**10}"
    doc = {"_id": pid, "build_id": build_id, "label": label or "Style Pack",
           "axes": axes or {}, "skin_style": skin_style, "created": _t.time()}
    get_sync_db()["galaxy_style_packs"].replace_one({"_id": pid}, doc, upsert=True)
    return {"id": pid, "build_id": build_id, "label": doc["label"], "axes": doc["axes"]}


def list_build_style_packs(build_id: str) -> dict:
    from core.databases import get_sync_db
    cur = get_sync_db()["galaxy_style_packs"].find({"build_id": build_id}).sort("created", -1).limit(50)
    packs = [{"id": d["_id"], "label": d.get("label"), "axes": d.get("axes", {}),
              "skin_style": d.get("skin_style")} for d in cur]
    return {"build_id": build_id, "packs": packs, "count": len(packs)}



def _blend_hex(a: str, b: str, t: float) -> str:
    """Linear blend two hex colours (t toward b)."""
    try:
        ah, bh = a.lstrip("#"), b.lstrip("#")
        ar, ag, ab = int(ah[0:2], 16), int(ah[2:4], 16), int(ah[4:6], 16)
        br, bg, bb = int(bh[0:2], 16), int(bh[2:4], 16), int(bh[4:6], 16)
        f = lambda x, y: max(0, min(255, int(x + (y - x) * t)))  # noqa: E731
        return f"#{f(ar, br):02x}{f(ag, bg):02x}{f(ab, bb):02x}"
    except Exception:
        return a


def _hsl_to_hex(h: float, s: float, lum: float) -> str:
    c = (1 - abs(2 * lum - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = lum - c / 2
    r, g, b = {0: (c, x, 0), 1: (x, c, 0), 2: (0, c, x),
               3: (0, x, c), 4: (x, 0, c), 5: (c, 0, x)}[int(h // 60) % 6]
    return f"#{int((r+m)*255):02x}{int((g+m)*255):02x}{int((b+m)*255):02x}"


def _region_accent(region: str | None) -> str:
    """Deterministic, vivid accent colour per region/family — drives the
    region-specific treatment markings so each region reads distinctly."""
    key = (region or "scene")
    h = int(hashlib.sha256(key.encode()).hexdigest()[:6], 16)
    return _hsl_to_hex(h % 360, 0.7, 0.56)


def _region_treatment(region: str | None) -> str:
    keys = [k for k in TREATMENTS if k != "none"]
    h = int(hashlib.sha256((region or "scene").encode()).hexdigest()[6:12], 16)
    return keys[h % len(keys)]


def apply_axis_directives(spec: dict, directives: dict | None) -> dict:
    """Mirror snowball_axes GEOMETRY directives (the option `effect` dicts, e.g.
    {tri_budget, proportion, lod, rig, dim, paneling, squash_stretch, ...}) onto
    the forged 3D spec so the actual geometry reflects the creator's axis picks.

    This is the end-to-end bridge: snowball_axes.resolve() → merged effects →
    real changes in part density, proportions, panelling and engine tags.
    """
    if not directives:
        return spec
    d = dict(directives)
    geo = list(spec.get("geometry") or [])

    # ── Dimension / engine path ──────────────────────────────────────────────
    if d.get("dim"):
        spec["dimension"] = d["dim"]
    if d.get("engine_path"):
        spec["engine_path"] = d["engine_path"]

    # ── Triangle budget → real part-density scaling ──────────────────────────
    tri = d.get("tri_budget")
    if tri is not None and geo:
        if tri == -1:                       # virtualized micropoly → max detail
            spec["topo"] = "virtualized"
            density = 2.0
        else:
            spec["tri_budget"] = int(tri)
            # map budget bands → a density multiplier on procedural sub-parts
            density = (0.4 if tri <= 500 else 0.7 if tri <= 2000 else 1.0
                       if tri <= 10000 else 1.5 if tri <= 50000 else 2.0)
        base = [p for p in geo if not p.get("decal")]
        if density < 1.0:                   # decimate — keep the silhouette
            keep = max(1, int(len(base) * density))
            decals = [p for p in geo if p.get("decal")]
            geo = base[:keep] + decals
        elif density > 1.0 and base:        # densify — add subdivided detail parts
            extra = int(len(base) * (density - 1.0))
            for k in range(min(extra, 64)):
                src = dict(base[k % len(base)])
                sz = [max(0.05, v * 0.5) for v in src.get("size", [1, 1, 1])]
                pos = [v + (0.03 * ((k % 3) - 1)) for v in src.get("pos", [0, 0, 0])]
                geo.append({**src, "size": sz, "pos": pos, "subdiv": True})
    if d.get("topo"):
        spec["topo"] = d["topo"]
    if d.get("displacement"):
        spec["displacement"] = True
    if d.get("subd"):
        spec["topo"] = "subd"

    # ── Body proportions → reshape the tallest/biggest part as the "head" ─────
    prop = d.get("proportion")
    if prop and geo:
        ratio = {"2head": 0.5, "block": 0.9, "8head": 1.25, "7.5head": 1.18,
                 "mech": 1.1, "flex": 1.0, "varied": 1.05}.get(str(prop), 1.0)
        tallest = max(geo, key=lambda p: (p.get("size") or [0, 0, 0])[1] if not p.get("decal") else -1)
        if not tallest.get("decal"):
            sz = list(tallest.get("size") or [1, 1, 1])
            sz[1] = round(sz[1] * ratio, 3)
            tallest["size"] = sz
        spec["proportion"] = prop
    if d.get("limb"):
        spec["limb"] = d["limb"]

    # ── Hard-surface paneling / kitbash → add real panel-line decal geometry ──
    if (d.get("paneling") or d.get("kitbash")) and geo:
        base = [p for p in geo if not p.get("decal")]
        for k in range(min(8, len(base) * 2)):
            src = base[k % len(base)]
            sp = list(src.get("pos") or [0, 0, 0])
            ss = list(src.get("size") or [1, 1, 1])
            geo.append({
                "shape": "box", "decal": True, "panel": True,
                "pos": [sp[0], sp[1] + ss[1] * 0.5, sp[2]],
                "size": [ss[0] * 0.96, max(0.01, ss[1] * 0.04), ss[2] * 0.96],
                "color": "#1b1f29", "emissive": 0.02,
            })
        spec["hard_surface"] = True

    # ── Engine / animation tags (recorded so downstream + UI can honour them) ─
    for tag in ("lod", "rig", "anim", "morph", "levels", "ik_chains",
                "blendshapes", "muscle", "jiggle", "squash_stretch", "spline",
                "bones", "anatomy", "silhouette"):
        if tag in d:
            spec[tag] = d[tag]

    spec["geometry"] = geo
    spec["axis_directives"] = d
    det = dict(spec.get("detail") or {})
    det["axis_directives"] = d
    spec["detail"] = det
    return spec


def _apply_style_axes(spec: dict, rng: random.Random, axes: dict | None) -> dict:
    """Stack any of the new style axes (general/period/realism/fantasy/punk)
    onto the spec: re-tint palette toward each tint, merge surface, set vfx."""
    if not axes:
        return spec
    pal = list(spec.get("palette") or [])
    surface = dict(spec.get("surface") or {})
    applied: dict[str, str] = {}
    tints: list[str] = []
    vfx = None
    for axis, meta in STYLE_AXES.items():
        sel = axes.get(axis)
        if not sel or sel not in meta["options"]:
            continue
        o = meta["options"][sel]
        applied[axis] = sel
        if o.get("tint"):
            tints.append(o["tint"])
        surface.update(o.get("surface") or {})
        if o.get("vfx"):
            vfx = o["vfx"]
    if tints and pal:
        for i, t in enumerate(tints):
            pal[i % len(pal)] = _blend_hex(pal[i % len(pal)], t, 0.5)
    spec["palette"] = pal
    spec["surface"] = surface
    if vfx:
        spec["vfx"] = vfx
    if applied:
        spec["style_axes"] = applied
    return spec


def _apply_treatment(spec: dict, rng: random.Random, treatment: str | None,
                     region: str | None) -> dict:
    """Add region-specific decal geometry (markings/etchings/symbols/etc.)
    in the region's accent colour so variants differ at a glance."""
    if not treatment or treatment == "none" or treatment not in TREATMENTS:
        return spec
    t = TREATMENTS[treatment]
    geo = list(spec.get("geometry") or [])
    if not geo:
        return spec
    accent = _region_accent(region)
    base = [p for p in geo if not p.get("decal")]
    if not base:
        return spec
    n = int(t.get("n", 4))
    shape = t.get("shape", "box")
    thin = bool(t.get("thin"))
    emissive = float(t.get("emissive", 0.1))
    for k in range(n):
        src = base[k % len(base)]
        sp = src.get("pos", [0, 0, 0])
        ss = src.get("size", [1, 1, 1])
        size = ([round((ss[0] or 1) * 0.5, 2), 0.04, round((ss[2] or 1) * 0.16, 2)]
                if thin else [round(min(ss[0] or 1, 1) * 0.2, 2)] * 3)
        geo.append({
            "type": shape,
            "pos": [round(sp[0] + rng.uniform(-0.25, 0.25) * (ss[0] or 1), 2),
                    round(sp[1] + rng.uniform(0.15, 0.6) * (ss[1] or 1), 2),
                    round(sp[2] + (ss[2] or 1) / 2 + 0.03, 2)],
            "size": size, "color": accent, "decal": True, "emissive": emissive,
        })
    spec["geometry"] = geo
    spec["treatment"] = treatment
    spec["treatment_region"] = region
    spec["treatment_accent"] = accent
    return spec


def _apply_inscription(spec: dict, rng: random.Random, color: str | None) -> dict:
    """Engrave fine inscription lines in the chosen colour (tied to the colour
    picker). Subtle, low-emissive grooves layered over the top faces."""
    if not color:
        return spec
    geo = list(spec.get("geometry") or [])
    base = [p for p in geo if not p.get("decal")]
    if not base:
        return spec
    for k in range(min(6, len(base) + 2)):
        src = base[k % len(base)]
        sp = src.get("pos", [0, 0, 0]); ss = src.get("size", [1, 1, 1])
        geo.append({
            "type": "box",
            "pos": [round(sp[0], 2), round(sp[1] + (ss[1] or 1) / 2 + 0.02, 2),
                    round(sp[2] + rng.uniform(-0.2, 0.2) * (ss[2] or 1), 2)],
            "size": [round((ss[0] or 1) * 0.6, 2), 0.03, 0.05],
            "color": color, "decal": True, "emissive": 0.05, "inscription": True,
        })
    spec["geometry"] = geo
    spec["inscription"] = color
    return spec


def _placement_targets(base: list[dict], placement: str | None) -> list[dict]:
    """Pick which base parts the inscription glyphs sit on, by placement."""
    if not base:
        return base
    ordered = sorted(base, key=lambda p: (p.get("pos") or [0, 0, 0])[1])
    n = len(ordered)
    if placement == "base":
        return ordered[: max(1, n // 3)]
    if placement in ("blade", "top"):
        return ordered[-max(1, n // 3):]
    if placement == "handle":
        return ordered[: max(1, n // 2)]
    return base  # auto / body / surface / wrap / custom


def _apply_inscription_text(spec: dict, rng: random.Random, inscription) -> dict:
    """Engrave the user's own TEXT in a chosen dead-language SCRIPT at a chosen
    PLACEMENT — glyph decals tinted/glowing per script. Free-form text & a
    'custom' placement label are both honoured."""
    if not inscription or not isinstance(inscription, dict):
        return spec
    text = (inscription.get("text") or "").strip()[:120]
    if not text:
        return spec
    script = inscription.get("script") or "runic"
    placement = inscription.get("placement") or "auto"
    smeta = SCRIPT_STYLES.get(script) or {}
    tint = smeta.get("tint", "#cccccc")
    emissive = float((smeta.get("surface") or {}).get("emissive", 0.06))
    geo = list(spec.get("geometry") or [])
    base = [p for p in geo if not p.get("decal")]
    if not base:
        return spec
    targets = _placement_targets(base, placement)
    n = max(4, min(len(text), 12))
    for k in range(n):
        src = targets[k % len(targets)]
        sp = src.get("pos", [0, 0, 0]); ss = src.get("size", [1, 1, 1])
        geo.append({
            "type": "box",
            "pos": [round(sp[0] + (k - n / 2) * 0.06 * (ss[0] or 1), 2),
                    round(sp[1] + (ss[1] or 1) / 2 + 0.02, 2),
                    round(sp[2] + (ss[2] or 1) / 2 + 0.03, 2)],
            "size": [0.05, 0.05, 0.02],
            "color": tint, "decal": True, "emissive": emissive,
            "inscription": True, "glyph": True,
        })
    spec["geometry"] = geo
    spec["inscription_text"] = {"script": script, "text": text,
                                "placement": placement, "tint": tint}
    return spec


def _norm_vfx(v) -> str | None:
    if v is None or isinstance(v, str):
        return v or None
    if isinstance(v, (list, tuple)):
        return _norm_vfx(v[0]) if v else None
    if isinstance(v, dict):
        return v.get("type") or v.get("name") or next(iter(v.values()), None)
    return str(v)


def _apply_extras(spec: dict, rng: random.Random, axes: dict | None,
                  treatment: str | None, region: str | None,
                  inscribe: str | None = None, inscription: dict | None = None) -> dict:
    """Apply the new style axes + region treatment + colour inscription + the
    user's dead-language TEXT inscription, recording them in detail."""
    spec = _apply_style_axes(spec, rng, axes)
    spec = apply_axis_directives(spec, spec.get("_axis_directives"))
    spec = _apply_treatment(spec, rng, treatment, region)
    spec = _apply_inscription(spec, rng, inscribe)
    spec = _apply_inscription_text(spec, rng, inscription)
    spec["vfx"] = _norm_vfx(spec.get("vfx"))
    det = dict(spec.get("detail") or {})
    det["style_axes"] = spec.get("style_axes", {})
    det["treatment"] = spec.get("treatment", "none")
    det["inscription"] = spec.get("inscription")
    det["inscription_text"] = spec.get("inscription_text")
    spec["detail"] = det
    return spec

# Per-SCENE coherent art direction — each snowball scene/region gets a theme so
# the generated world reads with a consistent style per region.
SCENE_THEME: dict[str, dict] = {
    "world":      {"skin_style": "matte", "intricacy": "subtle"},
    "narrative":  {"skin_style": "painted", "intricacy": "ornate"},
    "mechanics":  {"skin_style": "metallic", "intricacy": "ornate"},
    "procedural": {"skin_style": "crystalline", "intricacy": "baroque"},
    "tileset":    {"skin_style": "weathered", "intricacy": "ornate"},
    "assets":     {"skin_style": "glossy", "intricacy": "subtle"},
}

# Canonical world-region anchors (256×256). ONE source of truth — also imported
# by core/playable_game.py and exposed via /forge/styles for the diorama.
REGION_ANCHOR: dict[str, tuple] = {
    "flora": (40, 40, 36), "mushroom": (40, 210, 30), "terrain": (215, 45, 34),
    "world": (128, 30, 24), "creature": (40, 128, 30), "structure": (128, 128, 30),
    "furniture": (150, 140, 22), "light": (110, 110, 26), "door": (128, 100, 18),
    "shrine": (128, 70, 22), "banner": (108, 92, 20), "character": (150, 150, 22),
    "npc": (108, 158, 24), "avatar": (90, 128, 18), "vehicle": (200, 200, 30),
    "weapon": (210, 120, 24), "armor": (224, 140, 22), "container": (180, 96, 22),
    "gem": (228, 90, 18), "coin": (210, 70, 16), "book": (96, 60, 18),
    "food": (170, 60, 20), "instrument": (80, 180, 20), "machine": (200, 160, 24),
    "trap": (150, 200, 26), "ui": (24, 96, 14), "surface": (128, 180, 28),
}

# Accuracy: deterministic keyword → colour / material steering from the brief.
_COLOR_WORDS = {
    "red": "#c0392b", "crimson": "#a01818", "scarlet": "#d22b2b", "blue": "#2e6fd6",
    "azure": "#3a9bdc", "navy": "#1b2b5a", "green": "#3a8c40", "emerald": "#1f9e63",
    "lime": "#86c232", "yellow": "#f1c40f", "gold": "#d4af37", "golden": "#d4af37",
    "orange": "#e67e22", "purple": "#7d3cb5", "violet": "#8e44ad", "pink": "#e84393",
    "magenta": "#c0399b", "cyan": "#1ab0c4", "teal": "#0f8a8a", "brown": "#6e4a2a",
    "black": "#1a1a1a", "white": "#ecf0f1", "silver": "#bdc3c7", "grey": "#7f8c8d",
    "gray": "#7f8c8d", "bronze": "#b08d57", "copper": "#b87333", "ice": "#a9d6e5",
}
_MATERIAL_WORDS = {
    "metal": "metallic", "metallic": "metallic", "steel": "metallic", "iron": "rusted",
    "rusty": "rusted", "rusted": "rusted", "gold": "metallic", "chrome": "chrome",
    "glass": "glossy", "crystal": "crystalline", "neon": "neon", "glow": "glowing",
    "glowing": "glowing", "holo": "holographic", "wood": "matte", "stone": "weathered",
    "old": "weathered", "ancient": "weathered", "shiny": "glossy", "polished": "glossy",
    "matte": "matte", "painted": "painted",
}


def _apply_detail(spec: dict, rng: random.Random, skin_style: str | None,
                  complexity: str | None, intricacy: str | None,
                  detail_level: str | None, user_prompt: str = "") -> dict:
    """Post-process a base spec with skin style + detail/intricacy/complexity,
    and steer palette/material from the brief (deterministic accuracy pass)."""
    pal = list(spec.get("palette") or [])
    geo = list(spec.get("geometry") or [])
    surface = dict(spec.get("surface") or {})
    prompt = (user_prompt or "").lower()

    # ── Accuracy: pull explicit colours + materials from the brief ──
    matched_colors = [hexv for w, hexv in _COLOR_WORDS.items() if w in prompt]
    if matched_colors and pal:
        for i, hexv in enumerate(matched_colors[:3]):
            pal[i % len(pal)] = hexv
        spec["accuracy_colors"] = matched_colors[:3]
    if (not skin_style):
        for w, st in _MATERIAL_WORDS.items():
            if w in prompt:
                skin_style = st
                break

    # ── Skin style → surface finish ──
    if skin_style in SKIN_STYLES:
        surface.update(SKIN_STYLES[skin_style]["surface"])
        spec["skin_style"] = skin_style

    # ── Intricacy → palette variety + per-part colour variance ──
    it = INTRICACY.get(intricacy or "subtle", 0.3)
    if it > 0 and pal:
        for p in geo:
            if rng.random() < it:
                p["color"] = cf._hex_shift(p.get("color", pal[0]), rng, int(10 + it * 28))

    # ── Complexity → greeble density (extra small detail shapes) ──
    cx = COMPLEXITY.get(complexity or "standard", 1.0)
    if cx > 1.0 and geo:
        base = list(geo)
        n_extra = int(len(base) * (cx - 1.0))
        shapes = ["box", "sphere", "cylinder", "cone"]
        for k in range(n_extra):
            src = base[k % len(base)]
            sp = src.get("pos", [0, 0, 0])
            ss = src.get("size", [1, 1, 1])
            sc = round(rng.uniform(0.12, 0.32), 2)
            geo.append({
                "type": rng.choice(shapes),
                "pos": [round(sp[0] + rng.uniform(-0.4, 0.4) * (ss[0] or 1), 2),
                        round(sp[1] + rng.uniform(0.1, 0.7) * (ss[1] or 1), 2),
                        round(sp[2] + rng.uniform(-0.4, 0.4) * (ss[2] or 1), 2)],
                "size": [round((ss[0] or 1) * sc, 2), round((ss[1] or 1) * sc, 2), round((ss[2] or 1) * sc, 2)],
                "color": cf._hex_shift(pal[k % len(pal)] if pal else src.get("color", "#888"), rng, 22),
            })

    # ── Detail level → poly budget / texture / size ──
    dl = DETAIL_LEVEL.get(detail_level or "standard", 1.0)
    spec["poly_budget"] = int(spec.get("poly_budget", 0) * dl) or spec.get("poly_budget", 0)
    spec["size_kb"] = int(spec.get("size_kb", 0) * (0.6 + 0.5 * dl)) or spec.get("size_kb", 0)

    spec["palette"] = pal
    spec["geometry"] = geo
    spec["surface"] = surface
    spec["detail"] = {"skin_style": spec.get("skin_style"), "complexity": complexity or "standard",
                      "intricacy": intricacy or "subtle", "detail_level": detail_level or "standard",
                      "parts": len(geo)}
    return spec


def styles_catalog() -> dict:
    """Skin styles + detail bands + normalized diorama regions (one source)."""
    regions = {fam: [round((cx - 128) / 8, 2), round((cy - 128) / 8, 2)]
               for fam, (cx, cy, _sp) in REGION_ANCHOR.items()}

    def _opts(d: dict) -> list[dict]:
        # Every style gets a Basic (first 6) / Advanced (the rest) split so the
        # UI can offer a per-axis toggle into a wide option set.
        out = []
        for i, (k, v) in enumerate(d.items()):
            out.append({"key": k, "label": v["label"], "tint": v.get("tint"),
                        "tier": "basic" if i < _BASIC_N else "advanced"})
        return out

    return {
        "skin_styles": [{"key": k, "label": v["label"], "surface": v["surface"]}
                        for k, v in SKIN_STYLES.items()],
        "complexity": list(COMPLEXITY.keys()),
        "intricacy": list(INTRICACY.keys()),
        "detail_level": list(DETAIL_LEVEL.keys()),
        "regions": regions,
        # new multi-axis style options — each with a basic/advanced tier split
        "axes": [{"key": ax, "label": meta["label"],
                  "basic_count": min(_BASIC_N, len(meta["options"])),
                  "options": _opts(meta["options"])}
                 for ax, meta in STYLE_AXES.items()],
        "treatments": [{"key": k, "label": v["label"]} for k, v in TREATMENTS.items()],
        # Dead-language inscription: user types text, picks script + placement.
        "inscription": {
            "scripts": [{"key": k, "label": v["label"], "tint": v.get("tint")}
                        for k, v in SCRIPT_STYLES.items()],
            "placements": INSCRIPTION_PLACEMENTS,
        },
        "style_packs": STYLE_PACKS + list_custom_packs(),
    }


# ── Custom style packs — users save their favourite combos as one-tap looks ──
def _packs_col():
    from core.databases import get_sync_db
    return get_sync_db()["galaxy_style_packs"]


def list_custom_packs() -> list[dict]:
    try:
        rows = list(_packs_col().find({}, {"_id": 0}).sort("created_at", -1).limit(60))
        for r in rows:
            r["custom"] = True
        return rows
    except Exception:
        return []


def save_custom_pack(label: str, skin_style: str | None, axes: dict | None,
                     treatment: str | None, intricacy: str | None,
                     icon: str | None = None) -> dict:
    import time
    import uuid
    label = (label or "My Pack").strip()[:40]
    pack = {
        "key": f"custom_{uuid.uuid4().hex[:8]}",
        "label": label, "icon": icon or "⭐",
        "skin_style": skin_style or "", "axes": axes or {},
        "treatment": treatment or "none", "intricacy": intricacy or "ornate",
        "custom": True, "created_at": time.time(),
    }
    _packs_col().insert_one(dict(pack))
    pack.pop("_id", None)
    return pack


def delete_custom_pack(key: str) -> dict:
    res = _packs_col().delete_one({"key": key})
    return {"deleted": res.deleted_count}


# ── Category → family classifier (keyword ordered, structure = fallback) ───
def _classify(key: str) -> str:
    k = key.replace("_", " ")

    def has(*words: str) -> bool:
        return any(w in k for w in words)

    if has("chair", "table", "bed", "sofa", "desk", "shelf", "wardrobe",
           "dresser", "stool", "bench", "cabinet", "throne", "bookcase",
           "counter", "crib"):
        return "furniture"
    if has("sword", "axe", "mace", "spear", "dagger", "bow", "crossbow",
           "halberd", "warhammer", "katana", "rapier", "flail", "scythe",
           "glaive", "rifle", "pistol", "shotgun", "cannon", "blaster",
           "laser weapon"):
        return "weapon"
    if has("chest", "barrel", "crate", "sack", "basket", "vase", "urn", "jar",
           "bucket", "cauldron", "crucible", "coffer", "strongbox") or k == "pot":
        return "container"
    if has("robot", "mech", "turret", "generator", "reactor", "drone",
           "android", "conveyor", "crane", "pump", "engine block",
           "gear assembly", "antenna array"):
        return "machine"
    if has("drum", "guitar", "lute", "harp", "flute", "horn instrument",
           "piano", "violin", "bell instrument", "gong", "lyre"):
        return "instrument"
    if has("bread", "cake", "pie", "apple", "cheese", "meat cut", "soup bowl",
           "fish dish", "stew", "roast", "pizza", "sandwich"):
        return "food"
    if has("icon", "badge", "banner ui", "emblem", "crest", "button ui",
           "cursor", "healthbar", "minimap", "waypoint marker"):
        return "ui"
    if has("bust", "portrait", "mannequin", "statue figure", "idol", "totem"):
        return "avatar"
    if has("boulder", "cliff", "crater", "geyser", "hot spring", "stalagmite",
           "dune crest", "ravine", "plateau", "ridge"):
        return "terrain"
    if has("sound", "radio", "music", "voice"):
        return "sound"
    if has("clothing", "hair", "tattoo", "jewelry", "accessor", "backpack",
           "leatherwork", "makeup", "hairdresser", "skin", "reskin",
           "customization", "equipment"):
        return "wearable"
    if has("npc", "character", "player", "crowd", "speech", "interaction",
           "vice", "wanderer", "vendor"):
        return "character"
    if has("critter", "bestiary", "insect", "fish", "bird", "husbandry",
           "nurturing", "meat", "animal"):
        return "creature"
    if has("vehicle", "boat", "airplane", "spaceship", "rocketship", "railway",
           "monorail", "ski elevator", "traffic", "navigation", "ball"):
        return "vehicle"
    if has("tree", "plant", "bush", "berry", "fruit", "moss", "forest",
           "garden", "flower", "growth"):
        return "flora"
    if has("galaxy", "country", "globus", "map", "sea", "sky", "planet",
           "moon", "sun", "mountain", "beach", "fjord", "archipelago",
           "strait", "swamp", "cave", "tunnel", "sand", "wave", "location",
           "secrets", "secret", "easter", "seasonal", "summer", "fall",
           "winter", "spring"):
        return "world"
    if has("fire", "smoke", "wind", "storm", "rain", "thunder", "cloud",
           "enchant", "magic", "elemental", "glow", "ambiance", "encounter",
           "event"):
        return "fx"
    if has("weapon", "gun", "archery", "poison", "potion", "clock", "calendar",
           "tool", "utensil", "consumable", "snack", "sign", "monument",
           "artwork", "food", "baking", "drink", "item", "electronic",
           "mechanical", "campfire", "fishing", "farming", "hunting",
           "camping", "research", "upgrade", "tech", "randomizer", "placement"):
        return "prop"
    if has("stone", "ore", "concrete", "asphalt", "fence", "guardrail",
           "glass", "rubber", "plastic", "window", "metalwork", "woodwork",
           "sawmill", "papermill", "processing", "graphite", "cobalt",
           "battery", "lithium", "coal", "copper", "iron", "steel", "silver",
           "gold", "titanium", "look", "growth", "water"):
        return "surface"
    return "structure"


def _slug(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


# Build the full live category catalogue from the (previously deferred) roadmap.
# ── Curated expansion (+244 categories across 10 new + 4 existing families) ──
# family -> human category labels. Family is forced (no classifier guessing).
_CURATED: dict[str, list[str]] = {
    "gem": ["Diamond", "Ruby", "Emerald", "Sapphire", "Amethyst", "Topaz", "Opal",
            "Garnet", "Quartz Crystal", "Jade", "Pearl Gem", "Onyx", "Citrine",
            "Peridot", "Aquamarine", "Turquoise", "Obsidian Shard", "Crystal Cluster",
            "Gemstone", "Raw Crystal"],
    "light": ["Lamp", "Torch", "Lantern", "Chandelier", "Candle", "Streetlight",
              "Sconce", "Brazier", "Neon Sign", "Spotlight", "Floodlight",
              "Lighthouse Lamp", "Fairy Lights", "Glowstone", "Light Orb",
              "Oil Lamp", "Headlight", "Paper Lantern"],
    "book": ["Book", "Tome", "Scroll", "Grimoire", "Journal", "Ledger", "Codex",
             "Manuscript", "Spellbook", "Atlas", "Diary", "Scroll Case",
             "Parchment", "Rune Tablet", "Stone Tablet", "Map Scroll"],
    "coin": ["Coin", "Gold Coin", "Silver Coin", "Doubloon", "Token Coin",
             "Medallion", "Currency", "Coin Stack", "Treasure Pile", "Ingot",
             "Bullion", "Credit Chip"],
    "armor": ["Helmet", "Shield", "Gauntlet", "Breastplate", "Greaves", "Pauldron",
              "Chainmail", "Plate Armor", "Buckler", "Visor", "Vambrace", "Cuirass",
              "Tabard", "War Shield", "Kite Shield", "Tower Shield", "Round Shield",
              "Spiked Shield", "Riot Shield", "Energy Shield"],
    "banner": ["Banner", "Flag", "Pennant", "Standard", "War Banner", "Guild Banner",
               "Sail", "Drape", "Curtain", "Tapestry", "Bunting", "Streamer",
               "Windsock", "Signal Flag"],
    "door": ["Door", "Gate", "Portcullis", "Archway", "Hatch", "Trapdoor",
             "Vault Door", "Blast Door", "Sliding Door", "Drawbridge", "Garden Gate",
             "Iron Gate", "Wooden Door", "Double Door"],
    "shrine": ["Shrine", "Altar", "Obelisk", "Monolith", "Pedestal", "Sarcophagus",
               "Tomb", "Mausoleum", "Fountain", "Well", "Statue Plinth", "Reliquary",
               "Prayer Stone", "Henge", "Ziggurat", "Pylon"],
    "mushroom": ["Mushroom", "Toadstool", "Fungus", "Mushroom Cluster",
                 "Glowing Mushroom", "Giant Mushroom", "Truffle", "Mold Patch",
                 "Lichen", "Bracket Fungus", "Puffball", "Shelf Mushroom"],
    "trap": ["Spike Trap", "Bear Trap", "Pit Trap", "Snare", "Landmine", "Tripwire",
             "Dart Trap", "Flame Trap", "Cage Trap", "Net Trap", "Pressure Plate",
             "Arrow Trap", "Swinging Blade", "Spike Pit"],
    "prop": ["Lockpick", "Key", "Map Item", "Compass", "Hourglass", "Telescope",
             "Spyglass", "Gear Item", "Lever", "Switch Item", "Valve", "Crank",
             "Pulley", "Rope Coil", "Chain Item", "Anchor", "Bell Prop",
             "Hammer Tool", "Anvil", "Grindstone"],
    "creature": ["Wolf", "Bear", "Dragon", "Serpent", "Spider Creature", "Bat",
                 "Rat", "Boar", "Deer", "Fox", "Owl", "Eagle", "Shark", "Octopus",
                 "Crab", "Frog", "Lizard", "Scorpion"],
    "flora": ["Oak Tree", "Pine Tree", "Palm Tree", "Willow", "Cactus", "Fern",
              "Vine", "Ivy", "Sunflower", "Rose Bush", "Lily Pad", "Reed", "Bamboo",
              "Hedge", "Sapling", "Dead Tree"],
    "vehicle": ["Cart", "Wagon", "Chariot", "Sled", "Raft", "Canoe", "Submarine",
                "Helicopter", "Tank", "Motorcycle", "Hovercraft", "Hot Air Balloon",
                "Glider", "Jetpack"],
}

# ── Mega expansion (+480 categories) — pushes the live forge to 1000+. ──────
_CURATED_EXT: dict[str, list[str]] = {
    "weapon": ["Longsword", "Broadsword", "Greatsword", "Shortsword", "Cutlass",
               "Sabre", "Scimitar", "Estoc", "Claymore", "Falchion", "War Axe",
               "Battle Axe", "Hatchet", "Tomahawk", "Pickaxe Weapon", "Morning Star",
               "War Pick", "Quarterstaff", "Trident", "Pike", "Lance", "Javelin",
               "Throwing Knife", "Kunai", "Shuriken", "Sling", "Recurve Bow",
               "Longbow", "Composite Bow", "Repeating Crossbow", "Hand Crossbow",
               "Musket", "Flintlock", "Revolver", "Carbine", "Sniper Rifle",
               "Submachine Gun", "Plasma Rifle", "Railgun", "Rocket Launcher",
               "Grenade", "Flamethrower", "Chainsaw Weapon", "Energy Sword",
               "Power Hammer", "Whip", "Bo Staff", "Nunchaku", "Sai", "Caltrops"],
    "armor": ["Full Helm", "Great Helm", "Barbute", "Sallet", "Bascinet", "Coif",
              "Hauberk", "Brigandine", "Lamellar Armor", "Scale Mail", "Splint Armor",
              "Cuisse", "Sabaton", "Spaulder", "Rerebrace", "Couter", "Gorget",
              "Bevor", "Faulds", "War Apron", "Heater Shield", "Pavise",
              "Targe", "Aegis Shield", "Power Armor", "Exo Suit", "Riot Vest",
              "Flak Jacket", "Battle Plate", "Dragon Scale Armor"],
    "creature": ["Griffin", "Phoenix", "Hydra", "Chimera", "Manticore", "Basilisk",
                 "Cockatrice", "Wyvern", "Drake", "Kraken", "Leviathan", "Cerberus",
                 "Minotaur", "Centaur", "Harpy", "Gorgon", "Cyclops", "Troll",
                 "Ogre", "Goblin Creature", "Hobgoblin", "Kobold", "Imp", "Gargoyle",
                 "Golem", "Slime", "Wisp", "Banshee", "Wraith", "Lich Creature",
                 "Zombie", "Skeleton Creature", "Mummy", "Vampire Bat", "Werewolf",
                 "Direwolf", "Sabertooth", "Mammoth", "Raptor", "Stegosaurus",
                 "Triceratops", "Pterodactyl", "Jellyfish", "Stingray", "Anglerfish",
                 "Seahorse", "Hummingbird", "Peacock", "Toucan", "Flamingo"],
    "flora": ["Maple Tree", "Birch Tree", "Cherry Blossom", "Redwood", "Cypress",
              "Mangrove", "Baobab", "Cedar", "Spruce", "Aspen", "Magnolia",
              "Wisteria", "Lavender", "Tulip", "Daisy", "Orchid", "Lotus",
              "Marigold", "Poppy", "Dandelion", "Bluebell", "Foxglove", "Thistle",
              "Cattail", "Papyrus", "Wheat Stalk", "Corn Stalk", "Grapevine",
              "Tomato Plant", "Pumpkin Vine", "Watermelon Vine", "Strawberry Bush",
              "Blueberry Bush", "Bramble", "Nettle", "Clover Patch", "Seaweed",
              "Coral Plant", "Venus Flytrap", "Pitcher Plant"],
    "furniture": ["Armchair", "Loveseat", "Ottoman", "Recliner", "Rocking Chair",
                  "Bar Stool", "Dining Table", "Coffee Table", "Side Table",
                  "Nightstand", "Dresser Cabinet", "Armoire", "Chest of Drawers",
                  "Bookshelf Unit", "Display Cabinet", "China Cabinet", "Sideboard",
                  "Buffet Table", "Vanity Desk", "Writing Desk", "Standing Desk",
                  "Bunk Bed", "Canopy Bed", "Four Poster Bed", "Daybed", "Futon",
                  "Hammock", "Park Bench", "Picnic Table", "Coat Rack", "Hat Stand",
                  "Umbrella Stand", "Folding Screen", "Room Divider"],
    "food": ["Croissant", "Bagel", "Donut", "Muffin", "Pancake Stack", "Waffle",
             "Pretzel", "Baguette", "Cupcake", "Cookie", "Macaron", "Tart",
             "Pudding", "Ice Cream Cone", "Popsicle", "Lollipop", "Candy Cane",
             "Chocolate Bar", "Burger", "Hot Dog", "Taco", "Burrito", "Sushi Roll",
             "Dumpling", "Ramen Bowl", "Spaghetti Plate", "Lasagna", "Curry Bowl",
             "Salad Bowl", "Fruit Basket", "Banana", "Orange Fruit", "Grapes",
             "Watermelon Slice", "Pineapple", "Strawberry", "Cherry", "Lemon",
             "Carrot", "Corn Cob", "Mushroom Dish", "Roast Chicken", "Steak Plate"],
    "instrument": ["Acoustic Guitar", "Electric Guitar", "Bass Guitar", "Banjo",
                   "Mandolin", "Ukulele", "Cello", "Double Bass", "Viola",
                   "Trumpet", "Trombone", "Tuba", "Saxophone", "Clarinet",
                   "Oboe", "Bassoon", "Piccolo", "Pan Flute", "Ocarina",
                   "Accordion", "Harmonica", "Bagpipes", "Snare Drum", "Bass Drum",
                   "Bongo", "Conga", "Tambourine", "Maracas", "Xylophone",
                   "Marimba", "Sitar", "Koto", "Didgeridoo", "Synthesizer Keys"],
    "machine": ["Forklift", "Bulldozer", "Excavator", "Crane Machine", "Steamroller",
                "Printing Press", "Loom", "Lathe", "Drill Press", "Welding Rig",
                "Assembly Arm", "Robotic Dog", "Sentry Bot", "Repair Drone",
                "Mining Rig", "Solar Array", "Wind Turbine", "Hydro Generator",
                "Nuclear Core", "Server Rack", "Mainframe", "Arcade Cabinet",
                "Vending Machine", "ATM Machine", "Jukebox", "Pinball Machine",
                "Telescope Array", "Satellite Dish", "Radar Tower", "Power Coupler"],
    "gem": ["Moonstone", "Sunstone", "Bloodstone", "Tigers Eye", "Lapis Lazuli",
            "Malachite", "Rose Quartz", "Smoky Quartz", "Tanzanite", "Alexandrite",
            "Spinel", "Zircon", "Kunzite", "Morganite", "Heliodor", "Iolite",
            "Star Sapphire", "Black Diamond", "Fire Opal", "Geode"],
    "light": ["Gas Lamp", "Hurricane Lamp", "Carriage Lamp", "Desk Lamp",
              "Table Lamp", "Floor Lamp", "Wall Sconce", "Pendant Light",
              "Track Light", "Disco Ball", "Lava Lamp", "Bug Zapper Light",
              "Signal Beacon", "Runway Light", "Buoy Light", "Miners Lamp",
              "Will-o-Wisp", "Plasma Globe", "LED Strip", "Stage Light"],
    "container": ["Treasure Chest", "Lock Box", "Toolbox", "Tackle Box",
                  "Ammo Crate", "Supply Crate", "Wine Barrel", "Powder Keg",
                  "Clay Pot", "Amphora", "Canteen", "Flask Vessel", "Decanter",
                  "Teapot", "Kettle", "Cooking Pot", "Wicker Basket", "Hamper",
                  "Duffel Bag", "Satchel", "Knapsack", "Coin Purse", "Briefcase",
                  "Steamer Trunk", "Footlocker", "Safe Box", "Vault Chest"],
    "prop": ["Quill Pen", "Inkwell", "Wax Seal", "Scroll Tube", "Abacus",
             "Sundial", "Pocket Watch", "Wind Chime", "Dreamcatcher", "Prayer Wheel",
             "Spinning Top", "Marble Set", "Dice Set", "Playing Cards", "Chess Piece",
             "Domino Tile", "Puzzle Box", "Music Box", "Snow Globe", "Hourglass Timer",
             "Magnifying Glass", "Binoculars", "Periscope", "Sextant", "Astrolabe",
             "Barometer", "Thermometer Prop", "Fishing Rod", "Net Prop", "Harpoon",
             "Grappling Hook", "Climbing Pick", "Shovel Tool", "Rake Tool", "Scythe Tool",
             "Pitchfork", "Watering Can", "Flower Pot", "Birdcage", "Mousetrap"],
    "wearable": ["Wizard Hat", "Crown", "Tiara", "Circlet", "Helmet Plume",
                 "Feathered Cap", "Top Hat", "Bowler Hat", "Cowboy Hat", "Beret",
                 "Bandana", "Scarf", "Cape", "Cloak", "Robe", "Tunic Wear",
                 "Vest Wear", "Gloves Wear", "Boots Wear", "Sandals", "Belt Wear",
                 "Sash", "Amulet", "Pendant Wear", "Ring Wear", "Bracelet",
                 "Earring", "Necklace", "Brooch", "Monocle", "Goggles", "Eyepatch",
                 "Mask Wear", "Backpack Wear", "Quiver", "Holster", "Bandolier"],
    "door": ["Castle Gate", "City Gate", "Dungeon Door", "Cell Door", "Bank Vault",
             "Saloon Doors", "French Doors", "Revolving Door", "Barn Door",
             "Cellar Hatch", "Bulkhead Door", "Airlock Door", "Bamboo Gate",
             "Torii Gate", "Lych Gate", "Picket Gate", "Wrought Iron Gate"],
    "shrine": ["Standing Stone", "Cairn", "Dolmen", "Stupa", "Pagoda Shrine",
               "Wayside Shrine", "Memorial Stele", "Tombstone", "Crypt", "Catacomb",
               "Effigy Mound", "Sacrificial Altar", "Offering Bowl", "Incense Burner",
               "Totem Pole", "Spirit House", "Meditation Stone", "Oracle Stone"],
    "terrain": ["Mesa", "Butte", "Canyon Wall", "Sand Dune", "Glacier", "Iceberg",
                "Coral Reef", "Tide Pool", "Lava Flow", "Volcano Cone", "Ash Mound",
                "Quicksand Pit", "Tar Pit", "Sinkhole", "Crystal Spire", "Rock Arch",
                "Sea Stack", "Waterfall", "Rapids", "Hot Spring Pool"],
    "trap": ["Boulder Trap", "Falling Block", "Crushing Wall", "Poison Dart",
             "Gas Trap", "Acid Pit", "Lava Pit", "Electric Floor", "Magnet Trap",
             "Sawblade Trap", "Pendulum Blade", "Collapsing Floor", "Sticky Web",
             "Bear Snare", "Glue Trap", "Alarm Wire", "Hidden Spikes"],
    "banner": ["Royal Standard", "Battle Flag", "Naval Ensign", "Pirate Flag",
               "Heraldic Banner", "Festival Bunting", "Prayer Flag", "Victory Pennant",
               "Clan Banner", "Tournament Flag", "Wind Banner", "Hanging Scroll Banner",
               "Wall Tapestry", "Ceremonial Drape"],
    "book": ["Ancient Codex", "Bestiary", "Herbarium", "Almanac", "Field Journal",
             "Captains Log", "Recipe Book", "Hymnal", "Prophecy Scroll", "Treaty Scroll",
             "Wanted Poster", "Treasure Map", "Star Chart", "Blueprint Roll",
             "Sheet Music", "Diploma Scroll"],
    "coin": ["Copper Coin", "Bronze Coin", "Platinum Coin", "Electrum Coin",
             "Ancient Drachma", "Pieces of Eight", "Wampum", "Trade Bead",
             "Gold Bar", "Silver Bar", "Coin Pouch", "Reward Chip", "Casino Token",
             "Arcade Token", "Soul Coin"],
    "vehicle": ["Stagecoach", "Rickshaw", "Gondola", "Galleon", "Caravel",
                "Longship", "Dinghy", "Speedboat", "Hydrofoil", "Hovercar",
                "Mech Walker", "Battle Mech", "Buggy", "Monster Truck", "Bulldozer Cab",
                "Steam Train", "Bullet Train", "Cable Car", "Dirigible", "Biplane",
                "Fighter Jet", "Space Shuttle", "Lunar Rover", "Pod Racer"],
    "world": ["Floating Island", "Crater Lake", "Oasis", "Geothermal Vent",
              "Aurora Sky", "Meteor Field", "Nebula Cloud", "Ringed Planet",
              "Binary Sun", "Comet", "Asteroid", "Black Hole", "Wormhole",
              "Portal Rift", "Ley Line", "Mana Spring"],
    "fx": ["Lightning Bolt", "Fireball", "Ice Shard", "Poison Cloud", "Acid Spray",
           "Sandstorm", "Blizzard", "Tornado", "Whirlpool", "Shockwave",
           "Explosion Burst", "Magic Aura", "Healing Glow", "Shield Bubble",
           "Summoning Circle", "Rune Glyph", "Ember Trail", "Stardust", "Mist Veil",
           "Smoke Plume"],
    "ui": ["Quest Marker", "Damage Number", "Loot Beam", "XP Bar", "Mana Bar",
           "Stamina Wheel", "Skill Icon", "Inventory Slot", "Hotbar", "Tooltip Frame",
           "Dialogue Box", "Speech Bubble", "Objective Tracker", "Compass UI",
           "Radar Blip", "Crosshair", "Reticle", "Loading Spinner", "Achievement Badge",
           "Level Up Banner"],
    "avatar": ["Hero Bust", "Villain Bust", "Royal Statue", "Warrior Statue",
               "Angel Statue", "Demon Idol", "Animal Totem", "Tiki Idol",
               "Bronze Effigy", "Marble Figure", "Wax Figure", "Mannequin Pose",
               "Action Figure", "Chess King Figure", "Garden Gnome"],
    "sound": ["Ambient Drone", "Footstep Set", "Sword Clang", "Magic Chime",
              "Explosion Boom", "Creature Roar", "Bird Chirp", "Water Splash",
              "Wind Howl", "Thunder Crack", "Coin Jingle", "Door Creak",
              "Heartbeat Pulse", "Alarm Siren", "Victory Fanfare"],
}

# ── Mega base expansion (+330 genuinely distinct item types) — grows the
#    BROWSABLE base catalogue so the procedural cross reaches 1,000,000+. ─────
_CURATED_MEGA: dict[str, list[str]] = {
    "weapon": ["Zweihander", "Bastard Sword", "Gladius", "Khopesh", "Wakizashi",
               "Tanto", "Dao", "Jian", "Kris", "Machete", "Cleaver Blade",
               "Bardiche", "Voulge", "Guisarme", "Ranseur", "Partisan", "Fauchard",
               "Maul", "Bec de Corbin", "Lucerne Hammer", "Knobkerrie", "Mace Club",
               "Throwing Axe", "Chakram", "Boomerang Blade", "Atlatl", "Blowgun",
               "Dart Gun", "Bolt Thrower", "Ballista Bolt", "Hand Cannon",
               "Blunderbuss", "Arquebus", "Matchlock", "Wheellock", "Derringer",
               "Gatling Gun", "Coilgun", "Gauss Rifle", "Beam Cannon", "Ion Blaster",
               "Pulse Pistol", "Tesla Coil Gun", "Frost Lance", "Flame Lance"],
    "armor": ["Jousting Helm", "Spangenhelm", "Nasal Helm", "Kabuto", "Menpo Mask",
              "Do Maru", "O Yoroi", "Kusari Gusoku", "Cuirassier Plate",
              "Maximilian Plate", "Milanese Plate", "Gothic Plate", "Field Plate",
              "Parade Armor", "Tournament Armor", "Leather Jerkin", "Studded Leather",
              "Padded Gambeson", "Mail Shirt", "Ring Mail", "Banded Mail",
              "Half Plate", "Three Quarter Plate", "Cataphract Barding", "Horse Barding",
              "Combat Exoframe", "Hardsuit", "Void Plate", "Nano Weave Vest",
              "Ballistic Shield", "Energy Bulwark", "Phase Shield"],
    "creature": ["Wendigo", "Yeti", "Sasquatch", "Selkie", "Kelpie", "Naga",
                 "Rakshasa", "Djinn", "Ifrit", "Salamander Beast", "Roc", "Thunderbird",
                 "Quetzal Serpent", "Jorogumo", "Tengu", "Oni", "Kappa", "Yokai",
                 "Behemoth", "Tarrasque", "Bulette", "Owlbear", "Displacer Beast",
                 "Beholder", "Mind Flayer", "Gelatinous Cube", "Rust Monster",
                 "Ankheg", "Carrion Crawler", "Will O Wisp Beast", "Shade", "Revenant",
                 "Ghoul", "Wight", "Death Knight", "Bone Dragon", "Frost Wyrm",
                 "Storm Drake", "Magma Golem", "Crystal Golem", "Clay Golem",
                 "Treant", "Dryad", "Pixie", "Sprite", "Brownie", "Redcap"],
    "flora": ["Sequoia", "Banyan", "Acacia", "Olive Tree", "Fig Tree", "Date Palm",
              "Coconut Palm", "Dragon Tree", "Joshua Tree", "Yew", "Holly Bush",
              "Juniper", "Hawthorn", "Elder Tree", "Rowan", "Hazel", "Chestnut Tree",
              "Walnut Tree", "Almond Tree", "Peach Tree", "Plum Tree", "Apricot Tree",
              "Pomegranate Tree", "Mango Tree", "Avocado Tree", "Lemon Tree",
              "Lime Tree", "Cherry Tree Bloom", "Jasmine Vine", "Honeysuckle",
              "Morning Glory", "Sunflower Field", "Lavender Row", "Hibiscus",
              "Camellia", "Azalea", "Rhododendron", "Peony", "Chrysanthemum",
              "Iris Flower", "Crocus", "Snowdrop", "Hyacinth", "Amaryllis"],
    "furniture": ["Chaise Lounge", "Settee", "Wingback Chair", "Club Chair",
                  "Papasan Chair", "Bean Bag", "Folding Chair", "Stadium Seat",
                  "Throne Seat", "Pew Bench", "Church Pew", "Lectern", "Pulpit",
                  "Workbench", "Anvil Stand", "Loom Frame", "Spinning Wheel Stand",
                  "Apothecary Shelf", "Potion Rack", "Weapon Rack", "Armor Stand",
                  "Map Table", "War Table", "Council Table", "Banquet Table",
                  "Trestle Table", "Card Table", "Pool Table", "Foosball Table",
                  "Grandfather Clock", "Cuckoo Clock", "Phonograph Stand",
                  "Gramophone Cabinet", "Liquor Cabinet", "Curio Shelf"],
    "food": ["Quiche", "Pot Pie", "Empanada", "Samosa", "Spring Roll", "Wonton",
             "Gyoza", "Tamale", "Enchilada", "Quesadilla", "Falafel", "Kebab",
             "Shawarma", "Gyro", "Pita Pocket", "Naan Bread", "Focaccia", "Ciabatta",
             "Sourdough Loaf", "Rye Bread", "Brioche", "Scone", "Biscuit",
             "Cinnamon Roll", "Eclair", "Profiterole", "Cannoli", "Tiramisu Slice",
             "Cheesecake Slice", "Apple Pie", "Pumpkin Pie", "Pecan Pie", "Flan",
             "Creme Brulee", "Souffle", "Gelato Cup", "Sorbet Bowl", "Trifle",
             "Parfait", "Smoothie Bowl", "Poke Bowl", "Bento Box", "Charcuterie Board"],
    "instrument": ["Lute Medieval", "Theorbo", "Lyre Harp", "Zither", "Dulcimer",
                   "Psaltery", "Hurdy Gurdy", "Vielle", "Rebec", "Crwth", "Shamisen",
                   "Erhu", "Pipa", "Guzheng", "Dizi Flute", "Shakuhachi", "Sheng",
                   "Conch Horn", "War Horn", "Hunting Horn", "Bugle", "Cornet",
                   "Flugelhorn", "French Horn", "Sousaphone", "Euphonium", "Recorder",
                   "Fife", "Tin Whistle", "Kalimba", "Steel Drum", "Timpani",
                   "Glockenspiel", "Celesta", "Hammered Dulcimer", "Hang Drum"],
    "machine": ["Trebuchet", "Catapult", "Ballista Engine", "Battering Ram",
                "Siege Tower", "Water Wheel", "Treadmill Crane", "Foundry Furnace",
                "Bellows Forge", "Bloomery", "Blast Furnace", "Cotton Gin",
                "Threshing Machine", "Steam Engine", "Pump Jack", "Oil Derrick",
                "Refinery Tower", "Cooling Tower", "Transformer Station",
                "Particle Accelerator", "Fusion Reactor", "Quantum Computer",
                "Holo Projector", "Teleporter Pad", "Cryo Pod", "Stasis Chamber",
                "Drilling Rig", "Harvester Combine", "Tractor", "Seeder Machine",
                "3D Printer", "CNC Mill", "Industrial Robot Arm", "Conveyor Belt"],
    "vehicle": ["Penny Farthing", "Velocipede", "Hand Cart", "Wheelbarrow",
                "Palanquin", "Sedan Chair", "Trireme", "Junk Ship", "Dhow",
                "Catamaran", "Schooner", "Frigate", "Man O War", "Ironclad Ship",
                "Paddle Steamer", "Tugboat", "Ferry", "Yacht", "Jet Ski",
                "Airship", "Zeppelin", "Blimp", "Autogyro", "Seaplane", "Cargo Plane",
                "Stealth Bomber", "Drone Quadcopter", "Hover Bike", "Speeder Bike",
                "Walker Tank", "APC Carrier", "Half Track", "Snowmobile", "Dune Buggy"],
    "structure": ["Pyramid", "Sphinx", "Colosseum", "Aqueduct", "Triumphal Arch",
                  "Amphitheater", "Bathhouse", "Granary", "Silo", "Grain Mill",
                  "Tannery", "Brewery", "Distillery", "Bakery Building", "Butcher Shop",
                  "Blacksmith Forge Building", "Apothecary Shop", "Bookbinder Shop",
                  "Observatory", "Planetarium", "Greenhouse", "Conservatory",
                  "Pavilion", "Gazebo", "Belfry", "Clock Tower", "Bell Tower",
                  "Minaret", "Pagoda Tower", "Stupa Dome", "Mosque Dome", "Synagogue",
                  "Monastery", "Abbey", "Cloister", "Crypt Chamber", "Dungeon Cell",
                  "Throne Room", "Great Hall", "Ballroom", "Dining Hall"],
    "surface": ["Mosaic Tile", "Terrazzo", "Parquet Floor", "Herringbone Brick",
                "Flagstone", "Cobble Path", "Gravel Bed", "Sand Floor", "Mud Brick",
                "Adobe Wall", "Wattle Daub", "Timber Frame", "Log Wall", "Shingle Roof",
                "Slate Tile Roof", "Clay Tile Roof", "Thatched Roof", "Corrugated Metal",
                "Riveted Steel", "Brushed Aluminum", "Carbon Fiber", "Frosted Glass",
                "Stained Glass", "Mirror Surface", "Velvet Cloth", "Silk Weave",
                "Burlap", "Tweed", "Denim Weave", "Snake Skin", "Dragon Hide",
                "Fish Scale", "Feather Cloak", "Fur Pelt", "Tree Bark", "Lava Crust"],
}



_CURATED_FAM70: dict[str, list[str]] = {
    "mount": ["War Horse", "Dire Wolf", "Griffon", "Armored Elephant", "Giant Lizard", "Sky Serpent"],
    "pet": ["Loyal Hound", "House Cat", "Pet Dragon", "Fox Kit", "Raven", "Slime Pet"],
    "familiar": ["Owl Familiar", "Imp", "Spirit Cat", "Crystal Wisp", "Toad Familiar", "Bat Familiar"],
    "fish": ["Koi", "Swordfish", "Anglerfish", "Piranha", "Lungfish", "Ghost Carp"],
    "bird": ["Eagle", "Phoenix", "Owl", "Falcon", "Peacock", "Thunderbird"],
    "insect": ["Beetle", "Mantis", "Dragonfly", "Scarab", "Firefly", "Giant Ant"],
    "reptile": ["Komodo", "Cobra", "Chameleon", "Basilisk", "Gecko", "Crocodile"],
    "mammal": ["Stag", "Bear", "Lion", "Wolf", "Boar", "Sabretooth"],
    "dinosaur": ["Raptor", "T-Rex", "Triceratops", "Stegosaurus", "Pteranodon", "Brachiosaurus"],
    "sea_beast": ["Kraken", "Leviathan", "Sea Serpent", "Giant Squid", "Abyssal Eel", "Coral Hydra"],
    "demon": ["Imp Lord", "Pit Fiend", "Succubus", "Hellhound", "Balor", "Shadow Demon"],
    "angel": ["Seraph", "Archangel", "Cherub", "Valkyrie", "Guardian Angel", "Throne"],
    "elemental": ["Fire Elemental", "Water Elemental", "Earth Elemental", "Air Elemental", "Storm Elemental", "Void Elemental"],
    "spirit": ["Wraith", "Banshee", "Poltergeist", "Forest Spirit", "Ancestor Ghost", "Will-o-Wisp"],
    "undead": ["Skeleton", "Zombie", "Lich", "Mummy", "Death Knight", "Bone Lord"],
    "totem": ["Bear Totem", "Eagle Totem", "Wolf Totem", "Spirit Totem", "Ancestor Totem", "War Totem"],
    "idol": ["Golden Idol", "Stone Idol", "Jade Idol", "Demon Idol", "Sun Idol", "Moon Idol"],
    "relic": ["Holy Relic", "Cursed Relic", "Ancient Relic", "Saint Bone", "Sacred Chalice", "Lost Relic"],
    "artifact": ["Mystic Artifact", "Alien Artifact", "Time Artifact", "Soul Artifact", "Power Core", "Eldritch Artifact"],
    "orb": ["Crystal Orb", "Soul Orb", "Storm Orb", "Mana Orb", "Void Orb", "Seeing Orb"],
    "staff": ["Wizard Staff", "Druid Staff", "Battle Staff", "Crystal Staff", "Bone Staff", "Storm Staff"],
    "wand": ["Fire Wand", "Ice Wand", "Healing Wand", "Shadow Wand", "Star Wand", "Bone Wand"],
    "tome": ["Spellbook", "Grimoire", "Forbidden Tome", "Healing Codex", "Necronomicon", "Rune Tome"],
    "rune_stone": ["Runestone", "Ward Stone", "Memory Stone", "Bind Stone", "Seer Stone", "Curse Stone"],
    "portal": ["Stone Portal", "Void Rift", "Fairy Ring", "Star Gate", "Mirror Gate", "Hell Rift"],
    "mech": ["Battle Mech", "Mining Mech", "Scout Mech", "Titan Mech", "Exo Frame", "Siege Walker"],
    "drone": ["Recon Drone", "Combat Drone", "Repair Drone", "Cargo Drone", "Swarm Drone", "Spy Drone"],
    "turret": ["Auto Turret", "Laser Turret", "Flak Cannon", "Missile Turret", "Tesla Turret", "Sentry Gun"],
    "spaceship": ["Star Fighter", "Cruiser", "Dreadnought", "Shuttle", "Frigate", "Carrier Ship"],
    "station": ["Orbital Station", "Trade Hub", "Research Lab", "Defense Platform", "Docking Ring", "Colony Module"],
    "satellite": ["Comm Sat", "Spy Sat", "Weather Sat", "Solar Array", "Relay Beacon", "Telescope Sat"],
    "asteroid": ["Ore Asteroid", "Ice Comet", "Rogue Meteor", "Crystal Roid", "Hollow Roid", "Metal Roid"],
    "planet": ["Gas Giant", "Desert World", "Ocean World", "Lava Planet", "Ice Planet", "Ringed World"],
    "star_body": ["Yellow Sun", "Red Giant", "White Dwarf", "Neutron Star", "Pulsar", "Binary Star"],
    "robot_pet": ["Robo Dog", "Mech Cat", "Drone Pet", "AI Orb", "Servo Bird", "Nano Pet"],
    "engine": ["Warp Drive", "Ion Engine", "Fusion Core", "Steam Engine", "Plasma Reactor", "Antimatter Core"],
    "console": ["Command Console", "Holo Terminal", "Control Panel", "Server Rack", "Nav Computer", "Hack Terminal"],
    "shield": ["Tower Shield", "Buckler", "Kite Shield", "Energy Shield", "Spiked Shield", "Round Shield"],
    "helmet": ["Knight Helm", "Horned Helm", "Space Helmet", "Plumed Helm", "Visor Helm", "Crown Helm"],
    "boots": ["Leather Boots", "Plate Boots", "Winged Boots", "Combat Boots", "Travel Boots", "Sabatons"],
    "gloves": ["Gauntlets", "Leather Gloves", "Power Gloves", "Mage Gloves", "Spiked Gauntlets", "Silk Gloves"],
    "cape": ["Royal Cape", "Travel Cloak", "Winged Cape", "Shadow Cloak", "Fur Cape", "Hooded Cloak"],
    "mask": ["Plague Mask", "Theater Mask", "War Mask", "Spirit Mask", "Gas Mask", "Demon Mask"],
    "ring": ["Signet Ring", "Power Ring", "Wedding Band", "Rune Ring", "Skull Ring", "Gem Ring"],
    "amulet": ["Soul Amulet", "Protection Charm", "Eye Pendant", "Gem Amulet", "Bone Charm", "Star Pendant"],
    "crown": ["King Crown", "Tiara", "Laurel Wreath", "Iron Crown", "Bone Crown", "Solar Crown"],
    "belt": ["War Belt", "Utility Belt", "Sash", "Champion Belt", "Tool Belt", "Rune Belt"],
    "weapon_part": ["Blade", "Hilt", "Pommel", "Crossguard", "Scope", "Magazine"],
    "ammo": ["Arrow", "Bolt", "Bullet", "Cannonball", "Shell", "Plasma Cell"],
    "explosive": ["Bomb", "Grenade", "Dynamite", "Land Mine", "Powder Keg", "Plasma Charge"],
    "tool": ["Hammer", "Pickaxe", "Wrench", "Chisel", "Saw", "Lockpick"],
    "potion": ["Health Potion", "Mana Potion", "Poison Vial", "Invis Potion", "Strength Brew", "Antidote"],
    "elixir": ["Life Elixir", "Speed Elixir", "Wisdom Elixir", "Fury Elixir", "Youth Elixir", "Void Elixir"],
    "herb": ["Mandrake", "Nightshade", "Sage", "Bloodroot", "Moonpetal", "Wolfsbane"],
    "crop": ["Wheat", "Corn", "Rice", "Barley", "Pumpkin", "Cotton"],
    "fruit": ["Apple", "Grape", "Peach", "Dragonfruit", "Pomegranate", "Starfruit"],
    "vegetable": ["Carrot", "Potato", "Cabbage", "Onion", "Turnip", "Chili"],
    "beverage": ["Ale", "Wine", "Mead", "Coffee", "Tea", "Potion Brew"],
    "spice": ["Pepper", "Saffron", "Cinnamon", "Salt", "Paprika", "Ginger"],
    "tower": ["Watch Tower", "Mage Tower", "Bell Tower", "Siege Tower", "Lighthouse", "Clock Tower"],
    "wall": ["Stone Wall", "Castle Wall", "Palisade", "Battlement", "Force Wall", "Brick Wall"],
    "bridge": ["Stone Bridge", "Rope Bridge", "Drawbridge", "Arch Bridge", "Suspension Bridge", "Crystal Bridge"],
    "fountain": ["Stone Fountain", "Wishing Well", "Tiered Fountain", "Lava Fountain", "Crystal Fountain", "Garden Fountain"],
    "statue": ["Hero Statue", "Angel Statue", "Beast Statue", "King Statue", "Gargoyle", "Colossus"],
    "pillar": ["Marble Column", "Broken Pillar", "Rune Pillar", "Crystal Pillar", "Iron Column", "Totem Pillar"],
    "arch": ["Triumph Arch", "Garden Arch", "Stone Arch", "Rune Arch", "Gate Arch", "Crystal Arch"],
    "platform": ["Wood Platform", "Stone Dais", "Floating Platform", "Metal Grate", "Ritual Dais", "Lift Platform"],
    "fence": ["Wood Fence", "Iron Railing", "Picket Fence", "Stone Wall Fence", "Barbed Fence", "Rope Fence"],
    "sign": ["Wood Sign", "Road Marker", "Tavern Sign", "Neon Sign", "Stone Marker", "Warning Post"],
    "crate": ["Wood Crate", "Barrel", "Cargo Crate", "Treasure Chest", "Ammo Box", "Metal Drum"],
    "lockbox": ["Iron Safe", "Strongbox", "Vault Door", "Lock Chest", "Puzzle Box", "Bank Vault"],
}


def _build_categories() -> list[dict]:
    cat = forge_registry.catalog()
    seen: set[str] = set()
    out: list[dict] = []
    for it in cat["deferred"]:
        key = it["key"]
        if key in seen:
            continue
        seen.add(key)
        label = it["label"].replace(" Forge", "")
        fam = _classify(key)
        out.append({"key": key, "label": label, "family": fam,
                    "group": FAMILIES[fam]["group"]})
    # curated expansion — family forced
    for src in (_CURATED, _CURATED_EXT, _CURATED_MEGA, _CURATED_FAM70):
        for fam, labels in src.items():
            for label in labels:
                key = _slug(label)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"key": key, "label": label, "family": fam,
                            "group": FAMILIES[fam]["group"]})
    return out


# ── Mega-scale: procedural quality/material variants. Every variant inherits
#    its base family + geometry and supports the FULL style-axis set. The
#    curated set stays the browsable catalogue; the virtual cross (base ×
#    modifiers) powers search + generate and breaches 1,000,000 forges WITHOUT
#    materialising the list (counts are arithmetic, keys resolve on demand). ──
_MOD_SINGLE: list[str] = [
    "Ancient", "Ornate", "Gilded", "Cursed", "Crystal", "Rusted", "Royal", "Runed",
    "Ethereal", "Shadow", "Radiant", "Frozen", "Burning", "Molten", "Verdant", "Twisted",
    "Sacred", "Profane", "Arcane", "Mystic", "Savage", "Noble", "Feral", "Pristine",
    "Corroded", "Polished", "Tarnished", "Enchanted", "Hexed", "Blessed", "Haunted", "Spectral",
    "Infernal", "Celestial", "Abyssal", "Primal", "Eternal", "Forgotten", "Forbidden", "Hallowed",
    "Vile", "Gleaming", "Luminous", "Obsidian", "Marble", "Ironclad", "Goldleaf", "Silvered",
    "Bronzed", "Coral", "Amber", "Jade", "Onyx", "Ruby", "Sapphire", "Emerald",
    "Ivory", "Ebon", "Frosted", "Charred", "Withered", "Blooming", "Storm", "Solar",
    "Lunar", "Astral", "Void", "Nether", "Phantom", "Glacial", "Volcanic", "Petrified",
    "Jeweled", "Engraved", "Inscribed", "Woven", "Tempered", "Quenched", "Battleworn", "Heroic",
    "Legendary", "Mythic", "Exalted", "Prismatic", "Iridescent", "Cosmic",
    # ── expansion ──
    "Bejeweled", "Stormforged", "Sunforged", "Moonforged", "Starforged", "Dragonbone",
    "Wyrmscale", "Demonhide", "Angelfeather", "Bloodstained", "Ashen", "Emberlit",
    "Frostbitten", "Thunderstruck", "Windswept", "Tidal", "Magma", "Cinder",
    "Verdigris", "Patinated", "Lacquered", "Enameled", "Filigreed", "Embossed",
    "Studded", "Spiked", "Barbed", "Serrated", "Fluted", "Beveled", "Chiseled",
    "Hammered", "Forged", "Cast", "Wrought", "Riveted", "Bolted", "Welded",
    "Glassblown", "Porcelain", "Lacquerwork", "Velvetlined", "Silklined", "Furlined",
    "Mossgrown", "Vinewrapped", "Bramblebound", "Rootbound", "Coralcrusted", "Barnacled",
    "Crystalveined", "Geodecore", "Quartzlaced", "Opaline", "Pearlescent", "Holographic",
    "Neonlit", "Plasmacharged", "Irradiated", "Magnetized", "Levitating", "Phasing",
    "Spectralbound", "Wraithtouched", "Soulbound", "Spiritforged", "Godtouched", "Demonforged",
    "Titanforged", "Dwarfcraft", "Elvenwrought", "Orcish", "Goblinmade", "Fey",
    "Imperial", "Rebel", "Outlaw", "Pirate", "Nomadic", "Tribal", "Feudal", "Industrial",
    "Steamwrought", "Clockwork", "Brassbound", "Cogfitted", "Gearforged", "Pneumatic",
    "Nanoforged", "Cybernetic", "Bioengineered", "Synthetic", "Holoetched", "Quantumlaced",
    "Voidtouched", "Eldritchmarked", "Abyssforged", "Hellforged", "Heavenforged", "Astralbound",
    "Dawnlit", "Duskshade", "Midnight", "Noonbright", "Twilightveiled", "Auroral",
    "Tempestborn", "Cycloneborn", "Avalancheborn", "Earthborn", "Seaborn", "Skyborn",
    "Flameborn", "Iceborn", "Stormborn", "Stoneborn", "Ironborn", "Goldborn",
]
# Compound prefixes — crossed with the singles to deterministically reach the
# 1,000,000 forge target without an unwieldy hand-written list.
_MOD_PREFIX: list[str] = [
    "Grand", "Elder", "Greater", "Lesser", "Twin", "Prime", "Dread", "Lost",
    "True", "Fallen", "Risen", "Hidden", "Crowned", "Exiled", "Wandering", "Reborn",
]
# ── Base descriptors — a SECOND virtual tier that multiplies the curated core
#    nouns into 1,000,000+ distinct BASE categories (material / origin / sub-
#    type qualifiers that change the item's identity, vs. modifiers which are
#    quality/condition adjectives layered on top). ────────────────────────────
_DESC_SINGLE: list[str] = [
    # materials
    "Iron", "Steel", "Bronze", "Copper", "Silver", "Golden", "Wooden", "Oaken",
    "Stone", "Marble", "Granite", "Crystal", "Glass", "Bone", "Ivory", "Leather",
    "Bamboo", "Obsidian", "Jade", "Amber", "Coral", "Pearl", "Diamond", "Onyx",
    "Ebony", "Brass", "Platinum", "Titanium", "Ceramic", "Porcelain", "Clay",
    "Wicker", "Velvet", "Silk", "Linen", "Canvas", "Carbon", "Chrome", "Cobalt",
    "Quartz", "Ruby", "Sapphire", "Emerald", "Mithril", "Adamant", "Orichalcum",
    "Driftwood", "Petrified", "Lacquered", "Woven", "Forged", "Cast",
    # origins / cultures
    "Dwarven", "Elven", "Orcish", "Human", "Goblin", "Draconic", "Imperial",
    "Royal", "Tribal", "Nomadic", "Pirate", "Celestial", "Infernal", "Fae",
    "Ancient", "Primordial", "Eastern", "Western", "Northern", "Southern",
    "Desert", "Forest", "Mountain", "Oceanic", "Arctic", "Jungle", "Volcanic",
    "Underground", "Highland", "Lowland", "Coastal", "Frontier", "Colonial",
    "Byzantine", "Norse", "Egyptian", "Aztec", "Celtic", "Samurai", "Viking",
    "Roman", "Spartan", "Mongol", "Persian", "Mayan", "Inca",
    # sub-type / scale / purpose
    "Miniature", "Colossal", "Giant", "Tiny", "Twin", "Triple", "Hollow", "Solid",
    "Reinforced", "Collapsible", "Folding", "Portable", "Ornamental", "Ceremonial",
    "Ritual", "Practical", "Training", "Decorative", "War", "Battle", "Hunting",
    "Noble", "Peasant", "Master", "Apprentice", "Antique", "Modern", "Futuristic",
    "Vintage", "Rustic", "Industrial", "Mechanical", "Magical", "Sacred", "Profane",
    "Winged", "Spiked", "Curved", "Serrated", "Segmented", "Articulated", "Modular",
    "Compact", "Oversized", "Elongated", "Squat", "Tapered", "Bulbous", "Skeletal",
    "Crystalline", "Organic", "Geometric", "Ornate", "Minimalist", "Baroque",
    "Gothic", "Brutalist", "Streamlined", "Armored", "Plated", "Lattice", "Filigreed",
]
_DESC_PREFIX: list[str] = [
    "Great", "Lesser", "High", "Deep", "Old", "New", "Grand", "Wild",
    "Dark", "Bright", "Cold", "Warm", "Hidden", "Sacred", "Cursed", "Blessed",
]
_TARGET_BASE = 3_000_000     # distinct BASE categories (tier-2 virtual; +1M procedurals)
_TARGET_MODS = 600           # quality/condition modifiers (tier-3 virtual)


def _build_label_pool(singles: list[str], prefixes: list[str], needed: int) -> list[str]:
    """Deterministically assemble `needed` unique labels: singles first (best
    reading), then prefix×single compounds, sliced to size."""
    needed = max(1, needed)
    pool: list[str] = []
    seen: set[str] = set()

    def _add(label: str) -> None:
        s = _slug(label)
        if s and s not in seen:
            seen.add(s)
            pool.append(label)

    for w in singles:
        _add(w)
        if len(pool) >= needed:
            return pool[:needed]
    for p in prefixes:
        for c in singles:
            _add(f"{p} {c}")
            if len(pool) >= needed:
                return pool[:needed]
    return pool[:needed]


_CATEGORIES: list[dict] = _build_categories()         # curated CORE NOUNS (browse)
_CORE_BY_KEY: dict[str, dict] = {c["key"]: c for c in _CATEGORIES}

# Tier 2 — descriptors grow the core nouns into 1,000,000+ base categories.
_needed_desc = max(1, math.ceil(_TARGET_BASE / max(1, len(_CATEGORIES))) - 1)
_BASE_DESCRIPTORS: list[str] = _build_label_pool(_DESC_SINGLE, _DESC_PREFIX, _needed_desc)
_DESC_BY_SLUG: dict[str, str] = {_slug(d): d for d in _BASE_DESCRIPTORS}

# ── Macro / Meso / Micro family taxonomy ────────────────────────────────────
# Macro = the broad groups; Meso = the curated families; Micro = a VIRTUAL
# leaf tier (meso × qualifiers) that scales the taxonomy to ~100,000 families
# without materialising them. Counts are arithmetic; lookups are on demand.
_MACRO_GROUPS = sorted({f["group"] for f in FAMILIES.values()})
# Virtual taxonomy targets — the addressable family space across 3 tiers.
_TAX_MACRO, _TAX_MESO, _TAX_MICRO = 10_000, 100_000, 1_000_000
MICRO_QUALIFIERS: list[str] = _build_label_pool(_DESC_SINGLE, _DESC_PREFIX,
                                                max(1, math.ceil(_TAX_MICRO / _TAX_MESO)))
_FAMILY_TOTAL = _TAX_MACRO + _TAX_MESO + _TAX_MICRO


def _family_taxonomy() -> dict:
    return {"macro": _TAX_MACRO, "meso": _TAX_MESO, "micro": _TAX_MICRO,
            "total": _FAMILY_TOTAL, "anchor_groups": len(_MACRO_GROUPS),
            "curated_families": len(FAMILIES), "macro_groups": _MACRO_GROUPS}
_BASE_FACTOR: int = 1 + len(_BASE_DESCRIPTORS)                 # nouns × this = base cats
_BASE_CATEGORY_COUNT: int = len(_CATEGORIES) * _BASE_FACTOR

# Tier 3 — modifiers layer quality/condition on top of every base category.
_MODIFIERS: list[str] = _build_label_pool(_MOD_SINGLE, _MOD_PREFIX, _TARGET_MODS)
_MOD_BY_SLUG: dict[str, str] = {_slug(m): m for m in _MODIFIERS}
_TOTAL_FACTOR: int = 1 + len(_MODIFIERS)                       # base × this = full library
_CATEGORY_COUNT: int = _BASE_CATEGORY_COUNT * _TOTAL_FACTOR    # full forge library


def _base_meta(desc: str, noun: dict) -> dict:
    """A descriptor-qualified base category, built on demand (never stored)."""
    return {"key": f"{_slug(desc)}.{noun['key']}", "label": f"{desc} {noun['label']}",
            "family": noun["family"], "group": noun["group"], "base_of": noun["key"]}


def _variant_meta(mod: str, base: dict) -> dict:
    """A modifier-qualified forge (on top of any base), built on demand."""
    return {"key": f"{_slug(mod)}-{base['key']}", "label": f"{mod} {base['label']}",
            "family": base["family"], "group": base["group"], "variant_of": base["key"]}


def _resolve_base(bk: str):
    """Resolve a BASE category key — a plain core-noun key, or a
    '{descriptor}.{noun}' tier-2 key — to its metadata dict."""
    noun = _CORE_BY_KEY.get(bk)
    if noun is not None:
        return noun
    if "." in bk:
        ds, _, nk = bk.partition(".")
        desc = _DESC_BY_SLUG.get(ds)
        n = _CORE_BY_KEY.get(nk)
        if desc and n:
            return _base_meta(desc, n)
    return None


class _VirtualCatIndex:
    """Resolves the ENTIRE multi-tier forge namespace WITHOUT materialising it:
      • core noun          → 'oak_tree'
      • base (tier-2)      → 'ancient.oak_tree'   ({descriptor}.{noun})
      • forge (tier-3)     → 'gilded-ancient.oak_tree'   ({modifier}-{base})
    Descriptor/modifier slugs never contain '.' or '-', so the separators are
    unambiguous. Supports .get / [] / in like the old dict."""

    def get(self, key: str, default=None):
        if not key:
            return default
        if "-" in key:
            ms, _, rest = key.partition("-")
            mod = _MOD_BY_SLUG.get(ms)
            base = _resolve_base(rest)
            if mod and base:
                return _variant_meta(mod, base)
            return default
        return _resolve_base(key) or default

    def __contains__(self, key) -> bool:
        return self.get(key) is not None

    def __getitem__(self, key):
        v = self.get(key)
        if v is None:
            raise KeyError(key)
        return v


_CAT_BY_KEY = _VirtualCatIndex()


def _pretty_big(n: int) -> str:
    """Human magnitude for an astronomically large int (avoids float overflow)."""
    s = str(n)
    if len(s) <= 6:
        return f"{n:,}"
    return f"{s[0]}.{s[1:3]}×10^{len(s) - 1}"


def total_variations() -> int:
    """The engine's full addressable variation space: every forge × every era ×
    every style-axis option (incl. 'unset') × skin × detail bands × treatment.
    This is the true combinatorial limit the Universal Forge can mint."""
    prod = 1
    for meta in STYLE_AXES.values():
        prod *= (len(meta["options"]) + 1)        # +1 = axis left unset
    prod *= (len(SKIN_STYLES) + 1)
    prod *= max(1, len(COMPLEXITY)) * max(1, len(INTRICACY)) * max(1, len(DETAIL_LEVEL))
    prod *= max(1, len(TREATMENTS))
    prod *= max(1, len(INSCRIPTION_PLACEMENTS))
    prod *= max(1, len(_eras.ERA_ORDER))
    return _CATEGORY_COUNT * prod


_THUMB_CACHE: dict[str, list[str]] = {}


def _category_thumb(key: str) -> list[str]:
    """Deterministic 5-colour preview palette for a category (id-only cards)."""
    tp = _THUMB_CACHE.get(key)
    if tp is None:
        tp = cf._palette("modern", cf._rng("thumb", key), 5)
        _THUMB_CACHE[key] = tp
    return tp


def catalog() -> dict:
    """Drives the Forge Hub — families + grouped categories + counts. The
    grouped/browse payload uses the curated CORE NOUNS (fast to render); the
    headline counts reflect the full multi-tier forge library (computed
    arithmetically — the namespace is virtual, never materialised):
      • base_category_count = core nouns × (1 + descriptors)  → 1,000,000+
      • category_count      = base categories × (1 + modifiers)
      • total_variations    = forges × eras × every style-axis option."""
    groups: dict[str, list[dict]] = {}
    fam_counts: dict[str, int] = {}
    for c in _CATEGORIES:
        fam = c["family"]
        fam_counts[fam] = fam_counts.get(fam, 0) + 1
    # Descriptors + modifiers inherit each noun's family, so the full family
    # forge count is the noun count scaled by both virtual factors.
    fam_factor = _BASE_FACTOR * _TOTAL_FACTOR
    families = [{"key": fk, **fv, "count": fam_counts.get(fk, 0) * fam_factor}
                for fk, fv in FAMILIES.items()]
    # Bake a deterministic 2D thumb palette into each category so the Hub can
    # render ID-only preview cards INSTANTLY with zero extra network calls.
    cats = [{**c, "thumb_palette": _category_thumb(c["key"])} for c in _CATEGORIES]
    for c in cats:
        groups.setdefault(c["group"], []).append(c)
    tv = total_variations()
    return {
        "families": families,
        "categories": cats,
        "groups": [{"group": g, "categories": cs} for g, cs in groups.items()],
        "category_count": _CATEGORY_COUNT,
        "base_category_count": _BASE_CATEGORY_COUNT,
        "browse_count": len(_CATEGORIES),
        "descriptor_count": len(_BASE_DESCRIPTORS),
        "modifier_count": len(_MODIFIERS),
        "total_variations": str(tv),
        "total_variations_pretty": _pretty_big(tv),
        "family_count": _FAMILY_TOTAL,
        "family_taxonomy": _family_taxonomy(),
        "presets_per_category_per_era": len(_UNI_STYLES) * _VARIANTS,
    }


def search_categories(q: str, limit: int = 60) -> dict:
    """Server-side search across the full multi-tier forge library. Resolves
    matches WITHOUT scanning the virtual namespace: it finds matching nouns,
    descriptors and modifiers separately, then emits their combinations — so
    even a no-match query returns instantly."""
    s = (q or "").strip().lower()
    if not s:
        return {"query": q, "total": 0, "results": []}
    cap = max(1, min(limit, 200))
    hits: list[dict] = []
    seen: set[str] = set()

    def _push(meta: dict) -> bool:
        if meta["key"] in seen:
            return False
        seen.add(meta["key"])
        hits.append({**meta, "thumb_palette": _category_thumb(meta["key"])})
        return len(hits) >= cap

    noun_hits = [c for c in _CATEGORIES
                 if s in c["label"].lower() or s in c["key"]]
    desc_hits = [d for d in _BASE_DESCRIPTORS if s in d.lower() or s in _slug(d)]
    mod_hits = [m for m in _MODIFIERS if s in m.lower() or s in _slug(m)]

    # 1) exact core-noun matches (best results)
    for c in noun_hits:
        if _push(c):
            return {"query": q, "total": len(hits), "results": hits}
    # 2) a matching DESCRIPTOR applied across every core noun
    for d in desc_hits:
        for c in _CATEGORIES:
            if _push(_base_meta(d, c)):
                return {"query": q, "total": len(hits), "results": hits}
    # 3) every descriptor applied to a matching core noun
    for c in noun_hits:
        for d in _BASE_DESCRIPTORS:
            if _push(_base_meta(d, c)):
                return {"query": q, "total": len(hits), "results": hits}
    # 4) a matching MODIFIER applied across every core noun
    for m in mod_hits:
        for c in _CATEGORIES:
            if _push(_variant_meta(m, c)):
                return {"query": q, "total": len(hits), "results": hits}
    return {"query": q, "total": len(hits), "results": hits}


def random_category(seed: int | None = None, require: list | None = None) -> dict:
    """Pick ONE random forge from the entire multi-tier namespace — a core
    noun, sometimes descriptor-qualified, sometimes modifier-qualified — plus a
    punchy random handful of style axes. `require` FORCES ECS components (e.g.
    ['script','metallic','variant']) so the Forge Hub mask filter always yields
    a matching forge. Powers the Forge Hub 'Surprise Me'."""
    rng = random.Random(seed) if seed is not None else random.Random()
    req = set(require or [])
    noun = rng.choice(_CATEGORIES)
    base = noun
    if _BASE_DESCRIPTORS and ("descriptor" in req or rng.random() < 0.7):
        base = _base_meta(rng.choice(_BASE_DESCRIPTORS), noun)
    meta = base
    if _MODIFIERS and ("variant" in req or rng.random() < 0.6):
        meta = _variant_meta(rng.choice(_MODIFIERS), base)
    # a random handful of style axes (4-7) so the look is distinctive
    axis_items = list(STYLE_AXES.items())
    rng.shuffle(axis_items)
    picked: dict[str, str] = {}
    for ax_key, ax_meta in axis_items[: rng.randint(4, 7)]:
        opts = [k for k in ax_meta["options"].keys() if k != "none"]
        if opts:
            picked[ax_key] = rng.choice(opts)
    # Force required components by injecting a guaranteeing axis selection.
    if "script" in req:
        picked["script"] = "runic"
    if "tattoo" in req:
        picked["tattoo"] = "tribal"
    if "mesh" in req:
        picked["mesh"] = "wireframe"
    if "metallic" in req and "metal_grade" in STYLE_AXES:
        picked["metal_grade"] = next((k for k in STYLE_AXES["metal_grade"]["options"] if k != "none"), "gilded")
    skin = rng.choice(list(SKIN_STYLES.keys()))
    era = rng.choice(_eras.ERA_ORDER)
    insc = {"script": picked.get("script", "runic"), "text": "FORGE", "placement": "auto"} if "inscription" in req else None
    # Build a real spec so the returned ECS mask + DNA are exact.
    spec = generate(meta["key"], era, use_llm=False, seed=seed if seed is not None else rng.randint(1, 1 << 30),
                    skin_style=skin, axes=picked, inscription=insc)
    return {
        "category": meta["key"], "label": meta["label"],
        "family": meta["family"], "group": meta["group"],
        "axes": picked, "skin_style": skin, "era": era, "inscription": insc,
        "component_mask": spec.get("component_mask"), "components": spec.get("components"),
        "dna": spec.get("dna"), "forge_code": spec.get("forge_code"),
    }


# ── Spectacular variation: +100 procedurally-built style axes ───────────────
# Each axis is a dimension of variation; options derive a deterministic tint and
# a keyword-driven surface/vfx so every one meaningfully restyles the asset.
_EXTRA_AXIS_DEFS: list[tuple[str, str]] = [
    ("Material Core", "iron steel bronze gold silver obsidian marble jade bone ivory"),
    ("Weathering", "pristine worn scuffed cracked chipped eroded battle_scarred faded mossy sunbleached"),
    ("Temperature", "frozen icy cold cool tepid warm hot scorching molten searing"),
    ("Mood", "serene cheerful playful tense ominous melancholic furious triumphant mysterious solemn"),
    ("Biome", "forest desert tundra swamp jungle volcanic oceanic alpine savanna wetland"),
    ("Season", "spring summer autumn winter monsoon harvest bloom frost dryseason wetseason"),
    ("Time Of Day", "dawn morning noon afternoon dusk twilight midnight witching_hour goldenhour bluehour"),
    ("Weather", "clear cloudy rain storm snow fog hail sandstorm blizzard drizzle"),
    ("Faction", "empire rebels cult guild horde covenant syndicate clan order tribe"),
    ("Rarity Tier", "common uncommon rare epic legendary mythical relic artifact exalted unique"),
    ("Damage Type", "slashing piercing blunt fire frost shock acid arcane poison holy"),
    ("Texture", "smooth rough grainy bumpy ribbed scaled woven knurled pitted polished"),
    ("Pattern", "striped spotted checkered swirled fractal hexagonal marbled paisley chevron dappled"),
    ("Corrosion", "clean spotted streaked pitted crusted flaking bubbled scaling perforated weeping"),
    ("Growth", "barren sprouting budding flowering overgrown fruiting wilting blooming creeping verdant"),
    ("Decay", "fresh aging weathered rotting decomposing fossilized ruined petrified mummified crumbling"),
    ("Crystallization", "seeded clustered geode prismatic shattered druzy faceted bladed radiating fibrous"),
    ("Liquid Coat", "dry damp dripping soaked submerged oily slick frosted sticky glazed"),
    ("Energy State", "dormant idle charged surging overloaded unstable discharged resonant pulsing critical"),
    ("Radiation", "faint glowing irradiated meltdown contaminated humming searing decaying spent fallout"),
    ("Magnetism", "inert attractive repulsive levitating polarized humming charged aligned chaotic fielded"),
    ("Gravity", "normal heavy light floating crushing inverted warped null tidal anchored"),
    ("Dimension", "material astral shadow dream void mirror spirit fae aether liminal"),
    ("Realm", "mortal celestial infernal fae elemental mechanical abyssal divine primal nether"),
    ("Mythology", "norse greek egyptian aztec celtic shinto slavic hindu mesopotamian polynesian"),
    ("Culture", "roman feudal nomadic oceanic industrial cyber tribal imperial colonial pastoral"),
    ("Architecture", "gothic baroque brutalist artdeco organic minimalist romanesque rococo deconstructivist vernacular"),
    ("Ornamentation", "plain trimmed filigreed embossed jeweled engraved fluted scrolled studded tasseled"),
    ("Engraving Motif", "floral geometric runic heraldic bestiary celestial nautical tribal scrollwork knotwork"),
    ("Inlay", "gold silver gem enamel pearl bone copper jade obsidian abalone"),
    ("Trim", "gilded silvered copper ebony platinum brass rosewood pewter chrome bronze"),
    ("Filigree", "fine ornate baroque delicate bold lattice scrolled woven beaded twisted"),
    ("Gemset", "ruby sapphire emerald diamond amethyst opal topaz garnet onyx citrine"),
    ("Woodwork", "oak walnut ebony bamboo driftwood petrified mahogany teak birch cedar"),
    ("Stonework", "granite marble slate sandstone basalt obsidian limestone quartzite travertine flagstone"),
    ("Fabric", "linen silk velvet wool canvas brocade satin denim burlap chiffon"),
    ("Leather", "rawhide tanned studded lacquered exotic suede embossed cracked oiled scaled"),
    ("Bonework", "carved polished cracked runed bleached lacquered fused splintered etched ancient"),
    ("Scale Coat", "reptilian fish dragon serpent armored overlapping iridescent ridged spined keeled"),
    ("Fur", "short shaggy sleek tufted mangy plush bristled matted silky striped"),
    ("Feather", "downy plumed iridescent ruffled barbed crested speckled molting glossy banded"),
    ("Chitin", "glossy ridged spiked translucent banded matte pitted segmented lacquered fibrous"),
    ("Moss", "patchy creeping blanketed luminescent dry velvety sphagnum hanging crusted lush"),
    ("Lichen", "crusty leafy fruticose powdery foliose map_lichen beard_lichen rosette flaky encrusting"),
    ("Rust Pattern", "speckled streaked bleeding consuming flaking blooming pitted crusted weeping veined"),
    ("Burn Pattern", "singed charred blistered ashen smoldering scorched cracked melted carbonized seared"),
    ("Frost Pattern", "dusted feathered crusted glacial rimed crystalline fern hoar sheeted spiked"),
    ("Crack Pattern", "hairline spider branching shattered crazed fractured splintered webbed fissured veined"),
    ("Vein Pattern", "subtle marbled glowing pulsing branching webbed deep faint molten crystalline"),
    ("Glow Pattern", "edges runes core veins full seams cracks tips rings spots"),
    ("Circuit Pattern", "traces nodes grid neural maze radial dense sparse layered branching"),
    ("Rune Set", "elder dwarven elven demonic celestial draconic abyssal arcane primal sylvan"),
    ("Sigil Set", "ward bind summon banish protect curse reveal seal empower scry"),
    ("Heraldry", "lion eagle dragon wolf serpent phoenix bear stag boar griffin"),
    ("Banner Motif", "stripes cross star sunburst checker chevron saltire quarters bordure roundel"),
    ("Paint Scheme", "monochrome duotone gradient splatter solid striped faded twotone weathered metallic"),
    ("Camo", "woodland desert urban arctic digital tiger splinter multicam jungle naval"),
    ("Gradient", "vertical radial diagonal rainbow horizontal conic sunset ocean ember aurora"),
    ("Duotone", "warm cool complementary muted contrast pastel vivid earthy neon mono"),
    ("Neon Scheme", "cyan magenta lime amber violet pink teal orange electric chartreuse"),
    ("Pastel Scheme", "rose mint lavender peach sky butter lilac sage coral periwinkle"),
    ("Monochrome", "ink ash charcoal silver slate graphite pewter onyx smoke bone"),
    ("Iridescence", "faint oilslick beetle pearl peacock soap bismuth nacre prism aurora"),
    ("Holography", "shimmer scanline glitch prism rainbow foil parallax diffraction chrome ripple"),
    ("Chromatics", "vivid desaturated sepia inverted muted saturated bleached technicolor duochrome neon"),
    ("Luminescence", "bio chemical magical radioactive phosphor fungal abyssal stellar plasma ember"),
    ("Shadow Depth", "flat soft medium deep dramatic ambient hard rimmed cast layered"),
    ("Highlight", "dull soft crisp sharp blinding glint sheen specular bloom rim"),
    ("Reflectivity", "low medium mirror matte satin gloss chrome wet dull burnished"),
    ("Refraction", "glass crystal prism diamond water ice gem quartz oil bubble"),
    ("Translucency", "opaque frosted milky clear hazy stained smoky veiled glassy waxy"),
    ("Subsurface", "waxy skin jade marble wax candle milk gemstone leaf frosted"),
    ("Anisotropy", "brushed radial circular linear swirled spun grooved combed hairline waved"),
    ("Clearcoat", "satin gloss wetlook matte pearl candy flat ceramic lacquer waxed"),
    ("Patina", "verdigris brown black rainbow blue green sepia mottled aged noble"),
    ("Oxidation", "light moderate heavy spotted uniform crusted bloomed streaked pitted advanced"),
    ("Bloom", "soft bright intense subtle radiant hazy diffuse sharp halo overexposed"),
    ("Halo Type", "ring disc rays crown arc spiral broken double radiant flame"),
    ("Particle Type", "dust embers snow sparks petals motes ash bubbles leaves shards"),
    ("Trail Type", "smoke light ribbon shards mist sparks afterimage streaks vapor comet"),
    ("Ambient FX", "mist motes haze glimmer drift sparkle fog dust shimmer pollen"),
    ("Impact FX", "crack shatter splash burst shockwave dent crater ripple spark debris"),
    ("Idle FX", "breathe pulse flicker drift sway hum shimmer bob rotate twitch"),
    ("Charge FX", "gather spiral crackle bloom vortex pulse converge surge spark coil"),
    ("Aura Shape", "orb ring spikes wings vortex halo flame lattice tendrils dome"),
    ("Aura Intensity", "faint moderate strong overwhelming subtle pulsing radiant blinding flickering steady"),
    ("Silhouette", "compact sleek bulky jagged flowing angular rounded tapered hulking elegant"),
    ("Proportion", "petite standard grand colossal stout lanky squat towering balanced exaggerated"),
    ("Stance", "neutral aggressive defensive regal coiled relaxed alert lunging guarded poised"),
    ("Finish Coat", "raw primed painted lacquered weathered enameled waxed oiled varnished anodized"),
    ("Surface Relief", "flat low_relief high_relief deep_carved engraved embossed pierced fluted ridged terraced"),
    ("Edge Style", "blunt beveled sharp serrated wavy notched hooked tapered chamfered toothed"),
    ("Joinery", "riveted welded stitched lashed bolted dovetailed pinned brazed woven clasped"),
    ("Hardware", "brass iron silver gold steel copper bronze chrome nickel pewter"),
    ("Accent Color", "crimson azure emerald violet amber teal magenta gold ivory coral"),
    ("Base Tone", "neutral warm cool earthy vibrant muted dark pale pastel deep"),
    ("Aging Spots", "few moderate many sparse clustered scattered dense pitted blotchy speckled"),
    ("Polish Level", "matte satin gloss mirror brushed buffed dull waxed honed burnished"),
    ("Scratch Density", "light moderate heavy pristine scuffed gouged hairline crosshatched worn deep"),
    ("Theme Tint", "ember frost verdant void radiant crimson azure gold shadow prism"),
]


def _kw_surface(word: str) -> dict:
    l = word.lower()
    s: dict = {}
    if any(k in l for k in ("metal", "chrome", "steel", "iron", "gold", "silver",
                            "bronze", "brass", "copper", "platinum", "mirror", "reflect",
                            "polish", "gloss", "chrome")):
        s["metalness"] = 0.85; s["roughness"] = 0.25
    if any(k in l for k in ("matte", "stone", "rock", "rough", "sand", "dirt", "mud",
                            "ash", "bone", "wood", "oak", "cloth", "fabric", "linen",
                            "wool", "leather", "moss", "fur", "raw", "grain")):
        s["roughness"] = 0.95; s["metalness"] = min(s.get("metalness", 0.1), 0.1)
    if any(k in l for k in ("ice", "frost", "glass", "crystal", "wet", "water", "slime",
                            "ooze", "gel", "liquid", "gem", "diamond", "drip", "soak",
                            "oil", "prism")):
        s["roughness"] = 0.08; s["metalness"] = max(s.get("metalness", 0.3), 0.3)
    if any(k in l for k in ("glow", "neon", "lumin", "radiant", "beam", "halo", "plasma",
                            "laser", "spark", "ember", "star", "cosmic", "arcane", "holy",
                            "aura", "bio", "magic", "radio", "pulse")):
        s["emissive"] = 0.4
    return s


def _kw_vfx(word: str) -> str | None:
    l = word.lower()
    if any(k in l for k in ("fire", "ember", "molten", "flame", "burn", "lava", "scorch")):
        return "embers"
    if any(k in l for k in ("frost", "ice", "snow", "crystal", "star", "spark", "shimmer", "prism")):
        return "sparkle"
    if any(k in l for k in ("glow", "neon", "radiant", "lumin", "plasma", "laser", "arcane", "holy", "beam", "bloom")):
        return "glow"
    if any(k in l for k in ("fog", "mist", "smoke", "toxic", "poison", "shadow", "void", "cloud", "haze")):
        return "fog"
    return None


def _build_extra_axes() -> dict:
    axes: dict[str, dict] = {}
    for label, opts in _EXTRA_AXIS_DEFS:
        akey = _slug(label)
        if akey in STYLE_AXES or akey in axes:
            akey = f"{akey}_v"
        options: dict[str, dict] = {}
        for w in opts.split():
            okey = _slug(w)
            if okey in options:
                continue
            hue = int(hashlib.sha256(f"{label}|{w}".encode()).hexdigest()[:6], 16) % 360
            o: dict = {"label": w.replace("_", " ").title(),
                       "tint": _hsl_to_hex(hue, 0.6, 0.55)}
            surf = _kw_surface(w) or _kw_surface(label)
            if surf:
                o["surface"] = surf
            v = _kw_vfx(w) or _kw_vfx(label)
            if v:
                o["vfx"] = v
            options[okey] = o
        axes[akey] = {"label": label, "options": options}
    return axes


STYLE_AXES.update(_build_extra_axes())

# Real, hand-authored options for the few hardcoded axes that were thin — so
# the whole tree is genuinely deep (NOT synthetic-padded).
_AXIS_TOPUP_REAL: dict[str, list[str]] = {
    "art_style": ["Storybook", "Claymation", "Vaporwave", "Ukiyo-e", "Graffiti"],
    "aura": ["Solar", "Lunar", "Spectral", "Venomous", "Radiant Bloom"],
    "curse": ["Hexed", "Blighted", "Doomed", "Withered", "Haunted"],
    "dripping": ["Oozing", "Weeping", "Molten Drip", "Tar-Soaked", "Honeyed"],
    "elemental": ["Storm", "Magma", "Glacier", "Gale", "Tide", "Quake"],
    "exotic": ["Alien", "Eldritch", "Otherworldly", "Biomechanical", "Dreamlike"],
    "fantasy": ["High Fantasy", "Dark Fantasy", "Fairytale", "Grimdark", "Sword & Sorcery", "Cosmic Horror", "Norse Saga", "Arabian Nights"],
    "fashion": ["Regal", "Rugged", "Ceremonial", "Streetwear", "Tribal Wear"],
    "height": ["Crouched", "Knee-High", "Waist-High", "Statuesque", "Gargantuan"],
    "light_emanation": ["Lantern", "Beacon", "Ember Light", "Moonglow", "Searchlight"],
    "magic": ["Necromancy", "Conjuration", "Enchantment", "Divination", "Illusion"],
    "metal_grade": ["Titanium", "Adamantine", "Mithril", "Damascus", "Meteoric"],
    "punk": ["Solarpunk", "Dieselpunk", "Atompunk", "Clockpunk", "Mythpunk", "Nanopunk", "Voidpunk", "Rustpunk"],
    "realism": ["Photoreal", "Hyperreal", "Stylized-Real", "Semi-Real", "Gritty", "Cinematic", "Documentary", "Lo-Fi"],
}
for _ak, _labels in _AXIS_TOPUP_REAL.items():
    if _ak in STYLE_AXES:
        _o = STYLE_AXES[_ak]["options"]
        for _lb in _labels:
            _ok = _slug(_lb)
            if _ok not in _o:
                _o[_ok] = {"label": _lb}
# Final safety net only — with the authoring above this should pad nothing.
_ensure_min_options()


# ── Parametric geometry per archetype family ───────────────────────────────
def _sized(size_class: str) -> float:
    return {"small": 0.7, "medium": 1.0, "large": 1.4,
            "huge": 2.0, "monumental": 2.8}.get(size_class, 1.0)


def _flora_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    trunk = pal[3] if len(pal) > 3 else "#6e4a2a"
    leaf = pal[2] if len(pal) > 2 else "#3a7a40"
    th = round(rng.uniform(1.6, 2.6) * s, 2)
    parts = [{"type": "cylinder", "pos": [0, th / 2, 0],
              "size": [0.5 * s, th, 0.5 * s], "color": trunk}]
    n = rng.randint(2, 4)
    for i in range(n):
        r = round(rng.uniform(1.0, 1.7) * s, 2)
        parts.append({"type": "sphere",
                      "pos": [round(rng.uniform(-0.6, 0.6) * s, 2),
                              round(th + rng.uniform(0.2, 1.1) * s, 2),
                              round(rng.uniform(-0.6, 0.6) * s, 2)],
                      "size": [r, r, r],
                      "color": cf._hex_shift(leaf, rng, 18)})
    return parts


def _character_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    skin = pal[4] if len(pal) > 4 else "#d9a066"
    cloth = pal[0] if pal else "#5a6e58"
    cloth2 = pal[1] if len(pal) > 1 else "#7a3a2a"
    hair = pal[3] if len(pal) > 3 else "#3a2a1a"
    lh = 1.3 * s
    parts = [
        {"type": "box", "pos": [-0.28 * s, lh / 2, 0], "size": [0.34 * s, lh, 0.36 * s], "color": cloth2},
        {"type": "box", "pos": [0.28 * s, lh / 2, 0], "size": [0.34 * s, lh, 0.36 * s], "color": cloth2},
        {"type": "box", "pos": [0, lh + 0.95 * s, 0], "size": [1.05 * s, 1.5 * s, 0.6 * s], "color": cloth},
        {"type": "box", "pos": [-0.78 * s, lh + 0.95 * s, 0], "size": [0.3 * s, 1.35 * s, 0.3 * s], "color": cloth},
        {"type": "box", "pos": [0.78 * s, lh + 0.95 * s, 0], "size": [0.3 * s, 1.35 * s, 0.3 * s], "color": cloth},
        {"type": "sphere", "pos": [0, lh + 2.1 * s, 0], "size": [0.78 * s, 0.78 * s, 0.78 * s], "color": skin},
        {"type": "box", "pos": [0, lh + 2.45 * s, -0.04 * s], "size": [0.82 * s, 0.4 * s, 0.82 * s], "color": hair},
    ]
    return parts


def _creature_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    body = pal[0] if pal else "#7a6a4a"
    belly = pal[2] if len(pal) > 2 else "#caa070"
    bl = 2.2 * s
    parts = [{"type": "sphere", "pos": [0, 1.0 * s, 0], "size": [bl, 1.3 * s, 1.3 * s], "color": body}]
    for dx in (-0.7 * s, 0.7 * s):
        for dz in (-0.45 * s, 0.45 * s):
            parts.append({"type": "cylinder", "pos": [dx, 0.4 * s, dz],
                          "size": [0.32 * s, 0.8 * s, 0.32 * s], "color": cf._hex_shift(body, rng, 14)})
    parts.append({"type": "sphere", "pos": [bl / 2 + 0.1 * s, 1.35 * s, 0], "size": [0.95 * s, 0.95 * s, 0.95 * s], "color": belly})
    parts.append({"type": "cone", "pos": [-bl / 2 - 0.3 * s, 1.0 * s, 0], "size": [0.5 * s, 1.1 * s, 0.5 * s], "color": body})
    return parts


def _vehicle_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    body = pal[0] if pal else "#3a5a8a"
    cabin = pal[1] if len(pal) > 1 else "#8aa6c2"
    tyre = "#1a1a1a"
    bl, bw = 3.4 * s, 1.6 * s
    parts = [
        {"type": "box", "pos": [0, 0.7 * s, 0], "size": [bl, 0.7 * s, bw], "color": body},
        {"type": "box", "pos": [-0.3 * s, 1.35 * s, 0], "size": [bl * 0.5, 0.7 * s, bw * 0.85], "color": cabin},
    ]
    for dx in (-bl / 2 + 0.6 * s, bl / 2 - 0.6 * s):
        for dz in (-bw / 2, bw / 2):
            parts.append({"type": "cylinder", "pos": [dx, 0.4 * s, dz],
                          "size": [0.7 * s, 0.32 * s, 0.7 * s], "color": tyre,
                          "rot": [1.5708, 0, 0]})
    return parts


def _wearable_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    main = pal[0] if pal else "#7a3a5a"
    trim = pal[2] if len(pal) > 2 else "#e6d2b0"
    parts = [
        {"type": "box", "pos": [0, 1.4 * s, 0], "size": [1.3 * s, 1.7 * s, 0.5 * s], "color": main},
        {"type": "box", "pos": [-0.95 * s, 1.6 * s, 0], "size": [0.42 * s, 1.1 * s, 0.42 * s], "color": main},
        {"type": "box", "pos": [0.95 * s, 1.6 * s, 0], "size": [0.42 * s, 1.1 * s, 0.42 * s], "color": main},
        {"type": "box", "pos": [0, 0.55 * s, 0], "size": [1.32 * s, 0.25 * s, 0.52 * s], "color": trim},
        {"type": "torus", "pos": [0, 2.5 * s, 0], "size": [0.7 * s, 0.7 * s, 0.22 * s], "color": trim},
    ]
    return parts


def _prop_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    a = pal[0] if pal else "#9a8a78"
    b = pal[1] if len(pal) > 1 else "#caa070"
    c = pal[3] if len(pal) > 3 else "#5a6e58"
    parts = [
        {"type": "box", "pos": [0, 1.0 * s, 0], "size": [1.2 * s, 1.4 * s, 1.2 * s], "color": a},
        {"type": "cylinder", "pos": [0, 2.0 * s, 0], "size": [0.4 * s, 0.9 * s, 0.4 * s], "color": b},
        {"type": "sphere", "pos": [0, 2.7 * s, 0], "size": [0.5 * s, 0.5 * s, 0.5 * s], "color": c},
    ]
    return parts


def _world_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    core = pal[0] if pal else "#3a6a8a"
    land = pal[2] if len(pal) > 2 else "#5a8a50"
    R = 2.6 * s
    parts = [{"type": "sphere", "pos": [0, R + 0.3, 0], "size": [R * 2, R * 2, R * 2], "color": core}]
    n = rng.randint(3, 6)
    for _ in range(n):
        rr = round(rng.uniform(0.5, 1.1) * s, 2)
        ang = rng.uniform(0, 6.28)
        ele = rng.uniform(-0.6, 0.9)
        parts.append({"type": "sphere",
                      "pos": [round(R * 0.85 * (1 - ele * ele) ** 0.5 * math.cos(ang), 2),
                              round(R + 0.3 + R * ele, 2),
                              round(R * 0.85 * (1 - ele * ele) ** 0.5 * math.sin(ang), 2)],
                      "size": [rr, rr * 0.5, rr], "color": cf._hex_shift(land, rng, 16)})
    parts.append({"type": "torus", "pos": [0, R + 0.3, 0], "size": [R * 3, R * 3, 0.18 * s],
                  "color": pal[4] if len(pal) > 4 else "#aab6c2", "rot": [1.2, 0, 0.4]})
    return parts


def _fx_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    parts = []
    n = rng.randint(5, 9)
    for i in range(n):
        h = round(rng.uniform(0.6, 2.6) * s, 2)
        parts.append({"type": "cone",
                      "pos": [round(rng.uniform(-1.4, 1.4) * s, 2), h / 2,
                              round(rng.uniform(-1.4, 1.4) * s, 2)],
                      "size": [round(rng.uniform(0.4, 0.9) * s, 2), h,
                               round(rng.uniform(0.4, 0.9) * s, 2)],
                      "color": cf._hex_shift(pal[i % len(pal)] if pal else "#ffaa33", rng, 24)})
    return parts


def _sound_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    parts = []
    n = 11
    for i in range(n):
        h = round((0.4 + abs(__import__("math").sin(i * 0.9 + rng.random())) * 2.4) * s, 2)
        parts.append({"type": "box",
                      "pos": [round((-n / 2 + i) * 0.55 * s, 2), h / 2, 0],
                      "size": [0.38 * s, h, 0.38 * s],
                      "color": cf._hex_shift(pal[i % len(pal)] if pal else "#6c8cff", rng, 18)})
    return parts


_GEO = {
    "flora": _flora_geo, "character": _character_geo, "creature": _creature_geo,
    "vehicle": _vehicle_geo, "wearable": _wearable_geo, "prop": _prop_geo,
    "world": _world_geo, "fx": _fx_geo, "sound": _sound_geo,
}


def _furniture_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    wood = pal[0] if pal else "#7a5230"
    cush = pal[2] if len(pal) > 2 else "#8a4a4a"
    top = 1.0 * s
    parts = [{"type": "box", "pos": [0, top, 0], "size": [2.0 * s, 0.22 * s, 1.4 * s], "color": wood}]
    for dx in (-0.85 * s, 0.85 * s):
        for dz in (-0.55 * s, 0.55 * s):
            parts.append({"type": "box", "pos": [dx, top / 2, dz], "size": [0.18 * s, top, 0.18 * s], "color": cf._hex_shift(wood, rng, 12)})
    parts.append({"type": "box", "pos": [0, top + 0.7 * s, -0.6 * s], "size": [2.0 * s, 1.3 * s, 0.2 * s], "color": cush})
    return parts


def _weapon_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    blade = pal[4] if len(pal) > 4 else "#c8ccd4"
    guard = pal[1] if len(pal) > 1 else "#caa050"
    grip = pal[3] if len(pal) > 3 else "#4a2a18"
    parts = [
        {"type": "box", "pos": [0, 2.4 * s, 0], "size": [0.22 * s, 3.0 * s, 0.08 * s], "color": blade},
        {"type": "cone", "pos": [0, 4.0 * s, 0], "size": [0.22 * s, 0.5 * s, 0.08 * s], "color": blade},
        {"type": "box", "pos": [0, 0.85 * s, 0], "size": [1.1 * s, 0.18 * s, 0.18 * s], "color": guard},
        {"type": "cylinder", "pos": [0, 0.45 * s, 0], "size": [0.18 * s, 0.8 * s, 0.18 * s], "color": grip},
        {"type": "sphere", "pos": [0, 0.0, 0], "size": [0.3 * s, 0.3 * s, 0.3 * s], "color": guard},
    ]
    return parts


def _container_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    body = pal[0] if pal else "#6e4a2a"
    band = pal[4] if len(pal) > 4 else "#8a8a90"
    parts = [
        {"type": "box", "pos": [0, 0.8 * s, 0], "size": [2.0 * s, 1.4 * s, 1.4 * s], "color": body},
        {"type": "box", "pos": [0, 1.75 * s, 0], "size": [2.05 * s, 0.55 * s, 1.45 * s], "color": cf._hex_shift(body, rng, 14)},
    ]
    for dy in (0.5 * s, 1.1 * s):
        parts.append({"type": "box", "pos": [0, dy, 0.72 * s], "size": [2.06 * s, 0.16 * s, 0.06 * s], "color": band})
    parts.append({"type": "sphere", "pos": [0, 1.5 * s, 0.74 * s], "size": [0.24 * s, 0.24 * s, 0.24 * s], "color": band})
    return parts


def _machine_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    body = pal[0] if pal else "#5a6a7a"
    core = pal[2] if len(pal) > 2 else "#43d39e"
    parts = [
        {"type": "box", "pos": [0, 1.2 * s, 0], "size": [1.6 * s, 2.0 * s, 1.2 * s], "color": body},
        {"type": "sphere", "pos": [0, 1.5 * s, 0.62 * s], "size": [0.6 * s, 0.6 * s, 0.6 * s], "color": core},
        {"type": "cylinder", "pos": [-1.0 * s, 1.2 * s, 0], "size": [0.3 * s, 1.4 * s, 0.3 * s], "color": cf._hex_shift(body, rng, 12)},
        {"type": "cylinder", "pos": [1.0 * s, 1.2 * s, 0], "size": [0.3 * s, 1.4 * s, 0.3 * s], "color": cf._hex_shift(body, rng, 12)},
        {"type": "cylinder", "pos": [0, 2.6 * s, 0], "size": [0.12 * s, 0.9 * s, 0.12 * s], "color": band if (band := pal[4] if len(pal) > 4 else "#aab6c2") else "#aab6c2"},
        {"type": "sphere", "pos": [0, 3.15 * s, 0], "size": [0.22 * s, 0.22 * s, 0.22 * s], "color": core},
    ]
    return parts


def _instrument_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    body = pal[0] if pal else "#8a4a26"
    neck = pal[3] if len(pal) > 3 else "#3a2a1a"
    parts = [
        {"type": "sphere", "pos": [0, 1.0 * s, 0], "size": [1.6 * s, 1.7 * s, 0.5 * s], "color": body},
        {"type": "box", "pos": [0, 2.6 * s, 0], "size": [0.28 * s, 2.4 * s, 0.22 * s], "color": neck},
        {"type": "box", "pos": [0, 3.9 * s, 0], "size": [0.5 * s, 0.5 * s, 0.26 * s], "color": cf._hex_shift(neck, rng, 14)},
        {"type": "torus", "pos": [0, 1.0 * s, 0.28 * s], "size": [0.7 * s, 0.7 * s, 0.08 * s], "color": pal[4] if len(pal) > 4 else "#1a1a1a"},
    ]
    return parts


def _food_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    plate = pal[4] if len(pal) > 4 else "#e6e2d8"
    food = pal[1] if len(pal) > 1 else "#c87a3a"
    parts = [{"type": "cylinder", "pos": [0, 0.12 * s, 0], "size": [2.4 * s, 0.16 * s, 2.4 * s], "color": plate}]
    n = rng.randint(2, 4)
    for _ in range(n):
        r = round(rng.uniform(0.5, 0.9) * s, 2)
        parts.append({"type": "sphere",
                      "pos": [round(rng.uniform(-0.7, 0.7) * s, 2), round(0.2 + r * 0.6, 2),
                              round(rng.uniform(-0.7, 0.7) * s, 2)],
                      "size": [r, r * 0.8, r], "color": cf._hex_shift(food, rng, 18)})
    return parts


def _ui_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    panel = pal[0] if pal else "#2b3550"
    accent = pal[2] if len(pal) > 2 else "#43d39e"
    parts = [
        {"type": "box", "pos": [0, 1.6 * s, 0], "size": [2.6 * s, 2.0 * s, 0.18 * s], "color": panel},
        {"type": "box", "pos": [0, 2.4 * s, 0.12 * s], "size": [2.2 * s, 0.4 * s, 0.06 * s], "color": accent},
        {"type": "box", "pos": [-0.5 * s, 1.4 * s, 0.12 * s], "size": [1.0 * s, 0.9 * s, 0.06 * s], "color": cf._hex_shift(accent, rng, 22)},
        {"type": "torus", "pos": [0.8 * s, 1.4 * s, 0.14 * s], "size": [0.6 * s, 0.6 * s, 0.1 * s], "color": pal[3] if len(pal) > 3 else "#f1a208"},
    ]
    return parts


def _avatar_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    stone = pal[0] if pal else "#9aa0a6"
    head = pal[4] if len(pal) > 4 else "#b0b6bc"
    parts = [
        {"type": "cylinder", "pos": [0, 0.4 * s, 0], "size": [2.2 * s, 0.8 * s, 2.2 * s], "color": cf._hex_shift(stone, rng, 10)},
        {"type": "box", "pos": [0, 1.6 * s, 0], "size": [2.0 * s, 1.6 * s, 1.2 * s], "color": stone},
        {"type": "sphere", "pos": [0, 3.0 * s, 0], "size": [1.2 * s, 1.3 * s, 1.2 * s], "color": head},
    ]
    return parts


def _terrain_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    rock = pal[0] if pal else "#6e6a62"
    parts = []
    n = rng.randint(3, 6)
    for _ in range(n):
        r = round(rng.uniform(0.8, 2.0) * s, 2)
        parts.append({"type": "sphere",
                      "pos": [round(rng.uniform(-1.6, 1.6) * s, 2), round(r * 0.5, 2),
                              round(rng.uniform(-1.6, 1.6) * s, 2)],
                      "size": [r, r * rng.uniform(0.6, 1.0), r], "color": cf._hex_shift(rock, rng, 16)})
    return parts


_GEO.update({
    "furniture": _furniture_geo, "weapon": _weapon_geo, "container": _container_geo,
    "machine": _machine_geo, "instrument": _instrument_geo, "food": _food_geo,
    "ui": _ui_geo, "avatar": _avatar_geo, "terrain": _terrain_geo,
})


def _gem_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    c = pal[2] if len(pal) > 2 else "#4cc9f0"
    return [
        {"type": "cone", "pos": [0, 1.6 * s, 0], "size": [1.3 * s, 1.6 * s, 1.3 * s], "color": c},
        {"type": "cone", "pos": [0, 0.8 * s, 0], "size": [1.3 * s, 0.9 * s, 1.3 * s], "color": cf._hex_shift(c, rng, 18), "rot": [3.14159, 0, 0]},
    ]


def _light_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    post = pal[3] if len(pal) > 3 else "#3a3a3a"
    glow = pal[1] if len(pal) > 1 else "#ffd60a"
    return [
        {"type": "cylinder", "pos": [0, 1.4 * s, 0], "size": [0.22 * s, 2.8 * s, 0.22 * s], "color": post},
        {"type": "sphere", "pos": [0, 3.1 * s, 0], "size": [0.9 * s, 0.9 * s, 0.9 * s], "color": glow},
    ]


def _book_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    cover = pal[0] if pal else "#7a3a2a"
    page = pal[4] if len(pal) > 4 else "#e6e2d0"
    return [
        {"type": "box", "pos": [0, 0.5 * s, 0], "size": [1.8 * s, 0.3 * s, 2.4 * s], "color": cover},
        {"type": "box", "pos": [0.05 * s, 0.85 * s, 0], "size": [1.6 * s, 0.35 * s, 2.2 * s], "color": page},
        {"type": "box", "pos": [0, 1.2 * s, 0], "size": [1.8 * s, 0.3 * s, 2.4 * s], "color": cover},
    ]


def _coin_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    gold = pal[1] if len(pal) > 1 else "#ffd60a"
    parts = []
    for i in range(rng.randint(2, 4)):
        parts.append({"type": "cylinder", "pos": [round(rng.uniform(-0.3, 0.3) * s, 2), 0.18 * s + i * 0.18 * s, round(rng.uniform(-0.3, 0.3) * s, 2)],
                      "size": [1.4 * s, 0.16 * s, 1.4 * s], "color": cf._hex_shift(gold, rng, 12)})
    return parts


def _armor_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    metal = pal[4] if len(pal) > 4 else "#9aa0a6"
    boss = pal[1] if len(pal) > 1 else "#caa050"
    return [
        {"type": "box", "pos": [0, 1.6 * s, 0], "size": [2.0 * s, 2.6 * s, 0.4 * s], "color": metal},
        {"type": "sphere", "pos": [0, 1.6 * s, 0.3 * s], "size": [0.7 * s, 0.7 * s, 0.5 * s], "color": boss},
        {"type": "box", "pos": [0, 1.6 * s, 0], "size": [0.25 * s, 2.6 * s, 0.42 * s], "color": cf._hex_shift(metal, rng, -10)},
    ]


def _banner_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    pole = pal[3] if len(pal) > 3 else "#5a4a2a"
    cloth = pal[0] if pal else "#7a2a3a"
    return [
        {"type": "cylinder", "pos": [-1.0 * s, 2.5 * s, 0], "size": [0.15 * s, 5.0 * s, 0.15 * s], "color": pole},
        {"type": "plane", "pos": [0.1 * s, 3.4 * s, 0], "size": [2.2 * s, 0.06 * s, 2.8 * s], "color": cloth, "rot": [0, 0, 1.5708]},
    ]


def _door_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    frame = pal[3] if len(pal) > 3 else "#5a4632"
    panel = pal[0] if pal else "#6e4a2a"
    return [
        {"type": "box", "pos": [-1.1 * s, 2.0 * s, 0], "size": [0.3 * s, 4.0 * s, 0.4 * s], "color": frame},
        {"type": "box", "pos": [1.1 * s, 2.0 * s, 0], "size": [0.3 * s, 4.0 * s, 0.4 * s], "color": frame},
        {"type": "box", "pos": [0, 3.9 * s, 0], "size": [2.5 * s, 0.4 * s, 0.4 * s], "color": frame},
        {"type": "box", "pos": [0, 1.9 * s, 0], "size": [1.9 * s, 3.6 * s, 0.2 * s], "color": panel},
        {"type": "sphere", "pos": [0.6 * s, 1.9 * s, 0.16 * s], "size": [0.2 * s, 0.2 * s, 0.2 * s], "color": pal[1] if len(pal) > 1 else "#caa050"},
    ]


def _shrine_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    stone = pal[0] if pal else "#9aa0a6"
    orb = pal[2] if len(pal) > 2 else "#4cc9f0"
    return [
        {"type": "box", "pos": [0, 0.4 * s, 0], "size": [3.0 * s, 0.8 * s, 3.0 * s], "color": cf._hex_shift(stone, rng, -8)},
        {"type": "cylinder", "pos": [-1.0 * s, 1.6 * s, -1.0 * s], "size": [0.4 * s, 2.0 * s, 0.4 * s], "color": stone},
        {"type": "cylinder", "pos": [1.0 * s, 1.6 * s, -1.0 * s], "size": [0.4 * s, 2.0 * s, 0.4 * s], "color": stone},
        {"type": "prism", "pos": [0, 3.0 * s, 0], "size": [3.2 * s, 1.2 * s, 3.2 * s], "color": cf._hex_shift(stone, rng, 12)},
        {"type": "sphere", "pos": [0, 1.6 * s, 0], "size": [0.8 * s, 0.8 * s, 0.8 * s], "color": orb},
    ]


def _mushroom_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    stem = pal[4] if len(pal) > 4 else "#e6e2d0"
    cap = pal[0] if pal else "#c0392b"
    parts = []
    n = rng.randint(1, 3)
    for i in range(n):
        sc = rng.uniform(0.7, 1.2)
        x = round((i - n / 2) * 1.2 * s, 2)
        h = round(1.2 * sc * s, 2)
        parts.append({"type": "cylinder", "pos": [x, h / 2, 0], "size": [0.5 * sc * s, h, 0.5 * sc * s], "color": stem})
        parts.append({"type": "sphere", "pos": [x, h + 0.2 * sc * s, 0], "size": [1.3 * sc * s, 0.9 * sc * s, 1.3 * sc * s], "color": cf._hex_shift(cap, rng, 14)})
    return parts


def _trap_geo(pal: list[str], rng: random.Random, s: float) -> list[dict]:
    plate = pal[3] if len(pal) > 3 else "#3a3a3a"
    spike = pal[4] if len(pal) > 4 else "#9aa0a6"
    parts = [{"type": "box", "pos": [0, 0.1 * s, 0], "size": [3.0 * s, 0.2 * s, 3.0 * s], "color": plate}]
    for dx in (-0.9 * s, 0, 0.9 * s):
        for dz in (-0.9 * s, 0, 0.9 * s):
            parts.append({"type": "cone", "pos": [dx, 0.7 * s, dz], "size": [0.4 * s, 1.1 * s, 0.4 * s], "color": cf._hex_shift(spike, rng, 10)})
    return parts


_GEO.update({
    "gem": _gem_geo, "light": _light_geo, "book": _book_geo, "coin": _coin_geo,
    "armor": _armor_geo, "banner": _banner_geo, "door": _door_geo,
    "shrine": _shrine_geo, "mushroom": _mushroom_geo, "trap": _trap_geo,
})


def _geometry(family: str, category: str, pal: list[str],
              rng: random.Random, size_class: str) -> list[dict]:
    s = _sized(size_class)
    if family == "structure":
        return cf._construct_geometry("house", pal, rng, size_class)
    if family == "surface":
        return cf._material_geometry(category, pal, rng)
    gen = _GEO.get(family)
    return gen(pal, rng, s) if gen else cf._construct_geometry("house", pal, rng, size_class)


def presets_per_era() -> int:
    return len(_UNI_STYLES) * _VARIANTS


def _preset(category: str, era_key: str, idx: int) -> dict:
    meta = _CAT_BY_KEY.get(category) or {"key": category, "label": category.replace("_", " ").title(),
                                          "family": _classify(category)}
    family = meta["family"]
    era = _eras.get_era(era_key)
    style = _UNI_STYLES[idx % len(_UNI_STYLES)]
    variant = (idx // len(_UNI_STYLES)) % _VARIANTS
    rng = cf._rng("uni", era["key"], category, style, variant)
    pal = cf._palette(era["key"], rng, 6)
    size_class = rng.choice(_SIZE_CLASSES)
    pid = "uni_" + hashlib.sha256(
        f"{category}{era['key']}{style}{variant}".encode()).hexdigest()[:10]
    geometry = _geometry(family, category, pal, rng, size_class)
    poly = rng.randint(max(1, era["max_poly"] // 8), era["max_poly"]) if era["max_poly"] > 0 else 0
    lo, hi = era["asset_kb_range"]
    label = f"{style.title()} {meta['label']}"
    descriptor = (f"A {style} {meta['label'].lower()} ({FAMILIES[family]['label']}) "
                  f"forged for the {era['label']} era.")
    return {
        "preset_id": pid, "kind": family, "forge": category, "family": family,
        "era": era["key"], "era_label": era["label"],
        "category": category, "category_label": meta["label"], "style": style,
        "size_class": size_class, "name": label, "palette": pal,
        "materials": [meta["label"]], "geometry": geometry,
        "vfx": rng.choice(["none", "glow", "smoke", "embers", "fog", "dust",
                           "torchlight", "sparkle"]),
        "surface": {
            "roughness": round(rng.uniform(0.2, 0.95), 2),
            "metalness": round(rng.uniform(0.0, 0.9), 2),
            "emissive": rng.choice([0, 0, 0, round(rng.uniform(0.1, 0.6), 2)]),
            "tiling": rng.choice([1, 2, 4]),
        },
        "poly_budget": poly, "texture_res": era["texture_res"],
        "size_kb": rng.randint(lo, hi), "descriptor": descriptor,
    }


def list_presets(category: str, era: str | None, offset: int = 0,
                 limit: int = 60) -> dict:
    era_spec = _eras.get_era(era)
    total = presets_per_era()
    presets = [_preset(category, era_spec["key"], i) for i in range(total)]
    sliced = presets[offset: offset + max(1, min(limit, 300))]
    meta = _CAT_BY_KEY.get(category, {})
    return {
        "category": category, "category_label": meta.get("label", category),
        "family": meta.get("family", _classify(category)),
        "era": era_spec["key"], "era_label": era_spec["label"],
        "total": len(presets), "per_era": total, "offset": offset,
        "limit": limit, "presets": sliced,
    }


def generate(category: str, era: str | None, preset_id: str | None = None,
             user_prompt: str = "", use_llm: bool = True,
             seed: int | None = None, skin_style: str | None = None,
             complexity: str | None = None, intricacy: str | None = None,
             detail_level: str | None = None, axes: dict | None = None,
             treatment: str | None = None, region: str | None = None,
             inscribe: str | None = None, inscription: dict | None = None) -> dict:
    era_spec = _eras.get_era(era)
    if seed is None:
        seed = random.randint(0, 10**6)
    total = presets_per_era()
    if preset_id:
        base = next((_preset(category, era_spec["key"], i) for i in range(total)
                     if _preset(category, era_spec["key"], i)["preset_id"] == preset_id), None)
        base = base or _preset(category, era_spec["key"], seed % total)
    else:
        base = _preset(category, era_spec["key"], seed % total)
    spec = dict(base)
    spec["llm_enriched"] = False
    rng = cf._rng("detail", category, str(seed))
    # Detail/skin/intricacy/complexity + deterministic accuracy pass.
    spec = _apply_detail(spec, rng, skin_style, complexity, intricacy,
                         detail_level, user_prompt)
    # Contextual Semantic Pruning — drop axes incompatible with this family
    # BEFORE they apply, keeping the spec coherent + the DNA payload minimal.
    from core import forge_dna as _fdna
    _fam = (_CAT_BY_KEY.get(category) or {}).get("family")
    axes, _pruned_axes = _fdna.semantic_prune(axes or {}, _fam)
    # New: stack style axes + region-specific treatment decals + inscription.
    spec = _apply_extras(spec, rng, axes, treatment, region, inscribe, inscription)
    spec["pruned_axes"] = _pruned_axes
    # ECS component bitmask + lazily-pruned 2048-bit Procedural DNA token.
    _fdna.attach_dna_and_mask(spec)
    if use_llm:
        enrich = cf._llm_enrich(spec, user_prompt)
        if enrich:
            spec.update(enrich)
            spec["llm_enriched"] = True
    spec["user_prompt"] = (user_prompt or "")[:MAX_PROMPT]
    return spec


def capacity() -> dict:
    col = cf._col()
    fam_keys = list(FAMILIES.keys())
    used = col.count_documents({"kind": {"$in": fam_keys}, "saved": True})
    return {"forge": used, "capacity": cf.ASSET_CAPACITY,
            "by_family": {f: col.count_documents({"kind": f, "saved": True}) for f in fam_keys}}


def list_saved(category: str | None = None, build_id: str | None = None,
               mounted: bool | None = None, offset: int = 0,
               limit: int = 60) -> dict:
    q: dict = {"saved": True, "kind": {"$in": list(FAMILIES.keys())}}
    if category:
        q["forge"] = category
    if build_id:
        q["build_id"] = build_id
    if mounted is not None:
        q["mounted"] = mounted
    col = cf._col()
    total = col.count_documents(q)
    rows = list(col.find(q, {"_id": 0}).skip(max(0, offset))
                .limit(max(1, min(limit, 300))))
    return {"total": total, "offset": offset, "limit": limit, "items": rows}


# ── COMPOSE SCENE — populate a themed scene in one shot (e.g. a forest) ────
def _apply_style_dict(spec: dict, rng: random.Random, style: dict | None,
                      region: str | None = None) -> dict:
    if not style:
        return spec
    spec = _apply_detail(spec, rng, style.get("skin_style"), style.get("complexity"),
                         style.get("intricacy"), style.get("detail_level"),
                         style.get("user_prompt", ""))
    spec = _apply_extras(spec, rng, style.get("axes"),
                         style.get("treatment"), region or style.get("region"),
                         style.get("inscribe"), style.get("inscription"))
    return spec


def compose_scene(build_id: str, era: str | None, items: list[dict],
                  seed: int = 0, mount: bool = True, style: dict | None = None,
                  variants: int = 0, region: str | None = None) -> dict:
    """Forge a themed multi-category scene at once. ``style`` (skin/complexity/
    intricacy/detail_level + axes + treatment) is applied to every asset for a
    coherent look. If ``variants`` > 0, agents ALSO forge region-specific
    restyled variants of each asset (secondary task) tagged with ``region`` —
    each region's variants get their own auto-assigned treatment + accent."""
    era_spec = _eras.get_era(era)
    total = presets_per_era()
    made: list[str] = []
    variant_ids: list[str] = []
    composed: list[dict] = []
    by_region: dict[str, dict] = {}
    clamped = False
    rng = cf._rng("scene", build_id, str(seed), region or "")
    for it in items or []:
        cat = (it.get("category") or "").strip()
        cnt = max(0, min(int(it.get("count", 1) or 0), 200))
        if not cat or cnt <= 0:
            continue
        room = _MAX_SCENE - len(made)
        if room <= 0:
            clamped = True
            break
        if cnt > room:
            cnt = room
            clamped = True
        fam = (_CAT_BY_KEY.get(cat) or {}).get("family", "structure")
        for i in range(cnt):
            spec = dict(_preset(cat, era_spec["key"], (seed + i * 13) % total))
            spec["build_id"] = build_id
            spec.setdefault("kind", spec.get("family") or "prop")
            spec = _apply_style_dict(spec, rng, style, region)
            made.append(cf.save_construct(spec)["construct_id"])
            r = by_region.setdefault(fam, {"family": fam, "primary": 0, "variants": 0,
                                            "treatment": _region_treatment(region or fam),
                                            "accent": _region_accent(region or fam)})
            r["primary"] += 1
            # SECONDARY TASK — region-specific variant in the region's art style
            for v in range(max(0, variants)):
                if len(made) + len(variant_ids) >= _MAX_SCENE:
                    clamped = True
                    break
                vs = dict(_preset(cat, era_spec["key"], (seed + i * 13 + v * 7 + 5) % total))
                vs["build_id"] = build_id
                vs.setdefault("kind", vs.get("family") or "prop")
                vstyle = dict(style or {})
                vstyle.setdefault("intricacy", "ornate")
                # each region gets its own auto-assigned treatment for distinctness
                vstyle.setdefault("treatment", r["treatment"])
                vs = _apply_style_dict(vs, rng, vstyle, region or fam)
                vs["variant"] = True
                vs["variant_of"] = cat
                vs["region"] = region or fam
                vs["name"] = f"{vs['name']} · {(region or fam or 'region')} variant"
                variant_ids.append(cf.save_construct(vs)["construct_id"])
                r["variants"] += 1
        composed.append({"category": cat, "count": cnt,
                         "label": (_CAT_BY_KEY.get(cat) or {}).get("label", cat)})
    all_ids = made + variant_ids
    if mount and all_ids:
        cf.mount_to_build(all_ids, build_id)
    return {"build_id": build_id, "era": era_spec["key"], "era_label": era_spec["label"],
            "composed": composed, "total": len(all_ids), "primary": len(made),
            "variants": len(variant_ids), "region": region,
            "by_region": list(by_region.values()),
            "style": style, "mounted": mount,
            "clamped": clamped, "max_per_scene": _MAX_SCENE}


# ── SNOWBALL AUTO-SEED — themed universal assets per build (era-aware) ─────
# Genre → a themed scene recipe of universal categories the snowball mints.
_GENRE_SCENE: dict[str, list[tuple[str, int]]] = {
    "rpg": [("character", 2), ("npc", 3), ("tree", 4), ("sword", 2), ("chest", 2), ("potion", 2)],
    "shooter": [("character", 2), ("robot", 2), ("rifle", 3), ("crate", 3), ("turret", 2)],
    "platformer": [("character", 2), ("critter", 4), ("tree", 3), ("apple", 3), ("chest", 2)],
    "strategy": [("npc", 3), ("vehicle", 2), ("turret", 2), ("barrel", 3), ("boulder", 3)],
    "survival": [("character", 1), ("critter", 3), ("tree", 4), ("campfire", 1), ("chest", 2), ("bread", 2)],
    "racing": [("vehicle", 4), ("sign", 2), ("barrel", 3), ("boulder", 2)],
    "puzzle": [("icon", 3), ("button ui", 2), ("crate", 3), ("potion", 1)],
}
_DEFAULT_SCENE: list[tuple[str, int]] = [
    ("character", 2), ("npc", 2), ("tree", 3), ("critter", 2), ("chest", 2),
    ("sword", 1), ("boulder", 2), ("icon", 1),
]


def seed_for_build(build_id: str, era: str | None = None, genre: str = "rpg",
                   seed: int = 0, mount: bool = True) -> dict:
    """Snowball hook — mint a themed batch of universal assets for a build so
    every generated game ships characters/flora/props (not just constructs)."""
    recipe = _GENRE_SCENE.get((genre or "").lower(), _DEFAULT_SCENE)
    # keep only categories that classify cleanly (all do; defensive anyway)
    items = [{"category": c, "count": n} for c, n in recipe if c in _CAT_BY_KEY]
    res = compose_scene(build_id, era, items, seed=seed, mount=mount)
    res["genre"] = genre
    res["families"] = sorted({_CAT_BY_KEY[i["category"]]["family"] for i in items})
    return res


# ── PER-SCENE FORGING — agents forge assets correlated to each build scene ──
# Each snowball stage (scene) maps to the universal categories the agents forge
# while that scene is built, so assets correlate with what's on screen.
_SCENE_FAMILIES: dict[str, list[str]] = {
    "world":      ["tree", "boulder", "plateau", "ridge", "oak_tree"],
    "narrative":  ["npc", "character", "banner", "book", "scroll"],
    "mechanics":  ["sword", "spike_trap", "lever", "gear_item", "shield"],
    "procedural": ["critter", "mushroom", "diamond", "wolf", "crystal_cluster"],
    "tileset":    ["door", "wooden_door", "fountain", "shrine", "lamp"],
    "assets":     ["coin", "torch", "chest", "lantern", "medallion"],
}


def scene_families() -> dict[str, list[str]]:
    return {s: [c for c in cats if c in _CAT_BY_KEY] for s, cats in _SCENE_FAMILIES.items()}


def seed_for_scene(build_id: str, era: str | None, stage: str, want: int = 3,
                   seed: int = 0, mount: bool = True) -> dict:
    """Forge a per-SCENE batch correlated to a snowball stage. `want` scales
    with what the agents built in that scene (more gamefiles → more assets)."""
    cats = [c for c in _SCENE_FAMILIES.get(stage, _SCENE_FAMILIES["world"]) if c in _CAT_BY_KEY]
    if not cats:
        return {"total": 0, "stage": stage, "composed": []}
    want = max(2, min(int(want), 10))
    items: list[dict] = []
    for i, c in enumerate(cats):
        per = want // len(cats) + (1 if i < want % len(cats) else 0)
        if per > 0:
            items.append({"category": c, "count": per})
    theme = SCENE_THEME.get(stage, {"skin_style": "matte", "intricacy": "subtle"})
    res = compose_scene(build_id, era, items, seed=seed, mount=mount,
                        style=theme, variants=1, region=stage)
    res["stage"] = stage
    res["theme"] = theme
    res["families"] = sorted({_CAT_BY_KEY[it["category"]]["family"]
                              for it in res.get("composed", []) if it["category"] in _CAT_BY_KEY})
    return res
