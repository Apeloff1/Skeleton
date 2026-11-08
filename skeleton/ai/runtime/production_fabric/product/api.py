"""Compatibility entrypoint for the one canonical offline LocalAPI dispatcher.

The dispatcher owns input validation and authority. This module only preserves
legacy imports; it must not introduce a second API class or execution path.
"""

from .dispatcher import LocalAPI

__all__ = ["LocalAPI"]
