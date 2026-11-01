"""Tests for #807 B099 (modding/UGC sandbox), adapted from Ørjan's draft."""

from dataclasses import replace

from skeleton.gameforge.batch_b09x import b099_ugc_sandbox as m

K = "-".join(
    ["test", "signing", "material"]
).encode()  # built at runtime; not a real secret


def pkg(**kw):
    p = replace(
        m.ModPackage("hats", "1.0", (1, 0), ("add_content",), {"hat.tres": "data"}),
        **kw,
    )
    return replace(p, signature=m.sign(p, K))


def test_install_grants_scoped_permissions():
    status, caps = m.install(pkg(), K, lambda p: True)
    assert status == "installed" and caps == [
        m.ModGrant("mod:hats", "add_content", "hats")
    ]


def test_custom_grant_hook_receives_scoped_calls():
    seen = []
    m.install(
        pkg(permissions=("ui_overlay", "add_content")),
        K,
        lambda p: True,
        grant=lambda *a: seen.append(a) or a,
    )
    assert seen == [
        ("mod:hats", "add_content", "hats"),
        ("mod:hats", "ui_overlay", "hats"),
    ]


def test_rejections_grant_nothing():
    seen = []
    g = lambda *a: seen.append(a)  # noqa: E731
    ok = lambda p: True  # noqa: E731
    assert m.install(replace(pkg(), version="2"), K, ok, g)[0] == "rejected:signature"
    assert m.install(pkg(), b"other", ok, g)[0] == "rejected:signature"
    assert m.install(pkg(sdk_api=(2, 0)), K, ok, g)[0] == "rejected:incompatible"
    assert m.install(pkg(permissions=("network",)), K, ok, g)[0].startswith(
        "rejected:permissions"
    )
    assert m.install(pkg(files={"x.dll": "MZ"}), K, ok, g)[0] == "rejected:native_code"
    assert m.install(pkg(), K, lambda p: False, g)[0] == "rejected:moderation"
    assert seen == []


def test_signature_covers_file_contents():
    p = pkg()
    tampered = replace(p, files={"hat.tres": "evil"})
    assert m.install(tampered, K, lambda p: True)[0] == "rejected:signature"


def test_signed_unsafe_member_paths_fail_closed_before_grants():
    seen = []
    for name in ("../escape.tres", "/absolute.tres", "C:\\\\system.dll", "dir/./x.tres",
                 "dir//x.tres", "dir/../x.tres", "dir/\\\\x.tres", "dir/\u0000x.tres"):
        status, caps = m.install(
            pkg(files={name: "data"}), K, lambda p: True,
            grant=lambda *a: seen.append(a),
        )
        assert status == "rejected:unsafe_path" and caps == []
    assert seen == []


def test_casefolded_native_extensions_and_duplicate_grants_rejected():
    seen = []
    grant = lambda *a: seen.append(a)
    for name in ("MOD.EXE", "lib.DlL", "lib.SO", "plugin.DYLIB"):
        status, caps = m.install(pkg(files={name: "data"}), K, lambda p: True, grant)
        assert status == "rejected:native_code" and caps == []
    status, caps = m.install(
        pkg(permissions=("add_content", "add_content")), K, lambda p: True, grant
    )
    assert status == "rejected:permissions:duplicate" and caps == []
    assert seen == []
