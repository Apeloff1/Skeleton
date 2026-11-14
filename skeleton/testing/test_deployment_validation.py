"""Fail-closed, coded validation of self-host profiles."""

from __future__ import annotations

import os
from collections import namedtuple

import pytest

from skeleton.deployment.profile import SelfHostProfile, get_profile
from skeleton.deployment.validation import (
    RULES,
    DeploymentConfigError,
    Severity,
    ValidationReport,
    is_loopback_host,
    parse_mongo_uri,
    validate_against_settings,
    validate_profile,
)

TOKEN = "Zq8vT2mX9rL4wB7nK1pD6sF3hJ0cY5gA"  # 32 chars, diverse


def codes(profile: SelfHostProfile, **kwargs) -> list[str]:
    return validate_profile(profile, **kwargs).codes()


def prod(**changes) -> SelfHostProfile:
    base = dict(service_token=TOKEN, allowed_tenants="t1", allowed_capabilities="c1")
    base.update(changes)
    return get_profile("selfhost").with_overrides(**base)


def test_every_registered_rule_has_a_description() -> None:
    assert all(code.startswith("DEP") and text for code, text in RULES.items())


def test_report_rejects_unregistered_codes() -> None:
    with pytest.raises(KeyError):
        ValidationReport("x", "f").add("DEP999", Severity.ERROR, "f", "m")


@pytest.mark.parametrize("name", ["local", "test"])
def test_dev_builtins_are_clean(name: str) -> None:
    report = validate_profile(get_profile(name), check_settings=True)
    assert report.ok, report.to_dict()
    assert report.issues == []


def test_selfhost_requires_a_token_and_warns_on_wildcards() -> None:
    report = validate_profile(get_profile("selfhost"))
    assert "DEP011" in report.codes()
    assert report.codes().count("DEP051") == 2
    assert not report.ok


def test_hardened_production_profile_is_clean() -> None:
    report = validate_profile(prod(mongo_uri="mongodb://app:pw@db:27017/skeleton"), check_settings=True)
    assert report.ok
    assert report.issues == [], report.to_dict()


def test_raise_for_errors() -> None:
    report = validate_profile(get_profile("selfhost"))
    with pytest.raises(DeploymentConfigError, match="DEP011") as info:
        report.raise_for_errors()
    assert info.value.report is report
    clean = validate_profile(get_profile("local"))
    assert clean.raise_for_errors() is clean


def test_report_dict_shape() -> None:
    payload = validate_profile(get_profile("selfhost")).to_dict()
    assert payload["kind"] == "deployment_validation"
    assert payload["ok"] is False
    assert payload["error_count"] >= 1
    assert {"code", "severity", "field", "message", "hint"} <= set(payload["issues"][0])


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"environment": "prod"}, "DEP001"),
        ({"port": 0}, "DEP002"),
        ({"port": 70000}, "DEP002"),
        ({"host": "bad host!"}, "DEP004"),
        ({"host": "-lead.example"}, "DEP004"),
        ({"host": ""}, "DEP004"),
        ({"host": "0.0.0.0"}, "DEP005"),
        ({"log_level": "LOUD"}, "DEP006"),
        ({"workers": 0}, "DEP024"),
        ({"service_token": "short"}, "DEP010"),
        ({"service_token": " " + TOKEN}, "DEP010"),
        ({"service_token": "ab" * 20}, "DEP013"),
        ({"service_principal": "has space"}, "DEP014"),
        ({"mongo_uri": "postgres://db"}, "DEP030"),
        ({"mongo_uri": "nohost"}, "DEP030"),
        ({"mongo_uri": "mongodb://db:notaport"}, "DEP030"),
        ({"mongo_database": "bad.name"}, "DEP032"),
        ({"mongo_database": ""}, "DEP032"),
        ({"chroma_port": 0}, "DEP040"),
        ({"allowed_tenants": ""}, "DEP050"),
        ({"extra_env": {"lower": "x"}}, "DEP070"),
        ({"extra_env": {"SKL_SERVER_PORT": "1"}}, "DEP071"),
    ],
)
def test_single_rule_violations(changes, code) -> None:
    profile = get_profile("local").with_overrides(**changes)
    assert code in codes(profile)


def test_privileged_port_warns_for_non_root(monkeypatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000, raising=False)
    assert "DEP003" in codes(get_profile("local").with_overrides(port=80))
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    assert "DEP003" not in codes(get_profile("local").with_overrides(port=80))


def test_debug_logging_in_production_warns() -> None:
    assert "DEP007" in codes(prod(log_level="DEBUG"))


def test_multiple_workers_with_memory_stores_warn() -> None:
    assert "DEP025" in codes(get_profile("test").with_overrides(workers=2))
    assert "DEP025" not in codes(get_profile("local").with_overrides(workers=2))


def test_token_recommended_for_staging_and_public_binds() -> None:
    staging = get_profile("local").with_overrides(environment="staging")
    assert "DEP012" in codes(staging)
    public_dev = get_profile("local").with_overrides(host="192.168.1.5")
    assert "DEP012" in codes(public_dev)
    assert "DEP012" not in codes(get_profile("test").with_overrides(host="0.0.0.0"))


def test_production_without_data_dir_is_an_error() -> None:
    assert "DEP020" in codes(prod(data_dir="", chroma_persist=False))


def test_memory_store_override_in_production_is_an_error() -> None:
    assert "DEP021" in codes(prod(store_overrides={"engine_quota": ":memory:"}))


def test_colliding_stores_are_detected(tmp_path) -> None:
    shared = str(tmp_path / "same.sqlite")
    profile = get_profile("local").with_overrides(
        data_dir=str(tmp_path), store_overrides={"engine_quota": shared, "engine_pressure": shared})
    assert "DEP022" in codes(profile)


