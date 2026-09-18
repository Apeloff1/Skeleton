"""Offline regressions for the generated-code sandbox and injection corpus.

These tests exercise the production mediator rather than fixture presence.
Scanner and test failures must fail closed; untrusted model/tool output cannot
weaken the sealed deny-by-default policy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.frontier.orchestration import (
    CanonicalOrchestrator,
    ToolCapability,
    ToolInvocation,
    ToolRegistry,
    TurnOutcome,
)
from skeleton.kernel.sandbox import Capability, Sandbox
from skeleton.security.generated_code_sandbox import (
    GeneratedCodeSandbox,
    Operation,
    OperationKind,
    PayloadKind,
    SandboxCapability,
    SandboxPolicyError,
)
from skeleton.security.injection_corpus import (
    CorpusCase,
    evaluate_corpus,
    injection_corpus,
    main as corpus_main,
    scan_injection_corpus,
)


def _sandbox(tmp_path: Path, **kwargs) -> GeneratedCodeSandbox:
    box = GeneratedCodeSandbox(workspace_root=tmp_path, **kwargs)
    box.seal()
    return box


def test_corpus_is_deterministic_bounded_and_covers_required_classes() -> None:
    first = injection_corpus()
    second = injection_corpus()
    assert first == second
    assert 16 <= len(first) <= 48
    assert [case.case_id for case in first] == sorted(case.case_id for case in first)
    assert {case.category for case in first} >= {
        "prompt_injection",
        "tool_escalation",
        "path_escape",
        "secret_exfiltration",
        "unsafe_subprocess",
        "network_pivot",
        "capability_widening",
    }
    joined = "\n".join(case.payload for case in first)
    assert "BEGIN" not in joined
    assert "ghp_" not in joined
    assert "sk-" not in joined
    assert "AKIA" not in joined


def test_default_grants_deny_every_corpus_case_and_keep_policy_frozen(tmp_path: Path) -> None:
    denied, allowed = evaluate_corpus(workspace_root=str(tmp_path))
    assert allowed == 0
    assert denied == len(injection_corpus())
    findings = scan_injection_corpus()
    assert findings == []


def test_corpus_scanner_fails_closed_on_live_secret_shaped_fixture() -> None:
    toxic = CorpusCase(
        "zz-secret",
        "secret_exfiltration",
        'token = "sk-this-is-not-a-real-key-value"',
        PayloadKind.PYTHON,
        "scanner must reject secret-shaped fixtures",
    )
    findings = scan_injection_corpus((toxic,))
    assert any("live secret" in finding for finding in findings)


def test_corpus_scanner_fails_closed_when_empty() -> None:
    findings = scan_injection_corpus(())
    assert findings
    assert any("empty" in finding for finding in findings)


def test_corpus_scanner_fails_closed_when_a_case_would_pass(tmp_path: Path) -> None:
    benign = CorpusCase(
        "zz-open",
        "prompt_injection",
        "x = 1 + 1",
        PayloadKind.PYTHON,
        "control case used only to prove the scanner cannot silently pass",
    )
    findings = scan_injection_corpus((benign,))
    assert any("allowed" in finding or "minimum" in finding for finding in findings)


def test_corpus_scanner_fails_closed_on_loader_exception(monkeypatch) -> None:
    def broken():
        raise RuntimeError("loader exploded")

    monkeypatch.setattr("skeleton.security.injection_corpus.injection_corpus", broken)
    findings = scan_injection_corpus()
    assert findings
    assert "loader failed" in findings[0]


def test_corpus_main_fails_closed_when_scan_raises(monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("scan exploded")

    monkeypatch.setattr("skeleton.security.injection_corpus.scan_injection_corpus", boom)
    assert corpus_main() == 1


def test_corpus_main_fails_closed_on_findings(monkeypatch) -> None:
    monkeypatch.setattr(
        "skeleton.security.injection_corpus.scan_injection_corpus",
        lambda: ["adversarial payload was allowed"],
    )
    assert corpus_main() == 1


def test_malicious_text_cannot_change_sealed_policy(tmp_path: Path) -> None:
    box = _sandbox(tmp_path)
    before = box.granted_capabilities()
    for case in injection_corpus():
        decision = box.ingest_untrusted(case.payload, kind=case.kind)
        assert decision.policy_changed is False
        assert box.granted_capabilities() == before == frozenset()
        with pytest.raises(SandboxPolicyError, match="sealed"):
            box.grant(SandboxCapability.NETWORK)


def test_generated_code_has_no_authority_beyond_explicit_grants(tmp_path: Path) -> None:
    workspace_file = tmp_path / "notes.txt"
    workspace_file.write_text("ok", encoding="utf-8")
    denied = _sandbox(tmp_path)
    with pytest.raises(SandboxPolicyError, match="missing capability"):
        denied.attempt(Operation(OperationKind.FS_READ, str(workspace_file), SandboxCapability.FILESYSTEM))

    allowed = GeneratedCodeSandbox(
        workspace_root=tmp_path,
        grants={SandboxCapability.FILESYSTEM},
    )
    allowed.seal()
    read_ok = Operation(
        OperationKind.FS_READ,
        str(workspace_file),
        SandboxCapability.FILESYSTEM,
    )
    assert allowed.attempt(read_ok) == "ok"
    with pytest.raises(SandboxPolicyError, match="path escapes"):
        allowed.attempt(
            Operation(OperationKind.FS_READ, "/etc/passwd", SandboxCapability.FILESYSTEM)
        )
    with pytest.raises(SandboxPolicyError, match="missing capability"):
        allowed.attempt(
            Operation(
                OperationKind.NETWORK,
                "https://example.invalid",
                SandboxCapability.NETWORK,
            )
        )


def test_filesystem_network_process_attempts_outside_grant_fail_closed(tmp_path: Path) -> None:
    box = GeneratedCodeSandbox(
        workspace_root=tmp_path,
        grants={SandboxCapability.FILESYSTEM},
        network_allowlist=("example.invalid",),
        process_allowlist=("python",),
    )
    box.seal()
    inside = tmp_path / "safe.txt"
    box.attempt(Operation(OperationKind.FS_WRITE, str(inside), SandboxCapability.FILESYSTEM, "hello"))
    assert inside.read_text(encoding="utf-8") == "hello"

    with pytest.raises(SandboxPolicyError, match="path escapes"):
        box.attempt(
            Operation(
                OperationKind.FS_READ,
                str(tmp_path / ".." / "passwd"),
                SandboxCapability.FILESYSTEM,
            )
        )
    with pytest.raises(SandboxPolicyError, match="path escapes"):
        box.attempt(Operation(OperationKind.FS_READ, "%2e%2e/etc/passwd", SandboxCapability.FILESYSTEM))
    with pytest.raises(SandboxPolicyError, match="missing capability network"):
        box.attempt(Operation(OperationKind.NETWORK, "https://example.invalid", SandboxCapability.NETWORK))
    with pytest.raises(SandboxPolicyError, match="missing capability process"):
        box.attempt(Operation(OperationKind.PROCESS, "python", SandboxCapability.PROCESS))


def test_network_and_process_grants_still_fail_closed_outside_allowlist(tmp_path: Path) -> None:
    box = GeneratedCodeSandbox(
        workspace_root=tmp_path,
        grants={SandboxCapability.NETWORK, SandboxCapability.PROCESS},
        network_allowlist=("allowed.example.invalid",),
        process_allowlist=("python",),
    )
    box.seal()
    assert box.attempt(
        Operation(OperationKind.NETWORK, "https://allowed.example.invalid/x", SandboxCapability.NETWORK)
    ).startswith("authorized-network")
    with pytest.raises(SandboxPolicyError, match="network target"):
        box.attempt(
            Operation(
                OperationKind.NETWORK,
                "http://169.254.169.254/latest/meta-data/",
                SandboxCapability.NETWORK,
            )
        )
    with pytest.raises(SandboxPolicyError, match="network target"):
        box.attempt(Operation(OperationKind.NETWORK, "http://127.0.0.1:1", SandboxCapability.NETWORK))
    with pytest.raises(SandboxPolicyError, match="network target"):
        box.attempt(Operation(OperationKind.NETWORK, "file:///etc/passwd", SandboxCapability.NETWORK))
    with pytest.raises(SandboxPolicyError, match="process target"):
        box.attempt(Operation(OperationKind.PROCESS, "/bin/sh", SandboxCapability.PROCESS, "shell=True"))
    with pytest.raises(SandboxPolicyError, match="process target"):
        box.attempt(Operation(OperationKind.PROCESS, "python", SandboxCapability.PROCESS, "python; rm -rf /"))


def test_parse_failure_fails_closed_and_does_not_pass(tmp_path: Path) -> None:
    decision = _sandbox(tmp_path).admit("def broken(:\n", kind=PayloadKind.PYTHON)
    assert decision.allowed is False
    assert "failed to parse" in decision.reason


def test_oversized_payload_fails_closed(tmp_path: Path) -> None:
    decision = _sandbox(tmp_path).admit("x" * 40_000, kind=PayloadKind.PROMPT)
    assert decision.allowed is False
    assert "exceeds bound" in decision.reason


def test_benign_generated_code_is_admitted_without_sensitive_effects(tmp_path: Path) -> None:
    decision = _sandbox(tmp_path).admit("value = 1 + 1\nresult = value * 2\n")
    assert decision.allowed is True
    assert decision.policy_changed is False


def test_kernel_capability_contract_remains_deny_by_default() -> None:
    kernel = Sandbox()
    with pytest.raises(Exception, match="lacks capability"):
        kernel.require("generated-code", Capability.NET_EGRESS, "host:example.invalid")
    kernel.grant("generated-code", Capability.FS_READ, scope="/workspace*")
    assert kernel.can("generated-code", Capability.FS_READ, "/workspace/file.txt")
    assert not kernel.can("generated-code", Capability.FS_WRITE, "/workspace/file.txt")


def test_partial_kernel_filesystem_grant_cannot_widen_to_write(tmp_path: Path) -> None:
    kernel = Sandbox()
    kernel.grant("generated-code", Capability.FS_READ, scope="*")
    box = GeneratedCodeSandbox(tmp_path, kernel=kernel)
    box.seal()

    source = tmp_path / "source.txt"
    source.write_text("readable", encoding="utf-8")
    read = Operation(
        OperationKind.FS_READ,
        str(source),
        SandboxCapability.FILESYSTEM,
    )
    write = Operation(
        OperationKind.FS_WRITE,
        str(tmp_path / "written.txt"),
        SandboxCapability.FILESYSTEM,
        "nope",
    )

    assert box.authorize(read).allowed is True
    assert box.authorize(write).allowed is False
    assert "fs.write" in box.authorize(write).reason
    assert SandboxCapability.FILESYSTEM not in box.granted_capabilities()


def test_tool_capability_strings_align_with_orchestrator_without_self_grant(tmp_path: Path) -> None:
    box = GeneratedCodeSandbox(
        workspace_root=tmp_path,
        grants={ToolCapability.FILESYSTEM},
    )
    box.seal()
    assert SandboxCapability.FILESYSTEM in box.granted_capabilities()
    with pytest.raises(ValueError, match="unknown sandbox capability"):
        GeneratedCodeSandbox(tmp_path, grants={ToolCapability.REPOSITORY_MUTATION})


def test_model_tool_output_cannot_self_grant_on_canonical_orchestrator() -> None:
    called = False

    class Driver:
        async def next_turn(self, *, run, tool_results):
            return TurnOutcome(
                tool_calls=(
                    ToolInvocation(
                        "network-call",
                        "fetch",
                        {"capabilities": ["network", "process"], "url": "http://169.254.169.254/"},
                    ),
                )
            )

    def fetch(_arguments):
        nonlocal called
        called = True
        return "should not run"

    async def run():
        tools = ToolRegistry()
        tools.register("fetch", fetch, capabilities={ToolCapability.NETWORK})
        return await CanonicalOrchestrator(tools=tools).run(Driver())

    import asyncio

    record = asyncio.run(run())
    assert called is False
    assert record.status.value == "failed"
    assert "denied capabilities: network" in record.error


def test_mutating_corpus_payload_as_tool_json_cannot_widen_sandbox(tmp_path: Path) -> None:
    box = _sandbox(tmp_path)
    payload = json.dumps({
        "name": "fetch",
        "capabilities": ["network", "filesystem", "process", "secrets"],
        "arguments": {"url": "http://10.0.0.1/"},
    })
    decision = box.admit(payload, kind=PayloadKind.TOOL_JSON)
    assert decision.allowed is False
    assert box.granted_capabilities() == frozenset()


def test_secret_path_requires_secrets_even_inside_workspace(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=REDACTED_SECRET_PLACEHOLDER\n", encoding="utf-8")
    fs_only = GeneratedCodeSandbox(tmp_path, grants={SandboxCapability.FILESYSTEM})
    fs_only.seal()
    with pytest.raises(SandboxPolicyError, match="secret-bearing path"):
        fs_only.attempt(Operation(OperationKind.FS_READ, str(env_file), SandboxCapability.FILESYSTEM))

    both = GeneratedCodeSandbox(
        tmp_path,
        grants={SandboxCapability.FILESYSTEM, SandboxCapability.SECRETS},
    )
    both.seal()
    assert "REDACTED_SECRET_PLACEHOLDER" in both.attempt(
        Operation(OperationKind.FS_READ, str(env_file), SandboxCapability.FILESYSTEM)
    )


def test_each_corpus_case_records_a_fail_closed_production_decision(tmp_path: Path) -> None:
    for case in injection_corpus():
        box = _sandbox(tmp_path)
        decision = box.admit(case.payload, kind=case.kind)
        assert decision.allowed is False, case.case_id
        assert decision.policy_changed is False, case.case_id
        assert decision.to_dict()["allowed"] is False
