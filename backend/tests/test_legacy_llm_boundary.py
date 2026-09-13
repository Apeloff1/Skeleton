"""Regression tests for the optional legacy LLM import boundary."""


def test_legacy_llm_symbols_import_without_third_party_dependency():
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    assert UserMessage("hello").args == ("hello",)
    assert LlmChat.__name__ == "LlmChat"


def test_legacy_llm_adapter_fails_closed_if_instantiated():
    from emergentintegrations.llm.chat import LlmChat

    try:
        LlmChat()
    except RuntimeError as exc:
        assert "consolidated AI integration boundary" in str(exc)
    else:
        raise AssertionError("retired LlmChat adapter must fail closed")
