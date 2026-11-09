from __future__ import annotations

import pytest

from skeleton.ai.integrations.openai_oss import TiktokenTokenizer


class _Encoding:
    name = "fake-bpe"

    def encode(self, text: str, **kwargs):
        if "<SPECIAL>" in text and kwargs.get("disallowed_special", "all") != ():
            raise ValueError("special token text rejected")
        return list(text.encode("utf-8"))

    def decode(self, tokens):
        return bytes(tokens).decode("utf-8", errors="ignore")


class _Tiktoken:
    @staticmethod
    def encoding_for_model(model):
        assert model == "gpt-test"
        return _Encoding()

    @staticmethod
    def get_encoding(name):
        assert name == "test-encoding"
        return _Encoding()


def _importer(name: str):
    assert name == "tiktoken"
    return _Tiktoken


def test_tiktoken_adapter_counts_and_truncates_exactly() -> None:
    tokenizer = TiktokenTokenizer(model="gpt-test", importer=_importer)
    count = tokenizer.count("hello")
    assert count.encoding_name == "fake-bpe"
    assert count.token_count == 5
    assert count.character_count == 5
    assert tokenizer.fits("hello", maximum_tokens=5)
    assert not tokenizer.fits("hello!", maximum_tokens=5)
    assert tokenizer.truncate("hello!", maximum_tokens=5) == "hello"


def test_tiktoken_special_token_text_is_fail_closed_by_default() -> None:
    tokenizer = TiktokenTokenizer(encoding_name="test-encoding", importer=_importer)
    with pytest.raises(ValueError):
        tokenizer.encode("<SPECIAL>")
    assert tokenizer.encode("<SPECIAL>", allow_special_text=True)


def test_tiktoken_requires_exactly_one_selector() -> None:
    with pytest.raises(ValueError):
        TiktokenTokenizer(importer=_importer)
    with pytest.raises(ValueError):
        TiktokenTokenizer(model="a", encoding_name="b", importer=_importer)
