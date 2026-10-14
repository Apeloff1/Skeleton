from __future__ import annotations
import pytest
from skeleton.training.curriculum import *
def cur(): return Curriculum((CurriculumStage("STAGE.BASE","CAP.BASE",(),True,.8),CurriculumStage("STAGE.HARD","CAP.HARD",("STAGE.BASE",),True,.9),CurriculumStage("STAGE.OPTIONAL","CAP.EXTRA",(),False,.5)))
def test_prerequisite_controls_stage_readiness(): assert cur().ready(())==("STAGE.BASE","STAGE.OPTIONAL")
def test_required_hard_competency_cannot_be_starved_by_easy_optional_work():
 c=cur();signals=(ProgressSignal("STAGE.BASE",.9,1),ProgressSignal("STAGE.OPTIONAL",1,1));assert not c.curriculum_complete(signals) and c.ready(signals)==("STAGE.HARD",)
def test_required_stages_complete_only_after_thresholds(): assert cur().curriculum_complete((ProgressSignal("STAGE.BASE",.9,1),ProgressSignal("STAGE.HARD",.95,1)))
def test_unknown_prerequisite_rejected():
 with pytest.raises(CurriculumError,match="prerequisite"): Curriculum((CurriculumStage("STAGE.A","CAP.A",("STAGE.MISSING",),True,.5),))
def test_cycle_rejected():
 with pytest.raises(CurriculumError,match="cycle"): Curriculum((CurriculumStage("STAGE.A","CAP.A",("STAGE.B",),True,.5),CurriculumStage("STAGE.B","CAP.B",("STAGE.A",),True,.5)))