"""Static playability analysis for source-bound original world manifests."""
from ..contracts.spec import World
from ..contracts.errors import ContractError

def adjacency(world: World) -> dict[str, list[str]]:
    return {sid: sorted({ch.destination for ch in scene.choices}) for sid, scene in world.scenes.items()}

def structural_reachability(world: World) -> dict:
    graph = adjacency(world)
    pending = [world.start]
    seen = {world.start}
    while pending:
        for dest in graph[pending.pop()]:
            if dest not in seen:
                seen.add(dest)
                pending.append(dest)
    return {'reachable': sorted(seen), 'unreachable': sorted(set(world.scenes) - seen), 'endings_reachable': sorted(set(world.endings) & seen), 'dangling': []}

def validate_playable(world: World) -> bool:
    report = structural_reachability(world)
    if report['unreachable'] or not report['endings_reachable']:
        raise ContractError('unreachable content or endings')
    return True
