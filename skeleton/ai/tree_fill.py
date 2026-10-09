"""Capability entry. Calls the body. Does not pretend a re-export is the capability."""

def load():
    from ai_tree_fill.capability_body import run_body
    return run_body()
