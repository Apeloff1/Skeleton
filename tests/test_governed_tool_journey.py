"""A governed tool result can support an answer only by what it stored."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from skeleton.skills.tool_contract import ToolExecutionRequest, ToolExecutionStatus
from skeleton.skills.tool_runtime import ToolRuntime
from skeleton.intelligence.grounded_journey import GroundedJourney
from skeleton.skills.tool_adapters.surface import GovernedToolSurface


def _request(tool_id: str, arguments: dict, *, operation_id: str | None = None) -> ToolExecutionRequest:
    return ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=operation_id or str(uuid4()),
        tenant_id="tenant-a",
        tool_id=tool_id,
        idempotency_key="idem-1",
        arguments=arguments,
        requested_at=datetime.now(timezone.utc),
    )


def _surface() -> tuple[ToolRuntime, GovernedToolSurface]:
    def database(request):
        return {"rows": [{"name": "ada", "role": "maintainer"}]}

    def network(request):
        return {
            "results": [
                {"title": "Docs", "url": "https://example.com/docs", "snippet": "public index page"},
                {"title": "Local", "url": "http://127.0.0.1/secret", "snippet": "secret metadata"},
            ]
        }

    def sandbox(request):
        raise AssertionError("sandbox port should not be called")

    def artifacts(request):
        return {"artifact_id": request["build_id"], "bytes": 128}

    runtime = ToolRuntime()
    surface = GovernedToolSurface(
        database=database,
        network=network,
        sandbox=sandbox,
        artifacts=artifacts,
    )
    surface.register(runtime)
    return runtime, surface


def test_forbidden_query_never_reaches_the_database() -> None:
    runtime, surface = _surface()
    surface.database = lambda request: (_ for _ in ()).throw(AssertionError("port called"))
    journey = GroundedJourney(runtime, surface)
    result = journey.run(
        _request("repository.query", {"collection": "notes", "filter": {"$where": "this.a == 1"}}),
        "Ada is the maintainer.",
    )
    assert surface.calls == []
    assert result.disposition == "block"
    assert result.receipt_status == ToolExecutionStatus.FAILED.value
    assert result.error_code == "ToolAdapterDenied"


def test_stored_row_grounds_the_answer_and_replay_does_not_call_again() -> None:
    runtime, surface = _surface()
    journey = GroundedJourney(runtime, surface)
    operation_id = str(uuid4())
    request = _request(
        "repository.query",
        {"collection": "notes", "filter": {"name": "ada"}},
        operation_id=operation_id,
    )
    result = journey.run(request, "Ada is the maintainer.")
    assert result.disposition == "answer"
    assert result.citations
    assert "maintainer" in result.citations[0].excerpt
    replay = _request(
        "repository.query",
        {"collection": "notes", "filter": {"name": "ada"}},
        operation_id=operation_id,
    )
    # Same operation, same answer, new request id. The tool idempotency key
    # still matches, so the port must not run a second time.
    replay = ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=operation_id,
        tenant_id="tenant-a",
        tool_id="repository.query",
        idempotency_key="idem-1",
        arguments={"collection": "notes", "filter": {"name": "ada"}},
        requested_at=datetime.now(timezone.utc),
    )
    again = journey.run(replay, "Ada is the maintainer.")
    assert again.disposition == "answer"
    assert len(surface.calls) == 1


def test_invented_sentence_qualifies_and_a_different_replay_conflicts() -> None:
    runtime, surface = _surface()
    journey = GroundedJourney(runtime, surface)
    operation_id = str(uuid4())
    result = journey.run(
        _request(
            "repository.query",
            {"collection": "notes"},
            operation_id=operation_id,
        ),
        "Ada is the maintainer. The service runs on mars.",
    )
    assert result.disposition == "qualified"
    assert result.ungrounded_sentences == ("The service runs on mars.",)
    with pytest.raises(ValueError):
        journey.run(
            ToolExecutionRequest(
                request_id=str(uuid4()),
                operation_id=operation_id,
                tenant_id="tenant-a",
                tool_id="repository.query",
                idempotency_key="idem-2",
                arguments={"collection": "notes"},
                requested_at=datetime.now(timezone.utc),
            ),
            "Something else entirely.",
        )


def test_private_search_hits_are_not_quotable() -> None:
    runtime, surface = _surface()
    journey = GroundedJourney(runtime, surface)
    result = journey.run(
        _request("network.search", {"query": "docs"}),
        "Secret metadata is available. Public index page.",
    )
    excerpts = " ".join(citation.excerpt for citation in result.citations)
    assert "secret" not in excerpts.lower()
    assert "public index page" in excerpts
    assert result.disposition == "qualified"


def test_disallowed_language_does_not_enter_the_sandbox() -> None:
    runtime, surface = _surface()
    journey = GroundedJourney(runtime, surface)
    result = journey.run(
        _request("sandbox.compile", {"language": "python", "code": "print(1)"}),
        "print(1)",
    )
    assert surface.calls == []
    assert result.disposition == "block"
    assert result.error_code == "ToolAdapterDenied"


def test_negation_is_not_supported_by_a_positive_quote() -> None:
    runtime, surface = _surface()
    journey = GroundedJourney(runtime, surface)
    result = journey.run(
        _request("repository.query", {"collection": "notes"}),
        "Ada is not the maintainer.",
    )
    assert result.disposition == "abstain"
    assert result.ungrounded_sentences == ("Ada is not the maintainer.",)


def test_citation_budget_does_not_skip_ahead() -> None:
    from skeleton.skills.tool_adapters.citations import Citation, pack_citations

    citations = (
        Citation("a", "ref", "one", 2),
        Citation("b", "ref", "two two", 5),
        Citation("c", "ref", "three", 1),
    )
    packed = pack_citations(citations, budget_tokens=3)
    assert [item.citation_id for item in packed] == ["a"]


def test_a_broken_port_is_not_reported_as_a_policy_denial() -> None:
    runtime, surface = _surface()
    surface.database = lambda request: "not-an-object"
    journey = GroundedJourney(runtime, surface)
    result = journey.run(
        _request("repository.query", {"collection": "notes"}),
        "Ada is the maintainer.",
    )
    assert surface.calls
    assert result.disposition == "block"
    assert result.error_code == "ToolRuntimeError"
