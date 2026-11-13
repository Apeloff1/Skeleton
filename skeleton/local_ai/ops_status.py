"""
Operational status aggregator. Single call for full health.
"""
from .full_stack import get_stack
from .ops_index import OPS

def status() -> dict:
    stack = get_stack()
    return {
        "ops_components": len(OPS),
        "health": stack.health.check(),
        "seams": stack.gaps.list().__len__(),
        "operational": True
    }
