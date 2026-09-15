"""Zaibatsu substrate for the Skeleton backend.

One law, three languages: this package implements the same contracts as
the Rust core (gameforge-rs) and the C# gate (gameforge-middleware):

- seal:    HMAC-SHA256 request seals — verified, never self-declared
- audit:   hash-chained WORM audit log, fsync'd, verified at startup
- outbox:  journal-first durable intents with a background reconciler
- chaos:   the degradation ladder (Normal -> EmergencyReadOnly)
- fabric:  hash-chained event spine; tamper-evident by construction
- gate:    the ASGI gauntlet every request crosses, in fixed order
- diplomat: ctypes binding to gf-ffi — the Rust courts, in-process

Every module is bounded by construction and fails closed. Nothing in this
package trusts a caller, a message string, or a process lifetime.
"""

__all__ = ["seal", "audit", "outbox", "chaos", "fabric", "gate", "diplomat"]
__version__ = "1.0.0"
