"""Computer-science learning pathways mined from Tutolage's CS engine."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

class CSFamily(str, Enum):
    DATA_STRUCTURES="data_structures"; ALGORITHMS="algorithms"; SYSTEMS="systems"; GRAPHICS="graphics"; AI="ai_ml"; NETWORKING="networking"; ARCHITECTURE="architecture"

@dataclass(frozen=True)
class CSPathway:
    pathway_id: str; family: CSFamily; concept: str; prerequisites: tuple[str, ...]; implementation: str; applications: tuple[str, ...]; transfer_question: str

PATHWAYS: tuple[CSPathway, ...] = (
    CSPathway("arrays_to_pools",CSFamily.DATA_STRUCTURES,"arrays and lists",(),"Implement a dynamic array or object pool",("entity storage","command buffers"),"When does contiguous storage improve a real system?"),
    CSPathway("graphs",CSFamily.DATA_STRUCTURES,"graphs",("arrays and lists",),"Implement adjacency lists and a graph traversal",("dependency planning","navigation"),"What representation makes the graph's structure easiest to reason about?"),
    CSPathway("trees_to_spatial",CSFamily.DATA_STRUCTURES,"trees and spatial structures",("arrays and lists",),"Implement a quadtree or BVH",("collision detection","spatial queries"),"How does spatial partitioning change the search work?"),
    CSPathway("graphs_to_pathfinding",CSFamily.ALGORITHMS,"graph traversal and shortest paths",("graphs",),"Implement BFS, Dijkstra, or A*",("navigation","dependency planning"),"Which graph assumptions make one pathfinding strategy preferable?"),
    CSPathway("dp_to_optimization",CSFamily.ALGORITHMS,"dynamic programming",("graph traversal and shortest paths",),"Implement a memoized and tabulated solution",("resource planning","sequence optimization"),"What repeated subproblem justifies storing state?"),
    CSPathway("memory_to_cache",CSFamily.SYSTEMS,"memory layout and cache behavior",("arrays and lists",),"Build a small benchmark comparing layouts",("frame processing","object pools"),"What evidence shows that layout, rather than algorithm choice, is the bottleneck?"),
    CSPathway("concurrency_to_jobs",CSFamily.SYSTEMS,"concurrency and task systems",("memory layout and cache behavior",),"Implement a bounded worker or job queue",("asset loading","parallel simulation"),"Which work can safely run concurrently and what synchronization is required?"),
    CSPathway("rendering_to_shaders",CSFamily.GRAPHICS,"rendering pipeline",("memory layout and cache behavior",),"Implement a minimal rendering stage or shader",("materials","post-processing"),"Which pipeline stage owns the visual effect and why?"),
    CSPathway("game_ai_to_agents",CSFamily.AI,"behavior trees and utility AI",("graph traversal and shortest paths",),"Implement a small decision agent",("NPC behavior","dynamic difficulty"),"How does the agent choose between competing goals?"),
    CSPathway("networking_to_sync",CSFamily.NETWORKING,"state synchronization",("concurrency and task systems",),"Implement a snapshot or reliability layer",("multiplayer state","prediction"),"Which state must be authoritative and which can be predicted?"),
    CSPathway("ecs_to_architecture",CSFamily.ARCHITECTURE,"entity-component architecture",("arrays and lists","concurrency and task systems"),"Implement a minimal ECS and scheduler",("game engine architecture","parallel systems"),"How does data ownership affect system scheduling and extensibility?"),
)

_BY_ID = {path.pathway_id: path for path in PATHWAYS}
_BY_CONCEPT = {path.concept: path.pathway_id for path in PATHWAYS}


def pathways_for(*, family: CSFamily | None = None, concept: str | None = None) -> tuple[CSPathway, ...]:
    concept_key = concept.lower().strip() if concept else None
    return tuple(path for path in PATHWAYS if (family is None or path.family == family) and (concept_key is None or concept_key in path.concept.lower()))


def _normalize_completed(completed: Sequence[str]) -> set[str]:
    """Accept pathway ids or exact concept names without mixing namespaces."""
    result: set[str] = set()
    for item in completed:
        key = str(item).strip().lower()
        if key in _BY_ID:
            result.add(key)
            continue
        for concept, pathway_id in _BY_CONCEPT.items():
            if concept.lower() == key:
                result.add(pathway_id)
                break
    return result


def next_pathway(completed: Sequence[str], *, interests: Sequence[str] = ()) -> CSPathway | None:
    done = _normalize_completed(completed)
    interest = {item.lower() for item in interests}
    ready = [
        path for path in PATHWAYS
        if path.pathway_id not in done
        and all(_BY_CONCEPT.get(req, req) in done for req in path.prerequisites)
    ]
    if not ready:
        return None
    return sorted(ready, key=lambda path: (
        -sum(1 for item in interest if item in path.concept.lower() or any(item in app.lower() for app in path.applications)),
        len(path.prerequisites), path.pathway_id,
    ))[0]
