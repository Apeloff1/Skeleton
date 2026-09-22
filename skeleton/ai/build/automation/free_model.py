"""Compatibility facade for the repository-automation model provider.

Credential and network ownership intentionally remain in
`skeleton.automation.free_model` while the AI file-tree migration is staged.
This destination is a pure re-export and must not acquire provider credentials,
SDK imports, or network behavior of its own.
"""

from skeleton.automation.free_model import FreeModelClient, ModelError, redact_secrets

__all__ = ["FreeModelClient", "ModelError", "redact_secrets"]
