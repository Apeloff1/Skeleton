"""Shared, non-destructive shutdown qualification for the local application.

Stop is deliberately independent of healthy HTTP endpoints, runtime image
identity and current storage migration holds. It must still establish
which Compose project it will affect, and confirm the same containers
and volumes remain present afterward. Never remove containers or volumes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from skeleton.app.compose_storage_binding import _json_observation, _PROJECT
from skeleton.app.storage_custody import CONTAINER_ROLES, StorageCustodyDenied, _names
from skeleton.app.runtime_mutation import run_mutation
from skeleton.app.runtime_operation import RuntimeOperationDenied, compose_operation_environment
from skeleton.app.setup_runtime import runtime_source_fingerprint

_CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
_DAEMON_ID = re.compile(r"[0-9A-Za-z:_-]{1,256}\Z")
_MAX_MODEL = 2 * 1024 * 1024
_MAX_STATE = 32 * 1024
_FIXED = {"tutolage-" + role:role for role in CONTAINER_ROLES}
_STOPPED = {"created","exited"}
_INSPECT = (
    '{"id":{{json .Id}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
    '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
    '"running":{{json .State.Running}},"status":{{json .State.Status}}}'
)


class StopDenied(ValueError):
    pass


def _need(condition, code):
    if condition is not True:
        raise StopDenied(code)


@dataclass(frozen=True, slots=True, repr=False)
class StopSnapshot:
    daemon: str
    project: str
    containers: tuple[tuple[str,str,str,bool], ...]
    volumes: frozenset[str]


@dataclass(frozen=True, slots=True)
class StopReport:
    ok: bool
    code: str
    detail: str
    stopped: int = 0


def _render_stop(command):
    command = tuple(command)
    # No caller-selected arbitrary Compose options or removal flags.
    expected = ("docker","compose","-f","docker-compose.yml","--env-file",".env",
                "--profile","full","stop")
    _need(command == expected, "stop_command_scope_invalid")
    return (*command[:-1],"config","--format","json")


def observe_stop(root: Path, *, command, environ, runner, admit):
    render = _render_stop(command)
    def fence():
        _need(admit() is True,"stop_configuration_changed")
    def inspect(args,limit):
        fence()
        data=_json_observation(root,runner,args,environ,limit=limit)
        fence()
        return data
    def names(args):
        fence()
        data=_names(root,runner,args,environ)
        fence()
        return data
    def daemon():
        value=inspect(["docker","info","--format",'{"id":{{json .ID}}}'],_MAX_STATE).get("id")
        _need(type(value) is str and _DAEMON_ID.fullmatch(value) is not None,
              "stop_daemon_unverified")
        return value
    ident=daemon()
    config=inspect(render,_MAX_MODEL)
    project=config.get("name")
    services=config.get("services")
    _need(type(project) is str and _PROJECT.fullmatch(project) is not None,
          "stop_project_unverified")
    _need(type(services) is dict and set(services)==set(CONTAINER_ROLES)
          and all(type(spec) is dict and spec.get("container_name")=="tutolage-"+role
                  for role,spec in services.items()),"stop_service_scope_invalid")
    del config,services
    container_args=["ps","--all","--format","{{.Names}}"]
    project_args=["ps","--all","--filter","label=com.docker.compose.project="+project,
                  "--format","{{.Names}}"]
    volume_args=["volume","ls","--format","{{.Name}}"]
    all_names=names(container_args)
    owned=names(project_args)
    volumes=names(volume_args)
    _need(owned.issubset(all_names) and owned==all_names.intersection(_FIXED),
          "stop_container_ownership_mismatch")
    containers=[]
    for name in sorted(owned):
        payload=inspect(["docker","container","inspect","--format",_INSPECT,name],_MAX_STATE)
        cid=payload.get("id")
        running=payload.get("running")
        status=payload.get("status")
        _need(payload.get("project")==project and payload.get("service")==_FIXED[name],
              "stop_container_ownership_mismatch")
        _need(type(cid) is str and _CONTAINER_ID.fullmatch(cid) is not None
              and type(running) is bool and type(status) is str
              and status in {"created","running","paused","restarting","exited","dead","removing"},
              "stop_container_state_unverified")
        containers.append((name,cid,status,running))
    _need(len({row[1] for row in containers})==len(containers),"stop_container_identity_duplicate")
    _need(names(project_args)==owned and names(container_args)==all_names
          and names(volume_args)==volumes and daemon()==ident,"stop_inventory_changed")
    final=inspect(render,_MAX_MODEL)
    _need(final.get("name")==project,"stop_project_changed")
    return StopSnapshot(ident,project,tuple(containers),volumes)


def stop_owned_runtime(root: Path, *, command, environ, runner=subprocess.run, lease):
    """Execute the reviewed stop command once, preserving uncertain intent."""
    captured=compose_operation_environment(environ)
    try:
        epoch=runtime_source_fingerprint(root)
        def admit():
            try:
                return lease.current() and runtime_source_fingerprint(root)==epoch
            except (OSError,ValueError):
                return False
        before=observe_stop(root,command=command,environ=captured,runner=runner,admit=admit)
        _need(admit(),"stop_configuration_changed")
    except (StopDenied,StorageCustodyDenied,OSError,ValueError,TypeError,KeyError,
            subprocess.SubprocessError):
        return StopReport(False,"stop_preflight_unverified",
                          "Stop blocked: selected project or storage custody unverified; preserve existing containers")
    # Even if no containers are present, the preflight proves the selected
    # project scope. No unnecessary mutation is issued.
    if not before.containers:
        return StopReport(True,"already_stopped","No application containers observed in the selected project")
    try:
        completed=run_mutation(lease,"compose-stop",runner,list(command),cwd=root,env=captured,
                               check=False,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,text=True,timeout=90)
    except (OSError,subprocess.SubprocessError,RuntimeOperationDenied) as exc:
        return StopReport(False,"stop_completion_uncertain",
                          "Unable to stop services: "+type(exc).__name__+"; inspect runtime recovery")
    status=getattr(completed,"returncode",None)
    if type(status) is not int or not 0<=status<=255:
        return StopReport(False,"stop_completion_uncertain","Stop completion uncertain; inspect runtime recovery")
    if status:
        return StopReport(False,"stop_process_failed",f"Stop command failed with exit {status}")
    try:
        after=observe_stop(root,command=command,environ=captured,runner=runner,admit=admit)
        _need(after.daemon==before.daemon and after.project==before.project,
              "stop_project_changed")
        _need({row[:2] for row in after.containers}=={row[:2] for row in before.containers},
              "stop_container_identity_changed")
        _need(before.volumes.issubset(after.volumes),"stop_volume_missing")
        _need(all(row[2] in _STOPPED and row[3] is False for row in after.containers),
              "stop_container_still_active")
        _need(admit(),"stop_configuration_changed")
    except (StopDenied,StorageCustodyDenied,OSError,ValueError,TypeError,KeyError,
            subprocess.SubprocessError):
        return StopReport(False,"stop_postcondition_unverified",
                          "Stop exit observed but container or volume preservation unverified; inspect existing services")
    return StopReport(True,"stopped_observed","Skeleton services stopped; container and volume presence reobserved",
                      len(after.containers))
