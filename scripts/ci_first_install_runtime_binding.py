"""Ephemeral CI qualification using the shipping storage and runtime gates.

This script is for the existing isolated App Foundation E2E job only.
All credentials come from the job environment. No secret values, Docker
inspect payloads, or keyed model fingerprints are printed or retained.
It never performs teardown or automatically retries an uncertain mutation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

# Script invocation puts scripts/ rather than the checkout on sys.path.
_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(_ROOT))

from skeleton.app.assembly import compose_command, load_manifest
from skeleton.app.compose_storage_binding import observe_binding
from skeleton.app.runtime_operation import compose_operation_environment
from skeleton.app.setup_runtime import runtime_source_fingerprint


def qualify(root, *, environ, runner=subprocess.run, observe=observe_binding):
    if (environ.get("GITHUB_ACTIONS")!="true"
            or environ.get("COMPOSE_PROJECT_NAME")!="skeleton-e2e"):
        return {"ok":False,"code":"isolated_ci_project_required"}
    root=Path(root).resolve()
    config=root/".env"
    # Own a deliberately empty, private env file. The fixed ephemeral
    # credentials are supplied by the existing CI environment. Never
    # overwrite an existing operator config, even for a test job.
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0)
    try:
        fd=os.open(config,flags,0o600)
    except OSError:
        return {"ok":False,"code":"ephemeral_env_creation_denied"}
    with os.fdopen(fd,"wb") as handle:
        info=os.fstat(handle.fileno())
        identity=(info.st_dev,info.st_ino)
        handle.write(b"# Isolated CI; ephemeral values supplied in process environment.\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        manifest=load_manifest()
        captured=compose_operation_environment(environ,manifest.mode_env("production"))
        # The workflow has already built all required images, just as its
        # independent production Nginx test expects. Do not rebuild here.
        command=compose_command("up",manifest=manifest,build=False,install_env=True)
        epoch=runtime_source_fingerprint(root)
        def admit():
            try:
                head=config.lstat()
                return (stat.S_ISREG(head.st_mode) and (head.st_dev,head.st_ino)==identity
                        and runtime_source_fingerprint(root)==epoch)
            except (OSError,ValueError):
                return False
        before=observe(root,command=command,environ=captured,runner=runner,admit=admit)
        if not before.admitted or not admit():
            return {"ok":False,"code":"prestart_binding_unqualified","observation":before.to_dict()}
        # This isolated CI job owns its disposable project. No live operator
        # environment or production credentials are used. Preserve the
        # shipping lifecycle sequence and do not bypass the binding gate.
        # compose_command(build=False) omits --build rather than disallowing
        # implicit builds, so explicitly deny a rebuild in this job.
        args=list(command)
        args.insert(args.index("up")+1,"--no-build")
        done=runner(args,cwd=root,env=captured,check=False,
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    timeout=480)
        if type(getattr(done,"returncode",None)) is not int or done.returncode!=0:
            return {"ok":False,"code":"isolated_start_unqualified"}
        if not admit():
            return {"ok":False,"code":"ephemeral_configuration_changed"}
        post=observe(root,command=command,environ=captured,runner=runner,admit=admit,
                     previous=before,require_started=True)
        return {"ok":post.admitted and admit(),"code":post.code,
                "observation":post.to_dict(),"physical_device_qualified":False,
                "release_qualified":False}
    except (OSError,ValueError,subprocess.SubprocessError):
        return {"ok":False,"code":"isolated_binding_execution_unavailable"}
    finally:
        # Never unlink a replaced private file. The runner owns only the
        # precise inode that it created for this isolated operation.
        try:
            current=config.lstat()
            if stat.S_ISREG(current.st_mode) and (current.st_dev,current.st_ino)==identity:
                config.unlink()
        except OSError:
            pass


if __name__=="__main__":
    result=qualify(_ROOT,environ=os.environ)
    print(json.dumps(result,sort_keys=True))
    raise SystemExit(0 if result["ok"] is True else 1)
