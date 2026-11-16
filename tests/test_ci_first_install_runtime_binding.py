"""CI-only launch adapter tests; no actual Docker or credentials."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import importlib.util
import subprocess
import sys

import pytest

_SCRIPT=Path(__file__).resolve().parents[1]/"scripts"/"ci_first_install_runtime_binding.py"
_spec=importlib.util.spec_from_file_location("ci_first_install_runtime_binding",_SCRIPT)
ci=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci)
from skeleton.app.compose_storage_binding import BindingReport

ENV={"GITHUB_ACTIONS":"true","COMPOSE_PROJECT_NAME":"skeleton-e2e"}


@pytest.mark.parametrize("env",[{},{"GITHUB_ACTIONS":"true"},{"GITHUB_ACTIONS":"true","COMPOSE_PROJECT_NAME":"production"}])
def test_ci_adapter_never_dispatches_outside_fixed_isolated_project(tmp_path,env):
    deny=Mock(side_effect=AssertionError("unexpected dispatch"))
    assert ci.qualify(tmp_path,environ=env,runner=deny,observe=deny)["ok"] is False
    assert not list(tmp_path.iterdir())
    deny.assert_not_called()


def test_ci_adapter_never_overwrites_existing_private_env(tmp_path):
    path=tmp_path/".env"
    path.write_bytes(b"PRIVATE=fixture\n")
    deny=Mock(side_effect=AssertionError("unexpected dispatch"))
    assert not ci.qualify(tmp_path,environ=ENV,runner=deny,observe=deny)["ok"]
    assert path.read_bytes()==b"PRIVATE=fixture\n"
    deny.assert_not_called()


@pytest.mark.parametrize("scenario",["pass","pre-denied","post-denied","exit-failed","timeout","drift"])
def test_ci_adapter_preserves_gate_order_and_redacts_output(tmp_path,scenario):
    calls=[]
    before=BindingReport(True,scenario!="pre-denied","fixture_pre")
    after=BindingReport(True,scenario!="post-denied","fixture_post")
    def observe(root,**kw):
        assert kw["admit"]() is True
        assert kw["environ"]["COMPOSE_PROJECT_NAME"]=="skeleton-e2e"
        assert kw["environ"]["COMPOSE_REMOVE_ORPHANS"]=="0"
        if kw.get("require_started"):
            assert kw["previous"] is before
            calls.append("post")
            return after
        calls.append("pre")
        return before
    def runner(args,**kw):
        calls.append("up")
        assert "up" in args and "--no-build" in args and "--env-file" in args
        assert kw["stdout"]==kw["stderr"]==subprocess.DEVNULL
        if scenario=="drift":
            (tmp_path/".env").write_text("# changed\n")
        if scenario=="timeout":
            raise subprocess.TimeoutExpired(args,480)
        return SimpleNamespace(returncode=1 if scenario=="exit-failed" else 0)
    result=ci.qualify(tmp_path,environ=ENV,runner=runner,observe=observe)
    assert result["ok"] is (scenario=="pass")
    assert not (tmp_path/".env").exists()
    assert calls==(["pre"] if scenario=="pre-denied" else
                   ["pre","up"] if scenario in {"exit-failed","timeout","drift"} else ["pre","up","post"])
