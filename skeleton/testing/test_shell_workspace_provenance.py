from pathlib import Path
import pytest

from skeleton.shells.provenance import canonical_json, command_fingerprint, digest_arguments, digest_environment_keys, digest_path
from skeleton.shells.workspace import WorkspacePolicy


def test_workspace_accepts_nested_directory(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    policy = WorkspacePolicy((tmp_path,))
    assert policy.resolve("python", nested) == nested.resolve()


def test_workspace_denies_outside_root(tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    with pytest.raises(Exception):
        WorkspacePolicy((allowed,)).resolve("python", outside)


def test_workspace_denied_subroot_overrides_allowed_root(tmp_path):
    denied = tmp_path / "denied"
    denied.mkdir()
    policy = WorkspacePolicy((tmp_path,), deny_roots=(denied,))
    with pytest.raises(Exception):
        policy.resolve("python", denied)


def test_workspace_depth_limit(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    policy = WorkspacePolicy((tmp_path,), max_depth=1)
    with pytest.raises(Exception):
        policy.resolve("python", nested)


def test_workspace_narrow_rejects_widening(tmp_path):
    child = tmp_path / "child"
    child.mkdir()
    outside = tmp_path.parent
    policy = WorkspacePolicy((tmp_path,))
    narrowed = policy.narrow((child,))
    assert narrowed.roots == (child.resolve(),)
    with pytest.raises(ValueError):
        policy.narrow((outside,))


def test_canonical_json_is_order_stable():
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})


def test_argument_digest_is_order_sensitive():
    assert digest_arguments(["a", "b"]) != digest_arguments(["b", "a"])


def test_environment_key_digest_is_order_insensitive_and_value_free():
    assert digest_environment_keys(["B", "A"]) == digest_environment_keys(["A", "B"])


def test_command_fingerprint_changes_with_args_and_cwd(tmp_path):
    one = command_fingerprint("python", ["a"], cwd=tmp_path, env_keys=["LANG"])
    two = command_fingerprint("python", ["b"], cwd=tmp_path, env_keys=["LANG"])
    assert one != two


def test_path_digest_does_not_expose_path(tmp_path):
    digest = digest_path(tmp_path)
    assert str(tmp_path) not in digest
    assert len(digest) == 64
