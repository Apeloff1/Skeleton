import json
import pytest
from scripts.studio_walk_transcript_cli import main
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_walkable import playable_world_source


def test_operator_cli_proves_source_bound_physics_not_external_authenticity(tmp_path,capsys):
    project="studio_arena_fighting_glacial_fjord"
    world=playable_world_source(read_blueprint(project))
    receipt={"schema":"skeleton.game_builder.offline_walk_events.v1",
             "project_id":project,"source_digest":world["source_digest"],
             "events":[["move","right"]],
             "external_evidence_verified":False,
             "native_genre_runtime_verified":False,"release_certified":False}
    path=tmp_path/"walk.json"
    path.write_text(json.dumps(receipt))
    assert main(["--project",project,"--events",str(path)])==0
    data=json.loads(capsys.readouterr().out)
    assert data["accepted_moves"]==1
    assert data["position"]==[2,1]
    path.write_text(json.dumps({**receipt,"events":[["move","left"]]}))
    with pytest.raises(SystemExit) as blocked:
        main(["--project",project,"--events",str(path)])
    assert blocked.value.code==2
