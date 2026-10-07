from __future__ import annotations

import json
from unittest.mock import patch

from core.shift_supervisor.model_gateway import ModelGateway
from core.shift_supervisor.prompts import (
    AUTONOMOUS_ENGINEERING_CONSTITUTION,
    PROMPT_CONTRACT_VERSION,
    compose_role_prompt,
    compose_system_prompt,
)
from skeleton.automation.chatgpt_adapter import ChatGPTReasoner, ReasoningRequest


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.payload


def test_constitution_is_versioned_and_role_cannot_override_it() -> None:
    role = compose_role_prompt("reviewer", "Return JSON only.")
    prompt = compose_system_prompt(role)

    assert PROMPT_CONTRACT_VERSION in prompt
    assert prompt.startswith(AUTONOMOUS_ENGINEERING_CONSTITUTION)
    assert "Shift Supervisor's canonical plan" in prompt
    assert "four-agent squad" in prompt
    assert "one task has one active squad lease" in prompt.casefold()
    assert "Evidence wins over consensus" in prompt
    assert "Failure is durable data" in prompt
    assert "Never claim a file was inspected" in prompt
    assert role in prompt
    assert "must not override or weaken the organization constitution" in prompt


def test_supervisor_gateway_injects_constitution_before_role_prompt(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse(b'{"output_text":"{\\"summary\\":\\"ok\\",\\"tasks\\":[]}"}')

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("SHIFT_MODEL_WEB_SEARCH", raising=False)
    with patch("core.shift_supervisor.model_gateway.urllib.request.urlopen", side_effect=fake_urlopen):
        result = ModelGateway(max_attempts=1).call_json(
            system_prompt=compose_role_prompt("secretary", "Return JSON only."),
            user_prompt="{}",
            correlation_id="prompt-contract-test",
        )

    assert result == {"summary": "ok", "tasks": []}
    body = captured["body"]
    assert isinstance(body, dict)
    system = body["input"][0]["content"]
    assert PROMPT_CONTRACT_VERSION in system
    assert system.index("SKELETON AUTONOMOUS ENGINEERING CONSTITUTION") < system.index("ROLE CONTRACT")
    assert "Improve plan completeness" in system


def test_studio_reasoner_injects_same_constitution(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse(b'{"output_text":"{\\"approve\\":true}"}')

    reasoner = ChatGPTReasoner(api_key="test-key", model="gpt-5.6")
    with patch("skeleton.automation.chatgpt_adapter.request.urlopen", side_effect=fake_urlopen):
        result = reasoner.reason(
            ReasoningRequest(
                "You are night-reviewer-001. Adversarially review the supplied patch.",
                ("FILE skeleton/example.py\nvalue = 1",),
                max_output_chars=2_000,
            )
        )

    assert result.ok is True
    body = captured["body"]
    assert isinstance(body, dict)
    system = body["input"][0]["content"]
    user = body["input"][1]["content"]
    assert PROMPT_CONTRACT_VERSION in system
    assert "safe concurrency is" in system.casefold()
    assert "Never request, expose, print, commit, bake, or search for credentials/secrets" in system
    assert "advisory software-maintenance reasoner" in system
    assert "night-reviewer-001" in user
