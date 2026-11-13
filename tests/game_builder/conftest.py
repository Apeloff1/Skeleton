import pytest

from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.project_bundle.project_save import ProjectSaver
from skeleton.kernel.game_save_plane import GameSavePlane


def edit(ws, project, path, text):
    cur = {f.path: f.sha256 for f in ws.files("current", project)}
    import hashlib
    before = cur.get(path, hashlib.sha256(b"").hexdigest())
    p = ws.propose(project, path, text, expected_sha256=before,
                   reason="test edit for bundle coverage", authorized=True)
    ws.commit(p["proposal_id"], human_approved=True, authorized=True)


@pytest.fixture
def ws(tmp_path):
    w = GameWorkspace.create(tmp_path / "studio", authorized=True)
    w.create_project("hero", "platformer", authorized=True)
    return w


@pytest.fixture
def saver():
    return ProjectSaver(GameSavePlane())
