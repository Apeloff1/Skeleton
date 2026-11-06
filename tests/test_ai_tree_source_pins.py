"""Fail-closed integrated AI-tree source-pin maintenance regressions."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from scripts.reconcile_ai_tree_source_pins import (
    INTEGRATED_SOURCE_PIN_IDS,
    PinDrift,
    SourcePinError,
    _source_path,
    compare_pins,
    main,
    replace_pins,
)

IDS = frozenset({"AIFT-JEEVES", "AIFT-AUTOMATION"})
FIRST = "1" * 40
SECOND = "2" * 40
THIRD = "3" * 40


def _manifest(*, first: str = FIRST, second: str = SECOND):
    return {
        "mappings": [
            {"id": "AIFT-JEEVES", "source": "skeleton/jeeves",
             "source_git_object_sha": first, "role": "keep-original"},
            {"id": "AIFT-AUTOMATION", "source": "skeleton/automation",
             "source_git_object_sha": second, "role": "keep-original"},
        ],
        "status": "staged_mirror",
        "pre_move_readiness": {"implementation_complete": False},
    }


def _lookup(source: str) -> str:
    return {
        "skeleton/jeeves": THIRD,
        "skeleton/automation": SECOND,
    }[source]


def test_integration_pin_set_keeps_all_28_canonical_identities():
    assert len(INTEGRATED_SOURCE_PIN_IDS) == 28
    assert {"AIFT-JEEVES", "AIFT-AUTOMATION", "AIFT-ARCHITECTURE-LEGACY"} <= INTEGRATED_SOURCE_PIN_IDS


def test_compare_reports_exact_stale_source_and_retains_correct_peer():
    changes = compare_pins(_manifest(), _lookup, ids=IDS)
    assert changes == [PinDrift("AIFT-JEEVES", "skeleton/jeeves", FIRST, THIRD)]


def test_compare_accepts_exact_identical_pins_without_rewriting():
    changes = compare_pins(_manifest(first=THIRD), _lookup, ids=IDS)
    assert changes == []


@pytest.mark.parametrize("source", [
    "../skeleton/jeeves",
    "/skeleton/jeeves",
    "skeleton/../secrets",
    "skeleton//jeeves",
    "skeleton/./jeeves",
    "skeleton\\jeeves",
    "skeleton/jeeves:HEAD",
    "skeleton/.git/objects",
    "skeleton/a" + "\x00" + "b",
    "skeleton/",
])
def test_source_pins_reject_noncanonical_paths(source):
    with pytest.raises(SourcePinError):
        _source_path(source)


@pytest.mark.parametrize("change", ["missing", "duplicate", "invalid-sha", "invalid-source"])
def test_missing_ambiguous_or_malformed_source_mapping_fails_closed(change):
    source = _manifest()
    if change == "missing":
        source["mappings"].pop()
    elif change == "duplicate":
        source["mappings"].append(dict(source["mappings"][0]))
    elif change == "invalid-sha":
        source["mappings"][0]["source_git_object_sha"] = "bad"
    else:
        source["mappings"][0]["source"] = "backend/unsafe"
    with pytest.raises(SourcePinError):
        compare_pins(source, _lookup, ids=IDS)


def test_resolver_must_supply_real_full_git_object_identifier():
    with pytest.raises(SourcePinError, match="unresolved"):
        compare_pins(_manifest(), lambda _: "not-a-git-object", ids=IDS)


def test_replace_only_changed_identity_and_preserve_all_other_manifest_bytes():
    original = json.dumps(_manifest(), indent=2, ensure_ascii=False) + "\n"
    changed = replace_pins(
        original, [PinDrift("AIFT-JEEVES", "skeleton/jeeves", FIRST, THIRD)],
    )
    assert changed == original.replace(
        '"source_git_object_sha": "' + FIRST + '"',
        '"source_git_object_sha": "' + THIRD + '"',
    )
    assert json.loads(changed)["pre_move_readiness"]["implementation_complete"] is False
    assert '"role": "keep-original"' in changed


def test_duplicate_raw_old_sha_is_not_silently_rewritten():
    source = _manifest(second=FIRST)
    original = json.dumps(source, indent=2) + "\n"
    with pytest.raises(SourcePinError, match="ambiguous"):
        replace_pins(original, [PinDrift("AIFT-JEEVES", "skeleton/jeeves", FIRST, THIRD)])
    assert source["mappings"][1]["source_git_object_sha"] == FIRST


def test_mismatched_pin_or_owner_fails_before_patch():
    original = json.dumps(_manifest(), indent=2)
    with pytest.raises(SourcePinError, match="changed since comparison"):
        replace_pins(
            original, [PinDrift("AIFT-JEEVES", "skeleton/automation", FIRST, THIRD)],
        )


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def test_actual_git_index_checked_read_only_then_explicit_atomic_repair(tmp_path, capsys):
    """Only --write changes metadata; no Git push, force, merge or release."""
    _git(tmp_path, "init", "-q")
    entries = []
    for number, mapping_id in enumerate(sorted(INTEGRATED_SOURCE_PIN_IDS)):
        source = f"skeleton/source_pin_{number:02d}.py"
        file = tmp_path / source
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(f"VALUE = {number}\n", encoding="utf-8")
        entries.append((mapping_id, source))
    _git(tmp_path, "add", "skeleton")
    tree = _git(tmp_path, "write-tree")
    mappings = [
        {
            "id": mapping_id,
            "source": source,
            "source_git_object_sha": (
                FIRST if number == 0 else _git(tmp_path, "rev-parse", f"{tree}:{source}")
            ),
        }
        for number, (mapping_id, source) in enumerate(entries)
    ]
    index = tmp_path / "machine" / "ai_file_tree.json"
    index.parent.mkdir()
    original = json.dumps({"mappings": mappings}, indent=2) + "\n"
    index.write_text(original, encoding="utf-8")

    assert main(["--check"], root=tmp_path) == 1
    assert index.read_text(encoding="utf-8") == original
    assert "AIFT-" in capsys.readouterr().err
    assert main([], root=tmp_path) == 1
    assert index.read_text(encoding="utf-8") == original
    capsys.readouterr()
    assert main(["--write"], root=tmp_path) == 0
    assert index.read_text(encoding="utf-8") != original
    assert "Refreshed 1 AI integration source pins" in capsys.readouterr().out
    assert main(["--check"], root=tmp_path) == 0
    assert "OK (28" in capsys.readouterr().out
