"""Local Compose isolation contract, checked against model and live daemon.

No environment values, credential material, network addresses, or container
configuration dumps are published. These are constrained runtime settings,
not proof of host security, kernel isolation, or image provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from skeleton.app.compose_runtime_identity import RuntimeIdentityDenied

_PROTECTED = frozenset(("backend", "skeleton"))
_NETWORK = "tutolage"
_NO_PRIVS = frozenset(("no-new-privileges:true", "no-new-privileges=true"))


def _need(condition, code):
    if condition is not True:
        raise RuntimeIdentityDenied(code)


def _empty(value):
    return value is None or (type(value) in (list,dict) and len(value)==0)


def _options(value):
    _need(type(value) is list and len(value)<=16 and all(type(v) is str for v in value),
          "security_options_invalid")
    return set(value)


def _private_namespaces(spec, *, live=False):
    if live:
        _need(spec.get("privileged") is False, "runtime_privileged_container")
        _need(spec.get("pid_mode") in ("",None)
              and spec.get("ipc_mode") in ("","private","shareable",None)
              and spec.get("uts_mode") in ("",None),
              "runtime_shared_host_namespace")
        for key in ("cap_add","devices","device_requests","device_cgroup_rules"):
            _need(_empty(spec.get(key)), "runtime_unreviewed_device_or_capability")
    else:
        _need(spec.get("privileged",False) is False, "compose_privileged_container")
        _need(spec.get("pid") in (None,"") and spec.get("ipc") in (None,"","private","shareable")
              and spec.get("uts") in (None,"") and spec.get("network_mode") in (None,""),
              "compose_shared_host_namespace")
        for key in ("cap_add","devices","device_cgroup_rules","device_requests","gpus",
                    "volumes_from","external_links","links"):
            _need(_empty(spec.get(key)), "compose_unreviewed_device_or_capability")


@dataclass(frozen=True, slots=True)
class IsolationContract:
    network: str
    protected: bool
    tmpfs_required: bool


def _network_names(value):
    if type(value) is dict:
        return set(value)
    if type(value) is list and all(type(v) is str for v in value):
        return set(value)
    raise RuntimeIdentityDenied("compose_network_inventory_invalid")


def _tmpfs_options(value):
    if type(value) is str:
        return set(value.split(","))
    raise RuntimeIdentityDenied("runtime_tmpfs_options_invalid")


def _required_tmpfs(options):
    _need({"rw","noexec","nosuid","nodev"}.issubset(options),
          "runtime_tmpfs_isolation_missing")
    # Engine and backend need writable temporary space, but not an
    # unbounded tmpfs. Docker may normalize size=64m to size=67108864.
    sizes={v for v in options if v.startswith("size=")}
    _need(len(sizes)==1 and next(iter(sizes)).lower() in ("size=64m","size=67108864"),
          "runtime_tmpfs_capacity_mismatch")


def model_security(config, *, root: Path, hot: bool):
    project=config["name"]
    networks=config.get("networks")
    _need(type(networks) is dict and set(networks)=={_NETWORK},
          "compose_network_inventory_invalid")
    net=networks[_NETWORK]
    expected=project+"_"+_NETWORK
    _need(type(net) is dict and net.get("name")==expected
          and net.get("driver")=="bridge" and net.get("external",False) is False
          and not net.get("driver_opts"),"compose_network_identity_mismatch")
    contracts={}
    for role,spec in config["services"].items():
        _private_namespaces(spec)
        _need(_network_names(spec.get("networks"))=={_NETWORK},
              "compose_service_network_mismatch")
        if role in _PROTECTED:
            _need(spec.get("read_only") is True
                  and _options(spec.get("cap_drop"))=={"ALL"}
                  and len(_options(spec.get("security_opt")))==1
                  and _options(spec.get("security_opt")).issubset(_NO_PRIVS),
                  "compose_required_isolation_missing")
            tmpfs=spec.get("tmpfs")
            _need(type(tmpfs) is list and len(tmpfs)==1 and type(tmpfs[0]) is str
                  and tmpfs[0].startswith("/tmp:"),"compose_tmpfs_missing")
            _required_tmpfs(_tmpfs_options(tmpfs[0].split(":",1)[1]))
            _need(spec.get("user") not in ("root","0","0:0",0),
                  "compose_root_user_override")
        # Bind-mounted host paths are admitted only at reviewed roles and
        # destinations; no Docker socket or arbitrary host path exposure.
        allowed={"skeleton": {"/app/local-ai": True}}
        if hot:
            allowed.update({"backend":{"/app":True,"/app/skeleton":True},
                            "frontend":{"/app":False}})
        actual={}
        for mount in spec.get("volumes",[]):
            if mount.get("type")=="bind":
                target=mount.get("target")
                source=mount.get("source")
                ro=mount.get("read_only",False)
                _need(target in allowed.get(role,{}) and ro is allowed[role][target]
                      and type(source) is str and Path(source).is_absolute(),
                      "compose_host_bind_not_reviewed")
                if role!="skeleton":
                    folder= "skeleton" if target=="/app/skeleton" else role
                    _need(Path(source).resolve()==(root/folder).resolve(),
                          "compose_host_bind_source_mismatch")
                else:
                    path=Path(source).resolve()
                    _need(path!=Path(path.anchor) and path!=(root/".env").resolve(),
                          "compose_model_bind_path_invalid")
                actual[target]=ro
        _need(actual==allowed.get(role,{}),"compose_reviewed_bind_missing")
        contracts[role]=IsolationContract(expected,role in _PROTECTED,role in _PROTECTED)
    return contracts


def live_security(payload, expected: IsolationContract, *, require_healthy=False):
    # Only fixed HostConfig fields are projected by the caller; no Config.Env.
    spec=payload.get("isolation")
    _need(type(spec) is dict,"runtime_isolation_unobserved")
    _private_namespaces(spec,live=True)
    names=spec.get("networks")
    _need(type(names) is list and names==[expected.network]
          and spec.get("network_mode")==expected.network,
          "runtime_network_identity_mismatch")
    if expected.protected:
        _need(spec.get("read_only") is True
              and _options(spec.get("cap_drop"))=={"ALL"}
              and len(_options(spec.get("security_opt")))==1
              and _options(spec.get("security_opt")).issubset(_NO_PRIVS),
              "runtime_required_isolation_missing")
        user=spec.get("user")
        _need(type(user) is str and user and user.split(":",1)[0] not in ("root","0"),
              "runtime_nonroot_user_unverified")
        tmpfs=spec.get("tmpfs")
        _need(type(tmpfs) is dict and set(tmpfs)=={"/tmp"},"runtime_tmpfs_missing")
        _required_tmpfs(_tmpfs_options(tmpfs["/tmp"]))
    # On initial post-start the health check may be starting. At the final
    # HTTP continuity gate, require Docker's independent health verdict.
    if require_healthy:
        _need(payload.get("health")=="healthy","runtime_daemon_health_unverified")
    return (expected.network,expected.protected,expected.tmpfs_required)


def network_security(payload, project, expected):
    """Bind network identity to the canonical local, project-owned bridge."""
    ident=payload.get("id")
    _need(type(ident) is str and re.fullmatch(r"[0-9a-f]{64}",ident) is not None
          and payload.get("name")==expected and payload.get("project")==project
          and payload.get("role")==_NETWORK and payload.get("driver")=="bridge"
          and payload.get("scope")=="local" and payload.get("ingress") is False,
          "runtime_bridge_ownership_unverified")
    return ident
