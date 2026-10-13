"""Real wiki query owner integration and fail-closed query budget."""
from __future__ import annotations
import json
from unittest.mock import patch
from skeleton.__main__ import main


def test_wiki_select_reaches_actual_canonical_query(capsys):
    org=type("Org",(),{"galaxy":type("G",(),{"mesh":object()})()})()
    with patch("skeleton.organism.organismer.live_organismer",return_value=org):
        with patch("skeleton.galaxy.query.run",
                   return_value={"kind":"wiki-query","n":1,"rows":[{"topic":"principle"}]}) as query:
            assert main(["wiki","SELECT * WHERE kind=principle","--limit","32"])==0
            assert query.call_args.args[0] is org.galaxy.mesh
            assert query.call_args.args[1]=="SELECT * WHERE kind=principle"
            assert query.call_args.kwargs["limit"]==32
    assert json.loads(capsys.readouterr().out)["n"]==1


def test_wiki_limit_and_query_size_rejected_before_organism_boot():
    with patch("skeleton.organism.organismer.live_organismer") as owner:
        assert main(["wiki","test","--limit","0"])==2
        assert main(["wiki","test","--limit","999"])==2
        assert main(["wiki","x"*4097])==2
        owner.assert_not_called()
