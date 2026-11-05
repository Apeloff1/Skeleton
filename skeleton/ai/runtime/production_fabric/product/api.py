"""Pure JSON command dispatcher: local state operations only, no network execution."""
from ..contracts.canonical import loads, dumps
from ..contracts.errors import ContractError, FabricError
from ..contracts.identity import identifier
from ..planning.engine import ProductionEngine

class LocalAPI:

    def __init__(self, engine: ProductionEngine):
        self.engine = engine

    def dispatch(self, request: dict) -> dict:
        if not isinstance(request, dict) or len(request) > 8:
            raise ContractError('invalid API envelope')
        method = request.get('method')
        session = identifier(request.get('session', ''))
        if method == 'inspect':
            if set(request) != {'method', 'session'}:
                raise ContractError('unexpected inspect fields')
            return self.engine.inspect(session)
        if method == 'play':
            if set(request) != {'method', 'session', 'token', 'choice', 'expected_revision'}:
                raise ContractError('unexpected play fields')
            if type(request['expected_revision']) is not int:
                raise ContractError('invalid revision type')
            return self.engine.play(session, identifier(request['token']), identifier(request['choice']), request['expected_revision'])
        if method == 'verify':
            if set(request) != {'method', 'session'}:
                raise ContractError('unexpected verify fields')
            return self.engine.verify(session)
        if method == 'qualify':
            if set(request) != {'method', 'session'}:
                raise ContractError('unexpected qualify fields')
            return self.engine.qualify()
        raise ContractError('unknown offline API method')

    def json(self, raw: bytes) -> bytes:
        try:
            return dumps({'ok': True, 'result': self.dispatch(loads(raw))})
        except FabricError as exc:
            return dumps({'ok': False, 'error': {'code': exc.code, 'message': exc.message}})
