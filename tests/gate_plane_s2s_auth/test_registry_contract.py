import pytest

from skeleton.gate_plane.s2s.registry import RegistryError, ServiceIdentity, ServiceRegistry, normalize_fingerprint


def test_clamp_and_excess():
    ident = ServiceIdentity.build("svc-a", scopes=["forge:read"])
    assert ident.clamp_scopes(["forge:read", "forge:write"]) == {"forge:read"}
    assert ident.excess_scopes(["forge:read", "forge:write"]) == {"forge:write"}


def test_roundtrip_and_digest_stable():
    reg = ServiceRegistry([ServiceIdentity.build("svc-a", scopes=["forge:read"], audiences=["gate"])])
    again = ServiceRegistry.from_dicts(reg.to_dicts())
    assert again.digest() == reg.digest()


def test_duplicate_register_rejected_and_events():
    reg = ServiceRegistry()
    seen = []
    reg.add_listener(seen.append)
    reg.register(ServiceIdentity.build("svc-a"))
    with pytest.raises(RegistryError):
        reg.register(ServiceIdentity.build("svc-a"))
    reg.disable("svc-a", reason="incident")
    assert not reg.require("svc-a").enabled
    assert [e.action for e in seen][:2] == ["register", "disable"]


def test_fingerprint_normalization():
    assert normalize_fingerprint("AA:" * 31 + "AA") == "aa" * 32
    with pytest.raises(RegistryError):
        normalize_fingerprint("nothex")


def test_audience_restriction():
    ident = ServiceIdentity.build("svc-a", audiences=["gate"])
    assert ident.may_address("gate") and not ident.may_address("other")
