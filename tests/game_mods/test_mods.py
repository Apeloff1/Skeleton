import json

import pytest

from backend.core.save_envelope import SaveCodec
from skeleton.ai.game_builder.mods import (
    DeclarativeHook, HookError, ModError, ModManifest, ResolveError, SemVer, VersionSpec, apply_mods,
    pack_mod, resolve_load_order, unpack_mod,
)
from skeleton.ai.game_builder.project_bundle.manifest import BUNDLE_SCHEMA_VERSION
from skeleton.gameforge.batch_b09x.b095_plugin_sdk import KINDS
from skeleton.gameforge.batch_b09x.b099_ugc_sandbox import MOD_PERMISSIONS

CODEC = SaveCodec(BUNDLE_SCHEMA_VERSION)
KEY = b"k" * 32
PLAN = {"title": "Forge", "player": {"speed": 4, "hp": 10},
        "levels": [{"id": "cave", "name": "Cave"}, {"id": "gate", "name": "Gate"}]}
RW = ("add_content", "override_content")


def mm(mod_id, version="1.0.0", **kw):
    kw.setdefault("permissions", RW)
    return ModManifest(mod_id, SemVer.parse(version), **kw)


def test_b095_b099_extended():
    assert KINDS["content_hook"] == ("apply",) and "override_content" in MOD_PERMISSIONS


@pytest.mark.parametrize("spec,v,ok", [
    ("^1.2.0", "1.9.3", True), ("^1.2.0", "2.0.0", False), ("^0.2.1", "0.2.9", True),
    ("^0.2.1", "0.3.0", False), ("~1.2.3", "1.2.9", True), ("~1.2.3", "1.3.0", False),
    (">=1.0.0 <2.0.0", "1.5.0", True), (">= 1.0.0 < 2.0.0", "2.0.0", False), ("1.4.2", "1.4.2", True),
    ("*", "9.9.9", True), ("^1.0.0 || ^3.0.0", "3.1.0", True), ("^1.0.0", "1.1.0-beta.1", False),
    (">=1.1.0-beta.1", "1.1.0-beta.2", True), (">=1.1.0-alpha", "1.1.0-beta", True)])
def test_semver_specs(spec, v, ok):
    assert VersionSpec(spec).matches(SemVer.parse(v)) is ok


def test_semver_ordering_and_validation():
    assert SemVer.parse("1.0.0-alpha") < SemVer.parse("1.0.0-alpha.1") < SemVer.parse("1.0.0-beta") < SemVer.parse("1.0.0")
    assert SemVer.parse("1.0.0-2") < SemVer.parse("1.0.0-10")
    for bad in ("1.0", "01.0.0", "x"):
        with pytest.raises(ModError):
            SemVer.parse(bad)
    with pytest.raises(ModError):
        VersionSpec("^^1")
    with pytest.raises(ModError):
        mm("Bad Id")
    with pytest.raises(ModError):
        mm("a1", permissions=("root",))
    with pytest.raises(ModError):
        mm("a1", sdk_api=(2, 0))
    m = mm("core", "2.1.0-rc.1", depends={"lib": VersionSpec("^1.0.0")}, targets=("levels",))
    assert ModManifest.from_dict(json.loads(json.dumps(m.to_dict()))) == m


def test_load_order_deterministic_with_after_before():
    plan = resolve_load_order([
        mm("zeta"), mm("alpha", load_after=("zeta",)), mm("lib"),
        mm("ui", depends={"lib": VersionSpec("^1.0.0")}, load_before=("alpha",)),
        mm("extra", optional={"lib": VersionSpec("^1.0.0"), "absent": VersionSpec("*")})])
    ids = plan.ids()
    assert ids.index("zeta") < ids.index("alpha") and ids.index("lib") < ids.index("ui") < ids.index("alpha")
    assert ids.index("lib") < ids.index("extra") and ids == resolve_load_order(reversed(plan.order)).ids()


def test_resolution_reports_every_problem():
    with pytest.raises(ResolveError) as ei:
        resolve_load_order([
            mm("aa", depends={"missing": VersionSpec("*"), "bb": VersionSpec("^2.0.0")}),
            mm("bb"), mm("cc", conflicts=("bb",)), mm("bb2", conflicts=("cc",)),
            mm("x1", load_after=("x2",)), mm("x2", load_after=("x1",)), mm("bb")])
    p = " | ".join(ei.value.problems)
    for frag in ("duplicate mod bb", "requires missing missing", "requires bb ^2.0.0, found 1.0.0",
                 "bb conflicts with cc", "bb2 conflicts with cc", "cycle among ['x1', 'x2']"):
        assert frag in p
    assert p.count("conflicts with cc") == 2


