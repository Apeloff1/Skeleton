import pytest

from skeleton.learning.school.quiz_bank import (
    QuizBank, QuizBankError, QuizQuestion, default_bank,
)


def _q(subject="cs", diff=1, n=0):
    return QuizQuestion(subject, "cat", f"q{diff}-{n}?", ("a", "b"), "a", "because", diff)


def _bank(per_tier=10):
    bank = QuizBank()
    bank.extend(_q(diff=d, n=i) for d in range(1, 6) for i in range(per_tier))
    return bank


def test_question_validation():
    with pytest.raises(QuizBankError):
        QuizQuestion("cs", "c", "p", ("a", "b"), "z", "e", 1)
    with pytest.raises(QuizBankError):
        QuizQuestion("cs", "c", "p", ("a", "b"), "a", "e", 9)
    with pytest.raises(QuizBankError):
        QuizQuestion("cs", "c", "p", ("a", "a"), "a", "e", 1)


def test_duplicate_rejected():
    bank = QuizBank()
    bank.add(_q())
    with pytest.raises(QuizBankError):
        bank.add(_q())


def test_build_quiz_deterministic_and_ordered():
    bank = _bank()
    a = bank.build_quiz("cs", 19, seed="learner-1")
    b = bank.build_quiz("cs", 19, seed="learner-1")
    assert [q.qid for q in a] == [q.qid for q in b]
    assert len(a) == 19 and len({q.qid for q in a}) == 19
    diffs = [q.difficulty for q in a]
    assert diffs == sorted(diffs)
    assert diffs.count(1) >= diffs.count(5)


def test_max_difficulty_and_backfill():
    bank = _bank(per_tier=3)
    quiz = bank.build_quiz("cs", 6, max_difficulty=2)
    assert len(quiz) == 6 and all(q.difficulty <= 2 for q in quiz)
    with pytest.raises(QuizBankError):
        bank.build_quiz("cs", 7, max_difficulty=2)
    with pytest.raises(QuizBankError):
        bank.build_quiz("cs", 0)


def test_grade_and_mastery():
    bank = _bank()
    quiz = bank.build_quiz("cs", 10, seed="s")
    answers = {q.qid: ("a" if q.difficulty <= 3 else "b") for q in quiz}
    res = QuizBank.grade(quiz, answers)
    assert res.total == 10
    assert res.mastery_tier == 3
    assert 0 < res.score < 1
    assert QuizBank.grade([], {}).score == 0.0


def test_default_bank():
    bank = default_bank()
    assert bank.subjects() == ["cs", "math", "physics"]
    assert bank.stats()["physics"]["mastery"] == 1
    assert len(bank.build_quiz("physics", 6)) == 6


def test_mirror_identical():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert (root / "learning/school/quiz_bank.py").read_bytes() == \
        (root / "ai/learning/school/quiz_bank.py").read_bytes()
