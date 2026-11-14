"""Self-host profiles: rendering, parsing, precedence and registry."""

from __future__ import annotations

import json

import pytest

from skeleton.deployment.profile import (
    MANAGED_ENV,
    MEMORY_PATH,
    STORE_KEYS,
    STORE_LAYOUT,
    ProfileError,
    Secret,
    SelfHostProfile,
    builtin_profile_names,
    get_profile,
    list_profiles,
    parse_bool,
    parse_csv,
    register_profile,
    resolve_profile,
)

TOKEN = "k" * 20 + "abcdefghijklmnopqrstuvwxyz"


def test_builtin_profiles_are_registered_in_stable_order() -> None:
    assert builtin_profile_names() == ("local", "selfhost", "offline", "test")
    names = [item["name"] for item in list_profiles()]
    assert names[:4] == ["local", "selfhost", "offline", "test"]
    for item in list_profiles()[:4]:
        assert item["builtin"] is True
        assert item["description"]


@pytest.mark.parametrize("name", ["local", "selfhost", "offline", "test"])
def test_builtin_profiles_construct_and_are_named(name: str) -> None:
    profile = get_profile(name)
    assert profile.name == name
    assert profile.environment in ("development", "production", "test")


def test_unknown_profile_lists_alternatives() -> None:
    with pytest.raises(ProfileError, match="available: .*local"):
        get_profile("nope")


def test_get_profile_is_case_insensitive() -> None:
    assert get_profile("  LOCAL ").name == "local"


def test_store_paths_follow_compose_layout_under_data_dir(tmp_path) -> None:
    profile = SelfHostProfile(name="x", data_dir=str(tmp_path))
    paths = profile.store_paths()
    assert list(paths) == list(STORE_KEYS)
    for key, _env, filename in STORE_LAYOUT:
        assert paths[key] == str(tmp_path / filename)
    assert profile.durable is True


def test_store_paths_are_memory_without_data_dir() -> None:
    profile = SelfHostProfile(name="x", data_dir=None)
    assert set(profile.store_paths().values()) == {MEMORY_PATH}
    assert profile.durable is False


def test_blank_data_dir_normalizes_to_none() -> None:
    assert SelfHostProfile(name="x", data_dir="   ").data_dir is None


def test_store_override_wins_and_unknown_store_is_rejected(tmp_path) -> None:
    profile = SelfHostProfile(name="x", data_dir=str(tmp_path), store_overrides={"engine_quota": "/srv/q.sqlite"})
    assert profile.store_paths()["engine_quota"] == "/srv/q.sqlite"
    with pytest.raises(ProfileError, match="unknown store"):
        SelfHostProfile(name="x", store_overrides={"nope": "/x"})


def test_to_env_matches_runtime_variable_names(tmp_path) -> None:
    profile = SelfHostProfile(
        name="x", data_dir=str(tmp_path), mongo_uri="mongodb://u:p@db:27017", service_token=TOKEN,
        public_dev_surfaces=True, offline=True, chroma_persist=True,
    )
    env = profile.to_env()
    assert env["SKL_ENVIRONMENT"] == "development"
    assert env["SKL_SERVER_PORT"] == "8001"
    assert env["SKL_MONGO_URI"] == "mongodb://u:p@db:27017"
    assert env["SKL_ENGINE_SERVICE_TOKEN"] == TOKEN
    assert env["SKL_GOVERNANCE_LIFECYCLE_PATH"] == str(tmp_path / "governance_lifecycle.sqlite")
    assert env["SKL_CHROMA_PERSIST_DIRECTORY"] == str(tmp_path / "chroma")
    assert env["SKELETON_PUBLIC_DEV_SURFACES"] == "1"
    assert env["SKELETON_OFFLINE"] == "1"
    assert env["SKELETON_DATA_DIR"] == str(tmp_path)
    assert set(env) <= MANAGED_ENV


def test_to_env_omits_unset_optional_values() -> None:
    env = SelfHostProfile(name="x").to_env()
    assert "SKL_MONGO_URI" not in env  # server binds Mongo memory only when set
    assert "SKL_ENGINE_SERVICE_TOKEN" not in env
    assert "SKELETON_PUBLIC_DEV_SURFACES" not in env
    assert "SKL_CHROMA_PERSIST_DIRECTORY" not in env


