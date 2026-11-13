"""
Hive merkle gossip. Root history, tournament on roots, local helix jsonl consensus. No chain and no coin.
"""
ROOTS = []

def gossip(root: str) -> None:
    ROOTS.append(root)
