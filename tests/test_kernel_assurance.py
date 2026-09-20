from skeleton.kernel.assurance import AssuranceEnvelope, AssuranceState


def test_assurance_digest_is_stable():
    first = AssuranceEnvelope.create(
        task_id="task-1",
        source="worker-a",
        payload={"value": 1},
    )
    second = AssuranceEnvelope.create(
        task_id="task-1",
        source="worker-a",
        payload={"value": 1},
    )

    assert first.digest == second.digest
    assert first.state is AssuranceState.PENDING


def test_assurance_rejects_empty_identity():
    try:
        AssuranceEnvelope.create(
            task_id="",
            source="worker-a",
            payload={"value": 1},
        )
    except ValueError:
        return

    raise AssertionError("empty task identity must fail")
