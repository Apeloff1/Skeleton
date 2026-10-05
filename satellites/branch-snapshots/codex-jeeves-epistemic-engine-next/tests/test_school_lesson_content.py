from skeleton.school.lesson_content import generate_lesson_content


def test_lesson_generation_is_deterministic():
    first = generate_lesson_content("ds_week_1", 1, "Algorithms", ("arrays", "complexity"))
    second = generate_lesson_content("ds_week_1", 1, "Algorithms", ("arrays", "complexity"))
    assert first == second
    assert len(first.exercises) == 5
    assert len(first.learning_objectives) == 2


def test_category_drives_code_example():
    lesson = generate_lesson_content("db_week_2", 2, "Database Indexes", ("indexes", "queries"))
    assert lesson.category == "databases"
    assert lesson.topics[0].code_example.startswith("-- indexes")
    assert "Transfer:" in lesson.assessment_rubric[-1]
