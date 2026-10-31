"""Quest graph 008.
"""
from __future__ import annotations

QUEST = "quest_008"

def graph() -> dict:
    nodes = ["start", "mid", "choice", "end"]
    edges = [["start", "mid"], ["mid", "choice"], ["choice", "end"]]
    return {"id": QUEST, "nodes": nodes, "edges": edges, "reward": "rare" if 8 % 3 == 0 else "common"}
