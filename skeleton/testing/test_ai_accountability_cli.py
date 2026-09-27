from __future__ import annotations

import json

from scripts import ai_accountability as cli


def test_accountability_cli_signature_methods_are_identity_bound() -> None:
    assert "manual_attestation" not in cli.SIGNATURE_METHODS
    assert {"github_identity", "git_gpg", "git_ssh", "sigstore", "ci_oidc"} <= cli.SIGNATURE_METHODS


def test_accountability_cli_phase_status_mapping() -> None:
    queue = {"type": "queue_task"}
    catalog = {"type": "catalog_entry"}
    p1 = {"type": "p1_task"}
    volume = {"type": "volume"}
    assert cli.type_status(queue, "start") == "in_progress"
    assert cli.type_status(queue, "implementation") == "evidence_pending"
    assert cli.type_status(queue, "complete") == "done"
    assert cli.type_status(p1, "implementation") == "evidence_pending"
    assert cli.type_status(p1, "verification") == "evidence_pending"
    assert cli.type_status(p1, "complete") == "done"
    assert cli.type_status(catalog, "verification") == "passing"
    assert cli.type_status(catalog, "complete") == "closed"
    assert cli.type_status(catalog, "accepted_risk") == "accepted_risk"
    assert cli.type_status(volume, "implementation") == "implemented"
    assert cli.type_status(volume, "verification") == "verified"


def test_accountability_cli_render_exposes_every_checkbox() -> None:
    ledger = json.loads(cli.LEDGER.read_text(encoding="utf-8"))
    rendered = cli.render(ledger)
    for record in ledger["records"]:
        assert f"`{record['id']}`" in rendered
        assert f"- {record['checkbox_mark']} " in rendered
    assert f"Tracked items: **{ledger['tracked_counts']['total']}**" in rendered
    assert "44 P1 tasks" in rendered
    assert "## Lifecycle" in rendered
    assert "## Audit and correction rule" in rendered
    assert "Do not rewrite prior sign-offs." in rendered
