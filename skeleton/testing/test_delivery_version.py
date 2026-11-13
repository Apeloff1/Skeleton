import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.version import Version, latest


def test_parse_roundtrip():
    assert str(Version.parse("v1.2.3-rc.1+build.5")) == "1.2.3-rc.1+build.5"


@pytest.mark.parametrize("bad", ["1.2", "01.2.3", "1.2.3-01", "x", ""])
def test_parse_rejects(bad):
    with pytest.raises(DeliveryError):
        Version.parse(bad)


def test_precedence_follows_semver():
    order = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2",
             "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
    parsed = [Version.parse(v) for v in order]
    assert parsed == sorted(parsed, key=lambda v: v._key())
    for a, b in zip(parsed, parsed[1:]):
        assert a < b


def test_build_metadata_ignored_for_precedence():
    assert Version.parse("1.0.0+a").precedence_equal(Version.parse("1.0.0+b"))


def test_bumps():
    v = Version.parse("1.2.3")
    assert str(v.bump("major")) == "2.0.0"
    assert str(v.bump("minor")) == "1.3.0"
    assert str(v.bump("patch")) == "1.2.4"
    assert str(v.bump("prerelease")) == "1.2.4-rc.1"
    assert str(Version.parse("1.2.4-rc.1").bump("prerelease")) == "1.2.4-rc.2"
    assert str(Version.parse("1.2.4-rc.2").bump("patch")) == "1.2.4"


def test_latest_skips_prerelease_by_default():
    assert str(latest(["1.0.0", "1.1.0-rc.1", "0.9.0"])) == "1.0.0"
    assert str(latest(["1.0.0", "1.1.0-rc.1"], include_prerelease=True)) == "1.1.0-rc.1"
    assert latest([]) is None
