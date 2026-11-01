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


def test_custom_grant_hook_rejects_nonatomic_multiple_permissions():
    seen = []
    status, caps = m.install(
        pkg(permissions=("ui_overlay", "add_content")),
        K,
        lambda p: True,
        grant=lambda *a: seen.append(a) or a,
    )
    assert status == "rejected:non_atomic_grant" and caps == []
    assert seen == []


def test_custom_single_grant_receives_scoped_call():
    seen = []
    status, caps = m.install(
        pkg(), K, lambda p: True,
        grant=lambda *a: seen.append(a) or a,
    )
    assert status == "installed"
    assert seen == [("mod:hats", "add_content", "hats")]
    assert caps == seen


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


def test_unicode_alias_and_casefold_collision_rejected_before_grants():
    seen = []
    for files in (
        {"dir\\leaf.tres": "data"},
        {"fullwidth\uff0fname.tres": "data"},
        {"A.tres": "a", "a.tres": "b"},
    ):
        status, caps = m.install(
            pkg(files=files), K, lambda _: True,
            grant=lambda *args: seen.append(args),
        )
        assert status == "rejected:unsafe_path" and caps == []
    assert seen == []


def test_compression_misleading_oversize_and_aggregate_inputs_rejected():
    from unittest.mock import patch

    with patch.object(m, "MAX_FILE_BYTES", 8):
        status, caps = m.install(
            replace(pkg(), files={"huge": "repeated" * 100}),
            K, lambda _: True,
        )
        assert status == "rejected:files" and caps == []
    with patch.object(m, "MAX_TOTAL_BYTES", 12):
        status, caps = m.install(
            replace(pkg(), files={"one": "12345", "two": "12345"}),
            K, lambda _: True,
        )
        assert status == "rejected:files" and caps == []


def test_moderation_exception_and_untrusted_non_json_body_fail_closed():
    assert m.install(pkg(), K, lambda _: (_ for _ in ()).throw(RuntimeError("failed"))) == (
        "rejected:moderation", []
    )
    status, caps = m.install(
        replace(pkg(), files={"x": float("nan")}), K, lambda _: True,
    )
    assert status == "rejected:files" and caps == []


def test_no_grants_after_signature_mismatch_from_mutated_file_body():
    p = pkg()
    p.files["hat.tres"] = "swapped"
    status, caps = m.install(p, K, lambda _: True)
    assert status == "rejected:signature" and caps == []
