"""sampling boundary semantics: fail closed on cross-field conflicts."""
from ..contracts import fail

def check(p):
    if p["max_output"] >= p["context_window"]: fail("output exceeds context window")
    if p["temperature"] <= 0: fail("temperature must be positive")
    if p["top_p"] <= 0: fail("top-p must be positive")
