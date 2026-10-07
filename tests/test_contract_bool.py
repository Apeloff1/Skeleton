"""A boolean flag is not an integer count."""

from skeleton.intelligence.contract import Contract


def test_true_is_not_an_int() -> None:
    contract = Contract({"count": {"type": int, "required": True}})
    issues = contract.validate({"count": True})
    assert issues and issues[0].problem == "wrong_type"
    repaired = contract.repair({"count": True})
    assert repaired.ok is False
    assert repaired.payload["count"] is True
