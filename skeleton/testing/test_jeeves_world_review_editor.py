"""Offline review editor: source lease, CSP, no script injection, custody."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.jeeves.worlds.evidence import (
    EvidenceStore, propose_evidence,
)
from skeleton.jeeves.worlds.factions import (
    FactionStore, propose_factions,
)
from skeleton.jeeves.worlds.review_editor import ReviewEditorStore
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose,
)


def world():
    return propose(
        world_id="marsh", premise="A courier crosses the marsh.",
        protagonist="Iris", region="Marsh", goal="Deliver the letter.",
    )


def prepare(root):
    data = world()
    WorldStore(root).publish(data, create=True)
    faction = propose_factions(
        data, prompt="Trust is earned", faction_id="couriers",
        name="Couriers", description="A guild", choice_id="pursue_goal",
        delta=10, reason="Delivered the letter.")
    evidence = propose_evidence(
        data, prompt="Find a hidden clue", clue_id="letter",
        title="Sealed letter", detail="The truth is hidden.",
        unlock_choice="pursue_goal")
    return (FactionStore(root).publish("marsh", faction, create=True),
            EvidenceStore(root).publish("marsh", evidence, create=True))


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
@pytest.mark.parametrize("kind", ["factions", "evidence"])
def test_source_to_editor_and_exact_verification(tmp_path, kind):
    root = tmp_path / "private"
    faction_digest, evidence_digest = prepare(root)
    expected = faction_digest if kind == "factions" else evidence_digest
    store = ReviewEditorStore(root)
    receipt = store.render("marsh", kind, expected)
    assert receipt == store.verify("marsh", kind)
    page = (root / ("marsh." + kind + ".editor.html")).read_text()
    assert "Content-Security-Policy" in page
    assert "script-src 'sha256-" in page
    assert "connect-src 'none'" in page
    assert "Original world review" in page
    assert "download" in page
    with pytest.raises(CanonError, match="stale_review_editor"):
        store.render("marsh", kind, "0" * 64)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_html_and_receipt_tamper_rejected(tmp_path):
    root = tmp_path / "private"
    faction_digest, _ = prepare(root)
    store = ReviewEditorStore(root)
    store.render("marsh", "factions", faction_digest)
    (root / "marsh.factions.editor.html").write_text("forged")
    with pytest.raises(CanonError, match="review_editor_html_mismatch"):
        store.verify("marsh", "factions")
    store.render("marsh", "factions", faction_digest)
    (root / "marsh.factions.editor.receipt.json").write_text("{}")
    with pytest.raises(CanonError, match="review_editor_receipt_mismatch"):
        store.verify("marsh", "factions")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_stale_source_and_symlink_artifact_rejected(tmp_path):
    root = tmp_path / "private"
    faction_digest, _ = prepare(root)
    store = ReviewEditorStore(root)
    store.render("marsh", "factions", faction_digest)
    path = root / "marsh.factions.editor.html"
    path.unlink()
    path.symlink_to(root / "marsh.json")
    with pytest.raises(OSError):
        store.verify("marsh", "factions")
    path.unlink()
    changed = world()
    changed["prompt"] = "The courier changed course."
    (root / "marsh.json").write_text(json.dumps(changed))
    with pytest.raises(CanonError, match="faction_world_lease_mismatch"):
        store.verify("marsh", "factions")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_untrusted_original_text_cannot_escape_json_script(tmp_path):
    root = tmp_path / "private"
    data = world()
    data["prompt"] = '</script><script>alert("x")</script>'
    WorldStore(root).publish(data, create=True)
    factions = propose_factions(
        data, prompt='</script><img src=x onerror=alert(1)>',
        faction_id="couriers", name="Couriers", description="A guild",
        choice_id="pursue_goal", delta=1, reason="Earned.")
    source_digest = FactionStore(root).publish("marsh", factions, create=True)
    ReviewEditorStore(root).render("marsh", "factions", source_digest)
    page = (root / "marsh.factions.editor.html").read_text()
    assert "</script><img" not in page
    assert "<img src=x" not in page
    assert "\\u003c/img" in page
