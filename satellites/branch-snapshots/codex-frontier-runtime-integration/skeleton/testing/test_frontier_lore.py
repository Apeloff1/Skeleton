from skeleton.frontier.contracts import ProvenanceRecord
from skeleton.frontier.lore import LoreEntry, LoreIndex


def test_lore_index_filters_by_query_and_confidence():
    provenance = ProvenanceRecord(source_repository="Apeloff1/Lorebuffa", operation="promote")
    index = LoreIndex()
    index.upsert(LoreEntry("city", "The city has three gates", ("world",), 0.9, provenance))
    index.upsert(LoreEntry("rumor", "A hidden gate exists", ("rumor",), 0.3))

    assert [entry.key for entry in index.search("gates", minimum_confidence=0.8)] == ["city"]
    assert index.search("missing") == []


def test_lore_entry_validates_confidence_and_identity():
    try:
        LoreEntry("", "text")
    except ValueError:
        pass
    else:
        raise AssertionError("empty key must fail")

    try:
        LoreEntry("x", "text", confidence=1.1)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid confidence must fail")
