"""Compatibility exports for the single, pure offline production dispatcher.

The authoritative LocalAPI class lives in dispatcher.py. Re-export that exact
class rather than defining a second implementation with divergent identity.
Keep legacy module attributes available for existing integrations.
"""
from ..contracts.canonical import dumps as dumps, loads as loads
from ..contracts.errors import ContractError as ContractError, FabricError as FabricError
from ..contracts.identity import identifier as identifier
from ..planning.engine import ProductionEngine as ProductionEngine
from .dispatcher import LocalAPI as LocalAPI
