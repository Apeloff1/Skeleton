"""Empty text is not a sentence, and a custom extractor cannot return a guess."""

import pytest

from skeleton.retrieval.extraction import TripleExtractor


def test_empty_text_and_bad_custom_extractor() -> None:
    extractor = TripleExtractor()
    assert extractor.extract("   ") == []
    assert extractor.stats()["sentences"] == 0
    with pytest.raises(TypeError):
        extractor.extract(None)  # type: ignore[arg-type]
    found = extractor.extract("Skeleton is a runtime for agents.")
    assert ("Skeleton", "is_a", "runtime for agents") in found or any(
        item[0] == "Skeleton" and item[1] == "is_a" for item in found
    )
    custom = TripleExtractor(custom=lambda text: None)
    with pytest.raises(ValueError):
        custom.extract("Skeleton is a runtime.")
