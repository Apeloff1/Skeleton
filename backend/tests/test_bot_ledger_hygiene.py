from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
IDLE = REPO_ROOT / ".github" / "workflows" / "idle-studio.yml"
NIGHT = REPO_ROOT / ".github" / "workflows" / "autonomous-studio.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_studio_machine_records_search_all_issue_states() -> None:
    idle = _text(IDLE)
    night = _text(NIGHT)

    for text in (idle, night):
        assert '--state all --search "$worker_title in:title"' in text
        assert '--state all --search "$title in:title"' in text
        assert '-f state=closed' in text

    assert "[Shift Supervisor] Idle Worker Status" in idle
    assert "bot: idle studio ledger" in idle
    assert "[Shift Supervisor] Night Worker Status" in night
    assert "bot: autonomous studio ledger" in night


def test_new_studio_machine_records_are_resolved_before_close() -> None:
    idle = _text(IDLE)
    night = _text(NIGHT)

    assert 'worker_number="${worker_url##*/}"' in idle
    assert 'worker_number="${worker_url##*/}"' in night
    assert "valid worker-status issue number" in idle
    assert "valid worker-status issue number" in night
    assert "valid ledger issue number" in idle
    assert "valid ledger issue number" in night


def test_open_repository_snapshot_stays_open_only() -> None:
    idle = _text(IDLE)
    night = _text(NIGHT)

    # Planning snapshots intentionally exclude the closed machine ledgers.
    assert 'issues?state=open&sort=updated&direction=desc' in idle
    assert 'gh issue list --repo "$REPO" --state open --limit 100 --json number,title,body,updatedAt,labels,url' in night
