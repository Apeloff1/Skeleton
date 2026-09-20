from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "idle-security-bot.yml"


def test_security_digest_uses_supported_issue_creation_contract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "gh issue create" not in text
    assert 'gh api --method POST "repos/${REPO}/issues"' in text
    assert "--jq '.number'" in text
    assert '[[ ! "$issue_number" =~ ^[0-9]+$ ]]' in text


def test_security_digest_resolves_exact_issue_from_paginated_rest_results() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert '"/repos/${REPO}/issues?state=all&per_page=100"' in text
    assert '"/repos/${REPO}/issues?state=open&per_page=100"' not in text
    assert '(has("pull_request") | not)' in text
    assert '(.title == $title)' in text
    assert '(.user.login == "github-actions[bot]")' in text
    assert "gh issue list" not in text
    assert "head -n 1" not in text


def test_security_digest_fails_closed_on_alert_collection_errors() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "apparently empty security backlog" in text
    assert "if ! gh api" not in text
    assert "printf '[]'" not in text
    assert text.count("jq -e") >= 2


def test_security_digest_does_not_hijack_user_created_lookalike_issue() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    selector = text.split("first(", 1)[1].split(") // empty", 1)[0]
    assert '.title == $title' in selector
    assert '.user.login == "github-actions[bot]"' in selector


def test_security_digest_flattens_paginated_alert_pages() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.count("gh api --paginate --slurp") == 3
    assert "code-scanning/alerts?state=open&per_page=100" in text
    assert "dependabot/alerts?state=open&per_page=100" in text
    assert text.count('if type == "array" then .[] else empty end') == 3


def test_security_digest_remains_closed_after_refresh() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'repos/${REPO}/issues/${issue_number}' in text
    assert "-f state=closed" in text


def test_security_digest_runs_hourly_and_caps_each_remediation_batch_at_50() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "- cron: '11 * * * *'" in text
    assert "BATCH_SIZE: '50'" in text
    assert '| .[:$limit]' in text
    assert "Prioritized remediation batch" in text


def test_security_digest_exposes_actionable_locations_and_root_cause_groups() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert ".most_recent_instance.location.path" in text
    assert ".most_recent_instance.location.start_line" in text
    assert ".dependency.manifest_path" in text
    assert 'group: ("code:" + (.rule.id // "unknown-rule"))' in text
    assert 'group: ("dependabot:" + (.dependency.package.name // "unknown-package"))' in text
    assert "group_by(.group)" in text


def test_security_digest_deduplicates_alert_identity_before_batch_cap() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    unique_pos = text.index("unique_by([.kind, .number])")
    sort_pos = text.index("sort_by([.priority, -(.number // 0)])")
    cap_pos = text.index("| .[:$limit]")
    assert unique_pos < sort_pos < cap_pos
    assert "invalid alert number" in text


def test_security_digest_updates_one_issue_body_without_hourly_comment_growth() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'gh issue edit "$issue_number" --repo "$REPO"' in text
    assert '--body-file "$body_file" --add-label' in text
    assert "gh issue comment" not in text


def test_security_digest_checks_batch_bound_after_collection() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "expected_batch=$(( total < BATCH_SIZE ? total : BATCH_SIZE ))" in text
    assert "batch_count > BATCH_SIZE" in text
    assert "Nominal target before de-duplication" in text


def test_security_digest_prioritizes_without_dismissing_findings() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'if $severity == "critical" then 0' in text
    assert 'elif $severity == "high" or $severity == "error" then 1' in text
    assert "sort_by([.priority, -(.number // 0)])" in text
    assert "code-scanning/alerts/" not in text
    assert "dependabot/alerts/" not in text
    assert "dismiss" in text.lower()


def test_security_digest_bounds_untrusted_display_fields() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "def clip($value; $max):" in text
    assert 'rule_id: clip((.rule.id // "unknown-rule"); 100)' in text
    assert 'summary: clip((.rule.description // .rule.id // "unknown rule"); 180)' in text
    assert 'path: clip((.most_recent_instance.location.path // "unknown"); 260)' in text
    assert 'package: clip((.dependency.package.name // "unknown-package"); 100)' in text
    assert 'url: clip((.html_url // ""); 220)' in text


def test_security_digest_has_bounded_issue_body() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "BODY_MAX_BYTES: '60000'" in text
    assert 'body_bytes=$(wc -c < "$body_file" | tr -d \' \')' in text
    assert "body_bytes > BODY_MAX_BYTES" in text
    assert "Security digest body exceeds bounded issue payload." in text
