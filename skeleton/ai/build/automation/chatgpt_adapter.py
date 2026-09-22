"""Compatibility facade for skeleton.automation.chatgpt_adapter.

Credential and network ownership remain in the legacy source module while the
AI file-tree migration is staged. This destination intentionally re-exports the
public API without owning credentials, provider SDKs, or network configuration.
"""

from skeleton.automation.chatgpt_adapter import *  # noqa: F401,F403
