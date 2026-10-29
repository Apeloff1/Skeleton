"""Quest graph 007.
"""
from __future__ import annotations

QUEST = "quest_007"

def graph() -> dict:
    nodes = ["start", "mid", "choice", "end"]
    edges = [["start", "mid"], ["mid", "choice"], ["choice", "end"]]
    return {"id": QUEST, "nodes": nodes, "edges": edges, "reward": "rare" if 7 % 3 == 0 else "common"}
