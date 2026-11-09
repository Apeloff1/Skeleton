"""Volume plane tests. No shard import. No deck import."""

from clip import binding_mass, clip_mass, projection


def test_ceiling() -> None:
    assert clip_mass(5.0, 1.0) == 1.1


def test_negative_rejected() -> None:
    try:
        clip_mass(-1.0, 1.0)
    except ValueError:
        return
    raise AssertionError("negative accepted")


def test_measured_binding() -> None:
    assert binding_mass(0, 0) == 1.0392


def test_header_gap() -> None:
    body = projection()
    assert body["projected"] == 1530001800
    assert body["header_gap"] == 30200


if __name__ == "__main__":
    test_ceiling()
    test_negative_rejected()
    test_measured_binding()
    test_header_gap()
    print("volume-ok")
