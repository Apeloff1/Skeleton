"""A field filter without a name or a value is not a silent match-all."""

import pytest

from skeleton.kernel.errors import RetrievalError
from skeleton.retrieval.query_language import QueryParser


def test_empty_field_is_rejected() -> None:
    with pytest.raises(RetrievalError):
        QueryParser.parse("tag:")
    with pytest.raises(RetrievalError):
        QueryParser.parse(":alpha")
    parsed = QueryParser.parse("tag:alpha")
    assert parsed[0].field == "tag"
    assert parsed[0].raw == "alpha"
