"""Actual Compose plugin source-contract check, with no daemon mutation.

Render the repository's real YAML and invoke the production model validators
with ephemeral fixture credentials. No image is pulled, built or started.
Only fixed case labels are emitted; rendered environment remains private.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from skeleton.app.assembly import compose_command, load_manifest
from skeleton.app.compose_runtime_identity import model_identity
from skeleton.app.compose_security_contract import model_security
from skeleton.app.compose_wiring import validate_wiring
from skeleton.app.compose_storage_binding import _json_observation, _render_command, _resolved_model
from skeleton.app.runtime_operation import compose_operation_environment


def _fixture_environment():
    # Do not inherit app secrets or environment interpolation variables from
    # the calling shell. Docker config only requires the executable and a
    # small set of host environment settings; it does not contact the daemon.
    env = {key: os.environ[key] for key in
           ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
           if key in os.environ}
    pw = secrets.token_hex(32)
    authority = "admin:" + pw
    env.update(COMPOSE_PROJECT_NAME="skeleton-render-fixture",
               MONGO_INITDB_ROOT_USERNAME="admin", MONGO_INITDB_ROOT_PASSWORD=pw,
               MONGO_URL="mongodb://" + authority + "@mongo:27017/tutolage?authSource=admin",
               SKL_MONGO_URI="mongodb://" + authority + "@mongo:27017/skeleton?authSource=admin")
    for key in ("JWT_SECRET", "GAMEFORGE_JWT_SECRET", "GF_SEAL_SECRET",
                "GF_KEYHOLDER_SEED", "SKELETON_MASTER_SECRET", "SKL_ENGINE_SERVICE_TOKEN"):
        env[key] = secrets.token_hex(32)
    return env


def qualify(root, *, runner=subprocess.run):
    root = Path(root).resolve()
    config = root / ".env"
    identity = None
    cases = (
        ("development","development",False,{}),
        ("production","production",False,{}),
        ("custom_production","production",False,{"BACKEND_PORT":"8401","SKELETON_PORT":"8410",
                                                  "FRONTEND_PORT":"3400","MONGO_PORT":"27117"}),
        ("hot_reload","development",True,{"FRONTEND_PORT":"3400"}),
    )
    passed = []
    try:
        fd=os.open(config,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
        with os.fdopen(fd,"wb") as handle:
            info=os.fstat(handle.fileno())
            identity=(info.st_dev,info.st_ino)
            handle.write(b"# Ephemeral source render fixture; no application credentials stored.\n")
        manifest=load_manifest()
        base=_fixture_environment()
        for label,mode,hot,overrides in cases:
            env=compose_operation_environment({**base,**overrides},manifest.mode_env(mode))
            command=compose_command("up",manifest=manifest,hot=hot,install_env=True)
            model=_json_observation(root,runner,_render_command(command),env,limit=2*1024*1024)
            _resolved_model(model,root=root,hot=hot)
            model_identity(model,values=env,hot=hot)
            model_security(model,root=root,hot=hot)
            validate_wiring(model,root=root,values=env,hot=hot)
            passed.append(label)
        return {"schema":"skeleton.app.compose_source_render_qualification.v1","ok":True,
                "passed_cases":passed,"service_started":False,"physical_device_qualified":False}
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):
        return {"schema":"skeleton.app.compose_source_render_qualification.v1","ok":False,
                "passed_cases":passed,"code":"compose_source_render_unqualified",
                "service_started":False,"physical_device_qualified":False}
    finally:
        if identity is not None:
            try:
                info=config.lstat()
                if stat.S_ISREG(info.st_mode) and (info.st_dev,info.st_ino)==identity:
                    config.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    report=qualify(_ROOT)
    print(json.dumps(report,sort_keys=True))
    raise SystemExit(0 if report["ok"] is True else 1)
