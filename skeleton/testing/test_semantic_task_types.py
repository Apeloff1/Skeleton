from skeleton.runtime.task_types import SideEffectClass, TaskClassification, TaskKind, TaskTypeError, semantic_task_type


def test_identity_and_authority_boundary() -> None:
    left = semantic_task_type(TaskKind.CODING, capabilities=("write", "read"))
    right = semantic_task_type(TaskKind.CODING, capabilities=("read", "write"))
    assert left.identity == right.identity
    result = TaskClassification(left, ("e1",), "classifier-v1", 900000)
    assert result.receipt()["grants_execution_authority"] is False


def test_high_impact_requires_verification() -> None:
    try:
        semantic_task_type(TaskKind.EXECUTION, side_effect=SideEffectClass.IRREVERSIBLE)
    except TaskTypeError:
        pass
    else:
        raise AssertionError("expected fail-closed validation")


def test_malformed_classification_fails_closed() -> None:
    task = semantic_task_type(TaskKind.REVIEW)
    for evidence, confidence in [((), 1), (("e2", "e1"), 1), (("e1",), 1000001)]:
        try:
            TaskClassification(task, evidence, "classifier-v1", confidence)
        except TaskTypeError:
            continue
        raise AssertionError("expected invalid classification to fail")
