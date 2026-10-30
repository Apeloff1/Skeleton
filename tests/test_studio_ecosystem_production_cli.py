import json
import pytest
from scripts.studio_ecosystem_production_cli import main

def test_opt_in_cli_makes_complete_offline_bundle(tmp_path,capsys):
    private=tmp_path/"private"
    private.mkdir(mode=0o700)
    output=tmp_path/"output"
    output.mkdir(mode=0o700)
    assert main(["--private-root",str(private),"--output-root",str(output),
                 "--project","studio_aerial_traversal_amber_highlands",
                 "--working-set-bytes","1024","--estimated-output-bytes","1024"])==0
    report=json.loads(capsys.readouterr().out)
    assert report["completed_projects"]==1
    assert (output/"studio_aerial_traversal_amber_highlands"/"studio.html").exists()
    assert not report["consumer_release_certified"]

def test_cli_requires_explicit_selection(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["--private-root",str(tmp_path),"--output-root",str(tmp_path)])
    assert exc.value.code==2

def test_cli_explicit_interactive_story_option(tmp_path,capsys):
    root=tmp_path/"private";root.mkdir(mode=0o700)
    output=tmp_path/"exports";output.mkdir(mode=0o700)
    assert main(["--private-root",str(root),"--output-root",str(output),
                 "--project","studio_arena_fighting_glacial_fjord",
                 "--interactive-story","--working-set-bytes","1024",
                 "--estimated-output-bytes","1024"])==0
    assert (output/"studio_arena_fighting_glacial_fjord"/"quest.html").is_file()
    assert json.loads(capsys.readouterr().out)["all_projects_completed"]
