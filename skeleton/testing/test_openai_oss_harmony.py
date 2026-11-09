from __future__ import annotations

from enum import Enum

from skeleton.ai.integrations.openai_oss import (
    HarmonyGptOssCodec,
    HarmonyInputMessage,
)


class _Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    DEVELOPER = "developer"
    TOOL = "tool"


class _Author:
    def __init__(self, role):
        self.role = role


class _Content:
    def __init__(self, text):
        self.text = text


class _Message:
    def __init__(self, role, content):
        self.author = _Author(role)
        self.content = [_Content(content)]
        self.channel = None
        self.recipient = None

    @classmethod
    def from_role_and_content(cls, role, content):
        return cls(role, content)

    def with_channel(self, channel):
        self.channel = channel
        return self

    def with_recipient(self, recipient):
        self.recipient = recipient
        return self


class _Conversation:
    def __init__(self, messages):
        self.messages = list(messages)

    @classmethod
    def from_messages(cls, messages):
        return cls(messages)


class _Names:
    HARMONY_GPT_OSS = "HarmonyGptOss"


class _Encoding:
    def render_conversation_for_completion(self, conversation, role):
        assert role is _Role.ASSISTANT
        return [len(conversation.messages), 99]

    def parse_messages_from_completion_tokens(self, tokens, role=None, strict=True):
        assert tokens == [7, 8]
        analysis = _Message(_Role.ASSISTANT, "private model reasoning")
        analysis.channel = "analysis"
        final = _Message(_Role.ASSISTANT, "answer")
        final.channel = "final"
        return [analysis, final]


class _Harmony:
    Role = _Role
    Message = _Message
    Conversation = _Conversation
    HarmonyEncodingName = _Names

    @staticmethod
    def load_harmony_encoding(name):
        assert name == "HarmonyGptOss"
        return _Encoding()


def _importer(name: str):
    assert name == "openai_harmony"
    return _Harmony


def test_harmony_codec_renders_provider_neutral_messages() -> None:
    codec = HarmonyGptOssCodec(importer=_importer)
    prompt = codec.render_for_completion(
        (
            HarmonyInputMessage("developer", "policy"),
            HarmonyInputMessage("user", "question"),
        )
    )
    assert prompt.tokens == (2, 99)
    assert len(prompt.digest) == 64


def test_harmony_analysis_channel_is_not_user_facing_by_default() -> None:
    codec = HarmonyGptOssCodec(importer=_importer)
    visible = codec.parse_completion((7, 8))
    assert [item.content for item in visible] == ["answer"]
    assert visible[0].channel == "final"

    research = codec.parse_completion((7, 8), include_analysis=True)
    assert [item.channel for item in research] == ["analysis", "final"]
