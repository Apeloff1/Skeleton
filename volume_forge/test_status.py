"""Status test. No tree read."""

from status import percent

def test_percent() -> None:
    assert percent() == 70

if __name__ == "__main__":
    test_percent()
    print("status-ok")
