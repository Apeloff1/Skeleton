"""Read-only admission of resolved Compose project and persistent bindings.

The ordinary Compose config check validates syntax, not storage identity.
Use the actual resolved project, not a directory-name approximation. Never
return rendered configuration, credentials, host mount sources or container
labels to an installation receipt. No daemon mutations are performed here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
import json
import re
import subprocess
import tempfile
from pathlib import Path
from collections.abc import Mapping

from skeleton.app.compose_runtime_identity import RuntimeIdentityDenied
from skeleton.app.storage_custody import (
    CONTAINER_ROLES, VOLUME_ROLES, StorageCustodyDenied, _names,
)

_PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}\Z")
_BINDINGS = {
    "mongo": {"/data/db": "mongo_data", "/data/configdb": "mongo_config"},
    "backend": {"/app/data": "backend_data"},
    "skeleton": {"/app/data": "skeleton_data"},
}
_MAX_CONFIG = 2 * 1024 * 1024
_MAX_INSPECT = 128 * 1024
_ACTIVE_ROLES = ("mongo", "skeleton", "backend", "frontend")
_VOLUME_STAMP = re.compile(r"[0-9A-Za-z:+. -]{1,128}\Z")
_DAEMON_ID = re.compile(r"[0-9A-Za-z:_-]{1,256}\Z")
_CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                                    ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class _BindingIdentity:
    daemon_digest: str
    model_digest: str
    volume_digests: tuple[tuple[str, str], ...]
    # A random per-campaign HMAC key avoids exposing an offline secret
    # guessing oracle even if an in-memory identity is accidentally logged.
    model_key: bytes
    active_runtime_digests: tuple[tuple[str, str], ...]
# Emit only the relevant labels and mount metadata. Never inspect Config.Env.
_CONTAINER_TEMPLATE = (
    '{"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
    '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
    '"id":{{json .Id}},"running":{{json .State.Running}},'
    '"image_id":{{json .Image}},"image_ref":{{json .Config.Image}},'
    '"started_at":{{json .State.StartedAt}},"restart_count":{{json .RestartCount}},'
    '"ports":{{json .NetworkSettings.Ports}},"mounts":{{json .Mounts}}}'
)
_VOLUME_TEMPLATE = (
    '{"project":{{json (index .Labels "com.docker.compose.project")}},'
    '"role":{{json (index .Labels "com.docker.compose.volume")}},'
    '"driver":{{json .Driver}},"scope":{{json .Scope}},'
    '"created":{{json .CreatedAt}},"options":{{json .Options}}}'
)


@dataclass(frozen=True, slots=True)
class BindingReport:
    observed: bool
    admitted: bool
    code: str
    existing_containers: int = 0
    existing_volumes: int = 0
    identity: _BindingIdentity | None = None

    def to_dict(self):
        return {
            "schema":"skeleton.app.compose_storage_binding.v1",
            "observed":self.observed,"admitted":self.admitted,"code":self.code,
            "existing_containers":self.existing_containers,
            "existing_volumes":self.existing_volumes,
            "database_authenticated":False,"backup_verified":False,
            "storage_modified":False,
            "runtime_image_provenance_verified":False,
            "source_to_image_verified":False,
        }


class BindingDenied(StorageCustodyDenied):
    pass


def _require(condition, code):
    if condition is not True:
        raise BindingDenied(code)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BindingDenied("duplicate_observation_field")
        result[key] = value
    return result


def _constant(_value):
    raise BindingDenied("invalid_observation_number")


def _json_observation(root, runner, command, environ, *, limit):
    # Disk-backed, private temporary capture, immediately closed. Rendered
    # config can include secrets, so no stdout/stderr is inherited or logged.
    # This is ephemeral capture, not secure erasure or backup custody.
    with tempfile.TemporaryFile() as output:
        completed = runner(list(command), cwd=root, env=dict(environ),
                           check=False, stdin=subprocess.DEVNULL, stdout=output,
                           stderr=subprocess.DEVNULL, text=False, timeout=30)
        _require(type(getattr(completed,"returncode",None)) is int
                 and completed.returncode == 0, "docker_observation_failed")
        output.seek(0)
        raw = output.read(limit + 1)
    _require(0 < len(raw) <= limit, "docker_observation_size_invalid")
    result = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_constant)
    _require(type(result) is dict, "docker_observation_schema_invalid")
    return result


def _reviewed_hot_parent(root, service, target, other, mount, *, hot):
    # The canonical hot overlay has a read-only /app source bind and an
    # explicit named /app/data volume. Compose mounts the more specific
    # destination independently. Never grant the exception to an arbitrary
    # source path, writable bind or another service.
    if (not hot or service != "backend" or target != "/app/data" or other != "/app"
            or mount.get("type") != "bind" or mount.get("read_only") is not True):
        return False
    source = mount.get("source")
    return (type(source) is str and Path(source).is_absolute()
            and Path(source).resolve() == (root / "backend").resolve())


def _resolved_model(config, *, root=None, hot=False):
    project = config.get("name")
    _require(type(project) is str and _PROJECT.fullmatch(project) is not None,
             "compose_project_identity_invalid")
    services, volumes = config.get("services"), config.get("volumes")
    _require(type(services) is dict and type(volumes) is dict
             and len(services) <= 32 and len(volumes) <= 32, "compose_storage_model_invalid")
    _require(set(_BINDINGS).issubset(services) and "frontend" in services
             and set(services).issubset(CONTAINER_ROLES), "compose_service_inventory_invalid")
    resolved = {}
    required_roles = {role for mounts in _BINDINGS.values() for role in mounts.values()}
    _require(required_roles.issubset(volumes) and set(volumes).issubset(VOLUME_ROLES),
             "compose_volume_inventory_invalid")
    for role, spec in volumes.items():
        _require(type(spec) is dict, "compose_volume_model_invalid")
        name = project + "_" + role
        _require(spec.get("name") == name
                 and spec.get("driver", "local") == "local"
                 and spec.get("external", False) is False
                 and not spec.get("driver_opts"), "compose_volume_identity_mismatch")
        resolved[role] = name
    for service, spec in services.items():
        _require(type(spec) is dict and spec.get("container_name") == "tutolage-" + service,
                 "compose_container_identity_mismatch")
        mounts = spec.get("volumes", [])
        _require(type(mounts) is list and len(mounts) <= 64, "compose_mount_inventory_invalid")
        targets = {}
        for mount in mounts:
            _require(type(mount) is dict and type(mount.get("target")) is str,
                     "compose_mount_model_invalid")
            target = mount["target"]
            _require(target not in targets, "compose_duplicate_mount_target")
            targets[target] = mount
        for target, role in _BINDINGS.get(service, {}).items():
            mount = targets.get(target)
            _require(type(mount) is dict and mount.get("type") == "volume"
                     and mount.get("source") == role and mount.get("read_only", False) is False,
                     "compose_persistent_mount_mismatch")
            # A volume mounted over a parent directory can conceal application
            # files or another state mount; prohibit parents of canonical paths.
            for other in targets:
                if other != target:
                    shadow = (target.startswith(other.rstrip("/") + "/")
                              or other.startswith(target.rstrip("/") + "/"))
                    _require(not shadow or (root is not None and _reviewed_hot_parent(
                        root,service,target,other,targets[other],hot=hot)),
                        "compose_persistent_parent_mount")
        for target, mount in targets.items():
            if mount.get("type") == "volume" and mount.get("source") in required_roles:
                _require(_BINDINGS.get(service, {}).get(target) == mount["source"],
                         "compose_authority_volume_aliased")
    return project, resolved


def _container_binding(payload, project, role, resolved, *, require_running=False):
    _require(payload.get("project") == project and payload.get("service") == role,
             "existing_container_project_mismatch")
    ident = payload.get("id")
    _require(type(ident) is str and _CONTAINER_ID.fullmatch(ident) is not None
             and type(payload.get("running")) is bool, "existing_container_state_invalid")
    if require_running:
        _require(payload["running"] is True, "required_container_not_running")
    mounts = payload.get("mounts")
    _require(type(mounts) is list and len(mounts) <= 128, "existing_mount_inventory_invalid")
    targets = {}
    for mount in mounts:
        _require(type(mount) is dict and type(mount.get("Destination")) is str,
                 "existing_mount_inventory_invalid")
        destination = mount["Destination"]
        _require(destination not in targets, "existing_duplicate_mount_target")
        targets[destination] = mount
    for target, volume_role in _BINDINGS.get(role, {}).items():
        mount = targets.get(target)
        _require(type(mount) is dict and mount.get("Type") == "volume"
                 and mount.get("Name") == resolved[volume_role] and mount.get("RW") is True,
                 "existing_persistent_mount_mismatch")
        for other in targets:
            if other != target:
                shadow = (target.startswith(other.rstrip("/") + "/")
                          or other.startswith(target.rstrip("/") + "/"))
                # Existing backend hot-reload containers can be stopped or
                # re-created into production without treating their explicit
                # writable child data mount as a foreign volume. This
                # observes storage topology, not the bind's code provenance.
                prior_hot = (role == "backend" and target == "/app/data" and other == "/app"
                             and targets[other].get("Type") == "bind"
                             and targets[other].get("RW") is False)
                _require(not shadow or prior_hot, "existing_persistent_mount_shadowed")
    authority = {resolved[volume] for mounts in _BINDINGS.values() for volume in mounts.values()}
    for target,mount in targets.items():
        if mount.get("Type") == "volume" and mount.get("Name") in authority:
            expected = _BINDINGS.get(role,{}).get(target)
            _require(expected is not None and mount["Name"] == resolved[expected],
                     "existing_authority_volume_aliased")
    return _digest((ident, payload["running"], role, [
        (target, mount.get("Type"), mount.get("Name"), mount.get("RW"))
        for target,mount in sorted(targets.items())
    ]))


def _volume_binding(payload, project, role):
    _require(payload.get("project") == project and payload.get("role") == role
             and payload.get("driver") == "local" and payload.get("scope") == "local",
             "existing_volume_ownership_mismatch")
    created = payload.get("created")
    _require(type(created) is str and _VOLUME_STAMP.fullmatch(created) is not None,
             "existing_volume_creation_unverified")
    _require(payload.get("options") in (None, {}), "existing_volume_driver_options_unqualified")
    return _digest((project,role,payload["driver"],payload["scope"],created))


def _render_command(command):
    # Only accept the already constructed pinned Compose invocation. Reuse
    # its exact file/env selection; never accept arbitrary executable flags.
    command = tuple(command)
    _require(command[:2] == ("docker","compose") and "up" in command
             and "--env-file" in command, "compose_launch_command_invalid")
    offset = command.index("up")
    prefix = command[:offset]
    _require(prefix.count("--env-file") == 1
             and prefix[prefix.index("--env-file")+1:prefix.index("--env-file")+2] == (".env",),
             "compose_environment_not_pinned")
    return (*prefix,"config","--format","json")


def observe_binding(root: Path, *, command, environ: Mapping[str,str], runner=subprocess.run,
                    admit=None, previous: BindingReport | None=None,
                    require_started: bool=False,
                    require_same_runtime: bool=False,
                    require_frontend: bool=False) -> BindingReport:
    """Observe intended and existing storage, then recheck inventory and epoch."""
    root = Path(root).resolve()
    copied = dict(environ)
    existing_containers = existing_volumes = 0

    def fence():
        _require(admit is None or admit() is True, "runtime_epoch_changed")

    def names(args):
        fence()
        result = _names(root,runner,args,copied)
        fence()
        return result

    def inspect(args, limit):
        fence()
        result = _json_observation(root,runner,args,copied,limit=limit)
        fence()
        return result

    try:
        render = _render_command(command)
        _require(type(require_started) is bool and type(require_same_runtime) is bool
                 and type(require_frontend) is bool
                 and not (require_started and require_frontend)
                 and (not require_same_runtime or require_started or require_frontend),
                 "binding_mode_invalid")
        active_roles = _ACTIVE_ROLES if require_started else ("frontend",) if require_frontend else ()
        _require(not active_roles or previous is not None, "prior_binding_unverified")
        def daemon():
            data = inspect(["docker","info","--format",'{"id":{{json .ID}}}'],_MAX_INSPECT)
            identity = data.get("id")
            _require(type(identity) is str and _DAEMON_ID.fullmatch(identity) is not None,
                     "docker_daemon_identity_unverified")
            return _digest(identity)

        daemon_digest = daemon()
        hot = "docker-compose.hot.yml" in render
        from skeleton.app.assembly import _runtime_env
        from skeleton.app.compose_runtime_identity import model_identity, actual_identity, verify_image
        config = inspect(render,_MAX_CONFIG)
        project, resolved = _resolved_model(config,root=root,hot=hot)
        values = _runtime_env(root,copied)
        expected_runtime = model_identity(config,values=values,hot=hot)
        if previous is not None:
            _require(type(previous) is BindingReport and previous.admitted is True
                     and previous.identity is not None, "prior_binding_unverified")
        key = previous.identity.model_key if previous is not None else secrets.token_bytes(32)

        def model_mac(value):
            raw = json.dumps(value,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode("ascii")
            return hmac.new(key,raw,hashlib.sha256).hexdigest()

        # Bind the entire resolved model across observations, including
        # build args, environment, security, networks and dependency policy.
        # Neither the raw model nor its keyed fingerprint is published.
        model_digest = model_mac(config)
        del config,values
        if previous is not None:
            _require(previous.identity.daemon_digest == daemon_digest
                     and previous.identity.model_digest == model_digest,
                     "launch_daemon_or_storage_model_changed")
        volume_args = ["volume","ls","--format","{{.Name}}"]
        container_args = ["ps","--all","--format","{{.Names}}"]
        all_volumes, all_containers = names(volume_args), names(container_args)
        volume_digests = {}
        container_digests = {}
        runtime_digests = {}

        def observe_runtime(role,payload):
            expected = expected_runtime[role]
            image_id,ports = actual_identity(payload,expected)
            tagged = inspect(["docker","image","inspect","--format",'{"id":{{json .Id}}}',
                              expected.image],_MAX_INSPECT)
            verify_image(tagged,image_id)
            started = payload.get("started_at")
            restarts = payload.get("restart_count")
            _require(type(started) is str and _VOLUME_STAMP.fullmatch(started) is not None
                     and not started.startswith("0001-")
                     and type(restarts) is int and 0 <= restarts <= 2**31-1,
                     "running_container_epoch_unverified")
            return _digest((payload["id"],started,restarts,image_id,ports))

        if active_roles:
            _require(all("tutolage-"+role in all_containers for role in active_roles),
                     "required_runtime_storage_not_observed")
        if require_started:
            _require(all(resolved[role] in all_volumes
                         for mounts in _BINDINGS.values() for role in mounts.values()),
                     "required_runtime_storage_not_observed")
        for role, expected in resolved.items():
            # Legacy suffix matches and Compose-labeled volumes both imply
            # previous state. Refuse a parallel empty replacement project.
            matches = {name for name in all_volumes
                       if name == role or name.endswith("_" + role)}
            matches.update(names(["volume","ls","--filter",
                                  "label=com.docker.compose.volume="+role,"--format","{{.Name}}"]))
            _require(matches.issubset({expected}), "alternate_persistent_volume_detected")
            if expected in all_volumes:
                payload = inspect(["docker","volume","inspect","--format",_VOLUME_TEMPLATE,expected],
                                  _MAX_INSPECT)
                volume_digests[role] = _volume_binding(payload,project,role)
                existing_volumes += 1
        for role in CONTAINER_ROLES:
            name = "tutolage-" + role
            if name in all_containers:
                payload = inspect(["docker","container","inspect","--format",
                                   _CONTAINER_TEMPLATE,name],_MAX_INSPECT)
                container_digests[role] = _container_binding(payload,project,role,resolved,
                    require_running=role in active_roles)
                if role in active_roles:
                    runtime_digests[role] = observe_runtime(role,payload)
                existing_containers += 1
        if previous is not None:
            for role, digest in previous.identity.volume_digests:
                _require(volume_digests.get(role) == digest, "previous_persistent_volume_changed")
        if require_same_runtime:
            _require(dict(previous.identity.active_runtime_digests) == runtime_digests
                     and set(runtime_digests) == set(active_roles),
                     "runtime_epoch_changed_during_qualification")
        for role, digest in volume_digests.items():
            payload = inspect(["docker","volume","inspect","--format",_VOLUME_TEMPLATE,resolved[role]],_MAX_INSPECT)
            _require(_volume_binding(payload,project,role) == digest, "volume_binding_changed")
        for role,digest in container_digests.items():
            payload = inspect(["docker","container","inspect","--format",_CONTAINER_TEMPLATE,
                               "tutolage-"+role],_MAX_INSPECT)
            _require(_container_binding(payload,project,role,resolved,
                require_running=role in active_roles) == digest,
                "container_binding_changed")
            if role in runtime_digests:
                _require(observe_runtime(role,payload)==runtime_digests[role],
                         "running_image_or_ingress_changed")
        _require(names(volume_args) == all_volumes and names(container_args) == all_containers,
                 "docker_storage_inventory_changed")
        reloaded = inspect(render,_MAX_CONFIG)
        _require(_resolved_model(reloaded,root=root,hot=hot) == (project,resolved)
                 and hmac.compare_digest(model_mac(reloaded),model_digest),
                 "compose_storage_model_changed")
        del reloaded
        fence()
        _require(daemon() == daemon_digest, "docker_daemon_changed")
        identity = _BindingIdentity(daemon_digest,model_digest,tuple(sorted(volume_digests.items())),
                                    key,tuple(sorted(runtime_digests.items())))
        return BindingReport(True,True,"binding_observed",existing_containers,existing_volumes,identity)
    except (BindingDenied, RuntimeIdentityDenied) as exc:
        # All BindingDenied codes are fixed internal identifiers.
        return BindingReport(False,False,str(exc))
    except (StorageCustodyDenied,OSError,ValueError,TypeError,KeyError,IndexError,
            RecursionError,subprocess.SubprocessError):
        return BindingReport(False,False,"binding_observation_unavailable")



def recovery_render_matches(start_command, recovery_command):
    """Admit only the canonical independently startable frontend recovery."""
    try:
        original=tuple(start_command)
        recovery=tuple(recovery_command)
        _require(_render_command(original)==_render_command(recovery),
                 "recovery_compose_model_mismatch")
        offset=recovery.index("up")
        _require(recovery[offset:]==("up","-d","--no-deps","frontend"),
                 "recovery_command_scope_invalid")
        return True
    except (BindingDenied,ValueError,TypeError):
        return False
