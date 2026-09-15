"""CI-1: Jeeves import shims stay compatible with the current tutor core."""

from __future__ import annotations

import skeleton
from skeleton.__main__ import main
from skeleton.jeeves import Jeeves as PackageJeeves
from skeleton.jeeves.core import Jeeves, JeevesCore
from skeleton.jeeves.llm_core import JeevesCore as LlmJeevesCore


def test_skeleton_import_fail_closed() -> None:
    assert skeleton.__version__


def test_core_alias_is_tutor_jeeves() -> None:
    assert JeevesCore is Jeeves
    assert Jeeves is PackageJeeves
    assert hasattr(JeevesCore, "plan_build")
    assert hasattr(JeevesCore, "observe_run")


def test_llm_core_remains_distinct() -> None:
    assert LlmJeevesCore is not Jeeves


def test_cli_help_remains_available() -> None:
    assert main(["help"]) == 0
