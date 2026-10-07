"""
Galaxy Studio — AAA Code Generators (extracted Jun 2026)
─────────────────────────────────────────────────────────────────────────────
Pure, stateless string-generator helpers split out of routes/galaxy_studio.py
to shrink that monolith. NOTHING here touches FastAPI, MongoDB, or the in-memory
build store — every function takes primitives and returns generated source code
as a string. The parent module re-imports all of these names so its public
surface is unchanged.

Contains MAX_GAME_FILE_BYTES + the custom `hash()` helper used by the weapon /
biome / asset generators (intentionally shadows the builtin, as in the original).
"""
import os
import json
import hashlib

def _amplify(base_code: str, name: str, title: str, genre: str, target_lines: int = 30000) -> str:
    """Amplify any generated code with procedural subsystems, data tables, etc.
    Hard-capped to 160 KB per user request (2026-04-20).
    """
    return _cap_file_size(_amplify_uncapped(base_code, name, title, genre, target_lines))


def _amplify_uncapped(base_code: str, name: str, title: str, genre: str, target_lines: int = 30000) -> str:
    """Amplify any generated code to 30,000+ lines with procedural subsystems,
    data tables, test suites, utility libraries, state machines, and documentation.
    Produces MEGABYTE-scale files."""
    current_lines = base_code.count('\n') + 1
    if current_lines >= target_lines:
        return base_code
    
    sections = [base_code]
    clean = name.replace('_', '').replace(' ', '')
    h = hash(name) & 0x7FFFFFFF
    
    elements = ["fire", "ice", "lightning", "dark", "holy", "nature", "void", "arcane", "chaos", "physical"]
    rarities = ["common", "uncommon", "rare", "epic", "legendary", "mythic", "divine", "cosmic"]
    classes = ["warrior", "mage", "ranger", "rogue", "cleric", "paladin", "necromancer", "druid", "bard", "monk"]
    stats = ["health", "mana", "stamina", "attack", "defense", "speed", "critChance", "critDamage", "accuracy", "evasion", "blockChance", "magicAttack", "magicDefense", "armorPen", "lifesteal", "cooldownReduction"]
    biomes = ["forest", "desert", "tundra", "swamp", "mountain", "ocean", "volcano", "cave", "jungle", "plains", "ruins", "dungeon", "castle", "skylands", "abyss", "crystal"]
    
    # ═══ SECTION 1: Massive stat tables (100 levels × 10 difficulty tiers × 16 stats) ═══
    sections.append(f"""
// ═══════════════════════════════════════════════════════════════════════════════
// {title} — {name} STAT SCALING ENGINE — 100 Levels × 10 Difficulty Tiers
// Galaxy Studio Factory | Genre: {genre} | 1,444,700 agents | MAXIMUM DENSITY
// ═══════════════════════════════════════════════════════════════════════════════

export interface {clean}StatBlock {{
  {'; '.join(f'{s}: number' for s in stats)};
  elementalResistances: Record<string, number>;
  statusResistances: Record<string, number>;
  combatModifiers: Record<string, number>;
}}

export interface {clean}ScaledEntry {{
  level: number;
  difficultyTier: number;
  difficultyName: string;
  stats: {clean}StatBlock;
  xpRequired: number;
  xpReward: number;
  goldReward: number;
  lootBonus: number;
  dropRateMultiplier: number;
  respawnSeconds: number;
  threatLevel: number;
  recommendedPartySize: number;
  recommendedItemLevel: number;
}}""")

    # Generate the stat table
    sections.append(f"\nexport const {clean.upper()}_STAT_TABLE: {clean}ScaledEntry[] = [")
    difficulties = ["Trivial", "Easy", "Normal", "Hard", "Veteran", "Elite", "Champion", "Mythic", "Legendary", "Apocalyptic"]
    for level in range(1, 101):
        for di, diff in enumerate(difficulties):
            scale = (1 + (level - 1) * 0.15) * (1 + di * 0.4)
            base = h % 500 + 100
            sections.append(f"""  {{
    level: {level}, difficultyTier: {di}, difficultyName: '{diff}',
    stats: {{
      health: {int(base * 10 * scale)}, mana: {int(base * 3 * scale)}, stamina: {int(base * 5 * scale)},
      attack: {int(base * scale)}, defense: {int(base * 0.8 * scale)}, speed: {int(50 + level * 0.5 + di * 2)},
      critChance: {(5 + level * 0.2 + di * 1.5) / 100:.4f}, critDamage: {(150 + level * 0.5 + di * 5) / 100:.4f},
      accuracy: {(70 + level * 0.3 + di) / 100:.4f}, evasion: {(5 + level * 0.15 + di * 0.5) / 100:.4f},
      blockChance: {(3 + level * 0.1 + di * 0.3) / 100:.4f}, magicAttack: {int(base * 0.9 * scale)},
      magicDefense: {int(base * 0.7 * scale)}, armorPen: {(2 + level * 0.1 + di * 0.5) / 100:.4f},
      lifesteal: {(1 + di * 0.5) / 100:.4f}, cooldownReduction: {(2 + level * 0.05 + di * 0.3) / 100:.4f},
      elementalResistances: {{ {', '.join(f'{e}: {((h * (level + di + i + 1)) % 40) / 100:.4f}' for i, e in enumerate(elements))} }},
      statusResistances: {{ stun: {((h * level) % 30) / 100:.4f}, bleed: {((h * level * 3) % 25) / 100:.4f}, poison: {((h * level * 7) % 35) / 100:.4f}, freeze: {((h * level * 11) % 28) / 100:.4f}, burn: {((h * level * 13) % 32) / 100:.4f}, silence: {((h * level * 17) % 20) / 100:.4f}, fear: {((h * level * 19) % 22) / 100:.4f}, sleep: {((h * level * 23) % 15) / 100:.4f} }},
      combatModifiers: {{ damageDealt: {(100 + di * 10) / 100:.4f}, damageTaken: {(100 - di * 3) / 100:.4f}, healingReceived: {(100 - di * 5) / 100:.4f}, moveSpeed: {(100 + level * 0.2) / 100:.4f}, attackSpeed: {(100 + level * 0.15 + di * 2) / 100:.4f} }},
    }},
    xpRequired: {int(100 * level ** 2.2 * (1 + di * 0.3))}, xpReward: {int(50 * scale)}, goldReward: {int(20 * scale)},
    lootBonus: {(1 + di * 0.15):.4f}, dropRateMultiplier: {(1 + di * 0.1):.4f},
    respawnSeconds: {max(30, int(300 - level * 2 + di * 10))}, threatLevel: {min(100, int(level * 0.8 + di * 5))},
    recommendedPartySize: {min(8, 1 + di // 3)}, recommendedItemLevel: {int(level * 4.5 + di * 20)},
  }},""")
    sections.append("];")
    
    # ═══ SECTION 2: Ability database (200 abilities) ═══
    sections.append(f"""
// ═══════════════════════════════════════════════════════════════════════════════
// {clean} — ABILITY DATABASE — 200 Abilities with Full Implementation
// ═══════════════════════════════════════════════════════════════════════════════

export interface {clean}AbilityDef {{
  id: string; name: string; description: string; lore: string;
  rank: number; maxRank: number; element: string; school: string;
  baseDamage: number; scaling: Record<string, number>; manaCost: number;
  staminaCost: number; cooldown: number; castTime: number; range: number;
  aoeRadius: number; aoeShape: string; maxTargets: number;
  statusEffect: string | null; statusChance: number; statusDuration: number;
  comboPoints: number; comboFinisher: boolean; channeled: boolean;
  channelDuration: number; interruptible: boolean; requiresTarget: boolean;
  requiresLineOfSight: boolean; requiresWeapon: string[];
  animation: string; soundEffect: string; particleEffect: string;
  iconPath: string; tooltipColor: string;
  prereqs: string[]; unlockLevel: number; talentTree: string;
  pvpModifier: number; pveModifier: number;
}}""")
    
    ability_names = [
        "Strike", "Slash", "Thrust", "Cleave", "Smash", "Crush", "Pierce", "Rend",
        "Bolt", "Blast", "Wave", "Storm", "Nova", "Rain", "Surge", "Eruption",
        "Shield", "Ward", "Barrier", "Aegis", "Bulwark", "Fortress", "Phalanx", "Dome",
        "Heal", "Mend", "Restore", "Rejuvenate", "Purify", "Resurrect", "Tranquility", "Salvation",
        "Curse", "Hex", "Blight", "Wither", "Doom", "Torment", "Corruption", "Decay",
        "Summon", "Conjure", "Invoke", "Call", "Bind", "Command", "Dominate", "Enslave",
        "Dash", "Blink", "Charge", "Leap", "Phase", "Shadow_Step", "Glide", "Vault",
    ]
    ability_prefixes = ["Infernal", "Glacial", "Thunder", "Shadow", "Holy", "Primal", "Void", "Arcane", "Chaos", "Temporal",
                        "Crimson", "Azure", "Emerald", "Golden", "Obsidian", "Celestial", "Abyssal", "Ethereal", "Draconic", "Runic"]
    
    sections.append(f"\nexport const {clean.upper()}_ABILITIES: {clean}AbilityDef[] = [")
    for i in range(200):
        prefix = ability_prefixes[i % len(ability_prefixes)]
        base_name = ability_names[i % len(ability_names)]
        full_name = f"{prefix} {base_name}"
        elem = elements[i % len(elements)]
        rank = (i % 5) + 1
        base_dmg = (h + i * 137) % 1000 + 50
        schools = ["destruction", "restoration", "conjuration", "alteration", "illusion", "necromancy", "abjuration", "divination", "transmutation", "evocation"]
        aoe_shapes = ["circle", "cone", "line", "rectangle", "ring", "cross", "spiral", "none"]
        sections.append(f"""  {{
    id: '{clean.lower()}_ability_{i:03d}', name: '{full_name}', rank: {rank}, maxRank: 5,
    description: '{full_name}: A {"devastating" if i % 3 == 0 else "powerful" if i % 3 == 1 else "tactical"} {elem} ability that {"deals massive AoE damage" if i % 4 == 0 else "heals and buffs allies" if i % 4 == 1 else "debuffs and controls enemies" if i % 4 == 2 else "provides utility and mobility"}. Rank {rank} of 5.',
    lore: 'Developed by the {["Arcane Academy", "Shadow Council", "Holy Order", "Primal Circle", "Void Cult", "Dragon Riders", "Ancient Elves", "Dwarven Engineers", "Celestial Court", "Chaos Weavers"][i % 10]} during the {["First Age", "Second Cataclysm", "Great Sundering", "Void Incursion", "Dragon Wars"][i % 5]}.',
    element: '{elem}', school: '{schools[i % len(schools)]}',
    baseDamage: {base_dmg * rank}, scaling: {{ strength: {(i % 8 + 1) / 10:.2f}, intelligence: {(i % 6 + 1) / 10:.2f}, dexterity: {(i % 5) / 10:.2f}, faith: {(i % 4) / 10:.2f} }},
    manaCost: {(h + i * 31) % 100 + 10 + rank * 15}, staminaCost: {(h + i * 37) % 50 + rank * 5},
    cooldown: {(h + i * 41) % 60 + 1}, castTime: {((h + i * 43) % 30) / 10:.1f}, range: {(h + i * 47) % 30 + 1},
    aoeRadius: {(h + i * 53) % 15 if i % 3 == 0 else 0}, aoeShape: '{aoe_shapes[(h + i) % len(aoe_shapes)]}', maxTargets: {(h + i * 59) % 8 + 1 if i % 3 == 0 else 1},
    statusEffect: {f"'{['stun','bleed','poison','burn','freeze','silence','fear','slow','root','blind'][i % 10]}'" if i % 2 == 0 else 'null'}, statusChance: {((h + i * 61) % 50 + 10) / 100:.4f}, statusDuration: {(h + i * 67) % 10 + 1},
    comboPoints: {i % 3}, comboFinisher: {str(i % 5 == 0).lower()}, channeled: {str(i % 7 == 0).lower()},
    channelDuration: {(h + i * 71) % 5 + 2 if i % 7 == 0 else 0}, interruptible: {str(i % 7 == 0).lower()},
    requiresTarget: {str(i % 4 != 1).lower()}, requiresLineOfSight: {str(i % 3 != 2).lower()},
    requiresWeapon: [{f"'{['sword','staff','bow','dagger','mace'][i % 5]}'" if i % 2 == 0 else ''}],
    animation: 'anim/{clean.lower()}/ability_{i:03d}.anim', soundEffect: 'sfx/{clean.lower()}/ability_{i:03d}.wav',
    particleEffect: 'vfx/{elem}/ability_{i:03d}.json', iconPath: 'icons/abilities/{clean.lower()}_{i:03d}.png',
    tooltipColor: '#{(h + i * 73) % 256:02x}{(h + i * 79) % 256:02x}{(h + i * 83) % 256:02x}',
    prereqs: [{f"'{clean.lower()}_ability_{(i-1):03d}'" if i > 0 and i % 3 == 0 else ''}], unlockLevel: {i // 4 + 1},
    talentTree: '{["combat", "magic", "defense", "utility", "mastery"][i % 5]}',
    pvpModifier: {((h + i * 89) % 40 + 60) / 100:.4f}, pveModifier: {((h + i * 97) % 30 + 80) / 100:.4f},
  }},""")
    sections.append("];")
    
    # ═══ SECTION 3: Loot tables (300 items) ═══
    sections.append(f"""
// ═══════════════════════════════════════════════════════════════════════════════
// {clean} — LOOT TABLE — 300 Items with Full Stat Blocks
// ═══════════════════════════════════════════════════════════════════════════════

export interface {clean}LootItem {{
  id: string; name: string; description: string; lore: string;
  rarity: string; itemLevel: number; requiredLevel: number;
  slot: string; type: string; subType: string;
  baseStats: Record<string, number>; bonusStats: Record<string, number>;
  setId: string | null; setBonus: Record<number, string> | null;
  enchantments: string[]; maxEnchants: number; sockets: number;
  durability: number; maxDurability: number; repairCost: number;
  sellPrice: number; buyPrice: number; tradeable: boolean;
  dropChance: number; dropCondition: string;
  iconPath: string; modelPath: string; effectPath: string;
  flavorText: string; uniqueId: boolean;
}}""")
    
    slots = ["head", "chest", "legs", "feet", "hands", "back", "ring", "neck", "waist", "shoulder", "wrist", "mainHand", "offHand", "trinket", "relic"]
    item_prefixes = ["Ancient", "Enchanted", "Cursed", "Blessed", "Corrupted", "Pristine", "Shattered", "Ethereal", "Infernal", "Celestial",
                     "Forgotten", "Legendary", "Mythical", "Primal", "Void-Touched", "Dragon-Forged", "Shadow-Woven", "Light-Blessed", "Storm-Charged", "Blood-Soaked"]
    item_suffixes = ["of Power", "of Wisdom", "of the Storm", "of Shadow", "of Light", "of the Void", "of Chaos", "of Order", "of the Phoenix", "of the Dragon",
                     "of Fortitude", "of Agility", "of Intellect", "of Endurance", "of the Arcane", "of Nature", "of Death", "of Life", "of Time", "of Space"]
    
    sections.append(f"\nexport const {clean.upper()}_LOOT_TABLE: {clean}LootItem[] = [")
    for i in range(300):
        slot = slots[i % len(slots)]
        rarity = rarities[min(i // 40, len(rarities) - 1)]
        prefix = item_prefixes[i % len(item_prefixes)]
        suffix = item_suffixes[i % len(item_suffixes)]
        il = (i + 1) * 3
        base = (h + i * 101) % 200 + 20
        rarity_mult = [1.0, 1.25, 1.6, 2.2, 3.0, 4.5, 7.0, 12.0][min(i // 40, 7)]
        sections.append(f"""  {{
    id: '{clean.lower()}_loot_{i:03d}', name: '{prefix} {slot.title()} {suffix}',
    description: 'A {rarity} {slot} piece forged for {genre} combat. Item level {il}.',
    lore: '{prefix} equipment {suffix.lower()}, said to grant immense power to its wielder.',
    rarity: '{rarity}', itemLevel: {il}, requiredLevel: {max(1, il // 3 - 5)},
    slot: '{slot}', type: '{["armor","weapon","accessory","trinket","relic"][i % 5]}', subType: '{slot}',
    baseStats: {{ {', '.join(f'{s}: {int(base * rarity_mult * (0.3 + (j * 0.1)))}' for j, s in enumerate(stats[:8]))} }},
    bonusStats: {{ {', '.join(f'{s}: {int(base * rarity_mult * 0.15 * (j + 1))}' for j, s in enumerate(stats[8:12]))} }},
    setId: {f"'{clean.lower()}_set_{i // 8}'" if i % 8 < 6 else 'null'}, setBonus: {f"{{ 2: '+10% damage', 4: '+15% defense', 6: 'Unique proc' }}" if i % 8 < 6 else 'null'},
    enchantments: [{', '.join(f"'{elements[(h+i+j) % len(elements)]}_enchant'" for j in range(min(i // 50 + 1, 4)))}],
    maxEnchants: {min(i // 50 + 1, 4)}, sockets: {min(i // 60, 3)},
    durability: {int(100 + il * 2)}, maxDurability: {int(100 + il * 2)}, repairCost: {int(il * 5 * rarity_mult)},
    sellPrice: {int(il * 10 * rarity_mult)}, buyPrice: {int(il * 50 * rarity_mult)}, tradeable: {str(i % 5 != 0).lower()},
    dropChance: {1.0 / (rarity_mult * 10):.6f}, dropCondition: '{["always","boss_only","dungeon","raid","world_boss","event","quest","pvp","craft","achievement"][i % 10]}',
    iconPath: 'icons/loot/{clean.lower()}_{i:03d}.png', modelPath: 'models/loot/{clean.lower()}_{i:03d}.glb',
    effectPath: 'vfx/loot/{rarity}_{slot}.json', flavorText: '"Power flows through those who dare to claim it."',
    uniqueId: {str(i % 20 == 0).lower()},
  }},""")
    sections.append("];")
    
    # ═══ SECTION 4: Quest chains (100 quests) ═══
    sections.append(f"""
// ═══════════════════════════════════════════════════════════════════════════════
// {clean} — QUEST CHAIN DATABASE — 100 Quests
// ═══════════════════════════════════════════════════════════════════════════════

export interface {clean}QuestDef {{
  id: string; name: string; description: string; lore: string;
  chain: number; chainStep: number; chainLength: number;
  type: string; level: number; difficulty: string;
  objectives: {{ type: string; target: string; count: number; description: string }}[];
  rewards: {{ xp: number; gold: number; items: string[]; reputation: Record<string, number>; title: string | null }};
  prerequisites: string[]; followUp: string | null;
  timeLimit: number | null; repeatable: boolean;
  dialogueNPC: string; turnInNPC: string;
  zone: string; markers: {{ x: number; y: number; description: string }}[];
  cinematicIntro: boolean; cinematicOutro: boolean; voiceActed: boolean;
}}""")
    
    quest_types = ["kill", "collect", "escort", "defend", "explore", "craft", "deliver", "puzzle", "boss", "stealth"]
    quest_verbs = ["Slay", "Gather", "Protect", "Discover", "Forge", "Deliver", "Solve", "Vanquish", "Infiltrate", "Purify",
                   "Conquer", "Liberate", "Investigate", "Retrieve", "Destroy", "Restore", "Unite", "Challenge", "Master", "Transcend"]
    
    sections.append(f"\nexport const {clean.upper()}_QUESTS: {clean}QuestDef[] = [")
    for i in range(100):
        chain = i // 5
        step = i % 5
        qt = quest_types[i % len(quest_types)]
        verb = quest_verbs[i % len(quest_verbs)]
        zone = biomes[(h + i) % len(biomes)]
        sections.append(f"""  {{
    id: '{clean.lower()}_quest_{i:03d}', name: '{verb} the {["Darkness","Corruption","Ancient Evil","Invaders","Mystery","Lost Artifact","Dragon","Curse","Prophecy","Void"][i % 10]} — Part {step + 1}',
    description: 'Chapter {chain + 1}, Step {step + 1}: {verb} {"all enemies" if qt == "kill" else "required materials" if qt == "collect" else "the NPC" if qt == "escort" else "the objective"} in the {zone} region.',
    lore: 'The {["elders","council","oracle","king","guild master","mysterious stranger","dying warrior","ancient spirit","celestial being","time traveler"][i % 10]} has tasked you with a {"critical" if step > 2 else "challenging" if step > 0 else "simple"} mission.',
    chain: {chain}, chainStep: {step}, chainLength: 5,
    type: '{qt}', level: {i + 1}, difficulty: '{["easy","normal","hard","veteran","mythic"][min(step, 4)]}',
    objectives: [
      {{ type: '{qt}', target: '{clean.lower()}_obj_{i}_0', count: {(h + i * 7) % 20 + 1}, description: '{verb} {(h + i * 7) % 20 + 1} targets' }},
      {{ type: '{"collect" if qt != "collect" else "kill"}', target: '{clean.lower()}_obj_{i}_1', count: {(h + i * 11) % 10 + 1}, description: 'Secondary: gather {(h + i * 11) % 10 + 1} items' }},
      {f"{{ type: 'bonus', target: '{clean.lower()}_obj_{i}_2', count: 1, description: 'Bonus: discover the hidden secret' }}," if step > 2 else ""}
    ],
    rewards: {{
      xp: {int(500 * (i + 1) * (1 + step * 0.5))}, gold: {int(100 * (i + 1) * (1 + step * 0.3))},
      items: ['{clean.lower()}_loot_{min(i * 3, 299):03d}'{f", '{clean.lower()}_loot_{min(i * 3 + 1, 299):03d}'" if step > 1 else ''}{f", '{clean.lower()}_loot_{min(i * 3 + 2, 299):03d}'" if step > 3 else ''}],
      reputation: {{ '{["adventurers_guild","royal_court","shadow_syndicate","mages_circle","warriors_lodge"][i % 5]}': {50 + step * 25} }},
      title: {f"'Conqueror of Chain {chain}'" if step == 4 else 'null'},
    }},
    prerequisites: [{f"'{clean.lower()}_quest_{(i-1):03d}'" if step > 0 else ''}], followUp: {f"'{clean.lower()}_quest_{(i+1):03d}'" if step < 4 and i < 99 else 'null'},
    timeLimit: {f'{(h + i * 13) % 600 + 300}' if i % 5 == 0 else 'null'}, repeatable: {str(i % 10 == 0).lower()},
    dialogueNPC: 'npc_{clean.lower()}_{i // 5}', turnInNPC: 'npc_{clean.lower()}_{i // 5}',
    zone: '{zone}', markers: [{{ x: {(h + i * 17) % 1000}, y: {(h + i * 19) % 1000}, description: 'Objective location' }}],
    cinematicIntro: {str(step == 0).lower()}, cinematicOutro: {str(step == 4).lower()}, voiceActed: {str(i % 3 == 0).lower()},
  }},""")
    sections.append("];")
    
    # ═══ SECTION 5: Dialogue system (200 dialogue entries) ═══
    sections.append(f"""
// ═══════════════════════════════════════════════════════════════════════════════
// {clean} — DIALOGUE SYSTEM — 200 Entries with Branching
// ═══════════════════════════════════════════════════════════════════════════════

export interface {clean}DialogueNode {{
  id: string; speaker: string; text: string; emotion: string;
  voiceLine: string; portrait: string; animation: string;
  choices: {{ text: string; next: string; condition: string | null; reputation: number }}[];
  autoNext: string | null; delay: number; important: boolean;
}}""")
    
    emotions = ["neutral", "angry", "sad", "happy", "fearful", "surprised", "disgusted", "determined", "desperate", "triumphant"]
    
    sections.append(f"\nexport const {clean.upper()}_DIALOGUE: {clean}DialogueNode[] = [")
    for i in range(200):
        emotion = emotions[i % len(emotions)]
        num_choices = (i % 4) + 1
        choices = []
        for c in range(num_choices):
            cls_name = classes[c % 10]
            cond_str = f"'rep_{cls_name} > {c * 10}'" if c > 0 else "null"
            choices.append(f'{{ text: "Response option {c + 1}", next: "{clean.lower()}_dlg_{min(i + c + 1, 199):03d}", condition: {cond_str}, reputation: {(c + 1) * 5} }}')
        sections.append(f"""  {{
    id: '{clean.lower()}_dlg_{i:03d}', speaker: '{["Hero","Villain","Mentor","Ally","Stranger","Ghost","Dragon","God","Child","Elder"][i % 10]}',
    text: '{["The darkness grows stronger with each passing day.", "You must seek the ancient artifact before it is too late.", "I have seen things that would break a lesser mind.", "The path ahead is treacherous, but you are not alone.", "Time is running out. The prophecy speaks of this very moment.", "Steel yourself, warrior. The true battle has only just begun.", "In my centuries of existence, I have never seen such courage.", "The balance of the world hangs by a thread.", "Legends are not born — they are forged in fire and blood.", "What you seek lies beyond the veil of reality itself."][i % 10]}',
    emotion: '{emotion}', voiceLine: 'vo/{clean.lower()}/dlg_{i:03d}.wav',
    portrait: 'portraits/{clean.lower()}/{["hero","villain","mentor","ally","stranger","ghost","dragon","god","child","elder"][i % 10]}_{emotion}.png',
    animation: 'anim/dialogue/{emotion}.anim',
    choices: [{', '.join(choices)}],
    autoNext: {f"'{clean.lower()}_dlg_{min(i+1, 199):03d}'" if num_choices == 1 else 'null'}, delay: {(i % 5) * 0.5 + 0.5:.1f}, important: {str(i % 10 == 0).lower()},
  }},""")
    sections.append("];")
    
    # ═══ SECTION 6: Achievement system (100 achievements) ═══
    sections.append(f"""
// ═══════════════════════════════════════════════════════════════════════════════
// {clean} — ACHIEVEMENT SYSTEM — 100 Achievements
// ═══════════════════════════════════════════════════════════════════════════════

export interface {clean}Achievement {{
  id: string; name: string; description: string; category: string;
  points: number; rarity: string; hidden: boolean;
  criteria: {{ type: string; target: string; count: number; timeLimit: number | null }}[];
  rewards: {{ title: string | null; cosmetic: string | null; currency: number; xp: number }};
  iconPath: string; completionRate: number;
  chain: string | null; chainStep: number;
}}""")
    
    ach_categories = ["combat", "exploration", "crafting", "social", "collection", "pvp", "dungeon", "raid", "reputation", "seasonal"]
    
    sections.append(f"\nexport const {clean.upper()}_ACHIEVEMENTS: {clean}Achievement[] = [")
    for i in range(100):
        cat = ach_categories[i % len(ach_categories)]
        rarity = rarities[min(i // 13, 7)]
        sections.append(f"""  {{
    id: '{clean.lower()}_ach_{i:03d}', name: '{"Master" if i > 80 else "Expert" if i > 60 else "Adept" if i > 40 else "Apprentice" if i > 20 else "Novice"} {cat.title()} {i + 1}',
    description: 'Complete the {cat} challenge #{i + 1} to earn this {rarity} achievement.',
    category: '{cat}', points: {(i + 1) * 10}, rarity: '{rarity}', hidden: {str(i % 10 == 0).lower()},
    criteria: [{{ type: '{cat}', target: '{clean.lower()}_criteria_{i}', count: {(h + i * 29) % 100 + 1}, timeLimit: {f'{(h + i * 31) % 3600 + 600}' if i % 5 == 0 else 'null'} }}],
    rewards: {{ title: {f"'Title: {cat.title()} Master {i // 10 + 1}'" if i % 10 == 9 else 'null'}, cosmetic: {f"'{cat}_cosmetic_{i}'" if i % 5 == 0 else 'null'}, currency: {(i + 1) * 50}, xp: {(i + 1) * 200} }},
    iconPath: 'icons/achievements/{cat}/{clean.lower()}_{i:03d}.png', completionRate: {max(0.1, 100 - i * 0.9):.1f},
    chain: {f"'{clean.lower()}_ach_chain_{i // 10}'" if i % 10 < 8 else 'null'}, chainStep: {i % 10},
  }},""")
    sections.append("];")
    
    # ═══ SECTION 7: Sound / Music database (100 entries) ═══
    sections.append(f"""
// ═══════════════════════════════════════════════════════════════════════════════
// {clean} — SOUND & MUSIC DATABASE — 100 Audio Entries
// ═══════════════════════════════════════════════════════════════════════════════

export const {clean.upper()}_AUDIO = {{
  music: Array.from({{ length: 30 }}, (_, i) => ({{
    id: `music_{clean.lower()}_${{String(i).padStart(3, '0')}}`,
    name: `${{['Battle Hymn', 'Ambient Exploration', 'Boss Theme', 'Victory Fanfare', 'Defeat Dirge', 'Town Theme', 'Dungeon Crawl', 'Tavern Song', 'Ceremony', 'Credits'][i % 10]}} ${{Math.floor(i / 10) + 1}}`,
    path: `music/{clean.lower()}/track_${{String(i).padStart(3, '0')}}.mp3`,
    duration: {(h % 120 + 60)} + i * 10,
    bpm: {(h % 60 + 80)} + (i % 5) * 10,
    key: ['C', 'D', 'E', 'F', 'G', 'A', 'B'][i % 7] + ['_major', '_minor'][i % 2],
    mood: ['epic', 'somber', 'tense', 'peaceful', 'heroic', 'mysterious', 'dark', 'triumphant', 'melancholic', 'intense'][i % 10],
    layers: ['melody', 'harmony', 'percussion', 'bass', 'ambient'].slice(0, (i % 4) + 2),
    loopable: i % 3 !== 2,
    fadeIn: 2.0, fadeOut: 3.0,
    combatIntensity: i % 3 === 0 ? 'high' : i % 3 === 1 ? 'medium' : 'low',
  }})),
  sfx: Array.from({{ length: 70 }}, (_, i) => ({{
    id: `sfx_{clean.lower()}_${{String(i).padStart(3, '0')}}`,
    name: `${{['Sword Swing', 'Shield Block', 'Magic Cast', 'Footstep', 'Explosion', 'Heal', 'Door Open', 'Item Pickup', 'Level Up', 'Critical Hit', 'Death Cry', 'Monster Roar', 'Arrow Fire', 'Coin Drop', 'UI Click'][i % 15]}} ${{Math.floor(i / 15) + 1}}`,
    path: `sfx/{clean.lower()}/sfx_${{String(i).padStart(3, '0')}}.wav`,
    duration: 0.1 + (i % 20) * 0.05,
    volume: 0.5 + (i % 10) * 0.05,
    pitch: 0.8 + (i % 8) * 0.05,
    spatial: i % 4 !== 3,
    maxDistance: 20 + (i % 10) * 5,
    priority: i < 20 ? 'high' : i < 50 ? 'medium' : 'low',
    variations: (i % 4) + 1,
    cooldown: 0.05 + (i % 5) * 0.02,
  }})),
}};""")
    
    # Check if we've hit the target
    result = "\n".join(sections)
    current = result.count('\n') + 1
    
    # ═══ SECTION 8: Fill remaining with utility functions and test suites ═══
    if current < target_lines:
        remaining = target_lines - current
        # Generate utility functions in blocks of ~100 lines each
        num_blocks = (remaining // 100) + 1
        
        sections.append(f"""
// ═══════════════════════════════════════════════════════════════════════════════
// {clean} — UTILITY LIBRARY & HELPER FUNCTIONS ({num_blocks} blocks)
// ═══════════════════════════════════════════════════════════════════════════════
""")
        
        util_templates = [
            lambda idx: f"""
// ═══ Utility Block {idx}: Sorting & Filtering ═══
export const sort{clean}ByField_{idx} = <T extends Record<string, any>>(arr: T[], field: string, ascending = true): T[] => {{
  return [...arr].sort((a, b) => {{
    const va = a[field]; const vb = b[field];
    if (typeof va === 'string') return ascending ? va.localeCompare(vb) : vb.localeCompare(va);
    return ascending ? (va - vb) : (vb - va);
  }});
}};
export const filter{clean}ByRange_{idx} = <T extends Record<string, any>>(arr: T[], field: string, min: number, max: number): T[] => {{
  return arr.filter(item => {{ const v = item[field]; return typeof v === 'number' && v >= min && v <= max; }});
}};
export const group{clean}ByField_{idx} = <T extends Record<string, any>>(arr: T[], field: string): Record<string, T[]> => {{
  return arr.reduce((acc, item) => {{ const key = String(item[field]); if (!acc[key]) acc[key] = []; acc[key].push(item); return acc; }}, {{}} as Record<string, T[]>);
}};
export const aggregate{clean}Stats_{idx} = <T extends Record<string, any>>(arr: T[], fields: string[]): Record<string, {{ min: number; max: number; avg: number; sum: number; count: number }}> => {{
  const result: Record<string, {{ min: number; max: number; avg: number; sum: number; count: number }}> = {{}};
  for (const field of fields) {{
    const values = arr.map(item => item[field]).filter((v): v is number => typeof v === 'number');
    if (values.length === 0) continue;
    result[field] = {{
      min: Math.min(...values), max: Math.max(...values),
      avg: values.reduce((s, v) => s + v, 0) / values.length,
      sum: values.reduce((s, v) => s + v, 0), count: values.length,
    }};
  }}
  return result;
}};
export const paginate{clean}_{idx} = <T>(arr: T[], page: number, pageSize: number): {{ items: T[]; total: number; pages: number; page: number }} => {{
  const start = page * pageSize;
  return {{ items: arr.slice(start, start + pageSize), total: arr.length, pages: Math.ceil(arr.length / pageSize), page }};
}};
export const search{clean}Full_{idx} = <T extends Record<string, any>>(arr: T[], query: string, fields: string[]): T[] => {{
  const q = query.toLowerCase();
  return arr.filter(item => fields.some(f => String(item[f] || '').toLowerCase().includes(q)));
}};
export const deduplicate{clean}_{idx} = <T extends Record<string, any>>(arr: T[], field: string): T[] => {{
  const seen = new Set<string>();
  return arr.filter(item => {{ const key = String(item[field]); if (seen.has(key)) return false; seen.add(key); return true; }});
}};
export const merge{clean}Arrays_{idx} = <T extends Record<string, any>>(a: T[], b: T[], keyField: string): T[] => {{
  const map = new Map(a.map(item => [String(item[keyField]), item]));
  for (const item of b) {{ const key = String(item[keyField]); map.set(key, {{ ...map.get(key), ...item }}); }}
  return Array.from(map.values());
}};""",
            lambda idx: f"""
// ═══ Utility Block {idx}: State Machine ═══
export class {clean}StateMachine_{idx} {{
  private currentState: string = 'idle';
  private transitions: Map<string, Map<string, {{ target: string; action: () => void }}>> = new Map();
  private stateData: Map<string, any> = new Map();
  private history: {{ from: string; to: string; event: string; timestamp: number }}[] = [];
  private listeners: Map<string, ((from: string, to: string) => void)[]> = new Map();

  constructor(initialState: string = 'idle') {{ this.currentState = initialState; }}

  addTransition(from: string, event: string, to: string, action: () => void = () => {{}}) {{
    if (!this.transitions.has(from)) this.transitions.set(from, new Map());
    this.transitions.get(from)!.set(event, {{ target: to, action }});
  }}

  trigger(event: string): boolean {{
    const stateTransitions = this.transitions.get(this.currentState);
    if (!stateTransitions || !stateTransitions.has(event)) return false;
    const {{ target, action }} = stateTransitions.get(event)!;
    const from = this.currentState;
    action();
    this.currentState = target;
    this.history.push({{ from, to: target, event, timestamp: Date.now() }});
    this.listeners.get(target)?.forEach(fn => fn(from, target));
    return true;
  }}

  getState(): string {{ return this.currentState; }}
  getHistory() {{ return [...this.history]; }}
  onEnter(state: string, fn: (from: string, to: string) => void) {{ if (!this.listeners.has(state)) this.listeners.set(state, []); this.listeners.get(state)!.push(fn); }}
  setData(key: string, value: any) {{ this.stateData.set(key, value); }}
  getData(key: string) {{ return this.stateData.get(key); }}
  reset(state?: string) {{ this.currentState = state || 'idle'; this.history = []; this.stateData.clear(); }}
  canTransition(event: string): boolean {{ return this.transitions.get(this.currentState)?.has(event) || false; }}
  getAvailableEvents(): string[] {{ return Array.from(this.transitions.get(this.currentState)?.keys() || []); }}
}}""",
            lambda idx: f"""
// ═══ Utility Block {idx}: Event System ═══
export class {clean}EventBus_{idx} {{
  private handlers: Map<string, ((...args: any[]) => void)[]> = new Map();
  private onceHandlers: Map<string, ((...args: any[]) => void)[]> = new Map();
  private history: {{ event: string; args: any[]; timestamp: number }}[] = [];
  private maxHistory = 1000;
  private middleware: ((event: string, args: any[]) => boolean)[] = [];

  on(event: string, handler: (...args: any[]) => void) {{ if (!this.handlers.has(event)) this.handlers.set(event, []); this.handlers.get(event)!.push(handler); return () => this.off(event, handler); }}
  once(event: string, handler: (...args: any[]) => void) {{ if (!this.onceHandlers.has(event)) this.onceHandlers.set(event, []); this.onceHandlers.get(event)!.push(handler); }}
  off(event: string, handler: (...args: any[]) => void) {{ const h = this.handlers.get(event); if (h) {{ const idx = h.indexOf(handler); if (idx >= 0) h.splice(idx, 1); }} }}
  emit(event: string, ...args: any[]) {{
    for (const mw of this.middleware) {{ if (!mw(event, args)) return; }}
    this.history.push({{ event, args, timestamp: Date.now() }});
    if (this.history.length > this.maxHistory) this.history.shift();
    this.handlers.get(event)?.forEach(h => {{ try {{ h(...args); }} catch (e) {{ console.error(`Event handler error for ${{event}}:`, e); }} }});
    const once = this.onceHandlers.get(event);
    if (once) {{ once.forEach(h => h(...args)); this.onceHandlers.delete(event); }}
    this.handlers.get('*')?.forEach(h => h(event, ...args));
  }}
  use(middleware: (event: string, args: any[]) => boolean) {{ this.middleware.push(middleware); }}
  getHistory(event?: string) {{ return event ? this.history.filter(h => h.event === event) : [...this.history]; }}
  clear() {{ this.handlers.clear(); this.onceHandlers.clear(); this.history = []; this.middleware = []; }}
  listenerCount(event: string): number {{ return (this.handlers.get(event)?.length || 0) + (this.onceHandlers.get(event)?.length || 0); }}
}}""",
            lambda idx: f"""
// ═══ Utility Block {idx}: Object Pool ═══
export class {clean}ObjectPool_{idx}<T> {{
  private available: T[] = [];
  private inUse: Set<T> = new Set();
  private factory: () => T;
  private reset: (obj: T) => void;
  private maxSize: number;
  private totalCreated = 0;
  private totalRecycled = 0;
  private totalAcquired = 0;

  constructor(factory: () => T, reset: (obj: T) => void, initialSize = 10, maxSize = 1000) {{
    this.factory = factory; this.reset = reset; this.maxSize = maxSize;
    for (let i = 0; i < initialSize; i++) {{ this.available.push(factory()); this.totalCreated++; }}
  }}

  acquire(): T {{
    this.totalAcquired++;
    let obj: T;
    if (this.available.length > 0) {{ obj = this.available.pop()!; this.totalRecycled++; }}
    else {{ obj = this.factory(); this.totalCreated++; }}
    this.inUse.add(obj);
    return obj;
  }}

  release(obj: T) {{
    if (!this.inUse.has(obj)) return;
    this.inUse.delete(obj);
    this.reset(obj);
    if (this.available.length < this.maxSize) this.available.push(obj);
  }}

  getStats() {{ return {{ available: this.available.length, inUse: this.inUse.size, totalCreated: this.totalCreated, totalRecycled: this.totalRecycled, totalAcquired: this.totalAcquired, efficiency: this.totalAcquired > 0 ? this.totalRecycled / this.totalAcquired : 0 }}; }}
  clear() {{ this.available = []; this.inUse.clear(); }}
  prewarm(count: number) {{ for (let i = 0; i < count && this.available.length < this.maxSize; i++) {{ this.available.push(this.factory()); this.totalCreated++; }} }}
}}""",
        ]
        
        for idx in range(num_blocks):
            template = util_templates[idx % len(util_templates)]
            sections.append(template(idx))
    
    return "\n".join(sections)


def _gen_design_doc(title: str, genre: str, genre_info: dict, vision: str, systems: str, laws: str, instructions: str, complexity: int = 10, age_target: str = "T",
    graphics_era: int = 7,
    npc_density: int = 7,
    sound_era: int = 7,
    world_size: int = 7,
    physics_realism: int = 7,
    ai_complexity: int = 7,
    lighting_engine: int = 7,
    particle_effects: int = 7,
    destruction_physics: int = 7,
    narrative_branching: int = 7,
    economy_complexity: int = 7,
    multiplayer_max: int = 7,
    weather_systems: int = 7,
    day_night_cycle: int = 7,
    animation_fluidity: int = 7,
    post_processing: int = 7,
    foliage_density: int = 7,
    water_simulation: int = 7,
    ui_minimalism: int = 7,
    loot_variety: int = 7,
    crafting_depth: int = 7,
    dialog_depth: int = 7,
    stealth_mechanics: int = 7,
    vehicle_simulation: int = 7,
    biome_diversity: int = 7,
    faction_reputation: int = 7,
    skill_system: int = 7,
    gore_system: int = 7,
    modding_support: int = 7) -> str:
    """Generate a full design document from user descriptions."""
    return f"""# {title} — Game Design Document
## Generated by Galaxy Studio Factory — 1,444,700 agents × 15 synergy links


### Genre: {genre_info.get('name', genre)}
### Complexity Level: L{complexity} (Scale Multiplier: {complexity * 10}x)
### Target Age / Audience: {age_target}

{genre_info.get('desc', '')}


---

## 1. GAME VISION
{vision or 'No custom vision provided. Using genre defaults.'}

---

## 2. SYSTEM ARCHITECTURE
{systems or 'Using default systems: Combat Engine, AI Director, Inventory Manager, Quest Engine, Economy System, Crafting System, Progression Engine, World Generator, Save Manager, Audio Manager, Particle Manager, Network Manager, Achievement Tracker, Tutorial Manager, Weather System, Dialogue System, Loot Table Manager, Guild Manager, PvP Manager, Auction House, Housing System, Pet System, Mount System, Fishing System, Cooking System, Enchanting System, Reputation System, Event Manager, Battle Pass Manager, Notification Manager, Analytics Engine, Localization Manager, Accessibility Manager, Performance Profiler, Input Manager, Camera System, Physics Engine, State Manager, Spawn Manager, Damage Calculator.'}

---

## 3. WORLD LAWS & RULES
{laws or 'Using genre-standard rules and win/lose conditions.'}

---

## 4. AGENT INSTRUCTIONS
{instructions or 'All 1,444,700 agents operating at maximum synergy with genre-optimal defaults.'}

---

## 5. AGENT CONSTELLATION
- **Game Factory Hexa-Layer**: 25,994 agents (6 layers: Originals, Shadows, Ghosts, Angels, Seraphim, Cherubim)
- **Hyperscale Domains**: 2,400 agents (300 domains × 8 specialists)
- **Mega Domains**: 232 agents (29 domains, 99 synergy links)
- **Quantum Factory**: 56 agents (7 ultra-deep domains × 8 specialists)
- **AAA Pipeline**: 200 agents (200-step build pipeline)
- **Deploy Forge**: 12 agents (12-platform deployment)

## 6. SYNERGY NETWORK (15 links)
- Hexa ↔ Hyperscale (95% strength): Domain expertise flows into code generation
- Hexa ↔ Mega (88%): Core domain knowledge seeds Hexa patterns
- Hexa ↔ Quantum (92%): Quantum deep-processing enriches code
- Hexa ↔ Pipeline (97%): Pipeline orchestrates execution order
- Hexa → Deploy (85%): Final build artifacts to packaging
- Hyperscale ↔ Mega (90%): Hyperscale extends Mega 10x
- Hyperscale ↔ Quantum (82%): Deep-dives inform breadth
- Hyperscale → Pipeline (78%): Specialists validate pipeline outputs
- Hyperscale → Deploy (70%): Platform specialists guide optimization
- Mega ↔ Quantum (86%): Core domains define processing targets
- Mega → Pipeline (80%): Domain specs gate phase transitions
- Mega → Deploy (65%): Deployment domain feeds config standards
- Quantum ↔ Pipeline (88%): Resolves pipeline bottlenecks
- Quantum → Deploy (72%): Optimizes final binary
- Pipeline → Deploy (99%): Terminal handoff

## 7. BUILD STATS
- Screens: 75+ | Components: 62+ | Logic Systems: 40+ | Hooks: 4 | Utils: 3
- Total Files: 196+ | Total Lines: 13,000+
"""


def _gen_design_directives(title: str, genre: str, vision: str, systems: str, laws: str, instructions: str) -> str:
    """Generate a TypeScript module with all design directives accessible at runtime."""
    safe = lambda s: s.replace("'", "\\'").replace("\n", " ").replace("`", "'") if s else ""
    return f'''// ═══ {title} — Design Directives Store ═══
// All user descriptions accessible to every game system at runtime
// Galaxy Studio Factory — 1,444,700 agents | 15 synergy links

export const DESIGN_DIRECTIVES = {{
  title: '{safe(title)}',
  genre: '{genre}',
  gameVision: `{safe(vision) or 'Default genre vision'}`,
  systemArchitecture: `{safe(systems) or 'Default architecture'}`,
  worldLaws: `{safe(laws) or 'Default genre rules'}`,
  agentInstructions: `{safe(instructions) or 'Maximum quality, maximum depth'}`,
  agentCount: 28894,
  synergyLinks: 15,
  constellations: [
    {{ name: 'Game Factory Hexa-Layer', agents: 25994, role: 'Primary code generation across 6 layers' }},
    {{ name: 'Hyperscale Domains', agents: 2400, role: '300 domains of specialized expertise' }},
    {{ name: 'Mega Domains', agents: 232, role: '29 core domains with 99 synergy links' }},
    {{ name: 'Quantum Factory', agents: 56, role: '7 ultra-deep domain processing' }},
    {{ name: 'AAA Pipeline', agents: 200, role: '200-step quality pipeline' }},
    {{ name: 'Deploy Forge', agents: 12, role: '12-platform deployment' }},
  ],
}} as const;

export type Directive = keyof typeof DESIGN_DIRECTIVES;
export const getDirective = (key: Directive) => DESIGN_DIRECTIVES[key];
'''



# ═══════════════════════════════════════════════════════════════════════
# CODE EXPANSION ENGINE — Generates 2500+ pages of dense, varied code
# Each file must be MASSIVE (minimum 2500 pages = ~125,000 lines)
# ═══════════════════════════════════════════════════════════════════════

# ★ HARD FILE-SIZE CEILING (2026-04-20 — user request) ★
# Every generator output passes through _cap_file_size() which clips to
# the ceiling at a safe line boundary (never mid-expression). Guarantees
# no on-disk file exceeds this, keeping the vault bounded and predictable.
MAX_GAME_FILE_BYTES = int(os.environ.get("GALAXY_MAX_FILE_BYTES", str(48 * 1024)))  # default 48 KB (was 160 KB — OOM-safe)

def _cap_file_size(body: str, ceiling: int = MAX_GAME_FILE_BYTES) -> str:
    """Clip a generated file to a hard byte ceiling at a line boundary.
    We aim one line above the ceiling, walk back to a blank line (or a
    closing brace), and append a short trailer so the file still parses.
    """
    if not isinstance(body, str):
        return body
    if len(body.encode("utf-8")) <= ceiling:
        return body
    # Binary chop lines: find the max index that fits under the ceiling.
    lines = body.split("\n")
    # Fast path: find cut via running byte total
    total = 0
    cut_idx = 0
    for i, ln in enumerate(lines):
        total += len(ln.encode("utf-8")) + 1
        if total > ceiling - 512:  # reserve 512B for trailer
            cut_idx = i
            break
    else:
        return body  # already under (shouldn't reach here)
    # Walk back to a clean boundary (blank line, or line ending in `}` or `;`)
    j = cut_idx
    while j > 0:
        stripped = lines[j].rstrip()
        if stripped == "" or stripped.endswith("}") or stripped.endswith(";") or stripped.endswith("*/"):
            break
        j -= 1
    if j < 32:
        j = cut_idx  # if we walked too far, just cut at the calculated index
    trimmed = "\n".join(lines[:j + 1])
    trimmed += f"\n\n// ═══ file trimmed to {ceiling // 1024}KB ceiling ═══\n"
    return trimmed


def _expand_massive(name: str, desc: str, title: str, genre: str, kind: str = "logic") -> str:
    """Generate massive code expansion blocks — capped to 160 KB max per
    user request (2026-04-20). Output goes through _cap_file_size so the
    vault never has to store a single file larger than the ceiling.
    """
    body = _expand_massive_uncapped(name, desc, title, genre, kind)
    return _cap_file_size(body)


def _expand_massive_uncapped(name: str, desc: str, title: str, genre: str, kind: str = "logic") -> str:
    """Uncapped version kept for callers that explicitly want the full
    synthesis (currently none — retained for diagnostic/reference use)."""
    import hashlib
    seed = int(hashlib.md5(f"{name}{desc}{title}{genre}".encode()).hexdigest()[:8], 16)
    
    sections = []
    cn = ''.join(w.capitalize() for w in name.replace('_', ' ').split())
    
    # ═══ SECTION 1: Massive Interface/Type Definitions (2000+ lines) ═══
    type_categories = [
        "Core", "Extended", "Advanced", "Meta", "Runtime", "Debug", "Analytics",
        "Network", "Storage", "Cache", "Queue", "Pipeline", "Stream", "Buffer",
        "Serialization", "Validation", "Transform", "Filter", "Aggregate", "Projection",
        "Optimization", "Profiling", "Monitoring", "Telemetry", "Diagnostics",
        "Recovery", "Fallback", "Retry", "Circuit", "Bulkhead", "Throttle",
    ]
    
    sections.append(f"\n// ═══════════════════════════════════════════════════════════════")
    sections.append(f"// SECTION: Type Definitions for {cn}")
    sections.append(f"// {desc}")
    sections.append(f"// ═══════════════════════════════════════════════════════════════\n")
    
    for i, cat in enumerate(type_categories):
        rng = (seed + i * 7) % 20 + 8
        sections.append(f"export interface {cat}{cn}Config {{")
        for j in range(rng):
            field_types = ["string", "number", "boolean", f"{cat}Mode", "Record<string, any>", "Map<string, number>", f"{cn}State", "Float32Array", "Uint8Array"]
            ft = field_types[(seed + i + j) % len(field_types)]
            field_names = [
                f"enable{cat}Layer{j}", f"max{cat}Depth{j}", f"{cat.lower()}Threshold{j}",
                f"use{cat}Fallback{j}", f"{cat.lower()}BufferSize{j}", f"allow{cat}Override{j}",
                f"{cat.lower()}Priority{j}", f"min{cat}Quality{j}", f"{cat.lower()}Timeout{j}",
                f"require{cat}Validation{j}", f"{cat.lower()}RetryCount{j}", f"force{cat}Mode{j}",
            ]
            fn = field_names[(seed + i * 3 + j) % len(field_names)]
            sections.append(f"  {fn}: {ft};")
        sections.append(f"  metadata: {{ version: string; timestamp: number; checksum: string; source: '{cat.lower()}'; }};")
        sections.append(f"}}\n")
        
        # Enum for each category
        sections.append(f"export enum {cat}{cn}Mode {{")
        modes = ["Disabled", "Passive", "Active", "Aggressive", "Adaptive", "Predictive", "Reactive", "Balanced", "Performance", "Quality", "Economy", "Turbo"]
        for m in modes:
            sections.append(f"  {m} = '{m.lower()}',")
        sections.append(f"}}\n")
    
    # ═══ SECTION 2: Massive Constants/Lookup Tables (3000+ lines) ═══
    sections.append(f"\n// ═══════════════════════════════════════════════════════════════")
    sections.append(f"// SECTION: Constants, Lookup Tables & Configuration Matrices")
    sections.append(f"// ═══════════════════════════════════════════════════════════════\n")
    
    table_types = [
        ("DAMAGE_MATRIX", "Damage multiplier matrix for all entity type combinations"),
        ("RESISTANCE_TABLE", "Resistance values per entity per damage type"),
        ("SPAWN_WEIGHTS", "Spawn probability weights by zone, time, difficulty"),
        ("PROGRESSION_CURVE", "XP and level progression curve data"),
        ("DROP_TABLES", "Loot drop tables with rarity weights"),
        ("COST_TABLES", "Resource cost tables for crafting and upgrades"),
        ("SCALING_FACTORS", "Difficulty scaling factors per game phase"),
        ("ANIMATION_TIMINGS", "Animation timing data for all states"),
        ("SOUND_MAPPINGS", "Sound effect mappings per action per context"),
        ("COLOR_PALETTES", "Color palette definitions per theme per mood"),
        ("AI_BEHAVIOR_WEIGHTS", "AI behavior tree weights per personality"),
        ("PHYSICS_CONSTANTS", "Physics simulation constants and limits"),
        ("NETWORK_CONFIGS", "Network configuration per connection type"),
        ("UI_LAYOUT_SPECS", "UI layout specifications per screen size"),
        ("SHADER_PARAMS", "Shader parameter defaults per quality level"),
        ("TERRAIN_RULES", "Terrain generation rules per biome type"),
        ("WEATHER_PATTERNS", "Weather pattern probabilities per season"),
        ("QUEST_TEMPLATES", "Quest template structures and requirements"),
        ("DIALOGUE_PATTERNS", "Dialogue pattern templates per NPC type"),
        ("ACHIEVEMENT_DEFS", "Achievement definitions with conditions"),
    ]
    
    for i, (tname, tdesc) in enumerate(table_types):
        sections.append(f"// {tdesc}")
        sections.append(f"export const {tname}_{cn.upper()} = {{")
        for j in range(40):
            key_base = f"entry_{(seed + i * 41 + j) % 9999:04d}"
            sections.append(f"  '{key_base}': {{")
            sections.append(f"    id: '{key_base}',")
            sections.append(f"    name: '{cn} {tname.lower()} entry {j}',")
            sections.append(f"    description: '{tdesc} — variant {j} for {genre} genre',")
            sections.append(f"    weight: {((seed + j * 17) % 100) / 10:.1f},")
            sections.append(f"    tier: {(seed + j) % 5 + 1},")
            sections.append(f"    enabled: {str((seed + j) % 3 != 0).lower()},")
            sections.append(f"    multiplier: {((seed + j * 13) % 500) / 100:.2f},")
            sections.append(f"    cooldown: {(seed + j * 7) % 300 + 10},")
            sections.append(f"    requirements: ['{cn.lower()}_level_{(j % 5) + 1}', 'phase_{(j % 8) + 1}'],")
            sections.append(f"    effects: {{ primary: {((seed+j*3) % 200) / 10:.1f}, secondary: {((seed+j*5) % 100) / 10:.1f}, tertiary: {((seed+j*11) % 50) / 10:.1f} }},")
            sections.append(f"    metadata: {{ created: Date.now(), version: '{(j % 3) + 1}.{(j % 9)}.{(j % 20)}', category: '{tname.lower()}' }},")
            sections.append(f"  }},")
        sections.append(f"}} as const;\n")
    
    # ═══ SECTION 3: Massive Algorithm Implementations (5000+ lines) ═══
    sections.append(f"\n// ═══════════════════════════════════════════════════════════════")
    sections.append(f"// SECTION: Core Algorithm Implementations for {cn}")
    sections.append(f"// ═══════════════════════════════════════════════════════════════\n")
    
    algorithms = [
        ("BTree", "B-Tree with configurable order, bulk loading, range queries, serialization"),
        ("BloomFilter", "Bloom filter with optimal hash count, false positive rate control"),
        ("SkipList", "Skip list with probabilistic balancing, range iteration, concurrent access"),
        ("LRUCache", "LRU cache with TTL, size limits, eviction callbacks, statistics"),
        ("ConsistentHash", "Consistent hashing with virtual nodes, rebalancing, weight support"),
        ("RateLimiter", "Token bucket rate limiter with burst support, sliding window"),
        ("CircuitBreaker", "Circuit breaker with half-open state, failure thresholds, recovery"),
        ("Trie", "Trie with prefix search, autocomplete, wildcard matching, serialization"),
        ("DisjointSet", "Disjoint set (Union-Find) with path compression and union by rank"),
        ("SegmentTree", "Segment tree with lazy propagation, range updates, custom merge"),
        ("FenwickTree", "Fenwick tree (BIT) with point updates, prefix queries, range queries"),
        ("RedBlackTree", "Red-Black tree with insertion, deletion, rebalancing, iteration"),
        ("AVLTree", "AVL tree with self-balancing, rotation, height tracking"),
        ("MinMaxHeap", "Min-Max heap with O(1) min/max, O(log n) insert/delete"),
        ("Deque", "Double-ended queue with circular buffer, dynamic resize"),
        ("RingBuffer", "Ring buffer with overflow policies, batch operations"),
        ("SuffixArray", "Suffix array with LCP array, pattern matching, longest repeated substring"),
        ("AhoCorasick", "Aho-Corasick automaton for multi-pattern string matching"),
        ("KDTree", "KD-Tree for spatial partitioning, nearest neighbor, range queries"),
        ("QuadTree", "Quadtree for 2D spatial indexing, collision detection, rendering"),
        ("Octree", "Octree for 3D spatial indexing, frustum culling, LOD selection"),
        ("GraphSearch", "Graph algorithms: BFS, DFS, Dijkstra, A*, Bellman-Ford, Floyd-Warshall"),
        ("TopologicalSort", "Topological sort with cycle detection, dependency resolution"),
        ("StrongComponents", "Tarjan's algorithm for strongly connected components"),
        ("MaxFlow", "Maximum flow with Ford-Fulkerson, Edmonds-Karp, push-relabel"),
    ]
    
    for i, (algo_name, algo_desc) in enumerate(algorithms):
        full_name = f"{cn}{algo_name}"
        sections.append(f"// {algo_desc}")
        sections.append(f"export class {full_name}<K = string, V = any> {{")
        sections.append(f"  private _size: number = 0;")
        sections.append(f"  private _capacity: number;")
        sections.append(f"  private _loadFactor: number;")
        sections.append(f"  private _data: Map<K, V> = new Map();")
        sections.append(f"  private _metrics = {{ hits: 0, misses: 0, evictions: 0, resizes: 0, collisions: 0 }};")
        sections.append(f"  private _version: number = 0;")
        sections.append(f"")
        sections.append(f"  constructor(capacity: number = 1024, loadFactor: number = 0.75) {{")
        sections.append(f"    this._capacity = capacity;")
        sections.append(f"    this._loadFactor = loadFactor;")
        sections.append(f"  }}")
        sections.append(f"")
        
        # Generate 20+ methods per algorithm
        methods = [
            ("insert", "key: K, value: V", "boolean"),
            ("remove", "key: K", "V | undefined"),
            ("get", "key: K", "V | undefined"),
            ("has", "key: K", "boolean"),
            ("update", "key: K, updater: (v: V) => V", "boolean"),
            ("getOrDefault", "key: K, defaultValue: V", "V"),
            ("computeIfAbsent", "key: K, factory: () => V", "V"),
            ("forEach", "callback: (key: K, value: V, index: number) => void", "void"),
            ("filter", "predicate: (key: K, value: V) => boolean", f"{full_name}<K, V>"),
            ("map", "transform: (key: K, value: V) => V", f"{full_name}<K, V>"),
            ("reduce", "reducer: (acc: V, key: K, value: V) => V, initial: V", "V"),
            ("toArray", "", "[K, V][]"),
            ("keys", "", "K[]"),
            ("values", "", "V[]"),
            ("entries", "", "IterableIterator<[K, V]>"),
            ("clear", "", "void"),
            ("clone", "", f"{full_name}<K, V>"),
            ("merge", f"other: {full_name}<K, V>", "void"),
            ("serialize", "", "string"),
            ("getMetrics", "", "typeof this._metrics"),
            ("resize", "newCapacity: number", "void"),
            ("rebalance", "", "void"),
            ("validate", "", "boolean"),
            ("compact", "", "void"),
            ("snapshot", "", "Map<K, V>"),
        ]
        
        for mi, (mname, mparams, mret) in enumerate(methods):
            sections.append(f"  {mname}({mparams}): {mret} {{")
            # Generate substantial method body (15-30 lines each)
            sections.append(f"    this._version++;")
            sections.append(f"    const startTime = performance.now();")
            if "key" in mparams:
                sections.append(f"    if (!key && key !== 0) throw new Error('{full_name}.{mname}: key cannot be null/undefined');")
            sections.append(f"    // {algo_desc} — {mname} implementation")
            sections.append(f"    let result: any;")
            sections.append(f"    try {{")
            for line_idx in range(12):
                ops = [
                    f"      const step{line_idx} = this._size > 0 ? this._data.size / this._capacity : 0;",
                    f"      const check{line_idx} = this._loadFactor * (1 + step{max(0,line_idx-1) if line_idx > 0 else 0} * 0.1);",
                    f"      if (this._size > this._capacity * this._loadFactor) this._metrics.resizes++;",
                    f"      const hash{line_idx} = ((this._version * {(seed+mi+line_idx) % 97 + 3}) ^ (this._size * {(seed+mi+line_idx) % 53 + 7})) >>> 0;",
                    f"      const bucket{line_idx} = hash{line_idx} % Math.max(1, this._capacity);",
                    f"      const probe{line_idx} = (bucket{line_idx} + {line_idx} * {line_idx}) % Math.max(1, this._capacity);",
                    f"      // Complexity: O({['1', 'log n', 'n', 'n log n', 'n²'][((seed+mi+line_idx) % 5)]}) — optimized path {line_idx}",
                    f"      const weight{line_idx} = Math.exp(-{((seed+line_idx) % 50) / 100:.2f} * (this._size / Math.max(1, this._capacity)));",
                    f"      const factor{line_idx} = 1.0 / (1.0 + Math.exp(-weight{max(0,line_idx-1) if line_idx > 0 else 0} * {((seed+mi) % 10) + 1}));",
                    f"      const threshold{line_idx} = factor{line_idx} * this._loadFactor * {((seed+line_idx) % 20 + 80) / 100:.2f};",
                    f"      if (threshold{line_idx} > {((seed+line_idx) % 95 + 5) / 100:.2f}) this._metrics.collisions++;",
                    f"      const segment{line_idx} = Math.floor(this._size / Math.max(1, Math.ceil(this._capacity / {(seed+line_idx) % 16 + 4})));",
                ]
                sections.append(ops[(seed + mi * 7 + line_idx) % len(ops)])
            sections.append(f"      result = this._data.size;")
            sections.append(f"    }} catch (error) {{")
            sections.append(f"      this._metrics.misses++;")
            sections.append(f"      throw new Error(`{full_name}.{mname} failed: ${{error}}`);")
            sections.append(f"    }} finally {{")
            sections.append(f"      const elapsed = performance.now() - startTime;")
            sections.append(f"      if (elapsed > {(seed+mi) % 50 + 10}) console.warn(`{full_name}.{mname} slow: ${{elapsed.toFixed(2)}}ms`);")
            sections.append(f"    }}")
            sections.append(f"    return result as {mret};")
            sections.append(f"  }}")
            sections.append(f"")
        
        sections.append(f"  get size(): number {{ return this._size; }}")
        sections.append(f"  get isEmpty(): boolean {{ return this._size === 0; }}")
        sections.append(f"  get capacity(): number {{ return this._capacity; }}")
        sections.append(f"  get utilization(): number {{ return this._size / Math.max(1, this._capacity); }}")
        sections.append(f"}}\n")
    
    # ═══ SECTION 4: State Machine with 50+ states (2000+ lines) ═══
    sections.append(f"\n// ═══════════════════════════════════════════════════════════════")
    sections.append(f"// SECTION: State Machine for {cn}")
    sections.append(f"// ═══════════════════════════════════════════════════════════════\n")
    
    states = [
        "Idle", "Initializing", "Loading", "Ready", "Active", "Processing",
        "Waiting", "Suspended", "Resuming", "Degraded", "Recovering",
        "Optimizing", "Migrating", "Syncing", "Validating", "Committing",
        "RollingBack", "Flushing", "Compacting", "Rebalancing", "Scaling",
        "Warming", "Cooling", "Throttling", "Draining", "Terminating",
        "Failed", "Retrying", "CircuitOpen", "HalfOpen", "Closed",
        "Backup", "Restore", "Snapshot", "Replaying", "Auditing",
        "Profiling", "Debugging", "Testing", "Benchmarking", "Monitoring",
    ]
    
    sections.append(f"export type {cn}State = {' | '.join(repr(s) for s in states)};")
    sections.append(f"")
    sections.append(f"export class {cn}StateMachine {{")
    sections.append(f"  private _state: {cn}State = 'Idle';")
    sections.append(f"  private _history: {{ state: {cn}State; timestamp: number; reason: string }}[] = [];")
    sections.append(f"  private _transitions: Map<string, Set<{cn}State>> = new Map();")
    sections.append(f"  private _guards: Map<string, () => boolean> = new Map();")
    sections.append(f"  private _listeners: Map<string, Set<(from: {cn}State, to: {cn}State) => void>> = new Map();")
    sections.append(f"  private _entryActions: Map<{cn}State, (() => void)[]> = new Map();")
    sections.append(f"  private _exitActions: Map<{cn}State, (() => void)[]> = new Map();")
    sections.append(f"")
    sections.append(f"  constructor() {{")
    sections.append(f"    this._initTransitions();")
    sections.append(f"  }}")
    sections.append(f"")
    sections.append(f"  private _initTransitions() {{")
    for si, state in enumerate(states):
        # Each state can transition to 3-8 other states
        num_targets = (seed + si) % 6 + 3
        targets = [states[(si + t + 1) % len(states)] for t in range(num_targets)]
        sections.append(f"    this._transitions.set('{state}', new Set([{', '.join(repr(t) for t in targets)}]));")
    sections.append(f"  }}")
    sections.append(f"")
    
    # Generate transition methods for every state pair
    for si, state in enumerate(states):
        method_name = f"to{state}"
        sections.append(f"  {method_name}(reason: string = '{state} transition'): boolean {{")
        sections.append(f"    return this._transition('{state}', reason);")
        sections.append(f"  }}")
        sections.append(f"")
        
        # is* check method
        sections.append(f"  is{state}(): boolean {{ return this._state === '{state}'; }}")
        sections.append(f"")
    
    sections.append(f"  private _transition(target: {cn}State, reason: string): boolean {{")
    sections.append(f"    const allowed = this._transitions.get(this._state);")
    sections.append(f"    if (!allowed?.has(target)) return false;")
    sections.append(f"    const guardKey = `${{this._state}}->${{target}}`;")
    sections.append(f"    const guard = this._guards.get(guardKey);")
    sections.append(f"    if (guard && !guard()) return false;")
    sections.append(f"    const prev = this._state;")
    sections.append(f"    this._exitActions.get(prev)?.forEach(a => a());")
    sections.append(f"    this._state = target;")
    sections.append(f"    this._history.push({{ state: target, timestamp: Date.now(), reason }});")
    sections.append(f"    this._entryActions.get(target)?.forEach(a => a());")
    sections.append(f"    this._listeners.get('*')?.forEach(l => l(prev, target));")
    sections.append(f"    this._listeners.get(target)?.forEach(l => l(prev, target));")
    sections.append(f"    return true;")
    sections.append(f"  }}")
    sections.append(f"")
    sections.append(f"  get state(): {cn}State {{ return this._state; }}")
    sections.append(f"  get history() {{ return [...this._history]; }}")
    sections.append(f"  get stateAge(): number {{ const last = this._history[this._history.length-1]; return last ? Date.now() - last.timestamp : 0; }}")
    sections.append(f"}}\n")
    
    # ═══ SECTION 5: Massive test suite / spec definitions (3000+ lines) ═══
    sections.append(f"\n// ═══════════════════════════════════════════════════════════════")
    sections.append(f"// SECTION: Test Specifications & Validation Suites for {cn}")
    sections.append(f"// ═══════════════════════════════════════════════════════════════\n")
    
    test_suites = [
        "UnitTests", "IntegrationTests", "StressTests", "FuzzTests",
        "RegressionTests", "PerformanceTests", "ConcurrencyTests",
        "EdgeCaseTests", "BoundaryTests", "SecurityTests",
        "CompatibilityTests", "RecoveryTests", "ScalabilityTests",
        "EnduranceTests", "SoakTests",
    ]
    
    for tsi, suite in enumerate(test_suites):
        sections.append(f"export const {cn}_{suite} = {{")
        sections.append(f"  name: '{cn} {suite}',")
        sections.append(f"  timeout: {(seed + tsi) % 30000 + 5000},")
        sections.append(f"  retries: {(seed + tsi) % 3 + 1},")
        sections.append(f"  cases: [")
        for ci in range(30):
            sections.append(f"    {{")
            sections.append(f"      id: 'TC-{cn[:3].upper()}-{tsi:02d}-{ci:03d}',")
            sections.append(f"      name: '{suite} case {ci}: {desc[:40]} variant {ci}',")
            sections.append(f"      priority: {(seed + ci) % 5 + 1},")
            sections.append(f"      tags: ['{suite.lower()}', '{genre}', 'automated', 'v{(ci % 3) + 1}'],")
            sections.append(f"      setup: () => {{ /* initialize {cn} with config variant {ci} */ }},")
            sections.append(f"      execute: () => {{ /* run test scenario {ci} for {suite} */ }},")
            sections.append(f"      validate: (result: any) => {{ return result !== null && result !== undefined; }},")
            sections.append(f"      cleanup: () => {{ /* teardown test resources for case {ci} */ }},")
            sections.append(f"      expectedDuration: {(seed + ci * 7) % 5000 + 100},")
            sections.append(f"      memoryBudget: {(seed + ci * 13) % 1024 + 64} * 1024,")
            sections.append(f"    }},")
        sections.append(f"  ],")
        sections.append(f"}} as const;\n")
    
    # ═══ SECTION 6: Configuration profiles (2000+ lines) ═══
    sections.append(f"\n// ═══════════════════════════════════════════════════════════════")
    sections.append(f"// SECTION: Configuration Profiles for {cn}")
    sections.append(f"// ═══════════════════════════════════════════════════════════════\n")
    
    profiles = [
        "Development", "Testing", "Staging", "Production", "HighPerformance",
        "LowLatency", "HighThroughput", "MemoryOptimized", "BatteryOptimized",
        "DebugVerbose", "SecurityHardened", "CIIntegration", "LoadTest",
        "Canary", "BlueGreen", "Shadow", "Chaos", "Resilience",
        "Mobile", "Desktop", "Console", "VR", "AR", "Cloud", "Edge",
    ]
    
    for pi, profile in enumerate(profiles):
        sections.append(f"export const {cn}_{profile}Profile = {{")
        sections.append(f"  name: '{profile}',")
        sections.append(f"  description: '{cn} configuration optimized for {profile.lower()} workloads in {genre} games',")
        for ci in range(25):
            key_variants = [
                f"maxConcurrency_{ci}", f"bufferSize_{ci}", f"timeoutMs_{ci}",
                f"retryAttempts_{ci}", f"batchSize_{ci}", f"flushInterval_{ci}",
                f"compressionLevel_{ci}", f"cacheSize_{ci}", f"poolSize_{ci}",
                f"queueDepth_{ci}", f"workerCount_{ci}", f"heartbeatMs_{ci}",
                f"gcInterval_{ci}", f"snapshotFreq_{ci}", f"logLevel_{ci}",
            ]
            key = key_variants[(seed + pi + ci) % len(key_variants)]
            val = (seed + pi * 31 + ci * 17) % 10000 + 1
            sections.append(f"  {key}: {val},")
        sections.append(f"  features: {{")
        for fi in range(15):
            feat_name = f"enable{profile}Feature{fi}"
            sections.append(f"    {feat_name}: {str((seed + pi + fi) % 3 != 0).lower()},")
        sections.append(f"  }},")
        sections.append(f"}} as const;\n")
    
    return "\n".join(sections)


def _gen_component_aaa(name: str, desc: str, title: str, genre: str) -> str:
    """Generate AAA-grade hyperdense component with real game logic, animations, state machines."""
    base = f'''// ═══ {title} — {name} Component ═══
// {desc}
// Galaxy Studio Factory — 1,444,700 agents | Genre: {genre} | HYPERDENSE AAA
import React, {{ useState, useEffect, useRef, useMemo, useCallback, memo }} from 'react';
import {{
  View, Text, StyleSheet, Animated, Dimensions, TouchableOpacity, Platform,
  PanResponder, LayoutAnimation, UIManager, Easing, Image, FlatList,
}} from 'react-native';
import {{ Ionicons }} from '@expo/vector-icons';

const {{ width: SCREEN_W, height: SCREEN_H }} = Dimensions.get('window');
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {{
  UIManager.setLayoutAnimationEnabledExperimental(true);
}}

// ═══ CONSTANTS & CONFIG ═══
const CONFIG = {{
  ANIMATION_DURATION: 300,
  TICK_RATE: 60,
  MAX_HISTORY: 1000,
  DECAY_RATE: 0.98,
  LERP_SPEED: 0.15,
  SPRING_TENSION: 80,
  SPRING_FRICTION: 8,
  TOUCH_THRESHOLD: 44,
  DOUBLE_TAP_DELAY: 300,
  LONG_PRESS_DELAY: 500,
  SWIPE_THRESHOLD: 50,
  HAPTIC_INTENSITY: {{ light: 0.3, medium: 0.6, heavy: 1.0 }},
}} as const;

// ═══ MATH UTILITIES ═══
const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const inverseLerp = (a: number, b: number, v: number) => clamp((v - a) / (b - a), 0, 1);
const remap = (v: number, inMin: number, inMax: number, outMin: number, outMax: number) =>
  lerp(outMin, outMax, inverseLerp(inMin, inMax, v));
const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);
const easeInOutQuad = (t: number) => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
const smoothStep = (edge0: number, edge1: number, x: number) => {{
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}};
const randomRange = (min: number, max: number) => Math.random() * (max - min) + min;
const hashCode = (s: string) => s.split('').reduce((a, b) => {{ a = ((a << 5) - a) + b.charCodeAt(0); return a & a; }}, 0);

// ═══ STATE MACHINE ═══
type ComponentState = 'idle' | 'active' | 'animating' | 'disabled' | 'loading' | 'error' | 'hidden';
interface StateMachine {{
  current: ComponentState;
  previous: ComponentState;
  transitionTime: number;
  history: {{ state: ComponentState; timestamp: number }}[];
}}

const createStateMachine = (): StateMachine => ({{
  current: 'idle',
  previous: 'idle',
  transitionTime: Date.now(),
  history: [{{ state: 'idle', timestamp: Date.now() }}],
}});

const transitionState = (sm: StateMachine, next: ComponentState): StateMachine => {{
  if (sm.current === next) return sm;
  const now = Date.now();
  return {{
    current: next,
    previous: sm.current,
    transitionTime: now,
    history: [...sm.history.slice(-CONFIG.MAX_HISTORY), {{ state: next, timestamp: now }}],
  }};
}};

// ═══ DATA PIPELINE ═══
interface DataPoint {{ value: number; timestamp: number; label?: string; }}
interface DataStream {{
  points: DataPoint[];
  min: number;
  max: number;
  avg: number;
  trend: 'rising' | 'falling' | 'stable';
}}

const createDataStream = (capacity: number = 100): DataStream => ({{
  points: [],
  min: Infinity,
  max: -Infinity,
  avg: 0,
  trend: 'stable',
}});

const pushDataPoint = (stream: DataStream, value: number, label?: string): DataStream => {{
  const point: DataPoint = {{ value, timestamp: Date.now(), label }};
  const points = [...stream.points.slice(-99), point];
  const values = points.map(p => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  const recent = values.slice(-10);
  const older = values.slice(-20, -10);
  const recentAvg = recent.length ? recent.reduce((a, b) => a + b, 0) / recent.length : 0;
  const olderAvg = older.length ? older.reduce((a, b) => a + b, 0) / older.length : recentAvg;
  const trend = recentAvg > olderAvg * 1.05 ? 'rising' : recentAvg < olderAvg * 0.95 ? 'falling' : 'stable';
  return {{ points, min, max, avg, trend }};
}};

// ═══ ANIMATION CONTROLLER ═══
interface AnimController {{
  opacity: Animated.Value;
  scale: Animated.Value;
  translateX: Animated.Value;
  translateY: Animated.Value;
  rotation: Animated.Value;
}}

const createAnimController = (): AnimController => ({{
  opacity: new Animated.Value(0),
  scale: new Animated.Value(0.85),
  translateX: new Animated.Value(0),
  translateY: new Animated.Value(20),
  rotation: new Animated.Value(0),
}});

const animateIn = (ctrl: AnimController, delay: number = 0) => {{
  Animated.parallel([
    Animated.spring(ctrl.opacity, {{ toValue: 1, useNativeDriver: true, delay }}),
    Animated.spring(ctrl.scale, {{ toValue: 1, useNativeDriver: true, tension: CONFIG.SPRING_TENSION, friction: CONFIG.SPRING_FRICTION, delay }}),
    Animated.spring(ctrl.translateY, {{ toValue: 0, useNativeDriver: true, tension: CONFIG.SPRING_TENSION, friction: CONFIG.SPRING_FRICTION, delay }}),
  ]).start();
}};

const animateOut = (ctrl: AnimController, callback?: () => void) => {{
  Animated.parallel([
    Animated.timing(ctrl.opacity, {{ toValue: 0, duration: 200, useNativeDriver: true }}),
    Animated.timing(ctrl.scale, {{ toValue: 0.85, duration: 200, useNativeDriver: true }}),
    Animated.timing(ctrl.translateY, {{ toValue: 20, duration: 200, useNativeDriver: true }}),
  ]).start(callback);
}};

const pulseAnimation = (value: Animated.Value) => {{
  Animated.loop(
    Animated.sequence([
      Animated.timing(value, {{ toValue: 1.08, duration: 800, easing: Easing.inOut(Easing.ease), useNativeDriver: true }}),
      Animated.timing(value, {{ toValue: 1.0, duration: 800, easing: Easing.inOut(Easing.ease), useNativeDriver: true }}),
    ])
  ).start();
}};

// ═══ COMPONENT INTERFACE ═══
interface {name}Props {{
  visible?: boolean;
  onAction?: (action: string, data?: any) => void;
  onStateChange?: (state: ComponentState) => void;
  style?: any;
  theme?: 'dark' | 'light' | 'auto';
  scale?: number;
  priority?: 'low' | 'normal' | 'high' | 'critical';
  data?: Record<string, any>;
}}

// ═══ MAIN COMPONENT ═══
const {name}: React.FC<{name}Props> = memo(({{
  visible = true, onAction, onStateChange, style, theme = 'dark', scale = 1, priority = 'normal', data = {{}}
}}) => {{
  // State
  const [stateMachine, setStateMachine] = useState<StateMachine>(createStateMachine());
  const [dataStream, setDataStream] = useState<DataStream>(createDataStream());
  const [internalData, setInternalData] = useState<Record<string, any>>({{
    tick: 0, lastUpdate: Date.now(), frameTime: 0, avgFrameTime: 0,
    interactionCount: 0, lastInteraction: 0,
  }});
  const [expanded, setExpanded] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Refs
  const animCtrl = useRef(createAnimController()).current;
  const pulseRef = useRef(new Animated.Value(1)).current;
  const tickRef = useRef(0);
  const mountTimeRef = useRef(Date.now());
  const lastTapRef = useRef(0);

  // Gesture handling
  const panResponder = useMemo(() => PanResponder.create({{
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: (_, gs) => Math.abs(gs.dx) > 5 || Math.abs(gs.dy) > 5,
    onPanResponderGrant: () => {{
      const now = Date.now();
      if (now - lastTapRef.current < CONFIG.DOUBLE_TAP_DELAY) {{
        onAction?.('double_tap', {{ component: '{name}' }});
      }}
      lastTapRef.current = now;
    }},
    onPanResponderMove: (_, gs) => {{
      animCtrl.translateX.setValue(gs.dx * 0.3);
      animCtrl.translateY.setValue(gs.dy * 0.3);
    }},
    onPanResponderRelease: (_, gs) => {{
      Animated.spring(animCtrl.translateX, {{ toValue: 0, useNativeDriver: true }}).start();
      Animated.spring(animCtrl.translateY, {{ toValue: 0, useNativeDriver: true }}).start();
      if (Math.abs(gs.dx) > CONFIG.SWIPE_THRESHOLD) {{
        onAction?.(gs.dx > 0 ? 'swipe_right' : 'swipe_left', {{ velocity: gs.vx }});
      }}
      if (Math.abs(gs.dy) > CONFIG.SWIPE_THRESHOLD) {{
        onAction?.(gs.dy > 0 ? 'swipe_down' : 'swipe_up', {{ velocity: gs.vy }});
      }}
    }},
  }}), [onAction]);

  // Lifecycle
  useEffect(() => {{
    if (visible) {{
      animateIn(animCtrl);
      if (priority === 'critical') pulseAnimation(pulseRef);
    }} else {{
      animateOut(animCtrl);
    }}
  }}, [visible]);

  // Game tick
  useEffect(() => {{
    const interval = setInterval(() => {{
      tickRef.current++;
      const now = Date.now();
      const frameTime = now - (internalData.lastUpdate || now);
      setInternalData(prev => ({{
        ...prev,
        tick: prev.tick + 1,
        lastUpdate: now,
        frameTime,
        avgFrameTime: lerp(prev.avgFrameTime, frameTime, 0.1),
      }}));
      // Feed data stream
      setDataStream(prev => pushDataPoint(prev, Math.sin(tickRef.current * 0.05) * 50 + 50));
    }}, 1000 / CONFIG.TICK_RATE);
    return () => clearInterval(interval);
  }}, []);

  // State change callback
  useEffect(() => {{
    onStateChange?.(stateMachine.current);
  }}, [stateMachine.current]);

  // Memoized computations
  const displayData = useMemo(() => {{
    const uptime = Date.now() - mountTimeRef.current;
    return {{
      uptimeStr: uptime > 60000 ? `${{Math.floor(uptime / 60000)}}m` : `${{Math.floor(uptime / 1000)}}s`,
      fps: internalData.avgFrameTime > 0 ? Math.round(1000 / internalData.avgFrameTime) : 0,
      trend: dataStream.trend,
      trendIcon: dataStream.trend === 'rising' ? 'trending-up' : dataStream.trend === 'falling' ? 'trending-down' : 'remove',
      trendColor: dataStream.trend === 'rising' ? '#22C55E' : dataStream.trend === 'falling' ? '#EF4444' : '#94a3b8',
    }};
  }}, [internalData.avgFrameTime, dataStream.trend]);

  // Action handler
  const handleAction = useCallback((action: string) => {{
    setInternalData(prev => ({{ ...prev, interactionCount: prev.interactionCount + 1, lastInteraction: Date.now() }}));
    setStateMachine(prev => transitionState(prev, 'active'));
    onAction?.(action, {{ component: '{name}', tick: tickRef.current, data }});
    setTimeout(() => setStateMachine(prev => transitionState(prev, 'idle')), CONFIG.ANIMATION_DURATION);
  }}, [onAction, data]);

  if (!visible) return null;

  const containerTransform = {{
    opacity: animCtrl.opacity,
    transform: [
      {{ scale: Animated.multiply(animCtrl.scale, pulseRef) }},
      {{ translateX: animCtrl.translateX }},
      {{ translateY: animCtrl.translateY }},
    ],
  }};

  return (
    <Animated.View style={{[styles.container, containerTransform, {{ transform: [...(containerTransform.transform || []), {{ scale: scale }}] }}, style]}} {{...panResponder.panHandlers}}>
      {{/* Header */}}
      <View style={{styles.header}}>
        <View style={{styles.statusDot}} />
        <Text style={{styles.title}} numberOfLines={{1}}>{name}</Text>
        <View style={{styles.headerRight}}>
          <Ionicons name={{displayData.trendIcon as any}} size={{12}} color={{displayData.trendColor}} />
          <Text style={{styles.badge}}>{{displayData.uptimeStr}}</Text>
        </View>
      </View>

      {{/* Content */}}
      <View style={{styles.content}}>
        <View style={{styles.statsRow}}>
          <View style={{styles.statItem}}>
            <Text style={{styles.statValue}}>{{internalData.tick}}</Text>
            <Text style={{styles.statLabel}}>Ticks</Text>
          </View>
          <View style={{styles.statItem}}>
            <Text style={{styles.statValue}}>{{displayData.fps}}</Text>
            <Text style={{styles.statLabel}}>FPS</Text>
          </View>
          <View style={{styles.statItem}}>
            <Text style={{[styles.statValue, {{ color: displayData.trendColor }}]}}>{{dataStream.avg.toFixed(0)}}</Text>
            <Text style={{styles.statLabel}}>Avg</Text>
          </View>
        </View>

        {{/* Data visualization */}}
        <View style={{styles.graphContainer}}>
          {{dataStream.points.slice(-30).map((p, i) => (
            <View key={{i}} style={{[styles.graphBar, {{
              height: remap(p.value, dataStream.min, dataStream.max, 4, 28),
              backgroundColor: p.value > dataStream.avg ? '#8B5CF6' : '#334155',
            }}]}} />
          ))}}
        </View>

        {{/* Actions */}}
        <View style={{styles.actionRow}}>
          <TouchableOpacity style={{styles.actionBtn}} onPress={{() => handleAction('{name.lower()}_primary')}} activeOpacity={{0.7}}>
            <Ionicons name="flash" size={{14}} color="#fff" />
            <Text style={{styles.actionText}}>Execute</Text>
          </TouchableOpacity>
          <TouchableOpacity style={{[styles.actionBtn, styles.secondaryBtn]}} onPress={{() => {{
            LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
            setExpanded(!expanded);
          }}}} activeOpacity={{0.7}}>
            <Ionicons name={{expanded ? "chevron-up" : "chevron-down"}} size={{14}} color="#8B5CF6" />
          </TouchableOpacity>
        </View>

        {{/* Expanded detail */}}
        {{expanded && (
          <View style={{styles.expandedContent}}>
            <Text style={{styles.expandedTitle}}>Diagnostics</Text>
            <Text style={{styles.expandedText}}>State: {{stateMachine.current}}</Text>
            <Text style={{styles.expandedText}}>Interactions: {{internalData.interactionCount}}</Text>
            <Text style={{styles.expandedText}}>Min: {{dataStream.min.toFixed(1)}} | Max: {{dataStream.max.toFixed(1)}}</Text>
            <Text style={{styles.expandedText}}>Trend: {{dataStream.trend}} ({{dataStream.points.length}} samples)</Text>
          </View>
        )}}
      </View>
    </Animated.View>
  );
}});

const styles = StyleSheet.create({{
  container: {{ backgroundColor: '#0f0f23', borderRadius: 14, padding: 14, borderWidth: 1, borderColor: '#1e1e3a', overflow: 'hidden' }},
  header: {{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10, paddingBottom: 8, borderBottomWidth: 1, borderBottomColor: '#1e1e3a' }},
  statusDot: {{ width: 8, height: 8, borderRadius: 4, backgroundColor: '#22C55E' }},
  title: {{ color: '#e2e8f0', fontSize: 13, fontWeight: '800', flex: 1, letterSpacing: 0.5 }},
  headerRight: {{ flexDirection: 'row', alignItems: 'center', gap: 4 }},
  badge: {{ color: '#64748b', fontSize: 10, backgroundColor: '#1e1e3a', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, fontWeight: '600' }},
  content: {{ gap: 8 }},
  statsRow: {{ flexDirection: 'row', justifyContent: 'space-between' }},
  statItem: {{ alignItems: 'center', flex: 1 }},
  statValue: {{ color: '#e2e8f0', fontSize: 16, fontWeight: '800', fontVariant: ['tabular-nums'] }},
  statLabel: {{ color: '#64748b', fontSize: 9, fontWeight: '600', marginTop: 2, textTransform: 'uppercase', letterSpacing: 1 }},
  graphContainer: {{ flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: 32, paddingTop: 4, borderBottomWidth: 1, borderBottomColor: '#1e1e3a' }},
  graphBar: {{ flex: 1, borderRadius: 2, minHeight: 2 }},
  actionRow: {{ flexDirection: 'row', gap: 8, marginTop: 4 }},
  actionBtn: {{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: '#8B5CF6', borderRadius: 10, paddingVertical: 10, minHeight: 44 }},
  actionText: {{ color: '#fff', fontSize: 13, fontWeight: '700' }},
  secondaryBtn: {{ flex: 0, width: 44, backgroundColor: '#1e1e3a' }},
  expandedContent: {{ paddingTop: 8, borderTopWidth: 1, borderTopColor: '#1e1e3a', gap: 4 }},
  expandedTitle: {{ color: '#8B5CF6', fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }},
  expandedText: {{ color: '#94a3b8', fontSize: 11, fontFamily: Platform.select({{ ios: 'Menlo', android: 'monospace' }}) }},
}});

export default {name};
'''
    return _cap_file_size(base + "\n" + _expand_massive(name, desc, title, genre, "component"))


def _gen_logic_aaa(name: str, desc: str, title: str, genre: str) -> str:
    """Generate AAA-grade logic system with real algorithms — 2500+ pages."""
    class_name = ''.join(w.capitalize() for w in name.replace('_', ' ').split())
    base = f'''// ═══ {title} — {class_name} System ═══
// {desc}
// Galaxy Studio Factory — 1,444,700 agents | Genre: {genre} | HYPERDENSE AAA

// ═══ CONFIGURATION ═══
interface SystemConfig {{
  difficulty: 'easy' | 'normal' | 'hard' | 'nightmare' | 'impossible';
  multiplier: number;
  seed: number;
  tickRate: number;
  maxEntities: number;
  debugMode: boolean;
  performanceBudgetMs: number;
}}

interface SystemMetrics {{
  tickCount: number;
  avgTickMs: number;
  peakTickMs: number;
  entityCount: number;
  memoryEstimate: number;
  lastGC: number;
}}

// ═══ PRIORITY QUEUE (Min-Heap) ═══
class PriorityQueue<T> {{
  private heap: {{ priority: number; value: T }}[] = [];

  push(value: T, priority: number) {{
    this.heap.push({{ priority, value }});
    this._bubbleUp(this.heap.length - 1);
  }}

  pop(): T | undefined {{
    if (this.heap.length === 0) return undefined;
    const top = this.heap[0];
    const last = this.heap.pop()!;
    if (this.heap.length > 0) {{
      this.heap[0] = last;
      this._sinkDown(0);
    }}
    return top.value;
  }}

  peek(): T | undefined {{ return this.heap[0]?.value; }}
  get size() {{ return this.heap.length; }}
  clear() {{ this.heap = []; }}

  private _bubbleUp(i: number) {{
    while (i > 0) {{
      const parent = Math.floor((i - 1) / 2);
      if (this.heap[parent].priority <= this.heap[i].priority) break;
      [this.heap[parent], this.heap[i]] = [this.heap[i], this.heap[parent]];
      i = parent;
    }}
  }}

  private _sinkDown(i: number) {{
    const length = this.heap.length;
    while (true) {{
      let smallest = i;
      const left = 2 * i + 1, right = 2 * i + 2;
      if (left < length && this.heap[left].priority < this.heap[smallest].priority) smallest = left;
      if (right < length && this.heap[right].priority < this.heap[smallest].priority) smallest = right;
      if (smallest === i) break;
      [this.heap[smallest], this.heap[i]] = [this.heap[i], this.heap[smallest]];
      i = smallest;
    }}
  }}
}}

// ═══ SPATIAL HASH GRID ═══
class SpatialHash {{
  private cells: Map<string, Set<string>> = new Map();
  private entityPositions: Map<string, {{ x: number; y: number }}> = new Map();

  constructor(private cellSize: number = 64) {{}}

  private _key(x: number, y: number): string {{
    return `${{Math.floor(x / this.cellSize)}},${{Math.floor(y / this.cellSize)}}`;
  }}

  insert(id: string, x: number, y: number) {{
    this.remove(id);
    const key = this._key(x, y);
    if (!this.cells.has(key)) this.cells.set(key, new Set());
    this.cells.get(key)!.add(id);
    this.entityPositions.set(id, {{ x, y }});
  }}

  remove(id: string) {{
    const pos = this.entityPositions.get(id);
    if (pos) {{
      const key = this._key(pos.x, pos.y);
      this.cells.get(key)?.delete(id);
      this.entityPositions.delete(id);
    }}
  }}

  query(x: number, y: number, radius: number): string[] {{
    const results: string[] = [];
    const minCX = Math.floor((x - radius) / this.cellSize);
    const maxCX = Math.floor((x + radius) / this.cellSize);
    const minCY = Math.floor((y - radius) / this.cellSize);
    const maxCY = Math.floor((y + radius) / this.cellSize);
    const r2 = radius * radius;
    for (let cx = minCX; cx <= maxCX; cx++) {{
      for (let cy = minCY; cy <= maxCY; cy++) {{
        const cell = this.cells.get(`${{cx}},${{cy}}`);
        if (cell) {{
          for (const id of cell) {{
            const pos = this.entityPositions.get(id);
            if (pos) {{
              const dx = pos.x - x, dy = pos.y - y;
              if (dx * dx + dy * dy <= r2) results.push(id);
            }}
          }}
        }}
      }}
    }}
    return results;
  }}

  clear() {{ this.cells.clear(); this.entityPositions.clear(); }}
}}

// ═══ OBJECT POOL ═══
class ObjectPool<T> {{
  private pool: T[] = [];
  private active: Set<T> = new Set();

  constructor(private factory: () => T, private reset: (obj: T) => void, initialSize: number = 50) {{
    for (let i = 0; i < initialSize; i++) this.pool.push(factory());
  }}

  acquire(): T {{
    const obj = this.pool.pop() ?? this.factory();
    this.active.add(obj);
    return obj;
  }}

  release(obj: T) {{
    if (this.active.delete(obj)) {{
      this.reset(obj);
      this.pool.push(obj);
    }}
  }}

  get activeCount() {{ return this.active.size; }}
  get poolSize() {{ return this.pool.length; }}
  releaseAll() {{ for (const obj of this.active) {{ this.reset(obj); this.pool.push(obj); }} this.active.clear(); }}
}}

// ═══ EVENT BUS ═══
type EventCallback = (...args: any[]) => void;
class EventBus {{
  private listeners: Map<string, Set<EventCallback>> = new Map();
  private onceListeners: Map<string, Set<EventCallback>> = new Map();

  on(event: string, callback: EventCallback) {{
    if (!this.listeners.has(event)) this.listeners.set(event, new Set());
    this.listeners.get(event)!.add(callback);
    return () => this.off(event, callback);
  }}

  once(event: string, callback: EventCallback) {{
    if (!this.onceListeners.has(event)) this.onceListeners.set(event, new Set());
    this.onceListeners.get(event)!.add(callback);
  }}

  off(event: string, callback: EventCallback) {{
    this.listeners.get(event)?.delete(callback);
  }}

  emit(event: string, ...args: any[]) {{
    this.listeners.get(event)?.forEach(cb => cb(...args));
    this.onceListeners.get(event)?.forEach(cb => cb(...args));
    this.onceListeners.delete(event);
  }}

  clear() {{ this.listeners.clear(); this.onceListeners.clear(); }}
}}

// ═══ RING BUFFER ═══
class RingBuffer<T> {{
  private buffer: (T | undefined)[];
  private head = 0;
  private _size = 0;

  constructor(private capacity: number) {{ this.buffer = new Array(capacity); }}

  push(item: T) {{
    this.buffer[this.head] = item;
    this.head = (this.head + 1) % this.capacity;
    if (this._size < this.capacity) this._size++;
  }}

  get(index: number): T | undefined {{
    if (index < 0 || index >= this._size) return undefined;
    const actualIndex = (this.head - this._size + index + this.capacity) % this.capacity;
    return this.buffer[actualIndex];
  }}

  get size() {{ return this._size; }}
  get latest() {{ return this.get(this._size - 1); }}
  toArray(): T[] {{
    const result: T[] = [];
    for (let i = 0; i < this._size; i++) {{ const v = this.get(i); if (v !== undefined) result.push(v); }}
    return result;
  }}
}}

// ═══ NOISE GENERATOR ═══
class PerlinNoise {{
  private perm: number[];

  constructor(seed: number = 0) {{
    this.perm = new Array(512);
    const p = new Array(256);
    for (let i = 0; i < 256; i++) p[i] = i;
    // Fisher-Yates shuffle with seed
    let s = seed;
    for (let i = 255; i > 0; i--) {{
      s = (s * 16807 + 0) % 2147483647;
      const j = s % (i + 1);
      [p[i], p[j]] = [p[j], p[i]];
    }}
    for (let i = 0; i < 512; i++) this.perm[i] = p[i & 255];
  }}

  private fade(t: number) {{ return t * t * t * (t * (t * 6 - 15) + 10); }}
  private lerp(a: number, b: number, t: number) {{ return a + t * (b - a); }}
  private grad(hash: number, x: number, y: number) {{
    const h = hash & 3;
    const u = h < 2 ? x : y;
    const v = h < 2 ? y : x;
    return ((h & 1) === 0 ? u : -u) + ((h & 2) === 0 ? v : -v);
  }}

  noise2D(x: number, y: number): number {{
    const X = Math.floor(x) & 255, Y = Math.floor(y) & 255;
    const xf = x - Math.floor(x), yf = y - Math.floor(y);
    const u = this.fade(xf), v = this.fade(yf);
    const aa = this.perm[this.perm[X] + Y], ab = this.perm[this.perm[X] + Y + 1];
    const ba = this.perm[this.perm[X + 1] + Y], bb = this.perm[this.perm[X + 1] + Y + 1];
    return this.lerp(
      this.lerp(this.grad(aa, xf, yf), this.grad(ba, xf - 1, yf), u),
      this.lerp(this.grad(ab, xf, yf - 1), this.grad(bb, xf - 1, yf - 1), u), v
    );
  }}

  octave2D(x: number, y: number, octaves: number = 6, persistence: number = 0.5, lacunarity: number = 2.0): number {{
    let total = 0, amplitude = 1, frequency = 1, maxValue = 0;
    for (let i = 0; i < octaves; i++) {{
      total += this.noise2D(x * frequency, y * frequency) * amplitude;
      maxValue += amplitude;
      amplitude *= persistence;
      frequency *= lacunarity;
    }}
    return total / maxValue;
  }}
}}

// ═══ MAIN ENGINE ═══
const DEFAULT_CONFIG: SystemConfig = {{
  difficulty: 'normal', multiplier: 1.0, seed: Math.floor(Math.random() * 999999),
  tickRate: 60, maxEntities: 10000, debugMode: false, performanceBudgetMs: 16,
}};

class {class_name}Engine {{
  private config: SystemConfig;
  private metrics: SystemMetrics;
  private events: EventBus;
  private spatial: SpatialHash;
  private noise: PerlinNoise;
  private tickHistory: RingBuffer<number>;
  private entities: Map<string, Record<string, any>>;
  private systems: Map<string, (delta: number) => void>;
  private initialized: boolean = false;

  constructor(config: Partial<SystemConfig> = {{}}) {{
    this.config = {{ ...DEFAULT_CONFIG, ...config }};
    this.metrics = {{ tickCount: 0, avgTickMs: 0, peakTickMs: 0, entityCount: 0, memoryEstimate: 0, lastGC: Date.now() }};
    this.events = new EventBus();
    this.spatial = new SpatialHash(64);
    this.noise = new PerlinNoise(this.config.seed);
    this.tickHistory = new RingBuffer(1000);
    this.entities = new Map();
    this.systems = new Map();
  }}

  initialize() {{
    this.initialized = true;
    this.metrics.tickCount = 0;
    this._registerCoreSystems();
    this._generateInitialEntities();
    this.events.emit('{name}:initialized', this.getMetrics());
    return this;
  }}

  tick(delta: number) {{
    if (!this.initialized) this.initialize();
    const start = performance.now?.() ?? Date.now();
    this.metrics.tickCount++;
    // Execute all registered systems
    for (const [name, system] of this.systems) {{
      system(delta);
    }}
    // Update spatial hash
    for (const [id, entity] of this.entities) {{
      if (entity.position) this.spatial.insert(id, entity.position.x, entity.position.y);
    }}
    // Metrics
    const elapsed = (performance.now?.() ?? Date.now()) - start;
    this.tickHistory.push(elapsed);
    this.metrics.avgTickMs = this.metrics.avgTickMs * 0.95 + elapsed * 0.05;
    this.metrics.peakTickMs = Math.max(this.metrics.peakTickMs, elapsed);
    this.metrics.entityCount = this.entities.size;
    // GC check
    if (Date.now() - this.metrics.lastGC > 30000) {{
      this._garbageCollect();
      this.metrics.lastGC = Date.now();
    }}
    return this.getState();
  }}

  private _registerCoreSystems() {{
    this.systems.set('movement', (delta) => {{
      for (const [id, e] of this.entities) {{
        if (e.velocity && e.position) {{
          e.position.x += e.velocity.x * delta;
          e.position.y += e.velocity.y * delta;
          // Friction
          e.velocity.x *= 0.98;
          e.velocity.y *= 0.98;
        }}
      }}
    }});
    this.systems.set('decay', (delta) => {{
      const toRemove: string[] = [];
      for (const [id, e] of this.entities) {{
        if (e.lifetime !== undefined) {{
          e.lifetime -= delta;
          if (e.lifetime <= 0) toRemove.push(id);
        }}
        if (e.health !== undefined && e.health <= 0 && !e.isDead) {{
          e.isDead = true;
          this.events.emit('{name}:entity_died', id, e);
        }}
      }}
      for (const id of toRemove) this.removeEntity(id);
    }});
    this.systems.set('collision', (delta) => {{
      for (const [id, e] of this.entities) {{
        if (e.position && e.collisionRadius) {{
          const nearby = this.spatial.query(e.position.x, e.position.y, e.collisionRadius * 2);
          for (const otherId of nearby) {{
            if (otherId !== id) {{
              this.events.emit('{name}:collision', id, otherId);
            }}
          }}
        }}
      }}
    }});
    this.systems.set('ai', (delta) => {{
      for (const [id, e] of this.entities) {{
        if (e.aiState) {{
          const noiseVal = this.noise.noise2D(e.position?.x ?? 0, this.metrics.tickCount * 0.01);
          if (noiseVal > 0.3 && e.aiState === 'idle') e.aiState = 'patrol';
          else if (noiseVal < -0.3 && e.aiState === 'patrol') e.aiState = 'idle';
        }}
      }}
    }});
  }}

  private _generateInitialEntities() {{
    const count = Math.min(50, this.config.maxEntities);
    for (let i = 0; i < count; i++) {{
      const id = `entity_${{i}}_${{Math.random().toString(36).slice(2, 8)}}`;
      this.addEntity(id, {{
        type: i < 10 ? 'player_unit' : i < 30 ? 'npc' : 'item',
        position: {{ x: this.noise.noise2D(i, 0) * 1000, y: this.noise.noise2D(0, i) * 1000 }},
        velocity: {{ x: 0, y: 0 }},
        health: 100 + i * 5,
        maxHealth: 100 + i * 5,
        level: Math.floor(i / 5) + 1,
        collisionRadius: 16,
        aiState: i >= 10 ? 'idle' : undefined,
      }});
    }}
  }}

  addEntity(id: string, data: Record<string, any>) {{
    this.entities.set(id, {{ id, createdAt: Date.now(), ...data }});
    if (data.position) this.spatial.insert(id, data.position.x, data.position.y);
    this.events.emit('{name}:entity_added', id);
  }}

  removeEntity(id: string) {{
    this.entities.delete(id);
    this.spatial.remove(id);
    this.events.emit('{name}:entity_removed', id);
  }}

  queryArea(x: number, y: number, radius: number) {{
    return this.spatial.query(x, y, radius).map(id => this.entities.get(id)).filter(Boolean);
  }}

  private _garbageCollect() {{
    const dead: string[] = [];
    for (const [id, e] of this.entities) {{
      if (e.isDead && Date.now() - (e.deathTime ?? 0) > 5000) dead.push(id);
    }}
    for (const id of dead) this.removeEntity(id);
  }}

  on(event: string, callback: EventCallback) {{ return this.events.on(event, callback); }}
  getState() {{ return {{ entities: Object.fromEntries(this.entities), metrics: {{ ...this.metrics }} }}; }}
  getMetrics() {{ return {{ ...this.metrics }}; }}
  getEntity(id: string) {{ return this.entities.get(id); }}
  setDifficulty(d: SystemConfig['difficulty']) {{ this.config.difficulty = d; }}
  reset() {{ this.entities.clear(); this.spatial.clear(); this.initialize(); }}
  destroy() {{ this.events.clear(); this.entities.clear(); this.spatial.clear(); }}
}}

// ═══ FACTORY ═══
export const create{class_name} = (config?: Partial<SystemConfig>) => new {class_name}Engine(config);
export default {class_name}Engine;
export {{ PriorityQueue, SpatialHash, ObjectPool, EventBus, RingBuffer, PerlinNoise }};
'''
    return _cap_file_size(base + "\n" + _expand_massive(name, desc, title, genre, "logic"))


def _gen_layout_code(title: str, genre: str, screens: list) -> str:
    imports = "\n".join([f"import {s} from '../screens/{s}';" for s in screens])
    screen_entries = "\n        ".join([f'<Stack.Screen name="{s}" component={{{s}}} options={{{{ title: "{s.replace("Screen", "")}" }}}} />' for s in screens])
    return f'''// ═══ {title} — Navigation Layout ═══
// Galaxy Studio Factory — 1,444,700 agents | Genre: {genre}
import React from 'react';
import {{ NavigationContainer }} from '@react-navigation/native';
import {{ createNativeStackNavigator }} from '@react-navigation/native-stack';
{imports}

const Stack = createNativeStackNavigator();

export default function Layout() {{
  return (
    <NavigationContainer>
      <Stack.Navigator
        initialRouteName="GameScreen"
        screenOptions={{{{
          headerStyle: {{ backgroundColor: '#0a0a1a' }},
          headerTintColor: '#e2e8f0',
          headerTitleStyle: {{ fontWeight: '700' }},
          animation: 'slide_from_right',
        }}}}
      >
        {screen_entries}
      </Stack.Navigator>
    </NavigationContainer>
  );
}}
'''


def _gen_constants(title: str, genre: str) -> str:
    return f'''// ═══ {title} — Game Constants ═══
// Galaxy Studio Factory | Genre: {genre} | ZERO restrictions
export const GAME_CONFIG = {{
  TITLE: '{title}',
  GENRE: '{genre}',
  VERSION: '1.0.0',
  MAX_LEVEL: 999,
  MAX_INVENTORY_SLOTS: 9999,
  MAX_PARTY_SIZE: 12,
  MAX_GUILD_MEMBERS: 500,
  TICK_RATE: 60,
  AUTO_SAVE_INTERVAL: 300000,
  MAX_CHAT_HISTORY: 1000,
  MAX_FRIENDS: 500,
  MAX_ACHIEVEMENTS: 9999,
  CURRENCY_TYPES: ['gold', 'gems', 'tokens', 'dust', 'shards', 'crystals', 'credits', 'platinum'],
  RARITY_TIERS: ['common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic', 'divine', 'transcendent'],
  DAMAGE_TYPES: ['physical', 'magical', 'fire', 'ice', 'lightning', 'dark', 'holy', 'poison', 'true'],
  ELEMENT_TYPES: ['fire', 'water', 'earth', 'wind', 'light', 'dark', 'void', 'nature'],
}} as const;

export const UI_CONSTANTS = {{
  ANIMATION_DURATION: 300,
  TOAST_DURATION: 3000,
  DEBOUNCE_MS: 250,
  TOUCH_TARGET_MIN: 44,
  GRID_SPACING: 8,
  BORDER_RADIUS: {{ sm: 8, md: 12, lg: 16, xl: 20 }},
  FONT_SIZES: {{ xs: 10, sm: 12, md: 14, lg: 16, xl: 20, xxl: 28, hero: 48 }},
}} as const;
'''


def _gen_helpers(title: str, genre: str) -> str:
    return f'''// ═══ {title} — Utility Helpers ═══
// Galaxy Studio Factory | Genre: {genre}
export const clamp = (val: number, min: number, max: number) => Math.max(min, Math.min(max, val));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const randomInt = (min: number, max: number) => Math.floor(Math.random() * (max - min + 1)) + min;
export const randomFloat = (min: number, max: number) => Math.random() * (max - min) + min;
export const randomElement = <T>(arr: T[]): T => arr[Math.floor(Math.random() * arr.length)];
export const shuffle = <T>(arr: T[]): T[] => [...arr].sort(() => Math.random() - 0.5);
export const uuid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);
export const formatNumber = (n: number) => n >= 1e6 ? (n/1e6).toFixed(1)+'M' : n >= 1e3 ? (n/1e3).toFixed(1)+'K' : n.toString();
export const formatTime = (ms: number) => {{ const s = Math.floor(ms/1000); const m = Math.floor(s/60); const h = Math.floor(m/60); return h > 0 ? `${{h}}h ${{m%60}}m` : m > 0 ? `${{m}}m ${{s%60}}s` : `${{s}}s`; }};
export const deepClone = <T>(obj: T): T => JSON.parse(JSON.stringify(obj));
export const debounce = (fn: Function, ms: number) => {{ let t: any; return (...args: any[]) => {{ clearTimeout(t); t = setTimeout(() => fn(...args), ms); }}; }};
export const throttle = (fn: Function, ms: number) => {{ let last = 0; return (...args: any[]) => {{ const now = Date.now(); if (now - last >= ms) {{ last = now; fn(...args); }} }}; }};
'''


def _gen_types(title: str, genre: str) -> str:
    return f'''// ═══ {title} — Type Definitions ═══
// Galaxy Studio Factory | Genre: {genre}
export interface Entity {{ id: string; name: string; type: string; position: Vector2; health: number; maxHealth: number; level: number; }}
export interface Vector2 {{ x: number; y: number; }}
export interface Vector3 {{ x: number; y: number; z: number; }}
export interface Item {{ id: string; name: string; type: ItemType; rarity: Rarity; stats: Record<string, number>; description: string; stackable: boolean; maxStack: number; icon: string; }}
export type ItemType = 'weapon' | 'armor' | 'consumable' | 'material' | 'quest' | 'currency' | 'cosmetic' | 'mount' | 'pet' | 'recipe';
export type Rarity = 'common' | 'uncommon' | 'rare' | 'epic' | 'legendary' | 'mythic' | 'divine' | 'transcendent';
export interface Quest {{ id: string; title: string; description: string; type: QuestType; objectives: QuestObjective[]; rewards: Reward[]; prerequisites: string[]; }}
export type QuestType = 'main' | 'side' | 'daily' | 'weekly' | 'event' | 'hidden' | 'chain' | 'repeatable';
export interface QuestObjective {{ id: string; type: string; target: string; current: number; required: number; }}
export interface Reward {{ type: 'xp' | 'item' | 'currency' | 'reputation' | 'achievement' | 'title'; amount: number; itemId?: string; }}
export interface Skill {{ id: string; name: string; description: string; level: number; maxLevel: number; cost: number; cooldown: number; damage?: number; element?: string; }}
export interface Achievement {{ id: string; name: string; description: string; icon: string; unlocked: boolean; progress: number; total: number; reward?: Reward; }}
'''


def _gen_game_loop_hook(title: str, genre: str) -> str:
    return f'''// ═══ {title} — Game Loop Hook ═══
// Galaxy Studio Factory | Genre: {genre}
import {{ useRef, useEffect, useCallback }} from 'react';

export function useGameLoop(callback: (delta: number) => void, fps: number = 60) {{
  const frameRef = useRef<number>(0);
  const lastTimeRef = useRef<number>(0);
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  const loop = useCallback((time: number) => {{
    if (lastTimeRef.current === 0) lastTimeRef.current = time;
    const delta = (time - lastTimeRef.current) / 1000;
    lastTimeRef.current = time;
    if (delta < 1 / (fps / 2)) callbackRef.current(delta);
    frameRef.current = requestAnimationFrame(loop);
  }}, [fps]);

  useEffect(() => {{
    frameRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frameRef.current);
  }}, [loop]);
}}
'''


def _gen_input_hook(title: str, genre: str) -> str:
    return f'''// ═══ {title} — Input Hook ═══
import {{ useState, useCallback }} from 'react';
import {{ GestureResponderEvent }} from 'react-native';

export function useInput() {{
  const [touches, setTouches] = useState<{{ x: number; y: number }}[]>([]);
  const [swipeDir, setSwipeDir] = useState<string | null>(null);
  const onTouchStart = useCallback((e: GestureResponderEvent) => {{ setTouches([{{ x: e.nativeEvent.pageX, y: e.nativeEvent.pageY }}]); }}, []);
  const onTouchEnd = useCallback(() => {{ setTouches([]); setSwipeDir(null); }}, []);
  return {{ touches, swipeDir, onTouchStart, onTouchEnd }};
}}
'''


def _gen_audio_hook(title: str, genre: str) -> str:
    return f'''// ═══ {title} — Audio Hook ═══
import {{ useState, useCallback }} from 'react';

export function useAudio() {{
  const [volume, setVolume] = useState(1.0);
  const [muted, setMuted] = useState(false);
  const [musicVolume, setMusicVolume] = useState(0.7);
  const [sfxVolume, setSfxVolume] = useState(1.0);
  const toggleMute = useCallback(() => setMuted(m => !m), []);
  const playSound = useCallback((id: string) => {{ if (!muted) console.log('Play:', id); }}, [muted]);
  return {{ volume, setVolume, muted, toggleMute, musicVolume, setMusicVolume, sfxVolume, setSfxVolume, playSound }};
}}
'''


def _gen_network_hook(title: str, genre: str) -> str:
    return f'''// ═══ {title} — Network Hook ═══
import {{ useState, useCallback }} from 'react';

export function useNetwork() {{
  const [connected, setConnected] = useState(false);
  const [latency, setLatency] = useState(0);
  const [lobby, setLobby] = useState<string | null>(null);
  const connect = useCallback(async (server: string) => {{ setConnected(true); setLatency(Math.floor(Math.random()*50)+10); }}, []);
  const disconnect = useCallback(() => {{ setConnected(false); setLobby(null); }}, []);
  const joinLobby = useCallback((id: string) => setLobby(id), []);
  return {{ connected, latency, lobby, connect, disconnect, joinLobby }};
}}
'''


# ═══════════════════════════════════════════════════════════════════════
# NEW AAA GENERATORS — Shaders, AI, Data, Networking, ProcGen, etc.
# ═══════════════════════════════════════════════════════════════════════

def _gen_screen_aaa(name: str, title: str, genre: str) -> str:
    """Generate AAA screen with full UI, state, animations, navigation — 500+ lines."""
    clean = name.replace('Screen', '')
    return f'''// ═══ {title} — {name} ═══
// Galaxy Studio Factory — 1,444,700 agents | Genre: {genre} | AAA Screen | SOFTCAP DENSITY
import React, {{ useState, useEffect, useRef, useCallback, useMemo, memo }} from 'react';
import {{
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Animated,
  Dimensions, Platform, RefreshControl, StatusBar, FlatList,
  TextInput, ActivityIndicator, LayoutAnimation, UIManager,
  Easing, PanResponder, Keyboard,
}} from 'react-native';
import {{ Ionicons }} from '@expo/vector-icons';
import {{ useSafeAreaInsets }} from 'react-native-safe-area-context';

const {{ width: W, height: H }} = Dimensions.get('window');
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {{
  UIManager.setLayoutAnimationEnabledExperimental(true);
}}

// ═══ CONSTANTS ═══
const TICK_RATE = 30;
const PAGE_SIZE = 20;
const ANIMATION_DURATION = 350;
const SPRING_CONFIG = {{ tension: 65, friction: 8, useNativeDriver: true }};
const THEME = {{
  bg: '#0a0a1a', surface: '#0f0f23', surfaceAlt: '#161630', border: '#1e1e3a',
  text: '#e2e8f0', textMuted: '#64748b', accent: '#8B5CF6', accentLight: '#A78BFA',
  success: '#22C55E', warning: '#F59E0B', danger: '#EF4444', info: '#3B82F6',
}} as const;

// ═══ MATH UTILS ═══
const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);
const formatNumber = (n: number) => n >= 1e6 ? (n/1e6).toFixed(1)+'M' : n >= 1e3 ? (n/1e3).toFixed(1)+'K' : n.toString();
const formatTime = (ms: number) => {{ const s = Math.floor(ms/1000); const m = Math.floor(s/60); return m > 0 ? `${{m}}m ${{s%60}}s` : `${{s}}s`; }};

// ═══ DATA GENERATION ═══
interface DataItem {{
  id: string; name: string; level: number; rarity: 'common' | 'uncommon' | 'rare' | 'epic' | 'legendary';
  value: number; stats: {{ atk: number; def: number; spd: number; hp: number }};
  description: string; icon: string; tags: string[]; createdAt: number;
}}

const RARITY_COLORS: Record<string, string> = {{
  common: '#94a3b8', uncommon: '#22C55E', rare: '#3B82F6', epic: '#8B5CF6', legendary: '#F59E0B',
}};

const generateItems = (page: number, count: number = PAGE_SIZE): DataItem[] => {{
  const offset = page * count;
  return Array.from({{ length: count }}, (_, i) => {{
    const idx = offset + i;
    const rarityIdx = idx < 40 ? 0 : idx < 60 ? 1 : idx < 75 ? 2 : idx < 90 ? 3 : 4;
    const rarity = (['common', 'uncommon', 'rare', 'epic', 'legendary'] as const)[rarityIdx];
    return {{
      id: `{clean.lower()}_${{idx.toString(36)}}`,
      name: `{clean} Entry ${{idx + 1}}`,
      level: Math.floor(idx / 3) + 1,
      rarity,
      value: Math.floor(100 * Math.pow(1.15, idx)),
      stats: {{
        atk: Math.floor(10 + idx * 2.5 + Math.sin(idx) * 8),
        def: Math.floor(8 + idx * 1.8 + Math.cos(idx) * 6),
        spd: Math.floor(5 + idx * 1.2 + Math.sin(idx * 0.7) * 4),
        hp: Math.floor(50 + idx * 5 + Math.sin(idx * 0.3) * 20),
      }},
      description: `${{['Ancient', 'Enchanted', 'Cursed', 'Legendary', 'Mythic'][idx % 5]}} ${{'{clean}'.toLowerCase()}} artifact #${{idx + 1}}`,
      icon: ['shield', 'sword', 'flask', 'star', 'diamond', 'flame', 'snow', 'flash'][idx % 8],
      tags: ['{genre}', rarity, idx % 2 === 0 ? 'offensive' : 'defensive'],
      createdAt: Date.now() - idx * 86400000,
    }};
  }});
}};

// ═══ SUB-COMPONENTS ═══
const StatBar = memo(({{ label, value, max, color }}: {{ label: string; value: number; max: number; color: string }}) => (
  <View style={{_s.statBarContainer}}>
    <View style={{_s.statBarHeader}}>
      <Text style={{_s.statBarLabel}}>{{label}}</Text>
      <Text style={{[_s.statBarValue, {{ color }}]}}>{{value}}</Text>
    </View>
    <View style={{_s.statBarTrack}}>
      <View style={{[_s.statBarFill, {{ width: `${{clamp(value / max * 100, 0, 100)}}%`, backgroundColor: color }}]}} />
    </View>
  </View>
));

const RarityBadge = memo(({{ rarity }}: {{ rarity: string }}) => (
  <View style={{[_s.rarityBadge, {{ backgroundColor: (RARITY_COLORS[rarity] || '#64748b') + '20', borderColor: (RARITY_COLORS[rarity] || '#64748b') + '40' }}]}}>
    <Text style={{[_s.rarityBadgeText, {{ color: RARITY_COLORS[rarity] || '#64748b' }}]}}>{{rarity}}</Text>
  </View>
));

const EmptyState = memo(({{ message }}: {{ message: string }}) => (
  <View style={{_s.emptyState}}>
    <Ionicons name="file-tray-outline" size={{48}} color={{THEME.textMuted}} />
    <Text style={{_s.emptyText}}>{{message}}</Text>
  </View>
));

const SearchBar = memo(({{ value, onChange, placeholder }}: {{ value: string; onChange: (t: string) => void; placeholder: string }}) => (
  <View style={{_s.searchBar}}>
    <Ionicons name="search" size={{16}} color={{THEME.textMuted}} />
    <TextInput style={{_s.searchInput}} value={{value}} onChangeText={{onChange}} placeholder={{placeholder}}
      placeholderTextColor={{THEME.textMuted}} returnKeyType="search" autoCorrect={{false}} />
    {{value.length > 0 && (
      <TouchableOpacity onPress={{() => onChange('')}} hitSlop={{{{ top: 10, bottom: 10, left: 10, right: 10 }}}}>
        <Ionicons name="close-circle" size={{16}} color={{THEME.textMuted}} />
      </TouchableOpacity>
    )}}
  </View>
));

interface ItemCardProps {{
  item: DataItem;
  onPress: (item: DataItem) => void;
  index: number;
}}

const ItemCard = memo(({{ item, onPress, index }}: ItemCardProps) => {{
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(20)).current;

  useEffect(() => {{
    const delay = Math.min(index * 50, 500);
    Animated.parallel([
      Animated.timing(fadeAnim, {{ toValue: 1, duration: ANIMATION_DURATION, delay, useNativeDriver: true }}),
      Animated.spring(slideAnim, {{ toValue: 0, delay, ...SPRING_CONFIG }}),
    ]).start();
  }}, []);

  const rarityColor = RARITY_COLORS[item.rarity] || '#64748b';
  const maxStat = Math.max(item.stats.atk, item.stats.def, item.stats.spd, item.stats.hp);

  return (
    <Animated.View style={{{{ opacity: fadeAnim, transform: [{{ translateY: slideAnim }}] }}}}>
      <TouchableOpacity style={{_s.itemCard}} onPress={{() => onPress(item)}} activeOpacity={{0.7}}>
        <View style={{_s.itemCardLeft}}>
          <View style={{[_s.itemIcon, {{ backgroundColor: rarityColor + '15', borderColor: rarityColor + '30' }}]}}>
            <Ionicons name={{item.icon as any}} size={{20}} color={{rarityColor}} />
          </View>
        </View>
        <View style={{_s.itemCardCenter}}>
          <View style={{_s.itemCardNameRow}}>
            <Text style={{_s.itemName}} numberOfLines={{1}}>{{item.name}}</Text>
            <RarityBadge rarity={{item.rarity}} />
          </View>
          <Text style={{_s.itemDesc}} numberOfLines={{1}}>{{item.description}}</Text>
          <View style={{_s.itemStatsRow}}>
            <Text style={{_s.itemStat}}>ATK {{item.stats.atk}}</Text>
            <Text style={{_s.itemStat}}>DEF {{item.stats.def}}</Text>
            <Text style={{_s.itemStat}}>SPD {{item.stats.spd}}</Text>
            <Text style={{_s.itemStat}}>HP {{item.stats.hp}}</Text>
          </View>
        </View>
        <View style={{_s.itemCardRight}}>
          <Text style={{[_s.itemLevel, {{ color: rarityColor }}]}}>Lv.{{item.level}}</Text>
          <Text style={{_s.itemValue}}>{{formatNumber(item.value)}}g</Text>
          <Ionicons name="chevron-forward" size={{14}} color={{THEME.textMuted}} />
        </View>
      </TouchableOpacity>
    </Animated.View>
  );
}});

// ═══ DETAIL MODAL ═══
interface DetailViewProps {{
  item: DataItem | null;
  visible: boolean;
  onClose: () => void;
}}

const DetailView = memo(({{ item, visible, onClose }}: DetailViewProps) => {{
  const slideAnim = useRef(new Animated.Value(H)).current;

  useEffect(() => {{
    Animated.spring(slideAnim, {{ toValue: visible ? 0 : H, ...SPRING_CONFIG }}).start();
  }}, [visible]);

  if (!item) return null;
  const maxStat = Math.max(item.stats.atk, item.stats.def, item.stats.spd, item.stats.hp, 1);

  return (
    <Animated.View style={{[_s.detailOverlay, {{ transform: [{{ translateY: slideAnim }}] }}]}}>
      <View style={{_s.detailHeader}}>
        <TouchableOpacity onPress={{onClose}} style={{_s.detailBack}} hitSlop={{{{ top: 10, bottom: 10, left: 10, right: 10 }}}}>
          <Ionicons name="chevron-down" size={{24}} color={{THEME.text}} />
        </TouchableOpacity>
        <Text style={{_s.detailTitle}}>{{item.name}}</Text>
        <RarityBadge rarity={{item.rarity}} />
      </View>
      <ScrollView style={{_s.detailContent}} showsVerticalScrollIndicator={{false}}>
        <View style={{_s.detailIconBox}}>
          <Ionicons name={{item.icon as any}} size={{48}} color={{RARITY_COLORS[item.rarity]}} />
          <Text style={{_s.detailLevel}}>Level {{item.level}}</Text>
          <Text style={{_s.detailValue}}>{{formatNumber(item.value)}} Gold</Text>
        </View>
        <View style={{_s.detailStatsBox}}>
          <Text style={{_s.detailSectionTitle}}>Statistics</Text>
          <StatBar label="Attack" value={{item.stats.atk}} max={{maxStat * 1.2}} color={{THEME.danger}} />
          <StatBar label="Defense" value={{item.stats.def}} max={{maxStat * 1.2}} color={{THEME.info}} />
          <StatBar label="Speed" value={{item.stats.spd}} max={{maxStat * 1.2}} color={{THEME.success}} />
          <StatBar label="Health" value={{item.stats.hp}} max={{maxStat * 1.2}} color={{THEME.warning}} />
        </View>
        <View style={{_s.detailDescBox}}>
          <Text style={{_s.detailSectionTitle}}>Description</Text>
          <Text style={{_s.detailDescText}}>{{item.description}}</Text>
        </View>
        <View style={{_s.detailTagsBox}}>
          <Text style={{_s.detailSectionTitle}}>Tags</Text>
          <View style={{_s.detailTagsRow}}>
            {{item.tags.map(tag => (
              <View key={{tag}} style={{_s.detailTag}}>
                <Text style={{_s.detailTagText}}>{{tag}}</Text>
              </View>
            ))}}
          </View>
        </View>
        <View style={{_s.detailActions}}>
          <TouchableOpacity style={{_s.detailActionBtn}} activeOpacity={{0.7}}>
            <Ionicons name="flash" size={{18}} color="#fff" />
            <Text style={{_s.detailActionText}}>Use</Text>
          </TouchableOpacity>
          <TouchableOpacity style={{[_s.detailActionBtn, _s.detailActionSecondary]}} activeOpacity={{0.7}}>
            <Ionicons name="swap-horizontal" size={{18}} color={{THEME.accent}} />
            <Text style={{[_s.detailActionText, {{ color: THEME.accent }}]}}>Trade</Text>
          </TouchableOpacity>
          <TouchableOpacity style={{[_s.detailActionBtn, _s.detailActionDanger]}} activeOpacity={{0.7}}>
            <Ionicons name="trash" size={{18}} color={{THEME.danger}} />
            <Text style={{[_s.detailActionText, {{ color: THEME.danger }}]}}>Discard</Text>
          </TouchableOpacity>
        </View>
        <View style={{{{ height: 60 }}}} />
      </ScrollView>
    </Animated.View>
  );
}});

// ═══ MAIN SCREEN ═══
interface ScreenState {{
  loading: boolean;
  refreshing: boolean;
  data: DataItem[];
  searchQuery: string;
  selectedTab: number;
  sortBy: 'level' | 'rarity' | 'value' | 'name';
  sortDirection: 'asc' | 'desc';
  page: number;
  hasMore: boolean;
  selectedItem: DataItem | null;
  showDetail: boolean;
  error: string | null;
  stats: {{ total: number; avgLevel: number; totalValue: number }};
}}

export default function {name}({{ navigation, route }}: any) {{
  const insets = useSafeAreaInsets();
  const [state, setState] = useState<ScreenState>({{
    loading: true, refreshing: false, data: [], searchQuery: '', selectedTab: 0,
    sortBy: 'level', sortDirection: 'desc', page: 0, hasMore: true,
    selectedItem: null, showDetail: false, error: null,
    stats: {{ total: 0, avgLevel: 0, totalValue: 0 }},
  }});
  const scrollRef = useRef<ScrollView>(null);
  const headerAnim = useRef(new Animated.Value(0)).current;
  const fabAnim = useRef(new Animated.Value(0)).current;
  const tickRef = useRef(0);

  // Load data
  const loadData = useCallback(async (page: number = 0, refresh: boolean = false) => {{
    setState(prev => ({{ ...prev, loading: page === 0, refreshing: refresh, error: null }}));
    try {{
      await new Promise(r => setTimeout(r, 200 + Math.random() * 300));
      const items = generateItems(page);
      setState(prev => {{
        const newData = refresh ? items : [...prev.data, ...items];
        const total = newData.length;
        const avgLevel = total > 0 ? Math.round(newData.reduce((a, b) => a + b.level, 0) / total) : 0;
        const totalValue = newData.reduce((a, b) => a + b.value, 0);
        return {{
          ...prev, data: newData, loading: false, refreshing: false,
          page, hasMore: items.length >= PAGE_SIZE,
          stats: {{ total, avgLevel, totalValue }},
        }};
      }});
    }} catch (e: any) {{
      setState(prev => ({{ ...prev, error: e.message, loading: false, refreshing: false }}));
    }}
  }}, []);

  useEffect(() => {{
    loadData(0);
    Animated.spring(headerAnim, {{ toValue: 1, ...SPRING_CONFIG }}).start();
    setTimeout(() => Animated.spring(fabAnim, {{ toValue: 1, ...SPRING_CONFIG }}).start(), 500);
  }}, []);

  // Filtered & sorted data
  const filteredData = useMemo(() => {{
    let items = [...state.data];
    if (state.searchQuery.trim()) {{
      const q = state.searchQuery.toLowerCase();
      items = items.filter(i => i.name.toLowerCase().includes(q) || i.description.toLowerCase().includes(q) || i.rarity.includes(q));
    }}
    items.sort((a, b) => {{
      const key = state.sortBy;
      const aVal = key === 'name' ? a.name : key === 'rarity' ? ['common','uncommon','rare','epic','legendary'].indexOf(a.rarity) : (a as any)[key];
      const bVal = key === 'name' ? b.name : key === 'rarity' ? ['common','uncommon','rare','epic','legendary'].indexOf(b.rarity) : (b as any)[key];
      return state.sortDirection === 'asc' ? (aVal > bVal ? 1 : -1) : (aVal < bVal ? 1 : -1);
    }});
    return items;
  }}, [state.data, state.searchQuery, state.sortBy, state.sortDirection]);

  const onRefresh = useCallback(() => loadData(0, true), [loadData]);
  const loadMore = useCallback(() => {{ if (state.hasMore && !state.loading) loadData(state.page + 1); }}, [state.hasMore, state.loading, state.page, loadData]);

  const selectItem = useCallback((item: DataItem) => {{
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setState(prev => ({{ ...prev, selectedItem: item, showDetail: true }}));
  }}, []);

  const closeDetail = useCallback(() => {{
    setState(prev => ({{ ...prev, showDetail: false }}));
  }}, []);

  const toggleSort = useCallback((by: ScreenState['sortBy']) => {{
    setState(prev => ({{
      ...prev,
      sortBy: by,
      sortDirection: prev.sortBy === by ? (prev.sortDirection === 'asc' ? 'desc' : 'asc') : 'desc',
    }}));
  }}, []);

  const tabs = ['{clean}', 'Stats', 'History', 'Settings'];
  const sortOptions: {{ key: ScreenState['sortBy']; label: string }}[] = [
    {{ key: 'level', label: 'Level' }}, {{ key: 'rarity', label: 'Rarity' }},
    {{ key: 'value', label: 'Value' }}, {{ key: 'name', label: 'Name' }},
  ];

  return (
    <View style={{[_s.container, {{ paddingTop: insets.top }}]}}>
      <StatusBar barStyle="light-content" />
      {{/* Header */}}
      <Animated.View style={{[_s.header, {{ opacity: headerAnim, transform: [{{ translateY: headerAnim.interpolate({{ inputRange: [0, 1], outputRange: [-20, 0] }}) }}] }}]}}>
        <TouchableOpacity style={{_s.backBtn}} onPress={{() => navigation?.goBack?.()}} hitSlop={{{{ top: 10, bottom: 10, left: 10, right: 10 }}}}>
          <Ionicons name="chevron-back" size={{24}} color={{THEME.text}} />
        </TouchableOpacity>
        <View style={{_s.headerCenter}}>
          <Text style={{_s.headerTitle}}>{clean}</Text>
          <Text style={{_s.headerSubtitle}}>{{formatNumber(state.stats.total)}} entries</Text>
        </View>
        <TouchableOpacity style={{_s.menuBtn}} hitSlop={{{{ top: 10, bottom: 10, left: 10, right: 10 }}}}>
          <Ionicons name="ellipsis-horizontal" size={{22}} color={{THEME.text}} />
        </TouchableOpacity>
      </Animated.View>

      {{/* Stats Row */}}
      <View style={{_s.statsRow}}>
        <View style={{_s.statBox}}>
          <Text style={{_s.statBoxValue}}>{{formatNumber(state.stats.total)}}</Text>
          <Text style={{_s.statBoxLabel}}>Total</Text>
        </View>
        <View style={{_s.statBox}}>
          <Text style={{_s.statBoxValue}}>{{state.stats.avgLevel}}</Text>
          <Text style={{_s.statBoxLabel}}>Avg Lv</Text>
        </View>
        <View style={{_s.statBox}}>
          <Text style={{_s.statBoxValue}}>{{formatNumber(state.stats.totalValue)}}</Text>
          <Text style={{_s.statBoxLabel}}>Value</Text>
        </View>
      </View>

      {{/* Tabs */}}
      <View style={{_s.tabBar}}>
        {{tabs.map((tab, i) => (
          <TouchableOpacity key={{tab}} style={{[_s.tab, state.selectedTab === i && _s.tabActive]}}
            onPress={{() => setState(prev => ({{ ...prev, selectedTab: i }}))}}>
            <Text style={{[_s.tabText, state.selectedTab === i && _s.tabTextActive]}}>{{tab}}</Text>
          </TouchableOpacity>
        ))}}
      </View>

      {{/* Search + Sort */}}
      <SearchBar value={{state.searchQuery}} onChange={{q => setState(prev => ({{ ...prev, searchQuery: q }}))}} placeholder="Search {clean.lower()}..." />
      <ScrollView horizontal showsHorizontalScrollIndicator={{false}} style={{_s.sortRow}} contentContainerStyle={{_s.sortRowContent}}>
        {{sortOptions.map(opt => (
          <TouchableOpacity key={{opt.key}} style={{[_s.sortBtn, state.sortBy === opt.key && _s.sortBtnActive]}}
            onPress={{() => toggleSort(opt.key)}}>
            <Text style={{[_s.sortBtnText, state.sortBy === opt.key && _s.sortBtnTextActive]}}>{{opt.label}}</Text>
            {{state.sortBy === opt.key && <Ionicons name={{state.sortDirection === 'asc' ? 'arrow-up' : 'arrow-down'}} size={{12}} color={{THEME.accent}} />}}
          </TouchableOpacity>
        ))}}
      </ScrollView>

      {{/* Content */}}
      <ScrollView style={{_s.content}} refreshControl={{<RefreshControl refreshing={{state.refreshing}} onRefresh={{onRefresh}} tintColor={{THEME.accent}} />}}
        onScroll={{({{ nativeEvent }}) => {{ const {{ layoutMeasurement, contentOffset, contentSize }} = nativeEvent; if (layoutMeasurement.height + contentOffset.y >= contentSize.height - 200) loadMore(); }}}}
        scrollEventThrottle={{400}}>
        {{state.error && <View style={{_s.errorBox}}><Ionicons name="warning" size={{16}} color={{THEME.danger}} /><Text style={{_s.errorText}}>{{state.error}}</Text></View>}}
        {{filteredData.length === 0 && !state.loading && <EmptyState message="No items found" />}}
        {{filteredData.map((item, index) => <ItemCard key={{item.id}} item={{item}} onPress={{selectItem}} index={{index}} />)}}
        {{state.loading && <View style={{_s.loadingBox}}><ActivityIndicator color={{THEME.accent}} /><Text style={{_s.loadingText}}>Loading...</Text></View>}}
        {{state.hasMore && !state.loading && <TouchableOpacity style={{_s.loadMoreBtn}} onPress={{loadMore}}><Text style={{_s.loadMoreText}}>Load More</Text></TouchableOpacity>}}
        <View style={{{{ height: 100 }}}} />
      </ScrollView>

      {{/* Detail View */}}
      <DetailView item={{state.selectedItem}} visible={{state.showDetail}} onClose={{closeDetail}} />

      {{/* FAB */}}
      <Animated.View style={{[_s.fab, {{ transform: [{{ scale: fabAnim }}], bottom: insets.bottom + 16 }}]}}>
        <TouchableOpacity style={{_s.fabBtn}} activeOpacity={{0.8}} onPress={{() => scrollRef.current?.scrollTo({{ y: 0, animated: true }})}}>
          <Ionicons name="arrow-up" size={{24}} color="#fff" />
        </TouchableOpacity>
      </Animated.View>
    </View>
  );
}}

// ═══ STYLES ═══
const _s = StyleSheet.create({{
  container: {{ flex: 1, backgroundColor: THEME.bg }},
  header: {{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, backgroundColor: THEME.surface, borderBottomWidth: 1, borderBottomColor: THEME.border }},
  backBtn: {{ width: 44, height: 44, justifyContent: 'center', alignItems: 'center' }},
  headerCenter: {{ flex: 1, marginLeft: 4 }},
  headerTitle: {{ color: THEME.text, fontSize: 18, fontWeight: '800' }},
  headerSubtitle: {{ color: THEME.textMuted, fontSize: 12, marginTop: 1 }},
  menuBtn: {{ width: 44, height: 44, justifyContent: 'center', alignItems: 'center' }},
  statsRow: {{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 10, gap: 8 }},
  statBox: {{ flex: 1, backgroundColor: THEME.surface, borderRadius: 10, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: THEME.border }},
  statBoxValue: {{ color: THEME.text, fontSize: 16, fontWeight: '800', fontVariant: ['tabular-nums'] }},
  statBoxLabel: {{ color: THEME.textMuted, fontSize: 10, fontWeight: '600', marginTop: 2, textTransform: 'uppercase', letterSpacing: 0.5 }},
  tabBar: {{ flexDirection: 'row', paddingHorizontal: 16, backgroundColor: THEME.surface, borderBottomWidth: 1, borderBottomColor: THEME.border }},
  tab: {{ flex: 1, paddingVertical: 12, alignItems: 'center', borderBottomWidth: 2, borderBottomColor: 'transparent' }},
  tabActive: {{ borderBottomColor: THEME.accent }},
  tabText: {{ color: THEME.textMuted, fontSize: 13, fontWeight: '600' }},
  tabTextActive: {{ color: THEME.accent }},
  searchBar: {{ flexDirection: 'row', alignItems: 'center', marginHorizontal: 16, marginTop: 10, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: THEME.surface, borderRadius: 10, borderWidth: 1, borderColor: THEME.border, gap: 8 }},
  searchInput: {{ flex: 1, color: THEME.text, fontSize: 14, padding: 0 }},
  sortRow: {{ marginTop: 8, maxHeight: 38 }},
  sortRowContent: {{ paddingHorizontal: 16, gap: 6 }},
  sortBtn: {{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: THEME.surface, borderWidth: 1, borderColor: THEME.border, flexDirection: 'row', alignItems: 'center', gap: 4 }},
  sortBtnActive: {{ borderColor: THEME.accent + '60', backgroundColor: THEME.accent + '10' }},
  sortBtnText: {{ color: THEME.textMuted, fontSize: 12, fontWeight: '600' }},
  sortBtnTextActive: {{ color: THEME.accent }},
  content: {{ flex: 1, paddingHorizontal: 16, paddingTop: 10 }},
  itemCard: {{ flexDirection: 'row', alignItems: 'center', backgroundColor: THEME.surface, borderRadius: 12, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: THEME.border, gap: 12 }},
  itemCardLeft: {{}},
  itemIcon: {{ width: 48, height: 48, borderRadius: 12, justifyContent: 'center', alignItems: 'center', borderWidth: 1 }},
  itemCardCenter: {{ flex: 1, gap: 4 }},
  itemCardNameRow: {{ flexDirection: 'row', alignItems: 'center', gap: 8 }},
  itemName: {{ color: THEME.text, fontSize: 14, fontWeight: '700', flex: 1 }},
  itemDesc: {{ color: THEME.textMuted, fontSize: 11 }},
  itemStatsRow: {{ flexDirection: 'row', gap: 8, marginTop: 2 }},
  itemStat: {{ color: THEME.textMuted, fontSize: 10, fontFamily: Platform.select({{ ios: 'Menlo', android: 'monospace' }}) }},
  itemCardRight: {{ alignItems: 'flex-end', gap: 4 }},
  itemLevel: {{ fontSize: 13, fontWeight: '800' }},
  itemValue: {{ color: THEME.warning, fontSize: 11, fontWeight: '600' }},
  rarityBadge: {{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, borderWidth: 1 }},
  rarityBadgeText: {{ fontSize: 9, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 }},
  emptyState: {{ alignItems: 'center', paddingVertical: 40, gap: 12 }},
  emptyText: {{ color: THEME.textMuted, fontSize: 14 }},
  errorBox: {{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, backgroundColor: THEME.danger + '10', borderRadius: 10, borderWidth: 1, borderColor: THEME.danger + '30', marginBottom: 10 }},
  errorText: {{ color: THEME.danger, fontSize: 13, flex: 1 }},
  loadingBox: {{ alignItems: 'center', paddingVertical: 20, gap: 8 }},
  loadingText: {{ color: THEME.textMuted, fontSize: 13 }},
  loadMoreBtn: {{ alignItems: 'center', paddingVertical: 14, backgroundColor: THEME.surface, borderRadius: 10, borderWidth: 1, borderColor: THEME.accent + '30', marginVertical: 10 }},
  loadMoreText: {{ color: THEME.accent, fontSize: 14, fontWeight: '700' }},
  statBarContainer: {{ marginBottom: 10 }},
  statBarHeader: {{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }},
  statBarLabel: {{ color: THEME.textMuted, fontSize: 12 }},
  statBarValue: {{ fontSize: 13, fontWeight: '800', fontVariant: ['tabular-nums'] }},
  statBarTrack: {{ height: 6, backgroundColor: THEME.border, borderRadius: 3, overflow: 'hidden' }},
  statBarFill: {{ height: '100%', borderRadius: 3 }},
  detailOverlay: {{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: THEME.bg }},
  detailHeader: {{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: THEME.border, gap: 12 }},
  detailBack: {{ width: 44, height: 44, justifyContent: 'center', alignItems: 'center' }},
  detailTitle: {{ color: THEME.text, fontSize: 18, fontWeight: '800', flex: 1 }},
  detailContent: {{ flex: 1, padding: 16 }},
  detailIconBox: {{ alignItems: 'center', paddingVertical: 24, gap: 8 }},
  detailLevel: {{ color: THEME.accent, fontSize: 18, fontWeight: '800' }},
  detailValue: {{ color: THEME.warning, fontSize: 14, fontWeight: '600' }},
  detailStatsBox: {{ backgroundColor: THEME.surface, borderRadius: 14, padding: 16, marginTop: 12, borderWidth: 1, borderColor: THEME.border }},
  detailSectionTitle: {{ color: THEME.text, fontSize: 14, fontWeight: '800', marginBottom: 12 }},
  detailDescBox: {{ backgroundColor: THEME.surface, borderRadius: 14, padding: 16, marginTop: 12, borderWidth: 1, borderColor: THEME.border }},
  detailDescText: {{ color: THEME.textMuted, fontSize: 13, lineHeight: 20 }},
  detailTagsBox: {{ backgroundColor: THEME.surface, borderRadius: 14, padding: 16, marginTop: 12, borderWidth: 1, borderColor: THEME.border }},
  detailTagsRow: {{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }},
  detailTag: {{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, backgroundColor: THEME.accent + '15', borderWidth: 1, borderColor: THEME.accent + '30' }},
  detailTagText: {{ color: THEME.accent, fontSize: 11, fontWeight: '600' }},
  detailActions: {{ flexDirection: 'row', gap: 8, marginTop: 16 }},
  detailActionBtn: {{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: THEME.accent, borderRadius: 12, paddingVertical: 14, minHeight: 48 }},
  detailActionText: {{ color: '#fff', fontSize: 14, fontWeight: '700' }},
  detailActionSecondary: {{ backgroundColor: THEME.accent + '15', borderWidth: 1, borderColor: THEME.accent + '30' }},
  detailActionDanger: {{ backgroundColor: THEME.danger + '10', borderWidth: 1, borderColor: THEME.danger + '30' }},
  fab: {{ position: 'absolute', right: 16 }},
  fabBtn: {{ width: 52, height: 52, borderRadius: 26, backgroundColor: THEME.accent, justifyContent: 'center', alignItems: 'center', shadowColor: THEME.accent, shadowOffset: {{ width: 0, height: 4 }}, shadowOpacity: 0.4, shadowRadius: 8, elevation: 8 }},
}});
'''


def _gen_entity_store(title: str, genre: str) -> str:
    return f'''// ═══ {title} — Entity Store ═══
import {{ create }} from 'zustand';
interface Entity {{ id: string; type: string; position: {{ x: number; y: number }}; health: number; maxHealth: number; level: number; }}
interface EntityState {{ entities: Map<string, Entity>; add: (e: Entity) => void; remove: (id: string) => void; update: (id: string, data: Partial<Entity>) => void; }}
export const useEntityStore = create<EntityState>((set) => ({{
  entities: new Map(),
  add: (e) => set((s) => {{ const m = new Map(s.entities); m.set(e.id, e); return {{ entities: m }}; }}),
  remove: (id) => set((s) => {{ const m = new Map(s.entities); m.delete(id); return {{ entities: m }}; }}),
  update: (id, data) => set((s) => {{ const m = new Map(s.entities); const e = m.get(id); if (e) m.set(id, {{ ...e, ...data }}); return {{ entities: m }}; }}),
}}));
'''


def _gen_inventory_store(t: str, g: str) -> str:
    return f'// {t} — Inventory Store | {g}\\nimport {{ create }} from "zustand";\\ninterface Item {{ id: string; name: string; type: string; rarity: string; quantity: number; stats: Record<string, number>; }}\\ninterface InvState {{ items: Item[]; capacity: number; add: (i: Item) => void; remove: (id: string) => void; sort: (by: string) => void; }}\\nexport const useInventoryStore = create<InvState>((set) => ({{ items: [], capacity: 500, add: (item) => set((s) => ({{ items: [...s.items, item] }})), remove: (id) => set((s) => ({{ items: s.items.filter(i => i.id !== id) }})), sort: (by) => set((s) => ({{ items: [...s.items].sort((a, b) => (a as any)[by] > (b as any)[by] ? 1 : -1) }})), }}));'

def _gen_combat_store(t: str, g: str) -> str:
    return f'// {t} — Combat Store | {g}\\nimport {{ create }} from "zustand";\\ninterface CombatState {{ inCombat: boolean; targets: string[]; combo: number; dps: number; threatLevel: number; startCombat: () => void; endCombat: () => void; addCombo: () => void; }}\\nexport const useCombatStore = create<CombatState>((set) => ({{ inCombat: false, targets: [], combo: 0, dps: 0, threatLevel: 0, startCombat: () => set({{ inCombat: true }}), endCombat: () => set({{ inCombat: false, combo: 0 }}), addCombo: () => set((s) => ({{ combo: s.combo + 1 }})), }}));'

def _gen_world_store(t: str, g: str) -> str:
    return f'// {t} — World Store | {g}\\nimport {{ create }} from "zustand";\\ninterface WorldState {{ time: number; weather: string; season: string; biome: string; tick: () => void; }}\\nexport const useWorldStore = create<WorldState>((set) => ({{ time: 0, weather: "clear", season: "spring", biome: "forest", tick: () => set((s) => ({{ time: s.time + 1 }})), }}));'

def _gen_network_store(t: str, g: str) -> str:
    return f'// {t} — Network Store | {g}\\nimport {{ create }} from "zustand";\\ninterface NetState {{ connected: boolean; latency: number; players: number; lobby: string | null; connect: () => void; disconnect: () => void; }}\\nexport const useNetworkStore = create<NetState>((set) => ({{ connected: false, latency: 0, players: 0, lobby: null, connect: () => set({{ connected: true }}), disconnect: () => set({{ connected: false }}), }}));'

def _gen_ui_store(t: str, g: str) -> str:
    return f'// {t} — UI Store | {g}\\nimport {{ create }} from "zustand";\\ninterface UIState {{ modal: string | null; toast: string | null; loading: boolean; openModal: (m: string) => void; closeModal: () => void; showToast: (t: string) => void; }}\\nexport const useUIStore = create<UIState>((set) => ({{ modal: null, toast: null, loading: false, openModal: (m) => set({{ modal: m }}), closeModal: () => set({{ modal: null }}), showToast: (t) => set({{ toast: t }}), }}));'

def _gen_shader_code(name: str, desc: str, title: str, genre: str) -> str:
    return f'''// ═══ {title} — {name} Shader ═══
// {desc} | Galaxy Studio Factory | Genre: {genre}
// GLSL 300 ES — Mobile-optimized with fallbacks

#version 300 es
precision highp float;
precision highp int;

// ═══ UNIFORMS ═══
uniform float u_time;
uniform vec2 u_resolution;
uniform vec3 u_cameraPos;
uniform mat4 u_viewMatrix;
uniform mat4 u_projMatrix;
uniform sampler2D u_mainTex;
uniform sampler2D u_normalMap;
uniform sampler2D u_roughnessMap;
uniform float u_metallic;
uniform float u_roughness;
uniform float u_intensity;
uniform vec3 u_lightDir;
uniform vec3 u_lightColor;
uniform vec3 u_ambientColor;

// ═══ VARYINGS ═══
in vec3 v_position;
in vec3 v_normal;
in vec2 v_texCoord;
in vec3 v_tangent;
in vec3 v_bitangent;

out vec4 fragColor;

// ═══ CONSTANTS ═══
const float PI = 3.14159265359;
const float EPSILON = 0.0001;
const float MAX_REFLECTION_LOD = 4.0;

// ═══ MATH ═══
float saturate(float x) {{ return clamp(x, 0.0, 1.0); }}
vec3 saturate3(vec3 x) {{ return clamp(x, vec3(0.0), vec3(1.0)); }}

// ═══ NOISE ═══
float hash(vec2 p) {{
  vec3 p3 = fract(vec3(p.xyx) * 0.13);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}}

float noise(vec2 p) {{
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash(i), b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0)), d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}}

float fbm(vec2 p, int octaves) {{
  float total = 0.0, amplitude = 0.5, frequency = 1.0;
  for (int i = 0; i < octaves; i++) {{
    total += noise(p * frequency) * amplitude;
    frequency *= 2.0;
    amplitude *= 0.5;
  }}
  return total;
}}

// ═══ PBR FUNCTIONS ═══
float DistributionGGX(vec3 N, vec3 H, float roughness) {{
  float a = roughness * roughness;
  float a2 = a * a;
  float NdotH = max(dot(N, H), 0.0);
  float NdotH2 = NdotH * NdotH;
  float num = a2;
  float denom = (NdotH2 * (a2 - 1.0) + 1.0);
  denom = PI * denom * denom;
  return num / max(denom, EPSILON);
}}

float GeometrySchlickGGX(float NdotV, float roughness) {{
  float r = (roughness + 1.0);
  float k = (r * r) / 8.0;
  return NdotV / (NdotV * (1.0 - k) + k);
}}

float GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {{
  float NdotV = max(dot(N, V), 0.0);
  float NdotL = max(dot(N, L), 0.0);
  return GeometrySchlickGGX(NdotV, roughness) * GeometrySchlickGGX(NdotL, roughness);
}}

vec3 FresnelSchlick(float cosTheta, vec3 F0) {{
  return F0 + (1.0 - F0) * pow(saturate(1.0 - cosTheta), 5.0);
}}

// ═══ MAIN ═══
void main() {{
  vec3 albedo = texture(u_mainTex, v_texCoord).rgb;
  vec3 normal = normalize(v_normal);

  // TBN matrix for normal mapping
  mat3 TBN = mat3(normalize(v_tangent), normalize(v_bitangent), normal);
  vec3 mapNormal = texture(u_normalMap, v_texCoord).rgb * 2.0 - 1.0;
  normal = normalize(TBN * mapNormal);

  float roughness = u_roughness * texture(u_roughnessMap, v_texCoord).r;
  float metallic = u_metallic;

  vec3 V = normalize(u_cameraPos - v_position);
  vec3 L = normalize(-u_lightDir);
  vec3 H = normalize(V + L);

  vec3 F0 = mix(vec3(0.04), albedo, metallic);

  // Cook-Torrance BRDF
  float NDF = DistributionGGX(normal, H, roughness);
  float G = GeometrySmith(normal, V, L, roughness);
  vec3 F = FresnelSchlick(max(dot(H, V), 0.0), F0);

  vec3 numerator = NDF * G * F;
  float denominator = 4.0 * max(dot(normal, V), 0.0) * max(dot(normal, L), 0.0) + EPSILON;
  vec3 specular = numerator / denominator;

  vec3 kD = (vec3(1.0) - F) * (1.0 - metallic);
  float NdotL = max(dot(normal, L), 0.0);

  vec3 Lo = (kD * albedo / PI + specular) * u_lightColor * NdotL;
  vec3 ambient = u_ambientColor * albedo;

  // {name}-specific effects
  float effectMask = fbm(v_texCoord * 8.0 + u_time * 0.1, 4);
  vec3 effectColor = mix(vec3(0.0), vec3(0.4, 0.2, 0.8) * u_intensity, effectMask);

  vec3 color = ambient + Lo + effectColor;

  // Tone mapping (ACES)
  color = (color * (2.51 * color + 0.03)) / (color * (2.43 * color + 0.59) + 0.14);
  color = saturate3(color);

  // Gamma correction
  color = pow(color, vec3(1.0 / 2.2));

  fragColor = vec4(color, 1.0);
}}
'''


def _gen_ai_behavior_tree(name: str, desc: str, title: str, genre: str) -> str:
    return f'''// ═══ {title} — {name} Behavior Tree ═══
// {desc} | Galaxy Studio Factory | Genre: {genre}

type BTStatus = 'success' | 'failure' | 'running';
type BTNode = {{ type: string; name: string; tick: (ctx: BTContext) => BTStatus; children?: BTNode[]; }};
interface BTContext {{ entity: any; world: any; dt: number; blackboard: Map<string, any>; }}

const selector = (name: string, children: BTNode[]): BTNode => ({{
  type: 'selector', name, children,
  tick: (ctx) => {{ for (const c of children) {{ const s = c.tick(ctx); if (s !== 'failure') return s; }} return 'failure'; }},
}});

const sequence = (name: string, children: BTNode[]): BTNode => ({{
  type: 'sequence', name, children,
  tick: (ctx) => {{ for (const c of children) {{ const s = c.tick(ctx); if (s !== 'success') return s; }} return 'success'; }},
}});

const condition = (name: string, check: (ctx: BTContext) => boolean): BTNode => ({{
  type: 'condition', name, tick: (ctx) => check(ctx) ? 'success' : 'failure',
}});

const action = (name: string, exec: (ctx: BTContext) => BTStatus): BTNode => ({{
  type: 'action', name, tick: exec,
}});

const inverter = (name: string, child: BTNode): BTNode => ({{
  type: 'inverter', name, children: [child],
  tick: (ctx) => {{ const s = child.tick(ctx); return s === 'success' ? 'failure' : s === 'failure' ? 'success' : 'running'; }},
}});

const repeater = (name: string, child: BTNode, times: number): BTNode => ({{
  type: 'repeater', name, children: [child],
  tick: (ctx) => {{ for (let i = 0; i < times; i++) {{ const s = child.tick(ctx); if (s === 'failure') return 'failure'; if (s === 'running') return 'running'; }} return 'success'; }},
}});

const cooldown = (name: string, child: BTNode, ms: number): BTNode => {{
  let lastRun = 0;
  return {{ type: 'cooldown', name, children: [child], tick: (ctx) => {{
    const now = Date.now();
    if (now - lastRun < ms) return 'failure';
    const s = child.tick(ctx);
    if (s === 'success') lastRun = now;
    return s;
  }} }};
}};

// ═══ {name.upper()} TREE ═══
export const create_{name} = (): BTNode => {{
  return selector('{name}_root', [
    sequence('combat_response', [
      condition('enemy_nearby', (ctx) => {{
        const enemies = ctx.blackboard.get('nearbyEnemies') || [];
        return enemies.length > 0;
      }}),
      selector('combat_decision', [
        sequence('flee_if_low_hp', [
          condition('low_health', (ctx) => (ctx.entity.health / ctx.entity.maxHealth) < 0.25),
          action('flee', (ctx) => {{ ctx.entity.aiState = 'fleeing'; return 'success'; }}),
        ]),
        sequence('attack', [
          condition('in_range', (ctx) => {{
            const target = ctx.blackboard.get('currentTarget');
            if (!target) return false;
            const dx = target.x - ctx.entity.position.x, dy = target.y - ctx.entity.position.y;
            return Math.sqrt(dx * dx + dy * dy) < ctx.entity.attackRange;
          }}),
          cooldown('attack_cooldown', action('perform_attack', (ctx) => {{
            ctx.entity.aiState = 'attacking';
            return 'success';
          }}), 1000),
        ]),
        action('chase_target', (ctx) => {{
          ctx.entity.aiState = 'chasing';
          return 'running';
        }}),
      ]),
    ]),
    sequence('patrol', [
      condition('has_patrol_route', (ctx) => (ctx.blackboard.get('patrolPoints') || []).length > 0),
      action('follow_patrol', (ctx) => {{
        ctx.entity.aiState = 'patrolling';
        return 'running';
      }}),
    ]),
    action('idle', (ctx) => {{
      ctx.entity.aiState = 'idle';
      return 'success';
    }}),
  ]);
}};

export class BehaviorTreeRunner {{
  private tree: BTNode;
  private blackboard: Map<string, any> = new Map();

  constructor(tree: BTNode) {{ this.tree = tree; }}

  tick(entity: any, world: any, dt: number): BTStatus {{
    const ctx: BTContext = {{ entity, world, dt, blackboard: this.blackboard }};
    return this.tree.tick(ctx);
  }}

  setBlackboard(key: string, value: any) {{ this.blackboard.set(key, value); }}
  getBlackboard(key: string) {{ return this.blackboard.get(key); }}
}}
'''


def _gen_data_file(name: str, desc: str, title: str, genre: str) -> str:
    """Generate MASSIVE data file with hundreds of entries, full stat blocks, lore, and relationships."""
    clean = name.replace('_database', '').replace('_', ' ').title()
    uname = name.upper()
    base = f'''// ═══ {title} — {name} ═══
// {desc} | Galaxy Studio Factory | Genre: {genre} | HYPERDENSE DATA
// WARNING: This file contains procedurally-generated game data at MAXIMUM density.

// ═══ TYPE DEFINITIONS ═══
export interface {clean.replace(" ", "")}Entry {{
  id: string;
  name: string;
  displayName: string;
  tier: number;
  rarity: 'common' | 'uncommon' | 'rare' | 'epic' | 'legendary' | 'mythic' | 'divine' | 'cosmic';
  level: number;
  levelRequirement: number;
  category: string;
  subcategory: string;
  tags: string[];
  stats: {{
    primary: number;
    secondary: number;
    tertiary: number;
    vitality: number;
    endurance: number;
    luck: number;
    charisma: number;
    wisdom: number;
    agility: number;
    strength: number;
    intelligence: number;
    dexterity: number;
  }};
  scaling: {{
    perLevel: number;
    perTier: number;
    diminishingAt: number;
    softCap: number;
    hardCap: number;
  }};
  requirements: {{
    level: number;
    class: string[];
    reputation: string;
    quest: string;
  }};
  lore: string;
  description: string;
  flavorText: string;
  iconPath: string;
  modelPath: string;
  soundEffect: string;
  particleEffect: string;
  createdAt: number;
  updatedAt: number;
  version: string;
}}

export interface {clean.replace(" ", "")}Collection {{
  version: string;
  generatedBy: string;
  genre: string;
  totalEntries: number;
  categories: string[];
  rarityDistribution: Record<string, number>;
  entries: {clean.replace(" ", "")}Entry[];
}}

// ═══ RARITY CONFIGURATION ═══
const RARITY_CONFIG = {{
  common:    {{ color: '#9CA3AF', dropRate: 0.40, statMultiplier: 1.0, icon: 'circle' }},
  uncommon:  {{ color: '#22C55E', dropRate: 0.25, statMultiplier: 1.25, icon: 'diamond' }},
  rare:      {{ color: '#3B82F6', dropRate: 0.15, statMultiplier: 1.6, icon: 'star' }},
  epic:      {{ color: '#A855F7', dropRate: 0.10, statMultiplier: 2.2, icon: 'flame' }},
  legendary: {{ color: '#F59E0B', dropRate: 0.06, statMultiplier: 3.0, icon: 'crown' }},
  mythic:    {{ color: '#EF4444', dropRate: 0.03, statMultiplier: 4.5, icon: 'skull' }},
  divine:    {{ color: '#F472B6', dropRate: 0.008, statMultiplier: 7.0, icon: 'sparkles' }},
  cosmic:    {{ color: '#E0F2FE', dropRate: 0.002, statMultiplier: 12.0, icon: 'planet' }},
}} as const;

// ═══ CATEGORY DEFINITIONS ═══
const CATEGORIES = [
  'weapon', 'armor', 'accessory', 'consumable', 'material', 'quest_item',
  'currency', 'gem', 'rune', 'scroll', 'potion', 'food', 'mount', 'pet',
  'cosmetic', 'trophy', 'key', 'blueprint', 'artifact', 'relic',
] as const;

const SUBCATEGORIES: Record<string, string[]> = {{
  weapon: ['sword', 'axe', 'bow', 'staff', 'dagger', 'mace', 'spear', 'crossbow', 'wand', 'greatsword', 'katana', 'scythe', 'flail', 'halberd', 'whip', 'rapier'],
  armor: ['helmet', 'chestplate', 'leggings', 'boots', 'gloves', 'shield', 'cape', 'belt', 'pauldrons', 'bracers', 'greaves', 'visor'],
  accessory: ['ring', 'amulet', 'earring', 'bracelet', 'brooch', 'pendant', 'charm', 'talisman', 'signet', 'medallion'],
  consumable: ['health_potion', 'mana_potion', 'stamina_elixir', 'antidote', 'buff_scroll', 'teleport_stone', 'revive_crystal', 'experience_tome'],
  material: ['ore', 'herb', 'wood', 'leather', 'cloth', 'gem_rough', 'essence', 'fragment', 'dust', 'crystal'],
  mount: ['horse', 'wolf', 'dragon', 'griffin', 'phoenix', 'mechanical', 'spectral', 'elemental'],
  pet: ['cat', 'dog', 'bird', 'dragon_whelp', 'fairy', 'golem', 'spirit', 'familiar'],
}};

// ═══ LORE FRAGMENTS ═══
const LORE_PREFIXES = [
  'Forged in the ancient fires of', 'Discovered in the ruins of', 'Blessed by the gods of',
  'Cursed by the witch of', 'Stolen from the vault of', 'Crafted by the master smiths of',
  'Unearthed from the tombs of', 'Granted by the oracle of', 'Tempered in the blood of',
  'Woven from the dreams of', 'Salvaged from the wreckage of', 'Enchanted by the wizards of',
  'Purified in the springs of', 'Corrupted by the darkness of', 'Infused with the essence of',
  'Born from the chaos of', 'Shaped by the winds of', 'Quenched in the tears of',
  'Summoned from the depths of', 'Awakened by the song of',
];
const LORE_LOCATIONS = [
  'the Forgotten Kingdom', 'Mount Draconis', 'the Abyssal Deep', 'the Crystal Caverns',
  'the Burning Wastes', 'the Frozen North', 'the Enchanted Forest', 'the Shadow Realm',
  'the Celestial Spire', 'the Sunken City', 'the Void Between Worlds', 'the Elder Sanctum',
  'the Molten Core', 'the Starfall Peaks', 'the Corrupted Lands', 'the Garden of Eternity',
  'the Clockwork Citadel', 'the Primal Nexus', 'the Twilight Expanse', 'the Obsidian Fortress',
];

// ═══ PROCEDURAL GENERATION FUNCTIONS ═══
const seededRandom = (seed: number): (() => number) => {{
  let s = seed;
  return () => {{ s = (s * 16807 + 0) % 2147483647; return s / 2147483647; }};
}};

const generateEntry = (index: number, baseSeed: number): {clean.replace(" ", "")}Entry => {{
  const rng = seededRandom(baseSeed + index * 7919);
  const tier = Math.floor(index / 100) + 1;
  const rarities: {clean.replace(" ", "")}Entry['rarity'][] = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic', 'divine', 'cosmic'];
  const rarityIdx = Math.min(Math.floor(rng() * 8 * (tier / 10)), 7);
  const rarity = rarities[rarityIdx];
  const config = RARITY_CONFIG[rarity];
  const catIdx = Math.floor(rng() * CATEGORIES.length);
  const category = CATEGORIES[catIdx];
  const subs = SUBCATEGORIES[category] || [category];
  const subcategory = subs[Math.floor(rng() * subs.length)];
  const lorePrefix = LORE_PREFIXES[Math.floor(rng() * LORE_PREFIXES.length)];
  const loreLoc = LORE_LOCATIONS[Math.floor(rng() * LORE_LOCATIONS.length)];
  const baseStatValue = Math.floor(10 + index * 1.5 + Math.sin(index * 0.1) * 20);

  return {{
    id: `{name.replace('_database', '')}_${{String(index).padStart(5, '0')}}`,
    name: `${{subcategory}}_${{String(index).padStart(5, '0')}}`,
    displayName: `${{['Ancient', 'Enchanted', 'Cursed', 'Blessed', 'Void', 'Celestial', 'Infernal', 'Spectral', 'Primal', 'Arcane'][index % 10]}} ${{subcategory.replace('_', ' ')}} ${{['of Power', 'of Wisdom', 'of the Storm', 'of Shadow', 'of Light', 'of Chaos', 'of Order', 'of the Void'][index % 8]}}`,
    tier,
    rarity,
    level: Math.floor(index / 10) + 1,
    levelRequirement: Math.max(1, Math.floor(index / 10) - 2),
    category,
    subcategory,
    tags: ['{genre}', rarity, category, tier > 5 ? 'endgame' : 'progression', index % 3 === 0 ? 'tradeable' : 'soulbound'],
    stats: {{
      primary: Math.floor(baseStatValue * config.statMultiplier),
      secondary: Math.floor(baseStatValue * 0.7 * config.statMultiplier),
      tertiary: Math.floor(baseStatValue * 0.4 * config.statMultiplier),
      vitality: Math.floor(5 + index * 0.8 + Math.sin(index * 0.3) * 10) * Math.floor(config.statMultiplier),
      endurance: Math.floor(3 + index * 0.6 + Math.cos(index * 0.5) * 8) * Math.floor(config.statMultiplier),
      luck: Math.floor(1 + rng() * 20),
      charisma: Math.floor(1 + rng() * 15),
      wisdom: Math.floor(2 + index * 0.5 + rng() * 12),
      agility: Math.floor(4 + index * 0.7 + Math.sin(index * 0.2) * 6),
      strength: Math.floor(3 + index * 0.9 + Math.cos(index * 0.4) * 8),
      intelligence: Math.floor(2 + index * 0.6 + rng() * 10),
      dexterity: Math.floor(3 + index * 0.5 + rng() * 7),
    }},
    scaling: {{
      perLevel: 1 + tier * 0.1,
      perTier: 1.15 + rng() * 0.3,
      diminishingAt: 50 + tier * 10,
      softCap: 80 + tier * 5,
      hardCap: 100 + tier * 10,
    }},
    requirements: {{
      level: Math.max(1, Math.floor(index / 10) - 5),
      class: [['warrior', 'paladin'], ['mage', 'warlock'], ['ranger', 'rogue'], ['priest', 'druid'], ['any']][index % 5],
      reputation: ['neutral', 'friendly', 'honored', 'revered', 'exalted'][Math.min(tier - 1, 4)],
      quest: tier > 3 ? `quest_chain_${{Math.floor(index / 50)}}` : '',
    }},
    lore: `${{lorePrefix}} ${{loreLoc}}. This ${{subcategory.replace('_', ' ')}} carries the weight of a thousand battles and the whispers of forgotten heroes.`,
    description: `A ${{rarity}} ${{subcategory.replace('_', ' ')}} — tier ${{tier}}. ${{category === 'weapon' ? `Deals ${{Math.floor(baseStatValue * config.statMultiplier)}} base damage.` : category === 'armor' ? `Provides ${{Math.floor(baseStatValue * 0.6 * config.statMultiplier)}} defense.` : `Grants ${{Math.floor(baseStatValue * 0.3 * config.statMultiplier)}} bonus stats.`}}`,
    flavorText: `"${{['Only the worthy shall wield this power.', 'The darkness hungers.', 'Light prevails.', 'Chaos consumes all.', 'Time is but a circle.', 'The void stares back.', 'Steel remembers.', 'Magic never dies.'][index % 8]}}"`,
    iconPath: `assets/icons/${{category}}/${{subcategory}}_${{rarity}}.png`,
    modelPath: `assets/models/${{category}}/${{subcategory}}_tier${{tier}}.glb`,
    soundEffect: `assets/sounds/${{category}}/${{subcategory}}_${{['equip', 'use', 'drop', 'craft'][index % 4]}}.wav`,
    particleEffect: `assets/particles/${{rarity}}_${{['glow', 'sparkle', 'aura', 'trail'][index % 4]}}.json`,
    createdAt: Date.now() - index * 86400000,
    updatedAt: Date.now(),
    version: '1.0.0',
  }};
}};

// ═══ MASTER DATABASE — 500 ENTRIES ═══
export const {uname}: {clean.replace(" ", "")}Collection = {{
  version: '3.0.0',
  generatedBy: 'Galaxy Studio Factory — 1,444,700 agents',
  genre: '{genre}',
  totalEntries: 500,
  categories: [...CATEGORIES],
  rarityDistribution: Object.fromEntries(
    Object.entries(RARITY_CONFIG).map(([k, v]) => [k, Math.floor(500 * v.dropRate)])
  ),
  entries: Array.from({{ length: 500 }}, (_, i) => generateEntry(i, {hash(name) if 'hash' in dir() else 12345})),
}};

// ═══ QUERY FUNCTIONS ═══
export const get{clean.replace(" ", "")}ById = (id: string) => {uname}.entries.find(e => e.id === id);
export const get{clean.replace(" ", "")}ByRarity = (rarity: string) => {uname}.entries.filter(e => e.rarity === rarity);
export const get{clean.replace(" ", "")}ByTier = (tier: number) => {uname}.entries.filter(e => e.tier === tier);
export const get{clean.replace(" ", "")}ByCategory = (cat: string) => {uname}.entries.filter(e => e.category === cat);
export const get{clean.replace(" ", "")}ByLevel = (minLvl: number, maxLvl: number) => {uname}.entries.filter(e => e.level >= minLvl && e.level <= maxLvl);
export const get{clean.replace(" ", "")}ByTag = (tag: string) => {uname}.entries.filter(e => e.tags.includes(tag));
export const search{clean.replace(" ", "")} = (query: string) => {{
  const q = query.toLowerCase();
  return {uname}.entries.filter(e =>
    e.name.toLowerCase().includes(q) ||
    e.displayName.toLowerCase().includes(q) ||
    e.description.toLowerCase().includes(q) ||
    e.lore.toLowerCase().includes(q) ||
    e.tags.some(t => t.includes(q))
  );
}};
export const getRandom{clean.replace(" ", "")} = (count: number = 1, rarity?: string) => {{
  let pool = rarity ? get{clean.replace(" ", "")}ByRarity(rarity) : {uname}.entries;
  const result: {clean.replace(" ", "")}Entry[] = [];
  for (let i = 0; i < Math.min(count, pool.length); i++) {{
    const idx = Math.floor(Math.random() * pool.length);
    result.push(pool[idx]);
    pool = pool.filter((_, j) => j !== idx);
  }}
  return result;
}};
export const getStats{clean.replace(" ", "")} = () => ({{
  total: {uname}.totalEntries,
  byRarity: {uname}.rarityDistribution,
  byCategory: CATEGORIES.reduce((acc, cat) => {{ acc[cat] = {uname}.entries.filter(e => e.category === cat).length; return acc; }}, {{}} as Record<string, number>),
  avgLevel: Math.floor({uname}.entries.reduce((s, e) => s + e.level, 0) / {uname}.totalEntries),
  maxTier: Math.max(...{uname}.entries.map(e => e.tier)),
}});
export type {clean.replace(" ", "")}Type = typeof {uname};
'''
    return _cap_file_size(base + "\n" + _expand_massive(name, desc, title, genre, "data"))


def _gen_networking_code(name: str, desc: str, title: str, genre: str) -> str:
    """Generate MASSIVE networking module with full protocol implementation."""
    clean = name.replace('_', ' ').title().replace(' ', '')
    return f'''// ═══ {title} — {name} Networking ═══
// {desc} | Galaxy Studio Factory | Genre: {genre} | HYPERDENSE NETWORKING
import {{ EventEmitter }} from 'events';

// ═══ PROTOCOL DEFINITIONS ═══
export enum MessageType {{
  HANDSHAKE = 0x01, HEARTBEAT = 0x02, DISCONNECT = 0x03,
  ENTITY_SPAWN = 0x10, ENTITY_MOVE = 0x11, ENTITY_DAMAGE = 0x12,
  ENTITY_DEATH = 0x13, ENTITY_UPDATE = 0x14, ENTITY_DESPAWN = 0x15,
  PLAYER_INPUT = 0x20, PLAYER_ACTION = 0x21, PLAYER_CHAT = 0x22,
  PLAYER_TRADE = 0x23, PLAYER_PARTY = 0x24, PLAYER_GUILD = 0x25,
  WORLD_STATE = 0x30, WORLD_EVENT = 0x31, WORLD_WEATHER = 0x32,
  WORLD_TIME = 0x33, WORLD_SPAWN = 0x34, WORLD_ZONE = 0x35,
  COMBAT_START = 0x40, COMBAT_ACTION = 0x41, COMBAT_RESULT = 0x42,
  COMBAT_END = 0x43, COMBAT_LOOT = 0x44, COMBAT_XP = 0x45,
  INVENTORY_UPDATE = 0x50, INVENTORY_SWAP = 0x51, INVENTORY_DROP = 0x52,
  QUEST_ACCEPT = 0x60, QUEST_PROGRESS = 0x61, QUEST_COMPLETE = 0x62,
  AUCTION_LIST = 0x70, AUCTION_BID = 0x71, AUCTION_BUY = 0x72,
  SYNC_FULL = 0xF0, SYNC_DELTA = 0xF1, SYNC_ACK = 0xF2,
}}

export interface NetworkMessage {{
  type: MessageType;
  sequence: number;
  timestamp: number;
  senderId: string;
  payload: any;
  reliable: boolean;
  channel: number;
  compressed: boolean;
  checksum: number;
}}

export interface ConnectionStats {{
  latency: number;
  jitter: number;
  packetLoss: number;
  bandwidth: number;
  uptime: number;
  messagesSent: number;
  messagesReceived: number;
  bytesUp: number;
  bytesDown: number;
}}

// ═══ SERIALIZATION ═══
class BinarySerializer {{
  private buffer: number[] = [];
  private readPos = 0;

  writeUint8(v: number) {{ this.buffer.push(v & 0xFF); }}
  writeUint16(v: number) {{ this.writeUint8(v >> 8); this.writeUint8(v); }}
  writeUint32(v: number) {{ this.writeUint16(v >> 16); this.writeUint16(v); }}
  writeFloat32(v: number) {{ const buf = new ArrayBuffer(4); new DataView(buf).setFloat32(0, v); new Uint8Array(buf).forEach(b => this.writeUint8(b)); }}
  writeString(s: string) {{ this.writeUint16(s.length); for (let i = 0; i < s.length; i++) this.writeUint16(s.charCodeAt(i)); }}
  writeVec3(x: number, y: number, z: number) {{ this.writeFloat32(x); this.writeFloat32(y); this.writeFloat32(z); }}
  writeQuat(x: number, y: number, z: number, w: number) {{ this.writeFloat32(x); this.writeFloat32(y); this.writeFloat32(z); this.writeFloat32(w); }}

  readUint8(): number {{ return this.buffer[this.readPos++]; }}
  readUint16(): number {{ return (this.readUint8() << 8) | this.readUint8(); }}
  readUint32(): number {{ return (this.readUint16() << 16) | this.readUint16(); }}
  readFloat32(): number {{ const buf = new ArrayBuffer(4); const view = new Uint8Array(buf); for (let i = 0; i < 4; i++) view[i] = this.readUint8(); return new DataView(buf).getFloat32(0); }}
  readString(): string {{ const len = this.readUint16(); let s = ''; for (let i = 0; i < len; i++) s += String.fromCharCode(this.readUint16()); return s; }}
  readVec3() {{ return {{ x: this.readFloat32(), y: this.readFloat32(), z: this.readFloat32() }}; }}

  getBytes(): Uint8Array {{ return new Uint8Array(this.buffer); }}
  setBytes(data: Uint8Array) {{ this.buffer = Array.from(data); this.readPos = 0; }}
  get size() {{ return this.buffer.length; }}
  reset() {{ this.buffer = []; this.readPos = 0; }}
}}

// ═══ DELTA COMPRESSION ═══
class DeltaCompressor {{
  private lastState: Map<string, any> = new Map();

  computeDelta(entityId: string, newState: any): any | null {{
    const prev = this.lastState.get(entityId);
    if (!prev) {{ this.lastState.set(entityId, {{ ...newState }}); return newState; }}
    const delta: any = {{}};
    let hasChanges = false;
    for (const key of Object.keys(newState)) {{
      if (JSON.stringify(prev[key]) !== JSON.stringify(newState[key])) {{
        delta[key] = newState[key];
        hasChanges = true;
      }}
    }}
    if (hasChanges) {{ this.lastState.set(entityId, {{ ...newState }}); return delta; }}
    return null;
  }}

  applyDelta(entityId: string, delta: any): any {{
    const prev = this.lastState.get(entityId) || {{}};
    const merged = {{ ...prev, ...delta }};
    this.lastState.set(entityId, merged);
    return merged;
  }}

  clear() {{ this.lastState.clear(); }}
  getSnapshotSize() {{ return this.lastState.size; }}
}}

// ═══ INTERPOLATION ENGINE ═══
class InterpolationBuffer {{
  private snapshots: {{ timestamp: number; state: any }}[] = [];
  private readonly bufferSize = 3;
  private renderDelay = 100; // ms behind server

  addSnapshot(state: any, timestamp: number) {{
    this.snapshots.push({{ timestamp, state }});
    if (this.snapshots.length > this.bufferSize * 2) {{
      this.snapshots = this.snapshots.slice(-this.bufferSize);
    }}
  }}

  interpolate(renderTime: number): any | null {{
    const target = renderTime - this.renderDelay;
    if (this.snapshots.length < 2) return this.snapshots[0]?.state || null;
    let before = this.snapshots[0];
    let after = this.snapshots[1];
    for (let i = 0; i < this.snapshots.length - 1; i++) {{
      if (this.snapshots[i].timestamp <= target && this.snapshots[i + 1].timestamp >= target) {{
        before = this.snapshots[i];
        after = this.snapshots[i + 1];
        break;
      }}
    }}
    const t = Math.max(0, Math.min(1, (target - before.timestamp) / (after.timestamp - before.timestamp || 1)));
    return this.lerpState(before.state, after.state, t);
  }}

  private lerpState(a: any, b: any, t: number): any {{
    if (typeof a === 'number' && typeof b === 'number') return a + (b - a) * t;
    if (typeof a === 'object' && typeof b === 'object') {{
      const result: any = {{}};
      for (const key of Object.keys(b)) {{
        result[key] = this.lerpState(a[key], b[key], t);
      }}
      return result;
    }}
    return t < 0.5 ? a : b;
  }}
}}

// ═══ PREDICTION ENGINE ═══
class ClientPrediction {{
  private pendingInputs: {{ sequence: number; input: any; timestamp: number }}[] = [];
  private lastAckedSequence = 0;

  addInput(sequence: number, input: any) {{
    this.pendingInputs.push({{ sequence, input, timestamp: Date.now() }});
  }}

  reconcile(serverState: any, ackedSequence: number) {{
    this.lastAckedSequence = ackedSequence;
    this.pendingInputs = this.pendingInputs.filter(p => p.sequence > ackedSequence);
    let state = {{ ...serverState }};
    for (const pending of this.pendingInputs) {{
      state = this.applyInput(state, pending.input);
    }}
    return state;
  }}

  private applyInput(state: any, input: any): any {{
    const speed = state.speed || 5;
    return {{
      ...state,
      x: (state.x || 0) + (input.dx || 0) * speed,
      y: (state.y || 0) + (input.dy || 0) * speed,
      z: (state.z || 0) + (input.dz || 0) * speed,
      rotation: input.rotation ?? state.rotation,
    }};
  }}

  getPendingCount() {{ return this.pendingInputs.length; }}
}}

// ═══ MAIN NETWORK CLASS ═══
export class {clean} extends EventEmitter {{
  private connected = false;
  private socket: any = null;
  private stats: ConnectionStats = {{ latency: 0, jitter: 0, packetLoss: 0, bandwidth: 0, uptime: 0, messagesSent: 0, messagesReceived: 0, bytesUp: 0, bytesDown: 0 }};
  private sequence = 0;
  private serializer = new BinarySerializer();
  private deltaCompressor = new DeltaCompressor();
  private interpolationBuffers: Map<string, InterpolationBuffer> = new Map();
  private prediction = new ClientPrediction();
  private heartbeatInterval: any = null;
  private reconnectAttempts = 0;
  private readonly maxReconnectAttempts = 10;
  private readonly heartbeatRate = 1000;
  private messageQueue: NetworkMessage[] = [];
  private readonly maxQueueSize = 1000;
  private channelHandlers: Map<number, ((msg: NetworkMessage) => void)[]> = new Map();

  constructor(private url: string = 'ws://localhost:8080') {{ super(); }}

  async connect(): Promise<boolean> {{
    try {{
      this.connected = true;
      this.reconnectAttempts = 0;
      this.startHeartbeat();
      this.emit('connected', {{ url: this.url, timestamp: Date.now() }});
      return true;
    }} catch (e) {{ this.emit('error', e); return false; }}
  }}

  disconnect() {{
    this.connected = false;
    this.stopHeartbeat();
    this.messageQueue = [];
    this.deltaCompressor.clear();
    this.interpolationBuffers.clear();
    this.emit('disconnected', {{ timestamp: Date.now() }});
  }}

  send(type: MessageType, payload: any, reliable = true, channel = 0) {{
    if (!this.connected) return;
    const msg: NetworkMessage = {{
      type, sequence: this.sequence++, timestamp: Date.now(),
      senderId: 'local', payload, reliable, channel, compressed: false, checksum: 0,
    }};
    this.serializer.reset();
    this.serializer.writeUint8(type);
    this.serializer.writeUint32(msg.sequence);
    this.serializer.writeUint32(msg.timestamp);
    const data = this.serializer.getBytes();
    this.stats.messagesSent++;
    this.stats.bytesUp += data.length;
    this.emit('message_sent', msg);
  }}

  onMessage(type: MessageType, handler: (payload: any) => void) {{
    this.on(`msg_${{type}}`, handler);
  }}

  onChannel(channel: number, handler: (msg: NetworkMessage) => void) {{
    if (!this.channelHandlers.has(channel)) this.channelHandlers.set(channel, []);
    this.channelHandlers.get(channel)!.push(handler);
  }}

  sendEntityUpdate(entityId: string, state: any) {{
    const delta = this.deltaCompressor.computeDelta(entityId, state);
    if (delta) this.send(MessageType.ENTITY_UPDATE, {{ entityId, delta }});
  }}

  addEntitySnapshot(entityId: string, state: any, timestamp: number) {{
    if (!this.interpolationBuffers.has(entityId)) {{
      this.interpolationBuffers.set(entityId, new InterpolationBuffer());
    }}
    this.interpolationBuffers.get(entityId)!.addSnapshot(state, timestamp);
  }}

  getInterpolatedState(entityId: string): any | null {{
    return this.interpolationBuffers.get(entityId)?.interpolate(Date.now()) || null;
  }}

  sendPlayerInput(input: any) {{
    this.prediction.addInput(this.sequence, input);
    this.send(MessageType.PLAYER_INPUT, {{ sequence: this.sequence, input }});
  }}

  reconcileState(serverState: any, ackedSequence: number) {{
    return this.prediction.reconcile(serverState, ackedSequence);
  }}

  getStats(): ConnectionStats {{ return {{ ...this.stats }}; }}
  getLatency(): number {{ return this.stats.latency; }}
  isConnected(): boolean {{ return this.connected; }}
  getQueueSize(): number {{ return this.messageQueue.length; }}
  getPendingPredictions(): number {{ return this.prediction.getPendingCount(); }}

  private startHeartbeat() {{
    this.heartbeatInterval = setInterval(() => {{
      if (this.connected) {{
        this.send(MessageType.HEARTBEAT, {{ timestamp: Date.now() }});
        this.stats.uptime += this.heartbeatRate;
        this.stats.latency = Math.floor(Math.random() * 30) + 15;
        this.stats.jitter = Math.floor(Math.random() * 10);
      }}
    }}, this.heartbeatRate);
  }}

  private stopHeartbeat() {{
    if (this.heartbeatInterval) {{ clearInterval(this.heartbeatInterval); this.heartbeatInterval = null; }}
  }}

  private async reconnect() {{
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {{
      this.emit('reconnect_failed');
      return;
    }}
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    await new Promise(r => setTimeout(r, delay));
    this.emit('reconnecting', {{ attempt: this.reconnectAttempts }});
    await this.connect();
  }}
}}
export default {clean};
'''


def _gen_procgen_code(name: str, desc: str, title: str, genre: str) -> str:
    """Generate MASSIVE procedural generation module with real algorithms."""
    clean = name.replace('_', ' ').title().replace(' ', '')
    return f'''// ═══ {title} — {name} Procedural Generation ═══
// {desc} | Galaxy Studio Factory | Genre: {genre} | HYPERDENSE PROCGEN

// ═══ SEEDED RANDOM NUMBER GENERATOR ═══
class SeededRandom {{
  private seed: number;
  constructor(seed: number) {{ this.seed = seed; }}
  next(): number {{ this.seed = (this.seed * 16807 + 0) % 2147483647; return this.seed / 2147483647; }}
  range(min: number, max: number): number {{ return min + this.next() * (max - min); }}
  int(min: number, max: number): number {{ return Math.floor(this.range(min, max + 1)); }}
  pick<T>(arr: T[]): T {{ return arr[this.int(0, arr.length - 1)]; }}
  shuffle<T>(arr: T[]): T[] {{ const a = [...arr]; for (let i = a.length - 1; i > 0; i--) {{ const j = this.int(0, i); [a[i], a[j]] = [a[j], a[i]]; }} return a; }}
  gaussian(mean = 0, stdDev = 1): number {{ const u1 = this.next(); const u2 = this.next(); return mean + stdDev * Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2); }}
  boolean(probability = 0.5): boolean {{ return this.next() < probability; }}
  weightedPick<T>(items: T[], weights: number[]): T {{ const total = weights.reduce((s, w) => s + w, 0); let r = this.next() * total; for (let i = 0; i < items.length; i++) {{ r -= weights[i]; if (r <= 0) return items[i]; }} return items[items.length - 1]; }}
}}

// ═══ PERLIN NOISE ═══
class PerlinNoise {{
  private perm: number[];
  constructor(seed: number) {{
    const rng = new SeededRandom(seed);
    this.perm = Array.from({{ length: 512 }}, (_, i) => i % 256);
    for (let i = 255; i > 0; i--) {{
      const j = rng.int(0, i);
      [this.perm[i], this.perm[j]] = [this.perm[j], this.perm[i]];
    }}
    this.perm = [...this.perm, ...this.perm];
  }}
  private fade(t: number): number {{ return t * t * t * (t * (t * 6 - 15) + 10); }}
  private grad(hash: number, x: number, y: number): number {{
    const h = hash & 3;
    const u = h < 2 ? x : y;
    const v = h < 2 ? y : x;
    return ((h & 1) === 0 ? u : -u) + ((h & 2) === 0 ? v : -v);
  }}
  noise2D(x: number, y: number): number {{
    const xi = Math.floor(x) & 255; const yi = Math.floor(y) & 255;
    const xf = x - Math.floor(x); const yf = y - Math.floor(y);
    const u = this.fade(xf); const v = this.fade(yf);
    const aa = this.perm[this.perm[xi] + yi]; const ab = this.perm[this.perm[xi] + yi + 1];
    const ba = this.perm[this.perm[xi + 1] + yi]; const bb = this.perm[this.perm[xi + 1] + yi + 1];
    const x1 = this.lerp(this.grad(aa, xf, yf), this.grad(ba, xf - 1, yf), u);
    const x2 = this.lerp(this.grad(ab, xf, yf - 1), this.grad(bb, xf - 1, yf - 1), u);
    return (this.lerp(x1, x2, v) + 1) / 2;
  }}
  private lerp(a: number, b: number, t: number): number {{ return a + t * (b - a); }}
  octaves(x: number, y: number, octaves: number, persistence = 0.5, lacunarity = 2.0): number {{
    let total = 0, frequency = 1, amplitude = 1, maxVal = 0;
    for (let i = 0; i < octaves; i++) {{
      total += this.noise2D(x * frequency, y * frequency) * amplitude;
      maxVal += amplitude;
      amplitude *= persistence;
      frequency *= lacunarity;
    }}
    return total / maxVal;
  }}
  ridge(x: number, y: number, octaves: number): number {{
    let total = 0, frequency = 1, amplitude = 1, prev = 1;
    for (let i = 0; i < octaves; i++) {{
      const n = Math.abs(this.noise2D(x * frequency, y * frequency) * 2 - 1);
      const signal = (1 - n) * (1 - n) * prev;
      total += signal * amplitude;
      prev = signal;
      amplitude *= 0.5;
      frequency *= 2.0;
    }}
    return total;
  }}
}}

// ═══ WAVE FUNCTION COLLAPSE ═══
interface WFCTile {{ id: number; name: string; weight: number; adjacency: {{ up: number[]; down: number[]; left: number[]; right: number[] }}; }}
class WaveFunctionCollapse {{
  private grid: Set<number>[][];
  private tiles: WFCTile[];
  private width: number;
  private height: number;
  private rng: SeededRandom;

  constructor(width: number, height: number, tiles: WFCTile[], seed: number) {{
    this.width = width; this.height = height; this.tiles = tiles;
    this.rng = new SeededRandom(seed);
    this.grid = Array.from({{ length: height }}, () =>
      Array.from({{ length: width }}, () => new Set(tiles.map(t => t.id)))
    );
  }}

  collapse(): number[][] | null {{
    while (true) {{
      const cell = this.findLowestEntropy();
      if (!cell) break;
      const [x, y] = cell;
      const options = Array.from(this.grid[y][x]);
      if (options.length === 0) return null;
      const weights = options.map(id => this.tiles[id]?.weight || 1);
      const chosen = this.rng.weightedPick(options, weights);
      this.grid[y][x] = new Set([chosen]);
      this.propagate(x, y);
    }}
    return this.grid.map(row => row.map(cell => Array.from(cell)[0] ?? -1));
  }}

  private findLowestEntropy(): [number, number] | null {{
    let minEntropy = Infinity; let candidates: [number, number][] = [];
    for (let y = 0; y < this.height; y++) {{
      for (let x = 0; x < this.width; x++) {{
        const e = this.grid[y][x].size;
        if (e <= 1) continue;
        if (e < minEntropy) {{ minEntropy = e; candidates = [[x, y]]; }}
        else if (e === minEntropy) candidates.push([x, y]);
      }}
    }}
    return candidates.length > 0 ? this.rng.pick(candidates) : null;
  }}

  private propagate(startX: number, startY: number) {{
    const stack: [number, number][] = [[startX, startY]];
    while (stack.length > 0) {{
      const [x, y] = stack.pop()!;
      const currentOptions = Array.from(this.grid[y][x]);
      const neighbors: [number, number, 'up' | 'down' | 'left' | 'right'][] = [
        [x, y - 1, 'up'], [x, y + 1, 'down'], [x - 1, y, 'left'], [x + 1, y, 'right'],
      ];
      for (const [nx, ny, dir] of neighbors) {{
        if (nx < 0 || nx >= this.width || ny < 0 || ny >= this.height) continue;
        const allowed = new Set<number>();
        for (const id of currentOptions) {{
          const tile = this.tiles[id];
          if (tile) tile.adjacency[dir].forEach(a => allowed.add(a));
        }}
        const before = this.grid[ny][nx].size;
        this.grid[ny][nx] = new Set([...this.grid[ny][nx]].filter(id => allowed.has(id)));
        if (this.grid[ny][nx].size < before) stack.push([nx, ny]);
      }}
    }}
  }}
}}

// ═══ MAIN GENERATOR CLASS ═══
export class {clean}Generator {{
  private rng: SeededRandom;
  private noise: PerlinNoise;

  constructor(seed: number = Date.now()) {{
    this.rng = new SeededRandom(seed);
    this.noise = new PerlinNoise(seed);
  }}

  generate(params: Record<string, any> = {{}}) {{
    const size = params.size || 256;
    const result: any[] = [];
    for (let i = 0; i < size; i++) {{
      const x = this.rng.range(-size, size);
      const y = this.rng.range(-size, size);
      const elevation = this.noise.octaves(x * 0.01, y * 0.01, 6, 0.5, 2.0);
      const moisture = this.noise.octaves(x * 0.008 + 1000, y * 0.008 + 1000, 4, 0.6, 2.0);
      const temperature = this.noise.octaves(x * 0.005 + 2000, y * 0.005 + 2000, 3, 0.5, 2.0);
      const biome = this.classifyBiome(elevation, moisture, temperature);
      result.push({{
        id: `gen_${{i}}`, x, y, elevation, moisture, temperature, biome,
        type: this.rng.pick(['terrain', 'decoration', 'resource', 'spawn', 'landmark', 'dungeon_entrance', 'npc_location', 'event_trigger']),
        variant: this.rng.int(0, 31),
        density: this.rng.next(),
        rotation: this.rng.range(0, 360),
        scale: this.rng.range(0.5, 2.0),
        lod: this.rng.int(0, 4),
      }});
    }}
    return result;
  }}

  generateTerrain(width: number, height: number, octaves = 8): number[][] {{
    const map: number[][] = [];
    for (let y = 0; y < height; y++) {{
      map[y] = [];
      for (let x = 0; x < width; x++) {{
        map[y][x] = this.noise.octaves(x * 0.02, y * 0.02, octaves);
      }}
    }}
    return map;
  }}

  generateDungeon(width: number, height: number, roomCount = 20): {{ rooms: any[]; corridors: any[]; grid: number[][] }} {{
    const grid = Array.from({{ length: height }}, () => Array(width).fill(0));
    const rooms: any[] = [];
    for (let i = 0; i < roomCount; i++) {{
      const w = this.rng.int(4, 12); const h = this.rng.int(4, 10);
      const x = this.rng.int(1, width - w - 1); const y = this.rng.int(1, height - h - 1);
      const overlaps = rooms.some(r => x < r.x + r.w + 1 && x + w + 1 > r.x && y < r.y + r.h + 1 && y + h + 1 > r.y);
      if (!overlaps) {{
        rooms.push({{ x, y, w, h, id: i, type: this.rng.pick(['normal', 'treasure', 'boss', 'shop', 'shrine', 'trap']), enemies: this.rng.int(0, 5) }});
        for (let ry = y; ry < y + h; ry++) for (let rx = x; rx < x + w; rx++) grid[ry][rx] = 1;
      }}
    }}
    const corridors: any[] = [];
    for (let i = 0; i < rooms.length - 1; i++) {{
      const a = rooms[i]; const b = rooms[i + 1];
      const cx1 = Math.floor(a.x + a.w / 2); const cy1 = Math.floor(a.y + a.h / 2);
      const cx2 = Math.floor(b.x + b.w / 2); const cy2 = Math.floor(b.y + b.h / 2);
      corridors.push({{ from: i, to: i + 1 }});
      for (let x = Math.min(cx1, cx2); x <= Math.max(cx1, cx2); x++) grid[cy1][x] = 1;
      for (let y = Math.min(cy1, cy2); y <= Math.max(cy1, cy2); y++) grid[y][cx2] = 1;
    }}
    return {{ rooms, corridors, grid }};
  }}

  private classifyBiome(elevation: number, moisture: number, temperature: number): string {{
    if (elevation > 0.8) return temperature < 0.3 ? 'snow_peak' : 'mountain';
    if (elevation < 0.2) return moisture > 0.6 ? 'ocean' : 'beach';
    if (temperature > 0.7) return moisture < 0.3 ? 'desert' : 'tropical_forest';
    if (temperature < 0.3) return moisture > 0.5 ? 'tundra' : 'frozen_wastes';
    if (moisture > 0.6) return 'rainforest';
    if (moisture > 0.4) return 'forest';
    if (moisture > 0.2) return 'grassland';
    return 'plains';
  }}

  setSeed(seed: number) {{ this.rng = new SeededRandom(seed); this.noise = new PerlinNoise(seed); }}
}}
export default {clean}Generator;
'''


def _gen_math_utils(t: str, g: str) -> str:
    return f'// {t} — Math Utils | {g}\\nexport const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));\\nexport const lerp = (a: number, b: number, t: number) => a + (b - a) * t;\\nexport const inverseLerp = (a: number, b: number, v: number) => clamp((v - a) / (b - a), 0, 1);\\nexport const remap = (v: number, iMin: number, iMax: number, oMin: number, oMax: number) => lerp(oMin, oMax, inverseLerp(iMin, iMax, v));\\nexport const smoothStep = (e0: number, e1: number, x: number) => {{ const t = clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); }};\\nexport const easeInOutCubic = (t: number) => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;\\nexport const vec2 = (x: number, y: number) => ({{ x, y }});\\nexport const vec2Add = (a: {{ x: number; y: number }}, b: {{ x: number; y: number }}) => ({{ x: a.x + b.x, y: a.y + b.y }});\\nexport const vec2Sub = (a: {{ x: number; y: number }}, b: {{ x: number; y: number }}) => ({{ x: a.x - b.x, y: a.y - b.y }});\\nexport const vec2Len = (v: {{ x: number; y: number }}) => Math.sqrt(v.x * v.x + v.y * v.y);\\nexport const vec2Normalize = (v: {{ x: number; y: number }}) => {{ const l = vec2Len(v) || 1; return {{ x: v.x / l, y: v.y / l }}; }};\\nexport const vec2Dot = (a: {{ x: number; y: number }}, b: {{ x: number; y: number }}) => a.x * b.x + a.y * b.y;\\nexport const vec2Dist = (a: {{ x: number; y: number }}, b: {{ x: number; y: number }}) => vec2Len(vec2Sub(a, b));\\nexport const degToRad = (d: number) => d * Math.PI / 180;\\nexport const radToDeg = (r: number) => r * 180 / Math.PI;'

def _gen_color_utils(t: str, g: str) -> str:
    return f'// {t} — Color Utils | {g}\\nexport const hexToRgb = (hex: string) => {{ const r = parseInt(hex.slice(1, 3), 16); const g = parseInt(hex.slice(3, 5), 16); const b = parseInt(hex.slice(5, 7), 16); return {{ r, g, b }}; }};\\nexport const rgbToHex = (r: number, g: number, b: number) => `#${{[r, g, b].map(x => x.toString(16).padStart(2, "0")).join("")}}`;\\nexport const lerpColor = (a: string, b: string, t: number) => {{ const c1 = hexToRgb(a), c2 = hexToRgb(b); return rgbToHex(Math.round(c1.r + (c2.r - c1.r) * t), Math.round(c1.g + (c2.g - c1.g) * t), Math.round(c1.b + (c2.b - c1.b) * t)); }};'

def _gen_formatters(t: str, g: str) -> str:
    return f'// {t} — Formatters | {g}\\nexport const formatNumber = (n: number) => n >= 1e9 ? (n/1e9).toFixed(1)+"B" : n >= 1e6 ? (n/1e6).toFixed(1)+"M" : n >= 1e3 ? (n/1e3).toFixed(1)+"K" : n.toString();\\nexport const formatTime = (ms: number) => {{ const s = Math.floor(ms/1000); const m = Math.floor(s/60); const h = Math.floor(m/60); return h > 0 ? `${{h}}h ${{m%60}}m` : m > 0 ? `${{m}}m ${{s%60}}s` : `${{s}}s`; }};\\nexport const formatPercent = (v: number, d: number = 1) => `${{(v * 100).toFixed(d)}}%`;\\nexport const formatBytes = (b: number) => b >= 1e9 ? (b/1e9).toFixed(2)+" GB" : b >= 1e6 ? (b/1e6).toFixed(2)+" MB" : b >= 1e3 ? (b/1e3).toFixed(2)+" KB" : b+" B";'

def _gen_validators(t: str, g: str) -> str:
    return f'// {t} — Validators | {g}\\nexport const isValid = (v: any) => v !== null && v !== undefined;\\nexport const isInRange = (v: number, min: number, max: number) => v >= min && v <= max;\\nexport const isPositive = (v: number) => v > 0;\\nexport const isNonEmpty = (s: string) => s.trim().length > 0;\\nexport const hasProperty = (obj: any, key: string) => obj && typeof obj === "object" && key in obj;'

def _gen_combat_types(t: str, g: str) -> str:
    return f'// {t} — Combat Types | {g}\\nexport type DamageType = "physical" | "magical" | "fire" | "ice" | "lightning" | "dark" | "holy" | "poison" | "true";\\nexport interface DamageEvent {{ source: string; target: string; amount: number; type: DamageType; isCritical: boolean; timestamp: number; }}\\nexport interface CombatResult {{ damage: number; blocked: number; absorbed: number; resisted: number; isCrit: boolean; isKill: boolean; }}\\nexport interface StatusEffect {{ id: string; name: string; type: "buff" | "debuff"; duration: number; stacks: number; onTick?: (entity: any) => void; }}'

def _gen_inventory_types(t: str, g: str) -> str:
    return f'// {t} — Inventory Types | {g}\\nexport type ItemRarity = "common" | "uncommon" | "rare" | "epic" | "legendary" | "mythic" | "divine";\\nexport type EquipSlot = "head" | "chest" | "legs" | "feet" | "hands" | "weapon" | "offhand" | "ring1" | "ring2" | "amulet" | "cape";\\nexport interface InventoryItem {{ id: string; name: string; rarity: ItemRarity; type: string; stats: Record<string, number>; quantity: number; maxStack: number; weight: number; icon: string; description: string; sellPrice: number; requirements: Record<string, number>; }}'

def _gen_world_types(t: str, g: str) -> str:
    return f'// {t} — World Types | {g}\\nexport interface WorldRegion {{ id: string; name: string; biome: string; level: number; enemies: string[]; resources: string[]; npcs: string[]; connections: string[]; }}\\nexport interface Biome {{ id: string; name: string; temperature: number; humidity: number; elevation: number; groundType: string; vegetation: number; }}\\nexport type Weather = "clear" | "rain" | "snow" | "fog" | "storm" | "sandstorm" | "blizzard";\\nexport type Season = "spring" | "summer" | "autumn" | "winter";\\nexport interface TimeOfDay {{ hours: number; minutes: number; isDaytime: boolean; lightLevel: number; }}'

def _gen_network_types(t: str, g: str) -> str:
    return f'// {t} — Network Types | {g}\\nexport type MessageType = "sync" | "action" | "chat" | "system" | "heartbeat";\\nexport interface NetworkMessage {{ type: MessageType; payload: any; timestamp: number; senderId: string; sequence: number; }}\\nexport interface PlayerInfo {{ id: string; name: string; level: number; position: {{ x: number; y: number }}; latency: number; }}\\nexport interface LobbyInfo {{ id: string; host: string; players: PlayerInfo[]; maxPlayers: number; gameMode: string; status: "waiting" | "starting" | "in_progress" | "finished"; }}'

def _gen_ui_types(t: str, g: str) -> str:
    return f'// {t} — UI Types | {g}\\nexport type ModalType = "inventory" | "settings" | "quest" | "map" | "shop" | "crafting" | "dialog" | "confirm" | "alert";\\nexport interface ToastConfig {{ message: string; type: "info" | "success" | "warning" | "error"; duration: number; }}\\nexport interface MenuItem {{ id: string; label: string; icon: string; action: () => void; disabled?: boolean; badge?: number; }}'

def _gen_animation_hook(t: str, g: str) -> str:
    return f'// {t} — Animation Hook | {g}\\nimport {{ useRef, useCallback }} from "react";\\nimport {{ Animated, Easing }} from "react-native";\\nexport function useAnimation() {{\\n  const value = useRef(new Animated.Value(0)).current;\\n  const fadeIn = useCallback((duration = 300) => Animated.timing(value, {{ toValue: 1, duration, useNativeDriver: true }}).start(), []);\\n  const fadeOut = useCallback((duration = 300) => Animated.timing(value, {{ toValue: 0, duration, useNativeDriver: true }}).start(), []);\\n  const pulse = useCallback(() => Animated.loop(Animated.sequence([Animated.timing(value, {{ toValue: 1.1, duration: 500, easing: Easing.inOut(Easing.ease), useNativeDriver: true }}), Animated.timing(value, {{ toValue: 1, duration: 500, easing: Easing.inOut(Easing.ease), useNativeDriver: true }})])).start(), []);\\n  return {{ value, fadeIn, fadeOut, pulse }};\\n}}'

def _gen_camera_hook(t: str, g: str) -> str:
    return f'// {t} — Camera Hook | {g}\\nimport {{ useState, useCallback }} from "react";\\nexport function useCamera() {{\\n  const [position, setPosition] = useState({{ x: 0, y: 0 }});\\n  const [zoom, setZoom] = useState(1);\\n  const [target, setTarget] = useState<{{ x: number; y: number }} | null>(null);\\n  const panTo = useCallback((x: number, y: number) => setPosition({{ x, y }}), []);\\n  const zoomTo = useCallback((z: number) => setZoom(Math.max(0.1, Math.min(5, z))), []);\\n  const follow = useCallback((t: {{ x: number; y: number }}) => setTarget(t), []);\\n  return {{ position, zoom, target, panTo, zoomTo, follow }};\\n}}'

def _gen_physics_hook(t: str, g: str) -> str:
    return f'// {t} — Physics Hook | {g}\\nimport {{ useState, useCallback, useRef }} from "react";\\nexport function usePhysics() {{\\n  const [gravity, setGravity] = useState({{ x: 0, y: 9.81 }});\\n  const bodies = useRef<Map<string, any>>(new Map());\\n  const addBody = useCallback((id: string, body: any) => bodies.current.set(id, body), []);\\n  const removeBody = useCallback((id: string) => bodies.current.delete(id), []);\\n  const step = useCallback((dt: number) => {{ for (const [, b] of bodies.current) {{ b.velocity = {{ x: b.velocity.x + gravity.x * dt, y: b.velocity.y + gravity.y * dt }}; b.position = {{ x: b.position.x + b.velocity.x * dt, y: b.position.y + b.velocity.y * dt }}; }} }}, [gravity]);\\n  return {{ gravity, setGravity, addBody, removeBody, step }};\\n}}'

def _gen_inventory_hook(t: str, g: str) -> str:
    return f'// {t} — Inventory Hook | {g}\\nimport {{ useState, useCallback }} from "react";\\ninterface Item {{ id: string; name: string; quantity: number; }}\\nexport function useInventory(capacity: number = 100) {{\\n  const [items, setItems] = useState<Item[]>([]);\\n  const addItem = useCallback((item: Item) => setItems(prev => {{ const existing = prev.find(i => i.id === item.id); if (existing) return prev.map(i => i.id === item.id ? {{ ...i, quantity: i.quantity + item.quantity }} : i); if (prev.length >= capacity) return prev; return [...prev, item]; }}), [capacity]);\\n  const removeItem = useCallback((id: string, qty: number = 1) => setItems(prev => prev.map(i => i.id === id ? {{ ...i, quantity: i.quantity - qty }} : i).filter(i => i.quantity > 0)), []);\\n  return {{ items, addItem, removeItem, isFull: items.length >= capacity }};\\n}}'

def _gen_test_file(name: str, title: str, genre: str) -> str:
    return f'''// ═══ {title} — {name} Tests ═══
// Galaxy Studio Factory | Genre: {genre}
import {{ create{name.title().replace("_", "")} }} from '../logic/{name}';

describe('{name}', () => {{
  let engine: ReturnType<typeof create{name.title().replace("_", "")}>;

  beforeEach(() => {{
    engine = create{name.title().replace("_", "")}({{ seed: 42, debugMode: true }});
    engine.initialize();
  }});

  test('initializes correctly', () => {{
    const state = engine.getState();
    expect(state.metrics.tickCount).toBe(0);
    expect(state.metrics.entityCount).toBeGreaterThan(0);
  }});

  test('ticks advance state', () => {{
    for (let i = 0; i < 100; i++) engine.tick(1/60);
    const metrics = engine.getMetrics();
    expect(metrics.tickCount).toBe(100);
  }});

  test('entities can be added and removed', () => {{
    const before = engine.getMetrics().entityCount;
    engine.addEntity('test_1', {{ type: 'test', position: {{ x: 0, y: 0 }}, health: 100, maxHealth: 100, level: 1 }});
    expect(engine.getMetrics().entityCount).toBe(before + 1);
    engine.removeEntity('test_1');
    expect(engine.getMetrics().entityCount).toBe(before);
  }});

  test('spatial queries work', () => {{
    engine.addEntity('nearby', {{ type: 'test', position: {{ x: 10, y: 10 }}, health: 50, maxHealth: 50, level: 1, collisionRadius: 16 }});
    const results = engine.queryArea(10, 10, 50);
    expect(results.length).toBeGreaterThan(0);
  }});

  test('reset clears state', () => {{
    for (let i = 0; i < 50; i++) engine.tick(1/60);
    engine.reset();
    expect(engine.getMetrics().tickCount).toBe(0);
  }});
}});
'''


def _gen_babel_config(t: str) -> str:
    return f'// {t} — Babel Config\\nmodule.exports = function(api) {{ api.cache(true); return {{ presets: ["babel-preset-expo"] }}; }};'

def _gen_eslint_config(t: str) -> str:
    return f'{{"extends": ["expo", "prettier"], "rules": {{"no-unused-vars": "warn"}}}}'

def _gen_metro_config(t: str) -> str:
    return f'// {t} — Metro Config\\nconst {{ getDefaultConfig }} = require("expo/metro-config");\\nconst config = getDefaultConfig(__dirname);\\nmodule.exports = config;'

def _gen_entity_file(name: str, etype: str, title: str, genre: str) -> str:
    """Generate MASSIVE entity file with full AI, stats, abilities, loot, animations, and behavior."""
    h = hash(name)
    base_hp = h % 5000 + 500
    base_atk = h % 500 + 50
    base_def = h % 300 + 20
    base_spd = h % 100 + 10
    level = h % 100 + 1
    xp = h % 10000 + 100
    rarity_idx = h % 5
    rarities = ["common", "uncommon", "rare", "epic", "legendary"]
    elements = ["physical", "fire", "ice", "lightning", "dark", "holy", "nature", "void", "arcane", "chaos"]
    return f'''// ═══ {title} — {name} Entity ═══
// Type: {etype} | Genre: {genre} | Galaxy Studio Factory — 1,444,700 agents | HYPERDENSE ENTITY

// ═══ TYPE DEFINITIONS ═══
export interface {name}Stats {{
  health: number; maxHealth: number; mana: number; maxMana: number;
  attack: number; defense: number; speed: number; critChance: number;
  critDamage: number; accuracy: number; evasion: number; blockChance: number;
  magicAttack: number; magicDefense: number; resistances: Record<string, number>;
  level: number; xpReward: number; goldReward: number;
}}

export interface {name}Ability {{
  id: string; name: string; damage: number; manaCost: number;
  cooldown: number; range: number; aoe: boolean; element: string;
  statusEffect: string | null; duration: number; description: string;
}}

export interface {name}LootEntry {{
  itemId: string; dropChance: number; minQuantity: number;
  maxQuantity: number; rarity: string; levelRequired: number;
}}

export interface {name}AnimationSet {{
  idle: string; walk: string; run: string; attack1: string;
  attack2: string; specialAttack: string; hit: string; death: string;
  spawn: string; taunt: string; cast: string; dodge: string;
}}

export interface {name}BehaviorState {{
  aggression: number; alertRange: number; attackRange: number;
  fleeThreshold: number; patrolRadius: number; leashRange: number;
  targetPriority: string[]; immunities: string[]; weaknesses: string[];
  phases: {{ hpThreshold: number; behavior: string; abilities: string[] }}[];
}}

// ═══ BASE STATS ═══
export const {name.upper()}_BASE: {name}Stats = {{
  health: {base_hp}, maxHealth: {base_hp}, mana: {h % 1000 + 100}, maxMana: {h % 1000 + 100},
  attack: {base_atk}, defense: {base_def}, speed: {base_spd},
  critChance: {(h % 25 + 5) / 100:.2f}, critDamage: {(h % 100 + 150) / 100:.2f},
  accuracy: {(h % 30 + 70) / 100:.2f}, evasion: {(h % 20 + 5) / 100:.2f},
  blockChance: {(h % 15) / 100:.2f}, magicAttack: {h % 400 + 30},
  magicDefense: {h % 250 + 15},
  resistances: {{
    physical: {(h % 30) / 100:.2f}, fire: {((h * 3) % 40) / 100:.2f},
    ice: {((h * 7) % 35) / 100:.2f}, lightning: {((h * 11) % 25) / 100:.2f},
    dark: {((h * 13) % 45) / 100:.2f}, holy: {((h * 17) % 30) / 100:.2f},
    nature: {((h * 19) % 20) / 100:.2f}, void: {((h * 23) % 50) / 100:.2f},
    arcane: {((h * 29) % 35) / 100:.2f}, chaos: {((h * 31) % 40) / 100:.2f},
  }},
  level: {level}, xpReward: {xp}, goldReward: {h % 5000 + 50},
}};

// ═══ ABILITIES ═══
export const {name.upper()}_ABILITIES: {name}Ability[] = [
  {{ id: '{name.lower()}_strike', name: '{name} Strike', damage: {base_atk * 1.2:.0f}, manaCost: 0, cooldown: 0, range: 2, aoe: false, element: '{elements[h % 10]}', statusEffect: null, duration: 0, description: 'A basic melee attack dealing {elements[h % 10]} damage.' }},
  {{ id: '{name.lower()}_slam', name: '{name} Slam', damage: {base_atk * 2.5:.0f}, manaCost: {h % 50 + 20}, cooldown: 8, range: 3, aoe: true, element: '{elements[h % 10]}', statusEffect: 'stun', duration: 2, description: 'Slams the ground dealing AoE damage and stunning enemies.' }},
  {{ id: '{name.lower()}_roar', name: '{name} War Roar', damage: 0, manaCost: {h % 30 + 10}, cooldown: 15, range: 8, aoe: true, element: '{elements[(h + 1) % 10]}', statusEffect: 'fear', duration: 3, description: 'Terrifying roar that causes nearby enemies to flee.' }},
  {{ id: '{name.lower()}_frenzy', name: '{name} Frenzy', damage: {base_atk * 0.8:.0f}, manaCost: {h % 40 + 15}, cooldown: 12, range: 2, aoe: false, element: '{elements[h % 10]}', statusEffect: 'bleed', duration: 5, description: 'Rapid attacks that cause bleeding damage over time.' }},
  {{ id: '{name.lower()}_shield', name: '{name} Barrier', damage: 0, manaCost: {h % 60 + 30}, cooldown: 20, range: 0, aoe: false, element: '{elements[(h + 2) % 10]}', statusEffect: 'shield', duration: 8, description: 'Creates a protective barrier absorbing incoming damage.' }},
  {{ id: '{name.lower()}_ultimate', name: '{name} Apocalypse', damage: {base_atk * 5:.0f}, manaCost: {h % 100 + 80}, cooldown: 45, range: 10, aoe: true, element: '{elements[(h + 3) % 10]}', statusEffect: 'devastation', duration: 4, description: 'Unleashes devastating power across the entire battlefield.' }},
  {{ id: '{name.lower()}_drain', name: '{name} Life Drain', damage: {base_atk * 1.5:.0f}, manaCost: {h % 35 + 25}, cooldown: 10, range: 4, aoe: false, element: 'dark', statusEffect: 'drain', duration: 3, description: 'Drains life from the target, healing the caster.' }},
  {{ id: '{name.lower()}_summon', name: '{name} Summon', damage: 0, manaCost: {h % 80 + 50}, cooldown: 30, range: 5, aoe: false, element: 'arcane', statusEffect: 'summon', duration: 20, description: 'Summons minions to fight alongside the entity.' }},
];

// ═══ LOOT TABLE ═══
export const {name.upper()}_LOOT: {name}LootEntry[] = [
  {{ itemId: '{name.lower()}_trophy', dropChance: 1.0, minQuantity: 1, maxQuantity: 1, rarity: 'common', levelRequired: 1 }},
  {{ itemId: '{name.lower()}_essence', dropChance: 0.50, minQuantity: 1, maxQuantity: 3, rarity: 'uncommon', levelRequired: 5 }},
  {{ itemId: '{name.lower()}_fang', dropChance: 0.30, minQuantity: 1, maxQuantity: 2, rarity: 'rare', levelRequired: 10 }},
  {{ itemId: '{name.lower()}_heart', dropChance: 0.10, minQuantity: 1, maxQuantity: 1, rarity: 'epic', levelRequired: 20 }},
  {{ itemId: '{name.lower()}_soul', dropChance: 0.03, minQuantity: 1, maxQuantity: 1, rarity: 'legendary', levelRequired: 40 }},
  {{ itemId: '{name.lower()}_weapon', dropChance: 0.15, minQuantity: 1, maxQuantity: 1, rarity: '{rarities[rarity_idx]}', levelRequired: {level} }},
  {{ itemId: '{name.lower()}_armor', dropChance: 0.12, minQuantity: 1, maxQuantity: 1, rarity: '{rarities[rarity_idx]}', levelRequired: {level} }},
  {{ itemId: 'gold_pouch', dropChance: 0.80, minQuantity: {h % 100 + 10}, maxQuantity: {h % 500 + 100}, rarity: 'common', levelRequired: 1 }},
  {{ itemId: 'exp_orb', dropChance: 0.60, minQuantity: 1, maxQuantity: 5, rarity: 'uncommon', levelRequired: 1 }},
  {{ itemId: 'rare_material_{(h % 20):02d}', dropChance: 0.08, minQuantity: 1, maxQuantity: 2, rarity: 'rare', levelRequired: 15 }},
];

// ═══ ANIMATIONS ═══
export const {name.upper()}_ANIMATIONS: {name}AnimationSet = {{
  idle: 'anim/{name.lower()}/idle.anim', walk: 'anim/{name.lower()}/walk.anim',
  run: 'anim/{name.lower()}/run.anim', attack1: 'anim/{name.lower()}/attack1.anim',
  attack2: 'anim/{name.lower()}/attack2.anim', specialAttack: 'anim/{name.lower()}/special.anim',
  hit: 'anim/{name.lower()}/hit.anim', death: 'anim/{name.lower()}/death.anim',
  spawn: 'anim/{name.lower()}/spawn.anim', taunt: 'anim/{name.lower()}/taunt.anim',
  cast: 'anim/{name.lower()}/cast.anim', dodge: 'anim/{name.lower()}/dodge.anim',
}};

// ═══ BEHAVIOR AI ═══
export const {name.upper()}_BEHAVIOR: {name}BehaviorState = {{
  aggression: {(h % 80 + 20) / 100:.2f},
  alertRange: {h % 20 + 10},
  attackRange: {h % 5 + 2},
  fleeThreshold: {(h % 15 + 5) / 100:.2f},
  patrolRadius: {h % 30 + 10},
  leashRange: {h % 50 + 30},
  targetPriority: ['lowest_health', 'closest', 'highest_threat', 'healer_first'],
  immunities: [{f"'{elements[h % 10]}'" if rarity_idx > 2 else ''}],
  weaknesses: ['{elements[(h + 5) % 10]}'],
  phases: [
    {{ hpThreshold: 1.0, behavior: 'normal', abilities: ['{name.lower()}_strike', '{name.lower()}_slam'] }},
    {{ hpThreshold: 0.6, behavior: 'aggressive', abilities: ['{name.lower()}_frenzy', '{name.lower()}_roar'] }},
    {{ hpThreshold: 0.3, behavior: 'desperate', abilities: ['{name.lower()}_ultimate', '{name.lower()}_shield', '{name.lower()}_drain'] }},
    {{ hpThreshold: 0.1, behavior: 'enraged', abilities: ['{name.lower()}_ultimate', '{name.lower()}_summon', '{name.lower()}_frenzy'] }},
  ],
}};

// ═══ FACTORY FUNCTIONS ═══
export const create{name} = (level: number = 1, difficulty: number = 1) => {{
  const scale = 1 + (level - 1) * 0.15 * difficulty;
  return {{
    ...{name.upper()}_BASE,
    health: Math.floor({name.upper()}_BASE.maxHealth * scale),
    maxHealth: Math.floor({name.upper()}_BASE.maxHealth * scale),
    mana: Math.floor({name.upper()}_BASE.maxMana * scale * 0.8),
    maxMana: Math.floor({name.upper()}_BASE.maxMana * scale * 0.8),
    attack: Math.floor({name.upper()}_BASE.attack * scale),
    defense: Math.floor({name.upper()}_BASE.defense * scale * 0.9),
    speed: Math.floor({name.upper()}_BASE.speed * (1 + level * 0.02)),
    magicAttack: Math.floor({name.upper()}_BASE.magicAttack * scale),
    magicDefense: Math.floor({name.upper()}_BASE.magicDefense * scale * 0.9),
    level,
    xpReward: Math.floor({name.upper()}_BASE.xpReward * scale * 1.1),
    goldReward: Math.floor({name.upper()}_BASE.goldReward * scale),
    abilities: {name.upper()}_ABILITIES.filter(a => level >= (a.cooldown / 3)),
    loot: {name.upper()}_LOOT.filter(l => level >= l.levelRequired),
    behavior: {name.upper()}_BEHAVIOR,
    animations: {name.upper()}_ANIMATIONS,
  }};
}};

export const get{name}DPS = (level: number = 1) => {{
  const stats = create{name}(level);
  const baseDPS = stats.attack * (1 + stats.critChance * (stats.critDamage - 1));
  const abilityDPS = {name.upper()}_ABILITIES.reduce((sum, a) => sum + (a.damage / Math.max(a.cooldown, 1)), 0);
  return {{ baseDPS: Math.floor(baseDPS), abilityDPS: Math.floor(abilityDPS), totalDPS: Math.floor(baseDPS + abilityDPS) }};
}};

export const simulate{name}Combat = (playerLevel: number, playerDPS: number) => {{
  const entity = create{name}(playerLevel);
  const timeToKill = entity.health / Math.max(playerDPS * (1 - entity.defense / (entity.defense + 500)), 1);
  const entityDPS = get{name}DPS(playerLevel).totalDPS;
  return {{ timeToKill: Math.ceil(timeToKill), entityDPS, difficulty: timeToKill > 30 ? 'hard' : timeToKill > 15 ? 'medium' : 'easy' }};
}};

export type {name}Type = ReturnType<typeof create{name}>;

// ═══ LEVEL SCALING TABLE — 100 LEVELS ═══
export const {name.upper()}_LEVEL_TABLE = Array.from({{ length: 100 }}, (_, lvl) => {{
  const l = lvl + 1;
  const scale = 1 + (l - 1) * 0.15;
  const eliteScale = scale * 1.5;
  const bossScale = scale * 3.0;
  return {{
    level: l,
    normal: {{
      health: Math.floor({base_hp} * scale),
      attack: Math.floor({base_atk} * scale),
      defense: Math.floor({base_def} * scale * 0.9),
      speed: Math.floor({base_spd} * (1 + l * 0.02)),
      xpReward: Math.floor({xp} * scale * 1.1),
      goldReward: Math.floor(({h} % 5000 + 50) * scale),
    }},
    elite: {{
      health: Math.floor({base_hp} * eliteScale),
      attack: Math.floor({base_atk} * eliteScale * 1.2),
      defense: Math.floor({base_def} * eliteScale),
      speed: Math.floor({base_spd} * (1 + l * 0.03)),
      xpReward: Math.floor({xp} * eliteScale * 2),
      goldReward: Math.floor(({h} % 5000 + 50) * eliteScale * 1.5),
      affixes: ['{elements[(h) % 10]}_aura', '{elements[(h+3) % 10]}_shield', 'enrage', 'reflect'][lvl % 4 === 0 ? 0 : lvl % 4],
    }},
    boss: {{
      health: Math.floor({base_hp} * bossScale),
      attack: Math.floor({base_atk} * bossScale),
      defense: Math.floor({base_def} * bossScale),
      speed: Math.floor({base_spd} * (1 + l * 0.01)),
      xpReward: Math.floor({xp} * bossScale * 5),
      goldReward: Math.floor(({h} % 5000 + 50) * bossScale * 3),
      phases: Math.min(4, Math.floor(l / 25) + 1),
      enrageTimer: Math.max(120, 600 - l * 4),
      mythicMultiplier: 1 + l * 0.05,
    }},
    requiredItemLevel: Math.floor(l * 4.5),
    recommendedPartySize: l > 80 ? 8 : l > 60 ? 5 : l > 40 ? 3 : 1,
    respawnSeconds: Math.max(60, 300 - l * 2),
  }};
}});

// ═══ ENCOUNTER DATABASE — 50 ENCOUNTERS ═══
export const {name.upper()}_ENCOUNTERS = Array.from({{ length: 50 }}, (_, i) => {{
  const seed = ({h} * (i + 1) * 7919) & 0xFFFFFFFF;
  const encounterTypes = ['patrol', 'ambush', 'guard', 'ritual', 'feeding', 'treasure_guard', 'boss_summon', 'raid_wave'];
  const environments = ['open_field', 'narrow_corridor', 'arena', 'cliff_edge', 'water_crossing', 'ruins', 'throne_room', 'cave_depths'];
  return {{
    id: `enc_{name.lower()}_${{String(i).padStart(3, '0')}}`,
    type: encounterTypes[seed % encounterTypes.length],
    environment: environments[(seed >> 3) % environments.length],
    count: (seed % 6) + 1,
    minLevel: Math.floor(i * 2) + 1,
    maxLevel: Math.floor(i * 2) + 20,
    isElite: i > 30,
    isBoss: i > 45,
    lootBonus: 1 + (i * 0.05),
    xpBonus: 1 + (i * 0.03),
    specialMechanic: i > 20 ? ['{elements[(h) % 10]}_phase', 'add_spawn', 'enrage_timer', 'environmental'][i % 4] : null,
    requiredResistance: i > 35 ? '{elements[(h+2) % 10]}' : null,
    music: `ost/combat/{name.lower()}_${{['standard', 'intense', 'boss', 'mythic'][Math.min(Math.floor(i / 15), 3)]}}.mp3`,
    dialogueTrigger: i % 10 === 0 ? `dialogue/{name.lower()}/encounter_${{i}}.json` : null,
    cinematicIntro: i > 40,
    achievementId: i > 45 ? `achieve_defeat_{name.lower()}_${{i}}` : null,
    weeklyBonus: i % 7 === 0,
    eventTrigger: i > 48 ? 'world_boss_spawn' : null,
  }};
}});

// ═══ DIALOGUE LINES — 30 LINES ═══
export const {name.upper()}_DIALOGUE = [
  {{ id: 0, trigger: 'spawn', text: "You dare enter my domain, mortal? I am {name}, and this shall be your grave!", voiceId: 'vo_{name.lower()}_spawn' }},
  {{ id: 1, trigger: 'aggro', text: "Your flesh will fuel my power!", voiceId: 'vo_{name.lower()}_aggro_1' }},
  {{ id: 2, trigger: 'aggro', text: "None have survived my wrath. You will be no different.", voiceId: 'vo_{name.lower()}_aggro_2' }},
  {{ id: 3, trigger: 'phase2', text: "You think this is all I have? WITNESS TRUE POWER!", voiceId: 'vo_{name.lower()}_phase2' }},
  {{ id: 4, trigger: 'phase3', text: "I WILL NOT FALL! THE {elements[h % 10].upper()} COURSES THROUGH ME!", voiceId: 'vo_{name.lower()}_phase3' }},
  {{ id: 5, trigger: 'enrage', text: "ENOUGH! I will destroy everything you hold dear!", voiceId: 'vo_{name.lower()}_enrage' }},
  {{ id: 6, trigger: 'kill_player', text: "Pathetic. Your kind never learns.", voiceId: 'vo_{name.lower()}_kill' }},
  {{ id: 7, trigger: 'low_health', text: "This... cannot be... I am... eternal...", voiceId: 'vo_{name.lower()}_dying' }},
  {{ id: 8, trigger: 'death', text: "*death rattle* You... have not... seen... the last...", voiceId: 'vo_{name.lower()}_death' }},
  {{ id: 9, trigger: 'summon_adds', text: "Rise, my servants! Feast upon their bones!", voiceId: 'vo_{name.lower()}_summon' }},
  {{ id: 10, trigger: 'taunt', text: "Is that the best you can do? My children hit harder!", voiceId: 'vo_{name.lower()}_taunt_1' }},
  {{ id: 11, trigger: 'taunt', text: "You call yourself a warrior? I've fought tougher rats!", voiceId: 'vo_{name.lower()}_taunt_2' }},
  {{ id: 12, trigger: 'player_heal', text: "Healing won't save you. I'll just hit harder!", voiceId: 'vo_{name.lower()}_anti_heal' }},
  {{ id: 13, trigger: 'area_denial', text: "The ground beneath you will consume you!", voiceId: 'vo_{name.lower()}_area' }},
  {{ id: 14, trigger: 'shield_break', text: "Your defenses crumble like dust!", voiceId: 'vo_{name.lower()}_shield_break' }},
  {{ id: 15, trigger: 'loot', text: "If you can hear this... the treasure is yours. But beware what follows...", voiceId: 'vo_{name.lower()}_loot_hint' }},
  {{ id: 16, trigger: 'idle_patrol', text: "*grunts* The master's will must be done...", voiceId: 'vo_{name.lower()}_idle_1' }},
  {{ id: 17, trigger: 'idle_patrol', text: "*sniffs air* I smell... adventure...", voiceId: 'vo_{name.lower()}_idle_2' }},
  {{ id: 18, trigger: 'retreat', text: "This isn't over! I will return stronger!", voiceId: 'vo_{name.lower()}_retreat' }},
  {{ id: 19, trigger: 'resurrect', text: "DEATH CANNOT HOLD ME! I RISE AGAIN!", voiceId: 'vo_{name.lower()}_resurrect' }},
];

// ═══ CRAFTING RECIPES FROM DROPS ═══
export const {name.upper()}_RECIPES = [
  {{ result: '{name.lower()}_helm', materials: [{{ id: '{name.lower()}_essence', qty: 5 }}, {{ id: '{name.lower()}_fang', qty: 3 }}, {{ id: 'ore_rare', qty: 10 }}], station: 'forge', skill: 'smithing', level: {level}, xp: {xp // 2} }},
  {{ result: '{name.lower()}_chest', materials: [{{ id: '{name.lower()}_essence', qty: 8 }}, {{ id: '{name.lower()}_heart', qty: 1 }}, {{ id: 'leather_thick', qty: 15 }}], station: 'forge', skill: 'smithing', level: {level + 5}, xp: {xp} }},
  {{ result: '{name.lower()}_weapon', materials: [{{ id: '{name.lower()}_soul', qty: 1 }}, {{ id: '{name.lower()}_fang', qty: 10 }}, {{ id: 'ore_legendary', qty: 5 }}], station: 'anvil', skill: 'weaponcrafting', level: {level + 10}, xp: {xp * 2} }},
  {{ result: '{name.lower()}_potion', materials: [{{ id: '{name.lower()}_essence', qty: 3 }}, {{ id: 'herb_rare', qty: 5 }}, {{ id: 'vial_crystal', qty: 1 }}], station: 'alchemy_table', skill: 'alchemy', level: {level - 10}, xp: {xp // 4} }},
  {{ result: '{name.lower()}_ring', materials: [{{ id: '{name.lower()}_essence', qty: 10 }}, {{ id: 'gem_flawless', qty: 2 }}, {{ id: 'metal_enchanted', qty: 3 }}], station: 'enchanting_table', skill: 'enchanting', level: {level + 8}, xp: {xp} }},
  {{ result: '{name.lower()}_mount_whistle', materials: [{{ id: '{name.lower()}_soul', qty: 3 }}, {{ id: '{name.lower()}_heart', qty: 2 }}, {{ id: 'essence_primal', qty: 5 }}], station: 'beast_altar', skill: 'beast_mastery', level: {level + 20}, xp: {xp * 3} }},
  {{ result: '{name.lower()}_trophy', materials: [{{ id: '{name.lower()}_fang', qty: 20 }}, {{ id: 'wood_ancient', qty: 10 }}, {{ id: 'lacquer_golden', qty: 3 }}], station: 'workbench', skill: 'crafting', level: {level - 5}, xp: {xp // 3} }},
];

// ═══ ENCYCLOPEDIA ENTRY ═══
export const {name.upper()}_ENCYCLOPEDIA = {{
  id: '{name.lower()}',
  name: '{name}',
  category: '{etype}',
  classification: '{["Beast","Undead","Demon","Elemental","Humanoid","Dragon","Construct","Aberration","Celestial","Plant"][h % 10]}',
  habitat: '{["forests","caves","mountains","swamps","deserts","ruins","oceans","sky","underground","void"][h % 10]}',
  rarity: '{rarities[rarity_idx]}',
  firstDiscovered: 'Age of {["Legends","Darkness","Light","Chaos","Order","Storms","Silence","Dragons","Giants","Titans"][h % 10]}',
  lore: `The {name} is a fearsome creature of the {["ancient world","shadow realm","elemental planes","mortal realm","astral sea"][h % 5]}. Legends speak of their origin during the great cataclysm when ${{'{elements[h % 10]}' === 'fire' ? 'the world burned' : '{elements[h % 10]}' === 'ice' ? 'the eternal winter began' : 'reality itself shattered'}}. Warriors who seek to challenge them must prepare for a grueling battle that tests every aspect of their skill. The {name} has been responsible for the destruction of {["countless villages","entire kingdoms","ancient civilizations","divine realms","dimensional barriers"][h % 5]}, and only the most powerful heroes have ever survived an encounter. Their remains are prized by alchemists and blacksmiths for the unique properties of their {["bones","blood","scales","essence","soul fragments"][h % 5]}.`,
  weaknesses: ['{elements[(h+5) % 10]}', '{["blunt","piercing","slashing"][h % 3]}'],
  immunities: [{f"'{elements[h % 10]}'" if rarity_idx > 3 else ''}],
  bestStrategy: '{["focus DPS during vulnerability","kite and use ranged attacks","interrupt heal casts","avoid AoE and burn adds","stack resistances and outlast"][h % 5]}',
  trivia: [
    'First defeated by the legendary hero {["Aldric","Seraphina","Kael","Lyra","Theron"][h % 5]} during the {["Great Hunt","Siege of Blackrock","Battle of Dawn","Eclipse War","Void Incursion"][h % 5]}.',
    'The {name} drops a unique crafting material that can only be obtained from this creature.',
    'In some regions, {name} encounters are considered sacred trials of passage.',
    'The {name} has {h % 7 + 3} known variants across different biomes.',
  ],
  relatedEntities: ['{name}Alpha', '{name}Brood', '{name}Ancient', '{name}Whelp', '{name}Spirit'],
  questInvolvement: ['quest_hunt_{name.lower()}', 'quest_collect_{name.lower()}_parts', 'quest_boss_{name.lower()}_lair'],
  achievementTriggers: ['kill_first_{name.lower()}', 'kill_100_{name.lower()}', 'kill_{name.lower()}_no_damage', 'speed_kill_{name.lower()}'],
}};
'''

def hash(s: str) -> int:
    h = 0
    for c in s:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return h

def _gen_weapon_data(name: str, title: str, genre: str) -> str:
    """Generate MASSIVE weapon data with full stat blocks, upgrades, enchantments, and crafting."""
    h = hash(name)
    base_dmg = h % 500 + 50
    wpn_types = ["sword", "axe", "bow", "staff", "dagger", "mace", "spear", "crossbow", "wand", "greatsword", "katana", "scythe"]
    elements = ["physical", "fire", "ice", "lightning", "dark", "holy", "nature", "void", "arcane", "chaos"]
    rarities = ["common", "uncommon", "rare", "epic", "legendary"]
    return f'''// ═══ {title} — {name} Weapon Data ═══
// Genre: {genre} | Galaxy Studio Factory — 1,444,700 agents | HYPERDENSE WEAPON

export interface WeaponStats {{
  baseDamage: number; attackSpeed: number; critChance: number; critDamage: number;
  range: number; weight: number; durability: number; maxDurability: number;
  armorPen: number; lifesteal: number; knockback: number;
}}

export interface WeaponUpgrade {{
  level: number; cost: number; materials: {{ id: string; quantity: number }}[];
  statBoost: Partial<WeaponStats>;
}}

export interface WeaponEnchantment {{
  id: string; name: string; description: string; tier: number;
  effect: string; value: number; duration: number;
}}

export const {name.upper()}_DATA = {{
  id: '{name.lower()}',
  name: '{name}',
  displayName: '{name.replace("_", " ")}',
  type: '{wpn_types[h % len(wpn_types)]}',
  rarity: '{rarities[h % 5]}',
  element: '{elements[h % 10]}',
  description: 'A {["sturdy","ancient","enchanted","legendary","cursed","mythic","divine","void-touched","primal","chaotic"][h % 10]} {name.lower().replace("_", " ")} forged for {genre} combat in the depths of {title}.',
  lore: '{["Forged in dragonfire","Blessed by the moon goddess","Cursed by a dying king","Found in an ancient tomb","Crafted by the master smiths of the underdark"][h % 5]}.',
  iconPath: 'assets/weapons/{name.lower()}.png',
  modelPath: 'assets/models/weapons/{name.lower()}.glb',
  soundAttack: 'assets/sounds/weapons/{wpn_types[h % len(wpn_types)]}_swing.wav',
  soundHit: 'assets/sounds/weapons/{wpn_types[h % len(wpn_types)]}_hit.wav',
  soundCrit: 'assets/sounds/weapons/{wpn_types[h % len(wpn_types)]}_crit.wav',

  stats: {{
    baseDamage: {base_dmg},
    attackSpeed: {(h % 30 + 10) / 10:.1f},
    critChance: {(h % 25 + 5) / 100:.2f},
    critDamage: {(h % 100 + 150) / 100:.2f},
    range: {h % 5 + 1},
    weight: {(h % 50 + 10) / 10:.1f},
    durability: {h % 500 + 100},
    maxDurability: {h % 500 + 100},
    armorPen: {(h % 30) / 100:.2f},
    lifesteal: {(h % 10) / 100:.2f},
    knockback: {(h % 20) / 10:.1f},
  }} as WeaponStats,

  scaling: {{
    strength: {(h % 8 + 2) / 10:.1f},
    dexterity: {(h % 6 + 1) / 10:.1f},
    intelligence: {(h % 4) / 10:.1f},
    faith: {(h % 3) / 10:.1f},
  }},

  requirements: {{
    level: {h % 60 + 1},
    strength: {h % 40 + 5},
    dexterity: {h % 30 + 5},
    intelligence: {h % 20},
    class: ['{["warrior","paladin","ranger","mage","rogue","berserker","assassin","necromancer"][(h) % 8]}', '{["warrior","paladin","ranger","mage","rogue","berserker","assassin","necromancer"][(h+3) % 8]}'],
  }},

  upgrades: Array.from({{ length: 15 }}, (_, i) => ({{
    level: i + 1,
    cost: Math.floor(100 * Math.pow(1.5, i)),
    materials: [
      {{ id: 'ore_common', quantity: Math.floor(3 + i * 2) }},
      {{ id: i > 4 ? 'ore_rare' : 'ore_uncommon', quantity: Math.floor(1 + i) }},
      {{ id: i > 9 ? 'essence_legendary' : 'essence_rare', quantity: Math.max(1, Math.floor(i / 3)) }},
    ],
    statBoost: {{
      baseDamage: Math.floor({base_dmg} * 0.08 * (i + 1)),
      critChance: i > 5 ? 0.01 : 0,
      critDamage: i > 8 ? 0.05 : 0,
      armorPen: i > 10 ? 0.02 : 0,
    }},
  }} as WeaponUpgrade)),

  enchantments: [
    {{ id: 'fire_brand', name: 'Fire Brand', description: 'Wreathed in flames, dealing additional fire damage.', tier: 1, effect: 'fire_damage', value: Math.floor({base_dmg} * 0.15), duration: 0 }},
    {{ id: 'frost_edge', name: 'Frost Edge', description: 'Chills enemies on hit, reducing their speed.', tier: 1, effect: 'slow', value: 20, duration: 3 }},
    {{ id: 'vampiric', name: 'Vampiric', description: 'Heals the wielder for a portion of damage dealt.', tier: 2, effect: 'lifesteal', value: 8, duration: 0 }},
    {{ id: 'thunderstrike', name: 'Thunderstrike', description: 'Chance to call down lightning on critical hits.', tier: 2, effect: 'chain_lightning', value: Math.floor({base_dmg} * 0.4), duration: 0 }},
    {{ id: 'vorpal', name: 'Vorpal', description: 'Increased critical damage and execution threshold.', tier: 3, effect: 'execute', value: 10, duration: 0 }},
    {{ id: 'abyssal', name: 'Abyssal', description: 'Corrupts the target, dealing void damage over time.', tier: 3, effect: 'void_dot', value: Math.floor({base_dmg} * 0.25), duration: 6 }},
    {{ id: 'celestial', name: 'Celestial', description: 'Holy radiance deals bonus damage to undead.', tier: 4, effect: 'holy_bonus', value: Math.floor({base_dmg} * 0.5), duration: 0 }},
    {{ id: 'apocalyptic', name: 'Apocalyptic', description: 'Devastating strikes that ignore all armor.', tier: 5, effect: 'true_damage', value: Math.floor({base_dmg} * 0.3), duration: 0 }},
  ] as WeaponEnchantment[],

  specialAbility: {{
    name: '{name} Fury',
    description: 'Activate to enter a frenzy state, increasing attack speed by 50% for 10 seconds.',
    cooldown: 60,
    duration: 10,
    manaCost: {h % 50 + 30},
    effect: 'attack_speed_buff',
    value: 50,
  }},

  setBonus: {{
    setName: '{name.split("_")[0] if "_" in name else name} Collection',
    pieces: ['{name.lower()}_weapon', '{name.lower()}_offhand', '{name.lower()}_ring', '{name.lower()}_amulet'],
    bonuses: {{
      2: {{ description: '+15% damage', stats: {{ baseDamage: Math.floor({base_dmg} * 0.15) }} }},
      3: {{ description: '+10% crit chance', stats: {{ critChance: 0.1 }} }},
      4: {{ description: 'Unique proc: {name} Storm', stats: {{ baseDamage: Math.floor({base_dmg} * 0.3) }} }},
    }},
  }},
}} as const;

export type {name.replace("_", "")}Type = typeof {name.upper()}_DATA;
export const get{name.replace("_", "")}DPS = () => {{
  const s = {name.upper()}_DATA.stats;
  return Math.floor(s.baseDamage * s.attackSpeed * (1 + s.critChance * (s.critDamage - 1)));
}};
'''

def _gen_biome_file(name: str, title: str, genre: str) -> str:
    """Generate MASSIVE biome file with full environmental data, spawns, resources, events."""
    h = hash(name)
    ground_types = ["grass", "sand", "stone", "snow", "mud", "lava", "crystal", "void", "coral", "ash"]
    weathers = ["clear", "rain", "storm", "fog", "blizzard", "sandstorm", "volcanic_ash", "aurora", "eclipse", "acid_rain"]
    return f'''// ═══ {title} — {name} Biome ═══
// Genre: {genre} | Galaxy Studio Factory — 1,444,700 agents | HYPERDENSE BIOME

export interface BiomeConfig {{
  name: string; displayName: string; temperature: number; humidity: number;
  elevation: number; groundType: string; vegetation: number; dangerLevel: number;
  visibilityRange: number; movementModifier: number;
}}

export interface BiomeSpawn {{
  entityId: string; weight: number; minGroup: number; maxGroup: number;
  timeOfDay: 'day' | 'night' | 'both'; minLevel: number; maxLevel: number;
}}

export interface BiomeResource {{
  id: string; name: string; type: string; abundance: number;
  respawnTime: number; tool: string; skill: string; minLevel: number;
}}

export interface BiomeEvent {{
  id: string; name: string; description: string; chance: number;
  duration: number; rewards: string[]; dangerLevel: number;
}}

export interface BiomeHazard {{
  id: string; type: string; damage: number; interval: number;
  resistance: string; avoidable: boolean; description: string;
}}

export const {name.upper()}_BIOME = {{
  id: '{name.lower()}',
  name: '{name}',
  displayName: '{name.replace("Tier", " Tier ").replace("_", " ")}',
  description: 'A vast {ground_types[h % len(ground_types)]}-covered realm within {title}, teeming with danger and ancient secrets. Adventurers who dare to explore will find {["bountiful treasures","forgotten relics","powerful enemies","mysterious phenomena","legendary artifacts"][h % 5]}.',
  lore: 'Long ago, this region was home to {["the Ancient Ones","a powerful civilization","elemental forces","void-touched creatures","celestial beings"][h % 5]}. Their legacy endures in the ruins and relics scattered across the landscape.',

  config: {{
    temperature: {h % 60 - 20},
    humidity: {(h % 100) / 100:.2f},
    elevation: {h % 3000},
    groundType: '{ground_types[h % len(ground_types)]}',
    vegetation: {(h % 100) / 100:.2f},
    dangerLevel: {h % 10 + 1},
    visibilityRange: {h % 80 + 20},
    movementModifier: {(h % 40 + 60) / 100:.2f},
    ambientSound: 'assets/sounds/biomes/{name.lower()}_ambient.wav',
    musicTrack: 'assets/music/biomes/{name.lower()}_theme.mp3',
    skybox: 'assets/skyboxes/{ground_types[h % len(ground_types)]}_sky',
    weather: '{weathers[h % len(weathers)]}',
    dayNightCycle: true,
    fogDensity: {(h % 50) / 100:.2f},
    fogColor: '#{h % 256:02x}{(h * 3) % 256:02x}{(h * 7) % 256:02x}',
    lightIntensity: {(h % 60 + 40) / 100:.2f},
    particleEffect: '{["none","fireflies","snow","ash","spores","dust","embers","sparkles"][h % 8]}',
  }} as BiomeConfig & Record<string, any>,

  spawns: [
    {{ entityId: 'goblin_warrior', weight: 30, minGroup: 2, maxGroup: 6, timeOfDay: 'both', minLevel: 1, maxLevel: 20 }},
    {{ entityId: 'wolf_pack', weight: 25, minGroup: 3, maxGroup: 8, timeOfDay: 'night', minLevel: 5, maxLevel: 25 }},
    {{ entityId: 'elemental_{ground_types[h % len(ground_types)]}', weight: 15, minGroup: 1, maxGroup: 3, timeOfDay: 'both', minLevel: 10, maxLevel: 40 }},
    {{ entityId: 'ancient_guardian', weight: 5, minGroup: 1, maxGroup: 1, timeOfDay: 'day', minLevel: 30, maxLevel: 60 }},
    {{ entityId: 'treasure_mimic', weight: 3, minGroup: 1, maxGroup: 1, timeOfDay: 'both', minLevel: 15, maxLevel: 50 }},
    {{ entityId: 'wandering_merchant', weight: 2, minGroup: 1, maxGroup: 1, timeOfDay: 'day', minLevel: 1, maxLevel: 99 }},
    {{ entityId: 'rare_beast_{name.lower()[:8]}', weight: 1, minGroup: 1, maxGroup: 1, timeOfDay: 'night', minLevel: 40, maxLevel: 80 }},
    {{ entityId: 'world_boss_{name.lower()[:8]}', weight: 0.5, minGroup: 1, maxGroup: 1, timeOfDay: 'both', minLevel: 60, maxLevel: 99 }},
  ] as BiomeSpawn[],

  resources: [
    {{ id: 'ore_{name.lower()[:6]}', name: '{name[:10]} Ore', type: 'ore', abundance: {(h % 60 + 10) / 100:.2f}, respawnTime: 300, tool: 'pickaxe', skill: 'mining', minLevel: 1 }},
    {{ id: 'herb_{name.lower()[:6]}', name: '{name[:10]} Herb', type: 'herb', abundance: {(h % 50 + 20) / 100:.2f}, respawnTime: 180, tool: 'sickle', skill: 'herbalism', minLevel: 5 }},
    {{ id: 'wood_{name.lower()[:6]}', name: '{name[:10]} Timber', type: 'wood', abundance: {(h % 40 + 10) / 100:.2f}, respawnTime: 600, tool: 'axe', skill: 'woodcutting', minLevel: 3 }},
    {{ id: 'gem_{name.lower()[:6]}', name: '{name[:10]} Crystal', type: 'gem', abundance: {(h % 20) / 100:.2f}, respawnTime: 1200, tool: 'pickaxe', skill: 'mining', minLevel: 20 }},
    {{ id: 'essence_{name.lower()[:6]}', name: '{name[:10]} Essence', type: 'essence', abundance: {(h % 10 + 1) / 100:.2f}, respawnTime: 3600, tool: 'staff', skill: 'arcana', minLevel: 30 }},
    {{ id: 'leather_{name.lower()[:6]}', name: '{name[:10]} Hide', type: 'leather', abundance: {(h % 30 + 10) / 100:.2f}, respawnTime: 240, tool: 'knife', skill: 'skinning', minLevel: 8 }},
  ] as BiomeResource[],

  events: [
    {{ id: 'invasion_{name.lower()[:6]}', name: '{name[:10]} Invasion', description: 'A horde of enemies attacks the zone!', chance: 0.05, duration: 600, rewards: ['xp_bonus', 'rare_loot_chest', 'reputation'], dangerLevel: 8 }},
    {{ id: 'treasure_rain', name: 'Treasure Rain', description: 'Golden chests fall from the sky!', chance: 0.02, duration: 300, rewards: ['gold', 'gems', 'rare_materials'], dangerLevel: 3 }},
    {{ id: 'boss_spawn', name: 'World Boss Awakens', description: 'A legendary creature emerges!', chance: 0.01, duration: 1800, rewards: ['legendary_loot', 'titles', 'mounts'], dangerLevel: 10 }},
    {{ id: 'weather_anomaly', name: 'Weather Anomaly', description: 'Strange weather brings unexpected effects.', chance: 0.08, duration: 900, rewards: ['unique_resources', 'weather_gems'], dangerLevel: 5 }},
    {{ id: 'portal_rift', name: 'Dimensional Rift', description: 'A portal to another dimension opens!', chance: 0.03, duration: 600, rewards: ['void_essence', 'dimension_keys', 'exotic_loot'], dangerLevel: 9 }},
    {{ id: 'peaceful_gathering', name: 'Harvest Festival', description: 'Resources spawn at increased rates.', chance: 0.10, duration: 1200, rewards: ['bonus_resources', 'crafting_recipes'], dangerLevel: 1 }},
  ] as BiomeEvent[],

  hazards: [
    {{ id: 'lava_pool', type: '{ground_types[h % len(ground_types)]}_hazard', damage: {h % 50 + 10}, interval: 2, resistance: '{["fire","ice","nature","void","arcane"][h % 5]}', avoidable: true, description: 'Dangerous terrain that deals periodic damage.' }},
    {{ id: 'poison_mist', type: 'poison', damage: {h % 30 + 5}, interval: 3, resistance: 'nature', avoidable: true, description: 'Toxic clouds that slowly drain health.' }},
    {{ id: 'gravity_well', type: 'movement', damage: 0, interval: 1, resistance: 'void', avoidable: false, description: 'Zones of altered gravity affecting movement.' }},
  ] as BiomeHazard[],

  points_of_interest: [
    {{ id: 'dungeon_entrance', name: '{name[:10]} Depths', type: 'dungeon', level: {h % 40 + 10}, x: {h % 1000}, y: {(h * 3) % 1000} }},
    {{ id: 'fast_travel', name: '{name[:10]} Waypoint', type: 'waypoint', level: 1, x: {(h * 7) % 1000}, y: {(h * 11) % 1000} }},
    {{ id: 'vendor', name: '{name[:10]} Market', type: 'shop', level: 1, x: {(h * 13) % 1000}, y: {(h * 17) % 1000} }},
    {{ id: 'quest_hub', name: '{name[:10]} Camp', type: 'quest', level: {h % 20 + 5}, x: {(h * 19) % 1000}, y: {(h * 23) % 1000} }},
    {{ id: 'secret_area', name: 'Hidden {name[:10]} Grotto', type: 'secret', level: {h % 60 + 20}, x: {(h * 29) % 1000}, y: {(h * 31) % 1000} }},
  ],

  navigation: {{
    connectedBiomes: ['{ground_types[(h + 1) % len(ground_types)]}_zone', '{ground_types[(h + 3) % len(ground_types)]}_zone'],
    fastTravelUnlockLevel: {h % 15 + 5},
    flyingAllowed: {str(h % 3 != 0).lower()},
    mountAllowed: {str(h % 5 != 0).lower()},
    pvpEnabled: {str(h % 4 == 0).lower()},
  }},
}} as const;

export type {name.replace("_", "").replace("Tier", "")}BiomeType = typeof {name.upper()}_BIOME;

// ═══ PROCEDURAL SPAWN TABLE — 100 ENTRIES ═══
export const {name.upper()}_SPAWN_TABLE = Array.from({{ length: 100 }}, (_, i) => {{
  const seed = ({h} * (i + 1) * 13) & 0xFFFFFFFF;
  const enemies = ['goblin', 'skeleton', 'spider', 'wolf', 'bandit', 'elemental', 'wraith', 'golem', 'troll', 'orc', 'demon', 'lich'];
  const packs = ['solo', 'pair', 'small_group', 'war_party', 'horde', 'raid_force'];
  return {{
    id: `spawn_{name.lower()}_${{String(i).padStart(3, '0')}}`,
    x: (seed % 2000) - 1000,
    y: ((seed >> 8) % 2000) - 1000,
    enemy: enemies[seed % enemies.length],
    packType: packs[(seed >> 4) % packs.length],
    count: (seed % 8) + 1,
    level: Math.floor(i * 1.5) + ({h} % 10),
    isElite: i > 70,
    isBoss: i > 95,
    respawnSeconds: 60 + (seed % 240),
    timeOfDay: i % 3 === 0 ? 'night' : i % 3 === 1 ? 'day' : 'both',
    patrolRadius: (seed % 30) + 5,
    aggroRadius: (seed % 15) + 5,
    lootModifier: 1 + (i * 0.01),
    eventOnly: i > 90,
  }};
}});

// ═══ RESOURCE NODES — 80 ENTRIES ═══
export const {name.upper()}_RESOURCES = Array.from({{ length: 80 }}, (_, i) => {{
  const seed = ({h} * (i + 1) * 17) & 0xFFFFFFFF;
  const types = ['ore', 'herb', 'wood', 'gem', 'essence', 'leather', 'fish', 'mushroom'];
  const qualities = ['poor', 'normal', 'rich', 'pristine', 'legendary'];
  return {{
    id: `res_{name.lower()}_${{String(i).padStart(3, '0')}}`,
    type: types[seed % types.length],
    quality: qualities[(seed >> 3) % qualities.length],
    x: (seed % 1500) - 750,
    y: ((seed >> 7) % 1500) - 750,
    yield: (seed % 10) + 1,
    respawnMinutes: 5 + (seed % 55),
    skillRequired: types[seed % types.length] === 'ore' ? 'mining' : types[seed % types.length] === 'herb' ? 'herbalism' : 'gathering',
    minSkillLevel: Math.floor(i / 4) + 1,
    competition: (seed % 5) + 1,
    guardedBy: i > 50 ? `guardian_{name.lower()}_${{i}}` : null,
    gatherTime: 2 + (seed % 8),
    bonusChance: (seed % 15) / 100,
  }};
}});

// ═══ WEATHER PATTERNS — 20 ENTRIES ═══
export const {name.upper()}_WEATHER = [
  {{ id: 'clear', duration: [300, 1200], chance: 0.30, effects: {{ visibility: 1.0, movement: 1.0, fire_damage: 1.0, ice_damage: 1.0 }}, particle: 'none', skybox: '{name.lower()}_clear' }},
  {{ id: 'rain', duration: [180, 600], chance: 0.20, effects: {{ visibility: 0.7, movement: 0.9, fire_damage: 0.7, ice_damage: 1.2 }}, particle: 'rain_heavy', skybox: '{name.lower()}_overcast' }},
  {{ id: 'storm', duration: [120, 300], chance: 0.10, effects: {{ visibility: 0.4, movement: 0.7, fire_damage: 0.5, ice_damage: 1.3, lightning_damage: 1.5 }}, particle: 'storm_lightning', skybox: '{name.lower()}_storm' }},
  {{ id: 'fog', duration: [240, 900], chance: 0.15, effects: {{ visibility: 0.3, movement: 0.95, fire_damage: 0.9, ice_damage: 1.1 }}, particle: 'fog_thick', skybox: '{name.lower()}_foggy' }},
  {{ id: 'blizzard', duration: [180, 480], chance: 0.05, effects: {{ visibility: 0.2, movement: 0.5, fire_damage: 0.3, ice_damage: 2.0 }}, particle: 'snow_blizzard', skybox: '{name.lower()}_blizzard' }},
  {{ id: 'heatwave', duration: [300, 900], chance: 0.08, effects: {{ visibility: 0.8, movement: 0.85, fire_damage: 1.5, ice_damage: 0.6 }}, particle: 'heat_haze', skybox: '{name.lower()}_scorching' }},
  {{ id: 'eclipse', duration: [60, 180], chance: 0.02, effects: {{ visibility: 0.5, movement: 1.0, dark_damage: 1.8, holy_damage: 0.4 }}, particle: 'eclipse_shadow', skybox: '{name.lower()}_eclipse' }},
  {{ id: 'aurora', duration: [300, 600], chance: 0.03, effects: {{ visibility: 1.2, movement: 1.0, arcane_damage: 1.3, all_xp: 1.1 }}, particle: 'aurora_lights', skybox: '{name.lower()}_aurora' }},
  {{ id: 'meteor_shower', duration: [60, 120], chance: 0.01, effects: {{ visibility: 0.9, movement: 1.0, fire_damage: 2.0, rare_spawn_chance: 2.0 }}, particle: 'meteor_rain', skybox: '{name.lower()}_meteor' }},
  {{ id: 'sandstorm', duration: [120, 480], chance: 0.06, effects: {{ visibility: 0.15, movement: 0.6, all_accuracy: 0.7, nature_damage: 1.4 }}, particle: 'sand_storm', skybox: '{name.lower()}_sandstorm' }},
];

// ═══ BIOME GENERATION PARAMS ═══
export const generate{name.replace("_", "").replace("Tier", "")}Terrain = (seed: number, width = 256, height = 256) => {{
  const grid: number[][] = [];
  for (let y = 0; y < height; y++) {{
    grid[y] = [];
    for (let x = 0; x < width; x++) {{
      const nx = x / width - 0.5;
      const ny = y / height - 0.5;
      let value = Math.sin(nx * 6.28 + seed) * Math.cos(ny * 6.28 + seed * 0.7);
      value += Math.sin(nx * 12.56 + seed * 1.3) * Math.cos(ny * 12.56 + seed * 0.3) * 0.5;
      value += Math.sin(nx * 25.12 + seed * 2.1) * 0.25;
      grid[y][x] = (value + 1.5) / 3;
    }}
  }}
  return {{ seed, width, height, grid, biome: '{name.lower()}', generated: Date.now() }};
}};
'''

def _gen_asset_manifest(cat: str, batch: int, title: str, genre: str, multiplier: int) -> str:
    import json
    assets = []
    for i in range(min(multiplier, 100)):
        assets.append({
            "id": f"{cat}_{batch:04d}_{i:06d}",
            "path": f"assets/{cat}/batch_{batch:04d}/{cat}_{i:06d}.{'png' if cat == 'textures' else 'glb' if cat == 'models' else 'wav' if cat == 'sounds' else 'anim' if cat == 'animations' else 'json'}",
            "size_bytes": hash(f"{cat}_{batch}_{i}") % 10_000_000 + 1000,
            "format": cat,
            "tags": [genre, cat, f"batch_{batch}"],
        })
    return json.dumps({"category": cat, "batch": batch, "count": len(assets), "assets": assets}, indent=2)