def hook(m, ops):
    return DeclarativeHook.from_list(m, ops)


def test_hooks_override_and_extend_without_mutating_input():
    m = mm("tweak")
    h = hook(m, [
        {"op": "set", "path": "levels[id=cave].name", "value": "Crystal Cave"},
        {"op": "scale", "path": "player.speed", "factor": 10, "max": 20},
        {"op": "merge", "path": "player", "value": {"jump": 2}},
        {"op": "append", "path": "levels", "value": [{"id": "bonus", "name": "Bonus"}]},
        {"op": "remove", "path": "levels[id=gate]"}])
    out = apply_mods(PLAN, resolve_load_order([m]), {"tweak": h})
    assert out["levels"] == [{"id": "cave", "name": "Crystal Cave"}, {"id": "bonus", "name": "Bonus"}]
    assert out["player"] == {"speed": 20, "hp": 10, "jump": 2}
    assert PLAN["levels"][0]["name"] == "Cave" and len(PLAN["levels"]) == 2


def test_permissions_targets_and_safety_enforced():
    ro = mm("ro", permissions=("add_content",))
    with pytest.raises(HookError, match="override_content"):
        hook(ro, [{"op": "set", "path": "title", "value": "x"}])
    with pytest.raises(HookError, match="add_content"):
        hook(mm("none", permissions=()), [{"op": "append", "path": "levels", "value": []}])
    scoped = mm("scoped", targets=("levels",))
    with pytest.raises(HookError, match="outside declared targets"):
        hook(scoped, [{"op": "set", "path": "player.hp", "value": 1}])
    hook(scoped, [{"op": "set", "path": "levels[0].name", "value": "ok"}])
    for bad in ([{"op": "exec", "path": "title"}], [{"op": "set", "path": "a..b", "value": 1}],
                [{"op": "scale", "path": "player.hp", "factor": float("inf")}],
                [{"op": "set", "path": "title", "value": print}], "not-a-list"):
        with pytest.raises(HookError):
            hook(mm("bad"), bad)
    with pytest.raises(HookError, match="would overwrite"):
        apply_mods(PLAN, resolve_load_order([mm("m1")]),
                   {"m1": hook(mm("m1"), [{"op": "merge", "path": "player", "value": {"hp": 99}}])})


def test_mod_scale_overflow_fails_closed_even_when_clamped():
    m = mm("large")
    h = hook(m, [{"op": "scale", "path": "player.speed", "factor": 1e308, "max": 5}])
    original = {"player": {"speed": 1e308}}
    with pytest.raises(HookError, match="scale result is not finite"):
        apply_mods(original, resolve_load_order([m]), {"large": h})
    assert original["player"]["speed"] == 1e308


def test_mod_scale_rejects_nonfinite_and_huge_integer_targets():
    m = mm("large")
    h = hook(m, [{"op": "scale", "path": "player.speed", "factor": 2}])
    with pytest.raises(HookError, match="not finite"):
        h.apply({"plan": {"player": {"speed": float("inf")}}})
    with pytest.raises(HookError, match="numeric overflow"):
        h.apply({"plan": {"player": {"speed": 10 ** 400}}})


def test_override_conflict_unless_explicitly_ordered():
    a, b = mm("aaa"), mm("bbb")
    ops = [{"op": "set", "path": "levels[0].name", "value": "A"}]
    ops_b = [{"op": "set", "path": "levels[id=cave].name", "value": "B"}]  # same key, other form
    with pytest.raises(HookError, match="override conflict on levels.\\[id=cave\\].name"):
        apply_mods(PLAN, resolve_load_order([a, b]), {"aaa": hook(a, ops), "bbb": hook(b, ops_b)})
    b2 = mm("bbb", load_after=("aaa",))
    out = apply_mods(PLAN, resolve_load_order([a, b2]), {"aaa": hook(a, ops), "bbb": hook(b2, ops_b)})
    assert out["levels"][0]["name"] == "B"


def test_pack_unpack_roundtrip_via_bundle_and_b099():
    m = mm("gems", "1.2.0", permissions=("add_content",))
    ops = [{"op": "append", "path": "levels", "value": [{"id": "gem", "name": "Gem"}]}]
    raw = pack_mod(m, ops, KEY, CODEC, assets={"assets/readme.md": "hi"})
    assert raw == pack_mod(m, ops, KEY, CODEC, assets={"assets/readme.md": "hi"})
    got, h, caps = unpack_mod(raw, KEY, CODEC)
    assert got == m and [c.permission for c in caps] == ["add_content"]
    assert apply_mods(PLAN, resolve_load_order([got]), {"gems": h})["levels"][-1]["id"] == "gem"
    with pytest.raises(ModError, match="signature"):
        unpack_mod(raw, b"x" * 32, CODEC)
    with pytest.raises(ModError, match="moderation"):
        unpack_mod(raw, KEY, CODEC, moderate=lambda p: False)
    with pytest.raises(ModError):
        pack_mod(m, ops, KEY, CODEC, assets={"bin/x.so": ""})
    with pytest.raises(HookError):
        pack_mod(m, [{"op": "set", "path": "title", "value": 1}], KEY, CODEC)


