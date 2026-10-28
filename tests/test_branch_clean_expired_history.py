"""Static fail-closed contracts for stale squash-merged branch cleanup.

These checks are deliberately dependency-free except for pytest and bash.
They verify the actual shell embedded in the Actions workflow, not a detached
Python reimplementation of its policy.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/branch-clean.yml"


def cleanup_script() -> str:
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    marker = "      - name: Classify and prune redundant refs"
    idx = lines.index(marker)
    while idx < len(lines) and lines[idx] != "        run: |":
        idx += 1
    assert idx < len(lines), "cleanup script missing"
    body = []
    for line in lines[idx + 1:]:
        if line and not line.startswith("          "):
            break
        body.append(line[10:] if line else "")
    assert len(body) > 100, "cleanup script was unexpectedly truncated"
    return "\n".join(body) + "\n"


def test_cleanup_bash_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n"], input=cleanup_script(), text=True,
        capture_output=True, check=False, timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_expired_create_events_need_exact_mature_main_merge_evidence() -> None:
    source = cleanup_script()
    assert "merged_cutoff=$(date -u -d" in source
    assert re.search(r'--jq .*\.merged_at <= .*merged_cutoff', source)
    assert r'.base.ref == \"main\"' in source
    assert "merged_key=\"\u0024{branch}:\u0024{tip}\"" in source
    assert 'if [[ -z "\u0024{branch_creation_epochs[\u0024branch]+x}" ]]; then' in source
    assert 'if [[ -z "\u0024{merged_pr_head_tips[\u0024merged_key]+x}" ]]; then' in source
    assert "creation-age-unknown" in source
    assert "merged_without_create_count" in source


def test_active_stack_and_race_guards_remain_fail_closed() -> None:
    source = cleanup_script()
    for required in (
        "open_pr_heads", "open_pr_bases", "delayed-create-event",
        "recent-create-event", "recent-tip", "open-pr-head-late",
        "open-pr-base-late", "git merge-base --is-ancestor",
        "git push --quiet --atomic", "--force-with-lease",
        "live",
    ):
        assert required in source, required
    assert 'if [[ "\u0024tip" == "\u0024classified_main" ]]; then' in source
    assert source.index("open-pr-base-late") < source.index("git push --quiet --atomic")
    # Fast-forwarding main preserves the classified ancestor; a rewrite or
    # divergence defers pruning after classification and immediately before push.
    assert 'if git merge-base --is-ancestor "$classified_main" "$current_main"; then' in source
    assert 'if ! git merge-base --is-ancestor "$classified_main" "$live_main"; then' in source
