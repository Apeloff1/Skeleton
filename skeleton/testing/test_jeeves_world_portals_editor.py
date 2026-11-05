"""Multi-world portal offline editor, prompt tool and source leases."""
from __future__ import annotations

import os
import pytest

from skeleton.jeeves.worlds.portals import PortalStore, approve_network, propose_network
from skeleton.jeeves.worlds.portals_editor import render_editor
from skeleton.jeeves.worlds.tools import invoke_world_tool
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def sources():
    first = propose(
        world_id="island", premise="An original island.",
        protagonist="Ena", region="Island", goal="Cross the inlet.",
    )
    second = propose(
        world_id="mountain", premise="An original mountain.",
        protagonist="Ena", region="Mountain", goal="Find the ridge.",
    )
    return {"island": first, "mountain": second}


def draft():
    return propose_network(
        sources(), network_id="journey", prompt="Original two-world journey.",
        root_world="island", from_ending="resolution", to_world="mountain",
    )


def test_editor_csp_escapes_source_and_exports_unapproved_json():
    spec = draft()
    spec["portals"][0]["label"] = "</script><img src=x onerror=alert(1)>"
    output = render_editor(spec, sources()).decode()
    assert "Content-Security-Policy" in output
    assert "script-src 'sha256-" in output
    assert "connect-src 'none'" in output
    assert "Original multi-world portal editor" in output
    assert "Export JSON" in output
    assert "<img src=x" not in output
    assert "\\u003c/script>" in output


def test_approved_portal_network_not_editable_in_browser():
    source = sources()
    approved = approve_network(draft(), source, "Reviewed both worlds.")
    with pytest.raises(CanonError, match="portals_editor_requires_draft"):
        render_editor(approved, source)


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_editor_and_jeeves_proposal_with_canonical_leases(tmp_path):
    source = sources()
    worlds = WorldStore(tmp_path)
    for world in source.values():
        worlds.publish(world, create=True)
    tool = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.portals_propose_preview", "world_id": "island",
        "args": {
            "network_id": "journey", "prompt": "Original portal voyage.",
            "from_ending": "resolution", "to_world": "mountain",
        },
    })
    assert tool["persisted"] is False
    assert tool["review_required"] is True
    assert tool["result"]["approved"] is False
    assert not (tmp_path / "journey.portals.json").exists()
    store = PortalStore(tmp_path)
    spec = draft()
    lease = store.save("journey", spec, create=True)
    editor = store.editor("journey", expected_network_digest=lease)
    assert editor["network_digest"] == lease
    assert (tmp_path / editor["html_file"]).is_file()
    with pytest.raises(CanonError, match="portals_stale_edit"):
        store.editor("journey", expected_network_digest="0" * 64)
    (tmp_path / "island.lock").write_text("busy")
    with pytest.raises(CanonError, match="lease_busy"):
        store.editor("journey", expected_network_digest=lease)
