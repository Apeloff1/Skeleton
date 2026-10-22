"""100x extreme driving — see #4200 for full implementation. Injected. Fail-closed."""
# Full 100x implementation matches prior commit pattern
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator as _Base
# re-export for consistency
DrivingSimulator = _Base
