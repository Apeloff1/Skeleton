from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts.check_dependency_unlocks import (
    CLASSES,
    CONFLICT_DOMAIN,
    SATISFIED_STATUSES,
    SCHEMA_VERSION,
    TASK_KEY,
    classify_blocked_task,
    classify_document,
    load_document,
    main,
    parse_task,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_dependency_unlocks.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "dependency_unlocks" / "closed-graph.v1.json"


def _task(task_key: str, status: str, prerequisites: list[str] | None = None) -> dict[str, object]:
    return {
        "task_key": task_key,
        "status": status,
        "prerequisites": [] if prerequisites is None else prerequisites,
    }


def _graph(*tasks: dict[str, object], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {"schema_version": SCHEMA_VERSION, "tasks": list(tasks)}
    payload.update(overrides)
    return payload


def test_closed_class_set_and_seed_identity() -> None:
    assert CLASSES == ("still_blocked", "unlocked", "unknown")
    assert len(CLASSES) == len(set(CLASSES))
    assert SATISFIED_STATUSES == frozenset({"validated", "merged"})
    assert TASK_KEY == "reserve-S491-dependency-unlock-scan"
    assert CONFLICT_DOMAIN == "ops.readonly.dependency_unlocks"
    assert SCHEMA_VERSION == 1


def test_all_validated_or_merged_prerequisites_unlock() -> None:
    nodes = {"S489": "validated", "S490": "merged"}
    assert classify_blocked_task(["S489", "S490"], nodes) == "unlocked"


def test_remaining_open_prerequisite_is_still_blocked() -> None:
    nodes = {"S493": "working"}
    assert classify_blocked_task(["S493"], nodes) == "still_blocked"


def test_mixed_prerequisites_stay_still_blocked() -> None:
    nodes = {"S490": "merged", "S493": "queued"}
    assert classify_blocked_task(["S490", "S493"], nodes) == "still_blocked"


def test_rejected_prerequisite_is_still_blocked() -> None:
    nodes = {"S010": "rejected"}
    assert classify_blocked_task(["S010"], nodes) == "still_blocked"


def test_missing_prerequisite_fails_closed_unknown() -> None:
    assert classify_blocked_task(["missing"], {}) == "unknown"


def test_unreadable_prerequisite_fails_closed_unknown() -> None:
    assert classify_blocked_task(["S001"], {"S001": None}) == "unknown"


def test_empty_prerequisites_fail_closed_unknown() -> None:
    assert classify_blocked_task([], {"S001": "merged"}) == "unknown"


def test_unknown_status_token_fails_closed() -> None:
    assert parse_task(_task("S001", "done")) == (None, None, None)
    assert parse_task(_task("S001", "complete")) == (None, None, None)
    assert parse_task(["not", "an", "object"]) == (None, None, None)
    assert parse_task(_task("S001", "blocked") | {"owner": "night"}) == (None, None, None)


def test_committed_fixture_classifies_unlocked_and_still_blocked() -> None:
    rows, errors = classify_document(load_document(FIXTURE))
    assert errors == []
    by_key = {row["task_key"]: row["class"] for row in rows}
    assert by_key == {
        "reserve-S491-unlock-scan": "unlocked",
        "reserve-S492-reconcile": "still_blocked",
        "reserve-S494-docs": "still_blocked",
    }
    assert "unknown" not in by_key.values()


def test_non_blocked_tasks_are_not_classified() -> None:
    rows, errors = classify_document(
        _graph(
            _task("root", "merged"),
            _task("queued", "queued"),
            _task("child", "blocked", ["root"]),
        )
    )
    assert errors == []
    assert [row["task_key"] for row in rows] == ["child"]
    assert rows[0]["class"] == "unlocked"


def test_document_unknown_blocked_row_is_a_violation() -> None:
    rows, errors = classify_document(
        _graph(_task("orphan", "blocked", ["never-shipped"]))
    )
    assert rows[0]["class"] == "unknown"
    assert any("dependency-unlock unknown unclassified" in item for item in errors)


def test_unknown_document_fields_fail_closed() -> None:
    errors = classify_document(_graph(_task("root", "merged"), mutate=True))[1]
    assert any("dependency-unlock unknown field" in item for item in errors)
    assert any("mutate" in item for item in errors)


def test_wrong_schema_version_fails_closed() -> None:
    errors = classify_document(_graph(schema_version=2, tasks=[]))[1]
    assert any("dependency-unlock unknown schema_version" in item for item in errors)


def test_missing_tasks_field_fails_closed() -> None:
    rows, errors = classify_document({"schema_version": 1})
    assert rows == []
    assert any("dependency-unlock missing_value field" in item for item in errors)
    assert any("tasks" in item for item in errors)


def test_non_object_root_fails_closed() -> None:
    rows, errors = classify_document(["not", "a", "graph"])
    assert rows == []
    assert errors == ["dependency-unlock unknown root_type: document must be an object"]


def test_duplicate_task_keys_fail_closed() -> None:
    rows, errors = classify_document(
        _graph(
            _task("dup", "merged"),
            _task("dup", "validated"),
            _task("waiter", "blocked", ["dup"]),
        )
    )
    assert any("dependency-unlock unknown duplicate_task" in item for item in errors)
    waiter = next(row for row in rows if row["task_key"] == "waiter")
    assert waiter["class"] == "unknown"


def test_unreadable_graph_node_makes_dependents_unknown() -> None:
    rows, errors = classify_document(
        _graph(
            _task("dirty", "merged") | {"extra": True},
            _task("waiter", "blocked", ["dirty"]),
        )
    )
    assert any("dependency-unlock unknown unclassified" in item for item in errors)
    assert rows[0]["class"] == "unknown"


def test_cli_accepts_committed_fixture(capsys) -> None:
    assert main([str(FIXTURE)]) == 0
    out = capsys.readouterr().out
    assert "still_blocked=2" in out
    assert "unlocked=1" in out
    assert "unknown=0" in out
    assert "unlocked: reserve-S491-unlock-scan" in out


def test_cli_rejects_unknown_blocked_tasks(tmp_path: Path, capsys) -> None:
    path = tmp_path / "graph.json"
    path.write_text(
        json.dumps(_graph(_task("blocked", "blocked", ["ghost"]))),
        encoding="utf-8",
    )
    assert main([str(path)]) == 1
    stderr = capsys.readouterr().err
    assert "Dependency unlock scan failed:" in stderr
    assert "dependency-unlock unknown unclassified" in stderr


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "dependency-unlock unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_cli_rejects_missing_document(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "dependency-unlock unreadable missing_doc" in str(exc)
    else:
        raise AssertionError("missing fixture graph must fail closed")


def test_readonly_no_mutation_surface() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".", maxsplit=1)[0])
    forbidden = {"subprocess", "urllib", "requests", "http", "socket", "os", "shutil"}
    assert modules.isdisjoint(forbidden)
    assert "gh pr" not in source
    assert "gh api" not in source
    assert "github.com" not in source.lower()


def test_not_wired_into_quality_gates() -> None:
    quality_gates = (REPO_ROOT / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    assert "check_dependency_unlocks.py" not in quality_gates
    assert "test_dependency_unlocks.py" not in quality_gates
