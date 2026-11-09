"""A repeated key is not a document, and a tuple is not JSON."""

import pytest

from skeleton.jeeves.planning.serialization import dumps, loads


def test_a_duplicate_key_is_refused() -> None:
    with pytest.raises(ValueError):
        loads('{"a": 1, "a": 2}')
    with pytest.raises(ValueError):
        dumps((1, 2))
    with pytest.raises(ValueError):
        dumps({"n": float("nan")})
    assert loads(dumps({"a": 1, "b": [True, None]})) == {"a": 1, "b": [True, None]}
