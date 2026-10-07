"""Locale-neutral persistence and versioned translation contracts for VOL-087.

The contract separates machine identity/persistence from localized presentation:
identifiers/enums are canonical ASCII tokens; persisted numbers and timestamps
are locale-neutral; locale resources are versioned/content-addressed; and
critical safety/authority strings fail closed when fallback is unsafe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
import json
import math
import re
from typing import Iterable, Mapping

LOCALE_SCHEMA = "skeleton.contracts.localization.v1"
_MAX_TEXT = 4096
_MAX_MESSAGES = 8192
_MAX_FALLBACK_DEPTH = 8
_LOCALE = re.compile(
    r"^[A-Za-z]{2,8}(?:-[A-Za-z]{4})?(?:-(?:[A-Za-z]{2}|[0-9]{3}))?"
    r"(?:-[A-Za-z0-9]{5,8})*$"
)
_KEY = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+){0,15}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_CANONICAL_NUMBER = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_CANONICAL_INTEGER = re.compile(r"^-?(?:0|[1-9][0-9]*)$")
_CRITICAL_PREFIXES = (
    "authority.",
    "operation.",
    "recovery.",
    "safety.",
    "security.",
)


class LocalizationError(ValueError):
    """Locale, catalog or fallback contract is invalid."""


class TranslationCriticality(str, Enum):
    NORMAL = "normal"
    CRITICAL = "critical"


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LocalizationError("value must be deterministic JSON") from exc


def _digest(value: object) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _text(value: object, field: str, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise LocalizationError(f"{field} must be text")
    if value != value.strip() or not value or len(value) > maximum:
        raise LocalizationError(f"{field} must be normalized bounded text")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        raise LocalizationError(f"{field} contains control characters")
    return value


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise LocalizationError(f"{field} must be a canonical token")
    return value


def _key(value: object, field: str = "translation key") -> str:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise LocalizationError(f"{field} must be a canonical translation key")
    return value


def _positive_int(value: object, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LocalizationError(f"{field} must be an integer")
    if not 1 <= value <= maximum:
        raise LocalizationError(f"{field} must be within [1, {maximum}]")
    return value


@dataclass(frozen=True, slots=True, order=True)
class LocaleId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _LOCALE.fullmatch(self.value):
            raise LocalizationError("locale must be a bounded BCP47-shaped tag")
        parts = self.value.split("-")
        normalized = [parts[0].lower()]
        for part in parts[1:]:
            if len(part) == 4 and part.isalpha():
                normalized.append(part.title())
            elif (
                (len(part) == 2 and part.isalpha())
                or (len(part) == 3 and part.isdigit())
            ):
                normalized.append(part.upper())
            else:
                normalized.append(part.lower())
        object.__setattr__(self, "value", "-".join(normalized))

    @property
    def language(self) -> str:
        return self.value.split("-", 1)[0]

    def parent_chain(self) -> tuple["LocaleId", ...]:
        parts = self.value.split("-")
        parents: list[LocaleId] = []
        while len(parts) > 1:
            parts = parts[:-1]
            parents.append(LocaleId("-".join(parts)))
        return tuple(parents)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TranslationEntry:
    key: str
    text: str
    criticality: TranslationCriticality = TranslationCriticality.NORMAL
    reviewed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _key(self.key))
        object.__setattr__(self, "text", _text(self.text, "translation text"))
        if not isinstance(self.criticality, TranslationCriticality):
            raise LocalizationError(
                "criticality must be TranslationCriticality"
            )
        if not isinstance(self.reviewed, bool):
            raise LocalizationError("reviewed must be boolean")
        if self.is_critical and not self.reviewed:
            raise LocalizationError(
                "critical translation must be explicitly reviewed"
            )

    @property
    def is_critical(self) -> bool:
        return (
            self.criticality is TranslationCriticality.CRITICAL
            or self.key.startswith(_CRITICAL_PREFIXES)
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": LOCALE_SCHEMA,
                "kind": "translation-entry",
                "key": self.key,
                "text": self.text,
                "criticality": self.criticality.value,
                "reviewed": self.reviewed,
            }
        )


@dataclass(frozen=True, slots=True)
class TranslationCatalog:
    catalog_id: str
    locale: LocaleId
    version: int
    entries: tuple[TranslationEntry, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "catalog_id",
            _token(self.catalog_id, "catalog_id"),
        )
        if not isinstance(self.locale, LocaleId):
            raise LocalizationError("locale must be LocaleId")
        object.__setattr__(
            self,
            "version",
            _positive_int(self.version, "version", 1_000_000_000),
        )
        if not isinstance(self.entries, tuple):
            raise LocalizationError("entries must be a tuple")
        if not self.entries:
            raise LocalizationError("catalog requires at least one entry")
        if len(self.entries) > _MAX_MESSAGES:
            raise LocalizationError("catalog exceeds message bound")
        normalized = tuple(sorted(self.entries, key=lambda item: item.key))
        keys = [item.key for item in normalized]
        if len(keys) != len(set(keys)):
            raise LocalizationError("catalog contains duplicate translation key")
        object.__setattr__(self, "entries", normalized)

    @classmethod
    def from_mapping(
        cls,
        *,
        catalog_id: str,
        locale: str | LocaleId,
        version: int,
        messages: Mapping[str, str],
        critical_keys: Iterable[str] = (),
        reviewed_critical_keys: Iterable[str] = (),
    ) -> "TranslationCatalog":
        locale_id = locale if isinstance(locale, LocaleId) else LocaleId(locale)
        critical = {_key(item, "critical key") for item in critical_keys}
        reviewed = {
            _key(item, "reviewed critical key")
            for item in reviewed_critical_keys
        }
        if not critical.issubset(reviewed):
            missing = sorted(critical - reviewed)
            raise LocalizationError(
                "critical translation lacks review: " + ", ".join(missing)
            )
        entries = tuple(
            TranslationEntry(
                key=_key(key),
                text=value,
                criticality=(
                    TranslationCriticality.CRITICAL
                    if key in critical
                    else TranslationCriticality.NORMAL
                ),
                reviewed=(key in reviewed),
            )
            for key, value in messages.items()
        )
        return cls(
            catalog_id=catalog_id,
            locale=locale_id,
            version=version,
            entries=entries,
        )

    def get(self, key: str) -> TranslationEntry | None:
        normalized = _key(key)
        for entry in self.entries:
            if entry.key == normalized:
                return entry
        return None

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(entry.key for entry in self.entries)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": LOCALE_SCHEMA,
                "kind": "translation-catalog",
                "catalog_id": self.catalog_id,
                "locale": self.locale.value,
                "version": self.version,
                "entries": [
                    {"key": entry.key, "digest": entry.digest}
                    for entry in self.entries
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class LocaleFallbackPolicy:
    policy_id: str
    default_locale: LocaleId
    allow_language_parent: bool = True
    allow_default_locale: bool = True
    allow_critical_default_fallback: bool = True
    require_reviewed_critical: bool = True
    max_depth: int = 4

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_id",
            _token(self.policy_id, "policy_id"),
        )
        if not isinstance(self.default_locale, LocaleId):
            raise LocalizationError("default_locale must be LocaleId")
        for field in (
            "allow_language_parent",
            "allow_default_locale",
            "allow_critical_default_fallback",
            "require_reviewed_critical",
        ):
            if not isinstance(getattr(self, field), bool):
                raise LocalizationError(f"{field} must be boolean")
        object.__setattr__(
            self,
            "max_depth",
            _positive_int(self.max_depth, "max_depth", _MAX_FALLBACK_DEPTH),
        )

    def chain(self, requested: LocaleId) -> tuple[LocaleId, ...]:
        if not isinstance(requested, LocaleId):
            raise LocalizationError("requested locale must be LocaleId")
        candidates: list[LocaleId] = [requested]
        if self.allow_language_parent:
            candidates.extend(requested.parent_chain())
        if (
            self.allow_default_locale
            and self.default_locale not in candidates
        ):
            candidates.append(self.default_locale)
        unique: list[LocaleId] = []
        for candidate in candidates:
            if candidate not in unique:
                unique.append(candidate)
        return tuple(unique[: self.max_depth])

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": LOCALE_SCHEMA,
                "kind": "locale-fallback-policy",
                "policy_id": self.policy_id,
                "default_locale": self.default_locale.value,
                "allow_language_parent": self.allow_language_parent,
                "allow_default_locale": self.allow_default_locale,
                "allow_critical_default_fallback": (
                    self.allow_critical_default_fallback
                ),
                "require_reviewed_critical": self.require_reviewed_critical,
                "max_depth": self.max_depth,
            }
        )


@dataclass(frozen=True, slots=True)
class TranslationResolution:
    key: str
    requested_locale: LocaleId
    resolved_locale: LocaleId
    text: str
    catalog_id: str
    catalog_version: int
    catalog_digest: str
    policy_digest: str
    fallback_used: bool
    critical: bool
    reviewed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _key(self.key))
        if not isinstance(self.requested_locale, LocaleId):
            raise LocalizationError("requested_locale must be LocaleId")
        if not isinstance(self.resolved_locale, LocaleId):
            raise LocalizationError("resolved_locale must be LocaleId")
        object.__setattr__(self, "text", _text(self.text, "resolved text"))
        object.__setattr__(
            self,
            "catalog_id",
            _token(self.catalog_id, "catalog_id"),
        )
        object.__setattr__(
            self,
            "catalog_version",
            _positive_int(
                self.catalog_version,
                "catalog_version",
                1_000_000_000,
            ),
        )
        for field in ("catalog_digest", "policy_digest"):
            value = getattr(self, field)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise LocalizationError(f"{field} must be canonical sha256")
        for field in ("fallback_used", "critical", "reviewed"):
            if not isinstance(getattr(self, field), bool):
                raise LocalizationError(f"{field} must be boolean")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": LOCALE_SCHEMA,
                "kind": "translation-resolution",
                "key": self.key,
                "requested_locale": self.requested_locale.value,
                "resolved_locale": self.resolved_locale.value,
                "text": self.text,
                "catalog_id": self.catalog_id,
                "catalog_version": self.catalog_version,
                "catalog_digest": self.catalog_digest,
                "policy_digest": self.policy_digest,
                "fallback_used": self.fallback_used,
                "critical": self.critical,
                "reviewed": self.reviewed,
            }
        )


class TranslationRegistry:
    def __init__(self) -> None:
        self._catalogs: dict[str, TranslationCatalog] = {}

    def register(self, catalog: TranslationCatalog) -> TranslationCatalog:
        if not isinstance(catalog, TranslationCatalog):
            raise TypeError("catalog must be TranslationCatalog")
        key = catalog.locale.value
        existing = self._catalogs.get(key)
        if existing is not None:
            if existing == catalog:
                return existing
            if catalog.version <= existing.version:
                raise LocalizationError(
                    "catalog replacement must increase version"
                )
        self._catalogs[key] = catalog
        return catalog

    def get(self, locale: str | LocaleId) -> TranslationCatalog | None:
        locale_id = locale if isinstance(locale, LocaleId) else LocaleId(locale)
        return self._catalogs.get(locale_id.value)

    def resolve(
        self,
        *,
        key: str,
        requested_locale: str | LocaleId,
        policy: LocaleFallbackPolicy,
        critical: bool | None = None,
    ) -> TranslationResolution:
        normalized_key = _key(key)
        locale_id = (
            requested_locale
            if isinstance(requested_locale, LocaleId)
            else LocaleId(requested_locale)
        )
        if not isinstance(policy, LocaleFallbackPolicy):
            raise TypeError("policy must be LocaleFallbackPolicy")

        inferred_critical = normalized_key.startswith(_CRITICAL_PREFIXES)
        is_critical = inferred_critical if critical is None else bool(critical)

        for candidate in policy.chain(locale_id):
            catalog = self._catalogs.get(candidate.value)
            if catalog is None:
                continue
            entry = catalog.get(normalized_key)
            if entry is None:
                continue

            entry_critical = is_critical or entry.is_critical
            fallback_used = candidate != locale_id
            if (
                entry_critical
                and policy.require_reviewed_critical
                and not entry.reviewed
            ):
                raise LocalizationError(
                    f"critical translation is unreviewed: {normalized_key}"
                )
            if (
                entry_critical
                and fallback_used
                and candidate == policy.default_locale
                and not policy.allow_critical_default_fallback
            ):
                raise LocalizationError(
                    f"critical default fallback forbidden: {normalized_key}"
                )

            return TranslationResolution(
                key=normalized_key,
                requested_locale=locale_id,
                resolved_locale=candidate,
                text=entry.text,
                catalog_id=catalog.catalog_id,
                catalog_version=catalog.version,
                catalog_digest=catalog.digest,
                policy_digest=policy.digest,
                fallback_used=fallback_used,
                critical=entry_critical,
                reviewed=entry.reviewed,
            )

        if is_critical:
            raise LocalizationError(
                f"missing critical translation: {normalized_key}"
            )
        raise LocalizationError(f"missing translation: {normalized_key}")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": LOCALE_SCHEMA,
                "kind": "translation-registry",
                "catalogs": [
                    self._catalogs[key].digest
                    for key in sorted(self._catalogs)
                ],
            }
        )


def serialize_number(value: int | Decimal | float) -> str:
    if isinstance(value, bool):
        raise LocalizationError("boolean is not a numeric persistence value")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LocalizationError("persisted float must be finite")
        decimal_value = Decimal(str(value))
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, Decimal):
        decimal_value = value
    else:
        raise TypeError("value must be int, Decimal or float")

    if not decimal_value.is_finite():
        raise LocalizationError("persisted decimal must be finite")
    if decimal_value == 0:
        return "0"
    rendered = format(decimal_value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered == "-0":
        return "0"
    if not _CANONICAL_NUMBER.fullmatch(rendered):
        raise LocalizationError("numeric serialization was not canonical")
    return rendered


def parse_number(value: str) -> Decimal:
    if not isinstance(value, str) or not _CANONICAL_NUMBER.fullmatch(value):
        raise LocalizationError("number is not canonical locale-neutral text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise LocalizationError("number is invalid") from exc
    if not parsed.is_finite():
        raise LocalizationError("number must be finite")
    if serialize_number(parsed) != value:
        raise LocalizationError("number is not normalized canonical text")
    return parsed


def serialize_integer(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("value must be int")
    rendered = str(value)
    if not _CANONICAL_INTEGER.fullmatch(rendered):
        raise LocalizationError("integer serialization was not canonical")
    return rendered


def parse_integer(value: str) -> int:
    if not isinstance(value, str) or not _CANONICAL_INTEGER.fullmatch(value):
        raise LocalizationError("integer is not canonical locale-neutral text")
    parsed = int(value, 10)
    if str(parsed) != value:
        raise LocalizationError("integer is not normalized canonical text")
    return parsed


def serialize_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise TypeError("value must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise LocalizationError("persisted timestamp must be timezone-aware")
    utc = value.astimezone(timezone.utc)
    return utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise LocalizationError("timestamp must be canonical UTC RFC3339")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LocalizationError("timestamp is invalid RFC3339") from exc
    if serialize_timestamp(parsed) != value:
        raise LocalizationError("timestamp is not normalized canonical UTC")
    return parsed


def serialize_enum(value: Enum | str) -> str:
    raw = value.value if isinstance(value, Enum) else value
    return _token(raw, "enum value")


def parse_enum_token(value: str) -> str:
    return _token(value, "enum value")


def serialize_identifier(value: str) -> str:
    return _token(value, "identifier")


__all__ = [
    "LOCALE_SCHEMA",
    "LocaleFallbackPolicy",
    "LocaleId",
    "LocalizationError",
    "TranslationCatalog",
    "TranslationCriticality",
    "TranslationEntry",
    "TranslationRegistry",
    "TranslationResolution",
    "parse_enum_token",
    "parse_integer",
    "parse_number",
    "parse_timestamp",
    "serialize_enum",
    "serialize_identifier",
    "serialize_integer",
    "serialize_number",
    "serialize_timestamp",
]
