"""git_operations must not create /app (or any dir) at import; workspace resolves on first use."""
import os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_import_creates_no_workspace_and_first_use_does(tmp_path):
    target = tmp_path / "gitws"
    code = (
        "import os, routes.git_operations as g\n"
        f"assert not os.path.exists({str(target)!r}), 'created at import'\n"
        "assert g._workspace_base is None\n"
        "p = g.workspace_base()\n"
        f"assert os.path.isdir({str(target)!r}) and p == g.workspace_base()\n"
        "print('ok')\n"
    )
    env = dict(os.environ, GIT_WORKSPACE_BASE=str(target), PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH=f"{ROOT}{os.pathsep}{ROOT / 'backend'}")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT / "backend", env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "ok" in r.stdout
