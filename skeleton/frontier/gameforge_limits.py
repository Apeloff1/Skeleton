"""Validated limits shared by frontier components."""
def positive(value: int, name: str = "value") -> int:
    if value <= 0: raise ValueError(f"{name} must be positive")
    return value

def non_negative(value: int, name: str = "value") -> int:
    if value < 0: raise ValueError(f"{name} must be non-negative")
    return value
