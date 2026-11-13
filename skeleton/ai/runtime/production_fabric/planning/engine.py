"""One offline authoritative engine: typed worlds, durable choices, no model fallback."""
from ..contracts.canonical import digest
from ..contracts.spec import parse_world, World, to_data
from ..persistence.journal import Journal
from ..persistence.game_store import GameStore
from ..persistence.recovery import audit
from .choices import available
from .endings import discover
from .worlds import validate_playable

class ProductionEngine:

    def __init__(self, world_data: dict, journal: Journal | None=None):
        self._owns_journal = journal is None
        self.world: World = parse_world(world_data)
        validate_playable(self.world)
        self.journal = journal or Journal()
        self.store = GameStore(self.journal, self.world)
        self.world_sha256 = digest(to_data(self.world))

    def inspect(self, session: str) -> dict:
        state = self.store.load(session)
        scene = self.world.scenes[state.scene]
        return {'state': state.as_data(), 'title': scene.title, 'description': scene.description, 'choices': available(self.world, state), 'world_sha256': self.world_sha256}

    def play(self, session: str, token: str, choice: str, expected_revision: int) -> dict:
        state, receipt = self.store.choose(session, token, choice, expected_revision=expected_revision)
        return {'scene': self.inspect(session), 'receipt': receipt}

    def verify(self, session: str) -> dict:
        return audit(self.store, session)

    def qualify(self) -> dict:
        return discover(self.world)

    def close(self) -> None:
        """Close only the journal this engine created, not operator-owned storage."""
        if self._owns_journal:
            self.journal.close()

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.close()
