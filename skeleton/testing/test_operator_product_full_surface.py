"""The live product verb list must match wired CLI contracts."""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from skeleton.__main__ import main
from skeleton.organism.operator_cli import PRODUCT_COMMANDS


@pytest.mark.parametrize("verb", PRODUCT_COMMANDS)
def test_product_verb_reaches_real_owner_adapter(verb, capsys):
    with patch("skeleton.organism.organismer.live_organismer", return_value=object()):
        with patch("skeleton.organism.operator_cli._execute", return_value={"kind":verb,"ok":1}) as op:
            args=[verb,"mobile"] if verb=="switch" else [verb]
            assert main(args)==0
            assert op.call_args.args[0]==verb
            assert json.loads(capsys.readouterr().out)["kind"]==verb


@pytest.mark.parametrize("verb,args",[
    ("ready",["-n","99"]),("day",["-n","0"]),
    ("orgwalk",["-n","999"]),("fieldwalk",["-n","-1"]),
    ("week",["--days","99"]),("decade",["--seasons","99"]),
    ("conductor",["--run","--commit"]),("ctx",["--refine","--replay"]),
    ("dump",["--force","--hot"]),("switch",["unknown"])
])
def test_bad_flags_rejected_before_organism_boot(verb,args):
    with patch("skeleton.organism.organismer.live_organismer") as owner:
        assert main([verb,*args])==2
        owner.assert_not_called()


def test_real_orgwalk_n_is_preserved(capsys):
    with patch("skeleton.organism.organismer.live_organismer",return_value=object()):
        with patch("skeleton.organism.runloop.walk",return_value={"kind":"run","n":3}) as run:
            assert main(["orgwalk","-n","3"])==0
            assert run.call_args.kwargs["n"]==3
    assert json.loads(capsys.readouterr().out)["n"]==3


def test_product_docs_advertise_only_routed_verbs():
    text=Path("docs/PRODUCT.md").read_text(encoding="utf-8")
    opening=text.split("```",2)[1]
    advertised={line.split()[3] for line in opening.splitlines()
                if line.startswith("python -m skeleton ")}
    assert advertised <= set(PRODUCT_COMMANDS) | {"ready","product","health","next","doctor"}
    assert "orgwalk" in advertised
    assert "wiki" in advertised


def test_help_list_includes_all_wired_product_verbs(capsys):
    assert main(["help"])==0
    output=capsys.readouterr().out
    for command in PRODUCT_COMMANDS:
        assert "    "+command+" " in output,command
