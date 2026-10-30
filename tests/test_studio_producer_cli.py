import json
import pytest
from scripts.studio_producer_cli import main

def test_production_cli_reads_verified_original_source(capsys):
    assert main(["--project","studio_aerial_traversal_amber_highlands",
                 "--scene","arrival","--object","hazard_monitor",
                 "--social-choice","disclose_proof"])==0
    payload=json.loads(capsys.readouterr().out)
    assert payload["production"]["project_id"]=="studio_aerial_traversal_amber_highlands"
    assert payload["scene"]["unlocked"] is True
    assert payload["object_intent"]["object_interaction_performed"] is False
    assert payload["social"]["reputation"]["settlers"]==2
    assert payload["production"]["release_certified"] is False

def test_cli_rejects_invalid_quest_and_unavailable_scene():
    with pytest.raises(SystemExit) as err:
        main(["--project","studio_aerial_traversal_amber_highlands",
              "--quest-actions",'[["repair","cooperative_governance"]]'])
    assert err.value.code==2
    with pytest.raises(SystemExit) as err:
        main(["--project","studio_aerial_traversal_amber_highlands",
              "--scene","nonexistent"])
    assert err.value.code==2
