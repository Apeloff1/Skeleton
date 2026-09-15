"""Regression coverage for Jeeves local-provider policy handling."""

from skeleton.jeeves.llm_core import JeevesCore, SessionMode
from skeleton.jeeves.providers import LocalEchoProvider


class RecordingRetriever:
    def __init__(self):
        self.queries = []

    def retrieve(self, query, k=3):
        self.queries.append((query, k))
        return []


def test_local_fallback_preserves_mode_policy_in_prompt():
    retriever = RecordingRetriever()
    provider = LocalEchoProvider(retriever)
    core = JeevesCore(provider=provider)
    session = core.open_session("u", mode=SessionMode.DEBUG)

    core.ask(session.session_id, "find the bug")

    assert provider.supports_system_prompt is False
    assert retriever.queries == [
        ("You are a debugging assistant. Find the root cause.\n\nfind the bug", 3)
    ]
