"""AI volume census. No tree read."""

from skeleton.ai.volume_census import PROJECTION, admit, claimed_lines, clip_mass, pin


def test_admit() -> None:
    body = admit(claimed_lines())
    assert body["claimed"] == 280085289
    assert body["stored_prose"] == 0
    assert body["url"] == "pointer://ai/volume/census"
    assert body["x100_full"] is False


def test_projection_refused() -> None:
    try:
        admit(PROJECTION)
    except RuntimeError:
        return
    raise AssertionError("projection admitted")


def test_clip() -> None:
    assert clip_mass(5.0, 1.0) == 1.1


def test_pin() -> None:
    assert pin().startswith("dbe1aeb6")
