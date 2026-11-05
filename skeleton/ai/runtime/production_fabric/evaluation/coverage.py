"""Trace-backed scene and branch coverage distinct from existence of source files."""
from ..contracts.spec import World
from ..contracts.errors import ContractError

def report(world: World, traces: list[dict]) -> dict:
    visited = set()
    used = set()
    if not isinstance(traces, list) or len(traces) > 100000:
        raise ContractError('trace volume exceeded')
    for item in traces:
        if not isinstance(item, dict) or item.get('scene') not in world.scenes:
            raise ContractError('unrecognized trace scene')
        visited.add(item['scene'])
        if item.get('choice') is not None:
            used.add(item['choice'])
    all_choices = {c.id for scene in world.scenes.values() for c in scene.choices}
    if not used.issubset(all_choices):
        raise ContractError('unrecognized trace choice')
    return {'visited': len(visited), 'total_scenes': len(world.scenes), 'scene_coverage': round(len(visited) / len(world.scenes), 6), 'choice_coverage': round(len(used) / max(1, len(all_choices)), 6), 'missing_scenes': sorted(set(world.scenes) - visited)}
