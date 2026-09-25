"""An empty prefix does not cost a token."""

from skeleton.memory.prefix_renderer import estimate_tokens


def test_empty_text_is_zero_tokens() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
