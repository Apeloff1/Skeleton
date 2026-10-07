from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path

import pytest

from skeleton.contracts.localization import (
    LocaleFallbackPolicy,
    LocaleId,
    LocalizationError,
    TranslationCatalog,
    TranslationCriticality,
    TranslationEntry,
    TranslationRegistry,
    parse_enum_token,
    parse_integer,
    parse_number,
    parse_timestamp,
    serialize_enum,
    serialize_identifier,
    serialize_integer,
    serialize_number,
    serialize_timestamp,
)

ROOT = Path(__file__).resolve().parents[2]


def catalog(
    locale: str,
    *,
    version: int = 1,
    messages: dict[str, str] | None = None,
    critical: tuple[str, ...] = (),
) -> TranslationCatalog:
    values = messages or {
        "app.name": "Skeleton",
        "operation.cancel": "Cancel operation",
    }
    return TranslationCatalog.from_mapping(
        catalog_id=f"catalog.{locale.replace('-', '_')}.v{version}",
        locale=locale,
        version=version,
        messages=values,
        critical_keys=critical,
        reviewed_critical_keys=critical,
    )


def policy(**overrides) -> LocaleFallbackPolicy:
    values = {
        "policy_id": "locale.default.v1",
        "default_locale": LocaleId("en"),
        "allow_language_parent": True,
        "allow_default_locale": True,
        "allow_critical_default_fallback": True,
        "require_reviewed_critical": True,
        "max_depth": 4,
    }
    values.update(overrides)
    return LocaleFallbackPolicy(**values)


def test_locale_id_canonicalizes_language_script_and_region() -> None:
    assert LocaleId("EN-us").value == "en-US"
    assert LocaleId("zh-hant-tw").value == "zh-Hant-TW"
    assert LocaleId("nb-NO").language == "nb"


def test_locale_id_rejects_invalid_or_unbounded_tags() -> None:
    for value in ("", "en_US", "1n", "en--US", "e"):
        with pytest.raises(LocalizationError):
            LocaleId(value)


def test_parent_chain_is_deterministic() -> None:
    assert tuple(item.value for item in LocaleId("zh-Hant-TW").parent_chain()) == (
        "zh-Hant",
        "zh",
    )


def test_critical_translation_requires_explicit_review() -> None:
    with pytest.raises(LocalizationError, match="reviewed"):
        TranslationEntry(
            key="operation.cancel",
            text="Cancel operation",
            criticality=TranslationCriticality.CRITICAL,
            reviewed=False,
        )


def test_critical_prefix_is_treated_as_critical_even_without_flag() -> None:
    with pytest.raises(LocalizationError, match="reviewed"):
        TranslationEntry(
            key="authority.approve",
            text="Approve",
        )


def test_catalog_orders_entries_and_has_stable_digest() -> None:
    first = TranslationCatalog.from_mapping(
        catalog_id="catalog.en.v1",
        locale="en",
        version=1,
        messages={"z.last": "Last", "a.first": "First"},
    )
    second = TranslationCatalog.from_mapping(
        catalog_id="catalog.en.v1",
        locale="en",
        version=1,
        messages={"a.first": "First", "z.last": "Last"},
    )

    assert first == second
    assert first.keys == ("a.first", "z.last")
    assert first.digest == second.digest


def test_catalog_rejects_unreviewed_declared_critical_key() -> None:
    with pytest.raises(LocalizationError, match="lacks review"):
        TranslationCatalog.from_mapping(
            catalog_id="catalog.en.v1",
            locale="en",
            version=1,
            messages={"operation.cancel": "Cancel"},
            critical_keys=("operation.cancel",),
        )


def test_registry_registration_is_idempotent_and_version_monotonic() -> None:
    registry = TranslationRegistry()
    first = catalog("en")
    assert registry.register(first) is first
    assert registry.register(first) is first

    with pytest.raises(LocalizationError, match="increase version"):
        registry.register(
            TranslationCatalog.from_mapping(
                catalog_id="catalog.en.other",
                locale="en",
                version=1,
                messages={"app.name": "Other"},
            )
        )

    newer = TranslationCatalog.from_mapping(
        catalog_id="catalog.en.v2",
        locale="en",
        version=2,
        messages={"app.name": "Skeleton 2"},
    )
    assert registry.register(newer) is newer
    assert registry.get("EN").version == 2


def test_resolution_prefers_exact_locale_then_parent_then_default() -> None:
    registry = TranslationRegistry()
    registry.register(catalog("en", messages={"app.name": "English"}))
    registry.register(catalog("nb", messages={"app.name": "Norsk"}))

    exact = registry.resolve(
        key="app.name",
        requested_locale="nb",
        policy=policy(),
    )
    parent = registry.resolve(
        key="app.name",
        requested_locale="nb-NO",
        policy=policy(),
    )
    default = registry.resolve(
        key="app.name",
        requested_locale="fr-FR",
        policy=policy(),
    )

    assert exact.text == "Norsk"
    assert exact.fallback_used is False
    assert parent.resolved_locale == LocaleId("nb")
    assert parent.fallback_used is True
    assert default.resolved_locale == LocaleId("en")
    assert default.text == "English"


