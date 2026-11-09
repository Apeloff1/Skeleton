"""
Skeleton Vault — Key management service module

Provides:
- EnvelopeKMS: Envelope encryption (re-export hub)
"""

from __future__ import annotations

from skeleton.vault.access import EnvelopeKMS

__all__ = ["EnvelopeKMS"]