def test_to_env_can_mask_secrets() -> None:
    env = SelfHostProfile(name="x", service_token=TOKEN).to_env(include_secrets=False)
    assert env["SKL_ENGINE_SERVICE_TOKEN"] == "**********"


def test_extra_env_is_appended_sorted() -> None:
    env = SelfHostProfile(name="x", extra_env={"ZED": "1", "ALPHA": "2"}).to_env()
    keys = list(env)
    assert keys[-2:] == ["ALPHA", "ZED"]


def test_secret_never_leaks_through_repr_str_or_dict() -> None:
    profile = SelfHostProfile(name="x", service_token=TOKEN)
    assert TOKEN not in repr(profile)
    assert TOKEN not in str(profile.service_token)
    assert TOKEN not in json.dumps(profile.to_dict())
    assert profile.to_dict(redact=False)["service_token"] == TOKEN


def test_secret_semantics() -> None:
    assert Secret("a") == Secret("a")
    assert Secret("a") != Secret("b")
    assert not Secret("")
    assert len(Secret("abc")) == 3
    assert Secret(Secret("z")).reveal() == "z"
    with pytest.raises(ProfileError):
        Secret(5)  # type: ignore[arg-type]
    assert hash(Secret("a")) == hash(Secret("a"))


def test_fingerprint_is_stable_and_excludes_secret_value() -> None:
    one = SelfHostProfile(name="x", service_token="a" * 40)
    two = SelfHostProfile(name="x", service_token="b" * 40)
    three = SelfHostProfile(name="x", service_token="b" * 41)
    assert one.fingerprint() == two.fingerprint()  # same length, value not hashed
    assert one.fingerprint() != three.fingerprint()
    assert one.fingerprint() == SelfHostProfile(name="x", service_token="a" * 40).fingerprint()
    assert one.fingerprint() != one.with_overrides(port=9000).fingerprint()


def test_base_url_maps_wildcard_and_ipv6_hosts() -> None:
    assert SelfHostProfile(name="x", host="0.0.0.0", port=1).base_url == "http://127.0.0.1:1"
    assert SelfHostProfile(name="x", host="::1", port=2).base_url == "http://[::1]:2"
    assert SelfHostProfile(name="x", host="example.org", port=3).base_url == "http://example.org:3"


def test_with_overrides_coerces_types_and_rejects_unknown() -> None:
    profile = get_profile("local").with_overrides(port="9001", offline="yes", allowed_tenants="a, b,a")
    assert profile.port == 9001
    assert profile.offline is True
    assert profile.allowed_tenants == ("a", "b")
    with pytest.raises(ProfileError, match="unknown profile field"):
        profile.with_overrides(colour="red")
    with pytest.raises(ProfileError, match="integer"):
        profile.with_overrides(port="eighty")
    with pytest.raises(ProfileError, match="boolean"):
        profile.with_overrides(port=True)


def test_with_settings_supports_store_assignments() -> None:
    profile = get_profile("local").with_settings(["port=7000", "store.engine_quota=/q.sqlite", "log_level=debug"])
    assert profile.port == 7000
    assert profile.log_level == "DEBUG"
    assert dict(profile.store_overrides) == {"engine_quota": "/q.sqlite"}
    with pytest.raises(ProfileError, match="key=value"):
        profile.with_settings(["port"])


def test_env_round_trip_reproduces_rendered_environment() -> None:
    for name in builtin_profile_names():
        source = get_profile(name).with_overrides(service_token=TOKEN, mongo_uri="mongodb://db")
        parsed = SelfHostProfile.from_env(source.to_env(), base=get_profile("local"))
        expected = dict(source.to_env())
        actual = dict(parsed.to_env())
        expected.pop("SKELETON_DEPLOY_PROFILE")
        actual.pop("SKELETON_DEPLOY_PROFILE")
        assert actual == expected, name


def test_from_env_records_only_non_default_store_paths(tmp_path) -> None:
    env = {"SKELETON_DATA_DIR": str(tmp_path), "SKL_ENGINE_QUOTA_STATE_PATH": "/elsewhere/q.sqlite",
           "SKL_OPERATION_STATE_PATH": str(tmp_path / "operation_state.sqlite")}
    profile = SelfHostProfile.from_env(env, base=get_profile("test"))
    assert dict(profile.store_overrides) == {"engine_quota": "/elsewhere/q.sqlite"}
    assert profile.data_dir == str(tmp_path)


