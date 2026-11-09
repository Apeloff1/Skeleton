"""Fail-closed capability inventory: unknown stays unknown, never guessed safe."""

from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.inventory.capabilities import (
    CAPABILITY_NAMES,
    CONFLICT_DOMAIN,
    SCHEMA_VERSION,
    TASK_ID,
    CapabilityInventory,
    classify_path,
    classify_text,
    inventory_from_mapping,
    inventory_paths,
    inventory_repository,
    inventory_snapshot,
    secret_like_path,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER = Path("skeleton/inventory/capabilities.py")


def _verdicts(record) -> dict[str, str]:
    return dict(record.capabilities)


def test_secret_like_paths_mark_secret_access_present(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TOKEN=example\n", encoding="utf-8")
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "id_ed25519").write_text("not-a-real-key\n", encoding="utf-8")
    (tmp_path / "certs").mkdir()
    (tmp_path / "certs" / "tls.pem").write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")

    env = classify_path(tmp_path, ".env")
    key = classify_path(tmp_path, ".ssh/id_ed25519")
    pem = classify_path(tmp_path, "certs/tls.pem")

    assert secret_like_path(".env")
    assert secret_like_path(".env.production")
    assert secret_like_path("credentials.json")
    assert env.kind == key.kind == pem.kind == "secret_like"
    assert env.verdict("secret_access") == "present"
    assert key.verdict("secret_access") == "present"
    assert pem.verdict("secret_access") == "present"
    assert env.reasons["secret_access"] == ("path matches a secret-bearing location",)


def test_secret_like_paths_do_not_guess_other_capabilities_absent(tmp_path: Path) -> None:
    (tmp_path / ".env.local").write_text("OPENAI_API_KEY=sk-example\n", encoding="utf-8")
    record = classify_path(tmp_path, ".env.local")
    for name in CAPABILITY_NAMES:
        if name == "secret_access":
            assert record.verdict(name) == "present"
        else:
            assert record.verdict(name) == "unknown"


def test_workflow_write_permissions_mark_github_mutation() -> None:
    text = """name: mutate
on: [push]
permissions:
  contents: write
  pull-requests: write
jobs:
  ship:
    runs-on: ubuntu-latest
    steps:
      - run: gh pr comment 1 --body ok
"""
    record = classify_text(".github/workflows/mutate.yml", text)
    assert record.kind == "workflow"
    assert record.verdict("github_mutation") == "present"
    assert record.verdict("subprocess") == "present"
    assert record.verdict("secret_access") == "absent"


def test_workflow_empty_permissions_are_not_github_mutation() -> None:
    text = """name: safe
on: [push]
permissions: {}
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: echo hello
"""
    record = classify_text(".github/workflows/safe.yml", text)
    assert record.verdict("github_mutation") == "absent"
    assert record.verdict("subprocess") == "present"
    assert record.verdict("filesystem_write") == "unknown"
    assert record.verdict("network") == "unknown"


def test_workflow_missing_permissions_stay_unknown() -> None:
    text = """name: opaque
on: [push]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: echo hello
"""
    record = classify_text(".github/workflows/opaque.yml", text)
    assert record.verdict("github_mutation") == "unknown"
    assert "unknown stays unknown" in " ".join(record.reasons["github_mutation"])


def test_workflow_opaque_yaml_stays_unknown() -> None:
    text = """name: aliased
x-perms: &perms
  contents: write
permissions: *perms
jobs: {}
"""
    record = classify_text(".github/workflows/aliased.yml", text)
    assert record.kind == "workflow"
    assert all(record.verdict(name) == "unknown" for name in CAPABILITY_NAMES)


def test_workflow_read_only_with_secrets_leaves_mutation_unknown() -> None:
    text = """name: deploy
on: [push]
permissions:
  contents: read
jobs:
  notify:
    runs-on: ubuntu-latest
    env:
      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
    steps:
      - run: echo "$TOKEN"
"""
    record = classify_text(".github/workflows/deploy.yml", text)
    assert record.verdict("secret_access") == "present"
    assert record.verdict("github_mutation") == "unknown"


def test_unknown_files_stay_unknown(tmp_path: Path) -> None:
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02")
    (tmp_path / "notes.md").write_text("# docs\n", encoding="utf-8")
    binary = classify_path(tmp_path, "blob.bin")
    markdown = classify_path(tmp_path, "notes.md")
    assert binary.kind == "unknown"
    assert markdown.kind == "unknown"
    assert all(verdict == "unknown" for verdict in binary.capabilities.values())
    assert all(verdict == "unknown" for verdict in markdown.capabilities.values())


def test_bool_is_rejected_as_integer_max_file_bytes(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(TypeError, match="max_file_bytes must be an integer"):
        classify_path(tmp_path, "mod.py", max_file_bytes=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="max_file_bytes must be an integer"):
        inventory_paths(tmp_path, ["mod.py"], max_file_bytes=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive integer"):
        classify_path(tmp_path, "mod.py", max_file_bytes=0)


def test_bool_is_rejected_as_schema_version() -> None:
    payload = {
        "schema_version": True,
        "records": [],
    }
    with pytest.raises(TypeError, match="schema_version must be an integer"):
        inventory_from_mapping(payload)
    with pytest.raises(TypeError, match="schema_version must be an integer"):
        inventory_from_mapping({"schema_version": False, "records": []})


def test_missing_files_are_unknown_not_safe(tmp_path: Path) -> None:
    record = classify_path(tmp_path, "ghost.py")
    assert record.missing is True
    assert record.kind == "missing"
    assert all(verdict == "unknown" for verdict in record.capabilities.values())
    inventory = inventory_paths(tmp_path, ["ghost.py", "also-missing.yml"])
    assert len(inventory.records) == 2
    assert all(item.missing and item.verdict("network") == "unknown" for item in inventory.records)


def test_clean_python_module_is_absent(tmp_path: Path) -> None:
    (tmp_path / "pure.py").write_text("VALUE = 1\n\ndef add(left: int, right: int) -> int:\n    return left + right\n", encoding="utf-8")
    record = classify_path(tmp_path, "pure.py")
    assert record.kind == "python"
    assert _verdicts(record) == {name: "absent" for name in CAPABILITY_NAMES}


def test_python_subprocess_and_writes_are_present(tmp_path: Path) -> None:
    (tmp_path / "tool.py").write_text(
        "\n".join(
            [
                "import subprocess",
                "from pathlib import Path",
                "subprocess.run(['echo', 'ok'], check=True)",
                "Path('out.txt').write_text('ok', encoding='utf-8')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    record = classify_path(tmp_path, "tool.py")
    assert record.verdict("subprocess") == "present"
    assert record.verdict("filesystem_write") == "present"
    assert record.verdict("network") == "absent"
    assert record.verdict("github_mutation") == "absent"
    assert record.verdict("model_api") == "absent"
    assert record.verdict("secret_access") == "absent"


def test_python_eval_stays_unknown(tmp_path: Path) -> None:
    (tmp_path / "dynamic.py").write_text("payload = eval(open('x').read())\n", encoding="utf-8")
    record = classify_path(tmp_path, "dynamic.py")
    assert record.verdict("network") == "unknown"
    assert record.verdict("subprocess") == "unknown"
    assert record.verdict("github_mutation") == "unknown"
    assert record.verdict("model_api") == "unknown"
    assert record.verdict("secret_access") == "unknown"


def test_python_secret_and_model_env_are_present(tmp_path: Path) -> None:
    (tmp_path / "client.py").write_text(
        "import os\n"
        "token = os.environ['OPENAI_API_KEY']\n"
        "other = os.getenv('GITHUB_TOKEN')\n",
        encoding="utf-8",
    )
    record = classify_path(tmp_path, "client.py")
    assert record.verdict("secret_access") == "present"
    assert record.verdict("model_api") == "present"
    assert record.verdict("network") == "absent"


def test_inventory_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("import subprocess\n", encoding="utf-8")
    first = inventory_paths(tmp_path, ["b.py", "a.py", "b.py"])
    second = inventory_paths(tmp_path, ["a.py", "b.py"])
    assert [record.path for record in first.records] == ["a.py", "b.py"]
    assert inventory_snapshot(first) == inventory_snapshot(second)


def test_snapshot_round_trip_and_metadata() -> None:
    record = classify_text("mod.py", "VALUE = 1\n")
    snapshot = inventory_snapshot(CapabilityInventory(schema_version=SCHEMA_VERSION, records=(record,)))
    assert snapshot["schema_version"] == SCHEMA_VERSION == 1
    assert snapshot["task_key"] == TASK_ID
    assert snapshot["conflict_domain"] == CONFLICT_DOMAIN
    restored = inventory_from_mapping(snapshot)
    assert restored.records[0].path == "mod.py"
    assert restored.records[0].verdict("network") == "absent"


def test_classifier_module_has_no_side_effect_capabilities() -> None:
    record = classify_path(REPO_ROOT, CLASSIFIER)
    assert record.kind == "python"
    assert record.missing is False
    assert _verdicts(record) == {name: "absent" for name in CAPABILITY_NAMES}


def test_repository_inventory_is_deterministic_and_fail_closed() -> None:
    first = inventory_repository(REPO_ROOT)
    second = inventory_repository(REPO_ROOT)
    assert [record.path for record in first.records] == [record.path for record in second.records]
    assert inventory_snapshot(first) == inventory_snapshot(second)
    assert any(record.kind == "workflow" for record in first.records)
    assert any(record.path == CLASSIFIER.as_posix() for record in first.records)
    for record in first.records:
        assert set(record.capabilities) == set(CAPABILITY_NAMES)
        for name, verdict in record.capabilities.items():
            assert verdict in {"present", "absent", "unknown"}
            if verdict == "unknown":
                assert record.reasons[name], f"{record.path}:{name} unknown without reason"


def test_path_escape_stays_unknown(tmp_path: Path) -> None:
    record = classify_path(tmp_path, "../outside.py")
    assert record.verdict("network") == "unknown"
    assert record.kind == "unknown"


def test_unknown_capability_name_is_not_invented() -> None:
    record = classify_text("mod.py", "VALUE = 1\n")
    with pytest.raises(KeyError, match="unknown capability name"):
        record.verdict("shell")
