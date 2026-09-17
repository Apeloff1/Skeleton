"""Repository-local core package.

The explicit package marker keeps imports such as ``core.activation_security``
bound to this checkout during isolated CI collection instead of relying on
implicit namespace-package resolution.
"""
