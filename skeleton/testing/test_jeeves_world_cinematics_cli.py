"""End-user CLI storyboards: propose -> persist -> review -> compile -> verify."""
from __future__ import annotations

import json

from skeleton.jeeves.worlds.cinematics_cli import run
from skeleton.jeeves.worlds.world_canon import WorldStore, propose


def test_cli_full_storyboard_flow(tmp_path, capsys):
    world = propose(world_id="worldone", premise="A courier returns home",
                    protagonist="Ari", region="Silver Wood", goal="Find the road")
    WorldStore(tmp_path).publish(world, create=True)
    file = tmp_path / "proposal.json"
    file.write_text(json.dumps({"prompt": "An original homecoming sequence",
        "sequences": [{"scene": "opening", "beats": [{
            "id": "opening", "cue": "arrival", "caption": "Ari arrives.",
            "duration_ms": 1000}]}]}))
    base = ["--store", str(tmp_path)]
    def cmd(*args):
        status = run(base + list(args))
        output = json.loads(capsys.readouterr().out)
        return status, output
    status, preview = cmd("propose", "--id", "worldone", "--file", str(file))
    assert status == 0 and preview["review_required"]
    authored = tmp_path / "authored.json"
    authored.write_text(json.dumps(preview["proposal"]))
    status, saved = cmd("publish", "--id", "worldone", "--file",
                        str(authored), "--create")
    assert status == 0
    status, blocked = cmd("compile", "--id", "worldone", "--expected-digest",
                          saved["cinematics_digest"])
    assert status == 2 and blocked["error"] == "cinematics_review_required"
    status, approved = cmd("approve", "--id", "worldone", "--expected-digest",
                           saved["cinematics_digest"], "--note", "Original content reviewed")
    assert status == 0
    status, built = cmd("compile", "--id", "worldone", "--expected-digest",
                        approved["cinematics_digest"])
    assert status == 0 and built["artifacts"]
    status, verified = cmd("verify", "--id", "worldone")
    assert status == 0 and verified["artifacts"] == built["artifacts"]
    status, editor = cmd("editor", "--id", "worldone", "--expected-digest",
                         approved["cinematics_digest"])
    assert status == 0 and editor["html_sha256"]
