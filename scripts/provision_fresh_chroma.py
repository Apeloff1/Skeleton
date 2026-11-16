#!/usr/bin/env python3
"""Provision a new durable Chroma service without touching historical stores.

This is deliberately outside the legacy full Compose profile. The exact-head
disposable persistence receipt is a prerequisite, not production approval.
Existing legacy resources, uncertain creation, identity drift and unreviewed
receipts block operation. No code path removes or migrates any Docker resource.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from uuid import uuid4

from qualify_chroma_persistence import IMAGE, SCHEMA as FIXTURE_SCHEMA, digest, _await_ready
from stage_chroma_recovery import open_directory, read_private_file, _dir_stamp

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/chroma/durable.compose.yml"
SCHEMA = "skeleton.chroma.fresh-deployment.v1"
CHECKS = frozenset({
    "real_vector_crud_and_index", "same_container_restart_persistence",
    "durable_update_delete", "new_container_same_volume_data_and_vector_index",
    "verified_data_mount_and_volume_identity",
})
TOKEN_LABEL = "org.skeleton.chroma-provision"
PROJECT_LABEL = "com.docker.compose.project"
SERVICE_LABEL = "com.docker.compose.service"
NETWORK_LABEL = "com.docker.compose.network"
VOLUME_LABEL = "com.docker.compose.volume"
NAME = "tutolage-chroma"
ENGINE = "tutolage-skeleton"
BOUND = 512 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}\Z", re.ASCII)
TOKEN = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?\Z", re.ASCII)


class ProvisionDenied(RuntimeError):
    """Operator action is required; preserve any resources already created."""


def require(condition, detail):
    if condition is not True:
        raise ProvisionDenied(detail)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, "duplicate JSON field")
            result[key] = value
        return result

    def constant(_value):
        raise ProvisionDenied("nonfinite JSON value")

    require(type(raw) is bytes and len(raw) <= BOUND, "invalid bounded JSON")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ProvisionDenied("invalid JSON observation") from exc


def _head(expected):
    require(type(expected) is str and SHA.fullmatch(expected) is not None,
            "exact source head required")
    env = {"PATH": os.defpath, "HOME": "/tmp", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_OPTIONAL_LOCKS": "0"}
    def git(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              check=True, timeout=20).stdout
    try:
        require(git("rev-parse", "--verify", "HEAD").decode("ascii").strip() == expected,
                "source head differs from reviewed fixture")
        git("diff", "--quiet", "--no-ext-diff", "HEAD", "--")
        git("diff", "--cached", "--quiet", "--no-ext-diff", "HEAD", "--")
    except (subprocess.SubprocessError, UnicodeError, OSError) as exc:
        raise ProvisionDenied("exact clean tracked source unavailable") from exc


def fixture_receipt(raw, expected_digest, head):
    require(type(expected_digest) is str and HEX.fullmatch(expected_digest) is not None
            and sha(raw) == expected_digest, "independent fixture receipt pin mismatch")
    row = _json(raw)
    require(type(row) is dict and set(row) == {
        "schema", "source_head", "image", "image_id", "version", "scope", "checks",
        "fixture_cleanup_verified", "synthetic_vector_state_sha256",
        "legacy_migration_qualified", "production_full_profile_qualified",
        "release_qualified", "receipt_sha256",
    }, "fixture receipt shape invalid")
    body = dict(row)
    claimed = body.pop("receipt_sha256")
    require(type(claimed) is str and claimed == digest(body), "fixture receipt digest invalid")
    require(row["schema"] == FIXTURE_SCHEMA and row["source_head"] == head
            and row["image"] == IMAGE and row["scope"] == "disposable_named_volume_only",
            "fixture scope or image does not qualify this source")
    require(type(row["image_id"]) is str
            and re.fullmatch(r"sha256:[0-9a-f]{64}", row["image_id"]) is not None
            and type(row["version"]) is str and VERSION.fullmatch(row["version"]) is not None,
            "fixture image identity invalid")
    require(type(row["checks"]) is dict and set(row["checks"]) == CHECKS
            and all(value is True for value in row["checks"].values())
            and row["fixture_cleanup_verified"] is True
            and type(row["synthetic_vector_state_sha256"]) is str
            and HEX.fullmatch(row["synthetic_vector_state_sha256"]) is not None,
            "fixture has unqualified persistence lanes")
    require(all(row[key] is False for key in (
            "legacy_migration_qualified", "production_full_profile_qualified", "release_qualified")),
            "fixture improperly claims deployment authority")
    return row


def docker(*args, environment=None, timeout=30):
    """Fixed local daemon; no inherited Docker context, Compose project or env file."""
    env = {"PATH": os.defpath, "HOME": "/tmp", "LANG": "C", "LC_ALL": "C",
           "COMPOSE_REMOVE_ORPHANS": "0"}
    if environment is not None:
        require(set(environment) == {"SKELETON_CHROMA_NETWORK","SKELETON_CHROMA_VOLUME",
                                     "SKELETON_CHROMA_DURABLE_PORT","SKELETON_CHROMA_PROVISION_TOKEN"},
                "unreviewed Compose environment")
        env.update(environment)
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            done = subprocess.run(
                ["docker", "--host", "unix:///var/run/docker.sock", *args],
                env=env, cwd=ROOT, stdout=out, stderr=err, check=False, timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProvisionDenied("bounded local Docker observation unavailable") from exc
        out.seek(0)
        data = out.read(BOUND + 1)
        require(done.returncode == 0 and len(data) <= BOUND, "Docker operation failed or exceeded bound")
        return data


def _line_items(raw):
    try:
        rows = raw.decode("ascii").splitlines()
    except UnicodeError as exc:
        raise ProvisionDenied("non-ASCII Docker inventory") from exc
    require(all(row and row == row.strip() for row in rows)
            and len(rows) == len(set(rows)), "ambiguous Docker inventory")
    return rows


def _container_ids(*filters):
    return _line_items(docker("ps", "-a", "--no-trunc",
                             *[arg for value in filters for arg in ("--filter", value)],
                             "--format", "{{.ID}}"))


def _volumes(*filters):
    return _line_items(docker("volume", "ls",
                             *[arg for value in filters for arg in ("--filter", value)],
                             "--format", "{{.Name}}"))


def _inspect(kind, name, template):
    value = _json(docker(kind, "inspect", "--format", template, name))
    require(type(value) is dict, "invalid Docker identity observation")
    return value


def _project():
    ids = _container_ids("name=^/tutolage-skeleton$")
    require(len(ids) == 1 and HEX.fullmatch(ids[0]) is not None,
            "exact existing engine container unavailable")
    row = _inspect("container", ids[0],
        '{"id":{{json .Id}},"name":{{json .Name}},"running":{{json .State.Running}},'
        '"labels":{{json .Config.Labels}},"networks":{{json .NetworkSettings.Networks}}}')
    require(row.get("id") == ids[0] and row.get("name") == "/" + ENGINE
            and row.get("running") is True and type(row.get("labels")) is dict,
            "engine identity differs or is not running")
    labels = row["labels"]
    project = labels.get(PROJECT_LABEL)
    require(type(project) is str and PROJECT.fullmatch(project) is not None
            and labels.get(SERVICE_LABEL) == "skeleton", "engine is not the canonical Compose service")
    networks = row.get("networks")
    require(type(networks) is dict and len(networks) == 1, "engine network identity ambiguous")
    network, member = next(iter(networks.items()))
    require(network == project + "_tutolage" and type(member) is dict, "engine Compose network differs")
    observed = _inspect("network", network,
        '{"id":{{json .Id}},"name":{{json .Name}},"driver":{{json .Driver}},'
        '"scope":{{json .Scope}},"labels":{{json .Labels}},"containers":{{json .Containers}}}')
    require(observed.get("id") == member.get("NetworkID")
            and type(observed.get("id")) is str and HEX.fullmatch(observed["id"]) is not None
            and observed.get("name") == network and observed.get("driver") == "bridge"
            and observed.get("scope") == "local" and type(observed.get("labels")) is dict
            and observed["labels"].get(PROJECT_LABEL) == project
            and observed["labels"].get(NETWORK_LABEL) == "tutolage",
            "canonical engine network ownership unavailable")
    require(type(observed.get("containers")) is dict and ids[0] in observed["containers"],
            "engine network membership unavailable")
    return {"project": project, "engine_id": ids[0], "network": network,
            "network_id": observed["id"]}


def _legacy_absent():
    require(not _volumes("label=" + VOLUME_LABEL + "=chroma_data"),
            "historical Chroma volume detected; recovery staging required")
    require(not any(name == "chroma_data" or name.endswith("_chroma_data")
                    for name in _volumes()), "historical Chroma volume detected; no fresh provisioning")


def _fresh_absent(project, volume):
    _legacy_absent()
    require(not _container_ids("name=^/tutolage-chroma$")
            and not _container_ids("label=" + PROJECT_LABEL + "=" + project,
                                   "label=" + SERVICE_LABEL + "=chroma"),
            "existing Chroma container; no recreation or fresh provisioning")
    require(volume not in _volumes() and not _volumes("label=" + PROJECT_LABEL + "=" + project,
            "label=" + VOLUME_LABEL + "=chroma_durable_data"),
            "existing durable Chroma volume; reconcile preserved resources")


def _image_id():
    result = docker("image", "inspect", "--format", "{{.Id}}", IMAGE).decode("ascii").strip()
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", result) is not None,
            "pinned local image unavailable")
    return result


def _volume(volume, project, token):
    row = _inspect("volume", volume,
        '{"name":{{json .Name}},"driver":{{json .Driver}},"scope":{{json .Scope}},'
        '"labels":{{json .Labels}},"mountpoint":{{json .Mountpoint}},"created":{{json .CreatedAt}}}')
    require(row.get("name") == volume and row.get("driver") == "local" and row.get("scope") == "local"
            and type(row.get("labels")) is dict and row["labels"].get(PROJECT_LABEL) == project
            and row["labels"].get(VOLUME_LABEL) == "chroma_durable_data"
            and row["labels"].get(TOKEN_LABEL) == token
            and type(row.get("mountpoint")) is str and row["mountpoint"].startswith("/")
            and type(row.get("created")) is str and bool(row["created"]),
            "durable volume ownership differs")
    return sha(canonical(row))


def _container(project, volume, token, image_id, port, *, allow_running):
    ids = _container_ids("name=^/tutolage-chroma$")
    require(len(ids) == 1 and HEX.fullmatch(ids[0]) is not None
            and _container_ids("label=" + PROJECT_LABEL + "=" + project["project"],
                               "label=" + SERVICE_LABEL + "=chroma") == ids,
            "canonical Chroma container identity ambiguous")
    row = _inspect("container", ids[0],
        '{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Image}},'
        '"labels":{{json .Config.Labels}},"mounts":{{json .Mounts}},'
        '"ports":{{json .HostConfig.PortBindings}},"networks":{{json .NetworkSettings.Networks}},'
        '"running":{{json .State.Running}},"status":{{json .State.Status}}}')
    labels = row.get("labels")
    require(row.get("id") == ids[0] and row.get("name") == "/" + NAME
            and row.get("image") == image_id and type(labels) is dict
            and labels.get(TOKEN_LABEL) == token and labels.get(PROJECT_LABEL) == project["project"]
            and labels.get(SERVICE_LABEL) == "chroma", "container ownership differs")
    mounts = row.get("mounts")
    require(type(mounts) is list and len(mounts) == 1 and type(mounts[0]) is dict
            and mounts[0].get("Type") == "volume" and mounts[0].get("Name") == volume
            and mounts[0].get("Destination") == "/data" and mounts[0].get("RW") is True,
            "container does not have exactly one writable durable /data mount")
    require(row.get("ports") == {"8000/tcp":[{"HostIp":"127.0.0.1","HostPort":str(port)}]},
            "container port is not strictly loopback-bound")
    networks = row.get("networks")
    require(type(networks) is dict and set(networks) == {project["network"]}
            and type(networks[project["network"]]) is dict,
            "Chroma network attachment differs")
    connection = networks[project["network"]]
    # Docker may expose empty NetworkID before the first start.
    require(connection.get("NetworkID") in ("", project["network_id"])
            and "chroma" in (connection.get("Aliases") or []), "Chroma service alias differs")
    running = row.get("running")
    require(type(running) is bool and row.get("status") in ("created", "exited", "running")
            and (not running or allow_running is True)
            and (not running or connection.get("NetworkID") == project["network_id"]),
            "unexpected existing container state; preserve for reconciliation")
    return ids[0], running


def _receipt(body):
    return {**body, "receipt_sha256": sha(canonical(body))}


def _publish(path, body):
    """Create a private durable journal row without replacing any entry."""
    path = Path(path)
    require(path.is_absolute() and path != ROOT and ROOT not in path.parents,
            "receipt must be an absolute path outside the checkout")
    raw = canonical(_receipt(body)) + b"\n"
    with open_directory(path.parent, private=True) as parent:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                     os.O_CLOEXEC, 0o600, dir_fd=parent)
        try:
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                require(written > 0, "receipt write stalled")
                view = view[written:]
            os.fsync(fd)
            require(stat.S_ISREG(os.fstat(fd).st_mode), "receipt identity unavailable")
            with open_directory(path.parent, private=True) as current:
                require(_dir_stamp(os.fstat(parent)) == _dir_stamp(os.fstat(current)),
                        "receipt directory replaced")
            os.fsync(parent)
        finally:
            os.close(fd)
    return sha(raw)


@contextlib.contextmanager
def _lock(directory):
    import fcntl
    with open_directory(directory, private=True) as parent:
        fd = os.open(".chroma-provision.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW |
                     os.O_CLOEXEC | os.O_NONBLOCK, 0o600, dir_fd=parent)
        try:
            st = os.fstat(fd)
            require(stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid()
                    and stat.S_IMODE(st.st_mode) == 0o600 and st.st_nlink == 1,
                    "provision lock is not private")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ProvisionDenied("another cooperating provisioner is active") from exc
            yield
        finally:
            os.close(fd)


def _port(value):
    require(type(value) is int and 1024 <= value <= 65535, "explicit unprivileged Chroma port required")
    return value


def _compose(project, volume, token, port):
    env = {"SKELETON_CHROMA_NETWORK":project["network"], "SKELETON_CHROMA_VOLUME":volume,
           "SKELETON_CHROMA_PROVISION_TOKEN":token, "SKELETON_CHROMA_DURABLE_PORT":str(port)}
    args = ("compose","--project-name",project["project"],"--file",str(COMPOSE),"--env-file","/dev/null")
    docker(*args,"config","--quiet",environment=env)
    docker(*args,"create","--no-recreate","chroma",environment=env,timeout=180)


def fresh(head, fixture_raw, fixture_pin, port, journal):
    """New resources remain preserved on any failure or interrupted attempt."""
    require(os.name == "posix", "durable provisioner requires local POSIX custody")
    _head(head)
    fixture = fixture_receipt(fixture_raw, fixture_pin, head)
    _port(port)
    journal = Path(journal)
    require(journal.is_absolute() and journal != ROOT and ROOT not in journal.parents,
            "private journal outside checkout required")
    require(journal.suffix == ".json", "new journal filename must end in .json")
    ready_path = journal.with_name(journal.stem + ".created.json")
    with _lock(journal.parent):
        require(not os.path.lexists(journal) and not os.path.lexists(ready_path),
                "existing journal; do not repeat uncertain creation")
        project = _project()
        volume = project["project"] + "_chroma_durable_data"
        _fresh_absent(project["project"],volume)
        require(_image_id() == fixture["image_id"], "local image differs from physical fixture image")
        token = uuid4().hex
        body = {"schema":SCHEMA,"source_head":head,"fixture_sha256":fixture_pin,
                "project":project,"volume":volume,"token":token,"image_id":fixture["image_id"],
                "version":fixture["version"],"port":port}
        intent_pin = _publish(journal,{**body,"state":"creation_intent"})
        _head(head)
        require(_project() == project, "engine identity changed before creation")
        _fresh_absent(project["project"],volume)
        _compose(project,volume,token,port)
        _legacy_absent()
        require(_project() == project, "engine identity changed during creation")
        volume_id = _volume(volume,project["project"],token)
        cid,running = _container(project,volume,token,fixture["image_id"],port,allow_running=False)
        require(running is False,"unexpected running Chroma after creation")
        receipt = {**body,"state":"created_not_qualified","intent_sha256":intent_pin,
                   "volume_sha256":volume_id,"container_id":cid}
        created_pin = _publish(ready_path,receipt)
        # The start path is identical to an explicit restart from verified custody.
        observation = _observe_existing(receipt,head,start=True)
        return {**observation,"created_receipt_sha256":created_pin}


def created_receipt(raw, expected_digest):
    require(type(expected_digest) is str and HEX.fullmatch(expected_digest) is not None
            and sha(raw) == expected_digest,"independent created receipt pin mismatch")
    row = _json(raw)
    require(type(row) is dict and set(row) == {
        "schema","source_head","fixture_sha256","project","volume","token",
        "image_id","version","port","state","intent_sha256","volume_sha256",
        "container_id","receipt_sha256",
    },"created receipt shape invalid")
    body = dict(row)
    claimed = body.pop("receipt_sha256")
    require(claimed == sha(canonical(body)) and body["schema"] == SCHEMA
            and body["state"] == "created_not_qualified","created receipt digest or state invalid")
    require(all(type(body[key]) is str and HEX.fullmatch(body[key]) is not None
                for key in ("fixture_sha256","intent_sha256","volume_sha256","container_id"))
            and type(body["source_head"]) is str and SHA.fullmatch(body["source_head"]) is not None
            and type(body["token"]) is str and TOKEN.fullmatch(body["token"]) is not None
            and type(body["image_id"]) is str and re.fullmatch(r"sha256:[0-9a-f]{64}",body["image_id"]) is not None
            and type(body["version"]) is str and VERSION.fullmatch(body["version"]) is not None,
            "created receipt identity invalid")
    project = body["project"]
    require(type(project) is dict and set(project) == {"project","engine_id","network","network_id"}
            and type(project["project"]) is str and PROJECT.fullmatch(project["project"]) is not None
            and project["network"] == project["project"] + "_tutolage"
            and body["volume"] == project["project"] + "_chroma_durable_data"
            and all(type(project[key]) is str and HEX.fullmatch(project[key]) is not None
                    for key in ("engine_id","network_id")),"created receipt project invalid")
    _port(body["port"])
    return body


def _observe_existing(receipt,head,*,start):
    _head(head)
    require(receipt["source_head"] == head,"created receipt belongs to another source")
    project = _project()
    require(project == receipt["project"], "engine or network identity changed; no automatic adoption")
    _legacy_absent()
    require(_image_id() == receipt["image_id"],"image identity changed")
    def check():
        require(_project() == project,"engine identity changed")
        require(_volume(receipt["volume"],project["project"],receipt["token"]) == receipt["volume_sha256"],
                "durable volume custody changed")
        cid,running = _container(project,receipt["volume"],receipt["token"],
                                 receipt["image_id"],receipt["port"],allow_running=True)
        require(cid == receipt["container_id"],"container identity changed; no recreation")
        return running
    running = check()
    if start and not running:
        docker("start",receipt["container_id"],timeout=60)
        running = check()
        require(running is True,"durable container not running")
    healthy = False
    if running:
        require(_await_ready(receipt["port"]) == receipt["version"],"Chroma version changed")
        require(check() is True,"Chroma identity changed after heartbeat")
        healthy = True
    _head(head)
    return {"schema":"skeleton.chroma.fresh-deployment-observation.v1",
            "source_head":head,"container_id":receipt["container_id"],"volume":receipt["volume"],
            "fixture_sha256":receipt["fixture_sha256"],"running":running,"heartbeat_verified":healthy,
            "mount_identity_verified":True,"legacy_migration_qualified":False,
            "application_vector_integration_qualified":False,"production_full_profile_qualified":False,
            "release_qualified":False}


def existing(head, receipt_path, receipt_pin, *, start=False):
    require(os.name == "posix","durable provisioner requires POSIX")
    path = Path(receipt_path)
    require(path.is_absolute(),"absolute receipt required")
    with _lock(path.parent):
        raw = read_private_file(path,BOUND)
        return _observe_existing(created_receipt(raw,receipt_pin),head,start=start)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-head",required=True)
    modes = parser.add_subparsers(dest="mode",required=True)
    create = modes.add_parser("fresh")
    create.add_argument("--fixture",type=Path,required=True)
    create.add_argument("--fixture-sha256",required=True)
    create.add_argument("--port",type=int,required=True)
    create.add_argument("--journal",type=Path,required=True)
    for mode in ("inspect-existing","start-existing"):
        p = modes.add_parser(mode)
        p.add_argument("--receipt",type=Path,required=True)
        p.add_argument("--receipt-sha256",required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "fresh":
            result = fresh(args.source_head,read_private_file(args.fixture,BOUND),
                           args.fixture_sha256,args.port,args.journal)
        else:
            result = existing(args.source_head,args.receipt,args.receipt_sha256,
                              start=args.mode == "start-existing")
        print(json.dumps(result,sort_keys=True))
    except Exception:
        print("Chroma provision denied or interrupted; preserve journal, containers and volumes for review.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
