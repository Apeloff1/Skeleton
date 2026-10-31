"""Seed manager. Reproducible run seeds."""
from typing import Any, Dict
import random
class SeedManager:
    def __init__(self, seed: int = 8847291):
        self.seed = seed
        self.rng = random.Random(seed)
    def next_int(self, a: int, b: int) -> int:
        return self.rng.randint(a, b)
