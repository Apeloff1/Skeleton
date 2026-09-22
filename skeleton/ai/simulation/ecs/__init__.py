"""Deterministic engine-neutral ECS/simulation core.

The package exposes versioned state, deterministic execution, rollback/replay,
and bounded inspection contracts without depending on a renderer, transport,
provider SDK, or engine runtime.
"""

from .core import *
from .execution import *
from .runtime import *
from .scenario import *
