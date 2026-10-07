"""Regression tests for checkout credential hardening detection."""

from pathlib import Path

from backend.scripts.check_workflow_security import (
    _checkout_credentials_disabled,
    _flow_checkout_credentials_disabled,
    violations,
)

CHECKOUT_SHA = "0123456789012345678901234567890123456789"
CHECKOUT_FINDING = "actions/checkout must set persist-credentials: false"


def test_checkout_persist_credentials_requires_with_mapping() -> None:
    lines = [
        f"      - uses: actions/checkout@{CHECKOUT_SHA}",
        "        env:",
        "          persist-credentials: false",
    ]

    assert not _checkout_credentials_disabled(lines, 0)


def test_checkout_persist_credentials_accepts_direct_with_input() -> None:
    lines = [
        f"      - uses: actions/checkout@{CHECKOUT_SHA}",
        "        with:",
        "          fetch-depth: 1",
        "          persist-credentials: false",
    ]

    assert _checkout_credentials_disabled(lines, 0)


def test_named_checkout_step_accepts_sibling_with_mapping() -> None:
    lines = [
        "      - name: Checkout repository",
        f"        uses: actions/checkout@{CHECKOUT_SHA}",
        "        with:",
        "          persist-credentials: false",
        "      - name: Next step",
        "        run: echo done",
    ]

    assert _checkout_credentials_disabled(lines, 1)


def test_checkout_persist_credentials_rejects_nested_non_input() -> None:
    lines = [
        f"      - uses: actions/checkout@{CHECKOUT_SHA}",
        "        with:",
        "          metadata:",
        "            persist-credentials: false",
    ]

    assert not _checkout_credentials_disabled(lines, 0)


def test_checkout_persist_credentials_accepts_inline_with_mapping() -> None:
    lines = [
        f"      - uses: actions/checkout@{CHECKOUT_SHA}",
        "        with: { fetch-depth: 1, persist-credentials: false }",
    ]

    assert _checkout_credentials_disabled(lines, 0)


def test_flow_checkout_persist_credentials_is_scoped_to_with() -> None:
    valid = (
        f"- {{ uses: actions/checkout@{CHECKOUT_SHA}, "
        "with: { persist-credentials: false } }"
    )
    invalid = (
        f"- {{ uses: actions/checkout@{CHECKOUT_SHA}, "
        "env: { persist-credentials: false } }"
    )

    assert _flow_checkout_credentials_disabled(valid)
    assert not _flow_checkout_credentials_disabled(invalid)


def _workflow_with_step(tmp_path: Path, step: str) -> Path:
    workflow = tmp_path / "checkout.yml"
    workflow.write_text(
        "\n".join(
            [
                "name: checkout-scope",
                "on: push",
                "permissions: {}",
                "jobs:",
                "  test:",
                "    runs-on: ubuntu-latest",
                "    steps:",
                f"      {step}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return workflow


def test_flow_checkout_with_input_passes_full_scanner(tmp_path: Path) -> None:
    workflow = _workflow_with_step(
        tmp_path,
        f"- {{ uses: actions/checkout@{CHECKOUT_SHA}, with: {{ persist-credentials: false }} }}",
    )

    assert not any(CHECKOUT_FINDING in finding for finding in violations(workflow))


def test_flow_checkout_env_bypass_fails_full_scanner(tmp_path: Path) -> None:
    workflow = _workflow_with_step(
        tmp_path,
        f"- {{ uses: actions/checkout@{CHECKOUT_SHA}, env: {{ persist-credentials: false }} }}",
    )

    assert any(CHECKOUT_FINDING in finding for finding in violations(workflow))
