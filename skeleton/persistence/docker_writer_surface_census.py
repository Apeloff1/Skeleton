"""Fail-closed static census of KNOWN canonical Mongo source mutators.

This is a source-level guardrail: it enumerates *direct* Mongo write calls in
three exact production classes and proves their protection classification has
not drifted. It does not instantiate application objects, connect to Mongo,
inspect private actor records, discover third-party writers or certify that
every production writer/process has been enrolled in the shared epoch.

The legacy deletion and projection-publication paths receive explicit,
strictly limited exceptions; adding a method or a new direct mutation always
requires an intentional review of the census. No path automatically grants
readiness, writer custody, merge or release authorization.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "skeleton.local-ai.docker.canonical-mongo-mutator-census.v1"
_MAX_FILE_BYTES = 2_000_000

# Exact, reviewed direct Mongo mutation surfaces. Public decorators cover
# actor write windows, private methods must require a bound actor, one legacy
# governed deletion operation is denied with the protected epoch installed,
# and one projection acknowledgement is NOT a canonical memory source write.
_SOURCES = {
    "backend/core/conversations.py": (
        "MongoConversationAuthority",
        {
            "create_thread": "fence_conversation_write",
            "rename_thread": "fence_conversation_write",
            "append_message": "fence_conversation_write",
            "bind_chat_execution": "fence_conversation_write",
            "chat_dispatch": "fence_conversation_write",
            "bind_user_request_refs": "fence_conversation_write",
            "bind_user_engine_command": "fence_conversation_write",
            "bind_regeneration_request": "fence_conversation_write",
            "transition_regeneration_dispatch": "fence_conversation_write",
            "set_state": "fence_conversation_write",
            "_recover_prepared": "actor_guard",
            "execute_governed_deletion": "protected_epoch_denial",
        },
    ),
    "skeleton/persistence/memory_repository.py": (
        "MongoMemoryRepository",
        {
            "_ensure_revision_and_projection": "actor_guard",
            "_recover_reservation": "actor_guard",
            "_reserve": "actor_guard",
            "_release_failed_reservation": "actor_guard",
            "_commit_reservation": "actor_guard",
            "commit": "fence_memory_commit",
            "tombstone": "fence_memory_tombstone",
            "mark_projection_published": "projection_ack_only",
        },
    ),
    "skeleton/persistence/mongo_memento_repository.py": (
        "MongoMementoAuthority",
        {
            "publish": "fence_memento_write",
            "retire_thread": "fence_memento_write",
        },
    ),
}

_WRITE_OPERATIONS = frozenset({
    "insert_one", "insert_many", "update_one", "update_many",
    "find_one_and_update", "find_one_and_replace",
    "find_one_and_delete", "replace_one", "delete_one", "delete_many",
    "bulk_write", "drop", "drop_database", "drop_collection",
})
_ACTOR_GUARDS = frozenset({"_require_canonical_writer", "require_actor_writer"})


class WriterCensusError(RuntimeError):
    """A known canonical Mongo writer surface cannot be statically admitted."""


def _file_tree(root: Path, relative: str) -> ast.Module:
    if (not isinstance(root, Path) or not root.is_dir()
            or relative not in _SOURCES):
        raise WriterCensusError("canonical Mongo source root invalid")
    path = root / relative
    try:
        if (path.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(root.resolve())):
            raise WriterCensusError("canonical source path is untrusted")
        data = path.read_bytes()
        if not 0 < len(data) <= _MAX_FILE_BYTES:
            raise WriterCensusError("canonical source byte budget invalid")
        return ast.parse(data.decode("utf-8"), filename=relative)
    except WriterCensusError:
        raise
    except (OSError, UnicodeError, SyntaxError):
        raise WriterCensusError("canonical Mongo source unavailable") from None


def _call(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    return node.func.attr


def _mutation_calls(method: ast.AsyncFunctionDef | ast.FunctionDef) -> list[ast.Call]:
    return [
        n for n in ast.walk(method)
        if isinstance(n, ast.Call)
        and _call(n) in _WRITE_OPERATIONS
    ]


def _has_earlier_actor_guard(
    method: ast.AsyncFunctionDef | ast.FunctionDef, first_write: int,
) -> bool:
    return any(
        isinstance(n, ast.Call) and _call(n) in _ACTOR_GUARDS
        and n.lineno < first_write
        for n in ast.walk(method)
    )


def _protected_denial(method: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    # Canonical source deletion is not yet a globally fenced multi-owner
    # operation; it must refuse BEFORE entering any legacy deletion plan.
    body = [
        n for n in method.body
        if not (isinstance(n, ast.Expr) and
                isinstance(n.value, ast.Constant) and
                isinstance(n.value.value, str))
    ]
    if not body or not isinstance(body[0], ast.If):
        return False
    check = body[0]
    return (
        isinstance(check.test, ast.Compare)
        and len(check.test.ops) == 1
        and isinstance(check.test.ops[0], ast.IsNot)
        and len(check.test.comparators) == 1
        and isinstance(check.test.comparators[0], ast.Constant)
        and check.test.comparators[0].value is None
        and isinstance(check.test.left, ast.Call)
        and isinstance(check.test.left.func, ast.Name)
        and check.test.left.func.id == "getattr"
        and len(check.test.left.args) == 3
        and isinstance(check.test.left.args[0], ast.Name)
        and check.test.left.args[0].id == "self"
        and isinstance(check.test.left.args[1], ast.Constant)
        and check.test.left.args[1].value == "canonical_source_epoch"
        and not check.orelse
        and len(check.body) == 1
        and isinstance(check.body[0], ast.Raise)
    )


def _projection_only(calls: list[ast.Call]) -> bool:
    # The projection publication acknowledgement is an idempotent
    # derivative outbox flag, not a source conversation/memory write.
    # Any write to records/threads or any additional mutator loses exemption.
    if len(calls) != 1:
        return False
    mutator = calls[0].func
    return (
        isinstance(mutator, ast.Attribute)
        and mutator.attr == "update_one"
        and isinstance(mutator.value, ast.Attribute)
        and mutator.value.attr == "projection_outbox"
        and isinstance(mutator.value.value, ast.Name)
        and mutator.value.value.id == "self"
        and len(calls[0].args) == 2
        and isinstance(calls[0].args[0], ast.Dict)
        and isinstance(calls[0].args[1], ast.Dict)
        and {"event_id", "published_at"}.issubset({
            key.value for key in ast.walk(calls[0].args[0])
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        })
    )


def _admit_method(
    method: ast.AsyncFunctionDef | ast.FunctionDef,
    law: str, calls: list[ast.Call],
) -> None:
    if not calls:
        raise WriterCensusError("expected canonical Mongo write surface disappeared")
    decorators = {
        d.id for d in method.decorator_list
        if isinstance(d, ast.Name)
    }
    fenced = law.startswith("fence_")
    if fenced:
        if decorators != {law}:
            raise WriterCensusError("canonical direct Mongo writer fence changed")
    elif law == "actor_guard":
        if decorators or not _has_earlier_actor_guard(
            method, min(c.lineno for c in calls),
        ):
            raise WriterCensusError("internal Mongo mutation bypasses actor writer custody")
    elif law == "protected_epoch_denial":
        if decorators or not _protected_denial(method):
            raise WriterCensusError("legacy governed deletion could bypass protected epoch")
    elif law == "projection_ack_only":
        if decorators or not _projection_only(calls):
            raise WriterCensusError("projection acknowledgement changed canonical source")
    else:
        raise WriterCensusError("unrecognized canonical Mongo writer category")


def census_canonical_mongo_mutators(
    root: Path = ROOT,
) -> dict[str, object]:
    """Static immutable manifest of direct source mutators in 3 known classes."""
    covered = 0
    direct_calls = 0
    classifications = {
        "actor_decorated": 0, "actor_guarded_internal": 0,
        "protected_legacy_deletion_denied": 0,
        "projection_only_ack_unfenced": 0,
    }
    role_counts: dict[str, int] = {}
    for relative, (klass, expected) in _SOURCES.items():
        module = _file_tree(root, relative)
        classes = [
            n for n in module.body
            if isinstance(n, ast.ClassDef) and n.name == klass
        ]
        if len(classes) != 1:
            raise WriterCensusError("canonical source writer class changed")
        methods = {
            method.name: method
            for method in classes[0].body
            if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if len(methods) != sum(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            for n in classes[0].body
        ):
            raise WriterCensusError("duplicate canonical writer method identity")
        actual = {
            name: _mutation_calls(method)
            for name, method in methods.items()
        }
        found = {name for name, calls in actual.items() if calls}
        if found != set(expected):
            raise WriterCensusError("new, missing or unclassified direct Mongo mutator")
        for name, law in expected.items():
            calls = actual[name]
            _admit_method(methods[name], law, calls)
            direct_calls += len(calls)
            covered += 1
            classifications[{
                "actor_guard": "actor_guarded_internal",
                "protected_epoch_denial": "protected_legacy_deletion_denied",
                "projection_ack_only": "projection_only_ack_unfenced",
            }.get(law, "actor_decorated")] += 1
        role_counts[klass] = len(found)
    return {
        "schema": SCHEMA,
        "status": "known_direct_mongo_mutators_source_checked_not_external_registry",
        "class_count": len(_SOURCES),
        "direct_mutation_method_count": covered,
        "direct_mongo_call_count": direct_calls,
        "class_mutation_method_counts": role_counts,
        "classifications": classifications,
        "unclassified_known_source_mutators": 0,
        "source_files_modified": False,
        "database_read_or_written": False,
        "external_writer_registry_exhaustive": False,
        "migration_quiescence_verified": False,
        "protected_jeeves_chat_qualified": False,
        "release_authorized": False,
    }


def main() -> int:
    try:
        print(json.dumps(census_canonical_mongo_mutators(),
                         sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except WriterCensusError:
        print("canonical Mongo source mutator census: DENIED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
