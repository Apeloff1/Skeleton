"""Model-bound, fail-closed operational AI reliability contracts.

Does not replace the authoritative GGUF backend or durable SQLite spine.
"""
from .engine import validate,domains,Rejected
__all__=("validate","domains","Rejected")
