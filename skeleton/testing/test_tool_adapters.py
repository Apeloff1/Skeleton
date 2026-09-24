from __future__ import annotations

import pytest

from skeleton.skills.tool_adapters import (
    ArtifactAdapterPolicy,
    DatabaseAdapterPolicy,
    NetworkEgressPolicy,
    SandboxAdapterPolicy,
    ToolAdapterDenied,
)


def test_sandbox_rejects_unsupported_language_and_oversized_source() -> None:
    policy = SandboxAdapterPolicy(max_source_chars=4)

    with pytest.raises(ToolAdapterDenied, match="language"):
        policy.compile_request({"language": "python", "code": "print(1)"})

    with pytest.raises(ToolAdapterDenied, match="resource bound"):
        policy.compile_request({"language": "c", "code": "12345"})


def test_sandbox_rejects_nul_payload() -> None:
    with pytest.raises(ToolAdapterDenied, match="NUL"):
        SandboxAdapterPolicy().compile_request(
            {"language": "c", "code": "int main() {\x00}"}
        )


def test_database_scope_blocks_system_and_dangerous_server_side_operators() -> None:
    policy = DatabaseAdapterPolicy(max_limit=20)

    with pytest.raises(ToolAdapterDenied, match="outside database scope"):
        policy.query_request({"collection": "system.users"})

    with pytest.raises(ToolAdapterDenied, match=r"\$where"):
        policy.query_request(
            {
                "collection": "knowledge",
                "filter": {"$where": "sleep(1000)"},
            }
        )


def test_database_scope_can_be_explicit_allowlist_and_bounds_limit() -> None:
    policy = DatabaseAdapterPolicy(
        allowed_collections=frozenset({"knowledge", "facts"}),
        max_limit=5,
    )

    accepted = policy.query_request(
        {
            "collection": "knowledge",
            "filter": {"topic": "ai"},
            "project": {"_id": 0, "text": 1},
            "limit": 5,
        }
    )
    assert accepted["limit"] == 5

    with pytest.raises(ToolAdapterDenied, match="outside database scope"):
        policy.query_request({"collection": "secrets"})

    with pytest.raises(ToolAdapterDenied, match="within"):
        policy.query_request({"collection": "knowledge", "limit": 6})


def test_network_egress_bounds_query_count_and_result_scheme() -> None:
    policy = NetworkEgressPolicy(max_query_chars=10, max_results=3)

    assert policy.search_request({"query": "hello", "max_results": 3}) == {
        "query": "hello",
        "kind": "text",
        "max_results": 3,
    }

    with pytest.raises(ToolAdapterDenied, match="egress bound"):
        policy.search_request({"query": "x" * 11})

    with pytest.raises(ToolAdapterDenied, match="within"):
        policy.search_request({"query": "ok", "max_results": 4})

    assert policy.sanitize_result(
        {"title": "bad", "url": "file:///etc/passwd", "body": "x"}
    ) is None
    assert policy.sanitize_result(
        {"title": "ok", "url": "https://example.com/a", "body": "snippet"}
    ) == {
        "title": "ok",
        "url": "https://example.com/a",
        "snippet": "snippet",
    }


def test_artifact_scope_rejects_invalid_build_ids_and_unapproved_kinds() -> None:
    policy = ArtifactAdapterPolicy()

    with pytest.raises(ToolAdapterDenied, match="build_id"):
        policy.package_request({"build_id": "../escape", "kinds": ["zip"]})

    with pytest.raises(ToolAdapterDenied, match="not allowed"):
        policy.package_request({"build_id": "build-1", "kinds": ["exe"]})

    assert policy.package_request(
        {"build_id": "build-1", "kinds": ["zip", "zip", "apk"]}
    ) == {"build_id": "build-1", "kinds": ["zip", "apk"]}
