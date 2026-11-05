"""Offline parser tests for skeleton.godot_export (variant, ConfigFile, tscn, version, logs, pck)."""
from __future__ import annotations

import math
import struct

import pytest

from skeleton.godot_export import configfile, logscan, pck, tscn, variant, version


@pytest.mark.parametrize("text, expected", [
    ("true", True), ("false", False), ("null", None), ("42", 42), ("-7", -7), ("0x1F", 31),
    ("1.5", 1.5), ("-1.5e3", -1500.0), ('"a\\"b"', 'a"b'), ('"line\\nnext"', "line\nnext"),
    ("[]", []), ("[1, 2, 3]", [1, 2, 3]), ("{}", {}), ('{"k": [1, {"n": null}]}', {"k": [1, {"n": None}]}),
])
def test_variant_scalars_and_containers(text, expected):
    assert variant.parse(text) == expected


def test_variant_constructors_and_special_strings():
    v = variant.parse("Vector3(0, 1.5, -2)")
    assert v == variant.Constructor("Vector3", (0, 1.5, -2))
    assert variant.parse('&"jump"') == variant.StringName("jump")
    assert variant.parse('^"Player/Camera3D"') == variant.NodePath("Player/Camera3D")
    assert variant.parse('ExtResource("1_abc")').args == ("1_abc",)
    assert variant.parse("Transform3D()") == variant.Constructor("Transform3D", ())


def test_variant_typed_containers_round_trip():
    arr = variant.parse('Array[StringName]([&"a", &"b"])')
    assert arr.name == "Array[StringName]"
    assert arr.args == ([variant.StringName("a"), variant.StringName("b")],)
    assert variant.parse(variant.dump(arr)) == arr
    d = variant.parse('Dictionary[String, int]({"hp": 3})')
    assert d.name == "Dictionary[String,int]" and d.args == ({"hp": 3},)


def test_variant_inf_nan():
    assert variant.parse("inf") == math.inf
    assert variant.parse("-inf") == -math.inf
    assert math.isnan(variant.parse("nan"))


@pytest.mark.parametrize("bad", ["", "[1, 2", "{\"a\" 1}", "bareword", "1 2", '"unterminated', "Array[int"])
def test_variant_rejects_malformed(bad):
    with pytest.raises(variant.VariantParseError):
        variant.parse(bad)


@pytest.mark.parametrize("value", [
    True, None, 3, -0.25, 1.0, "q\"uote\\", [1, "x", [None]], {"a": {"b": 2}},
    variant.Constructor("Color", (1, 0.5, 0, 1)), variant.StringName("n"), variant.NodePath("A/B"),
])
def test_variant_dump_parse_round_trip(value):
    assert variant.parse(variant.dump(value)) == value


def test_variant_is_complete_tracks_brackets_and_strings():
    assert variant.is_complete("[1, 2]")
    assert not variant.is_complete("[1,")
    assert not variant.is_complete('"open [')
    assert variant.is_complete('"]" ')


def test_variant_dump_rejects_unknown_type():
    with pytest.raises(TypeError):
        variant.dump(object())


PROJECT = """; comment
config_version=5

[application]

config/name="Demo"
config/features=PackedStringArray("4.7", "Mobile")
run/main_scene="res://main.tscn"

[input]

jump={
"deadzone": 0.5,
"events": []
}
"""


def test_configfile_parses_header_sections_and_multiline():
    cfg = configfile.loads(PROJECT)
    assert cfg.header == {"config_version": 5}
    assert cfg.get("application", "config/name") == "Demo"
    assert cfg.get("input", "jump") == {"deadzone": 0.5, "events": []}
    assert cfg.keys("application") == ["config/name", "config/features", "run/main_scene"]
    assert cfg.section_names("app") == ["application"]
    assert ("input", "jump", {"deadzone": 0.5, "events": []}) in list(cfg.items())


def test_configfile_round_trip_is_stable():
    cfg = configfile.loads(PROJECT)
    again = configfile.loads(cfg.dumps())
    assert again.header == cfg.header and again.sections == cfg.sections
    assert configfile.loads(again.dumps()).dumps() == again.dumps()


def test_configfile_set_is_additive():
    cfg = configfile.loads(PROJECT)
    cfg.set("physics", "common/physics_ticks_per_second", 60)
    assert cfg.has_section("physics")
    assert configfile.loads(cfg.dumps()).get("physics", "common/physics_ticks_per_second") == 60


@pytest.mark.parametrize("text, line", [
    ("[a]\n[a]\n", 2), ("[a]\nnot a pair\n", 2), ("[a]\nk={\n", 2), ("[a]\nk=bare\n", 2),
])
def test_configfile_errors_carry_line_numbers(text, line):
    with pytest.raises(configfile.ConfigParseError) as exc:
        configfile.loads(text, "x.cfg")
    assert exc.value.line == line
    assert "x.cfg" in str(exc.value)


SCENE = """[gd_scene load_steps=3 format=3 uid="uid://abc"]

[ext_resource type="Script" path="res://p.gd" id="1_p"]

[sub_resource type="BoxShape3D" id="box"]
size = Vector3(1, 1, 1)

[node name="Root" type="Node3D"]

[node name="Body" type="RigidBody3D" parent="."]
mass = 3.0
script = ExtResource("1_p")
metadata/tags = [
"a",
"b"
]

[node name="Shape" type="CollisionShape3D" parent="Body"]
shape = SubResource("box")

[node name="Inst" parent="." instance=ExtResource("1_p")]

[connection signal="body_entered" from="Body" to="." method="_on_hit"]
"""


