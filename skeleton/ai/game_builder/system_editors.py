"""Typed original-game system editors with eight deterministic mechanics previews.

This is a bounded authoring layer, not a claim that every edited system is
already connected to a shipping runtime. Documents are human-reviewed source,
never external code, and all playable previews are isolated pure simulations.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence

SCHEMA = "skeleton.game_builder.system_editor.v1"
CATALOG = json.loads(r'''[
  {
    "id": "maze",
    "group": "World",
    "title": "Maze & Labyrinth",
    "description": "Connect original maze layouts, hazards, locked exits and proof budgets.",
    "fields": [
      {
        "key": "width",
        "kind": "int",
        "default": 21,
        "minimum": 5,
        "maximum": 255,
        "options": []
      },
      {
        "key": "height",
        "kind": "int",
        "default": 21,
        "minimum": 5,
        "maximum": 255,
        "options": []
      },
      {
        "key": "levels",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 128,
        "options": []
      },
      {
        "key": "hazards",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 64,
        "options": []
      },
      {
        "key": "topology",
        "kind": "enum",
        "default": "grid",
        "minimum": null,
        "maximum": null,
        "options": [
          "grid",
          "circular",
          "braided",
          "moving",
          "non_euclidean"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "rpg",
    "group": "World",
    "title": "Role Playing World",
    "description": "World-scale exploration and dialogue, persistent character progression.",
    "fields": [
      {
        "key": "perspective",
        "kind": "enum",
        "default": "isometric",
        "minimum": null,
        "maximum": null,
        "options": [
          "top_down",
          "isometric",
          "first_person",
          "third_person"
        ]
      },
      {
        "key": "party_size",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 16,
        "options": []
      },
      {
        "key": "quest_depth",
        "kind": "int",
        "default": 12,
        "minimum": 1,
        "maximum": 128,
        "options": []
      },
      {
        "key": "level_cap",
        "kind": "int",
        "default": 50,
        "minimum": 1,
        "maximum": 200,
        "options": []
      },
      {
        "key": "persistent_world",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "platformer",
    "group": "Action",
    "title": "Platformer Physics",
    "description": "Author jump timing, acceleration and tile-ground play; tickable preview.",
    "fields": [
      {
        "key": "gravity",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "jump_impulse",
        "kind": "int",
        "default": 12,
        "minimum": 2,
        "maximum": 40,
        "options": []
      },
      {
        "key": "run_speed",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 15,
        "options": []
      },
      {
        "key": "level_width",
        "kind": "int",
        "default": 60,
        "minimum": 16,
        "maximum": 600,
        "options": []
      },
      {
        "key": "double_jump",
        "kind": "bool",
        "default": false,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": "platformer"
  },
  {
    "id": "metroidvania",
    "group": "World",
    "title": "Interconnected Exploration",
    "description": "Persistent gated traversal, revisits and ability-driven route locks.",
    "fields": [
      {
        "key": "regions",
        "kind": "int",
        "default": 24,
        "minimum": 2,
        "maximum": 200,
        "options": []
      },
      {
        "key": "gates",
        "kind": "int",
        "default": 16,
        "minimum": 0,
        "maximum": 300,
        "options": []
      },
      {
        "key": "abilities",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 40,
        "options": []
      },
      {
        "key": "fast_travel_nodes",
        "kind": "int",
        "default": 4,
        "minimum": 0,
        "maximum": 70,
        "options": []
      },
      {
        "key": "sequence_breaks",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "foe_health",
        "kind": "int",
        "default": 7,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "foe_variation",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "foe_damage",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "enemy_variance",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "hazard_damage",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "starting_health",
        "kind": "int",
        "default": 38,
        "minimum": 5,
        "maximum": 150,
        "options": []
      },
      {
        "key": "starting_stamina",
        "kind": "int",
        "default": 12,
        "minimum": 3,
        "maximum": 60,
        "options": []
      },
      {
        "key": "attack_power",
        "kind": "int",
        "default": 6,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "armor",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "tonics",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "camp_supplies",
        "kind": "int",
        "default": 4,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "opening_shards",
        "kind": "int",
        "default": 6,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "boss_health",
        "kind": "int",
        "default": 30,
        "minimum": 1,
        "maximum": 300,
        "options": []
      },
      {
        "key": "boss_damage",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "boss_reward",
        "kind": "int",
        "default": 25,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "foe_reward",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "heavy_stamina",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 15,
        "options": []
      },
      {
        "key": "heavy_multiplier",
        "kind": "int",
        "default": 4,
        "minimum": 2,
        "maximum": 12,
        "options": []
      },
      {
        "key": "stamina_regen",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "evade_cost",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "focus_cost",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "focus_power",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "cache_variation",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "cache_tonics",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 6,
        "options": []
      },
      {
        "key": "heal_power",
        "kind": "int",
        "default": 12,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "camp_heal",
        "kind": "int",
        "default": 18,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "craft_cost",
        "kind": "int",
        "default": 10,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "craft_gain",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "max_attack",
        "kind": "int",
        "default": 25,
        "minimum": 5,
        "maximum": 100,
        "options": []
      },
      {
        "key": "fast_travel_cost",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "break_stamina",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "secret_interval",
        "kind": "int",
        "default": 3,
        "minimum": 2,
        "maximum": 10,
        "options": []
      },
      {
        "key": "secret_reward",
        "kind": "int",
        "default": 7,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "ending_policy",
        "kind": "enum",
        "default": "endless",
        "minimum": null,
        "maximum": null,
        "options": [
          "endless",
          "campaign"
        ]
      },
      {
        "key": "guard_block",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 15,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "procedural_world",
    "group": "World",
    "title": "Procedural World",
    "description": "Chunk streams, seeds, biome budgets and constrained world generation.",
    "fields": [
      {
        "key": "chunk_size",
        "kind": "int",
        "default": 32,
        "minimum": 8,
        "maximum": 128,
        "options": []
      },
      {
        "key": "active_chunks",
        "kind": "int",
        "default": 25,
        "minimum": 1,
        "maximum": 256,
        "options": []
      },
      {
        "key": "biomes",
        "kind": "int",
        "default": 9,
        "minimum": 1,
        "maximum": 64,
        "options": []
      },
      {
        "key": "seed",
        "kind": "int",
        "default": 10427,
        "minimum": 0,
        "maximum": 2147483647,
        "options": []
      },
      {
        "key": "persistence",
        "kind": "enum",
        "default": "save_deltas",
        "minimum": null,
        "maximum": null,
        "options": [
          "rebuild",
          "save_deltas",
          "snapshot"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "voxel",
    "group": "World",
    "title": "Voxel Construction",
    "description": "Cell-size, material, lighting and construction limits.",
    "fields": [
      {
        "key": "chunk_edge",
        "kind": "int",
        "default": 16,
        "minimum": 8,
        "maximum": 64,
        "options": []
      },
      {
        "key": "visible_chunks",
        "kind": "int",
        "default": 64,
        "minimum": 1,
        "maximum": 512,
        "options": []
      },
      {
        "key": "materials",
        "kind": "int",
        "default": 32,
        "minimum": 1,
        "maximum": 256,
        "options": []
      },
      {
        "key": "destruction",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "light_model",
        "kind": "enum",
        "default": "baked",
        "minimum": null,
        "maximum": null,
        "options": [
          "baked",
          "dynamic",
          "hybrid"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "puzzle",
    "group": "World",
    "title": "Puzzle Rules",
    "description": "Rule sets, undo depth, temporal rewrites and solver complexity.",
    "fields": [
      {
        "key": "logic",
        "kind": "enum",
        "default": "switches",
        "minimum": null,
        "maximum": null,
        "options": [
          "switches",
          "push_blocks",
          "circuits",
          "time",
          "non_euclidean"
        ]
      },
      {
        "key": "board_width",
        "kind": "int",
        "default": 12,
        "minimum": 3,
        "maximum": 60,
        "options": []
      },
      {
        "key": "board_height",
        "kind": "int",
        "default": 12,
        "minimum": 3,
        "maximum": 60,
        "options": []
      },
      {
        "key": "undo_depth",
        "kind": "int",
        "default": 32,
        "minimum": 0,
        "maximum": 1024,
        "options": []
      },
      {
        "key": "solution_required",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "roguelike",
    "group": "World",
    "title": "Roguelike Runs",
    "description": "Permadeath, procedural floors, meta-progression and reward pacing.",
    "fields": [
      {
        "key": "floors",
        "kind": "int",
        "default": 20,
        "minimum": 1,
        "maximum": 200,
        "options": []
      },
      {
        "key": "encounters_per_floor",
        "kind": "int",
        "default": 7,
        "minimum": 1,
        "maximum": 60,
        "options": []
      },
      {
        "key": "item_pool",
        "kind": "int",
        "default": 100,
        "minimum": 5,
        "maximum": 2000,
        "options": []
      },
      {
        "key": "permadeath",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "meta_progress",
        "kind": "enum",
        "default": "unlocks",
        "minimum": null,
        "maximum": null,
        "options": [
          "none",
          "unlocks",
          "upgrades"
        ]
      },
      {
        "key": "starting_health",
        "kind": "int",
        "default": 34,
        "minimum": 5,
        "maximum": 200,
        "options": []
      },
      {
        "key": "starting_stamina",
        "kind": "int",
        "default": 9,
        "minimum": 2,
        "maximum": 60,
        "options": []
      },
      {
        "key": "starting_mana",
        "kind": "int",
        "default": 7,
        "minimum": 0,
        "maximum": 60,
        "options": []
      },
      {
        "key": "attack_power",
        "kind": "int",
        "default": 7,
        "minimum": 1,
        "maximum": 60,
        "options": []
      },
      {
        "key": "armor",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 25,
        "options": []
      },
      {
        "key": "opening_gold",
        "kind": "int",
        "default": 12,
        "minimum": 0,
        "maximum": 200,
        "options": []
      },
      {
        "key": "arrows",
        "kind": "int",
        "default": 6,
        "minimum": 0,
        "maximum": 50,
        "options": []
      },
      {
        "key": "potions",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "rations",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "lockpicks",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "potion_healing",
        "kind": "int",
        "default": 14,
        "minimum": 1,
        "maximum": 80,
        "options": []
      },
      {
        "key": "wall_density",
        "kind": "int",
        "default": 4,
        "minimum": 2,
        "maximum": 20,
        "options": []
      },
      {
        "key": "trap_count",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 4,
        "options": []
      },
      {
        "key": "chest_count",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 4,
        "options": []
      },
      {
        "key": "trap_damage",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "foe_health",
        "kind": "int",
        "default": 10,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "foe_health_growth",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "health_variance",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "foe_attack",
        "kind": "int",
        "default": 4,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "boss_health",
        "kind": "int",
        "default": 32,
        "minimum": 1,
        "maximum": 250,
        "options": []
      },
      {
        "key": "boss_health_growth",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "boss_attack",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 60,
        "options": []
      },
      {
        "key": "boss_armor",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "floor_damage_cap",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "damage_scaling",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "poison_enabled",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "poison_damage",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "poison_duration",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 12,
        "options": []
      },
      {
        "key": "guard_block",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "revive_relic_cost",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "revival_gold_penalty",
        "kind": "int",
        "default": 15,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "enemy_patrol",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "aggro_distance",
        "kind": "int",
        "default": 6,
        "minimum": 0,
        "maximum": 16,
        "options": []
      },
      {
        "key": "archer_range",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 5,
        "options": []
      },
      {
        "key": "dash_cost",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "spell_range",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 5,
        "options": []
      },
      {
        "key": "spell_cost",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "spell_damage",
        "kind": "int",
        "default": 9,
        "minimum": 1,
        "maximum": 60,
        "options": []
      },
      {
        "key": "spell_poison",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "arrow_range",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 5,
        "options": []
      },
      {
        "key": "arrow_damage",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 50,
        "options": []
      },
      {
        "key": "mana_regen",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "food_stamina",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "food_heal",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "chest_gold",
        "kind": "int",
        "default": 10,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "chest_relics",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "chest_potions",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 5,
        "options": []
      },
      {
        "key": "kill_gold",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 40,
        "options": []
      },
      {
        "key": "boss_gold",
        "kind": "int",
        "default": 30,
        "minimum": 0,
        "maximum": 200,
        "options": []
      },
      {
        "key": "kill_xp",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 40,
        "options": []
      },
      {
        "key": "boss_xp",
        "kind": "int",
        "default": 40,
        "minimum": 0,
        "maximum": 200,
        "options": []
      },
      {
        "key": "xp_threshold",
        "kind": "int",
        "default": 18,
        "minimum": 1,
        "maximum": 200,
        "options": []
      },
      {
        "key": "level_health_gain",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "level_attack_gain",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "shrine_vitality",
        "kind": "int",
        "default": 7,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "shrine_attack",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "shrine_armor",
        "kind": "int",
        "default": 1,
        "minimum": 1,
        "maximum": 8,
        "options": []
      },
      {
        "key": "shrine_stamina",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "shrine_gold",
        "kind": "int",
        "default": 12,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "potion_price",
        "kind": "int",
        "default": 9,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "arrow_price",
        "kind": "int",
        "default": 6,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "arrow_bundle",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "weapon_upgrade_price",
        "kind": "int",
        "default": 18,
        "minimum": 1,
        "maximum": 200,
        "options": []
      },
      {
        "key": "armor_upgrade_price",
        "kind": "int",
        "default": 16,
        "minimum": 1,
        "maximum": 200,
        "options": []
      },
      {
        "key": "weapon_gain",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "armor_gain",
        "kind": "int",
        "default": 1,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "rest_health",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 50,
        "options": []
      },
      {
        "key": "disarm_stamina",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "search_recovery",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "scout_stamina",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "win_score",
        "kind": "int",
        "default": 200,
        "minimum": 1,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "spell_stun",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 8,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "sandbox",
    "group": "World",
    "title": "Open-ended Sandbox",
    "description": "Creative play with no mandatory win state; player-led building.",
    "fields": [
      {
        "key": "build_budget",
        "kind": "int",
        "default": 10000,
        "minimum": 100,
        "maximum": 1000000,
        "options": []
      },
      {
        "key": "world_regions",
        "kind": "int",
        "default": 128,
        "minimum": 1,
        "maximum": 4096,
        "options": []
      },
      {
        "key": "allow_perpetual_play",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "creative_mode",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "resource_policy",
        "kind": "enum",
        "default": "finite",
        "minimum": null,
        "maximum": null,
        "options": [
          "finite",
          "renewable",
          "unlimited"
        ]
      },
      {
        "key": "settler_count",
        "kind": "int",
        "default": 4,
        "minimum": 0,
        "maximum": 8,
        "options": []
      },
      {
        "key": "starting_energy",
        "kind": "int",
        "default": 20,
        "minimum": 3,
        "maximum": 100,
        "options": []
      },
      {
        "key": "starting_health",
        "kind": "int",
        "default": 60,
        "minimum": 5,
        "maximum": 150,
        "options": []
      },
      {
        "key": "worker_radius",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 7,
        "options": []
      },
      {
        "key": "crop_days",
        "kind": "int",
        "default": 3,
        "minimum": 2,
        "maximum": 8,
        "options": []
      },
      {
        "key": "crop_yield",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "season_length",
        "kind": "int",
        "default": 12,
        "minimum": 2,
        "maximum": 100,
        "options": []
      },
      {
        "key": "weather_enabled",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "ecology_enabled",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "regrowth_cap",
        "kind": "int",
        "default": 50,
        "minimum": 1,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "regrowth_period",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "rain_replenishment",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "fire_enabled",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "fire_damage",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "generator_output",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "generator_emissions",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "starvation_damage",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 40,
        "options": []
      },
      {
        "key": "morale_decay",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "hunger_gain",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 25,
        "options": []
      },
      {
        "key": "thirst_gain",
        "kind": "int",
        "default": 4,
        "minimum": 0,
        "maximum": 25,
        "options": []
      },
      {
        "key": "hazards_enabled",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "hunger_threshold",
        "kind": "int",
        "default": 80,
        "minimum": 10,
        "maximum": 100,
        "options": []
      },
      {
        "key": "thirst_threshold",
        "kind": "int",
        "default": 80,
        "minimum": 10,
        "maximum": 100,
        "options": []
      },
      {
        "key": "exposure_damage",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 40,
        "options": []
      },
      {
        "key": "milestone_houses",
        "kind": "int",
        "default": 1,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "milestone_population",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 8,
        "options": []
      },
      {
        "key": "move_energy",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 15,
        "options": []
      },
      {
        "key": "work_energy",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 15,
        "options": []
      },
      {
        "key": "harvest_strength",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "water_draw",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "fishing_yield",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 15,
        "options": []
      },
      {
        "key": "irrigation_cost",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "irrigation_effect",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "taming_cost",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "hunting_yield",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "structure_fee",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "plank_wood",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "cooking_yield",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "rest_energy",
        "kind": "int",
        "default": 6,
        "minimum": 1,
        "maximum": 40,
        "options": []
      },
      {
        "key": "portal_power",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "travel_food",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "travel_energy",
        "kind": "int",
        "default": 4,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "house_capacity",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "recruit_fee",
        "kind": "int",
        "default": 20,
        "minimum": 1,
        "maximum": 200,
        "options": []
      },
      {
        "key": "trading",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "food_price",
        "kind": "int",
        "default": 6,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "seed_price",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "ore_price",
        "kind": "int",
        "default": 10,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "terraforming",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "creative_hazards",
        "kind": "bool",
        "default": false,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "initial_fire",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 8,
        "options": []
      },
      {
        "key": "extinguish_water",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "fire_spread_period",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "well_output",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "wildlife_motion",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "wildlife_move_period",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "wildlife_birth_period",
        "kind": "int",
        "default": 7,
        "minimum": 1,
        "maximum": 40,
        "options": []
      },
      {
        "key": "wildlife_cap",
        "kind": "int",
        "default": 12,
        "minimum": 0,
        "maximum": 64,
        "options": []
      },
      {
        "key": "carry_capacity",
        "kind": "int",
        "default": 110,
        "minimum": 40,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "storage_bonus",
        "kind": "int",
        "default": 150,
        "minimum": 10,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "witness_radius",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 8,
        "options": []
      },
      {
        "key": "sound_radius",
        "kind": "int",
        "default": 4,
        "minimum": 0,
        "maximum": 14,
        "options": []
      },
      {
        "key": "observation_limit",
        "kind": "int",
        "default": 24,
        "minimum": 1,
        "maximum": 64,
        "options": []
      },
      {
        "key": "quest_limit",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 32,
        "options": []
      },
      {
        "key": "civic_grant_reserve",
        "kind": "int",
        "default": 60,
        "minimum": 0,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "quest_reward",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "sapling_days",
        "kind": "int",
        "default": 3,
        "minimum": 2,
        "maximum": 8,
        "options": []
      },
      {
        "key": "sapling_wood_yield",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "relief_food",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "relief_water",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "donation_amount",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 10,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "tactics",
    "group": "Strategy",
    "title": "Turn-based Tactics",
    "description": "Grid AP, attack range and bounded unit-turn simulation.",
    "fields": [
      {
        "key": "board_width",
        "kind": "int",
        "default": 10,
        "minimum": 4,
        "maximum": 48,
        "options": []
      },
      {
        "key": "board_height",
        "kind": "int",
        "default": 10,
        "minimum": 4,
        "maximum": 48,
        "options": []
      },
      {
        "key": "action_points",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "attack_range",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "unit_health",
        "kind": "int",
        "default": 12,
        "minimum": 1,
        "maximum": 100,
        "options": []
      }
    ],
    "preview": "tactics"
  },
  {
    "id": "rts",
    "group": "Strategy",
    "title": "Real-Time Strategy",
    "description": "Economy, unit-control groups, fog and command latency.",
    "fields": [
      {
        "key": "max_units",
        "kind": "int",
        "default": 300,
        "minimum": 4,
        "maximum": 5000,
        "options": []
      },
      {
        "key": "resource_nodes",
        "kind": "int",
        "default": 40,
        "minimum": 1,
        "maximum": 800,
        "options": []
      },
      {
        "key": "tick_rate",
        "kind": "int",
        "default": 20,
        "minimum": 5,
        "maximum": 60,
        "options": []
      },
      {
        "key": "fog_of_war",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "supply_model",
        "kind": "enum",
        "default": "population",
        "minimum": null,
        "maximum": null,
        "options": [
          "none",
          "population",
          "logistics"
        ]
      },
      {
        "key": "max_enemy_active",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "starting_wood",
        "kind": "int",
        "default": 32,
        "minimum": 0,
        "maximum": 10000,
        "options": []
      },
      {
        "key": "starting_ore",
        "kind": "int",
        "default": 24,
        "minimum": 0,
        "maximum": 10000,
        "options": []
      },
      {
        "key": "starting_energy",
        "kind": "int",
        "default": 18,
        "minimum": 0,
        "maximum": 10000,
        "options": []
      },
      {
        "key": "friendly_base_health",
        "kind": "int",
        "default": 45,
        "minimum": 1,
        "maximum": 500,
        "options": []
      },
      {
        "key": "enemy_base_health",
        "kind": "int",
        "default": 30,
        "minimum": 1,
        "maximum": 500,
        "options": []
      },
      {
        "key": "obstacle_count",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 12,
        "options": []
      },
      {
        "key": "wood_stock",
        "kind": "int",
        "default": 60,
        "minimum": 1,
        "maximum": 10000,
        "options": []
      },
      {
        "key": "ore_stock",
        "kind": "int",
        "default": 50,
        "minimum": 1,
        "maximum": 10000,
        "options": []
      },
      {
        "key": "energy_stock",
        "kind": "int",
        "default": 40,
        "minimum": 1,
        "maximum": 10000,
        "options": []
      },
      {
        "key": "worker_hp",
        "kind": "int",
        "default": 15,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "soldier_hp",
        "kind": "int",
        "default": 22,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "ranger_hp",
        "kind": "int",
        "default": 16,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "medic_hp",
        "kind": "int",
        "default": 17,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "siege_hp",
        "kind": "int",
        "default": 28,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "worker_attack",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "soldier_attack",
        "kind": "int",
        "default": 6,
        "minimum": 1,
        "maximum": 40,
        "options": []
      },
      {
        "key": "ranger_attack",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 40,
        "options": []
      },
      {
        "key": "siege_attack",
        "kind": "int",
        "default": 10,
        "minimum": 1,
        "maximum": 80,
        "options": []
      },
      {
        "key": "enemy_attack",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "ranger_range",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 6,
        "options": []
      },
      {
        "key": "siege_range",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 6,
        "options": []
      },
      {
        "key": "vision_radius",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 8,
        "options": []
      },
      {
        "key": "sight_upgrade",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 3,
        "options": []
      },
      {
        "key": "base_vision",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 8,
        "options": []
      },
      {
        "key": "worker_capacity",
        "kind": "int",
        "default": 6,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "gather_rate",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "economy_bonus",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "max_buildings",
        "kind": "int",
        "default": 16,
        "minimum": 2,
        "maximum": 30,
        "options": []
      },
      {
        "key": "building_health",
        "kind": "int",
        "default": 20,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "outpost_supply",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "supply_cap",
        "kind": "int",
        "default": 10,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "research_cap",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "research_wood",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 50,
        "options": []
      },
      {
        "key": "research_ore",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 50,
        "options": []
      },
      {
        "key": "research_energy",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 50,
        "options": []
      },
      {
        "key": "weapon_bonus",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "armor_bonus",
        "kind": "int",
        "default": 1,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "enemy_ai",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "enemy_patrol",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "enemy_aggro",
        "kind": "int",
        "default": 4,
        "minimum": 0,
        "maximum": 12,
        "options": []
      },
      {
        "key": "capture_ticks",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "hold_ticks",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "generator_cycle",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "energy_production",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "turret_range",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 6,
        "options": []
      },
      {
        "key": "turret_damage",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "enemy_waves",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "wave_interval",
        "kind": "int",
        "default": 12,
        "minimum": 2,
        "maximum": 100,
        "options": []
      },
      {
        "key": "wave_cap",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 50,
        "options": []
      },
      {
        "key": "scan_energy",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "scan_duration",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "scan_bonus",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 8,
        "options": []
      },
      {
        "key": "repair_wood",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "repair_amount",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "logistics_divisor",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "logistics_damage",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "kill_experience",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "medic_heal",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 40,
        "options": []
      },
      {
        "key": "medic_range",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 6,
        "options": []
      },
      {
        "key": "medic_energy_cost",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "siege_structure_bonus",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 50,
        "options": []
      },
      {
        "key": "veterancy_threshold",
        "kind": "int",
        "default": 6,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "max_veterancy",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "veterancy_damage_bonus",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "aggressive_radius",
        "kind": "int",
        "default": 6,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "defensive_radius",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 6,
        "options": []
      },
      {
        "key": "line_of_sight",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "rain_range_penalty",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 4,
        "options": []
      },
      {
        "key": "enemy_siege_range",
        "kind": "int",
        "default": 1,
        "minimum": 1,
        "maximum": 4,
        "options": []
      },
      {
        "key": "enemy_siege_damage",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 40,
        "options": []
      },
      {
        "key": "desert_logistics_penalty",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 20,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "tower_defense",
    "group": "Strategy",
    "title": "Tower Defense",
    "description": "Build towers, spend credits and resolve enemy waves.",
    "fields": [
      {
        "key": "lane_length",
        "kind": "int",
        "default": 12,
        "minimum": 4,
        "maximum": 64,
        "options": []
      },
      {
        "key": "wave_size",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "tower_range",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "tower_damage",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "starting_credits",
        "kind": "int",
        "default": 60,
        "minimum": 0,
        "maximum": 1000,
        "options": []
      }
    ],
    "preview": "tower_defense"
  },
  {
    "id": "city_builder",
    "group": "Strategy",
    "title": "City & Infrastructure",
    "description": "Zoning, demand, utilities and transport network budgets.",
    "fields": [
      {
        "key": "citizens",
        "kind": "int",
        "default": 200,
        "minimum": 0,
        "maximum": 100000,
        "options": []
      },
      {
        "key": "zones",
        "kind": "int",
        "default": 12,
        "minimum": 1,
        "maximum": 300,
        "options": []
      },
      {
        "key": "utility_nodes",
        "kind": "int",
        "default": 20,
        "minimum": 1,
        "maximum": 500,
        "options": []
      },
      {
        "key": "traffic_simulation",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "economic_model",
        "kind": "enum",
        "default": "mixed",
        "minimum": null,
        "maximum": null,
        "options": [
          "planned",
          "mixed",
          "market"
        ]
      },
      {
        "key": "opening_budget",
        "kind": "int",
        "default": 350,
        "minimum": 50,
        "maximum": 10000,
        "options": []
      },
      {
        "key": "housing_density",
        "kind": "int",
        "default": 24,
        "minimum": 4,
        "maximum": 100,
        "options": []
      },
      {
        "key": "road_capacity",
        "kind": "int",
        "default": 16,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "power_output",
        "kind": "int",
        "default": 60,
        "minimum": 5,
        "maximum": 200,
        "options": []
      },
      {
        "key": "water_output",
        "kind": "int",
        "default": 60,
        "minimum": 5,
        "maximum": 200,
        "options": []
      },
      {
        "key": "industrial_emissions",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "disaster_cycle",
        "kind": "int",
        "default": 8,
        "minimum": 3,
        "maximum": 20,
        "options": []
      },
      {
        "key": "disasters",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "policy",
        "kind": "enum",
        "default": "transit",
        "minimum": null,
        "maximum": null,
        "options": [
          "transit",
          "industrial",
          "ecology"
        ]
      },
      {
        "key": "ending_policy",
        "kind": "enum",
        "default": "endless",
        "minimum": null,
        "maximum": null,
        "options": [
          "endless",
          "campaign"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "colony",
    "group": "Strategy",
    "title": "Colony Simulator",
    "description": "Worker needs, schedules, production, health and crises.",
    "fields": [
      {
        "key": "settlers",
        "kind": "int",
        "default": 12,
        "minimum": 1,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "jobs",
        "kind": "int",
        "default": 16,
        "minimum": 1,
        "maximum": 200,
        "options": []
      },
      {
        "key": "need_decay",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "relationships",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "threats",
        "kind": "enum",
        "default": "adaptive",
        "minimum": null,
        "maximum": null,
        "options": [
          "off",
          "scheduled",
          "adaptive"
        ]
      },
      {
        "key": "initial_stores",
        "kind": "int",
        "default": 24,
        "minimum": 10,
        "maximum": 500,
        "options": []
      },
      {
        "key": "starting_credits",
        "kind": "int",
        "default": 20,
        "minimum": 0,
        "maximum": 200,
        "options": []
      },
      {
        "key": "worker_productivity",
        "kind": "int",
        "default": 1,
        "minimum": 1,
        "maximum": 5,
        "options": []
      },
      {
        "key": "water_yield",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "raid_interval",
        "kind": "int",
        "default": 5,
        "minimum": 3,
        "maximum": 14,
        "options": []
      },
      {
        "key": "disease_pressure",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 6,
        "options": []
      },
      {
        "key": "food_policy",
        "kind": "enum",
        "default": "balanced",
        "minimum": null,
        "maximum": null,
        "options": [
          "frugal",
          "balanced",
          "abundant"
        ]
      },
      {
        "key": "disasters",
        "kind": "enum",
        "default": "rare",
        "minimum": null,
        "maximum": null,
        "options": [
          "off",
          "rare",
          "frequent"
        ]
      },
      {
        "key": "ending_policy",
        "kind": "enum",
        "default": "endless",
        "minimum": null,
        "maximum": null,
        "options": [
          "endless",
          "thriving_victory"
        ]
      },
      {
        "key": "allow_migration",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "factory",
    "group": "Strategy",
    "title": "Factory & Automation",
    "description": "Belts, machines, throughput and deterministic production.",
    "fields": [
      {
        "key": "machines",
        "kind": "int",
        "default": 100,
        "minimum": 1,
        "maximum": 10000,
        "options": []
      },
      {
        "key": "belt_speed",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 60,
        "options": []
      },
      {
        "key": "recipes",
        "kind": "int",
        "default": 40,
        "minimum": 1,
        "maximum": 500,
        "options": []
      },
      {
        "key": "power_supply",
        "kind": "int",
        "default": 250,
        "minimum": 0,
        "maximum": 20000,
        "options": []
      },
      {
        "key": "pollution",
        "kind": "bool",
        "default": false,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "farming",
    "group": "Strategy",
    "title": "Farming & Ecology",
    "description": "Plant cycles, soil, seasons, supply and economic loops.",
    "fields": [
      {
        "key": "crop_types",
        "kind": "int",
        "default": 24,
        "minimum": 1,
        "maximum": 250,
        "options": []
      },
      {
        "key": "growth_days",
        "kind": "int",
        "default": 7,
        "minimum": 1,
        "maximum": 120,
        "options": []
      },
      {
        "key": "field_tiles",
        "kind": "int",
        "default": 120,
        "minimum": 1,
        "maximum": 50000,
        "options": []
      },
      {
        "key": "seasons",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "livestock",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "racing",
    "group": "Vehicle",
    "title": "Circuit Racing",
    "description": "Acceleration, braking, fuel, lap completion and fixed-point replay.",
    "fields": [
      {
        "key": "track_length",
        "kind": "int",
        "default": 100,
        "minimum": 20,
        "maximum": 50000,
        "options": []
      },
      {
        "key": "max_speed",
        "kind": "int",
        "default": 12,
        "minimum": 2,
        "maximum": 100,
        "options": []
      },
      {
        "key": "acceleration",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "brake_force",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "laps",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 50,
        "options": []
      }
    ],
    "preview": "racing"
  },
  {
    "id": "flight",
    "group": "Vehicle",
    "title": "Flight & Aerodynamics",
    "description": "Lift, stall tolerance, control response and airspace dynamics.",
    "fields": [
      {
        "key": "engine_thrust",
        "kind": "int",
        "default": 70,
        "minimum": 1,
        "maximum": 200,
        "options": []
      },
      {
        "key": "wing_lift",
        "kind": "int",
        "default": 85,
        "minimum": 1,
        "maximum": 300,
        "options": []
      },
      {
        "key": "stall_speed",
        "kind": "int",
        "default": 25,
        "minimum": 1,
        "maximum": 200,
        "options": []
      },
      {
        "key": "wind_strength",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "flight_model",
        "kind": "enum",
        "default": "simcade",
        "minimum": null,
        "maximum": null,
        "options": [
          "arcade",
          "simcade",
          "simulation"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "sailing",
    "group": "Vehicle",
    "title": "Sailing & Maritime",
    "description": "Wind, navigation, buoyancy and sea-state response.",
    "fields": [
      {
        "key": "wind_speed",
        "kind": "int",
        "default": 20,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "sea_state",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 12,
        "options": []
      },
      {
        "key": "hull_integrity",
        "kind": "int",
        "default": 100,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "crew_size",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 200,
        "options": []
      },
      {
        "key": "dynamic_currents",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "shooter",
    "group": "Action",
    "title": "Shooter & Waves",
    "description": "A bounded firing, reload and evasive wave combat preview.",
    "fields": [
      {
        "key": "player_health",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "ammo",
        "kind": "int",
        "default": 12,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "enemy_count",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "weapon_damage",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 50,
        "options": []
      },
      {
        "key": "dodge_charges",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 10,
        "options": []
      }
    ],
    "preview": "shooter"
  },
  {
    "id": "fighting",
    "group": "Action",
    "title": "Fighting Game",
    "description": "Frame data, hit stun, guard and combo rules.",
    "fields": [
      {
        "key": "round_seconds",
        "kind": "int",
        "default": 99,
        "minimum": 10,
        "maximum": 300,
        "options": []
      },
      {
        "key": "input_buffer",
        "kind": "int",
        "default": 6,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "hitstun_frames",
        "kind": "int",
        "default": 14,
        "minimum": 1,
        "maximum": 120,
        "options": []
      },
      {
        "key": "guard_meter",
        "kind": "int",
        "default": 100,
        "minimum": 1,
        "maximum": 200,
        "options": []
      },
      {
        "key": "rollback_compatible",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "arena_width",
        "kind": "int",
        "default": 12,
        "minimum": 8,
        "maximum": 16,
        "options": []
      },
      {
        "key": "rounds_to_win",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 5,
        "options": []
      },
      {
        "key": "player_health",
        "kind": "int",
        "default": 100,
        "minimum": 10,
        "maximum": 300,
        "options": []
      },
      {
        "key": "enemy_health",
        "kind": "int",
        "default": 100,
        "minimum": 10,
        "maximum": 300,
        "options": []
      },
      {
        "key": "starting_stamina",
        "kind": "int",
        "default": 100,
        "minimum": 10,
        "maximum": 300,
        "options": []
      },
      {
        "key": "stamina_regen",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "starting_meter",
        "kind": "int",
        "default": 10,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "meter_cap",
        "kind": "int",
        "default": 100,
        "minimum": 10,
        "maximum": 200,
        "options": []
      },
      {
        "key": "meter_gain_per_hit",
        "kind": "int",
        "default": 6,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "move_stamina",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "attack_stamina",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "jump_stamina",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "jump_duration_frames",
        "kind": "int",
        "default": 24,
        "minimum": 1,
        "maximum": 120,
        "options": []
      },
      {
        "key": "parry_stamina",
        "kind": "int",
        "default": 4,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "parry_stun_frames",
        "kind": "int",
        "default": 12,
        "minimum": 0,
        "maximum": 120,
        "options": []
      },
      {
        "key": "parry_meter_gain",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "guard_damage",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 40,
        "options": []
      },
      {
        "key": "guard_chip",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "guard_break_stun",
        "kind": "int",
        "default": 24,
        "minimum": 1,
        "maximum": 120,
        "options": []
      },
      {
        "key": "guard_regen",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "knockback",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 3,
        "options": []
      },
      {
        "key": "ring_outs",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "hazards_enabled",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "hazard_count",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 6,
        "options": []
      },
      {
        "key": "hazard_damage",
        "kind": "int",
        "default": 4,
        "minimum": 0,
        "maximum": 40,
        "options": []
      },
      {
        "key": "hazard_period_frames",
        "kind": "int",
        "default": 60,
        "minimum": 12,
        "maximum": 720,
        "options": []
      },
      {
        "key": "cover_enabled",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "cover_count",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 6,
        "options": []
      },
      {
        "key": "cover_health",
        "kind": "int",
        "default": 15,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "attack_bonus",
        "kind": "int",
        "default": 0,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "combo_limit",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "combo_damage_bonus",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "combo_damage_cap",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 60,
        "options": []
      },
      {
        "key": "frames_per_turn",
        "kind": "int",
        "default": 12,
        "minimum": 1,
        "maximum": 60,
        "options": []
      },
      {
        "key": "recovery_frames",
        "kind": "int",
        "default": 6,
        "minimum": 0,
        "maximum": 120,
        "options": []
      },
      {
        "key": "ai_style",
        "kind": "enum",
        "default": "adaptive",
        "minimum": null,
        "maximum": null,
        "options": [
          "aggressive",
          "defensive",
          "adaptive"
        ]
      },
      {
        "key": "ai_adaptation_threshold",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "ai_defense_frequency",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 4,
        "options": []
      },
      {
        "key": "charge_meter",
        "kind": "int",
        "default": 7,
        "minimum": 0,
        "maximum": 40,
        "options": []
      },
      {
        "key": "recover_stamina",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 50,
        "options": []
      },
      {
        "key": "feint_stamina",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "projectile_meter_cost",
        "kind": "int",
        "default": 12,
        "minimum": 0,
        "maximum": 90,
        "options": []
      },
      {
        "key": "special_meter_cost",
        "kind": "int",
        "default": 30,
        "minimum": 0,
        "maximum": 150,
        "options": []
      },
      {
        "key": "fog_projectile_penalty",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 4,
        "options": []
      },
      {
        "key": "accessibility_auto_guard",
        "kind": "bool",
        "default": false,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "rollback_window_frames",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "max_rollback_corrections",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 32,
        "options": []
      },
      {
        "key": "combo_window_frames",
        "kind": "int",
        "default": 48,
        "minimum": 1,
        "maximum": 480,
        "options": []
      },
      {
        "key": "dash_stamina_cost",
        "kind": "int",
        "default": 4,
        "minimum": 0,
        "maximum": 40,
        "options": []
      },
      {
        "key": "feint_range",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 6,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "stealth",
    "group": "Action",
    "title": "Stealth & Detection",
    "description": "Sight cones, suspicion, sound, patrol and disguise.",
    "fields": [
      {
        "key": "visibility_range",
        "kind": "int",
        "default": 12,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "noise_decay",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 40,
        "options": []
      },
      {
        "key": "guard_count",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 250,
        "options": []
      },
      {
        "key": "suspicion_threshold",
        "kind": "int",
        "default": 75,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "line_of_sight",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "health",
        "kind": "int",
        "default": 12,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "stamina",
        "kind": "int",
        "default": 8,
        "minimum": 2,
        "maximum": 40,
        "options": []
      },
      {
        "key": "sprint_stamina",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "stamina_regen",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "stun_charges",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "smoke_charges",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "emp_charges",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "hacking_charges",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "medkits",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "medkit_heal",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "disguises",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "stun_duration",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "smoke_duration",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "crouch_visibility_reduction",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 6,
        "options": []
      },
      {
        "key": "shadow_bonus",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 6,
        "options": []
      },
      {
        "key": "hearing_range",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 12,
        "options": []
      },
      {
        "key": "crouch_noise_threshold",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "detection_gain",
        "kind": "int",
        "default": 14,
        "minimum": 1,
        "maximum": 50,
        "options": []
      },
      {
        "key": "noise_gain",
        "kind": "int",
        "default": 6,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "contact_damage",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "camera_range",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "alarm_gain",
        "kind": "int",
        "default": 15,
        "minimum": 1,
        "maximum": 50,
        "options": []
      },
      {
        "key": "alarm_cooldown",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "alarm_damage",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "fail_on_alarm",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "emp_radius",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 12,
        "options": []
      },
      {
        "key": "mission",
        "kind": "enum",
        "default": "archive",
        "minimum": null,
        "maximum": null,
        "options": [
          "archive",
          "sabotage",
          "intelligence"
        ]
      },
      {
        "key": "intel_target",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "reinforcement_interval",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 20,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "physics",
    "group": "Action",
    "title": "Physical Objects",
    "description": "Rigid bodies, gravity, joints, collision layers and timestep.",
    "fields": [
      {
        "key": "gravity",
        "kind": "int",
        "default": 10,
        "minimum": 0,
        "maximum": 50,
        "options": []
      },
      {
        "key": "tick_hz",
        "kind": "int",
        "default": 60,
        "minimum": 20,
        "maximum": 240,
        "options": []
      },
      {
        "key": "max_bodies",
        "kind": "int",
        "default": 1000,
        "minimum": 1,
        "maximum": 50000,
        "options": []
      },
      {
        "key": "solver_iterations",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 64,
        "options": []
      },
      {
        "key": "dimension",
        "kind": "enum",
        "default": "2d",
        "minimum": null,
        "maximum": null,
        "options": [
          "2d",
          "3d"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "parkour",
    "group": "Action",
    "title": "Traversal & Parkour",
    "description": "Momentum, climbing, ledges, stamina and skill links.",
    "fields": [
      {
        "key": "max_velocity",
        "kind": "int",
        "default": 20,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "stamina",
        "kind": "int",
        "default": 100,
        "minimum": 10,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "wall_run_ticks",
        "kind": "int",
        "default": 25,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "grapple_reach",
        "kind": "int",
        "default": 20,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "mantling",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "survival",
    "group": "Simulation",
    "title": "Survival & Crafting",
    "description": "Actual bounded food, water, wood, health and crafting actions.",
    "fields": [
      {
        "key": "max_health",
        "kind": "int",
        "default": 20,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "starting_food",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "starting_water",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "initial_wood",
        "kind": "int",
        "default": 0,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "hunger_rate",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 10,
        "options": []
      }
    ],
    "preview": "survival"
  },
  {
    "id": "ecosystem",
    "group": "Simulation",
    "title": "Living Ecosystem",
    "description": "Species, predators, food webs, population and carrying capacity.",
    "fields": [
      {
        "key": "species",
        "kind": "int",
        "default": 20,
        "minimum": 2,
        "maximum": 500,
        "options": []
      },
      {
        "key": "food_capacity",
        "kind": "int",
        "default": 200,
        "minimum": 1,
        "maximum": 100000,
        "options": []
      },
      {
        "key": "predators",
        "kind": "int",
        "default": 4,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "season_ticks",
        "kind": "int",
        "default": 100,
        "minimum": 1,
        "maximum": 10000,
        "options": []
      },
      {
        "key": "migration",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "economy",
    "group": "Simulation",
    "title": "Trading & Economy",
    "description": "Goods, production, market adjustment and trade network.",
    "fields": [
      {
        "key": "goods",
        "kind": "int",
        "default": 60,
        "minimum": 1,
        "maximum": 500,
        "options": []
      },
      {
        "key": "market_nodes",
        "kind": "int",
        "default": 12,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "price_elasticity",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "trade_tax",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "finite_inventory",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "sports",
    "group": "Simulation",
    "title": "Team Sports",
    "description": "Squads, stamina, scoring, rules and match pacing.",
    "fields": [
      {
        "key": "team_size",
        "kind": "int",
        "default": 11,
        "minimum": 1,
        "maximum": 40,
        "options": []
      },
      {
        "key": "match_minutes",
        "kind": "int",
        "default": 90,
        "minimum": 1,
        "maximum": 180,
        "options": []
      },
      {
        "key": "substitutions",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "field_length",
        "kind": "int",
        "default": 100,
        "minimum": 10,
        "maximum": 500,
        "options": []
      },
      {
        "key": "rules",
        "kind": "enum",
        "default": "team",
        "minimum": null,
        "maximum": null,
        "options": [
          "team",
          "racket",
          "arena",
          "turn_based"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "rhythm",
    "group": "Creative",
    "title": "Rhythm & Timing",
    "description": "Generate beat windows and score timestamped input samples.",
    "fields": [
      {
        "key": "bpm",
        "kind": "int",
        "default": 120,
        "minimum": 30,
        "maximum": 320,
        "options": []
      },
      {
        "key": "beat_count",
        "kind": "int",
        "default": 16,
        "minimum": 1,
        "maximum": 256,
        "options": []
      },
      {
        "key": "hit_window_ms",
        "kind": "int",
        "default": 90,
        "minimum": 10,
        "maximum": 250,
        "options": []
      },
      {
        "key": "perfect_window_ms",
        "kind": "int",
        "default": 30,
        "minimum": 5,
        "maximum": 150,
        "options": []
      },
      {
        "key": "miss_penalty",
        "kind": "int",
        "default": 0,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "lane_count",
        "kind": "int",
        "default": 4,
        "minimum": 3,
        "maximum": 6,
        "options": []
      },
      {
        "key": "song_offset_ms",
        "kind": "int",
        "default": 0,
        "minimum": 0,
        "maximum": 5000,
        "options": []
      },
      {
        "key": "meter",
        "kind": "int",
        "default": 4,
        "minimum": 2,
        "maximum": 8,
        "options": []
      },
      {
        "key": "hold_notes",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "slides",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "chords",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "mines",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "hold_length_beats",
        "kind": "int",
        "default": 1,
        "minimum": 1,
        "maximum": 4,
        "options": []
      },
      {
        "key": "accent_interval",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 32,
        "options": []
      },
      {
        "key": "swing_limit_ms",
        "kind": "int",
        "default": 20,
        "minimum": 0,
        "maximum": 250,
        "options": []
      },
      {
        "key": "great_window_ms",
        "kind": "int",
        "default": 60,
        "minimum": 5,
        "maximum": 250,
        "options": []
      },
      {
        "key": "release_window_ms",
        "kind": "int",
        "default": 95,
        "minimum": 10,
        "maximum": 300,
        "options": []
      },
      {
        "key": "perfect_points",
        "kind": "int",
        "default": 100,
        "minimum": 1,
        "maximum": 5000,
        "options": []
      },
      {
        "key": "great_points",
        "kind": "int",
        "default": 70,
        "minimum": 0,
        "maximum": 5000,
        "options": []
      },
      {
        "key": "good_points",
        "kind": "int",
        "default": 35,
        "minimum": 0,
        "maximum": 5000,
        "options": []
      },
      {
        "key": "hold_bonus",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 8,
        "options": []
      },
      {
        "key": "max_multiplier",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 16,
        "options": []
      },
      {
        "key": "combo_interval",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 128,
        "options": []
      },
      {
        "key": "starting_health",
        "kind": "int",
        "default": 100,
        "minimum": 1,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "miss_health",
        "kind": "int",
        "default": 12,
        "minimum": 0,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "stray_interval",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 50,
        "options": []
      },
      {
        "key": "stray_health",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "mine_damage",
        "kind": "int",
        "default": 18,
        "minimum": 0,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "hit_heal",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "clear_threshold_percent",
        "kind": "int",
        "default": 70,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "fail_mode",
        "kind": "enum",
        "default": "health",
        "minimum": null,
        "maximum": null,
        "options": [
          "health",
          "finish_only"
        ]
      },
      {
        "key": "sustain_tolerance_ms",
        "kind": "int",
        "default": 95,
        "minimum": 10,
        "maximum": 300,
        "options": []
      },
      {
        "key": "timing_calibration_ms",
        "kind": "int",
        "default": 0,
        "minimum": 0,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "sound_enabled",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "instrument",
        "kind": "enum",
        "default": "original_sine",
        "minimum": null,
        "maximum": null,
        "options": [
          "original_sine",
          "original_triangle",
          "original_pulse",
          "silent"
        ]
      },
      {
        "key": "swing",
        "kind": "int",
        "default": 0,
        "minimum": 0,
        "maximum": 50,
        "options": []
      },
      {
        "key": "note_velocity",
        "kind": "int",
        "default": 80,
        "minimum": 1,
        "maximum": 127,
        "options": []
      },
      {
        "key": "auto_fail_on_stray",
        "kind": "bool",
        "default": false,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "practice_mode",
        "kind": "bool",
        "default": false,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "difficulty_curve",
        "kind": "enum",
        "default": "linear",
        "minimum": null,
        "maximum": null,
        "options": [
          "linear",
          "dynamic",
          "staged"
        ]
      },
      {
        "key": "accuracy_floor",
        "kind": "int",
        "default": 60,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "assist_mode",
        "kind": "enum",
        "default": "none",
        "minimum": null,
        "maximum": null,
        "options": [
          "none",
          "visual",
          "expanded"
        ]
      }
    ],
    "preview": "rhythm"
  },
  {
    "id": "deck_battler",
    "group": "Creative",
    "title": "Deck Battler",
    "description": "Spend energy, attack, block and progress against an enemy.",
    "fields": [
      {
        "key": "starting_health",
        "kind": "int",
        "default": 25,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "enemy_health",
        "kind": "int",
        "default": 30,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "energy_per_turn",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "attack_damage",
        "kind": "int",
        "default": 6,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "block_value",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 100,
        "options": []
      }
    ],
    "preview": "deck_battler"
  },
  {
    "id": "narrative",
    "group": "Creative",
    "title": "Branching Narrative",
    "description": "Choice forks, flags, continuity and multiple legitimate endings.",
    "fields": [
      {
        "key": "branch_depth",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 128,
        "options": []
      },
      {
        "key": "ending_count",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "state_flags",
        "kind": "int",
        "default": 16,
        "minimum": 1,
        "maximum": 256,
        "options": []
      },
      {
        "key": "postgame_play",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "structure",
        "kind": "enum",
        "default": "branching",
        "minimum": null,
        "maximum": null,
        "options": [
          "linear",
          "branching",
          "emergent",
          "endless"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "dialogue",
    "group": "Creative",
    "title": "Dialogue & Social Choice",
    "description": "Speaker memory, conditions, reputation and localization.",
    "fields": [
      {
        "key": "speakers",
        "kind": "int",
        "default": 20,
        "minimum": 1,
        "maximum": 500,
        "options": []
      },
      {
        "key": "lines_per_scene",
        "kind": "int",
        "default": 24,
        "minimum": 1,
        "maximum": 500,
        "options": []
      },
      {
        "key": "memory_turns",
        "kind": "int",
        "default": 32,
        "minimum": 0,
        "maximum": 10000,
        "options": []
      },
      {
        "key": "choice_consequences",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "text_delivery",
        "kind": "enum",
        "default": "subtitles",
        "minimum": null,
        "maximum": null,
        "options": [
          "subtitles",
          "bubble",
          "visual_novel"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "cinematics",
    "group": "Creative",
    "title": "Cutscenes & Camera",
    "description": "Author camera rigs, cues, tracks and interactive sequences.",
    "fields": [
      {
        "key": "shots",
        "kind": "int",
        "default": 20,
        "minimum": 1,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "max_shot_seconds",
        "kind": "int",
        "default": 30,
        "minimum": 1,
        "maximum": 600,
        "options": []
      },
      {
        "key": "camera_rigs",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 80,
        "options": []
      },
      {
        "key": "skippable",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "cutscene_mode",
        "kind": "enum",
        "default": "realtime",
        "minimum": null,
        "maximum": null,
        "options": [
          "realtime",
          "pre_render",
          "hybrid"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "audio",
    "group": "Creative",
    "title": "Audio & Music",
    "description": "Music layers, spatial mixing, voice concurrency and cue rules.",
    "fields": [
      {
        "key": "channels",
        "kind": "int",
        "default": 32,
        "minimum": 1,
        "maximum": 256,
        "options": []
      },
      {
        "key": "dynamic_layers",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 64,
        "options": []
      },
      {
        "key": "sample_rate",
        "kind": "int",
        "default": 48000,
        "minimum": 8000,
        "maximum": 192000,
        "options": []
      },
      {
        "key": "spatial_audio",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "mix_strategy",
        "kind": "enum",
        "default": "priority",
        "minimum": null,
        "maximum": null,
        "options": [
          "priority",
          "sidechain",
          "fixed"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "animation",
    "group": "Creative",
    "title": "Animation State Machines",
    "description": "Blend trees, root motion, rig budgets and event timelines.",
    "fields": [
      {
        "key": "states",
        "kind": "int",
        "default": 24,
        "minimum": 1,
        "maximum": 2000,
        "options": []
      },
      {
        "key": "blend_ticks",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "bones",
        "kind": "int",
        "default": 64,
        "minimum": 1,
        "maximum": 512,
        "options": []
      },
      {
        "key": "root_motion",
        "kind": "bool",
        "default": false,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "motion_style",
        "kind": "enum",
        "default": "keyframes",
        "minimum": null,
        "maximum": null,
        "options": [
          "keyframes",
          "procedural",
          "hybrid"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "ui_hud",
    "group": "Product",
    "title": "UI & Player HUD",
    "description": "Responsive HUD, interaction mapping, menus and feedback.",
    "fields": [
      {
        "key": "hud_panels",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "menu_depth",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 40,
        "options": []
      },
      {
        "key": "focus_targets",
        "kind": "int",
        "default": 30,
        "minimum": 1,
        "maximum": 500,
        "options": []
      },
      {
        "key": "controller_navigation",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "scalable_text",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "accessibility",
    "group": "Product",
    "title": "Accessibility",
    "description": "Remapping, subtitle, motion and input accommodation.",
    "fields": [
      {
        "key": "full_remap",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "subtitles",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "reduced_motion",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "color_independent_cues",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "font_scale_percent",
        "kind": "int",
        "default": 130,
        "minimum": 75,
        "maximum": 300,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "localization",
    "group": "Product",
    "title": "Localization & Text",
    "description": "Language catalog, string coverage and fallback policy.",
    "fields": [
      {
        "key": "language_count",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 150,
        "options": []
      },
      {
        "key": "text_keys",
        "kind": "int",
        "default": 1000,
        "minimum": 1,
        "maximum": 1000000,
        "options": []
      },
      {
        "key": "rtl_layout",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "plural_rules",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "fallback",
        "kind": "enum",
        "default": "source_language",
        "minimum": null,
        "maximum": null,
        "options": [
          "source_language",
          "display_key",
          "block_release"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "networking",
    "group": "Product",
    "title": "Multiplayer Netcode",
    "description": "Authoritative tick, snapshots, prediction and rollback budgets.",
    "fields": [
      {
        "key": "max_players",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 256,
        "options": []
      },
      {
        "key": "tick_rate",
        "kind": "int",
        "default": 30,
        "minimum": 10,
        "maximum": 120,
        "options": []
      },
      {
        "key": "rollback_frames",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 30,
        "options": []
      },
      {
        "key": "max_latency_ms",
        "kind": "int",
        "default": 150,
        "minimum": 10,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "authority",
        "kind": "enum",
        "default": "server",
        "minimum": null,
        "maximum": null,
        "options": [
          "server",
          "lockstep",
          "local_only"
        ]
      }
    ],
    "preview": null
  },
  {
    "id": "save_system",
    "group": "Product",
    "title": "Persistence & Savegames",
    "description": "Schema revisions, snapshots, autosaves and migration.",
    "fields": [
      {
        "key": "save_slots",
        "kind": "int",
        "default": 10,
        "minimum": 1,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "autosave_minutes",
        "kind": "int",
        "default": 10,
        "minimum": 0,
        "maximum": 120,
        "options": []
      },
      {
        "key": "history_depth",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "atomic_write",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "checksum_verify",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "platform_profile",
    "group": "Product",
    "title": "Platform & Era Adaptation",
    "description": "Budget-controlled genre fidelity across retro and modern targets.",
    "fields": [
      {
        "key": "era",
        "kind": "enum",
        "default": "modern",
        "minimum": null,
        "maximum": null,
        "options": [
          "8bit",
          "16bit",
          "32bit",
          "sixth_gen",
          "seventh_gen",
          "modern"
        ]
      },
      {
        "key": "ram_budget_mb",
        "kind": "int",
        "default": 512,
        "minimum": 1,
        "maximum": 131072,
        "options": []
      },
      {
        "key": "fps_target",
        "kind": "int",
        "default": 60,
        "minimum": 15,
        "maximum": 240,
        "options": []
      },
      {
        "key": "npc_active_budget",
        "kind": "int",
        "default": 40,
        "minimum": 0,
        "maximum": 5000,
        "options": []
      },
      {
        "key": "homebrew_only",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "quest_director",
    "group": "World",
    "title": "Quest & Event Director",
    "description": "NPC witnessed events, causal triggers, branches and consequences.",
    "fields": [
      {
        "key": "event_rules",
        "kind": "int",
        "default": 100,
        "minimum": 1,
        "maximum": 5000,
        "options": []
      },
      {
        "key": "active_quests",
        "kind": "int",
        "default": 16,
        "minimum": 0,
        "maximum": 512,
        "options": []
      },
      {
        "key": "witness_radius",
        "kind": "int",
        "default": 12,
        "minimum": 1,
        "maximum": 1000,
        "options": []
      },
      {
        "key": "consequence_depth",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "nonterminal_world",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "npc_count",
        "kind": "int",
        "default": 4,
        "minimum": 1,
        "maximum": 4,
        "options": []
      },
      {
        "key": "obstacle_count",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 12,
        "options": []
      },
      {
        "key": "site_integrity",
        "kind": "int",
        "default": 12,
        "minimum": 2,
        "maximum": 100,
        "options": []
      },
      {
        "key": "site_stock",
        "kind": "int",
        "default": 12,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "starting_trust",
        "kind": "int",
        "default": 7,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "npc_perception",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 6,
        "options": []
      },
      {
        "key": "starting_suspicion",
        "kind": "int",
        "default": 0,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "starting_gold",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 999,
        "options": []
      },
      {
        "key": "starting_supplies",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "stamina",
        "kind": "int",
        "default": 50,
        "minimum": 1,
        "maximum": 300,
        "options": []
      },
      {
        "key": "starting_reputation",
        "kind": "int",
        "default": 0,
        "minimum": -20,
        "maximum": 20,
        "options": []
      },
      {
        "key": "movement_stamina",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 10,
        "options": []
      },
      {
        "key": "action_stamina",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "help_supplies",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "help_power",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "harm_power",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "gather_units",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "repair_supplies",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "repair_power",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "trust_cap",
        "kind": "int",
        "default": 20,
        "minimum": 7,
        "maximum": 100,
        "options": []
      },
      {
        "key": "suspicion_cap",
        "kind": "int",
        "default": 20,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "empathy_gain",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "harm_trust_loss",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "harm_suspicion",
        "kind": "int",
        "default": 4,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "reputation_cap",
        "kind": "int",
        "default": 20,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "reputation_gain",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "reputation_loss",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "day_ticks",
        "kind": "int",
        "default": 12,
        "minimum": 4,
        "maximum": 100,
        "options": []
      },
      {
        "key": "night_fraction_percent",
        "kind": "int",
        "default": 75,
        "minimum": 25,
        "maximum": 100,
        "options": []
      },
      {
        "key": "night_sight_penalty",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 6,
        "options": []
      },
      {
        "key": "witnesses_required",
        "kind": "int",
        "default": 1,
        "minimum": 1,
        "maximum": 4,
        "options": []
      },
      {
        "key": "event_budget",
        "kind": "int",
        "default": 64,
        "minimum": 1,
        "maximum": 128,
        "options": []
      },
      {
        "key": "memory_records",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 64,
        "options": []
      },
      {
        "key": "rumor_enabled",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "rumor_interval",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "options": []
      },
      {
        "key": "rumor_radius",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "rumor_trust_floor",
        "kind": "int",
        "default": 1,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "rumor_per_tick",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "memory_decay_ticks",
        "kind": "int",
        "default": 48,
        "minimum": 0,
        "maximum": 256,
        "options": []
      },
      {
        "key": "quest_ttl",
        "kind": "int",
        "default": 100,
        "minimum": 4,
        "maximum": 512,
        "options": []
      },
      {
        "key": "evidence_min",
        "kind": "int",
        "default": 1,
        "minimum": 1,
        "maximum": 4,
        "options": []
      },
      {
        "key": "quest_goal",
        "kind": "int",
        "default": 2,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "failure_reputation",
        "kind": "int",
        "default": 18,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "ending_policy",
        "kind": "enum",
        "default": "persistent",
        "minimum": null,
        "maximum": null,
        "options": [
          "persistent",
          "campaign"
        ]
      },
      {
        "key": "rest_stamina",
        "kind": "int",
        "default": 10,
        "minimum": 1,
        "maximum": 50,
        "options": []
      },
      {
        "key": "reward_gold",
        "kind": "int",
        "default": 5,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "exploit_gold",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 100,
        "options": []
      },
      {
        "key": "rule_bonus_modulus",
        "kind": "int",
        "default": 3,
        "minimum": 1,
        "maximum": 16,
        "options": []
      },
      {
        "key": "testimony_trust_floor",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "npc_autonomy",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "npc_self_interest",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "npc_supplies",
        "kind": "int",
        "default": 3,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "npc_energy",
        "kind": "int",
        "default": 5,
        "minimum": 1,
        "maximum": 30,
        "options": []
      },
      {
        "key": "npc_action_energy_cost",
        "kind": "int",
        "default": 1,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "npc_act_interval",
        "kind": "int",
        "default": 10,
        "minimum": 1,
        "maximum": 64,
        "options": []
      },
      {
        "key": "npc_action_budget",
        "kind": "int",
        "default": 8,
        "minimum": 0,
        "maximum": 64,
        "options": []
      },
      {
        "key": "testimony_suspicion_tolerance",
        "kind": "int",
        "default": 2,
        "minimum": 0,
        "maximum": 20,
        "options": []
      },
      {
        "key": "npc_mobility",
        "kind": "bool",
        "default": false,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "npc_patrol_interval",
        "kind": "int",
        "default": 16,
        "minimum": 1,
        "maximum": 128,
        "options": []
      },
      {
        "key": "npc_walk_budget",
        "kind": "int",
        "default": 32,
        "minimum": 0,
        "maximum": 256,
        "options": []
      },
      {
        "key": "npc_move_energy_cost",
        "kind": "int",
        "default": 1,
        "minimum": 1,
        "maximum": 10,
        "options": []
      },
      {
        "key": "npc_lead_radius",
        "kind": "int",
        "default": 6,
        "minimum": 1,
        "maximum": 12,
        "options": []
      },
      {
        "key": "npc_investigation_memory",
        "kind": "int",
        "default": 8,
        "minimum": 1,
        "maximum": 64,
        "options": []
      },
      {
        "key": "npc_avoids_player",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      },
      {
        "key": "npc_pursues_evidence",
        "kind": "bool",
        "default": true,
        "minimum": null,
        "maximum": null,
        "options": []
      }
    ],
    "preview": null
  },
  {
    "id": "npc_society",
    "group": "World",
    "title": "NPC Social Systems",
    "description": "Needs, professions, relationships, schedules and learned evidence.",
    "fields": [
      {
        "key": "population",
        "kind": "int",
        "default": 200,
        "minimum": 0,
        "maximum": 100000,
        "options": []
      },
      {
        "key": "active_npcs",
        "kind": "int",
        "default": 40,
        "minimum": 0,
        "maximum": 10000,
        "options": []
      },
      {
        "key": "relationship_factors",
        "kind": "int",
        "default": 12,
        "minimum": 1,
        "maximum": 100,
        "options": []
      },
      {
        "key": "memory_records",
        "kind": "int",
        "default": 64,
        "minimum": 0,
        "maximum": 4096,
        "options": []
      },
      {
        "key": "simulation_lod",
        "kind": "enum",
        "default": "adaptive",
        "minimum": null,
        "maximum": null,
        "options": [
          "full",
          "adaptive",
          "background"
        ]
      }
    ],
    "preview": null
  }
]''')
# Advanced flight axes materially affect the executable flight model.
for _entry in CATALOG:
    if _entry["id"] == "flight":
        _entry["fields"].extend([
            {"key": "fuel_capacity", "kind": "int", "default": 160, "minimum": 20, "maximum": 500, "options": []},
            {"key": "mass", "kind": "int", "default": 45, "minimum": 1, "maximum": 150, "options": []},
            {"key": "drag", "kind": "int", "default": 20, "minimum": 1, "maximum": 80, "options": []},
            {"key": "turbulence", "kind": "int", "default": 4, "minimum": 0, "maximum": 20, "options": []},
            {"key": "engine_heat_limit", "kind": "int", "default": 90, "minimum": 20, "maximum": 200, "options": []},
            {"key": "cooling_rate", "kind": "int", "default": 2, "minimum": 1, "maximum": 20, "options": []},
            {"key": "runway_length", "kind": "int", "default": 12, "minimum": 6, "maximum": 20, "options": []},
            {"key": "route_length", "kind": "int", "default": 50, "minimum": 40, "maximum": 120, "options": []},
            {"key": "launch_altitude", "kind": "int", "default": 45, "minimum": 5, "maximum": 100, "options": []},
            {"key": "max_altitude", "kind": "int", "default": 240, "minimum": 40, "maximum": 400, "options": []},
            {"key": "landing_speed", "kind": "int", "default": 75, "minimum": 10, "maximum": 250, "options": []},
            {"key": "landing_altitude", "kind": "int", "default": 14, "minimum": 2, "maximum": 50, "options": []},
            {"key": "stall_sink", "kind": "int", "default": 9, "minimum": 1, "maximum": 20, "options": []},
            {"key": "repair_kits", "kind": "int", "default": 2, "minimum": 0, "maximum": 4, "options": []},
            {"key": "boost_charges", "kind": "int", "default": 3, "minimum": 0, "maximum": 8, "options": []},
            {"key": "fuel_burn", "kind": "int", "default": 1, "minimum": 1, "maximum": 5, "options": []},
            {"key": "terrain_height", "kind": "int", "default": 12, "minimum": 0, "maximum": 70, "options": []},
            {"key": "waypoint_floor", "kind": "int", "default": 10, "minimum": 1, "maximum": 100, "options": []},
            {"key": "waypoint_ceiling", "kind": "int", "default": 130, "minimum": 20, "maximum": 350, "options": []},
            {"key": "headwind", "kind": "int", "default": 2, "minimum": 0, "maximum": 20, "options": []},
            {"key": "wind_period", "kind": "int", "default": 6, "minimum": 1, "maximum": 12, "options": []},
            {"key": "damage_tolerance", "kind": "int", "default": 60, "minimum": 20, "maximum": 200, "options": []},
            {"key": "airspace_width", "kind": "int", "default": 4, "minimum": 1, "maximum": 8, "options": []},
            {"key": "lift_response", "kind": "int", "default": 4, "minimum": 1, "maximum": 12, "options": []},
            {"key": "control_response", "kind": "int", "default": 1, "minimum": 1, "maximum": 3, "options": []},
            {"key": "landing_fuel_reserve", "kind": "int", "default": 0, "minimum": 0, "maximum": 80, "options": []},
            {"key": "flight_steps_limit", "kind": "int", "default": 128, "minimum": 32, "maximum": 128, "options": []},
            {"key": "autopilot", "kind": "bool", "default": False, "minimum": None, "maximum": None, "options": []},
        ])
# Distinct genuine vessel mechanics for skiff, sloop and schooner.
for _entry in CATALOG:
    if _entry["id"] == "sailing":
        _entry["fields"].extend([
            {"key": "route_length", "kind": "int", "default": 48, "minimum": 40, "maximum": 120, "options": []},
            {"key": "harbor_length", "kind": "int", "default": 12, "minimum": 6, "maximum": 20, "options": []},
            {"key": "launch_speed", "kind": "int", "default": 3, "minimum": 0, "maximum": 15, "options": []},
            {"key": "cargo_capacity", "kind": "int", "default": 100, "minimum": 10, "maximum": 500, "options": []},
            {"key": "cargo_contract", "kind": "int", "default": 20, "minimum": 1, "maximum": 200, "options": []},
            {"key": "sail_area", "kind": "int", "default": 60, "minimum": 20, "maximum": 120, "options": []},
            {"key": "sail_trim", "kind": "int", "default": 80, "minimum": 0, "maximum": 100, "options": []},
            {"key": "mast_integrity", "kind": "int", "default": 75, "minimum": 10, "maximum": 100, "options": []},
            {"key": "engine_fuel", "kind": "int", "default": 60, "minimum": 0, "maximum": 300, "options": []},
            {"key": "engine_power", "kind": "int", "default": 25, "minimum": 1, "maximum": 50, "options": []},
            {"key": "tide_strength", "kind": "int", "default": 5, "minimum": 0, "maximum": 30, "options": []},
            {"key": "current_period", "kind": "int", "default": 5, "minimum": 1, "maximum": 12, "options": []},
            {"key": "max_speed", "kind": "int", "default": 12, "minimum": 3, "maximum": 25, "options": []},
            {"key": "draft", "kind": "int", "default": 4, "minimum": 1, "maximum": 12, "options": []},
            {"key": "shoal_damage", "kind": "int", "default": 14, "minimum": 1, "maximum": 60, "options": []},
            {"key": "repair_supplies", "kind": "int", "default": 2, "minimum": 0, "maximum": 8, "options": []},
            {"key": "provisions", "kind": "int", "default": 160, "minimum": 20, "maximum": 600, "options": []},
            {"key": "safe_dock_speed", "kind": "int", "default": 5, "minimum": 0, "maximum": 20, "options": []},
            {"key": "wind_variability", "kind": "int", "default": 6, "minimum": 0, "maximum": 20, "options": []},
            {"key": "storm_resistance", "kind": "int", "default": 20, "minimum": 0, "maximum": 100, "options": []},
            {"key": "crew_morale", "kind": "int", "default": 80, "minimum": 0, "maximum": 100, "options": []},
            {"key": "buoy_lane_tolerance", "kind": "int", "default": 1, "minimum": 0, "maximum": 3, "options": []},
            {"key": "fatigue_limit", "kind": "int", "default": 100, "minimum": 20, "maximum": 400, "options": []},
            {"key": "anchor_brake", "kind": "int", "default": 8, "minimum": 1, "maximum": 20, "options": []},
            {"key": "cargo_spill", "kind": "int", "default": 2, "minimum": 0, "maximum": 50, "options": []},
            {"key": "voyage_turn_limit", "kind": "int", "default": 128, "minimum": 30, "maximum": 128, "options": []},
            {"key": "vessel_class", "kind": "enum", "default": "sloop", "minimum": None, "maximum": None, "options": ["skiff", "sloop", "schooner"]},
        ])
# Original traversal mechanics are separately editable but share one guarded replay core.
for _entry in CATALOG:
    if _entry["id"] == "parkour":
        _entry["fields"].extend([
            {"key":"course_length","kind":"int","default":60,"minimum":36,"maximum":128,"options":[]},
            {"key":"max_stride","kind":"int","default":5,"minimum":2,"maximum":8,"options":[]},
            {"key":"stride_divisor","kind":"int","default":8,"minimum":2,"maximum":30,"options":[]},
            {"key":"sprint_gain","kind":"int","default":4,"minimum":1,"maximum":20,"options":[]},
            {"key":"sprint_cost","kind":"int","default":8,"minimum":1,"maximum":30,"options":[]},
            {"key":"jump_cost","kind":"int","default":7,"minimum":1,"maximum":25,"options":[]},
            {"key":"vault_cost","kind":"int","default":4,"minimum":1,"maximum":20,"options":[]},
            {"key":"slide_cost","kind":"int","default":3,"minimum":1,"maximum":20,"options":[]},
            {"key":"wall_run_cost","kind":"int","default":10,"minimum":1,"maximum":30,"options":[]},
            {"key":"grapple_cost","kind":"int","default":12,"minimum":1,"maximum":40,"options":[]},
            {"key":"climb_cost","kind":"int","default":7,"minimum":1,"maximum":30,"options":[]},
            {"key":"grapple_charges","kind":"int","default":5,"minimum":0,"maximum":20,"options":[]},
            {"key":"grip_strength","kind":"int","default":35,"minimum":10,"maximum":100,"options":[]},
            {"key":"jump_power","kind":"int","default":4,"minimum":1,"maximum":10,"options":[]},
            {"key":"climb_power","kind":"int","default":2,"minimum":1,"maximum":8,"options":[]},
            {"key":"vault_clearance","kind":"int","default":3,"minimum":1,"maximum":4,"options":[]},
            {"key":"wall_run_height","kind":"int","default":4,"minimum":1,"maximum":4,"options":[]},
            {"key":"gravity","kind":"int","default":2,"minimum":1,"maximum":8,"options":[]},
            {"key":"surface_friction","kind":"int","default":1,"minimum":0,"maximum":4,"options":[]},
            {"key":"wind_period","kind":"int","default":4,"minimum":1,"maximum":20,"options":[]},
            {"key":"wind_resistance","kind":"int","default":15,"minimum":1,"maximum":100,"options":[]},
            {"key":"momentum_decay","kind":"int","default":2,"minimum":1,"maximum":15,"options":[]},
            {"key":"stamina_recovery","kind":"int","default":8,"minimum":1,"maximum":40,"options":[]},
            {"key":"stamina_regen_per_turn","kind":"int","default":2,"minimum":0,"maximum":15,"options":[]},
            {"key":"max_health","kind":"int","default":100,"minimum":20,"maximum":200,"options":[]},
            {"key":"collision_damage","kind":"int","default":20,"minimum":1,"maximum":80,"options":[]},
            {"key":"hardcore_damage","kind":"int","default":15,"minimum":1,"maximum":80,"options":[]},
            {"key":"trick_reward","kind":"int","default":10,"minimum":1,"maximum":100,"options":[]},
            {"key":"medal_bonus","kind":"int","default":30,"minimum":1,"maximum":100,"options":[]},
            {"key":"completion_bonus","kind":"int","default":200,"minimum":20,"maximum":1000,"options":[]},
            {"key":"medals_required","kind":"int","default":2,"minimum":1,"maximum":4,"options":[]},
            {"key":"time_limit","kind":"int","default":128,"minimum":32,"maximum":128,"options":[]},
            {"key":"jump_cooldown","kind":"int","default":2,"minimum":1,"maximum":8,"options":[]},
            {"key":"double_jump","kind":"bool","default":False,"minimum":None,"maximum":None,"options":[]},
            {"key":"difficulty","kind":"enum","default":"flow","minimum":None,"maximum":None,"options":["assisted","flow","hardcore"]},
        ])
# Four original sports rulesets share typed controls but not scoring authority.
for _entry in CATALOG:
    if _entry["id"] == "sports":
        _entry["fields"].extend([
            {"key":"target_score","kind":"int","default":3,"minimum":1,"maximum":12,"options":[]},
            {"key":"match_turn_limit","kind":"int","default":128,"minimum":20,"maximum":128,"options":[]},
            {"key":"starting_stamina","kind":"int","default":100,"minimum":20,"maximum":300,"options":[]},
            {"key":"opponent_skill","kind":"int","default":8,"minimum":1,"maximum":30,"options":[]},
            {"key":"opponent_speed","kind":"int","default":3,"minimum":1,"maximum":10,"options":[]},
            {"key":"defense_radius","kind":"int","default":2,"minimum":0,"maximum":6,"options":[]},
            {"key":"interception_period","kind":"int","default":4,"minimum":2,"maximum":20,"options":[]},
            {"key":"run_speed","kind":"int","default":6,"minimum":1,"maximum":15,"options":[]},
            {"key":"sprint_speed","kind":"int","default":10,"minimum":2,"maximum":20,"options":[]},
            {"key":"pass_distance","kind":"int","default":9,"minimum":1,"maximum":25,"options":[]},
            {"key":"throw_distance","kind":"int","default":12,"minimum":1,"maximum":30,"options":[]},
            {"key":"tackle_range","kind":"int","default":3,"minimum":1,"maximum":10,"options":[]},
            {"key":"shot_range","kind":"int","default":18,"minimum":3,"maximum":40,"options":[]},
            {"key":"shot_power","kind":"int","default":12,"minimum":1,"maximum":30,"options":[]},
            {"key":"goal_lane_tolerance","kind":"int","default":1,"minimum":0,"maximum":2,"options":[]},
            {"key":"contact_radius","kind":"int","default":2,"minimum":1,"maximum":8,"options":[]},
            {"key":"collision_fatigue","kind":"int","default":7,"minimum":0,"maximum":30,"options":[]},
            {"key":"recovery_per_turn","kind":"int","default":3,"minimum":0,"maximum":20,"options":[]},
            {"key":"substitution_energy","kind":"int","default":25,"minimum":1,"maximum":100,"options":[]},
            {"key":"fatigue_limit","kind":"int","default":70,"minimum":20,"maximum":300,"options":[]},
            {"key":"fatigue_tax","kind":"int","default":2,"minimum":1,"maximum":20,"options":[]},
            {"key":"strike_precision","kind":"int","default":4,"minimum":1,"maximum":20,"options":[]},
            {"key":"rally_combo","kind":"int","default":3,"minimum":1,"maximum":12,"options":[]},
            {"key":"racket_control","kind":"int","default":4,"minimum":0,"maximum":30,"options":[]},
            {"key":"action_points","kind":"int","default":3,"minimum":1,"maximum":8,"options":[]},
            {"key":"rain_stride_penalty","kind":"int","default":2,"minimum":0,"maximum":8,"options":[]},
            {"key":"wind_shot_penalty","kind":"int","default":4,"minimum":0,"maximum":20,"options":[]},
            {"key":"press_tackle_bonus","kind":"int","default":2,"minimum":0,"maximum":6,"options":[]},
        ])
# Spatial topology changes the actual labyrinth transition rules.
for _entry in CATALOG:
    if _entry["id"] == "maze":
        _entry["fields"].extend([
            {"key":"key_count","kind":"int","default":2,"minimum":1,"maximum":4,"options":[]},
            {"key":"wall_budget","kind":"int","default":16,"minimum":0,"maximum":64,"options":[]},
            {"key":"health","kind":"int","default":100,"minimum":10,"maximum":200,"options":[]},
            {"key":"stamina","kind":"int","default":80,"minimum":5,"maximum":250,"options":[]},
            {"key":"torches","kind":"int","default":2,"minimum":0,"maximum":16,"options":[]},
            {"key":"torch_duration","kind":"int","default":12,"minimum":1,"maximum":40,"options":[]},
            {"key":"move_cost","kind":"int","default":1,"minimum":1,"maximum":10,"options":[]},
            {"key":"diagonal_cost","kind":"int","default":1,"minimum":0,"maximum":8,"options":[]},
            {"key":"stair_cost","kind":"int","default":2,"minimum":1,"maximum":10,"options":[]},
            {"key":"portal_cost","kind":"int","default":3,"minimum":1,"maximum":20,"options":[]},
            {"key":"phase_period","kind":"int","default":3,"minimum":1,"maximum":16,"options":[]},
            {"key":"hazard_damage","kind":"int","default":12,"minimum":1,"maximum":80,"options":[]},
            {"key":"crush_damage","kind":"int","default":15,"minimum":1,"maximum":80,"options":[]},
            {"key":"rest_recovery","kind":"int","default":9,"minimum":1,"maximum":40,"options":[]},
            {"key":"exploration_budget","kind":"int","default":128,"minimum":8,"maximum":128,"options":[]},
            {"key":"completion_bonus","kind":"int","default":200,"minimum":10,"maximum":1000,"options":[]},
            {"key":"key_reward","kind":"int","default":30,"minimum":1,"maximum":100,"options":[]},
            {"key":"turn_limit","kind":"int","default":128,"minimum":24,"maximum":128,"options":[]},
        ])
# Real standalone RPG and procedural world runtime configuration.
for _entry in CATALOG:
    if _entry["id"] in ("rpg","procedural_world"):
        _extended={
            "rpg":[
                {"key":"world_width","kind":"int","default":9,"minimum":8,"maximum":24,"options":[]},
                {"key":"world_height","kind":"int","default":9,"minimum":8,"maximum":24,"options":[]},
                {"key":"max_obstacles","kind":"int","default":16,"minimum":0,"maximum":64,"options":[]},
                {"key":"enemy_health","kind":"int","default":22,"minimum":1,"maximum":250,"options":[]},
                {"key":"enemy_damage","kind":"int","default":4,"minimum":0,"maximum":30,"options":[]},
                {"key":"hero_health","kind":"int","default":60,"minimum":10,"maximum":200,"options":[]},
                {"key":"hero_mana","kind":"int","default":25,"minimum":0,"maximum":100,"options":[]},
                {"key":"starting_herbs","kind":"int","default":3,"minimum":0,"maximum":20,"options":[]},
                {"key":"starting_potions","kind":"int","default":2,"minimum":0,"maximum":20,"options":[]},
                {"key":"camp_supplies","kind":"int","default":4,"minimum":0,"maximum":20,"options":[]},
                {"key":"starting_gold","kind":"int","default":20,"minimum":0,"maximum":200,"options":[]},
                {"key":"diplomacy_cost","kind":"int","default":3,"minimum":0,"maximum":30,"options":[]},
                {"key":"quest_gold_reward","kind":"int","default":12,"minimum":1,"maximum":100,"options":[]},
                {"key":"quest_xp","kind":"int","default":30,"minimum":1,"maximum":100,"options":[]},
                {"key":"combat_xp","kind":"int","default":40,"minimum":1,"maximum":100,"options":[]},
                {"key":"xp_per_level","kind":"int","default":20,"minimum":2,"maximum":100,"options":[]},
                {"key":"level_heal","kind":"int","default":8,"minimum":0,"maximum":50,"options":[]},
                {"key":"level_mana","kind":"int","default":4,"minimum":0,"maximum":30,"options":[]},
                {"key":"attack_damage","kind":"int","default":8,"minimum":1,"maximum":40,"options":[]},
                {"key":"spell_cost","kind":"int","default":4,"minimum":1,"maximum":30,"options":[]},
                {"key":"spell_damage","kind":"int","default":12,"minimum":1,"maximum":40,"options":[]},
                {"key":"guard_block","kind":"int","default":3,"minimum":0,"maximum":25,"options":[]},
                {"key":"potion_healing","kind":"int","default":18,"minimum":1,"maximum":100,"options":[]},
                {"key":"camp_healing","kind":"int","default":20,"minimum":1,"maximum":100,"options":[]},
                {"key":"camp_mana","kind":"int","default":12,"minimum":0,"maximum":100,"options":[]},
                {"key":"herb_capacity","kind":"int","default":20,"minimum":2,"maximum":100,"options":[]},
                {"key":"gear_cost","kind":"int","default":8,"minimum":1,"maximum":50,"options":[]},
                {"key":"max_gear","kind":"int","default":4,"minimum":1,"maximum":12,"options":[]},
                {"key":"chapter_bonus","kind":"int","default":200,"minimum":10,"maximum":1000,"options":[]},
                {"key":"turn_limit","kind":"int","default":128,"minimum":32,"maximum":128,"options":[]},
                {"key":"guardian_strike_bonus","kind":"int","default":3,"minimum":0,"maximum":12,"options":[]},
                {"key":"guardian_guard_bonus","kind":"int","default":3,"minimum":0,"maximum":15,"options":[]},
                {"key":"scholar_spell_bonus","kind":"int","default":5,"minimum":0,"maximum":20,"options":[]},
                {"key":"scout_evasion","kind":"int","default":1,"minimum":0,"maximum":10,"options":[]},
                {"key":"mender_heal_bonus","kind":"int","default":6,"minimum":0,"maximum":30,"options":[]},
                {"key":"ore_capacity","kind":"int","default":8,"minimum":1,"maximum":30,"options":[]},
            ],
            "procedural_world":[
                {"key":"world_radius_chunks","kind":"int","default":3,"minimum":1,"maximum":16,"options":[]},
                {"key":"resource_density","kind":"int","default":3,"minimum":1,"maximum":12,"options":[]},
                {"key":"starting_wood","kind":"int","default":8,"minimum":0,"maximum":100,"options":[]},
                {"key":"starting_stone","kind":"int","default":8,"minimum":0,"maximum":100,"options":[]},
                {"key":"starting_food","kind":"int","default":30,"minimum":0,"maximum":100,"options":[]},
                {"key":"starting_water","kind":"int","default":15,"minimum":0,"maximum":100,"options":[]},
                {"key":"starting_seeds","kind":"int","default":4,"minimum":0,"maximum":50,"options":[]},
                {"key":"health","kind":"int","default":80,"minimum":10,"maximum":200,"options":[]},
                {"key":"energy","kind":"int","default":120,"minimum":10,"maximum":250,"options":[]},
                {"key":"exploration_budget","kind":"int","default":128,"minimum":8,"maximum":128,"options":[]},
                {"key":"max_edited_tiles","kind":"int","default":64,"minimum":1,"maximum":128,"options":[]},
                {"key":"shelter_wood","kind":"int","default":3,"minimum":1,"maximum":20,"options":[]},
                {"key":"shelter_stone","kind":"int","default":2,"minimum":1,"maximum":20,"options":[]},
                {"key":"rest_energy","kind":"int","default":18,"minimum":1,"maximum":50,"options":[]},
                {"key":"shelter_healing","kind":"int","default":9,"minimum":0,"maximum":40,"options":[]},
                {"key":"hydration_gain","kind":"int","default":8,"minimum":1,"maximum":30,"options":[]},
                {"key":"tool_stone","kind":"int","default":2,"minimum":1,"maximum":20,"options":[]},
                {"key":"tool_ore","kind":"int","default":1,"minimum":0,"maximum":10,"options":[]},
                {"key":"survey_reward","kind":"int","default":40,"minimum":1,"maximum":100,"options":[]},
                {"key":"expedition_bonus","kind":"int","default":200,"minimum":10,"maximum":1000,"options":[]},
                {"key":"sprint_thirst","kind":"int","default":2,"minimum":0,"maximum":10,"options":[]},
                {"key":"thirst_period","kind":"int","default":5,"minimum":1,"maximum":20,"options":[]},
                {"key":"thirst_limit","kind":"int","default":30,"minimum":5,"maximum":100,"options":[]},
                {"key":"dehydration_damage","kind":"int","default":4,"minimum":1,"maximum":30,"options":[]},
                {"key":"turn_limit","kind":"int","default":128,"minimum":32,"maximum":128,"options":[]},
            ],
        }[_entry["id"]]
        _entry["fields"].extend(_extended)
# Executable source-defined society and living ecosystem controls.
for _entry in CATALOG:
    if _entry["id"] in ("npc_society","ecosystem"):
        _extension={
            "npc_society":[
                {"key":"initial_food","kind":"int","default":90,"minimum":0,"maximum":600,"options":[]},
                {"key":"food_capacity","kind":"int","default":500,"minimum":10,"maximum":1000,"options":[]},
                {"key":"initial_materials","kind":"int","default":30,"minimum":0,"maximum":500,"options":[]},
                {"key":"material_capacity","kind":"int","default":400,"minimum":10,"maximum":1000,"options":[]},
                {"key":"initial_gold","kind":"int","default":50,"minimum":0,"maximum":1000,"options":[]},
                {"key":"player_energy","kind":"int","default":100,"minimum":10,"maximum":300,"options":[]},
                {"key":"dialogue_bond","kind":"int","default":3,"minimum":1,"maximum":15,"options":[]},
                {"key":"help_food","kind":"int","default":2,"minimum":1,"maximum":20,"options":[]},
                {"key":"help_bond","kind":"int","default":5,"minimum":1,"maximum":20,"options":[]},
                {"key":"accusation_penalty","kind":"int","default":8,"minimum":1,"maximum":30,"options":[]},
                {"key":"trade_cost","kind":"int","default":3,"minimum":1,"maximum":30,"options":[]},
                {"key":"trade_food","kind":"int","default":4,"minimum":1,"maximum":20,"options":[]},
                {"key":"work_energy","kind":"int","default":5,"minimum":1,"maximum":30,"options":[]},
                {"key":"farm_yield","kind":"int","default":8,"minimum":1,"maximum":40,"options":[]},
                {"key":"work_yield","kind":"int","default":6,"minimum":1,"maximum":40,"options":[]},
                {"key":"donation_gold","kind":"int","default":4,"minimum":1,"maximum":30,"options":[]},
                {"key":"donation_trust","kind":"int","default":3,"minimum":1,"maximum":15,"options":[]},
                {"key":"mediation_trust","kind":"int","default":12,"minimum":1,"maximum":50,"options":[]},
                {"key":"checkpoint_trust","kind":"int","default":10,"minimum":1,"maximum":100,"options":[]},
                {"key":"checkpoint_food","kind":"int","default":10,"minimum":0,"maximum":100,"options":[]},
                {"key":"day_length","kind":"int","default":8,"minimum":4,"maximum":32,"options":[]},
                {"key":"coarse_period","kind":"int","default":4,"minimum":2,"maximum":16,"options":[]},
                {"key":"background_cohort","kind":"int","default":100,"minimum":10,"maximum":1000,"options":[]},
                {"key":"hunger_rate","kind":"int","default":1,"minimum":0,"maximum":10,"options":[]},
                {"key":"fatigue_rate","kind":"int","default":1,"minimum":0,"maximum":10,"options":[]},
                {"key":"meal_threshold","kind":"int","default":20,"minimum":5,"maximum":80,"options":[]},
                {"key":"meal_relief","kind":"int","default":15,"minimum":1,"maximum":80,"options":[]},
                {"key":"rest_relief","kind":"int","default":4,"minimum":1,"maximum":30,"options":[]},
                {"key":"focus_radius","kind":"int","default":2,"minimum":1,"maximum":8,"options":[]},
                {"key":"scarcity_unrest","kind":"int","default":3,"minimum":1,"maximum":30,"options":[]},
                {"key":"rest_energy","kind":"int","default":15,"minimum":1,"maximum":60,"options":[]},
                {"key":"turn_limit","kind":"int","default":128,"minimum":32,"maximum":128,"options":[]},
            ],
            "ecosystem":[
                {"key":"initial_population","kind":"int","default":5,"minimum":1,"maximum":40,"options":[]},
                {"key":"carrying_capacity","kind":"int","default":50,"minimum":5,"maximum":1000,"options":[]},
                {"key":"seed_bank","kind":"int","default":25,"minimum":0,"maximum":300,"options":[]},
                {"key":"starting_water","kind":"int","default":20,"minimum":0,"maximum":200,"options":[]},
                {"key":"medicine","kind":"int","default":4,"minimum":0,"maximum":100,"options":[]},
                {"key":"credits","kind":"int","default":40,"minimum":0,"maximum":1000,"options":[]},
                {"key":"food_regrowth","kind":"int","default":5,"minimum":0,"maximum":40,"options":[]},
                {"key":"drought_threshold","kind":"int","default":25,"minimum":2,"maximum":80,"options":[]},
                {"key":"evaporation","kind":"int","default":1,"minimum":0,"maximum":10,"options":[]},
                {"key":"individuals_per_food","kind":"int","default":8,"minimum":1,"maximum":100,"options":[]},
                {"key":"reproduction_period","kind":"int","default":4,"minimum":1,"maximum":20,"options":[]},
                {"key":"hunt_period","kind":"int","default":5,"minimum":1,"maximum":30,"options":[]},
                {"key":"predation_rate","kind":"int","default":1,"minimum":1,"maximum":12,"options":[]},
                {"key":"disease_resistance","kind":"int","default":10,"minimum":1,"maximum":100,"options":[]},
                {"key":"migration_period","kind":"int","default":5,"minimum":2,"maximum":30,"options":[]},
                {"key":"observation_budget","kind":"int","default":40,"minimum":1,"maximum":128,"options":[]},
                {"key":"seed_cost","kind":"int","default":2,"minimum":1,"maximum":20,"options":[]},
                {"key":"plant_food","kind":"int","default":12,"minimum":1,"maximum":100,"options":[]},
                {"key":"water_cost","kind":"int","default":1,"minimum":1,"maximum":20,"options":[]},
                {"key":"watering_gain","kind":"int","default":15,"minimum":1,"maximum":50,"options":[]},
                {"key":"restoration_cost","kind":"int","default":5,"minimum":1,"maximum":40,"options":[]},
                {"key":"restoration_heal","kind":"int","default":15,"minimum":1,"maximum":60,"options":[]},
                {"key":"protection_cost","kind":"int","default":3,"minimum":1,"maximum":30,"options":[]},
                {"key":"protection_ticks","kind":"int","default":6,"minimum":1,"maximum":32,"options":[]},
                {"key":"treatment_strength","kind":"int","default":10,"minimum":1,"maximum":100,"options":[]},
                {"key":"corridor_cost","kind":"int","default":5,"minimum":1,"maximum":50,"options":[]},
                {"key":"feed_cost","kind":"int","default":2,"minimum":1,"maximum":20,"options":[]},
                {"key":"feed_units","kind":"int","default":10,"minimum":1,"maximum":100,"options":[]},
                {"key":"reintroduction_food","kind":"int","default":5,"minimum":1,"maximum":40,"options":[]},
                {"key":"reintroduction_cost","kind":"int","default":8,"minimum":1,"maximum":100,"options":[]},
                {"key":"reintroduction_population","kind":"int","default":3,"minimum":1,"maximum":50,"options":[]},
                {"key":"minimum_interventions","kind":"int","default":1,"minimum":1,"maximum":8,"options":[]},
                {"key":"minimum_living_population","kind":"int","default":5,"minimum":1,"maximum":500,"options":[]},
                {"key":"outbreak_period","kind":"int","default":12,"minimum":2,"maximum":40,"options":[]},
                {"key":"infection_rate","kind":"int","default":8,"minimum":1,"maximum":30,"options":[]},
                {"key":"protection_strength","kind":"int","default":1,"minimum":1,"maximum":12,"options":[]},
                {"key":"cohort_period","kind":"int","default":8,"minimum":2,"maximum":32,"options":[]},
                {"key":"cohort_food_divisor","kind":"int","default":80,"minimum":10,"maximum":500,"options":[]},
                {"key":"turn_limit","kind":"int","default":128,"minimum":32,"maximum":128,"options":[]},
                {"key":"natural_corridors","kind":"bool","default":True,"minimum":None,"maximum":None,"options":[]},
            ],
        }[_entry["id"]]
        _entry["fields"].extend(_extension)
# Source-grounded economic simulation controls: no monetary or stock minting.
for _entry in CATALOG:
    if _entry["id"] == "economy":
        _entry["fields"].extend([
            {"key": key, "kind": "int", "default": default,
             "minimum": lo, "maximum": hi, "options": []}
            for key, default, lo, hi in (
                ("active_goods_budget", 8, 3, 8),
                ("active_market_budget", 8, 2, 16),
                ("starting_stock", 8, 1, 64),
                ("warehouse_capacity", 96, 16, 256),
                ("resource_reserve", 40, 0, 200),
                ("household_cash", 250, 0, 2000),
                ("market_treasury", 400, 0, 2000),
                ("starting_cash", 220, 0, 2000),
                ("player_energy", 80, 10, 200),
                ("labor_cost", 6, 1, 30),
                ("harvest_yield", 4, 1, 20),
                ("ore_per_tool", 2, 1, 8),
                ("cargo_capacity", 16, 1, 40),
                ("transport_cost", 2, 0, 20),
                ("rest_cost", 3, 1, 20),
                ("rest_gain", 25, 1, 80),
                ("relief_grant", 10, 1, 40),
                ("spread", 2, 1, 10),
                ("base_price", 9, 1, 60),
                ("price_floor", 1, 1, 20),
                ("price_ceiling", 80, 20, 150),
                ("target_stock", 10, 1, 100),
                ("demand_period", 2, 1, 20),
            )
        ])

MINIMUM_PROGRESSION = "advanced"
ADVANCED_ENGINE_IDS = frozenset({"platformer", "tactics", "tower_defense", "racing", "survival", "shooter", "deck_battler", "puzzle", "farming", "factory", "colony", "city_builder", "stealth", "metroidvania", "sandbox", "roguelike", "rts", "rhythm", "fighting", "quest_director", "flight", "sailing", "parkour", "sports", "maze", "rpg", "procedural_world", "npc_society", "ecosystem", "economy"})
ADVANCED_REQUIREMENTS = {
    "World": ("persistent_state", "causal_events", "player_choice_consequences",
              "branch_or_nonterminal_world", "evidence_and_fidelity"),
    "Action": ("frame_bounded_input", "collision_resolution", "combat_or_traversal",
               "resource_and_damage_budget", "replay_evidence"),
    "Strategy": ("finite_resources", "adversarial_agent_turns", "spatial_constraints",
                 "meaningful_economy_or_supply", "deterministic_replay"),
    "Vehicle": ("physics_envelope", "environmental_response", "control_modes",
                "collision_and_safety", "replay_evidence"),
    "Simulation": ("conserved_resources", "time_evolution", "emergent_state",
                   "system_feedback", "deterministic_replay"),
    "Creative": ("authored_timing_or_branches", "stateful_player_interaction",
                 "bounded_complexity", "accessibility", "source_and_replay_provenance"),
    "Product": ("device_budget", "fault_tolerance", "user_accessibility",
                "internationalization", "independent_release_assurance"),
}
for _editor in CATALOG:
    _editor["progression_floor"] = MINIMUM_PROGRESSION
    _editor["advanced_contract"] = list(ADVANCED_REQUIREMENTS[_editor["group"]])
    _editor["runtime_maturity"] = (
        "advanced_reference_runtime" if _editor["id"] in ADVANCED_ENGINE_IDS
        else "authoring_only"
    )
INDEX = {entry["id"]: entry for entry in CATALOG}
PREVIEW_ACTIONS = {
    "platformer": ("right", "right", "jump", "right", "right", "idle", "idle"),
    "racing": ("accelerate", "accelerate", "accelerate", "coast", "brake", "accelerate"),
    "tactics": ("east", "south", "attack", "end_turn", "east", "attack"),
    "tower_defense": ("build", "advance", "advance", "build", "advance", "advance"),
    "shooter": ("fire", "dodge", "fire", "reload", "fire", "fire"),
    "survival": ("gather_wood", "gather_food", "drink", "craft_fire", "rest"),
    "rhythm": (0, 25, -40, 180, 10),
    "deck_battler": ("strike", "block", "recharge", "strike", "strike"),
}
MAX_ACTIONS = 128

class SystemEditorError(ValueError):
    """An invalid, unsupported or unsafe system-editor action."""

def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)

def catalog() -> list[dict[str, Any]]:
    """Stable serializable metadata for all exposed editor controls."""
    return json.loads(_canonical(CATALOG))

def editor_spec(editor_id: str) -> dict[str, Any]:
    if type(editor_id) is not str or editor_id not in INDEX:
        raise SystemEditorError("unknown original-game system editor")
    return json.loads(_canonical(INDEX[editor_id]))

def _normalized_settings(editor_id: str, values: Mapping[str, object] | None) -> dict[str, object]:
    spec = editor_spec(editor_id)
    if values is None:
        values = {}
    if type(values) is not dict:
        raise SystemEditorError("system settings must be a JSON object")
    fields = {field["key"]: field for field in spec["fields"]}
    if len(values) > len(fields) or set(values) - set(fields):
        raise SystemEditorError("unknown system setting; undeclared knobs fail closed")
    normalized = {}
    for key, field in fields.items():
        value = values.get(key, field["default"])
        kind = field["kind"]
        if kind == "int":
            if type(value) is not int or not field["minimum"] <= value <= field["maximum"]:
                raise SystemEditorError("out-of-range integer setting: " + key)
        elif kind == "bool":
            if type(value) is not bool:
                raise SystemEditorError("boolean setting required: " + key)
        elif kind == "enum":
            if type(value) is not str or value not in field["options"]:
                raise SystemEditorError("unsupported enumeration: " + key)
        elif kind == "text":
            if type(value) is not str or not 1 <= len(value) <= 160 or any(
                ord(char) < 32 for char in value
            ):
                raise SystemEditorError("invalid bounded text: " + key)
        else:
            raise SystemEditorError("unknown editor field kind")
        normalized[key] = value
    # Physical, social and gameplay cross-constraints are enforced before a
    # proposed source can be accepted or a preview executed.
    if editor_id == "npc_society" and normalized["active_npcs"] > normalized["population"]:
        raise SystemEditorError("active NPC budget cannot exceed population")
    if editor_id == "rhythm" and normalized["perfect_window_ms"] > normalized["hit_window_ms"]:
        raise SystemEditorError("perfect window must fit inside hit window")
    if editor_id == "tactics" and normalized["attack_range"] > max(
        normalized["board_width"], normalized["board_height"]
    ):
        raise SystemEditorError("tactics range exceeds available board dimensions")
    if editor_id == "npc_society":
        if normalized["active_npcs"]>normalized["population"]:
            raise SystemEditorError("active NPC budget cannot exceed authored population")
        if normalized["initial_food"]>normalized["food_capacity"]:
            raise SystemEditorError("initial society food exceeds actual town capacity")
        if normalized["initial_materials"]>normalized["material_capacity"]:
            raise SystemEditorError("initial society materials exceed storage")
        if normalized["work_energy"]>normalized["player_energy"]:
            raise SystemEditorError("source citizen cannot perform actual labor")
        if normalized["help_food"]>normalized["food_capacity"]:
            raise SystemEditorError("helping must consume bounded food")
        if normalized["checkpoint_food"]>normalized["food_capacity"]:
            raise SystemEditorError("civic checkpoint must be physically achievable")
        if normalized["memory_records"]==0 and normalized["relationship_factors"]>50:
            raise SystemEditorError("complex witness scoring requires nonzero memory records")
    if editor_id == "economy":
        if not normalized["finite_inventory"]:
            raise SystemEditorError("advanced source market requires finite physical stock")
        if normalized["goods"] < 3 or normalized["market_nodes"] < 2:
            raise SystemEditorError("real manufacturing and routed trade need three goods and two markets")
        if normalized["warehouse_capacity"] < normalized["starting_stock"] + 3:
            raise SystemEditorError("authored warehouse cannot store initial or harvested goods")
        if normalized["price_floor"] > normalized["base_price"] or normalized["base_price"] > normalized["price_ceiling"]:
            raise SystemEditorError("market price envelope must contain base price")
        if normalized["market_treasury"] < normalized["base_price"] + 16:
            raise SystemEditorError("market cannot pay actual cargo bids")
        if normalized["player_energy"] < normalized["labor_cost"]:
            raise SystemEditorError("labor cannot fund a real production action")
        if normalized["starting_cash"] < normalized["base_price"] + normalized["spread"] + normalized["transport_cost"]:
            raise SystemEditorError("player cannot fund any physical market exchange")
    if editor_id == "ecosystem":
        if normalized["predators"]>normalized["species"]:
            raise SystemEditorError("predator species cannot exceed authored species count")
        if normalized["initial_population"]>normalized["carrying_capacity"]:
            raise SystemEditorError("starting wildlife exceeds physical carrying capacity")
        if normalized["reintroduction_population"]>normalized["carrying_capacity"]:
            raise SystemEditorError("reintroduced wildlife cannot exceed habitat capacity")
        if normalized["minimum_living_population"]>normalized["species"]*normalized["carrying_capacity"]:
            raise SystemEditorError("target biodiversity exceeds aggregate species capacity")
        if normalized["seed_cost"]>normalized["seed_bank"] and normalized["minimum_interventions"]>0 and normalized["credits"]==0:
            raise SystemEditorError("ecosystem cannot fund an ecological intervention")
    if editor_id == "rpg":
        if normalized["max_obstacles"] >= normalized["world_width"]*normalized["world_height"]//3:
            raise SystemEditorError("original RPG obstacles cannot seal most of the world")
        if normalized["starting_herbs"] > normalized["herb_capacity"]:
            raise SystemEditorError("initial herbs exceed real storage")
        if normalized["spell_cost"] > normalized["hero_mana"]:
            raise SystemEditorError("no original party spell is financeable")
        if normalized["camp_healing"] > normalized["hero_health"]:
            raise SystemEditorError("camp recovery exceeds actual hero capacity")
        if normalized["level_heal"] > normalized["hero_health"]:
            raise SystemEditorError("RPG level recovery exceeds hero capacity")
        if normalized["quest_depth"] > normalized["turn_limit"]*2:
            raise SystemEditorError("authoring quest depth exceeds bounded replay complexity")
    if editor_id == "procedural_world":
        if normalized["shelter_wood"]>normalized["starting_wood"]+normalized["resource_density"]*10:
            raise SystemEditorError("original shelter cannot be constructed from local resources")
        if normalized["shelter_stone"]>normalized["starting_stone"]+normalized["resource_density"]*10:
            raise SystemEditorError("original shelter stone budget is unreachable")
        if normalized["tool_stone"]>normalized["starting_stone"]+normalized["resource_density"]*10:
            raise SystemEditorError("tool stone cannot be sourced from local biome")
        if normalized["world_radius_chunks"]*normalized["chunk_size"]<12:
            raise SystemEditorError("original world cannot fit source exploration landmarks")
    if editor_id == "maze":
        cells=(normalized["width"]-2)*(normalized["height"]-2)*normalized["levels"]
        minimum_reserved=3+normalized["levels"]+(2 if normalized["topology"]=="non_euclidean" else 0)
        if normalized["key_count"]+normalized["hazards"]+minimum_reserved>cells:
            raise SystemEditorError("maze objective and finite hazards exceed actual cells")
        if normalized["topology"]=="non_euclidean" and normalized["height"]<6:
            raise SystemEditorError("non-Euclidean portals require separate spatial cells")
        if normalized["stair_cost"]>normalized["stamina"]:
            raise SystemEditorError("maze staircase beyond original stamina budget")
        if normalized["portal_cost"]>normalized["stamina"]:
            raise SystemEditorError("authored portal cannot be paid for")
        if normalized["move_cost"]>normalized["stamina"]:
            raise SystemEditorError("original walker cannot perform a legal move")
    if editor_id == "sports":
        if normalized["sprint_speed"] < normalized["run_speed"]:
            raise SystemEditorError("sports sprint cannot be slower than normal movement")
        if normalized["pass_distance"] >= normalized["field_length"]:
            raise SystemEditorError("a sports pass cannot exceed original stadium width")
        if normalized["rain_stride_penalty"] >= normalized["run_speed"]:
            raise SystemEditorError("rain cannot eliminate all active athletic movement")
        if normalized["shot_range"] >= normalized["field_length"]:
            raise SystemEditorError("original sports shots cannot span the entire field")
        if normalized["substitutions"] > normalized["team_size"]:
            raise SystemEditorError("substitution budget cannot exceed roster")
        if normalized["rules"]=="racket" and normalized["team_size"]>4:
            raise SystemEditorError("racket sports require original singles or doubles roster")
        if normalized["rules"]=="turn_based" and normalized["action_points"]>normalized["match_turn_limit"]:
            raise SystemEditorError("tactical action budget exceeds match")
    if editor_id == "parkour":
        if normalized["max_stride"]>normalized["course_length"]//5:
            raise SystemEditorError("parkour strides cannot leap the entire route")
        if normalized["sprint_cost"]>normalized["stamina"]:
            raise SystemEditorError("starting stamina cannot fund a sprint")
        if normalized["jump_cost"]>normalized["stamina"]:
            raise SystemEditorError("starting stamina cannot fund a jump")
        if normalized["grapple_charges"]>0 and normalized["grapple_reach"]==0:
            raise SystemEditorError("grapple ammunition requires reachable surfaces")
        if normalized["medals_required"]>normalized["course_length"]//6:
            raise SystemEditorError("medal schedule exceeds spatial route")
    if editor_id == "sailing":
        if normalized["cargo_contract"] > normalized["cargo_capacity"]:
            raise SystemEditorError("cargo delivery cannot exceed vessel hold capacity")
        if normalized["harbor_length"] > normalized["route_length"] // 3:
            raise SystemEditorError("harbor consumes essential navigation route")
        if normalized["launch_speed"] > normalized["max_speed"]:
            raise SystemEditorError("initial vessel velocity exceeds safe hull speed")
        if normalized["safe_dock_speed"] > normalized["max_speed"]:
            raise SystemEditorError("dock limit outside vessel velocity envelope")
    if editor_id == "flight":
        if normalized["stall_speed"] > normalized["engine_thrust"]:
            raise SystemEditorError("stall speed exceeds configured thrust envelope")
        if normalized["runway_length"] > normalized["route_length"] // 3:
            raise SystemEditorError("runway exceeds bounded route navigation budget")
        if not normalized["waypoint_floor"] < normalized["waypoint_ceiling"] <= normalized["max_altitude"]:
            raise SystemEditorError("navigation window outside physical ceiling")
        if normalized["launch_altitude"] >= normalized["max_altitude"]:
            raise SystemEditorError("launch altitude exceeds ceiling")
        if normalized["landing_speed"] < normalized["stall_speed"]:
            raise SystemEditorError("landing speed below stall threshold")
        if normalized["landing_altitude"] >= normalized["max_altitude"]:
            raise SystemEditorError("landing approach outside physical ceiling")
        if normalized["landing_fuel_reserve"] > normalized["fuel_capacity"]:
            raise SystemEditorError("impossible landing fuel reserve")

    if editor_id == "platform_profile" and normalized["npc_active_budget"] * 1 > normalized["ram_budget_mb"] * 20:
        raise SystemEditorError("active NPCs exceed requested conservative memory envelope")
    if editor_id == "colony" and normalized["settlers"] > normalized["jobs"] * 30:
        raise SystemEditorError("colony has no workable staffing capacity")
    return normalized

def make_editor_document(editor_id: str, settings: Mapping[str, object] | None = None) -> dict:
    values = _normalized_settings(editor_id, settings)
    payload = {"schema": SCHEMA, "editor": editor_id, "settings": values}
    return {**payload, "digest": sha256(_canonical(payload).encode()).hexdigest()}

def validate_editor_document(document: object) -> dict:
    if type(document) is not dict or set(document) != {"schema", "editor", "settings", "digest"}:
        raise SystemEditorError("exact typed editor document required")
    if document.get("schema") != SCHEMA or type(document.get("digest")) is not str:
        raise SystemEditorError("editor schema or source checksum mismatch")
    expected = make_editor_document(document["editor"], document["settings"])
    if document != expected:
        raise SystemEditorError("editor document differs from normalized, reviewed settings")
    return expected

def _simulate(editor_id: str, cfg: Mapping[str, object], actions: Sequence[object]) -> dict:
    if editor_id == "platformer":
        x = 0; y = 0; vy = 0; jumps = 0
        trajectory = []
        for action in actions:
            if action not in {"left", "right", "jump", "idle"}:
                raise SystemEditorError("invalid platformer action")
            if action == "jump" and (y == 0 or (cfg["double_jump"] and jumps < 2)):
                vy = cfg["jump_impulse"]; jumps += 1
            x = max(0, min(cfg["level_width"] - 1, x + (
                cfg["run_speed"] if action == "right" else
                -cfg["run_speed"] if action == "left" else 0
            )))
            y += vy
            vy -= cfg["gravity"]
            if y <= 0:
                y = 0; vy = 0; jumps = 0
            trajectory.append({"x": x, "y": y})
        return {"x": x, "y": y, "grounded": y == 0, "trajectory": trajectory}
    if editor_id == "racing":
        speed = 0; distance = 0; history = []
        for action in actions:
            if action not in {"accelerate", "brake", "coast"}:
                raise SystemEditorError("invalid racing action")
            if action == "accelerate":
                speed = min(cfg["max_speed"], speed + cfg["acceleration"])
            elif action == "brake":
                speed = max(0, speed - cfg["brake_force"])
            else:
                speed = max(0, speed - 1)
            distance = min(cfg["track_length"] * cfg["laps"], distance + speed)
            history.append({"speed": speed, "total_distance": distance})
        return {"laps_completed": distance // cfg["track_length"],
                "finished": distance >= cfg["track_length"] * cfg["laps"],
                "distance": distance, "speed": speed, "telemetry": history}
    if editor_id == "tactics":
        x = 0; y = 0; ap = cfg["action_points"]
        enemy = [cfg["board_width"] - 1, cfg["board_height"] - 1]
        hp = cfg["unit_health"]; enemy_hp = cfg["unit_health"]; attacks = 0
        for action in actions:
            if action == "end_turn":
                ap = cfg["action_points"]
            elif action in {"north", "south", "east", "west"}:
                if ap:
                    dx, dy = {"north": (0,-1),"south": (0,1),
                              "east": (1,0),"west": (-1,0)}[action]
                    target_x = max(0,min(cfg["board_width"] - 1,x+dx))
                    target_y = max(0,min(cfg["board_height"] - 1,y+dy))
                    if (target_x,target_y) != (x,y):
                        x,y = target_x,target_y; ap -= 1
            elif action == "attack":
                if ap and abs(x-enemy[0])+abs(y-enemy[1]) <= cfg["attack_range"] and enemy_hp:
                    enemy_hp = max(0, enemy_hp - 3); ap -= 1; attacks += 1
            else:
                raise SystemEditorError("invalid tactics command")
        return {"unit": [x,y], "ap_remaining": ap, "unit_hp": hp,
                "enemy_hp": enemy_hp, "attacks": attacks}
    if editor_id == "tower_defense":
        credits = cfg["starting_credits"]; built = 0; tick = 0
        enemies = []; killed = 0; escaped = 0; spawned = 0
        for action in actions:
            if action == "build":
                if credits >= 20:
                    credits -= 20; built += 1
            elif action == "advance":
                tick += 1
                if spawned < cfg["wave_size"]:
                    enemies.append([0, 3]); spawned += 1
                for enemy in enemies:
                    enemy[0] += 1
                for _ in range(built):
                    choices = [enemy for enemy in enemies if 0 < enemy[0] <= cfg["tower_range"]]
                    if choices:
                        choices[0][1] -= cfg["tower_damage"]
                survivors = []
                for enemy in enemies:
                    if enemy[1] <= 0:
                        killed += 1; credits += 5
                    elif enemy[0] >= cfg["lane_length"]:
                        escaped += 1
                    else:
                        survivors.append(enemy)
                enemies = survivors
            else:
                raise SystemEditorError("invalid tower defense action")
        return {"credits": credits, "towers": built, "enemies_active": len(enemies),
                "spawned": spawned, "killed": killed, "escaped": escaped, "ticks": tick}
    if editor_id == "shooter":
        hp = cfg["player_health"]; enemy_hp = [3] * cfg["enemy_count"]
        ammo = cfg["ammo"]; dodges = cfg["dodge_charges"]; defeats = 0
        for action in actions:
            if action == "fire":
                if ammo:
                    ammo -= 1
                    if enemy_hp:
                        enemy_hp[0] -= cfg["weapon_damage"]
                        if enemy_hp[0] <= 0:
                            enemy_hp.pop(0); defeats += 1
            elif action == "reload":
                ammo = cfg["ammo"]
            elif action == "dodge":
                if dodges: dodges -= 1
                elif enemy_hp: hp = max(0,hp - 1)
            elif action == "wait":
                if enemy_hp: hp = max(0,hp - 1)
            else:
                raise SystemEditorError("invalid shooter action")
        return {"health": hp, "ammo": ammo, "enemies_remaining": len(enemy_hp),
                "defeated": defeats, "dodges_left": dodges}
    if editor_id == "survival":
        health = cfg["max_health"]; food = cfg["starting_food"]
        water = cfg["starting_water"]; wood = cfg["initial_wood"]; fires = 0
        for action in actions:
            if action == "gather_wood": wood += 2
            elif action == "gather_food": food += 2
            elif action == "drink": water += 3
            elif action == "craft_fire":
                if wood >= 3: wood -= 3; fires += 1
            elif action == "rest": health = min(cfg["max_health"],health + fires + 1)
            else: raise SystemEditorError("invalid survival action")
            if food: food -= 1
            if water: water -= 1
            if not food or not water: health = max(0,health - cfg["hunger_rate"])
        return {"health":health,"food":food,"water":water,"wood":wood,"campfires":fires}
    if editor_id == "rhythm":
        points = 0; combo = 0; peak = 0; misses = 0
        beats = 0
        for offset in actions:
            if type(offset) is not int or not -2000 <= offset <= 2000:
                raise SystemEditorError("rhythm timing offsets must be bounded integer milliseconds")
            if beats >= cfg["beat_count"]: break
            beats += 1
            if abs(offset) <= cfg["perfect_window_ms"]:
                points += 100 + combo * 10; combo += 1
            elif abs(offset) <= cfg["hit_window_ms"]:
                points += 50 + combo * 5; combo += 1
            else:
                points = max(0, points - cfg["miss_penalty"]); misses += 1; combo = 0
            peak = max(peak, combo)
        return {"score":points,"max_combo":peak,"misses":misses,
                "beats_attempted":beats, "beat_period_ms":60000 // cfg["bpm"]}
    if editor_id == "deck_battler":
        hp = cfg["starting_health"]; foe = cfg["enemy_health"]
        energy = cfg["energy_per_turn"]; block = 0; turns = 1
        for action in actions:
            if action == "recharge":
                energy = cfg["energy_per_turn"]; turns += 1
                hp = max(0,hp - max(0,3-block)); block = 0
            elif action == "strike":
                if energy and foe:
                    energy -= 1; foe = max(0,foe - cfg["attack_damage"])
            elif action == "block":
                if energy:
                    energy -= 1; block += cfg["block_value"]
            elif action == "wait": pass
            else: raise SystemEditorError("invalid deck-battler command")
        return {"player_health":hp,"enemy_health":foe,"energy":energy,
                "block":block,"turns":turns,"victory":foe==0}
    raise SystemEditorError("runtime prototype not available for this editor")

def preview_editor(editor_id: str, settings: Mapping[str, object] | None = None,
                   actions: Sequence[object] | None = None) -> dict:
    document = make_editor_document(editor_id, settings)
    if editor_id not in PREVIEW_ACTIONS:
        return {"schema":"skeleton.game_builder.system_preview.v1",
                "editor":editor_id,"configuration_digest":document["digest"],
                "status":"authoring_only","simulation_executed":False}
    if actions is None:
        actions = PREVIEW_ACTIONS[editor_id]
    if type(actions) not in (list,tuple) or len(actions) > MAX_ACTIONS:
        raise SystemEditorError("preview actions must be a bounded sequence")
    state = _simulate(editor_id, document["settings"], actions)
    payload = {"schema":"skeleton.game_builder.system_preview.v1",
               "editor":editor_id,"configuration_digest":document["digest"],
               "actions":list(actions),"state":state,
               "status":"deterministic_prototype","simulation_executed":True}
    return {**payload,"digest":sha256(_canonical(payload).encode()).hexdigest()}

def editor_path(editor_id: str) -> str:
    editor_spec(editor_id)
    return "systems/" + editor_id + ".json"

def editor_source(editor_id: str, settings: Mapping[str, object] | None = None) -> str:
    return _canonical(make_editor_document(editor_id,settings)) + "\n"

__all__ = ["SCHEMA","CATALOG","MINIMUM_PROGRESSION","ADVANCED_ENGINE_IDS",
           "ADVANCED_REQUIREMENTS","SystemEditorError","catalog","editor_spec",
           "editor_path","editor_source","make_editor_document",
           "validate_editor_document","preview_editor"]
