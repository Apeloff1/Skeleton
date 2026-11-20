#!/usr/bin/env python3
"""Opt-in real-Docker synthetic Mongo majority/failover acceptance.

NEVER attaches or edits application containers, volumes, credentials or Mongo
data. Reuses only the immutable Mongo image ID from the already verified
offline four-image bundle. All three disposable voters have memory-only data,
no published ports, internal-only Docker networking and no hosted access.

A passing probe tests container-level election and acknowledged synthetic
writes; it DOES NOT qualify durable media, independent fault domains, shared
application writer epochs, production recovery or protected Jeeves chat.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import secrets
import subprocess
import sys
import time
from typing import Any

from scripts import local_ai_docker as host
from scripts import local_ai_offline_compose as binding

SCHEMA = "skeleton.local-ai.docker.synthetic-mongo-failover.v1"
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
CID = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"skl-mongo-q-[0-9a-f]{16}(?:-[0-2])?\Z")
MAX_OUTPUT = 32768
REPLICA = "skl_ephemeral_quorum"
DATABASE = "skl_ephemeral_qualification"


class SyntheticMongoError(host.LocalDockerError):
    """Synthetic Docker Mongo quorum admission failed closed."""


def _run(argv: list[str], *, timeout: int = 60, allow_failure: bool = False) -> str:
    if (not isinstance(argv, list) or not 2 <= len(argv) <= 64
            or any(type(item) is not str or not 0 < len(item) <= 8192
                   for item in argv)
            or argv[0] != "docker"):
        raise SyntheticMongoError("invalid bounded Docker probe command")
    try:
        result = subprocess.run(argv, capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise SyntheticMongoError("Docker synthetic probe unavailable") from None
    if len(result.stdout) > MAX_OUTPUT or len(result.stderr) > MAX_OUTPUT:
        raise SyntheticMongoError("Docker diagnostic exceeded bounded limit")
    if result.returncode != 0:
        if allow_failure:
            return ""
        raise SyntheticMongoError("Docker synthetic probe stage failed")
    return result.stdout.strip()


def _json(raw: str) -> dict[str, Any]:
    if not isinstance(raw, str) or not 0 < len(raw) < MAX_OUTPUT:
        raise SyntheticMongoError("unbounded or absent Docker inspection")
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise SyntheticMongoError("duplicate JSON field")
            out[key] = value
        return out
    def invalid(value):
        raise SyntheticMongoError("nonfinite JSON value")
    try:
        data = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)
    except (ValueError, TypeError, RecursionError):
        raise SyntheticMongoError("invalid bounded Docker JSON") from None
    if not isinstance(data, dict):
        raise SyntheticMongoError("Docker metadata must be an object")
    return data


def _local_daemon() -> None:
    if platform.system() != "Linux":
        raise SyntheticMongoError("physical synthetic quorum requires Linux Docker")
    if any(os.environ.get(name) for name in
           ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH")):
        raise SyntheticMongoError("Docker remote-context overrides are forbidden")
    context = _run(["docker", "context", "inspect", "--format",
                    "{{json .Endpoints.docker.Host}}"])
    try:
        endpoint = json.loads(context)
    except (ValueError, TypeError):
        raise SyntheticMongoError("Docker endpoint cannot be attested") from None
    if (not isinstance(endpoint, str)
            or not re.fullmatch(r"unix:///(?:var/run/docker\.sock|run/(?:user/[0-9]+/)?docker\.sock)", endpoint)):
        raise SyntheticMongoError("synthetic probe requires a local Unix Docker socket")
    if _run(["docker", "info", "--format", "{{.OSType}}"]) != "linux":
        raise SyntheticMongoError("synthetic quorum requires a Linux Docker daemon")


def _mongo(image_id: str, scope: str, idx: int) -> str:
    name = scope + "-" + str(idx)
    if not IMAGE.fullmatch(image_id) or not NAME.fullmatch(name):
        raise SyntheticMongoError("unsafe Mongo image or synthetic scope")
    cid = _run([
        "docker", "run", "-d", "--pull", "never", "--name", name,
        "--label", "skeleton.synthetic-mongo-quorum=" + scope,
        "--network", scope, "--network-alias", name,
        "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", "999:999",
        "--memory", "768m", "--cpus", "1", "--pids-limit", "192",
        "--tmpfs", "/data/db:rw,nosuid,nodev,uid=999,gid=999,mode=0700,size=402653184",
        "--tmpfs", "/data/configdb:rw,nosuid,nodev,uid=999,gid=999,mode=0700,size=16777216",
        "--tmpfs", "/tmp:rw,nosuid,nodev,uid=999,gid=999,mode=0700,size=16777216",
        "-e", "HOME=/tmp",
        image_id, "mongod", "--replSet", REPLICA,
        "--bind_ip_all", "--port", "27017",
        "--setParameter", "diagnosticDataCollectionEnabled=false",
    ], timeout=100)
    if not CID.fullmatch(cid):
        raise SyntheticMongoError("Docker did not return a unique container ID")
    return cid


def _inspect_network(scope: str) -> None:
    value = _json(_run(["docker", "network", "inspect",
                        "--format", "{{json .}}", scope]))
    if (value.get("Name") != scope or value.get("Internal") is not True
            or value.get("Attachable") is not False
            or value.get("EnableIPv6") is not False
            or value.get("Driver") != "bridge"
            or (value.get("Labels") or {}).get(
                "skeleton.synthetic-mongo-quorum") != scope):
        raise SyntheticMongoError("ephemeral Mongo network is not internal-only")


def _inspect_container(cid: str, name: str, image_id: str, scope: str,
                       *, stopped: bool = False) -> None:
    if not CID.fullmatch(cid) or not NAME.fullmatch(name):
        raise SyntheticMongoError("unknown synthetic container identity")
    value = _json(_run(["docker", "inspect", "--format", "{{json .}}", cid]))
    cfg, hostcfg, state = (value.get("Config"), value.get("HostConfig"),
                           value.get("State"))
    if not all(isinstance(x, dict) for x in (cfg, hostcfg, state)):
        raise SyntheticMongoError("synthetic container inspection incomplete")
    networks = value.get("NetworkSettings")
    networks = networks.get("Networks") if isinstance(networks, dict) else None
    if (value.get("Id") != cid or value.get("Image") != image_id
            or value.get("Name") != "/" + name
            or cfg.get("Image") != image_id
            or (cfg.get("Labels") or {}).get(
                "skeleton.synthetic-mongo-quorum") != scope
            or hostcfg.get("ReadonlyRootfs") is not True
            or "ALL" not in (hostcfg.get("CapDrop") or [])
            or "no-new-privileges" not in (hostcfg.get("SecurityOpt") or [])
            or hostcfg.get("Privileged") is not False
            or hostcfg.get("NetworkMode") != scope
            or hostcfg.get("PortBindings") not in (None, {})
            or cfg.get("ExposedPorts") not in (None, {"27017/tcp": {}})
            or not isinstance(networks, dict) or set(networks) != {scope}
            or state.get("Running") is not (not stopped)):
        raise SyntheticMongoError("physical synthetic container isolation drifted")
    tmpfs = hostcfg.get("Tmpfs") or {}
    if set(tmpfs) != {"/data/db", "/data/configdb", "/tmp"}:
        raise SyntheticMongoError("synthetic Mongo data is not memory-isolated")
    if value.get("Mounts") not in ([], None):
        raise SyntheticMongoError("synthetic container gained a persistent mount")


def _shell(cid: str, expr: str, *, allow_failure: bool = False) -> dict[str, Any]:
    if not CID.fullmatch(cid) or not isinstance(expr, str) or len(expr) > 6000:
        raise SyntheticMongoError("invalid synthetic Mongo command")
    # No passwords or application identities are ever passed to mongosh.
    snippet = 'const x=(function(){' + expr + '})();print("SKLPROBE:"+JSON.stringify(x));'
    out = _run(["docker", "exec", cid, "mongosh", "--quiet", "--norc",
                "mongodb://127.0.0.1:27017/?directConnection=true&readPreference=secondaryPreferred",
                "--eval", snippet],
               timeout=35, allow_failure=allow_failure)
    if not out and allow_failure:
        return {}
    hits = [line[len("SKLPROBE:"):] for line in out.splitlines()
            if line.startswith("SKLPROBE:")]
    if len(hits) != 1:
        if allow_failure:
            return {}
        raise SyntheticMongoError("synthetic Mongo returned no single structured receipt")
    return _json(hits[0])


def _await_mongod(nodes: dict[int, str]) -> None:
    """Wait for all real daemon listeners, not merely container Running."""
    if len(nodes) != 3 or len(set(nodes.values())) != 3:
        raise SyntheticMongoError("three distinct synthetic listeners required")
    for _ in range(40):
        if all(_shell(cid,
            'const h=db.adminCommand({hello:1});return {ok:h.ok===1};',
            allow_failure=True) == {"ok": True} for cid in nodes.values()):
            return
        time.sleep(1)
    raise SyntheticMongoError("three synthetic Mongo listeners never became ready")


def _hello(cid: str) -> dict[str, Any]:
    return _shell(cid, 'const h=db.adminCommand({hello:1});'
                  'return {ok:h.ok===1,primary:h.isWritablePrimary===true,'
                  'set:h.setName=== "' + REPLICA + '"};',
                  allow_failure=True)


def _primary(nodes: dict[int, str], *, excluded: str | None = None,
             attempts: int = 40) -> tuple[int, str]:
    for _ in range(attempts):
        leaders = [(index, cid) for index, cid in nodes.items()
                   if cid != excluded and _hello(cid) == {
                       "ok": True, "primary": True, "set": True}]
        if len(leaders) == 1:
            return leaders[0]
        if len(leaders) > 1:
            raise SyntheticMongoError("multiple synthetic Mongo primaries")
        time.sleep(1)
    raise SyntheticMongoError("synthetic Mongo election timed out")


def _majority_write(cid: str, nonce: str, step: int) -> None:
    if not re.fullmatch("[0-9a-f]{32}", nonce) or step not in (1, 2, 3):
        raise SyntheticMongoError("unsafe synthetic write identifier")
    result = _shell(
        cid, 'const d=db.getSiblingDB("' + DATABASE + '");'
        'const r=d.runCommand({insert:"proof",documents:[{_id:"' + nonce +
        '-' + str(step) + '",seq:' + str(step) + '}],'
        'writeConcern:{w:"majority",j:true,wtimeout:15000}});'
        'return {ok:r.ok===1,n:r.n===1,writeErrors:!!r.writeErrors,'
        'writeConcernError:!!r.writeConcernError};'
    )
    if result != {"ok": True, "n": True, "writeErrors": False,
                  "writeConcernError": False}:
        raise SyntheticMongoError("journaled majority write not acknowledged")



def _wait_minority_demoted(cid: str) -> None:
    """Require the sole living voter to recognize loss of quorum."""
    if not CID.fullmatch(cid):
        raise SyntheticMongoError("minority voter identity invalid")
    for _ in range(35):
        state = _hello(cid)
        if state == {"ok": True, "primary": False, "set": True}:
            return
        time.sleep(1)
    raise SyntheticMongoError("synthetic minority did not safely demote")


def _assert_minority_unacknowledged(cid: str, nonce: str) -> None:
    """A surviving minority may receive an uncommitted write; NEVER count it.

    Keep the transport alive and demand a structured real mongod response,
    distinguishing a server refusal/majority timeout from a broken probe.
    """
    if not CID.fullmatch(cid) or not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise SyntheticMongoError("minority challenge identity invalid")
    receipt = _shell(
        cid,
        'const d=db.getSiblingDB("' + DATABASE + '");'
        'try {const r=d.runCommand({insert:"proof",'
        'documents:[{_id:"' + nonce + '-minority",seq:0}],'
        'writeConcern:{w:"majority",j:true,wtimeout:3000},'
        'maxTimeMS:6000});'
        'return {server_answered:true,ok:r.ok===1,'
        'write_concern_failed:!!r.writeConcernError,'
        'n:r.n===1,'
        'code:Number.isInteger(r.code)?r.code:0};'
        '}catch(e){return {server_answered:true,ok:false,'
        'write_concern_failed:false,n:false,'
        'code:Number.isInteger(e.code)?e.code:0};}'
    )
    if (set(receipt) != {
            "server_answered", "ok", "write_concern_failed", "n", "code"
        } or receipt["server_answered"] is not True
            or type(receipt["code"]) is not int
            or not 0 <= receipt["code"] <= 1000000
            or type(receipt["ok"]) is not bool
            or type(receipt["n"]) is not bool
            or type(receipt["write_concern_failed"]) is not bool
            or (receipt["ok"] and not receipt["write_concern_failed"])
            or (not receipt["ok"] and receipt["code"] == 0)
            or (receipt["write_concern_failed"] is False and
                receipt["code"] == 0)):
        raise SyntheticMongoError(
            "minority write was acknowledged or denial could not be proven"
        )


def _restart_attested(cid: str, name: str, image_id: str, scope: str) -> None:
    """Restart only a previously attested stopped synthetic container."""
    _inspect_container(cid, name, image_id, scope, stopped=True)
    _run(["docker", "start", cid], timeout=40)
    _inspect_container(cid, name, image_id, scope)


def _majority_read(cid: str, nonce: str, step: int) -> None:
    result = _shell(
        cid, 'const d=db.getSiblingDB("' + DATABASE + '");'
        'const r=d.runCommand({find:"proof",filter:{_id:"' + nonce +
        '-' + str(step) + '"},readConcern:{level:"majority"},limit:1});'
        'const b=(r.cursor||{}).firstBatch||[];'
        'return {ok:r.ok===1,one:b.length===1,'
        'value:b.length===1&&b[0].seq===' + str(step) + '};',
        allow_failure=True,
    )
    if result != {"ok": True, "one": True, "value": True}:
        raise SyntheticMongoError("majority-committed synthetic record missing")


def _await_replay(nodes: dict[int, str], nonce: str, step: int) -> None:
    for _ in range(20):
        try:
            for cid in nodes.values():
                _majority_read(cid, nonce, step)
            return
        except SyntheticMongoError:
            time.sleep(1)
    raise SyntheticMongoError("majority-committed synthetic replay timed out")


def _initialize(cid: str, names: list[str]) -> None:
    if len(names) != 3 or any(not NAME.fullmatch(x) for x in names):
        raise SyntheticMongoError("synthetic replica set members invalid")
    members = [{"_id": n, "host": name + ":27017"}
               for n, name in enumerate(names)]
    encoded = json.dumps({"_id": REPLICA, "members": members},
                         separators=(",", ":"))
    result = _shell(cid, "const r=rs.initiate(" + encoded +
                    ");return {ok:r.ok===1};")
    if result != {"ok": True}:
        raise SyntheticMongoError("synthetic replica set initialization denied")



def _verify_policy(cid: str, *, minimum_healthy_voters: int) -> None:
    """Read real current primary, default concerns and voter health.

    This independently re-queries the *actual* disposable Mongo process
    after bootstrap, after failover, and after the restored-quorum election.
    No writes, configuration changes, or raw host metadata are returned.
    """
    if (not CID.fullmatch(cid)
            or type(minimum_healthy_voters) is not int
            or minimum_healthy_voters not in (2, 3)):
        raise SyntheticMongoError("majority policy target invalid")
    expr = (
        'const h=db.adminCommand({hello:1,maxTimeMS:5000});'
        'const s=db.adminCommand({replSetGetStatus:1,maxTimeMS:5000});'
        'const c=db.adminCommand({replSetGetConfig:1,maxTimeMS:5000});'
        'const w=db.adminCommand({getDefaultRWConcern:1,maxTimeMS:5000});'
        'const list=(c.config||{}).members||[];'
        'const health=(s.members||[]);'
        'const voters=list.filter(m=>m.votes!==0&&m.arbiterOnly!==true);'
        'return {all_ok:h.ok===1&&s.ok===1&&c.ok===1&&w.ok===1,'
        'set_match:h.setName==="' + REPLICA + '"&&'
        's.set==="' + REPLICA + '"&&(c.config||{})._id==="' +
        REPLICA + '",'
        'primary:h.isWritablePrimary===true&&s.myState===1,'
        'voters:voters.length,'
        'healthy:health.filter(m=>m.health===1&&'
        '(m.state===1||m.state===2)&&'
        'voters.some(v=>v._id===m._id)).length,'
        'majority_default:(w.defaultWriteConcern||{}).w==="majority",'
        'journal_default:(w.defaultWriteConcern||{}).j===true,'
        'members:list.length};'
    )
    for _ in range(20):
        receipt = _shell(cid, expr, allow_failure=True)
        if (set(receipt) == {
            "all_ok", "set_match", "primary", "voters", "healthy",
            "majority_default", "journal_default", "members"
        } and all(receipt.get(flag) is True for flag in (
            "all_ok", "set_match", "primary",
            "majority_default", "journal_default"
        )) and all(type(receipt.get(field)) is int for field in
                   ("voters", "healthy", "members"))
                and receipt["voters"] == receipt["members"] == 3
                and minimum_healthy_voters <= receipt["healthy"] <= 3):
            return
        time.sleep(1)
    raise SyntheticMongoError("synthetic replica policy or healthy quorum unverified")



def _set_majority_default(cid: str) -> None:
    result = _shell(cid,
        'const r=db.adminCommand({setDefaultRWConcern:1,'
        'defaultWriteConcern:{w:"majority",j:true}});'
        'return {ok:r.ok===1};')
    if result != {"ok": True}:
        raise SyntheticMongoError("synthetic majority default not admitted")


def _private_cleanup(nodes: dict[int, str], scope: str,
                     network_created: bool) -> None:
    """Remove only label-and-ID-verified ephemeral nodes, including orphans.

    A Docker run can create a container then lose the CLI acknowledgement.
    Discover those *solely* by the cryptographically random test label;
    never prune, filter by common image, or remove an unlabelled object.
    """
    if not re.fullmatch(r"skl-mongo-q-[0-9a-f]{16}", scope):
        raise SyntheticMongoError("synthetic cleanup scope invalid")
    errors = []
    discovered: set[str] = set()
    try:
        raw = _run(["docker", "ps", "--all", "--quiet", "--no-trunc",
                    "--filter", "label=skeleton.synthetic-mongo-quorum=" + scope])
        discovered = set(raw.splitlines()) if raw else set()
        if any(not CID.fullmatch(cid) for cid in discovered):
            raise SyntheticMongoError("invalid labelled synthetic container ID")
    except SyntheticMongoError:
        errors.append("discovery")
    # Keep known IDs even when Docker enumeration fails. Every candidate
    # still requires exact strong identity and label attestation before rm.
    for cid in sorted(discovered | set(nodes.values())):
        try:
            raw = _run(["docker", "inspect", "--format", "{{json .}}", cid],
                       allow_failure=True)
            if not raw:
                if cid in nodes.values():
                    errors.append("missing_known")
                continue
            doc = _json(raw)
            name = doc.get("Name")
            labels = (doc.get("Config") or {}).get("Labels") or {}
            suffix = name.removeprefix("/" + scope + "-") if isinstance(name, str) else ""
            if (doc.get("Id") != cid
                    or labels.get("skeleton.synthetic-mongo-quorum") != scope
                    or suffix not in ("0", "1", "2")
                    or (int(suffix) in nodes and nodes[int(suffix)] != cid)):
                errors.append("identity")
                continue
            _run(["docker", "rm", "--force", cid], timeout=40)
        except SyntheticMongoError:
            errors.append("container")
    # Docker network create can succeed then lose its response as well.
    # Query only the independently random scope; remove only a labelled
    # exact-name network once the three owned containers are absent.
    try:
        raw = _run(["docker", "network", "inspect", "--format",
                    "{{json .}}", scope], allow_failure=True)
        if raw:
            doc = _json(raw)
            if (doc.get("Name") != scope or doc.get("Internal") is not True
                    or (doc.get("Labels") or {}).get(
                        "skeleton.synthetic-mongo-quorum") != scope):
                errors.append("network_identity")
            else:
                _run(["docker", "network", "rm", scope], timeout=40)
        elif network_created:
            errors.append("network_missing")
    except SyntheticMongoError:
        errors.append("network")
    if errors:
        raise SyntheticMongoError(
            "synthetic Docker cleanup incomplete; inspect scoped test objects only"
        )


def qualify_synthetic_mongo(mode: str, archive: Path, overlay_directory: Path, *,
                           expected_receipt_sha256: str,
                           allow_synthetic_writes: bool = False,
                           root: Path = host.ROOT) -> dict[str, Any]:
    """Exercise REAL local Mongo election/failover on disposable tmpfs only."""
    if allow_synthetic_writes is not True:
        raise SyntheticMongoError("explicit synthetic-only write approval required")
    admitted = binding.verify_binding(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    images = admitted.get("images")
    mongo = [r.get("image_id") for r in images
             if isinstance(r, dict) and r.get("service") == "mongo"] if isinstance(images, list) else []
    if (len(mongo) != 1 or not isinstance(mongo[0], str)
            or not IMAGE.fullmatch(mongo[0])
            or admitted.get("all_four_image_ids_installed") is not True
            or admitted.get("actual_overlay_render_verified") is not True):
        raise SyntheticMongoError("verified immutable Mongo image absent")
    _local_daemon()
    scope = "skl-mongo-q-" + secrets.token_hex(8)
    nodes: dict[int, str] = {}
    created = False
    result = None
    failure = None
    try:
        network_id = _run(["docker", "network", "create", "--driver", "bridge",
                           "--internal", "--attachable=false",
                           "--label", "skeleton.synthetic-mongo-quorum=" + scope,
                           scope])
        if not re.fullmatch("[0-9a-f]{64}", network_id):
            raise SyntheticMongoError("synthetic network creation not attested")
        created = True
        _inspect_network(scope)
        for idx in range(3):
            nodes[idx] = _mongo(mongo[0], scope, idx)
            _inspect_container(nodes[idx], scope + "-" + str(idx),
                               mongo[0], scope)
        _await_mongod(nodes)
        _initialize(nodes[0], [scope + "-" + str(i) for i in range(3)])
        leader_index, leader = _primary(nodes)
        _set_majority_default(leader)
        _verify_policy(leader, minimum_healthy_voters=3)
        challenge = secrets.token_hex(16)
        _majority_write(leader, challenge, 1)
        _await_replay(nodes, challenge, 1)
        _run(["docker", "stop", "--time", "5", leader], timeout=30)
        _inspect_container(leader, scope + "-" + str(leader_index),
                           mongo[0], scope, stopped=True)
        survivors = {i: c for i, c in nodes.items() if i != leader_index}
        successor_index, successor = _primary(survivors, excluded=leader)
        if successor_index == leader_index or len(survivors) != 2:
            raise SyntheticMongoError("independent synthetic successor missing")
        _verify_policy(successor, minimum_healthy_voters=2)
        _majority_write(successor, challenge, 2)
        _await_replay(survivors, challenge, 1)
        _await_replay(survivors, challenge, 2)
        for i, cid in survivors.items():
            _inspect_container(cid, scope + "-" + str(i), mongo[0], scope)
        _inspect_network(scope)
        # Intentional QUORUM LOSS: two different stopped voters, one survivor.
        # The surviving member MUST demote and MUST NOT acknowledge w=majority.
        _run(["docker", "stop", "--time", "5", successor], timeout=30)
        _inspect_container(successor, scope + "-" + str(successor_index),
                           mongo[0], scope, stopped=True)
        minority = {i: c for i, c in survivors.items() if i != successor_index}
        if len(minority) != 1:
            raise SyntheticMongoError("synthetic quorum-loss membership invalid")
        lone_index, lone_cid = next(iter(minority.items()))
        _wait_minority_demoted(lone_cid)
        _assert_minority_unacknowledged(lone_cid, challenge)
        # Reintroduce the ORIGINAL primary, using its already-owned, exact
        # container ID. No newly constructed container or external volume.
        _restart_attested(leader, scope + "-" + str(leader_index),
                          mongo[0], scope)
        healed = {leader_index: leader, lone_index: lone_cid}
        restored_index, restored = _primary(healed)
        if restored_index not in healed:
            raise SyntheticMongoError("healed synthetic primary unavailable")
        _verify_policy(restored, minimum_healthy_voters=2)
        _await_replay(healed, challenge, 1)
        _await_replay(healed, challenge, 2)
        _majority_write(restored, challenge, 3)
        _await_replay(healed, challenge, 3)
        _inspect_container(successor, scope + "-" + str(successor_index),
                           mongo[0], scope, stopped=True)
        for i, cid in healed.items():
            _inspect_container(cid, scope + "-" + str(i), mongo[0], scope)
        _inspect_network(scope)
        result = {
            "schema": SCHEMA,
            "status": "real_synthetic_tmpfs_failover_quorum_loss_recovery_not_production_durability",
            "source_receipt_file_sha256": admitted["source_receipt_file_sha256"],
            "three_disposable_data_voters_started": True,
            "single_primary_initial_election_observed": True,
            "journal_requested_majority_write_acknowledged_before_failure": True,
            "majority_replay_verified_on_three_voters": True,
            "one_primary_stopped_intentionally": True,
            "different_primary_elected_with_two_survivors": True,
            "second_journal_requested_majority_write_acknowledged": True,
            "survivor_majority_replay_verified": True,
            "second_voter_stopped_and_single_member_left": True,
            "remaining_member_demoted_without_quorum": True,
            "synthetic_minority_majority_ack_denied": True,
            "original_voter_restarted_by_exact_container_id": True,
            "majority_reestablished_after_quorum_loss": True,
            "previously_committed_records_replayed_after_healing": True,
            "third_majority_ack_verified_after_healing": True,
            "live_config_and_majority_journal_defaults_reverified_three_times": True,
            "healed_majority_replay_verified": True,
            "no_registry_pull_requested": True,
            "no_host_ports_published": True,
            "internal_only_ephemeral_network": True,
            "only_disposable_memory_backed_database_files": True,
            "production_database_read_or_written": False,
            "production_volumes_mounted": False,
            "physical_persistent_media_durability_proven": False,
            "independent_failure_domains_proven": False,
            "production_mongo_majority_enabled": False,
            "shared_writer_epoch_or_migration_proven": False,
            "protected_chat_or_recovery_qualified": False,
            "merge_authorized": False,
            "release_authorized": False,
        }
    except Exception as exc:
        failure = exc
    try:
        _private_cleanup(nodes, scope, created)
    except SyntheticMongoError:
        raise
    if failure is not None:
        raise SyntheticMongoError("ephemeral Mongo quorum test failed closed; no production state accessed") from None
    assert result is not None
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("cpu", "nvidia", "rocm"), default="cpu")
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--overlay-directory", type=Path, required=True)
    p.add_argument("--expected-receipt-sha256", required=True)
    p.add_argument("--allow-synthetic-database-writes", action="store_true")
    args = p.parse_args(argv)
    try:
        result = qualify_synthetic_mongo(
            args.mode, args.directory, args.overlay_directory,
            expected_receipt_sha256=args.expected_receipt_sha256,
            allow_synthetic_writes=args.allow_synthetic_database_writes,
        )
    except SyntheticMongoError:
        print("synthetic Mongo quorum: DENIED (no production authorization)", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
