"""Unicode-safe identity checks for authority-bearing identifiers.

Security identifiers are compared as exact strings across policy, approval, and
authorization boundaries. Ambiguous Unicode must therefore fail closed rather
than be silently normalized into a potentially different identity.
"""

from __future__ import annotations

import unicodedata


class TextIdentityError(ValueError):
    """Raised when an authority-bearing text identity is ambiguous."""


_CONFUSABLE_SCRIPTS = ("LATIN", "GREEK", "CYRILLIC")


def _script_family(character: str) -> str | None:
    if not character.isalpha():
        return None
    name = unicodedata.name(character, "")
    for family in _CONFUSABLE_SCRIPTS:
        if name.startswith(family + " "):
            return family
    return None


def require_security_identifier(
    value: str,
    *,
    field: str = "identifier",
    max_length: int = 256,
) -> str:
    """Return *value* only when its Unicode identity is unambiguous.

    The function intentionally rejects compatibility-normalization drift,
    format/invisible controls, whitespace, and mixed Latin/Greek/Cyrillic
    alphabetic content. It does not rewrite the identifier because silently
    rewriting an authority key can create an alias with a different principal
    or capability.
    """
    if not isinstance(value, str):
        raise TextIdentityError(f"{field} must be text")
    if not value or len(value) > max_length:
        raise TextIdentityError(f"invalid {field} length")
    if unicodedata.normalize("NFKC", value) != value:
        raise TextIdentityError(f"{field} is not NFKC-canonical")

    scripts: set[str] = set()
    for character in value:
        category = unicodedata.category(character)
        if category in {"Cc", "Cf", "Cs"}:
            raise TextIdentityError(f"{field} contains control or invisible characters")
        if character.isspace():
            raise TextIdentityError(f"{field} contains whitespace")
        family = _script_family(character)
        if family is not None:
            scripts.add(family)

    if len(scripts) > 1:
        joined = ", ".join(sorted(scripts))
        raise TextIdentityError(f"{field} mixes confusable scripts: {joined}")
    return value


__all__ = ["TextIdentityError", "require_security_identifier"]