def test_tscn_structure():
    s = tscn.loads(SCENE, "s.tscn")
    assert s.kind == "gd_scene" and s.format == 3
    assert [e.path for e in s.ext_resources] == ["res://p.gd"]
    assert [b.attrs["id"] for b in s.sub_resources] == ["box"]
    assert [n.path for n in s.nodes] == [".", "Body", "Body/Shape", "Inst"]
    assert s.root().name == "Root"
    body = s.nodes_of_type("RigidBody3D")[0]
    assert body.props["mass"] == 3.0 and body.props["metadata/tags"] == ["a", "b"]
    assert s.nodes[-1].instance == "1_p"
    assert len(s.connections) == 1
    assert s.referenced_ids() == {("ExtResource", "1_p"), ("SubResource", "box")}


@pytest.mark.parametrize("text", [
    "", "mass = 1\n", "[node name=\"A\"]\n", "[gd_scene format=3]\n[node name=]\n",
    "[gd_scene format=3]\n[node name=\"A\"]\nx = [1,\n", "[gd_scene format=3]\n[node name=\"A\"]\n???\n",
])
def test_tscn_rejects_malformed(text):
    with pytest.raises(tscn.SceneParseError):
        tscn.loads(text)


def test_tres_resource_header_accepted():
    s = tscn.loads('[gd_resource type="Theme" format=3]\n\n[resource]\ndefault_font_size = 14\n')
    assert s.kind == "gd_resource" and s.blocks[0].props == {"default_font_size": 14}


@pytest.mark.parametrize("text, short, status", [
    ("4.7.2.stable.official.abc1234", "4.7.2", "stable"), ("4.3-stable", "4.3.0", "stable"),
    ("v4.4.beta2.custom_build", "4.4.0", "beta2"), ("4.7", "4.7.0", "stable"),
])
def test_version_parse(text, short, status):
    v = version.parse(text.replace("-", "."))
    assert v.short() == short and v.status == status


def test_version_ordering_and_pin():
    p = version.parse
    assert p("4.4.beta1") < p("4.4.beta2") < p("4.4.rc1") < p("4.4.stable") < p("4.4.1")
    assert p("4.7.2.stable.official.deadbeef").matches_pin("4.7.2")
    assert not p("4.7.1.stable").matches_pin("4.7.2")
    assert not p("4.7.2.rc1").matches_pin("4.7.2")
    assert version.feature_version(["Forward Plus", "4.7"]).short() == "4.7.0"
    assert version.feature_version(["Mobile"]) is None
    with pytest.raises(ValueError):
        p("Godot Engine")


def test_logscan_classifies_lines():
    out = "\n".join([
        "Godot Engine v4.7.2.stable.official",
        "WARNING: something minor",
        "ERROR: Condition failed",
        "SCRIPT ERROR: Parse Error: Unexpected token",
        "  Failed loading resource: res://gone.tres",
        "ERROR: No audio driver found",  # benign headless noise
        "ALSA lib pcm.c: unable to open",
    ])
    s = logscan.scan(out)
    assert s.warnings == ["WARNING: something minor"]
    assert s.fatal == ["ERROR: Condition failed", "SCRIPT ERROR: Parse Error: Unexpected token"]
    assert s.missing == ["Failed loading resource: res://gone.tres"]
    assert not s.clean
    assert logscan.scan("Godot Engine v4.7.2\nImport done\n").clean


def test_logscan_limit():
    s = logscan.scan("\n".join(["ERROR: x"] * 10), limit=3)
    assert len(s.fatal) == 3


def test_pck_standalone_and_embedded(tmp_path):
    hdr = pck.build_header((4, 7, 2), 5)
    h = pck.parse_header(hdr + b"\0" * 32)
    assert (h.format_version, h.engine, h.file_count, h.encrypted_dir) == (2, (4, 7, 2), 5, False)
    assert pck.parse_header(pck.build_header((4, 3, 0), 1, fmt=1)).flags == 0
    assert pck.parse_header(pck.build_header((4, 7, 2), 1, flags=1)).encrypted_dir

    standalone = tmp_path / "game.pck"
    standalone.write_bytes(hdr)
    assert pck.read(standalone).file_count == 5

    body = hdr + b"payload"
    exe = tmp_path / "game.x86_64"
    exe.write_bytes(b"\x7fELF" + b"\0" * 100 + body + struct.pack("<Q", len(body)) + pck.MAGIC)
    emb = pck.read(exe)
    assert emb.offset == 104 and emb.file_count == 5


def test_pck_rejects_bad_input(tmp_path):
    with pytest.raises(pck.PckError):
        pck.parse_header(b"NOPE" + b"\0" * 100)
    with pytest.raises(pck.PckError):
        pck.parse_header(pck.MAGIC + b"\1\0")
    with pytest.raises(pck.PckError):
        pck.parse_header(pck.build_header((4, 0, 0), 1, fmt=9))
    plain = tmp_path / "plain.bin"
    plain.write_bytes(b"\x7fELF" + b"\0" * 64)
    with pytest.raises(pck.PckError):
        pck.read(plain)
    assert pck.find_embedded(b"short") is None
    assert pck.find_embedded(b"\0" * 20 + struct.pack("<Q", 999) + pck.MAGIC) is None
