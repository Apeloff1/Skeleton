"""Compatibility facade for skeleton.cortex.catalog.

The canonical AI tree must not create a second credential-bearing surface.
Credential-marker text, provider configuration, and network ownership remain in
the legacy source module during staged migration; this file only re-exports the
public API.
"""

from skeleton.cortex.catalog import *  # noqa: F401,F403
