"""Source-bound world registry; one unambiguous immutable world digest per identifier."""
from ..contracts.spec import parse_world, to_data
from ..contracts.canonical import digest
from ..contracts.errors import ConflictError, ContractError

class Workspace:

    def __init__(self):
        self._worlds = {}

    def admit(self, document: dict) -> str:
        world = parse_world(document)
        seal = digest(to_data(world))
        prior = self._worlds.get(world.id)
        if prior and prior[0] != seal:
            raise ConflictError('world ID already bound to another source')
        self._worlds[world.id] = (seal, document)
        return seal

    def fetch(self, name: str) -> dict:
        if name not in self._worlds:
            raise ContractError('world not installed')
        return self._worlds[name][1]

    def inventory(self) -> list[dict]:
        return [{'world': id, 'sha256': value[0]} for id, value in sorted(self._worlds.items())]