def test_override_colliding_with_default_store_is_detected(tmp_path) -> None:
    profile = get_profile("local").with_overrides(
        data_dir=str(tmp_path), store_overrides={"engine_quota": str(tmp_path / "operation_state.sqlite")})
    assert "DEP022" in codes(profile)


def test_relative_store_override_warns() -> None:
    assert "DEP023" in codes(get_profile("local").with_overrides(store_overrides={"engine_quota": "q.sqlite"}))


def test_mongo_rules_for_production_and_offline() -> None:
    assert "DEP031" in codes(prod(mongo_uri="mongodb://db:27017"))
    assert "DEP031" not in codes(prod(mongo_uri="mongodb://u:p@db:27017"))
    offline = get_profile("offline").with_overrides(service_token=TOKEN, mongo_uri="mongodb://u:p@8.8.8.8")
    assert "DEP033" in codes(offline)
    assert "DEP033" not in codes(offline.with_overrides(mongo_uri="mongodb://u:p@10.0.0.4,127.0.0.1:27018"))


def test_chroma_rules() -> None:
    assert "DEP041" in codes(get_profile("test").with_overrides(chroma_persist=True))
    offline = get_profile("offline").with_overrides(service_token=TOKEN, chroma_host="vectors.example.com")
    assert "DEP042" in codes(offline)


def test_wildcard_allow_lists_only_warn_in_production() -> None:
    assert "DEP051" not in codes(get_profile("local"))
    report = validate_profile(prod(allowed_tenants="*"))
    issue = next(i for i in report.issues if i.code == "DEP051")
    assert issue.severity is Severity.WARNING
    assert report.ok


def test_dev_surfaces() -> None:
    assert "DEP060" in codes(prod(public_dev_surfaces=True))
    assert "DEP061" in codes(get_profile("local").with_overrides(public_dev_surfaces=True, environment="staging"))
    assert "DEP061" in codes(get_profile("local").with_overrides(public_dev_surfaces=True, host="0.0.0.0"))
    assert not {"DEP060", "DEP061"} & set(codes(get_profile("local").with_overrides(public_dev_surfaces=True)))


def test_offline_profile_may_not_forward_provider_credentials() -> None:
    offline = get_profile("offline").with_overrides(service_token=TOKEN, extra_env={"OPENAI_API_KEY": "sk"})
    assert "DEP072" in codes(offline)
    online = get_profile("local").with_overrides(extra_env={"OPENAI_API_KEY": "sk"})
    assert "DEP072" not in codes(online)


def test_filesystem_checks(tmp_path, monkeypatch) -> None:
    afile = tmp_path / "afile"
    afile.write_text("x", encoding="utf-8")
    assert "DEP082" in codes(get_profile("local").with_overrides(data_dir=str(afile)), check_filesystem=True)
    ok_profile = get_profile("local").with_overrides(data_dir=str(tmp_path / "new" / "dir"))
    assert validate_profile(ok_profile, check_filesystem=True).ok

    monkeypatch.setattr(os, "access", lambda *_a, **_k: False)
    assert "DEP080" in codes(ok_profile, check_filesystem=True)


def test_disk_space_thresholds(tmp_path, monkeypatch) -> None:
    import skeleton.deployment.validation as validation

    usage = namedtuple("usage", "total used free")
    profile = get_profile("local").with_overrides(data_dir=str(tmp_path))
    monkeypatch.setattr(validation.shutil, "disk_usage", lambda _p: usage(1, 1, 10))
    report = validate_profile(profile, check_filesystem=True)
    assert [i.severity for i in report.issues if i.code == "DEP081"] == [Severity.ERROR]
    monkeypatch.setattr(validation.shutil, "disk_usage", lambda _p: usage(1, 1, 100 * 1024 * 1024))
    report = validate_profile(profile, check_filesystem=True)
    assert [i.severity for i in report.issues if i.code == "DEP081"] == [Severity.WARNING]


def test_settings_parity_reports_runtime_rejections(monkeypatch) -> None:
    monkeypatch.setenv("SKL_SERVER_PORT", "1234")
    bad = get_profile("local").with_overrides(port=99999)
    report = validate_against_settings(bad)
    assert "DEP090" in report.codes()
    # The caller's environment is restored afterwards.
    assert os.environ["SKL_SERVER_PORT"] == "1234"


def test_settings_parity_passes_for_builtins_with_token() -> None:
    for name in ("local", "selfhost", "offline", "test"):
        profile = get_profile(name).with_overrides(service_token=TOKEN)
        assert validate_against_settings(profile).codes() == [], name


def test_settings_parity_catches_short_token_like_runtime() -> None:
    report = validate_against_settings(get_profile("local").with_overrides(service_token="short"))
    assert "DEP090" in report.codes()


def test_parse_mongo_uri_variants() -> None:
    assert parse_mongo_uri("mongodb://db") == ("mongodb", [("db", 27017)], False)
    scheme, hosts, creds = parse_mongo_uri("mongodb://u:p@a:1,b:2,[::1]:3/x?replicaSet=r")
    assert (scheme, creds) == ("mongodb", True)
    assert hosts == [("a", 1), ("b", 2), ("::1", 3)]
    assert parse_mongo_uri("mongodb+srv://cluster.example.net")[1] == [("cluster.example.net", 27017)]
    for bad in ("db:27017", "mongodb://", "mongodb://h:0", "mongodb://[::1"):
        with pytest.raises(ValueError):
            parse_mongo_uri(bad)


@pytest.mark.parametrize("host,expected", [("localhost", True), ("127.0.0.1", True), ("::1", True),
                                           ("[::1]", True), ("10.0.0.1", False), ("example.org", False)])
def test_is_loopback_host(host: str, expected: bool) -> None:
    assert is_loopback_host(host) is expected
