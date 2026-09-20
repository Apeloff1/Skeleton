"""Depth matrix for hybrid neo/midbrain routing bands."""
from __future__ import annotations
from typing import Any, Mapping, Tuple

DEPTH_BANDS: Tuple[Mapping[str, Any], ...] = (
    {
        "band": 1,
        "neo_depth": 2,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0588,
        "label": "depth-band-001",
    },
    {
        "band": 2,
        "neo_depth": 3,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1176,
        "label": "depth-band-002",
    },
    {
        "band": 3,
        "neo_depth": 4,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1765,
        "label": "depth-band-003",
    },
    {
        "band": 4,
        "neo_depth": 5,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2353,
        "label": "depth-band-004",
    },
    {
        "band": 5,
        "neo_depth": 6,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2941,
        "label": "depth-band-005",
    },
    {
        "band": 6,
        "neo_depth": 7,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.3529,
        "label": "depth-band-006",
    },
    {
        "band": 7,
        "neo_depth": 8,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4118,
        "label": "depth-band-007",
    },
    {
        "band": 8,
        "neo_depth": 1,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4706,
        "label": "depth-band-008",
    },
    {
        "band": 9,
        "neo_depth": 2,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5294,
        "label": "depth-band-009",
    },
    {
        "band": 10,
        "neo_depth": 3,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5882,
        "label": "depth-band-010",
    },
    {
        "band": 11,
        "neo_depth": 4,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.6471,
        "label": "depth-band-011",
    },
    {
        "band": 12,
        "neo_depth": 5,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7059,
        "label": "depth-band-012",
    },
    {
        "band": 13,
        "neo_depth": 6,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7647,
        "label": "depth-band-013",
    },
    {
        "band": 14,
        "neo_depth": 7,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8235,
        "label": "depth-band-014",
    },
    {
        "band": 15,
        "neo_depth": 8,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8824,
        "label": "depth-band-015",
    },
    {
        "band": 16,
        "neo_depth": 1,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.9412,
        "label": "depth-band-016",
    },
    {
        "band": 17,
        "neo_depth": 2,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0,
        "label": "depth-band-017",
    },
    {
        "band": 18,
        "neo_depth": 3,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0588,
        "label": "depth-band-018",
    },
    {
        "band": 19,
        "neo_depth": 4,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1176,
        "label": "depth-band-019",
    },
    {
        "band": 20,
        "neo_depth": 5,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1765,
        "label": "depth-band-020",
    },
    {
        "band": 21,
        "neo_depth": 6,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2353,
        "label": "depth-band-021",
    },
    {
        "band": 22,
        "neo_depth": 7,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2941,
        "label": "depth-band-022",
    },
    {
        "band": 23,
        "neo_depth": 8,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.3529,
        "label": "depth-band-023",
    },
    {
        "band": 24,
        "neo_depth": 1,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4118,
        "label": "depth-band-024",
    },
    {
        "band": 25,
        "neo_depth": 2,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4706,
        "label": "depth-band-025",
    },
    {
        "band": 26,
        "neo_depth": 3,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5294,
        "label": "depth-band-026",
    },
    {
        "band": 27,
        "neo_depth": 4,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5882,
        "label": "depth-band-027",
    },
    {
        "band": 28,
        "neo_depth": 5,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.6471,
        "label": "depth-band-028",
    },
    {
        "band": 29,
        "neo_depth": 6,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7059,
        "label": "depth-band-029",
    },
    {
        "band": 30,
        "neo_depth": 7,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7647,
        "label": "depth-band-030",
    },
    {
        "band": 31,
        "neo_depth": 8,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8235,
        "label": "depth-band-031",
    },
    {
        "band": 32,
        "neo_depth": 1,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8824,
        "label": "depth-band-032",
    },
    {
        "band": 33,
        "neo_depth": 2,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.9412,
        "label": "depth-band-033",
    },
    {
        "band": 34,
        "neo_depth": 3,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0,
        "label": "depth-band-034",
    },
    {
        "band": 35,
        "neo_depth": 4,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0588,
        "label": "depth-band-035",
    },
    {
        "band": 36,
        "neo_depth": 5,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1176,
        "label": "depth-band-036",
    },
    {
        "band": 37,
        "neo_depth": 6,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1765,
        "label": "depth-band-037",
    },
    {
        "band": 38,
        "neo_depth": 7,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2353,
        "label": "depth-band-038",
    },
    {
        "band": 39,
        "neo_depth": 8,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2941,
        "label": "depth-band-039",
    },
    {
        "band": 40,
        "neo_depth": 1,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.3529,
        "label": "depth-band-040",
    },
    {
        "band": 41,
        "neo_depth": 2,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4118,
        "label": "depth-band-041",
    },
    {
        "band": 42,
        "neo_depth": 3,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4706,
        "label": "depth-band-042",
    },
    {
        "band": 43,
        "neo_depth": 4,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5294,
        "label": "depth-band-043",
    },
    {
        "band": 44,
        "neo_depth": 5,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5882,
        "label": "depth-band-044",
    },
    {
        "band": 45,
        "neo_depth": 6,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.6471,
        "label": "depth-band-045",
    },
    {
        "band": 46,
        "neo_depth": 7,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7059,
        "label": "depth-band-046",
    },
    {
        "band": 47,
        "neo_depth": 8,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7647,
        "label": "depth-band-047",
    },
    {
        "band": 48,
        "neo_depth": 1,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8235,
        "label": "depth-band-048",
    },
    {
        "band": 49,
        "neo_depth": 2,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8824,
        "label": "depth-band-049",
    },
    {
        "band": 50,
        "neo_depth": 3,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.9412,
        "label": "depth-band-050",
    },
    {
        "band": 51,
        "neo_depth": 4,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0,
        "label": "depth-band-051",
    },
    {
        "band": 52,
        "neo_depth": 5,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0588,
        "label": "depth-band-052",
    },
    {
        "band": 53,
        "neo_depth": 6,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1176,
        "label": "depth-band-053",
    },
    {
        "band": 54,
        "neo_depth": 7,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1765,
        "label": "depth-band-054",
    },
    {
        "band": 55,
        "neo_depth": 8,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2353,
        "label": "depth-band-055",
    },
    {
        "band": 56,
        "neo_depth": 1,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2941,
        "label": "depth-band-056",
    },
    {
        "band": 57,
        "neo_depth": 2,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.3529,
        "label": "depth-band-057",
    },
    {
        "band": 58,
        "neo_depth": 3,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4118,
        "label": "depth-band-058",
    },
    {
        "band": 59,
        "neo_depth": 4,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4706,
        "label": "depth-band-059",
    },
    {
        "band": 60,
        "neo_depth": 5,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5294,
        "label": "depth-band-060",
    },
    {
        "band": 61,
        "neo_depth": 6,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5882,
        "label": "depth-band-061",
    },
    {
        "band": 62,
        "neo_depth": 7,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.6471,
        "label": "depth-band-062",
    },
    {
        "band": 63,
        "neo_depth": 8,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7059,
        "label": "depth-band-063",
    },
    {
        "band": 64,
        "neo_depth": 1,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7647,
        "label": "depth-band-064",
    },
    {
        "band": 65,
        "neo_depth": 2,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8235,
        "label": "depth-band-065",
    },
    {
        "band": 66,
        "neo_depth": 3,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8824,
        "label": "depth-band-066",
    },
    {
        "band": 67,
        "neo_depth": 4,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.9412,
        "label": "depth-band-067",
    },
    {
        "band": 68,
        "neo_depth": 5,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0,
        "label": "depth-band-068",
    },
    {
        "band": 69,
        "neo_depth": 6,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0588,
        "label": "depth-band-069",
    },
    {
        "band": 70,
        "neo_depth": 7,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1176,
        "label": "depth-band-070",
    },
    {
        "band": 71,
        "neo_depth": 8,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1765,
        "label": "depth-band-071",
    },
    {
        "band": 72,
        "neo_depth": 1,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2353,
        "label": "depth-band-072",
    },
    {
        "band": 73,
        "neo_depth": 2,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2941,
        "label": "depth-band-073",
    },
    {
        "band": 74,
        "neo_depth": 3,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.3529,
        "label": "depth-band-074",
    },
    {
        "band": 75,
        "neo_depth": 4,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4118,
        "label": "depth-band-075",
    },
    {
        "band": 76,
        "neo_depth": 5,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4706,
        "label": "depth-band-076",
    },
    {
        "band": 77,
        "neo_depth": 6,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5294,
        "label": "depth-band-077",
    },
    {
        "band": 78,
        "neo_depth": 7,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5882,
        "label": "depth-band-078",
    },
    {
        "band": 79,
        "neo_depth": 8,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.6471,
        "label": "depth-band-079",
    },
    {
        "band": 80,
        "neo_depth": 1,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7059,
        "label": "depth-band-080",
    },
    {
        "band": 81,
        "neo_depth": 2,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7647,
        "label": "depth-band-081",
    },
    {
        "band": 82,
        "neo_depth": 3,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8235,
        "label": "depth-band-082",
    },
    {
        "band": 83,
        "neo_depth": 4,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8824,
        "label": "depth-band-083",
    },
    {
        "band": 84,
        "neo_depth": 5,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.9412,
        "label": "depth-band-084",
    },
    {
        "band": 85,
        "neo_depth": 6,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0,
        "label": "depth-band-085",
    },
    {
        "band": 86,
        "neo_depth": 7,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0588,
        "label": "depth-band-086",
    },
    {
        "band": 87,
        "neo_depth": 8,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1176,
        "label": "depth-band-087",
    },
    {
        "band": 88,
        "neo_depth": 1,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1765,
        "label": "depth-band-088",
    },
    {
        "band": 89,
        "neo_depth": 2,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2353,
        "label": "depth-band-089",
    },
    {
        "band": 90,
        "neo_depth": 3,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2941,
        "label": "depth-band-090",
    },
    {
        "band": 91,
        "neo_depth": 4,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.3529,
        "label": "depth-band-091",
    },
    {
        "band": 92,
        "neo_depth": 5,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4118,
        "label": "depth-band-092",
    },
    {
        "band": 93,
        "neo_depth": 6,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4706,
        "label": "depth-band-093",
    },
    {
        "band": 94,
        "neo_depth": 7,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5294,
        "label": "depth-band-094",
    },
    {
        "band": 95,
        "neo_depth": 8,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5882,
        "label": "depth-band-095",
    },
    {
        "band": 96,
        "neo_depth": 1,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.6471,
        "label": "depth-band-096",
    },
    {
        "band": 97,
        "neo_depth": 2,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7059,
        "label": "depth-band-097",
    },
    {
        "band": 98,
        "neo_depth": 3,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7647,
        "label": "depth-band-098",
    },
    {
        "band": 99,
        "neo_depth": 4,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8235,
        "label": "depth-band-099",
    },
    {
        "band": 100,
        "neo_depth": 5,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8824,
        "label": "depth-band-100",
    },
    {
        "band": 101,
        "neo_depth": 6,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.9412,
        "label": "depth-band-101",
    },
    {
        "band": 102,
        "neo_depth": 7,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0,
        "label": "depth-band-102",
    },
    {
        "band": 103,
        "neo_depth": 8,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0588,
        "label": "depth-band-103",
    },
    {
        "band": 104,
        "neo_depth": 1,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1176,
        "label": "depth-band-104",
    },
    {
        "band": 105,
        "neo_depth": 2,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1765,
        "label": "depth-band-105",
    },
    {
        "band": 106,
        "neo_depth": 3,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2353,
        "label": "depth-band-106",
    },
    {
        "band": 107,
        "neo_depth": 4,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2941,
        "label": "depth-band-107",
    },
    {
        "band": 108,
        "neo_depth": 5,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.3529,
        "label": "depth-band-108",
    },
    {
        "band": 109,
        "neo_depth": 6,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4118,
        "label": "depth-band-109",
    },
    {
        "band": 110,
        "neo_depth": 7,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4706,
        "label": "depth-band-110",
    },
    {
        "band": 111,
        "neo_depth": 8,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5294,
        "label": "depth-band-111",
    },
    {
        "band": 112,
        "neo_depth": 1,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5882,
        "label": "depth-band-112",
    },
    {
        "band": 113,
        "neo_depth": 2,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.6471,
        "label": "depth-band-113",
    },
    {
        "band": 114,
        "neo_depth": 3,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7059,
        "label": "depth-band-114",
    },
    {
        "band": 115,
        "neo_depth": 4,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7647,
        "label": "depth-band-115",
    },
    {
        "band": 116,
        "neo_depth": 5,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8235,
        "label": "depth-band-116",
    },
    {
        "band": 117,
        "neo_depth": 6,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8824,
        "label": "depth-band-117",
    },
    {
        "band": 118,
        "neo_depth": 7,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.9412,
        "label": "depth-band-118",
    },
    {
        "band": 119,
        "neo_depth": 8,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0,
        "label": "depth-band-119",
    },
    {
        "band": 120,
        "neo_depth": 1,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0588,
        "label": "depth-band-120",
    },
    {
        "band": 121,
        "neo_depth": 2,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1176,
        "label": "depth-band-121",
    },
    {
        "band": 122,
        "neo_depth": 3,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1765,
        "label": "depth-band-122",
    },
    {
        "band": 123,
        "neo_depth": 4,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2353,
        "label": "depth-band-123",
    },
    {
        "band": 124,
        "neo_depth": 5,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2941,
        "label": "depth-band-124",
    },
    {
        "band": 125,
        "neo_depth": 6,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.3529,
        "label": "depth-band-125",
    },
    {
        "band": 126,
        "neo_depth": 7,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4118,
        "label": "depth-band-126",
    },
    {
        "band": 127,
        "neo_depth": 8,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4706,
        "label": "depth-band-127",
    },
    {
        "band": 128,
        "neo_depth": 1,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5294,
        "label": "depth-band-128",
    },
    {
        "band": 129,
        "neo_depth": 2,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5882,
        "label": "depth-band-129",
    },
    {
        "band": 130,
        "neo_depth": 3,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.6471,
        "label": "depth-band-130",
    },
    {
        "band": 131,
        "neo_depth": 4,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7059,
        "label": "depth-band-131",
    },
    {
        "band": 132,
        "neo_depth": 5,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7647,
        "label": "depth-band-132",
    },
    {
        "band": 133,
        "neo_depth": 6,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8235,
        "label": "depth-band-133",
    },
    {
        "band": 134,
        "neo_depth": 7,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8824,
        "label": "depth-band-134",
    },
    {
        "band": 135,
        "neo_depth": 8,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.9412,
        "label": "depth-band-135",
    },
    {
        "band": 136,
        "neo_depth": 1,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0,
        "label": "depth-band-136",
    },
    {
        "band": 137,
        "neo_depth": 2,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0588,
        "label": "depth-band-137",
    },
    {
        "band": 138,
        "neo_depth": 3,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1176,
        "label": "depth-band-138",
    },
    {
        "band": 139,
        "neo_depth": 4,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1765,
        "label": "depth-band-139",
    },
    {
        "band": 140,
        "neo_depth": 5,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2353,
        "label": "depth-band-140",
    },
    {
        "band": 141,
        "neo_depth": 6,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2941,
        "label": "depth-band-141",
    },
    {
        "band": 142,
        "neo_depth": 7,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.3529,
        "label": "depth-band-142",
    },
    {
        "band": 143,
        "neo_depth": 8,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4118,
        "label": "depth-band-143",
    },
    {
        "band": 144,
        "neo_depth": 1,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4706,
        "label": "depth-band-144",
    },
    {
        "band": 145,
        "neo_depth": 2,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5294,
        "label": "depth-band-145",
    },
    {
        "band": 146,
        "neo_depth": 3,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5882,
        "label": "depth-band-146",
    },
    {
        "band": 147,
        "neo_depth": 4,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.6471,
        "label": "depth-band-147",
    },
    {
        "band": 148,
        "neo_depth": 5,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7059,
        "label": "depth-band-148",
    },
    {
        "band": 149,
        "neo_depth": 6,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7647,
        "label": "depth-band-149",
    },
    {
        "band": 150,
        "neo_depth": 7,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8235,
        "label": "depth-band-150",
    },
    {
        "band": 151,
        "neo_depth": 8,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8824,
        "label": "depth-band-151",
    },
    {
        "band": 152,
        "neo_depth": 1,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.9412,
        "label": "depth-band-152",
    },
    {
        "band": 153,
        "neo_depth": 2,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0,
        "label": "depth-band-153",
    },
    {
        "band": 154,
        "neo_depth": 3,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0588,
        "label": "depth-band-154",
    },
    {
        "band": 155,
        "neo_depth": 4,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1176,
        "label": "depth-band-155",
    },
    {
        "band": 156,
        "neo_depth": 5,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1765,
        "label": "depth-band-156",
    },
    {
        "band": 157,
        "neo_depth": 6,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2353,
        "label": "depth-band-157",
    },
    {
        "band": 158,
        "neo_depth": 7,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2941,
        "label": "depth-band-158",
    },
    {
        "band": 159,
        "neo_depth": 8,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.3529,
        "label": "depth-band-159",
    },
    {
        "band": 160,
        "neo_depth": 1,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4118,
        "label": "depth-band-160",
    },
    {
        "band": 161,
        "neo_depth": 2,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4706,
        "label": "depth-band-161",
    },
    {
        "band": 162,
        "neo_depth": 3,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5294,
        "label": "depth-band-162",
    },
    {
        "band": 163,
        "neo_depth": 4,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5882,
        "label": "depth-band-163",
    },
    {
        "band": 164,
        "neo_depth": 5,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.6471,
        "label": "depth-band-164",
    },
    {
        "band": 165,
        "neo_depth": 6,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7059,
        "label": "depth-band-165",
    },
    {
        "band": 166,
        "neo_depth": 7,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.7647,
        "label": "depth-band-166",
    },
    {
        "band": 167,
        "neo_depth": 8,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8235,
        "label": "depth-band-167",
    },
    {
        "band": 168,
        "neo_depth": 1,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.8824,
        "label": "depth-band-168",
    },
    {
        "band": 169,
        "neo_depth": 2,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.9412,
        "label": "depth-band-169",
    },
    {
        "band": 170,
        "neo_depth": 3,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0,
        "label": "depth-band-170",
    },
    {
        "band": 171,
        "neo_depth": 4,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.0588,
        "label": "depth-band-171",
    },
    {
        "band": 172,
        "neo_depth": 5,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1176,
        "label": "depth-band-172",
    },
    {
        "band": 173,
        "neo_depth": 6,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.1765,
        "label": "depth-band-173",
    },
    {
        "band": 174,
        "neo_depth": 7,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2353,
        "label": "depth-band-174",
    },
    {
        "band": 175,
        "neo_depth": 8,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.2941,
        "label": "depth-band-175",
    },
    {
        "band": 176,
        "neo_depth": 1,
        "mid_depth": 2,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.3529,
        "label": "depth-band-176",
    },
    {
        "band": 177,
        "neo_depth": 2,
        "mid_depth": 3,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4118,
        "label": "depth-band-177",
    },
    {
        "band": 178,
        "neo_depth": 3,
        "mid_depth": 4,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.4706,
        "label": "depth-band-178",
    },
    {
        "band": 179,
        "neo_depth": 4,
        "mid_depth": 5,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5294,
        "label": "depth-band-179",
    },
    {
        "band": 180,
        "neo_depth": 5,
        "mid_depth": 1,
        "pfc_depth": 0,  # small LM — no transformer depth
        "skip_ratio": 0.5882,
        "label": "depth-band-180",
    },
)

def pfc_depth_always_zero() -> bool:
    return all(int(b["pfc_depth"]) == 0 for b in DEPTH_BANDS)

def select_band(n: int) -> Mapping[str, Any]:
    return DEPTH_BANDS[(n - 1) % len(DEPTH_BANDS)]
