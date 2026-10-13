"""Cockpit blended tensor must survive pre-roll and manual operator axes."""
from __future__ import annotations

from skeleton.context.cockpit import Cockpit
from skeleton.context.pipeline import GameForgeRun


def test_operator_blend_with_existing_oracle_survives_pipeline():
    c = Cockpit()
    c.apply("BLEND ERA arcade_golden_age soulslike 0.5")
    c.apply("SET AXIS intimacy 0.93")
    c.apply("ROLL ORACLE")
    fingerprint = c.tensor.fingerprint()
    output = GameForgeRun(cockpit=c).execute("")
    assert output["succeeded"], output["run"]
    assert "~" in output["era"]
    assert output["tensor"]["era"] == output["era"]
    assert abs(output["tensor"]["axes"]["intimacy"] - 0.93) < 1e-8
    assert c.tensor.fingerprint() == fingerprint


def test_explicit_era_outvotes_cockpit_blend():
    c = Cockpit()
    c.apply("BLEND ERA arcade_golden_age soulslike 0.5")
    output = GameForgeRun(cockpit=c).execute("", era="soulslike")
    assert output["succeeded"], output["run"]
    assert output["era"] == "soulslike"
    assert "~" not in output["tensor"]["era"]
