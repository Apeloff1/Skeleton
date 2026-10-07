from __future__ import annotations

import json
from pathlib import Path

from scripts.check_content_identity_schema import (
    CONFLICT_DOMAIN,
    DIGEST_ALGORITHMS,
    DOCUMENT_FIELDS,
    KIND_DIGEST_ALGORITHM,
    KIND_EXECUTABLE,
    KINDS,
    SCHEMA_VERSION,
    TASK_ID,
    canonical_repo_path,
    main,
    symlink_digest,
    validate_content_identity,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "check_content_identity_schema.py"

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SAMPLE_SHA256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
SAMPLE_GIT_SHA1 = "0123456789abcdef0123456789abcdef01234567"

S021_CLASSES = (
    "archive",
    "vendor",
    "generated",
    "fixture",
    "binary",
    "canonical",
    "first-party",
)
S021_CLASSIFICATION_FIELDS = (
    "source_class",
    "inventory_class",
    "generated",
    "vendor",
    "archive",
)


def _file(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "path": "scripts/check_content_identity_schema.py",
        "kind": "file",
        "executable": False,
        "digest_algorithm": "sha256",
        "digest": SAMPLE_SHA256,
        "target": None,
    }
    payload.update(overrides)
    return payload


def _executable(**overrides):
    payload = _file(
        path="scripts/run.sh",
        kind="executable",
        executable=True,
    )
    payload.update(overrides)
    return payload


def _symlink(target: str = "docs/README.md", **overrides):
    payload = _file(
        path="docs/latest.md",
        kind="symlink",
        executable=False,
        digest=symlink_digest(target),
        target=target,
    )
    payload.update(overrides)
    return payload


def _gitlink(**overrides):
    payload = _file(
        path="vendor/godot-cpp",
        kind="gitlink",
        executable=False,
        digest_algorithm="git-sha1",
        digest=SAMPLE_GIT_SHA1,
        target=None,
    )
    payload.update(overrides)
    return payload


def test_schema_identity_is_stable() -> None:
    assert TASK_ID == "reserve-S022-content-identity"
    assert CONFLICT_DOMAIN == "repo.spec.content_identity"
    assert SCHEMA_VERSION == 1
    assert KINDS == ("file", "executable", "symlink", "gitlink")
    assert DIGEST_ALGORITHMS == ("sha256", "git-sha1")
    assert DOCUMENT_FIELDS == {
        "schema_version",
        "path",
        "kind",
        "executable",
        "digest_algorithm",
        "digest",
        "target",
    }
    assert KIND_DIGEST_ALGORITHM == {
        "file": "sha256",
        "executable": "sha256",
        "symlink": "sha256",
        "gitlink": "git-sha1",
    }
    assert KIND_EXECUTABLE == {
        "file": False,
        "executable": True,
        "symlink": False,
        "gitlink": False,
    }
    errors = validate_content_identity(["bad"])
    assert errors and errors[0].startswith("content-identity ")


def test_schema_is_identity_not_source_root_classification() -> None:
    for field in S021_CLASSIFICATION_FIELDS:
        assert field not in DOCUMENT_FIELDS
    for kind in S021_CLASSES:
        assert kind not in KINDS
    source = CHECKER.read_text(encoding="utf-8")
    assert "check_source_path_inventory" in source
    assert "does not classify generated vs vendor" in source
    for token in (
        "ARCHIVE_PREFIXES",
        "VENDOR_PARTS",
        "GENERATED_PREFIXES",
        "classify_path",
        "first-party",
    ):
        assert token not in source
    assert CHECKER.name == "check_content_identity_schema.py"
    assert (REPO_ROOT / "tests" / "test_content_identity_schema.py").is_file()


def test_valid_file_and_executable_have_no_violations() -> None:
    assert validate_content_identity(_file()) == []
    assert validate_content_identity(_file(digest=EMPTY_SHA256, path="README.md")) == []
    assert validate_content_identity(_executable()) == []


def test_valid_symlink_and_gitlink_have_no_violations() -> None:
    assert validate_content_identity(_symlink()) == []
    assert validate_content_identity(_symlink(target="docs/guide.md")) == []
    assert validate_content_identity(_symlink(target="../outside")) == []
    assert validate_content_identity(_gitlink()) == []
    assert validate_content_identity(_gitlink(digest="a" * 40)) == []


def test_all_closed_kinds_are_accepted() -> None:
    documents = {
        "file": _file(),
        "executable": _executable(),
        "symlink": _symlink(),
        "gitlink": _gitlink(),
    }
    assert set(documents) == set(KINDS)
    for kind, document in documents.items():
        assert document["kind"] == kind
        assert validate_content_identity(document) == []


def test_unknown_kind_fails_closed() -> None:
    errors = validate_content_identity(_file(kind="generated"))
    assert any("content-identity unknown kind" in item for item in errors)
    assert any("generated" in item for item in errors)
    vendor = validate_content_identity(_file(kind="vendor"))
    assert any("content-identity unknown kind" in item for item in vendor)
    blob = validate_content_identity(_file(kind="blob"))
    assert any("content-identity unknown kind" in item for item in blob)


def test_missing_digest_fails_closed() -> None:
    document = _file()
    del document["digest"]
    errors = validate_content_identity(document)
    assert any("content-identity missing_value digest" in item for item in errors)
    assert any("content-identity missing_value field" in item for item in errors)
    assert any("digest" in item for item in errors)
    empty = validate_content_identity(_file(digest=""))
    assert any("content-identity missing_value digest" in item for item in empty)
    null = validate_content_identity(_file(digest=None))
    assert any("content-identity missing_value digest" in item for item in null)


def test_unknown_fields_fail_closed() -> None:
    errors = validate_content_identity(_file(vendor=True, generated=False, extras=[]))
    assert any("content-identity unknown field" in item for item in errors)
    assert any("vendor" in item for item in errors)
    assert any("generated" in item for item in errors)
    assert any("extras" in item for item in errors)


def test_source_classification_fields_fail_closed() -> None:
    errors = validate_content_identity(
        _file(source_class="canonical", inventory_class="first-party", archive=True)
    )
    assert any("content-identity unknown field" in item for item in errors)
    for field in ("source_class", "inventory_class", "archive"):
        assert any(field in item for item in errors)


def test_non_canonical_paths_fail_closed() -> None:
    for path in (
        "",
        "/etc/passwd",
        "../secret.py",
        "skeleton//kernel.py",
        "skeleton\\kernel.py",
        "skeleton/./kernel.py",
        "skeleton/../kernel.py",
        "scripts/",
        "foo\x00bar",
        None,
        12,
    ):
        assert canonical_repo_path(path) is None
        errors = validate_content_identity(_file(path=path))
        assert any("content-identity unknown path" in item for item in errors), path


def test_canonical_paths_are_accepted() -> None:
    for path in (
        "README.md",
        "scripts/check_content_identity_schema.py",
        ".github/workflows/ci.yml",
        "vendor/godot-cpp",
        "docs/latest.md",
    ):
        assert canonical_repo_path(path) == path
        kind_doc = {
            "README.md": _file(path=path),
            "scripts/check_content_identity_schema.py": _file(path=path),
            ".github/workflows/ci.yml": _file(path=path),
            "vendor/godot-cpp": _gitlink(path=path),
            "docs/latest.md": _symlink(path=path) if False else _file(path=path),
        }[path]
        assert validate_content_identity(kind_doc) == []


def test_kind_executable_mismatch_fails_closed() -> None:
    file_exec = validate_content_identity(_file(executable=True))
    assert any("content-identity unknown executable" in item for item in file_exec)
    exe_plain = validate_content_identity(_executable(executable=False))
    assert any("content-identity unknown executable" in item for item in exe_plain)
    link_exec = validate_content_identity(_symlink(executable=True))
    assert any("content-identity unknown executable" in item for item in link_exec)
    git_exec = validate_content_identity(_gitlink(executable=True))
    assert any("content-identity unknown executable" in item for item in git_exec)
    not_bool = validate_content_identity(_file(executable=0))
    assert any("content-identity unknown executable" in item for item in not_bool)


def test_kind_target_mismatch_fails_closed() -> None:
    file_target = validate_content_identity(_file(target="payload"))
    assert any("content-identity unknown target" in item for item in file_target)
    exe_target = validate_content_identity(_executable(target="payload"))
    assert any("content-identity unknown target" in item for item in exe_target)
    git_target = validate_content_identity(_gitlink(target="deadbeef"))
    assert any("content-identity unknown target" in item for item in git_target)
    missing_target = _symlink()
    missing_target["target"] = None
    errors = validate_content_identity(missing_target)
    assert any("content-identity unknown target" in item for item in errors)
    blank = validate_content_identity(_symlink(target=""))
    assert any("content-identity unknown target" in item for item in blank)
    backslash = validate_content_identity(_symlink(target="docs\\README.md"))
    assert any("content-identity unknown target" in item for item in backslash)


def test_symlink_digest_must_match_target_payload() -> None:
    errors = validate_content_identity(_symlink(digest=SAMPLE_SHA256, target="docs/README.md"))
    assert any("content-identity unknown digest" in item for item in errors)
    assert any("symlink digest" in item for item in errors)
    assert validate_content_identity(_symlink(target="docs/README.md")) == []


def test_unknown_and_mismatched_digest_algorithms_fail_closed() -> None:
    unknown = validate_content_identity(_file(digest_algorithm="md5"))
    assert any("content-identity unknown digest_algorithm" in item for item in unknown)
    file_git = validate_content_identity(_file(digest_algorithm="git-sha1", digest=SAMPLE_GIT_SHA1))
    assert any("content-identity unknown digest_algorithm" in item for item in file_git)
    git_sha = validate_content_identity(_gitlink(digest_algorithm="sha256", digest=SAMPLE_SHA256))
    assert any("content-identity unknown digest_algorithm" in item for item in git_sha)


def test_malformed_digests_fail_closed() -> None:
    upper = validate_content_identity(_file(digest=SAMPLE_SHA256.upper()))
    assert any("content-identity unknown digest" in item for item in upper)
    short = validate_content_identity(_file(digest="abc"))
    assert any("content-identity unknown digest" in item for item in short)
    git_short = validate_content_identity(_gitlink(digest="abc"))
    assert any("content-identity unknown digest" in item for item in git_short)
    git_upper = validate_content_identity(_gitlink(digest=SAMPLE_GIT_SHA1.upper()))
    assert any("content-identity unknown digest" in item for item in git_upper)
    not_str = validate_content_identity(_file(digest=12))
    assert any("content-identity unknown digest" in item for item in not_str)


def test_wrong_schema_version_and_missing_fields_fail_closed() -> None:
    version = validate_content_identity(_file(schema_version=2))
    assert any("content-identity unknown schema_version" in item for item in version)
    bool_version = validate_content_identity(_file(schema_version=True))
    assert any("content-identity unknown schema_version" in item for item in bool_version)
    document = _file()
    del document["path"]
    del document["kind"]
    errors = validate_content_identity(document)
    assert any("content-identity missing_value field" in item for item in errors)
    assert any("path" in item for item in errors)
    assert any("kind" in item for item in errors)


def test_non_object_root_fails_closed() -> None:
    errors = validate_content_identity(["not", "an", "object"])
    assert errors == [
        "content-identity unknown root_type: content identity document must be an object"
    ]


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "content-identity.json"
    path.write_text(json.dumps(_file()), encoding="utf-8")
    assert main([str(path)]) == 0
    assert "Content-identity schema v1 accepted" in capsys.readouterr().out


def test_cli_rejects_invalid_document(tmp_path: Path, capsys) -> None:
    path = tmp_path / "content-identity.json"
    path.write_text(json.dumps(_file(kind="blob", extra=True, digest="")), encoding="utf-8")
    assert main([str(path)]) == 1
    stderr = capsys.readouterr().err
    assert "Content-identity schema validation failed:" in stderr
    assert "content-identity unknown kind" in stderr
    assert "content-identity unknown field" in stderr
    assert "content-identity missing_value digest" in stderr


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "content-identity unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_not_wired_into_quality_gates() -> None:
    quality_gates = (REPO_ROOT / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    assert "check_content_identity_schema.py" not in quality_gates
    assert "test_content_identity_schema.py" not in quality_gates