def test_from_env_without_base_uses_profile_name_variable() -> None:
    profile = SelfHostProfile.from_env({"SKELETON_DEPLOY_PROFILE": "edge", "SKL_SERVER_PORT": "9"})
    assert profile.name == "edge"
    assert profile.port == 9


def test_from_mapping_accepts_to_dict_output() -> None:
    source = get_profile("selfhost").with_overrides(service_token=TOKEN)
    rebuilt = SelfHostProfile.from_mapping(source.to_dict(redact=False))
    assert rebuilt == source


def test_from_mapping_rejects_unknown_and_nameless_documents() -> None:
    with pytest.raises(ProfileError, match="requires a name"):
        SelfHostProfile.from_mapping({"port": 1})
    with pytest.raises(ProfileError, match="unknown profile field"):
        SelfHostProfile.from_mapping({"name": "x", "bogus": 1})
    with pytest.raises(ProfileError, match="mapping"):
        SelfHostProfile.from_mapping(["x"])  # type: ignore[arg-type]


def test_empty_name_is_rejected() -> None:
    with pytest.raises(ProfileError):
        SelfHostProfile(name=" ")


def test_absolutized_anchors_relative_paths(tmp_path) -> None:
    profile = SelfHostProfile(name="x", data_dir="rel/data", store_overrides={"engine_quota": "q.sqlite"})
    anchored = profile.absolutized(str(tmp_path))
    assert anchored.data_dir == str(tmp_path / "rel/data")
    assert dict(anchored.store_overrides)["engine_quota"] == str(tmp_path / "q.sqlite")
    assert anchored.absolutized(str(tmp_path)) == anchored
    memory = SelfHostProfile(name="m", store_overrides={"engine_quota": MEMORY_PATH}).absolutized(str(tmp_path))
    assert dict(memory.store_overrides)["engine_quota"] == MEMORY_PATH


def test_resolve_profile_precedence(tmp_path) -> None:
    profile = resolve_profile(
        "local",
        env_overlay={"SKL_SERVER_PORT": "9100", "SKL_OBS_LOG_LEVEL": "ERROR"},
        environ={"SKL_SERVER_PORT": "9200", "HOME": "/ignored", "SKELETON_DEPLOY_PROFILE": "ignored"},
        overrides={"host": "127.0.0.2", "port": None},
        assignments=["workers=2"],
    )
    assert profile.port == 9200  # environ beats env file
    assert profile.log_level == "ERROR"  # env file beats builtin
    assert profile.host == "127.0.0.2"  # overrides beat environ
    assert profile.workers == 2
    assert profile.name == "local"


def test_resolve_profile_from_file(tmp_path) -> None:
    document = tmp_path / "p.json"
    document.write_text(json.dumps({"name": "edge", "port": 9300, "environment": "staging"}), encoding="utf-8")
    profile = resolve_profile(profile_file=str(document))
    assert (profile.name, profile.port, profile.environment) == ("edge", 9300, "staging")
    with pytest.raises(ProfileError, match="cannot read profile file"):
        resolve_profile(profile_file=str(tmp_path / "missing.json"))


def test_register_profile_guards_builtins_and_duplicates() -> None:
    with pytest.raises(ProfileError, match="cannot be replaced"):
        register_profile("local", lambda: SelfHostProfile(name="local"))
    register_profile("unit-edge", lambda: SelfHostProfile(name="unit-edge", port=9400), replace_existing=True)
    assert get_profile("unit-edge").port == 9400
    with pytest.raises(ProfileError, match="already registered"):
        register_profile("unit-edge", lambda: SelfHostProfile(name="unit-edge"))
    assert any(item["name"] == "unit-edge" and not item["builtin"] for item in list_profiles())
    with pytest.raises(ProfileError):
        register_profile(" ", lambda: SelfHostProfile(name="x"))


@pytest.mark.parametrize("raw,expected", [("1", True), ("YES", True), ("on", True), ("0", False),
                                          ("off", False), ("", False), (True, True), (0, False)])
def test_parse_bool(raw, expected) -> None:
    assert parse_bool(raw) is expected


def test_parse_bool_rejects_garbage() -> None:
    with pytest.raises(ProfileError):
        parse_bool("maybe")


def test_parse_csv_dedupes_and_strips() -> None:
    assert parse_csv(" a, ,b,a ") == ("a", "b")
    assert parse_csv(["x", "x", " y "]) == ("x", "y")
    assert parse_csv("") == ()
