import json
import pytest
from scripts.studio_work_operator import main

def _args(root,command,*additional):
    return ["--root",str(root),
            "--project","studio_arena_fighting_glacial_fjord",
            command,*additional]

def test_private_cli_claim_submit_review_resume(tmp_path,monkeypatch,capsys):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    input_file=tmp_path/"design.txt"
    input_file.write_bytes(b"operator-reviewed original design")
    monkeypatch.setenv("SKELETON_STUDIO_WORK_TOKEN","long-private-operator-token")
    assert main(_args(root,"claim","--task","source-canon","--worker","writer"))==0
    assert main(_args(root,"submit","--task","source-canon","--worker","writer",
                      "--artifact",str(input_file)))==0
    assert main(_args(root,"review","--task","source-canon","--reviewer","inspector",
                      "--accept"))==0
    assert main(_args(root,"status"))==0
    state=json.loads(capsys.readouterr().out.splitlines()[-1])
    assert state["recovery_safe_for_review"]
    assert state["release_certified"] is False

def test_claim_rejects_missing_private_token(tmp_path,monkeypatch):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    monkeypatch.delenv("SKELETON_STUDIO_WORK_TOKEN",raising=False)
    with pytest.raises(SystemExit) as result:
        main(_args(root,"claim","--task","source-canon","--worker","writer"))
    assert result.value.code==2
