from frontier.repair_marker import RepairPlan


def test_repair_plan_rejects_invalid_priority():
    try:
        RepairPlan("backend", True)
    except ValueError:
        return
    raise AssertionError("boolean priority must be rejected")


def test_repair_plan_marks_critical_work():
    plan = RepairPlan("backend", 100)
    assert plan.critical is True
    assert plan.reversible is True


def test_repair_plan_rejects_non_boolean_reversible():
    try:
        RepairPlan("backend", 1, reversible=1)
    except TypeError:
        return
    raise AssertionError("reversible must remain boolean")
