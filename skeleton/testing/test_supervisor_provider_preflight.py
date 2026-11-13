"""Fail-closed configuration admission for repository Supervisor workers."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "supervisor.yml"
MODEL = ROOT / "skeleton" / "automation" / "free_model.py"


def test_secretary_requires_model_provider_before_any_worker_dispatch() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    secretary = text.split("\n  secretary:\n", 1)[1]
    preflight = secretary.index(
        "- name: Require configured repository automation provider"
    )
    checkout = secretary.index("- name: Checkout immutable admitted commit")
    dispatch = secretary.index("- name: Admit delegation and dispatch bounded workers")
    assert preflight < checkout < dispatch
    assert "set -euo pipefail" in secretary[preflight:checkout]
    assert "configuration_required:" in secretary[preflight:checkout]
    for name in ("MODEL_API_URL", "MODEL_NAME", "MODEL_API_KEY"):
        assert f'! "${{{name}:-}}" =~ [^[:space:]]' in secretary[preflight:checkout]


def test_preflight_does_not_disclose_credentials_or_disable_read_only_plan() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    plan, secretary = text.split("\n  secretary:\n", 1)
    assert "permissions: {}" in plan
    assert "contents: read" in plan
    assert "MODEL_API_KEY: ${{ secrets.MODEL_API_KEY }}" in secretary
    preflight = secretary.split(
        "- name: Require configured repository automation provider", 1
    )[1].split("- name: Checkout immutable admitted commit", 1)[0]
    assert "echo \"$MODEL_API_KEY\"" not in preflight
    assert "printenv" not in preflight
    assert "exit 1" in preflight


def test_automation_model_provider_requires_all_three_fields() -> None:
    source = MODEL.read_text(encoding="utf-8")
    for name in ("MODEL_API_URL", "MODEL_NAME", "MODEL_API_KEY"):
        assert name in source
    assert "MODEL_API_URL, MODEL_API_KEY and MODEL_NAME are required" in source


def test_whitespace_only_provider_configuration_fails_before_dispatch() -> None:
    """Whitespace-only Actions variables must not admit a worker."""
    import os
    import subprocess
    import textwrap

    workflow = WORKFLOW.read_text(encoding="utf-8")
    preflight = workflow.split(
        "- name: Require configured repository automation provider", 1
    )[1].split("- name: Checkout immutable admitted commit", 1)[0]
    script = textwrap.dedent(preflight.split("run: |", 1)[1])
    for empty_name in ("MODEL_API_URL", "MODEL_NAME", "MODEL_API_KEY"):
        values = {
            "MODEL_API_URL": "https://example.org/v1/chat/completions",
            "MODEL_NAME": "test-model",
            "MODEL_API_KEY": "DO_NOT_PRINT_TEST_KEY",
        }
        values[empty_name] = "  \t  "
        result = subprocess.run(
            ["bash", "-c", script],
            env={**os.environ, **values},
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0, empty_name
        assert "configuration_required" in result.stdout
        assert "DO_NOT_PRINT_TEST_KEY" not in result.stdout + result.stderr


def test_model_client_refuses_redirects_that_could_expose_credentials(
    monkeypatch,
) -> None:
    """Only the configured HTTPS origin may receive the model bearer token."""
    import io
    import urllib.request

    from skeleton.automation import free_model

    handler = free_model._RejectRedirects()
    request = urllib.request.Request(
        "https://models.example/v1/chat/completions",
        data=b"{}",
        headers={"Authorization": "Bearer DO_NOT_FORWARD"},
        method="POST",
    )
    assert handler.redirect_request(
        request, None, 302, "Found", {},
        "https://untrusted.example/collect",
    ) is None
    assert handler.redirect_request(
        request, None, 307, "Temporary Redirect", {},
        "https://models.example/other-path",
    ) is None

    observed = []

    class FakeOpener:
        def open(self, request, timeout):
            assert timeout == 5
            assert request.get_header("Authorization") == "Bearer DO_NOT_FORWARD"
            return io.BytesIO(b'{"choices":[{"message":{"content":"accepted"}}]}')

    def capture_opener(*handlers):
        observed.extend(handlers)
        return FakeOpener()

    monkeypatch.setattr(urllib.request, "build_opener", capture_opener)
    client = object.__new__(free_model.FreeModelClient)
    client.url = "https://models.example/v1/chat/completions"
    client.key = "DO_NOT_FORWARD"
    client.model = "test-model"
    client.timeout = 5
    assert client.chat("safe system", "safe request") == "accepted"
    assert len(observed) == 1
    assert isinstance(observed[0], free_model._RejectRedirects)


def test_provider_transport_failure_never_exposes_untrusted_exception_text(
    monkeypatch,
) -> None:
    """Arbitrary provider diagnostics must not reach worker traceback logs."""
    import traceback
    import urllib.error
    import urllib.request

    import pytest

    from skeleton.automation import free_model

    sentinel = "UNREDACTABLE_PROVIDER_CREDENTIAL_SENTINEL"

    class FailingOpener:
        def open(self, request, timeout):
            raise urllib.error.URLError(f"provider diagnostic: {sentinel}")

    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *handlers: FailingOpener()
    )
    client = object.__new__(free_model.FreeModelClient)
    client.url = "https://models.example/v1/chat/completions"
    client.key = "DO_NOT_PRINT"
    client.model = "test-model"
    client.timeout = 5

    with pytest.raises(free_model.ModelError) as raised:
        client.chat("system", "request")
    assert str(raised.value) == "model request failed"
    assert raised.value.__suppress_context__ is True
    assert sentinel not in "".join(traceback.format_exception(raised.value))
