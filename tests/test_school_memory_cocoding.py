from skeleton.school.cocoding import CodingPhase, CoCodingContext, HandoffStage, choose_action, next_handoff
from skeleton.school.memory import LearnerMemory, MemoryKind, MemoryStore
from skeleton.school.prompting import RefinementNeed, refine_prompt


def test_memory_retrieval_combines_skill_and_retention():
    store = MemoryStore()
    store.remember(LearnerMemory("m1", "student struggled with recursion", MemoryKind.MISCONCEPTION, ("recursion",), 0.9, 0.9, 3, 1))
    store.remember(LearnerMemory("m2", "student likes diagrams", MemoryKind.PREFERENCE, (), 0.5, 0.8, 1, 100))
    matches = store.retrieve(query_terms=("recursion",), skill_ids=("recursion",))
    assert matches[0].memory.key == "m1"


def test_retention_due_surfaces_weak_memory():
    store = MemoryStore([LearnerMemory("old", "review sorting", MemoryKind.SEMANTIC, ("sorting",), 0.2, 0.5, 0, 500)])
    assert store.retention_due(minimum_signal=0.7)[0].key == "old"


def test_coding_policy_preserves_learner_ownership():
    action = choose_action(CoCodingContext(CodingPhase.IMPLEMENT, HandoffStage.REFINE))
    assert action.learner_owns_next_step
    assert action.ask_before_writing


def test_stuck_learner_gets_debugging_guidance():
    action = choose_action(CoCodingContext(CodingPhase.IMPLEMENT, HandoffStage.REFINE, learner_stuck=True))
    assert action.action.startswith("guide")


def test_handoff_only_fades_after_evidence():
    assert next_handoff(HandoffStage.COMPLETE, successful=False, learner_explained=True) is HandoffStage.COMPLETE
    assert next_handoff(HandoffStage.COMPLETE, successful=True, learner_explained=True) is HandoffStage.REFINE


def test_prompt_refinement_detects_missing_contract():
    result = refine_prompt("help with python")
    assert RefinementNeed.SCOPE in result.needs
    assert RefinementNeed.SUCCESS in result.needs
    assert result.questions
