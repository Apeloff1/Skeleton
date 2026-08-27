"""Strongly-typed identifier value objects.

Identifiers in Skeleton are never bare strings. Each kind of entity gets a
distinct immutable value object with a prefix (``agent_01HZX…``), validation
on construction, and total ordering. They hash by value, so they can key
dicts and sets throughout the codebase, and they refuse to equal a different
identifier kind even when the underlying strings collide.
"""

from __future__ import annotations

import re
import secrets
import time

from skeleton.kernel.errors import InvalidIdentifierError

_BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _base62(number: int) -> str:
    """Encode a non-negative int as base62 (compact, URL-safe, sortable-ish)."""
    if number == 0:
        return "0"
    digits: list[str] = []
    while number:
        number, rem = divmod(number, 62)
        digits.append(_BASE62[rem])
    return "".join(reversed(digits))


def generate_token(*, entropy_bytes: int = 12) -> str:
    """Time-ordered random token: 8 base62 digits of millis + random suffix.

    The time prefix makes tokens roughly sortable by creation time, which is
    convenient in logs and listings; the random suffix guarantees uniqueness.
    """
    millis = int(time.time() * 1000)
    time_part = _base62(millis).rjust(8, "0")
    rand_part = _base62(secrets.randbits(entropy_bytes * 8)).rjust(entropy_bytes * 2, "0")
    return f"{time_part}{rand_part[:16]}"


class EntityId:
    """Base class for all typed identifiers.

    Subclasses set ``prefix``; instances render as ``{prefix}_{token}``.
    """

    prefix: str = "id"
    _PATTERN: re.Pattern[str] | None = None

    __slots__ = ("_token",)

    def __init__(self, token: str | None = None) -> None:
        if token is None:
            token = f"{self.prefix}_{generate_token()}"
        elif token.startswith(self.prefix + "_"):
            pass
        else:
            # allow bare tokens from generate_token()
            token = f"{self.prefix}_{token}"
        pattern = self._compiled_pattern()
        if not pattern.fullmatch(token):
            raise InvalidIdentifierError(
                f"Invalid token for {type(self).__name__}: {token!r}",
                context={"kind": type(self).__name__, "token": token},
            )
        object.__setattr__(self, "_token", token)

    @classmethod
    def _compiled_pattern(cls) -> re.Pattern[str]:
        if EntityId._PATTERN is None or "_kind_pattern" not in cls.__dict__:
            cls._kind_pattern = re.compile(rf"{re.escape(cls.prefix)}_[0-9A-Za-z]+")  # type: ignore[attr-defined]
        return cls._kind_pattern  # type: ignore[attr-defined]

    # -- constructors ------------------------------------------------------

    @classmethod
    def new(cls):
        """Mint a fresh identifier."""
        return cls()

    @classmethod
    def parse(cls, raw: str):
        """Parse from the canonical string form, validating kind and shape."""
        if not isinstance(raw, str):
            raise InvalidIdentifierError(
                f"Cannot parse {type(cls).__name__} from non-string",
                context={"raw": repr(raw)},
            )
        expected = cls.prefix + "_"
        if not raw.startswith(expected):
            raise InvalidIdentifierError(
                f"{raw!r} is not a {cls.__name__} (expected prefix {expected!r})",
                context={"raw": raw, "expected_prefix": expected},
            )
        return cls(raw)

    # -- dunder ------------------------------------------------------------

    @property
    def token(self) -> str:
        return self._token  # type: ignore[attr-defined]

    def __str__(self) -> str:
        return self._token  # type: ignore[attr-defined]

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._token!r})"  # type: ignore[attr-defined]

    def __hash__(self) -> int:
        return hash((type(self), self._token))  # type: ignore[attr-defined]

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and other._token == self._token  # type: ignore[attr-defined]

    def __lt__(self, other: "EntityId") -> bool:
        if type(other) is not type(self):
            return NotImplemented
        return self._token < other._token  # type: ignore[attr-defined]

    def __setattr__(self, name: str, value: object) -> None:  # immutability
        raise AttributeError(f"{type(self).__name__} is immutable")


class AgentId(EntityId):
    prefix = "agent"


class SessionId(EntityId):
    prefix = "sess"


class PipelineRunId(EntityId):
    prefix = "run"


class BlueprintId(EntityId):
    prefix = "bp"


class UserId(EntityId):
    prefix = "user"


class MemoryId(EntityId):
    prefix = "mem"


_KINDS: dict[str, type[EntityId]] = {
    kls.prefix: kls for kls in (AgentId, SessionId, PipelineRunId, BlueprintId, UserId, MemoryId)
}


def parse_any(raw: str) -> EntityId:
    """Parse any typed identifier from its string form via its prefix."""
    if not isinstance(raw, str) or "_" not in raw:
        raise InvalidIdentifierError(f"Unparseable identifier: {raw!r}")
    prefix = raw.split("_", 1)[0]
    kind = _KINDS.get(prefix)
    if kind is None:
        raise InvalidIdentifierError(
            f"Unknown identifier prefix {prefix!r}",
            context={"raw": raw, "known_prefixes": sorted(_KINDS)},
        )
    return kind.parse(raw)
