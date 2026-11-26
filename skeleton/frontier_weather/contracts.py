"""Shared bounds for the deterministic marathon weather slice.

The authoritative coupling step is one fixed interval. Nothing in this
package reads a wall clock. Stochastic gusts are not drawn; ``FIXED_SEED``
is recorded on every receipt and handed to the existing airflow sampler
with zero amplitude.

Documented numerical contract, also reimplemented by the finite-difference
reference in ``tests/test_game_frontier_marathon_turbulence.py``:

* von Karman logarithmic profile ``U = (u_star / 0.41) * ln((z_ref + z0) / z0)``
* terrain speed-up ``S = clamp(1 + gain * (h - min h) / length, 0.25, 4)``
* discrete vortex shed downstream of the first row-major ridge crest
* forward-Euler central advection with a five-point Laplacian on a periodic grid

Long-horizon kinetic energy of that turbulence step must stay within
``ENERGY_DRIFT_BOUND`` (relative) of an independent reference for at least
``MIN_HORIZON_STEPS`` steps. Droplet mass and coupled horizontal momentum
must stay within their stated epsilons across one atomic step.
"""

from __future__ import annotations

import json
import math
from typing import Mapping


class WeatherPhysicsError(ValueError):
    """A weather-physics input, step, or conservation check failed closed."""


class EnergyDriftError(WeatherPhysicsError):
    """Long-horizon kinetic energy left the documented reference bound."""


VON_KARMAN = 0.41
SPEEDUP_MIN = 0.25
SPEEDUP_MAX = 4.0
AUTHORITATIVE_DT_S = 0.05
MAX_EXPLICIT_DT_S = 0.1
MAX_CFL = 0.5
FIXED_SEED = 174329
WATER_DENSITY_KG_M3 = 1000.0
LIQUID_FLOW_RATE = 0.4
DROPLET_MASS_EPSILON_KG = 1e-8
COUPLED_MOMENTUM_EPSILON = 1e-7
ENERGY_DRIFT_BOUND = 1e-8
MIN_HORIZON_STEPS = 120
SCHEME = "ftcs-central-advection-log-ridge-vortex-v1"
SURFACE_EVAL_DT_S = 30.0


def require_real(
    value: float,
    name: str,
    *,
    lo: float,
    hi: float,
    inclusive_lo: bool = True,
    inclusive_hi: bool = True,
) -> float:
    """Reject booleans, NaN, infinities, and values outside the stated interval."""
    if type(value) not in (int, float) or not math.isfinite(value):
        raise WeatherPhysicsError(f"{name} must be finite")
    number = float(value)
    below = number < lo if inclusive_lo else number <= lo
    above = number > hi if inclusive_hi else number >= hi
    if below or above:
        raise WeatherPhysicsError(f"{name} outside documented interval")
    return number


def canonical_json(payload: Mapping[str, object]) -> str:
    """Compact canonical JSON: sorted keys, no whitespace, NaN rejected."""
    if not isinstance(payload, dict):
        raise WeatherPhysicsError("canonical payload must be an object")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
