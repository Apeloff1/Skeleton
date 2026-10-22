"""
Catalog economy as cards only. Bag, harbor, lineage weights. Weight sum equals 1.
Bag ops reversible. No currency network.
"""
WEIGHTS = {"bag": 0.4, "harbor": 0.3, "lineage": 0.3}

def sum_weights() -> float:
    return sum(WEIGHTS.values())
