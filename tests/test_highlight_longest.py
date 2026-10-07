"""A shorter query term must not steal the match from a longer one."""

from skeleton.retrieval.highlight import Highlighter
from skeleton.retrieval.query_language import QueryTerm


def test_longer_term_wins_the_span() -> None:
    marked = Highlighter().highlight(
        "catch the cat",
        (QueryTerm("cat"), QueryTerm("catch")),
    )
    assert marked == "<mark>catch</mark> the <mark>cat</mark>"
