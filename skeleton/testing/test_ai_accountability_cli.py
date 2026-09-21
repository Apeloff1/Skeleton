from __future__ import annotations

import json

from scripts import ai_accountability as cli


def test_accountability_cli_signature_methods_are_identity_bound() -> None:
    assert "manual_attestation" not in cli.SIGNATURE_METHODS
    assert {"github_identity", "git_gpg", "git_ssh", "sigstore", "ci_oidc"} <= cli.SIGNATURE_METHODS


def test_accountability_cli_phase_status_mapping() -> None:
    queue = {"type": "queue_task"}
    catalog = {"type": "catalog_entry"}
    volume = {"type": "volume"}
    assert cli.type_status(queue, "start") == "in_progress"
    assert cli.type_status(queue, "implementation") == "evidence_pending"
    assert cli.type_status(queue, "complete") == "done"
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
