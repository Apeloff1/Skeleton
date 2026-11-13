"""
One routing contract between EconomicOptimiser and the cascade. No third router.
"""
CONTRACT = "RouterContract"

def route(gate: str) -> str:
    return CONTRACT if gate else "CascadeAdapter"
