"""Quest graph 022.
"""
from __future__ import annotations

QUEST = "quest_022"

def graph() -> dict:
    nodes = ["start", "mid", "choice", "end"]
    edges = [["start", "mid"], ["mid", "choice"], ["choice", "end"]]
    return {"id": QUEST, "nodes": nodes, "edges": edges, "reward": "rare" if 22 % 3 == 0 else "common"}
