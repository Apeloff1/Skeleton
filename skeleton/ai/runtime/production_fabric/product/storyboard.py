"""Deterministic scene-to-storyboard projection for original offline game previews."""
from ..contracts.spec import World

def storyboard(world: World) -> list[dict]:
    return [{'sequence': i, 'scene': scene.id, 'title': scene.title, 'choice_count': len(scene.choices), 'terminal': scene.id in world.endings, 'description': scene.description} for i, scene in enumerate(world.scenes.values(), 1)]
