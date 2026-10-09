"""Gate test. No tree."""

from deck_pointer import card
from gate import gate


def test_gate() -> None:
    body = gate()
    assert body["ok"] is True
    assert body["eight_lines"] == 100800072
    assert body["x100_full"] is False


def test_card() -> None:
    body = card()
    assert body["url"] == "pointer://volume/eight"
    assert body["stored_prose"] == 0


if __name__ == "__main__":
    test_gate()
    test_card()
    print("gate-ok")
