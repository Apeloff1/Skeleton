"""Compatibility API facade for the canonical offline production dispatcher.

Do not define a second LocalAPI class here. CLI and imported product callers
must observe the *same* bounded request-validation, identity, and journal
contract as product.dispatcher; no provider or network endpoint is owned here.
"""

# Retain the historical helper names for callers that imported this module,
# but keep the dispatcher as the sole class/logic owner.
from ..contracts.canonical import loads, dumps
from ..contracts.errors import ContractError, FabricError
from ..contracts.identity import identifier
from ..planning.engine import ProductionEngine
from .dispatcher import LocalAPI
