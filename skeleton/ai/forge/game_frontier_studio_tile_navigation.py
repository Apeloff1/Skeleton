"""Turn authored tile corridors into real traversable expedition graph edges.

The existing ExpeditionWorld movement and save systems remain authoritative.
This bridge only adds walkable tile connections from Forge Studio source; it
never teleports to a missing cell or treats obstacle/water tiles as free paths.
"""
from __future__ import annotations

from collections import deque
import math

from .game_frontier_studio import StudioProject, StudioError
from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionWorld, ExpeditionError, TravelEdge, Waypoint,
)

_MAX_TILES=512
_PASSABLE=("floor","ground","road","path","grass","dirt","sand","bridge",
           "stone","soil","cobble","trail","tile")
_BLOCKED=("wall","water","lava","ocean","sea","cliff","void","block",
          "hazard","deep","river","lake","pit")


def _traversable(layer, x:int, y:int) -> bool:
    value=layer.data[y*layer.width+x]
    if value<0 or value>=len(layer.palette):
        return False
    surface=layer.palette[value].lower().replace("-","_")
    if any(word in surface for word in _BLOCKED):
        return False
    return any(word in surface for word in _PASSABLE)


def add_studio_walkable_paths(project: StudioProject,
                               world: ExpeditionWorld) -> ExpeditionWorld:
    """Add up to 512 reachable, adjacent source tiles as true walk connections.

    Only the first, terrain-bearing layer contributes collision-neutral travel
    paths. Traversal follows four-neighbour adjacency, not visual diagonals.
    Environmental physics and native navigation approval stay separate.
    """
    if not isinstance(project,StudioProject) or not isinstance(world,ExpeditionWorld):
        raise StudioError("native navigation requires typed Forge Studio and expedition source")
    if project.project_id != world.project_id:
        raise StudioError("authoring realm does not belong to the original game")
    ground=project.layers[0]
    passable={(x,y) for y in range(ground.height) for x in range(ground.width)
              if _traversable(ground,x,y)}
    if not passable:
        return world
    # Choose the nearest actual tile to the expedition arrival; no new root.
    origin=world.by_id[world.arrival]
    start=min(passable,key=lambda pt:(
        (pt[0]-origin.x_m)**2+(pt[1]-origin.y_m)**2,
        pt[1],pt[0]))
    queue=deque([start])
    visited={start}
    cells=[]
    while queue and len(cells)<_MAX_TILES:
        cell=queue.popleft()
        cells.append(cell)
        x,y=cell
        for next_cell in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if next_cell in passable and next_cell not in visited:
                visited.add(next_cell)
                queue.append(next_cell)
    # This is one reachable connected component. Excluded tiles retain their
    # source geometry but cannot silently receive an inaccessible jump edge.
    selected=set(cells)
    altitude=float(ground.elevation_m)
    nodes=list(world.waypoints)
    edges=list(world.edges)
    def node_name(cell):
        return f"studio_tile_{cell[0]:03d}_{cell[1]:03d}"
    try:
        for x,y in cells:
            nodes.append(Waypoint(node_name((x,y)),float(x),float(y),
                                  altitude,"ground",
                                  landmark=f"Authored {ground.layer_id} tile {x},{y}",
                                  discovery_score=0))
        for x,y in cells:
            source=node_name((x,y))
            for neighbour in ((x+1,y),(x,y+1)):
                if neighbour not in selected:
                    continue
                # Shared edges have a real reverse route through
                # ExpeditionWorld.by_edge, not duplicate ownership.
                edges.append(TravelEdge(
                    f"studio_path_{x:03d}_{y:03d}_{neighbour[0]:03d}_{neighbour[1]:03d}",
                    source,node_name(neighbour),"walk",
                    length_m=1,duration_s=1,stamina_cost=0,
                    risk=0.,scenic_score=0,one_way=False))
        anchor=nodes[len(world.waypoints)]
        distance=math.dist((origin.x_m,origin.y_m,origin.altitude_m),
                           (anchor.x_m,anchor.y_m,anchor.altitude_m))
        # Distinct authored access edge uses a mode compatible with
        # crossing elevation, without inventing an unconnected warp.
        mode="walk" if abs(origin.altitude_m-altitude)<=6 else "climb"
        edges.append(TravelEdge(
            "studio_map_entry",world.arrival,anchor.waypoint_id,mode,
            length_m=max(.01,distance),
            duration_s=max(1.,distance/2),stamina_cost=1,
            risk=0.0,scenic_score=1,one_way=False))
        return ExpeditionWorld(
            world.project_id,world.source_digest,tuple(nodes),tuple(edges),
            world.arrival,world.destinations,world.weather)
    except ExpeditionError as exc:
        raise StudioError("authored tile path graph cannot enter original expedition") from exc
