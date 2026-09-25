from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skeleton.ai.integrations.xai_oss import (
    CollectionsSearchSpec,
    ImageGenerationSpec,
    McpSpec,
    WebSearchSpec,
    XAIServerToolPolicy,
    XAIToolBuilder,
    XAIToolKind,
    XSearchSpec,
)


class _FakeTools:
    @staticmethod
    def web_search(**kwargs):
        return ("web_search", kwargs)

    @staticmethod
    def x_search(**kwargs):
        return ("x_search", kwargs)

    @staticmethod
    def code_execution():
        return ("code_execution", {})

    @staticmethod
    def collections_search(**kwargs):
        return ("collections_search", kwargs)

    @staticmethod
    def mcp(**kwargs):
        return ("mcp", kwargs)

    @staticmethod
    def image_generation(**kwargs):
        return ("image_generation", kwargs)


class _FakeSDK:
    pass


def _importer(name: str):
    if name == "xai_sdk":
        return _FakeSDK
    if name == "xai_sdk.tools":
        return _FakeTools
    raise ImportError(name)


def test_tool_policy_is_empty_by_default() -> None:
    builder = XAIToolBuilder(XAIServerToolPolicy(), importer=_importer)
    with pytest.raises(PermissionError):
        builder.code_execution()


def test_tool_policy_normalizes_string_kinds() -> None:
    policy = XAIServerToolPolicy(
        allowed_kinds=frozenset({"code_execution", XAIToolKind.WEB_SEARCH})
    )
    assert policy.allows(XAIToolKind.CODE_EXECUTION)
    assert policy.allows("web_search")


def test_web_search_filters_are_bounded_and_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        WebSearchSpec(allowed_domains=("a.com",), excluded_domains=("b.com",))
    with pytest.raises(ValueError, match="five"):
        WebSearchSpec(allowed_domains=tuple(f"{i}.example" for i in range(6)))
    with pytest.raises(ValueError, match="invalid"):
        WebSearchSpec(allowed_domains=("https://example.com",))

    builder = XAIToolBuilder(
        XAIServerToolPolicy(frozenset({XAIToolKind.WEB_SEARCH})),
        importer=_importer,
    )
    tool = builder.web_search(WebSearchSpec(allowed_domains=("example.com",)))
    assert tool[0] == "web_search"
    assert tool[1]["allowed_domains"] == ["example.com"]


def test_x_search_rejects_conflicts_and_invalid_ranges() -> None:
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    before = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="mutually exclusive"):
        XSearchSpec(allowed_handles=("xai",), excluded_handles=("spam",))
    with pytest.raises(ValueError, match="from_date"):
        XSearchSpec(from_date=now, to_date=before)
    with pytest.raises(ValueError, match="invalid X handle"):
        XSearchSpec(allowed_handles=("@xai",))


def test_remote_mcp_requires_https_and_explicit_tool_allowlist() -> None:
    with pytest.raises(ValueError, match="https"):
        McpSpec("http://mcp.example", ("read",))
    with pytest.raises(ValueError, match="allowlist"):
        McpSpec("https://mcp.example", ())

    builder = XAIToolBuilder(
        XAIServerToolPolicy(frozenset({XAIToolKind.MCP})),
        importer=_importer,
    )
    tool = builder.mcp(
        McpSpec("https://mcp.example", ("read", "search")),
        authorization="ephemeral-token",
    )
    assert tool[0] == "mcp"
    assert tool[1]["allowed_tool_names"] == ["read", "search"]
    assert tool[1]["authorization"] == "ephemeral-token"


def test_collection_and_image_specs_are_bounded() -> None:
    with pytest.raises(ValueError):
        CollectionsSearchSpec(())
    with pytest.raises(ValueError):
        CollectionsSearchSpec(tuple(str(i) for i in range(11)))
    with pytest.raises(ValueError):
        ImageGenerationSpec("unsafe")

    builder = XAIToolBuilder(
        XAIServerToolPolicy(
            frozenset(
                {
                    XAIToolKind.COLLECTIONS_SEARCH,
                    XAIToolKind.IMAGE_GENERATION,
                    XAIToolKind.CODE_EXECUTION,
                }
            )
        ),
        importer=_importer,
    )
    assert builder.collections_search(
        CollectionsSearchSpec(("c1",), retrieval_mode="semantic")
    )[0] == "collections_search"
    assert builder.image_generation(ImageGenerationSpec("edit"))[0] == "image_generation"
    assert builder.code_execution()[0] == "code_execution"
