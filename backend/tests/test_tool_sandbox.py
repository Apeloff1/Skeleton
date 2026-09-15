import pytest

from core.tool_sandbox import (
    CapabilityDenied,
    CapabilityGrant,
    CapabilitySandbox,
    ToolCapability,
    ToolMetadata,
    ToolRunContext,
)


def test_tool_metadata_exposes_declared_capabilities():
    metadata = ToolMetadata(
        "repo.inspect",
        required_capabilities=frozenset(
            {ToolCapability.FILESYSTEM_READ, ToolCapability.REPOSITORY_MUTATION}
        ),
        mutates=True,
    )

    assert metadata.snapshot() == {
        "name": "repo.inspect",
        "required_capabilities": [
            "filesystem.read",
            "repository.mutation",
        ],
        "mutates": True,
        "approval_required": False,
    }


def test_sensitive_capability_is_denied_by_default_before_handler_runs():
    sandbox = CapabilitySandbox()
    metadata = ToolMetadata(
        "shell.run",
        required_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )
    context = ToolRunContext(run_id="run-1", build_id="build-1")
    called = []

    def handler():
        called.append(True)

    with pytest.raises(CapabilityDenied, match="process.exec"):
        sandbox.invoke(metadata, handler, context=context)

    assert called == []
    assert sandbox.audit() == [
        {
            "kind": "capability.decision",
            "tool": "shell.run",
            "decision": "deny",
            "run_id": "run-1",
            "build_id": "build-1",
            "capability": "process.exec",
        }
    ]


def test_explicit_grant_allows_tool_and_audits_run_context():
    sandbox = CapabilitySandbox()
    metadata = ToolMetadata(
        "fetch.config",
        required_capabilities=frozenset(
            {ToolCapability.NETWORK, ToolCapability.SECRETS_READ}
        ),
    )
    context = ToolRunContext(run_id="run-2", build_id="build-2")
    grant = CapabilityGrant.of("network", "secrets.read")

    result = sandbox.invoke(
        metadata,
        lambda value: value + 1,
        context=context,
        grant=grant,
        kwargs={"value": 4},
    )

    assert result == 5
    audit = sandbox.audit()
    assert [row["decision"] for row in audit] == [
        "allow",
        "allow",
        "start",
        "success",
    ]
    assert [
        row.get("capability")
        for row in audit
        if row["kind"] == "capability.decision"
    ] == ["network", "secrets.read"]
    assert all(row["run_id"] == "run-2" for row in audit)
    assert all(row["build_id"] == "build-2" for row in audit)


def test_missing_capabilities_are_reported_in_deterministic_order():
    sandbox = CapabilitySandbox()
    metadata = ToolMetadata(
        "repo.publish",
        required_capabilities=frozenset(
            {
                ToolCapability.REPOSITORY_MUTATION,
                ToolCapability.NETWORK,
                ToolCapability.SECRETS_READ,
            }
        ),
    )

    with pytest.raises(
        CapabilityDenied,
        match=r"repository\.mutation, secrets\.read",
    ):
        sandbox.authorize(
            metadata,
            context=ToolRunContext(run_id="run-3"),
            grant=CapabilityGrant.of(ToolCapability.NETWORK),
        )

    decisions = [
        (row["capability"], row["decision"])
        for row in sandbox.audit()
    ]
    assert decisions == [
        ("network", "allow"),
        ("repository.mutation", "deny"),
        ("secrets.read", "deny"),
    ]


def test_unknown_or_non_normalized_capabilities_fail_closed():
    with pytest.raises(ValueError, match="unknown tool capability"):
        ToolMetadata(
            "bad.tool",
            required_capabilities=frozenset({"root"}),
        )

    with pytest.raises(ValueError, match="already be normalized"):
        CapabilityGrant.of(" Network ")


def test_handler_error_is_audited_without_persisting_exception_message():
    sandbox = CapabilitySandbox()
    metadata = ToolMetadata("safe.read")

    def handler():
        raise RuntimeError("secret internal detail")

    with pytest.raises(RuntimeError, match="secret internal detail"):
        sandbox.invoke(
            metadata,
            handler,
            context=ToolRunContext(run_id="run-4"),
        )

    error = sandbox.audit()[-1]
    assert error["kind"] == "tool.invoke"
    assert error["decision"] == "error"
    assert error["error_type"] == "RuntimeError"
    assert "secret internal detail" not in str(error)
