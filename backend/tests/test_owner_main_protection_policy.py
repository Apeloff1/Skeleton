from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "configure_main_protection.sh"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _payload(text: str) -> dict[str, object]:
    match = re.search(r"payload='(\{.*?\})'\n\nif \[\[", text, re.DOTALL)
    assert match is not None
    return json.loads(match.group(1))


def test_owner_main_protection_defaults_to_verification() -> None:
    text = _script()

    assert 'mode="${1:---verify}"' in text
    assert 'required_check="Merge Readiness"' in text
    assert "X-GitHub-Api-Version: 2022-11-28" in text


def test_owner_main_protection_payload_is_fail_closed_for_normal_changes() -> None:
    payload = _payload(_script())

    assert payload["required_status_checks"] == {
        "strict": True,
        "contexts": ["Merge Readiness"],
    }
    assert payload["enforce_admins"] is True
    assert payload["required_pull_request_reviews"] == {
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": False,
        "required_approving_review_count": 0,
        "require_last_push_approval": False,
    }
    assert payload["required_conversation_resolution"] is True
    assert payload["allow_force_pushes"] is False
    assert payload["allow_deletions"] is False
    assert payload["restrictions"] is None


def test_owner_main_protection_validates_repo_and_branch_inputs() -> None:
    text = _script()

    assert "REPO must be a safe owner/name value" in text
    assert "BRANCH contains unsupported characters" in text
    assert '.permissions.admin // false' in text
