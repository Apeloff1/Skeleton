"""Git provider boundaries are hard; repository growth and UI truncation are advisory."""
from scripts.studio_git_admission import (
    Change, RemoteCapacity, evaluate, MAX_CHANGED_FILES, MAX_CHANGED_LINES,
    MAX_RAW_DIFF_BYTES, MAX_SINGLE_BLOB_BYTES, MAX_DIRECTORY_WIDTH,
)

def cap(**kw):
    d=dict(repo_size_kib=253454,open_studio_drafts=10,remote_branches=200,pushes_last_minute=1)
    d.update(kw)
    return RemoteCapacity(**d)

def ev(*changes, capacity=None, diff=1024, width=80):
    return evaluate(tuple(changes),capacity or cap(),raw_diff_bytes=diff,largest_directory_width=width)

def test_source_patch_still_requires_independent_qualification():
    result=ev(Change("skeleton/ai/game_builder/real_module.py",24,3,2048))
    assert result["admitted"] and not result["release_certified"]

def test_320_file_eight_thousand_line_slice_is_admitted_with_review_warning():
    changes=tuple(Change(f"catalog/project_{i}/source.json",25,0,100) for i in range(320))
    result=ev(*changes,diff=300_000)
    assert result["admitted"] and result["measured"]["changed_lines"]==8000
    assert "pr_diff_file_visibility" in result["advisories"]
    assert result["full_review_required"] and not result["release_certified"]

def test_provider_object_and_complete_audit_bounds_are_not_waived():
    changes=tuple(Change(f"catalog/project_{i}/source.json",16,0,100) for i in range(MAX_CHANGED_FILES+1))
    assert "changed_file_count" in ev(*changes)["violations"]
    assert "changed_lines" in ev(Change("x/file.py",MAX_CHANGED_LINES+1,0,16))["violations"]
    assert "raw_diff_bytes" in ev(Change("x/file.py",1,0,16),diff=MAX_RAW_DIFF_BYTES+1)["violations"]
    assert "directory_width" in ev(Change("x/file.py",1,0,16),width=MAX_DIRECTORY_WIDTH+1)["violations"]

def test_repository_scale_is_an_advisory_while_push_rate_remains_guarded():
    change=Change("safe/source.py",1,0,24)
    result=ev(change,capacity=cap(repo_size_kib=6*1024*1024,open_studio_drafts=120,remote_branches=7000))
    assert result["admitted"]
    assert {"repository_size_review","studio_draft_backlog_review","branch_population_review"}<=set(result["advisories"])
    assert "push_rate" in ev(change,capacity=cap(pushes_last_minute=5))["violations"]

def test_unsafe_paths_symlinks_binary_and_oversize_are_rejected():
    assert "non_source_blob" in ev(Change("a/b.py",0,0,10,mode="120000"))["violations"]
    assert "non_source_blob" in ev(Change("a/b.bin",0,0,4,binary=True))["violations"]
    assert "single_blob_size" in ev(Change("a/c.py",1,0,MAX_SINGLE_BLOB_BYTES+1))["violations"]
    assert "unsafe_or_duplicate_path" in ev(Change("../escape.py",1,0,10))["violations"]
    assert "unsafe_or_duplicate_path" in ev(Change("a/a.py",1,0,1),Change("a/a.py",1,0,1))["violations"]
    assert ev(Change(".github/workflows/ci.yml",1,0,100))["admitted"]
    assert "unsafe_or_duplicate_path" in ev(Change(".git/hooks/post-commit",1,0,10))["violations"]
    assert "unsafe_or_duplicate_path" in ev(Change("safe/./file.py",1,0,10))["violations"]

def test_unmeasured_capacity_fails_closed():
    try:
        ev(Change("ok/a.py",1,0,1),capacity=RemoteCapacity(-1,0,0,0))
    except ValueError:
        pass
    else:
        raise AssertionError("unknown remote capacity accepted")
