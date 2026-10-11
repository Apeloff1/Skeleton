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
MINIMUM_PROGRESSION = "advanced"
ADVANCED_ENGINE_IDS = frozenset({"platformer", "tactics", "tower_defense"})
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
    if editor_id == "flight" and normalized["stall_speed"] > normalized["engine_thrust"]:
        raise SystemEditorError("stall speed exceeds configured thrust envelope")
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
