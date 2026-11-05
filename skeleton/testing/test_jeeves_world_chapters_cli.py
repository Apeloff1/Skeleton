"""End-to-end chapter CLI: typed proposal, reviewed persistence, playable handoff."""
from __future__ import annotations

import json

from skeleton.jeeves.worlds.chapters_cli import run
from skeleton.jeeves.worlds.world_canon import WorldStore, propose


def test_cli_chapters_flow(tmp_path, capsys):
    world = propose(world_id="chapcli", premise="A traveler reaches a crossroads",
                    protagonist="Sol", region="Riverbank", goal="Return safely")
    WorldStore(tmp_path).publish(world, create=True)
    proposal = tmp_path / "chapters-proposal.json"
    proposal.write_text(json.dumps({"prompt": "Two original story chapters",
        "chapters": [
            {"id": "beginning", "title": "Departure", "summary": "The road",
             "acts": [{"id": "start", "title": "First step", "summary": "Choice",
                       "scenes": ["opening"]}]},
            {"id": "ending", "title": "Return", "summary": "The home",
             "acts": [{"id": "finish", "title": "Final step", "summary": "Arrival",
                       "scenes": ["resolution"]}]}
        ]}))
    base = ["--store", str(tmp_path)]
    def cmd(*args):
        status = run(base + list(args))
        return status, json.loads(capsys.readouterr().out)
    status, preview = cmd("propose", "--id", "chapcli", "--file", str(proposal))
    assert status == 0 and preview["review_required"]
    source = tmp_path / "chapters-source.json"
    source.write_text(json.dumps(preview["proposal"]))
    status, published = cmd("publish", "--id", "chapcli", "--file", str(source), "--create")
    assert status == 0
    status, approved = cmd("approve", "--id", "chapcli", "--expected-digest",
                           published["chapters_digest"], "--note", "Reviewed")
    assert status == 0
    status, receipt = cmd("compile", "--id", "chapcli", "--expected-digest",
                          approved["chapters_digest"])
    assert status == 0 and receipt["artifacts"]
    status, verified = cmd("verify", "--id", "chapcli")
    assert status == 0 and verified["artifacts"] == receipt["artifacts"]
