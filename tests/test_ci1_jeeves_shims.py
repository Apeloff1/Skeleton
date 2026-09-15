"""CI-1: Jeeves import shims + CLI verbs stay discoverable. stored_prose=0"""

from __future__ import annotations

import skeleton
from skeleton.jeeves import Jeeves as PkgJeeves
from skeleton.jeeves.core import Jeeves, JeevesCore
from skeleton.jeeves.llm_core import JeevesCore as LlmJeevesCore
from skeleton.__main__ import main


def test_skeleton_import_fail_closed():
    assert skeleton.__version__


def test_core_alias_is_tutor_jeeves():
    assert JeevesCore is Jeeves
    assert Jeeves is PkgJeeves
    assert hasattr(JeevesCore, "plan_build")
    assert hasattr(JeevesCore, "observe_run")


def test_llm_core_remains_distinct():
    assert LlmJeevesCore is not Jeeves


def test_cli_verbs_registered():
    assert main(["help"]) == 0
