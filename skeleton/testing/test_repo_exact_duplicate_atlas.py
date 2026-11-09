"""Read-only exact-duplicate custody and fail-closed coverage tests."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.repo_intelligence.exact_duplicate_atlas import build_exact_duplicate_atlas
from skeleton.repo_intelligence.git_index import GitIndexSnapshot, TrackedFile


def file(path: str, digest: str, *, mode: str = "100644", size: int = 4) -> TrackedFile:
    return TrackedFile(path=path, mode=mode, index_blob=digest,
                       effective_blob=digest, size=size)


def snapshot(*items: TrackedFile) -> GitIndexSnapshot:
    return GitIndexSnapshot(
        head="a" * 40,
        object_format="sha1",
        source_digest="b" * 64,
        tracked_files=len(items),
        tracked_bytes=sum(i.size for i in items),
        files=tuple(items),
    )


def test_all_tracked_paths_and_every_exact_duplicate_are_retained():
    a, b, c = "1" * 40, "2" * 40, "3" * 40
    data = snapshot(file("skeleton/a.py", a), file("skeleton/ai/a.py", a),
                    file("docs/index.md", b),
                    file("bin/tool", c, mode="100755"))
    atlas = build_exact_duplicate_atlas(data)
    result = atlas.to_dict()
    assert result["head"] == "a" * 40
    assert result["tracked_files"] == result["enumerated_paths"] == 4
    assert result["coverage_complete"] is True
    assert result["automatic_deletion_allowed"] is False
    assert result["duplicate_file_paths"] == 2
    assert len(result["clusters"]) == 1
    assert result["clusters"][0]["paths"] == [
        "skeleton/a.py", "skeleton/ai/a.py",
    ]
    assert result["clusters"][0]["automatic_deletion_allowed"] is False
    assert result["all_paths"] == sorted(result["all_paths"])


def test_mode_distinctions_do_not_authorize_false_duplicates():
    digest = "d" * 40
    data = snapshot(file("bin/tool", digest, mode="100755"),
                    file("src/tool", digest, mode="100644"))
    result = build_exact_duplicate_atlas(data)
    assert result.duplicate_file_paths == 0


@pytest.mark.parametrize("bad", [
    lambda s: replace(s, head=None),
    lambda s: replace(s, object_format="md5"),
    lambda s: replace(s, tracked_files=99),
    lambda s: replace(s, tracked_bytes=0),
    lambda s: replace(s, files=(s.files[0], s.files[0])),
    lambda s: replace(s, files=(replace(s.files[0], working_tree=True),)),
    lambda s: replace(s, files=(replace(s.files[0], deleted=True),)),
    lambda s: replace(s, files=(replace(s.files[0], effective_blob="f" * 40),)),
])
def test_partial_or_mutated_snapshots_fail_instead_of_truncating(bad):
    data = snapshot(file("src/safe.py", "c" * 40))
    with pytest.raises(ValueError):
        build_exact_duplicate_atlas(bad(data))


def test_empty_tracked_snapshot_has_explicit_zero_coverage():
    atlas = build_exact_duplicate_atlas(snapshot())
    assert atlas.tracked_files == 0
    assert atlas.all_paths == ()
    assert atlas.clusters == ()
