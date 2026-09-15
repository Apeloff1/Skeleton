"""Regression coverage for the Jeeves compatibility import boundary."""

from __future__ import annotations

import skeleton
from skeleton.__main__ import main
from skeleton.jeeves import Jeeves as PackageJeeves
from skeleton.jeeves.core import Jeeves, JeevesCore
from skeleton.jeeves.llm_core import JeevesCore as LlmJeevesCore


def test_package_import_exposes_version() -> None:
    assert skeleton.__version__


def test_core_compatibility_alias_tracks_tutor_jeeves() -> None:
    assert JeevesCore is Jeeves
    assert Jeeves is PackageJeeves
    assert hasattr(JeevesCore, "plan_build")
    assert hasattr(JeevesCore, "observe_run")


def test_llm_core_remains_a_distinct_runtime() -> None:
    assert LlmJeevesCore is not Jeeves


def test_cli_help_remains_registered() -> None:
    assert main(["help"]) == 0
