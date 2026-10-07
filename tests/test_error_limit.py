"""A negative error report must not drop the most common failure."""

import pytest

from skeleton.intelligence.error_taxonomy import ErrorTaxonomy


def test_negative_top_errors_limit_is_rejected() -> None:
    taxonomy = ErrorTaxonomy()
    taxonomy.record("api", TimeoutError("request timed out"))
    taxonomy.record("api", TimeoutError("request timed out"))
    taxonomy.record("api", ValueError("bad"))
    with pytest.raises(ValueError):
        taxonomy.top_errors(-1)
    assert taxonomy.top_errors(0) == []
    assert taxonomy.top_errors(1)[0]["count"] == 2
