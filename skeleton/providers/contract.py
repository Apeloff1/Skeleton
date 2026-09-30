"""Compatibility facade for the canonical AI provider contract.

Canonical provider architecture and provider-neutral protocol types live in
`skeleton.ai.providers.contract`. This historical module path remains importable
for callers that have not migrated yet, but it must not create a second copy of
the contract classes: exception and receipt identities are part of the runtime
fail-closed boundary.
"""

from skeleton.ai.providers import contract as _contract

for _name in _contract.__all__:
    globals()[_name] = getattr(_contract, _name)

__all__ = list(_contract.__all__)

del _name