@pytest.mark.parametrize("bad", [
    "||", "1.2.3 ||", "|| 1.2.3", "1.2.3 || || 2.0.0", "* ||",
])
def test_version_specs_reject_empty_or_alternatives(bad):
    """An empty OR branch must not grant unrestricted dependency versions."""
    with pytest.raises(ModError, match="empty version spec alternative"):
        VersionSpec(bad)


@pytest.mark.parametrize("bad", [
    "1.0.0-alpha..1", "1.0.0-.alpha", "1.0.0-alpha.",
    "1.0.0-01", "1.0.0-alpha.001",
])
def test_semver_rejects_noncanonical_prerelease_identifiers(bad):
    with pytest.raises(ModError, match="invalid semver"):
        SemVer.parse(bad)


def test_hook_validation_cannot_be_bypassed_by_mutating_caller_owned_ops():
    """Directly constructed hooks must execute the validated op snapshot."""
    m = mm("scoped", permissions=("add_content",), targets=("levels",))
    original = {"op": "append", "path": "levels",
                "value": [{"id": "safe", "name": "Safe"}]}
    h = DeclarativeHook(m, (original,))
    # A frozen dataclass does not freeze the mutable mappings passed into it.
    original["op"] = "remove"
    original["path"] = "player.hp"
    original["value"][0]["id"] = "tampered"
    assert h.override_keys(PLAN) == set()
    result = apply_mods(PLAN, resolve_load_order([m]), {"scoped": h})
    assert result["levels"][-1] == {"id": "safe", "name": "Safe"}
    assert result["player"]["hp"] == 10
    assert PLAN["levels"][-1]["id"] == "gate"


def test_mod_manifest_rejects_unbounded_versions_and_target_scopes():
    """Hostile mod metadata cannot force unbounded parsing or target scans."""
    for value in ("1" * 5000 + ".0.0", "1.0.0-" + "a" * 5000):
        with pytest.raises(ModError, match="semver"):
            SemVer.parse(value)
    valid = mm("safe").to_dict()
    for targets in (["levels"] * 33, ["x" * 257], ["levels\\nother"]):
        with pytest.raises(ModError, match="targets"):
            ModManifest.from_dict({**valid, "targets": targets})
    with pytest.raises(ModError, match="targets"):
        mm("direct", targets=tuple(["levels"] * 33))
    assert ModManifest.from_dict({**valid, "targets": ["levels"]}).targets == ("levels",)

def test_resolver_rejects_unbounded_and_malformed_inputs():
    from itertools import repeat
    from skeleton.ai.game_builder.mods.resolve import MAX_RESOLVE_MODS

    with pytest.raises(ResolveError, match="count exceeds"):
        resolve_load_order(repeat(mm("same"), MAX_RESOLVE_MODS + 1))
    with pytest.raises(ResolveError, match="invalid mod manifest"):
        resolve_load_order([mm("good"), object()])
    assert resolve_load_order([mm("good")]).ids() == ["good"]


def test_resolver_rejects_unbounded_direct_manifest_edges():
    from dataclasses import replace
    from skeleton.ai.game_builder.mods.resolve import MAX_RESOLVE_REFERENCES

    direct = replace(mm("core"), load_after=tuple(
        f"mod{i}" for i in range(MAX_RESOLVE_REFERENCES + 1)))
    with pytest.raises(ResolveError, match="dependency graph exceeds"):
        resolve_load_order([direct])


def test_resolver_iterator_failure_is_typed_and_never_returns_partial_plan():
    def broken_inventory():
        yield mm("good")
        raise RuntimeError("untrusted inventory stopped")

    with pytest.raises(ResolveError, match="mod inventory iterator failed"):
        resolve_load_order(broken_inventory())

    class HostileManifest(ModManifest):
        @property
        def mod_id(self):
            raise AssertionError("subclass hook executed")

    # A forged subclass must not be consulted by the graph resolver.
    forged = object.__new__(HostileManifest)
    with pytest.raises(ResolveError, match="invalid mod manifest"):
        resolve_load_order([forged])
