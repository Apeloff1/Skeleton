"""
Parse splitter. Pointer clauses only. Bound N-cap 8. No stored sentence in the mesh.
"""
def split(stimulus: str) -> list:
    return [c for c in stimulus.split(".") if c.strip()][:8]
