from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "configure_repository_hygiene.sh"


def test_repository_hygiene_bootstrap_defaults_to_verification() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'mode="${1:---verify}"' in text
    assert '.permissions.admin // false' in text
    assert "X-GitHub-Api-Version: 2022-11-28" in text


def test_repository_hygiene_owner_policy_enables_branch_maintenance() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    for desired in (
        "allow_update_branch=true",
        "delete_branch_on_merge=true",
        "allow_auto_merge=true",
        "web_commit_signoff_required=true",
    ):
        assert desired in text


def test_repository_hygiene_apply_is_explicit() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "--dry-run" in text
    assert "--apply" in text
    assert 'if [[ "$mode" == "--verify" ]]' in text
    assert 'if [[ "$mode" == "--dry-run" ]]' in text
