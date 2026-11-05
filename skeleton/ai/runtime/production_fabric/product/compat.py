"""Read-only game studio interface contract without a second execution authority."""
from ..contracts.spec import World
from ..contracts.state import GameState
from ..planning.choices import available

def studio_view(world: World, state: GameState) -> dict:
    return {'schema_version': 1, 'world': world.id, 'scene': state.scene, 'revision': state.revision, 'choices': available(world, state), 'execution_owner': 'production_fabric.sqlite_journal', 'can_start_external_tools': False}