def test_critical_default_fallback_can_be_forbidden() -> None:
    registry = TranslationRegistry()
    registry.register(
        catalog(
            "en",
            messages={"operation.cancel": "Cancel operation"},
            critical=("operation.cancel",),
        )
    )

    with pytest.raises(LocalizationError, match="fallback forbidden"):
        registry.resolve(
            key="operation.cancel",
            requested_locale="fr-FR",
            policy=policy(allow_critical_default_fallback=False),
        )


def test_missing_critical_translation_fails_closed() -> None:
    registry = TranslationRegistry()
    registry.register(catalog("en", messages={"app.name": "Skeleton"}))

    with pytest.raises(LocalizationError, match="missing critical"):
        registry.resolve(
            key="authority.approve",
            requested_locale="en",
            policy=policy(),
        )


def test_resolution_binds_catalog_and_policy_digests() -> None:
    registry = TranslationRegistry()
    item = catalog(
        "en",
        messages={"operation.cancel": "Cancel operation"},
        critical=("operation.cancel",),
    )
    registry.register(item)
    chosen_policy = policy()

    result = registry.resolve(
        key="operation.cancel",
        requested_locale="en",
        policy=chosen_policy,
    )

    assert result.catalog_digest == item.digest
    assert result.policy_digest == chosen_policy.digest
    assert result.reviewed is True
    assert result.critical is True
    assert result.digest


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (-0.0, "0"),
        (1, "1"),
        (-17, "-17"),
        (1.5, "1.5"),
        (Decimal("1000.000"), "1000"),
        (Decimal("-0.1250"), "-0.125"),
    ],
)
def test_number_serialization_is_locale_neutral(value, expected: str) -> None:
    assert serialize_number(value) == expected
    assert parse_number(expected) == Decimal(expected)


@pytest.mark.parametrize(
    "value",
    [
        "1,5",
        "1 000",
        "+1",
        "01",
        "1.0",
        "1e3",
        "NaN",
        "Infinity",
        "١٢",
    ],
)
def test_number_parser_rejects_locale_or_nonnormalized_forms(value: str) -> None:
    with pytest.raises(LocalizationError):
        parse_number(value)


def test_nonfinite_numbers_fail_closed() -> None:
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(LocalizationError):
            serialize_number(value)


def test_integer_contract_rejects_grouping_plus_and_leading_zeroes() -> None:
    assert serialize_integer(-42) == "-42"
    assert parse_integer("-42") == -42
    for value in ("+42", "042", "4,200", "4 200"):
        with pytest.raises(LocalizationError):
            parse_integer(value)


def test_timestamp_is_canonical_utc_milliseconds() -> None:
    source = datetime(
        2026,
        10,
        5,
        14,
        41,
        12,
        987654,
        tzinfo=timezone(timedelta(hours=2)),
    )
    rendered = serialize_timestamp(source)

    assert rendered == "2026-10-05T12:41:12.987Z"
    assert serialize_timestamp(parse_timestamp(rendered)) == rendered


def test_timestamp_rejects_naive_offset_or_noncanonical_precision() -> None:
    with pytest.raises(LocalizationError):
        serialize_timestamp(datetime(2026, 10, 5, 12, 0, 0))
    for value in (
        "2026-10-05T12:00:00+00:00",
        "2026-10-05T12:00:00Z",
        "2026-10-05 12:00:00.000Z",
    ):
        with pytest.raises(LocalizationError):
            parse_timestamp(value)


class State(Enum):
    READY = "ready"


def test_enum_and_identifier_are_locale_neutral_tokens() -> None:
    assert serialize_enum(State.READY) == "ready"
    assert parse_enum_token("ready") == "ready"
    assert serialize_identifier("operation:abc-123") == "operation:abc-123"

    for value in ("with space", "pågående", ""):
        with pytest.raises(LocalizationError):
            serialize_identifier(value)


def test_registry_digest_is_registration_order_independent() -> None:
    en = catalog("en", messages={"app.name": "English"})
    nb = catalog("nb", messages={"app.name": "Norsk"})

    first = TranslationRegistry()
    first.register(en)
    first.register(nb)
    second = TranslationRegistry()
    second.register(nb)
    second.register(en)

    assert first.digest == second.digest


def test_canonical_and_ai_localization_contracts_are_byte_identical() -> None:
    assert (
        ROOT / "skeleton/contracts/localization.py"
    ).read_bytes() == (
        ROOT / "skeleton/ai/runtime/contracts/localization.py"
    ).read_bytes()


def test_canonical_and_ai_contract_exports_remain_byte_identical() -> None:
    assert (
        ROOT / "skeleton/contracts/__init__.py"
    ).read_bytes() == (
        ROOT / "skeleton/ai/runtime/contracts/__init__.py"
    ).read_bytes()
