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


def test_delivery_paths_reject_cross_platform_and_unicode_aliases():
    from skeleton.ai.build.core.delivery import _util as mirrored

    for normalize in (normalize_relpath, mirrored.normalize_relpath):
        for bad in ("C:artifact.bin", "a%2fb", "a?b", "a#b",
                    "cafe\u0301/asset.bin", "a" + chr(0xD800) + "b"):
            with pytest.raises(DeliveryError):
                normalize(bad)
        assert normalize("café/assets.bin") == "café/assets.bin"
