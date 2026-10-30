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

def test_cli_walkable_source_game_is_explicit_opt_in(tmp_path,capsys):
    root=tmp_path/"root";root.mkdir(mode=0o700)
    out=tmp_path/"out";out.mkdir(mode=0o700)
    assert main(["--private-root",str(root),"--output-root",str(out),
                 "--project","studio_aerial_traversal_amber_highlands",
                 "--walkable-story","--working-set-bytes","1024",
                 "--estimated-output-bytes","1024"])==0
    result=json.loads(capsys.readouterr().out)
    assert result["all_projects_completed"]
    assert (out/"studio_aerial_traversal_amber_highlands"/"walkable.html").is_file()

def test_explicit_parallel_cli_makes_source_verified_2d_games(tmp_path,capsys):
    root=tmp_path/"private";root.mkdir(mode=0o700)
    out=tmp_path/"output";out.mkdir(mode=0o700)
    assert main(["--private-root",str(root),"--output-root",str(out),
                 "--project","studio_arena_fighting_glacial_fjord",
                 "--parallel","--walkable-story",
                 "--working-set-bytes","1024",
                 "--estimated-output-bytes","1024"])==0
    assert (out/"studio_arena_fighting_glacial_fjord"/"walkable.html").is_file()
    assert json.loads(capsys.readouterr().out)["all_projects_completed"]

def test_operator_resume_rechecks_source_and_exact_game_mode(tmp_path,capsys):
    root=tmp_path/"private";root.mkdir(mode=0o700)
    out=tmp_path/"out";out.mkdir(mode=0o700)
    options=["--private-root",str(root),"--output-root",str(out),
             "--project","studio_arena_fighting_glacial_fjord",
             "--walkable-story","--working-set-bytes","1024",
             "--estimated-output-bytes","1024"]
    assert main(options)==0
    capsys.readouterr()
    assert main(options+["--resume"])==0
    result=json.loads(capsys.readouterr().out)
    assert result["recovery"]["reused_verified"]==["studio_arena_fighting_glacial_fjord"]
    assert result["recovery"]["built_now"]==[]
    assert not result["consumer_release_certified"]
