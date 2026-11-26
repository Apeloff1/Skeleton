"""Import path for the GF-P1-42 authoring-drift tests.

Pytest discovery is rooted at ``skeleton/testing``. The tests live in
``tests/test_game_frontier_marathon_authoring_drift.py``.
"""

from __future__ import annotations

import tests.test_game_frontier_marathon_authoring_drift as _suite

for _name in _suite.__all__:
    globals()[_name] = getattr(_suite, _name)
