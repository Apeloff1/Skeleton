"""Closed local ingress and running image identity contract.

Compare the effective Compose port model to the daemon's actual published
bindings. Image identity is local tag-to-container identity, not trusted
registry provenance, SBOM validation or source-to-image attestation.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IMAGE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,511}\Z")
_PORT = re.compile(r"[1-9][0-9]{0,4}\Z")
_LOCAL = "127.0.0.1"
HOST_DEFAULTS = {
    "mongo": ("MONGO_PORT",27017,27017),
    "skeleton": ("SKELETON_PORT",8010,8001),
    "backend": ("BACKEND_PORT",8001,8001),
    "frontend": ("FRONTEND_PORT",3000,3000),
    "chroma": ("CHROMA_PORT",8000,8000),
}
_HOT = (8081,19000,19001,19002)


class RuntimeIdentityDenied(ValueError):
    pass


def _need(condition, code):
    if condition is not True:
        raise RuntimeIdentityDenied(code)


def _port(value):
    if type(value) is int:
        number=value
    elif type(value) is str and _PORT.fullmatch(value):
        number=int(value)
    else:
        raise RuntimeIdentityDenied("runtime_port_invalid")
    _need(1 <= number <= 65535,"runtime_port_invalid")
    return number


@dataclass(frozen=True, slots=True)
class ServiceIdentity:
    role: str
    image: str
    ports: tuple[tuple[int,int], ...]


def model_identity(config, *, values: Mapping[str,str], hot: bool):
    """Return only nonsecret normalized identity, without interpolated Env."""
    project=config["name"]
    services=config["services"]
    _need(type(hot) is bool,"runtime_mode_invalid")
    records={}
    seen=set()
    for role,spec in services.items():
        key,default,target=HOST_DEFAULTS[role]
        published=_port(values.get(key) or default)
        if role=="frontend":
            target=_port(values.get("FRONTEND_CONTAINER_PORT") or target)
            _need(target in (3000,8080),"frontend_container_port_invalid")
        expected={(target,published)}
        if hot and role=="frontend":
            expected.update((port,port) for port in _HOT)
        ports=spec.get("ports")
        _need(type(ports) is list and 0 < len(ports) <= 8,"compose_ingress_inventory_invalid")
        observed=set()
        for row in ports:
            _need(type(row) is dict and row.get("host_ip")==_LOCAL
                  and row.get("protocol","tcp")=="tcp"
                  and row.get("mode","ingress") in ("ingress","host"),
                  "compose_ingress_not_loopback")
            pair=(_port(row.get("target")),_port(row.get("published")))
            _need(pair not in observed and pair[1] not in seen,"compose_ingress_collision")
            observed.add(pair)
            seen.add(pair[1])
        _need(observed==expected,"compose_ingress_mismatch")
        image=spec.get("image") or project+"-"+role
        _need(type(image) is str and _IMAGE_REF.fullmatch(image) is not None,
              "compose_image_reference_invalid")
        if role in ("mongo","chroma"):
            _need(re.search(r"@sha256:[0-9a-f]{64}\Z",image) is not None,
                  "compose_external_image_unpinned")
        records[role]=ServiceIdentity(role,image,tuple(sorted(observed)))
    return records


def actual_identity(payload, expected: ServiceIdentity):
    """Exact active TCP ingress and image reference; no container env access."""
    image_id=payload.get("image_id")
    _need(type(image_id) is str and _IMAGE_ID.fullmatch(image_id) is not None,
          "running_image_identity_invalid")
    # Docker may normalize a tagless Compose-built image to :latest.
    ref=payload.get("image_ref")
    candidates={expected.image}
    if "@" not in expected.image and ":" not in expected.image.rsplit("/",1)[-1]:
        candidates.add(expected.image+":latest")
    _need(type(ref) is str and ref in candidates,"running_image_reference_mismatch")
    ports=payload.get("ports")
    _need(type(ports) is dict and len(ports)<=64,"running_ingress_inventory_invalid")
    observed=set()
    for key,rows in ports.items():
        # Unpublished EXPOSE metadata is represented by null; it is not
        # a host binding. Any actual extra binding must pass the contract.
        if rows is None or rows==[]:
            continue
        _need(type(key) is str and key.endswith("/tcp") and type(rows) is list
              and len(rows)==1 and type(rows[0]) is dict,
              "running_ingress_binding_invalid")
        row=rows[0]
        _need(row.get("HostIp")==_LOCAL,"running_ingress_not_loopback")
        pair=(_port(key[:-4]),_port(row.get("HostPort")))
        _need(pair not in observed,"running_ingress_duplicate")
        observed.add(pair)
    _need(observed==set(expected.ports),"running_ingress_mismatch")
    return image_id,tuple(sorted(observed))


def verify_image(payload, observed_id):
    _need(type(payload) is dict and payload.get("id")==observed_id,
          "running_image_tag_identity_mismatch")
