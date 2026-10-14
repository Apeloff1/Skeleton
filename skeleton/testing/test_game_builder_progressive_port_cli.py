"""Original-homebrew progressive route CLI: no external media or network required."""
from __future__ import annotations

import json

import pytest

from skeleton.ai.game_builder.progressive_port_cli import main, preview_from_argv

PROOF = "9" * 64


def arguments(*destinations, mode="enhanced"):
    result = [
        "--project-id", "owned-clockwork-platformer",
        "--source", "bandai_wonderswan",
        "--rights-basis", "project_owned",
        "--evidence-sha256", PROOF,
        "--identity", "author-created engine and rules",
        "--identity", "own graphic style",
        "--mode", mode,
    ]
    for destination in destinations:
        result.extend(("--destination", destination))
    return result


def test_cli_produces_true_hop_lineage_and_never_promises_binary_or_release():
    options = arguments("windows_modern", "nintendo_game_boy", "linux_desktop")
    result = preview_from_argv(options)
    assert result["schema"] == "skeleton.game_builder.progressive_route_preview.v1"
    assert result["original_evidence_sha256"] == PROOF
    assert [item["to"] for item in result["hops"]] == [
        "windows_modern", "nintendo_game_boy", "linux_desktop",
    ]
    assert [item["from"] for item in result["hops"]] == [
        "bandai_wonderswan", "windows_modern", "nintendo_game_boy",
    ]
    assert result["hops"][1]["previous_design_digest"] == result["hops"][0]["design_digest"]
    assert all(item["native_binary_built"] is False for item in result["hops"])
    assert all(item["distribution_authorized"] is False for item in result["hops"])
    assert result == preview_from_argv(options)


def test_cli_prints_one_canonical_json_record_without_file_side_effects(capsys, tmp_path):
    before = set(tmp_path.iterdir())
    assert main(arguments("windows_modern")) == 0
    line = capsys.readouterr().out.strip()
    payload = json.loads(line)
    assert payload["original_project_id"] == "owned-clockwork-platformer"
    assert payload["native_binary_built"] is False
    assert line == json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"), allow_nan=False)
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("replace_arg", [
    ("--evidence-sha256", "claimed"),
    ("--source", "unknown_hardware"),
    ("--project-id", ""),
    ("--mode", "cross_hybrid"),
])
def test_cli_fails_closed_when_rights_or_hardware_arguments_are_invalid(replace_arg):
    args = arguments("windows_modern")
    old, new = replace_arg
    i = args.index(old)
    args[i+1] = new
    with pytest.raises(SystemExit) as exc:
        preview_from_argv(args)
    assert exc.value.code == 2


def test_cli_refuses_duplicate_targets_and_cycles():
    for destinations in (
        ("windows_modern", "windows_modern"),
        ("bandai_wonderswan",),
        (),
    ):
        with pytest.raises(SystemExit) as exc:
            preview_from_argv(arguments(*destinations))
        assert exc.value.code == 2


def test_cli_derives_hash_from_operator_owned_evidence_file(tmp_path):
    from hashlib import sha256
    source = tmp_path / "authorship.txt"
    source.write_bytes(b"Original authored console game; copyright owner notes.")
    args = arguments("windows_modern")
    i = args.index("--evidence-sha256")
    args[i:i+2] = ["--rights-evidence-file", str(source)]
    result = preview_from_argv(args)
    assert result["original_evidence_sha256"] == sha256(source.read_bytes()).hexdigest()
    assert result["rights_independently_verified"] is False
    assert result["distribution_authorized"] is False


def test_cli_rejects_symlinked_rights_document_before_preview(tmp_path):
    original = tmp_path / "original.txt"
    original.write_text("Owned game design", encoding="utf-8")
    shortcut = tmp_path / "shortcut.txt"
    try:
        shortcut.symlink_to(original)
    except OSError:
        pytest.skip("symlink test requires symlink-capable filesystem")
    args = arguments("windows_modern")
    index = args.index("--evidence-sha256")
    args[index:index+2] = ["--rights-evidence-file", str(shortcut)]
    with pytest.raises(SystemExit) as exc:
        preview_from_argv(args)
    assert exc.value.code == 2


def test_cli_refuses_competing_manual_and_file_evidence_claims(tmp_path):
    file = tmp_path / "authored.txt"
    file.write_bytes(b"own source")
    args = arguments("windows_modern")
    args.extend(("--rights-evidence-file", str(file)))
    with pytest.raises(SystemExit) as exc:
        preview_from_argv(args)
    assert exc.value.code == 2
