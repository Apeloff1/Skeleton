"""
ContactEngine house-copy LoRA. absorb_steps, rank, alpha, HF and Kimi aliases, dialect house.
"""
def attach(name: str, rank: int = 8, alpha: float = 16.0) -> dict:
    return {"name": name, "rank": rank, "alpha": alpha, "house": "dialect"}
