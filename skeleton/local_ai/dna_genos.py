"""
Emit DNAHelix pairs on forge and read them from the genos organ. Persist helix file under chronicle.
"""
PAIRS = []

def emit(pair: dict) -> None:
    PAIRS.append(pair)
