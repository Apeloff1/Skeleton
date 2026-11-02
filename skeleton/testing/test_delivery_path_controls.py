import pytest

from skeleton.build.delivery._util import DeliveryError, normalize_relpath


@pytest.mark.parametrize("bad", (
    "a" + chr(10) + "b", "a" + chr(13) + "b",
    "a" + chr(0x202E) + "b", "a" + chr(0x2028) + "b",
    "a" + chr(0) + "b", "a" + chr(92) + "b",
    "a" * 4097, "/".join(["part"] * 129),
))
def test_delivery_paths_reject_control_and_unbounded_aliases(bad):
    with pytest.raises(DeliveryError):
        normalize_relpath(bad)


def test_delivery_paths_preserve_valid_unicode_and_canonicalization():
    assert normalize_relpath("café/assets.bin") == "café/assets.bin"
    assert normalize_relpath("./assets/a.bin") == "assets/a.bin"
