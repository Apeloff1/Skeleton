"""A question mark does not turn an acknowledgement into a memory."""

from skeleton.memory.distill import is_non_lexical, worth_remembering


def test_trailing_question_mark_stays_filler() -> None:
    assert is_non_lexical("ok?")
    assert is_non_lexical("thanks?")
    assert worth_remembering("ok?") is False
    assert worth_remembering("Did we decide the budget?") is True
