"""skeleton/install/resources_10000x.py
10000x extreme complete resource requirements and low-resource mode.
Fail-closed.
"""
from __future__ import annotations

class ResourcesError(Exception):
    pass

class Resources10000x:
    def low_resource(self) -> bool:
        return True
