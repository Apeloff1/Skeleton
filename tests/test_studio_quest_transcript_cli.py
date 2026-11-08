import json
import pytest
from scripts.studio_quest_transcript_cli import main
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_story_html import story_source

def test_browser_story_transcript_cli_only_accepts_canonical_replay(tmp_path,capsys):
    pid="studio_arena_fighting_glacial_fjord"
    source=story_source(read_blueprint(pid))
    doc={"schema":"skeleton.game_builder.offline_story_choices.v1",
         "project_id":pid,"source_digest":source["source_digest"],
         "choices":[[source["stages"][0]["id"],
                     source["stages"][0]["alternatives"][0]]],
         "external_evidence_verified":False,
         "native_genre_runtime_verified":False,
         "release_certified":False}
    target=tmp_path/"choices.json"
    target.write_text(json.dumps(doc))
    assert main(["--project",pid,"--transcript",str(target)])==0
    report=json.loads(capsys.readouterr().out)
    assert len(report["completed_stages"])==1
    doc["release_certified"]=True
    target.write_text(json.dumps(doc))
    with pytest.raises(SystemExit) as error:
        main(["--project",pid,"--transcript",str(target)])
    assert error.value.code==2
