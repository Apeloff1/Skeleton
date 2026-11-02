import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.sbom import Component, build_sbom, parse_package_lock, parse_requirements, serialize


def test_requirements():
    comps = parse_requirements("# c\nPyYAML==6.0.1 ; python_version>'3'\nhttpx[http2]==0.28.1\n")
    assert [c.purl for c in comps] == ["pkg:pypi/pyyaml@6.0.1", "pkg:pypi/httpx@0.28.1"]
    with pytest.raises(DeliveryError, match="pinned"):
        parse_requirements("requests>=2")


def test_package_lock():
    lock = {"packages": {"": {"name": "app"}, "node_modules/react": {"version": "18.3.1", "license": "MIT"},
                         "node_modules/@expo/vector-icons": {"version": "14.0.0"}}}
    comps = parse_package_lock(lock)
    assert {c.name for c in comps} == {"react", "expo.vector-icons"}


def test_sbom_deterministic():
    comps = [Component("b", "1", "npm"), Component("a", "2", "pypi")]
    one = build_sbom("skeleton", "1.0.0", comps)
    two = build_sbom("skeleton", "1.0.0", list(reversed(comps)))
    assert serialize(one) == serialize(two)
    assert one["components"][0]["purl"] == "pkg:npm/b@1"
    assert one["serialNumber"].startswith("urn:sha256:")


def test_component_validation():
    with pytest.raises(DeliveryError):
        Component("bad name", "1", "pypi")
    with pytest.raises(DeliveryError):
        Component("a", "1", "maven")
    with pytest.raises(DeliveryError):
        Component("a", "1", "pypi", sha256="nope")

def test_sbom_intake_rejects_silent_dependency_omission():
    for directive in ("-r other.txt", "-e git+ssh://example/mod", "--extra-index-url https://index"):
        with pytest.raises(DeliveryError, match="unsupported requirements directive"):
            parse_requirements("safe==1.0.0\\n" + directive)
    for invalid in (
        {"packages": {"node_modules/react": {}}},
        {"packages": {"node_modules/react": "18.0.0"}},
    ):
        with pytest.raises(DeliveryError, match="lacks version evidence"):
            parse_package_lock(invalid)


def test_sbom_component_generator_is_bounded():
    from itertools import repeat
    from skeleton.build.delivery.sbom import MAX_SBOM_COMPONENTS

    with pytest.raises(DeliveryError, match="component count exceeds"):
        build_sbom("app", "1.0.0", repeat(Component("safe", "1", "pypi"),
                                           MAX_SBOM_COMPONENTS + 1))
