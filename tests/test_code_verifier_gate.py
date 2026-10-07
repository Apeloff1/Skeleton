"""Empty or ungrounded code is not accepted, even when the rubric looks high."""

import pytest

from skeleton.intelligence.verifier import CodeVerifier


def test_empty_code_and_a_missing_request_do_not_pass() -> None:
    verifier = CodeVerifier(accept_at=0.7)
    empty = verifier.verify("   ")
    assert empty.accepted is False
    assert empty.score == 0.0
    assert verifier.verdict("   ").confidence == 0.0

    code = "def total_price(items):\n    total = 0\n    return total\n"
    ungrounded = verifier.verify(code)
    assert ungrounded.accepted is False
    assert verifier.verdict(code).confidence == 0.0

    accepted = verifier.verify(code, request="compute the total price")
    assert accepted.accepted is True
    assert verifier.verdict(code, request="compute the total price").confidence > 0

    unsafe = verifier.verify(code + "\n    eval(items)\n", request="compute the total price")
    assert unsafe.accepted is False
    with pytest.raises(ValueError):
        CodeVerifier(accept_at=0)
