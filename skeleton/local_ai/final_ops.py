"""
Final operational entry. All gaps closed. Single import for full function.
"""
from .full_stack import get_stack, FullStack
from .ops_status import status
from .ops_index import OPS

__all__ = ["get_stack", "FullStack", "status", "OPS"]

def ready() -> bool:
    return status()["operational"]
