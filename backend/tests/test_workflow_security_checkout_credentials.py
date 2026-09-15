"""Regression tests for checkout credential hardening detection."""

from backend.scripts.check_workflow_security import (
    _checkout_credentials_disabled,
    _flow_checkout_credentials_disabled,
)


def test_checkout_persist_credentials_requires_with_mapping() -> None:
    lines = [
        "      - uses: actions/checkout@0123456789012345678901234567890123456789",
        "        env:",
        "          persist-credentials: false",
    ]

    assert not _checkout_credentials_disabled(lines, 0)


def test_checkout_persist_credentials_accepts_direct_with_input() -> None:
    lines = [
        "      - uses: actions/checkout@0123456789012345678901234567890123456789",
        "        with:",
        "          fetch-depth: 1",
        "          persist-credentials: false",
    ]

    assert _checkout_credentials_disabled(lines, 0)


def test_named_checkout_step_accepts_sibling_with_mapping() -> None:
    lines = [
        "      - name: Checkout repository",
        "        uses: actions/checkout@0123456789012345678901234567890123456789",
        "        with:",
        "          persist-credentials: false",
        "      - name: Next step",
        "        run: echo done",
    ]

    assert _checkout_credentials_disabled(lines, 1)


def test_checkout_persist_credentials_rejects_nested_non_input() -> None:
    lines = [
        "      - uses: actions/checkout@0123456789012345678901234567890123456789",
        "        with:",
        "          metadata:",
        "            persist-credentials: false",
    ]

    assert not _checkout_credentials_disabled(lines, 0)


def test_checkout_persist_credentials_accepts_inline_with_mapping() -> None:
    lines = [
        "      - uses: actions/checkout@0123456789012345678901234567890123456789",
        "        with: { fetch-depth: 1, persist-credentials: false }",
    ]

    assert _checkout_credentials_disabled(lines, 0)


def test_flow_checkout_persist_credentials_is_scoped_to_with() -> None:
    valid = (
        "- { uses: actions/checkout@0123456789012345678901234567890123456789, "
        "with: { persist-credentials: false } }"
    )
    invalid = (
        "- { uses: actions/checkout@0123456789012345678901234567890123456789, "
        "env: { persist-credentials: false } }"
    )

    assert _flow_checkout_credentials_disabled(valid)
    assert not _flow_checkout_credentials_disabled(invalid)
