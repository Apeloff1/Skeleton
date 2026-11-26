"""Fail-closed errors for the contact runtime.

A raised ``ContactRejected`` means the caller keeps the body it already had.
The step functions build a scratch pose and return it only after the whole
step succeeds.
"""

from __future__ import annotations


class ContactRejected(ValueError):
    """The contact step cannot be committed."""
