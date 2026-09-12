from skeleton.school.progression import AchievementEvidence, DEFAULT_ACHIEVEMENTS, achievement_learning_signal, evaluate_achievement, evaluate_progression
from skeleton.school.reflection import ReflectionEntry, ReflectionImportance, ReflectionJournal, ReflectionKind, reflection_prompts, summarize_reflection


def test_reflection_journal_captures_lessons_and_milestones():
    journal = ReflectionJournal()
    journal.record(ReflectionEntry("1", ReflectionKind.FAILURE, "Bug", "It failed", skills=("loops",), lesson_learned="Check the invariant."))
    journal.record(ReflectionEntry("2", ReflectionKind.MILESTONE, "Breakthrough", "Solved it", importance=ReflectionImportance.ACHIEVEMENT, skills=("loops",)))
    assert len(journal.milestones()) == 1
    assert journal.for_skill("loops")[0].entry_id == "2"
    assert journal.lessons() == ["Check the invariant."]


def test_reflection_prompts_are_kind_specific():
    prompts = reflection_prompts(ReflectionKind.MISCONCEPTION)
    assert prompts and prompts[0].required


def test_reflection_summary_is_compact_evidence():
    entries = [ReflectionEntry("1", ReflectionKind.FAILURE, "f", "x", lesson_learned="try again")]
    summary = summarize_reflection(entries)
    assert summary["failures"] == 1
    assert summary["lessons"] == ["try again"]


def test_achievement_threshold_and_signal():
    achievement = DEFAULT_ACHIEVEMENTS[1]
    result = evaluate_achievement(achievement, AchievementEvidence(achievement.metric, 4))
    assert result.progress == 0.8
    assert achievement_learning_signal(result) == "targeted_practice"


def test_progression_reports_new_unlocks_and_next_goals():
    snapshot = evaluate_progression(evidence={"successful_attempts": 5})
    assert "first_success" in snapshot.newly_unlocked
    assert "consistent_success" in snapshot.newly_unlocked
    assert "independent_solution" in snapshot.next_goals
