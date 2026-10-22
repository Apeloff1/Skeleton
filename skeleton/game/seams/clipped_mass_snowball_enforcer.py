"""Clipped mass snowball enforcer — full law implementation."""
class SnowballEnforcer:
    MAX_FACTOR = 1.1
    CLIP = 0.05

    def enforce(self, prior_mass: float, g_delta: float) -> float:
        clipped = max(min(g_delta, self.CLIP), -self.CLIP)
        candidate = prior_mass + abs(clipped)
        return min(prior_mass * self.MAX_FACTOR, candidate)
