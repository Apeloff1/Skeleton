from __future__ import annotations

import json

from scripts import check_ai_build_queue as checker


def _payloads():
    queue = json.loads(checker.QUEUE.read_text(encoding="utf-8"))
    construction = json.loads(checker.CONSTRUCTION.read_text(encoding="utf-8"))
    return queue, construction


def test_ai_build_queue_is_valid() -> None:
    assert checker.validate() == []


def test_queue_rejects_unknown_dependency() -> None:
    queue, construction = _payloads()
    mutated = json.loads(json.dumps(queue))
    mutated["tasks"][0]["task_dependencies"] = ["AIQ-DOES-NOT-EXIST"]

    errors = checker.validate(mutated, construction)

    assert any("unknown task dependency AIQ-DOES-NOT-EXIST" in e for e in errors)


def test_queue_rejects_dependency_cycle() -> None:
    queue, construction = _payloads()
    mutated = json.loads(json.dumps(queue))
    first = mutated["tasks"][0]
    second = mutated["tasks"][1]
    first["task_dependencies"] = [second["task_id"]]
    second["task_dependencies"] = [first["task_id"]]

    errors = checker.validate(mutated, construction)

    assert any("dependency cycle detected" in e for e in errors)


def test_queue_rejects_done_task_without_verification() -> None:
    queue, construction = _payloads()
    mutated = json.loads(json.dumps(queue))
    mutated["tasks"][0]["verification_signed"] = False

    errors = checker.validate(mutated, construction)

    assert any("done task needs verification signoff" in e for e in errors)


def test_queue_rejects_unknown_gap() -> None:
    queue, construction = _payloads()
    mutated = json.loads(json.dumps(queue))
    mutated["tasks"][0]["gap"] = "gap-does-not-exist"

    errors = checker.validate(mutated, construction)

    assert any("gap is not in construction gap_register" in e for e in errors)
