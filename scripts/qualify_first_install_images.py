#!/usr/bin/env python3
"""Build isolated reviewed first-install images and verify live image custody.

The builder admits only an exact Git archive, never the developer worktree,
ambient credentials, production tags or a running container. The build receipt
is an observation, not an independent signature. A separate operator approval
pins that receipt before deployment overlay publication or live verification.
No source qualification claims physical builds, inference or release.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

from stage_chroma_recovery import open_directory, read_private_file, _dir_stamp

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCHEMA = "skeleton.application.first-install-images.v1"
PLAN_SCHEMA = "skeleton.application.first-install-image-approval.v1"
OBS_SCHEMA = "skeleton.application.first-install-image-observation.v1"
DOMAIN = b"skeleton.first-install-image-approval.v1\0"
SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z", re.ASCII)
TOKEN = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}\Z", re.ASCII)
AUTHORITY = re.compile(r"[a-zA-Z0-9_.-]{1,96}\Z", re.ASCII)
ROLES = ("skeleton", "backend", "frontend")
NAMES = {role: "tutolage-" + role for role in ROLES}
CONTAINER_PORTS = {"skeleton": 8001, "backend": 8001, "frontend": 8080}
BOUND = 512 * 1024
MAX_ARCHIVE = 32 * 1024**3
MAX_MEMBER = 2 * 1024**3
MAX_FILES = 1_000_000
MAX_DEPTH = 80
CHUNK = 1024 * 1024
GIB = 1024**3
LABELS = {
    "revision": "org.opencontainers.image.revision",
    "archive": "org.skeleton.install.archive-sha256",
    "inventory": "org.skeleton.install.source-inventory-sha256",
    "candidate": "org.skeleton.install.candidate",
    "role": "org.skeleton.install.role",
}
PROJECT_LABEL = "com.docker.compose.project"
SERVICE_LABEL = "com.docker.compose.service"
NETWORK_LABEL = "com.docker.compose.network"


class ImageQualificationDenied(RuntimeError):
    """The observed source or image custody is insufficient."""


def require(condition, detail="first-install image qualification denied"):
    if condition is not True:
        raise ImageQualificationDenied(detail)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def _hex(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def _head(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def _image(value):
    return type(value) is str and IMAGE.fullmatch(value) is not None


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate evidence field")
        result[key] = value
    return result


def _constant(_):
    raise ImageQualificationDenied("nonfinite evidence field")


def decode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= BOUND, "invalid evidence size")
    try:
        return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_unique,
                          parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ImageQualificationDenied("invalid evidence JSON") from exc


def _git_env():
    return {"PATH": os.defpath, "HOME": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_OPTIONAL_LOCKS": "0",
            "LANG": "C", "LC_ALL": "C"}


def _git(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root), *args], env=_git_env(),
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                check=True, timeout=30)
        require(len(result.stdout) <= BOUND, "Git identity response too large")
        return result.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise ImageQualificationDenied("reviewed Git source unavailable") from exc


def _assert_source(root, head):
    require(_head(head), "literal exact Git commit required")
    require(_git(root, "rev-parse", "--verify", "HEAD").strip() == head.encode("ascii"),
            "reviewed checkout head changed")
    _git(root, "diff", "--quiet", "--no-ext-diff", "HEAD", "--")
    _git(root, "diff", "--cached", "--quiet", "--no-ext-diff", "HEAD", "--")


def _origin(value):
    require(type(value) is str and 1 <= len(value) <= 128, "invalid browser API origin")
    try:
        u = urlsplit(value)
        port = u.port
    except ValueError as exc:
        raise ImageQualificationDenied("invalid browser API origin") from exc
    require(u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1")
            and u.username is None and u.password is None and not u.path
            and not u.query and not u.fragment and type(port) is int and 1024 <= port <= 65535
            and value == "http://" + u.hostname + ":" + str(port),
            "browser API origin must be canonical explicit HTTP loopback")
    return value, port


def _origins(backend, engine):
    backend, backend_port = _origin(backend)
    engine, engine_port = _origin(engine)
    require(backend_port != engine_port, "backend and engine ports collide")
    return {"backend": backend, "skeleton": engine}


def _capacity(path, required):
    available = shutil.disk_usage(path).free
    require(available >= required + GIB, "private build workspace lacks reserved disk capacity")


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        require(n > 0, "partial private evidence write")
        view = view[n:]


def _archive(root, head, path, *, maximum=MAX_ARCHIVE, timeout=1800):
    """Bound both streamed archive size and wall-clock; no shell or source execution."""
    require(type(maximum) is int and 1 <= maximum <= MAX_ARCHIVE
            and type(timeout) is int and 1 <= timeout <= 1800)
    _assert_source(root, head)
    fd = None
    process = None
    h = hashlib.sha256()
    total = 0
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                     os.O_CLOEXEC, 0o600)
        process = subprocess.Popen(["git", "-C", str(root), "archive", "--format=tar", head],
                                   env=_git_env(), stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL)
        require(process.stdout is not None)
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                require(remaining > 0, "Git source archive exceeded deadline")
                require(bool(selector.select(remaining)), "Git source archive timed out")
                data = os.read(process.stdout.fileno(), CHUNK)
                if not data:
                    break
                total += len(data)
                require(total <= maximum, "Git source archive exceeds capacity")
                _capacity(path.parent, len(data))
                h.update(data)
                _write_all(fd, data)
        remaining = deadline - time.monotonic()
        require(remaining > 0 and process.wait(timeout=remaining) == 0 and total > 0,
                "Git source archive unsuccessful")
        os.fsync(fd)
        _assert_source(root, head)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ImageQualificationDenied("bounded Git source archive failed") from exc
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout is not None:
                process.stdout.close()
        if fd is not None:
            os.close(fd)
    return {"sha256": h.hexdigest(), "bytes": total}


def _relative(name):
    require(type(name) is str and 0 < len(name.encode("utf-8")) <= 4096
            and "\\" not in name and not name.startswith("/")
            and all(32 <= ord(c) != 127 for c in name), "unsafe archive member path")
    raw = name[:-1] if name.endswith("/") else name
    parts = raw.split("/")
    require(0 < len(parts) <= MAX_DEPTH and all(
        part not in ("", ".", "..") and len(part.encode("utf-8")) <= 255 for part in parts),
        "unsafe archive member component")
    require(not any(part.lower() == ".git" or
                    (part.lower().startswith(".env") and part.lower() != ".env.example")
                    for part in parts), "private configuration or Git metadata in source archive")
    return PurePosixPath(*parts)


def _parents(root, relative):
    """Only fresh ordinary directories under our private extraction root."""
    current = root
    for part in relative.parts:
        current = current / part
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        s = current.lstat()
        require(stat.S_ISDIR(s.st_mode) and not current.is_symlink() and s.st_uid == os.geteuid(),
                "unsafe source extraction directory")
    return current


def _inventory_digest(rows):
    h = hashlib.sha256(b"skeleton.first-install-source-inventory.v1\0")
    for row in sorted(rows, key=lambda item:item[0]):
        h.update(canonical(row))
        h.update(b"\n")
    return h.hexdigest()


def _extract(archive, root):
    """No symlinks, special files, duplicate members, overwrite or path escape."""
    root.mkdir(mode=0o700)
    members = set()
    rows = []
    total = 0
    try:
        with tarfile.open(archive, mode="r:") as tf:
            for member in tf:
                relative = _relative(member.name)
                key = relative.as_posix()
                require(key not in members and len(members) < MAX_FILES,
                        "duplicate or excessive source archive inventory")
                members.add(key)
                require(member.isdir() or member.isfile(), "nonregular source archive member")
                if member.isdir():
                    _parents(root, relative)
                    continue
                require(0 <= member.size <= MAX_MEMBER and total + member.size <= MAX_ARCHIVE,
                        "source member exceeds reviewed capacity")
                total += member.size
                _capacity(root, member.size)
                parent = _parents(root, relative.parent)
                target = parent / relative.name
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
                h = hashlib.sha256()
                count = 0
                mode = 0o500 if member.mode & 0o111 else 0o400
                try:
                    stream = tf.extractfile(member)
                    require(stream is not None, "source archive data missing")
                    with stream:
                        while True:
                            data = stream.read(CHUNK)
                            if not data:
                                break
                            count += len(data)
                            require(count <= member.size, "source member exceeds declared size")
                            h.update(data)
                            _write_all(fd, data)
                    require(count == member.size, "truncated source member")
                    os.fchmod(fd, mode)
                    os.fsync(fd)
                finally:
                    os.close(fd)
                rows.append((key, count, h.hexdigest(), mode))
    except (OSError, tarfile.TarError, UnicodeError) as exc:
        raise ImageQualificationDenied("safe source extraction failed") from exc
    require(bool(rows), "empty source archive")
    required = {"Dockerfile", "backend/Dockerfile", "frontend/Dockerfile", ".dockerignore",
                "frontend/.dockerignore", "pyproject.toml", "backend/requirements.txt",
                "frontend/package.json", "frontend/yarn.lock"}
    require(required.issubset({row[0] for row in rows}), "required image build inputs unavailable")
    return {"sha256": _inventory_digest(rows), "files": len(rows), "bytes": total}


def _stamp(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def _file_identity(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and before.st_size <= MAX_MEMBER and before.st_uid == os.geteuid(),
                "source member not an ordinary bounded owned file")
        h = hashlib.sha256()
        total = 0
        while True:
            data = os.read(fd,CHUNK)
            if not data:
                break
            total += len(data)
            require(total <= before.st_size, "source member changed while hashing")
            h.update(data)
        require(total == before.st_size and _stamp(before) == _stamp(os.fstat(fd))
                and _stamp(before) == _stamp(path.lstat()), "source member identity changed")
        return total,h.hexdigest(),stat.S_IMODE(before.st_mode)
    finally:
        os.close(fd)


def _inventory(root):
    rows = []
    total = 0
    entries = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        for child in dirs:
            path = Path(directory)/child
            require(stat.S_ISDIR(path.lstat().st_mode) and not path.is_symlink(),
                    "extracted source directory replaced")
        for name in names:
            path = Path(directory)/name
            relative = _relative(path.relative_to(root).as_posix())
            size, digest, mode = _file_identity(path)
            total += size
            require(total <= MAX_ARCHIVE and len(rows) < MAX_FILES, "extracted source inventory exceeded")
            rows.append((relative.as_posix(),size,digest,mode))
        entries += len(dirs)+len(names)
        require(entries <= MAX_FILES, "extracted source entry capacity exceeded")
    return {"sha256":_inventory_digest(rows),"files":len(rows),"bytes":total}


def _archive_recheck(path, expected):
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size==expected["bytes"]
                and before.st_nlink==1 and before.st_uid==os.geteuid(),"source archive identity changed")
        h=hashlib.sha256()
        count=0
        while True:
            raw=os.read(fd,CHUNK)
            if not raw:
                break
            count+=len(raw)
            require(count<=before.st_size,"source archive grew during verification")
            h.update(raw)
        require(count==before.st_size and h.hexdigest()==expected["sha256"]
                and _stamp(before)==_stamp(os.fstat(fd))==_stamp(path.lstat()),
                "source archive digest changed")
    finally:
        os.close(fd)


def _docker_config(path):
    path.mkdir(mode=0o700)
    # Explicit empty configuration: no registry auth, credential helper,
    # environment proxy injection or ambient Docker context.
    (path/"config.json").write_text("{}\n",encoding="ascii")
    return path


def _docker(config, *args, timeout=30):
    env={"PATH":os.defpath,"HOME":str(config),"DOCKER_CONFIG":str(config),
         "DOCKER_BUILDKIT":"1","LANG":"C","LC_ALL":"C"}
    with tempfile.TemporaryFile() as out:
        try:
            done = subprocess.run(["docker","--host","unix:///var/run/docker.sock",*args],
                                  env=env,cwd=ROOT,stdout=out,stderr=subprocess.DEVNULL,
                                  timeout=timeout,check=False)
        except (OSError,subprocess.SubprocessError) as exc:
            raise ImageQualificationDenied("bounded Docker operation unavailable") from exc
        out.seek(0)
        data=out.read(BOUND+1)
        require(done.returncode==0 and len(data)<=BOUND,"Docker operation failed or exceeded bound")
        return data


def _tag(head,token,role):
    require(_head(head) and type(token) is str and TOKEN.fullmatch(token) is not None and role in ROLES)
    return "skeleton-first-install-candidate-"+role+":"+head[:16]+"-"+token


def _labels(head,archive,inventory,token,role):
    return {LABELS["revision"]:head,LABELS["archive"]:archive,
            LABELS["inventory"]:inventory,LABELS["candidate"]:token,LABELS["role"]:role}


def _inspect(config,category,key,template):
    value=decode(_docker(config,category,"inspect","--format",template,key))
    require(type(value) is dict,"Docker identity object unavailable")
    return value


def _inspect_image(config,key,expected_labels,expected_id=None):
    row=_inspect(config,"image",key,
        '{"id":{{json .Id}},"labels":{{json .Config.Labels}},'
        '"os":{{json .Os}},"architecture":{{json .Architecture}}}')
    require(_image(row.get("id")) and (expected_id is None or row["id"]==expected_id)
            and row.get("os")=="linux" and row.get("architecture") in ("amd64","arm64")
            and type(row.get("labels")) is dict
            and all(row["labels"].get(k)==v for k,v in expected_labels.items()),
            "image build labels or platform identity differ")
    return {"image_id":row["id"],"os":row["os"],"architecture":row["architecture"]}


def _build_args(role,context,head,token,archive,inventory,origins,iidfile):
    labels=_labels(head,archive,inventory,token,role)
    command=["build","--tag",_tag(head,token,role),"--iidfile",str(iidfile),
             "--network","default"]
    for key,value in sorted(labels.items()):
        command+=["--label",key+"="+value]
    if role=="skeleton":
        command+=["--file",str(context/"Dockerfile"),str(context)]
    elif role=="backend":
        command+=["--file",str(context/"backend/Dockerfile"),"--target","production",
                  "--build-arg","VCS_REF="+head,str(context)]
    elif role=="frontend":
        command+=["--file",str(context/"frontend/Dockerfile"),"--target","production",
                  "--build-arg","VCS_REF="+head,
                  "--build-arg","EXPO_PUBLIC_BACKEND_URL="+origins["backend"],
                  "--build-arg","EXPO_PUBLIC_SKELETON_URL="+origins["skeleton"],
                  str(context/"frontend")]
    else:
        raise ImageQualificationDenied("unknown build service")
    return tuple(command)


def _build_image(config,role,context,head,token,archive,inventory,origins,iidfile):
    tag=_tag(head,token,role)
    existing=_docker(config,"image","ls","--filter","reference="+tag,"--format","{{.ID}}")
    require(not existing.strip(),"unique candidate tag already exists")
    expected=_labels(head,archive,inventory,token,role)
    # Build output may be arbitrarily verbose. Unlike a small inspect packet,
    # it is discarded rather than retained; no failed build logs enter a receipt.
    env={"PATH":os.defpath,"HOME":str(config),"DOCKER_CONFIG":str(config),
         "DOCKER_BUILDKIT":"1","LANG":"C","LC_ALL":"C"}
    try:
        done=subprocess.run(["docker","--host","unix:///var/run/docker.sock",
                             *_build_args(role,context,head,token,archive,inventory,origins,iidfile)],
                            cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                            timeout=3600,check=False)
        require(done.returncode==0,"candidate image build unsuccessful")
    except (OSError,subprocess.SubprocessError) as exc:
        raise ImageQualificationDenied("candidate image build failed or timed out") from exc
    image_id=iidfile.read_text(encoding="ascii").strip()
    require(_image(image_id),"build image-ID receipt invalid")
    row=_inspect_image(config,tag,expected,image_id)
    require(_inspect_image(config,image_id,expected,image_id)==row,"tag and built image differ")
    return {"role":role,"tag":tag,**row}


def _receipt(schema,body):
    result={"schema":schema,**body}
    return {**result,"receipt_sha256":sha(canonical(result))}


def _publish(path,payload):
    require(Path(path).is_absolute(),"private absolute receipt destination required")
    path=Path(path)
    require(path!=ROOT and ROOT not in path.parents,"evidence must be outside checkout")
    data=canonical(payload)+b"\n"
    require(len(data)<=BOUND,"evidence exceeds bound")
    with open_directory(path.parent,private=True) as parent:
        fd=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
        try:
            _write_all(fd,data)
            os.fsync(fd)
            with open_directory(path.parent,private=True) as observed:
                require(_dir_stamp(os.fstat(parent))==_dir_stamp(os.fstat(observed)),
                        "evidence destination parent replaced")
            os.fsync(parent)
        finally:
            os.close(fd)
    return sha(data)


def build(head,work_parent,receipt,backend_origin,engine_origin):
    """Explicit operator build. No container create/start, no production-tag changes."""
    require(os.name=="posix","reviewed archive builder requires POSIX")
    _assert_source(ROOT,head)
    origins=_origins(backend_origin,engine_origin)
    work_parent=Path(work_parent)
    receipt=Path(receipt)
    require(work_parent.is_absolute() and work_parent!=ROOT and ROOT not in work_parent.parents
            and receipt.is_absolute() and receipt!=ROOT and ROOT not in receipt.parents,
            "private workspace and receipt must be outside checkout")
    with open_directory(work_parent,private=True),open_directory(receipt.parent,private=True):
        require(not os.path.lexists(receipt),"build receipt already exists")
        token=uuid4().hex
        work=Path(tempfile.mkdtemp(prefix="candidate-"+token+"-",dir=work_parent))
        # Keep isolated source/build evidence after interruption; no automatic
        # removal of images, workspace, archive or ambiguous candidate tags.
        archive=work/"source.tar"
        context=work/"context"
        config=_docker_config(work/"docker-config")
        intent=work/"intent.json"
        _publish(intent,{"schema":"skeleton.application.install-image-intent.v1","source_head":head,
                        "candidate":token,"origins":origins,"tags":[_tag(head,token,r) for r in ROLES]})
        a=_archive(ROOT,head,archive)
        source=_extract(archive,context)
        require(_inventory(context)==source,"extracted source differs from archive")
        rows=[]
        for role in ROLES:
            _assert_source(ROOT,head)
            require(_inventory(context)==source,"private source changed before candidate build")
            row=_build_image(config,role,context,head,token,a["sha256"],source["sha256"],
                             origins,work/(role+".iid"))
            require(_inventory(context)==source,"private source changed during candidate build")
            rows.append(row)
            _publish(work/(role+".json"),row)
        _archive_recheck(archive,a)
        _assert_source(ROOT,head)
        require(len({row["image_id"] for row in rows})==3 and
                len({(row["os"],row["architecture"]) for row in rows})==1,
                "candidate image identities or platforms are inconsistent")
        result=_receipt(BUILD_SCHEMA,{"source_head":head,"candidate":token,"archive":a,
            "source_inventory":source,"origins":origins,"images":rows,
            "build_mode":"isolated_tracked_git_archive_production","ambient_credentials_forwarded":False,
            "independent_builder_approved":False,"hermetic_reproducibility_qualified":False,
            "runtime_qualified":False,"release_qualified":False})
        _publish(receipt,result)
        return result


def _body(raw,schema):
    row=decode(raw)
    require(type(row) is dict and row.get("schema")==schema and _hex(row.get("receipt_sha256")),
            "invalid receipt schema or digest")
    body=dict(row)
    claimed=body.pop("receipt_sha256")
    require(sha(canonical(body))==claimed,"receipt body digest differs")
    return body


def validate_build(raw,head):
    row=_body(raw,BUILD_SCHEMA)
    require(set(row)=={"schema","source_head","candidate","archive","source_inventory","origins","images",
                       "build_mode","ambient_credentials_forwarded","independent_builder_approved",
                       "hermetic_reproducibility_qualified","runtime_qualified","release_qualified"}
            and row["source_head"]==head and _head(head)
            and type(row["candidate"]) is str and TOKEN.fullmatch(row["candidate"]) is not None
            and row["build_mode"]=="isolated_tracked_git_archive_production"
            and all(row[key] is False for key in ("ambient_credentials_forwarded","independent_builder_approved",
                    "hermetic_reproducibility_qualified","runtime_qualified","release_qualified")),
            "build receipt scope differs")
    archive=row["archive"]
    source=row["source_inventory"]
    require(type(archive) is dict and set(archive)=={"sha256","bytes"} and _hex(archive["sha256"])
            and type(archive["bytes"]) is int and 0<archive["bytes"]<=MAX_ARCHIVE
            and type(source) is dict and set(source)=={"sha256","files","bytes"} and _hex(source["sha256"])
            and type(source["files"]) is int and 0<source["files"]<=MAX_FILES
            and type(source["bytes"]) is int and 0<source["bytes"]<=archive["bytes"],
            "build source evidence invalid")
    origins=row["origins"]
    require(type(origins) is dict and set(origins)=={"backend","skeleton"}
            and _origins(origins["backend"],origins["skeleton"])==origins,"build browser origins invalid")
    images=row["images"]
    require(type(images) is list and len(images)==len(ROLES),"incomplete candidate image inventory")
    for role,image in zip(ROLES,images,strict=True):
        require(type(image) is dict and set(image)=={"role","tag","image_id","os","architecture"}
                and image["role"]==role and image["tag"]==_tag(head,row["candidate"],role)
                and _image(image["image_id"]) and image["os"]=="linux"
                and image["architecture"] in ("amd64","arm64"),"candidate image identity invalid")
    require(len({r["image_id"] for r in images})==3 and len({r["architecture"] for r in images})==1,
            "duplicate image or mixed platform evidence")
    return row


@dataclass(frozen=True,slots=True)
class ApprovedBuild:
    receipt: dict
    receipt_sha256: str
    plan: dict
    authority_key_sha256: str

    def recheck(self,now=None):
        actual=int(time.time()) if now is None else now
        require(type(actual) is int and self.plan["issued_at"]<=actual<self.plan["expires_at"],
                "independent image approval expired")


def approve(receipt_raw,plan_raw,signature,key,*,head,authority,project,now=None):
    """Independent signature binds the precise build observation and scope."""
    row=validate_build(receipt_raw,head)
    plan=decode(plan_raw)
    actual=int(time.time()) if now is None else now
    require(type(plan) is dict and set(plan)=={"schema","source_head","build_receipt_sha256",
            "authority_id","project","review_evidence_sha256","issued_at","expires_at"}
            and plan["schema"]==PLAN_SCHEMA and plan["source_head"]==head
            and plan["build_receipt_sha256"]==sha(receipt_raw)
            and type(authority) is str and AUTHORITY.fullmatch(authority) is not None
            and plan["authority_id"]==authority and type(project) is str and PROJECT.fullmatch(project) is not None
            and plan["project"]==project and _hex(plan["review_evidence_sha256"])
            and plan["review_evidence_sha256"]!="0"*64
            and type(plan["issued_at"]) is int and type(plan["expires_at"]) is int
            and type(actual) is int and 0<plan["issued_at"]<=actual<plan["expires_at"]
            and plan["expires_at"]-plan["issued_at"]<=3600 and type(key) is bytes and len(key)==32
            and type(signature) is bytes and len(signature)==64,"independent image approval invalid")
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(signature,DOMAIN+canonical(plan))
    except (InvalidSignature,ValueError,TypeError) as exc:
        raise ImageQualificationDenied("independent build signature denied") from exc
    return ApprovedBuild(row,sha(receipt_raw),plan,sha(key))


def _verify_images(config,approved):
    approved.recheck()
    r=approved.receipt
    for image in r["images"]:
        labels=_labels(r["source_head"],r["archive"]["sha256"],r["source_inventory"]["sha256"],
                       r["candidate"],image["role"])
        expected={k:image[k] for k in ("image_id","os","architecture")}
        require(_inspect_image(config,image["tag"],labels,image["image_id"])==expected and
                _inspect_image(config,image["image_id"],labels,image["image_id"])==expected,
                "reviewed candidate image no longer available")
    approved.recheck()


def _ports(approved,frontend_port):
    require(type(frontend_port) is int and 1024<=frontend_port<=65535,"explicit frontend host port required")
    values={"frontend":frontend_port,"backend":_origin(approved.receipt["origins"]["backend"])[1],
            "skeleton":_origin(approved.receipt["origins"]["skeleton"])[1]}
    require(len(set(values.values()))==3,"first-install host ports collide")
    return values


def prepare(approved,output,frontend_port):
    """Emit a production Compose override; never start or replace containers."""
    _assert_source(ROOT,approved.receipt["source_head"])
    ports=_ports(approved,frontend_port)
    with tempfile.TemporaryDirectory(prefix="skeleton-image-review-") as tmp:
        config=_docker_config(Path(tmp)/"docker")
        _verify_images(config,approved)
        # Compose's base build mappings remain present. The operator MUST
        # use --no-build, and the observer checks resulting immutable IDs.
        overlay={"services":{r["role"]:{"image":r["tag"],"pull_policy":"never"}
                             for r in approved.receipt["images"]}}
        # Override actual loopback publication with Compose's explicit reset
        # syntax, rather than silently appending a second port binding.
        # JSON cannot encode !override tags; keep ports in the canonical
        # production environment and validate exact bindings after startup.
        approved.recheck()
        pin=_publish(output,overlay)
        return {"overlay_sha256":pin,"reviewed_build_receipt_sha256":approved.receipt_sha256,
                "project":approved.plan["project"],"required_host_ports":ports,
                "requires_no_build":True,"runtime_qualified":False,"release_qualified":False}


def _ids(config,*filters):
    raw=_docker(config,"ps","-a","--no-trunc",
                *[arg for value in filters for arg in ("--filter",value)],"--format","{{.ID}}")
    try:
        result=raw.decode("ascii").splitlines()
    except UnicodeError as exc:
        raise ImageQualificationDenied("invalid container identity inventory") from exc
    require(len(set(result))==len(result) and all(_hex(row) for row in result),"invalid container identity list")
    return result


def _running_container(config,approved,image,ports):
    role=image["role"]
    project=approved.plan["project"]
    name=NAMES[role]
    ids=_ids(config,"name=^/"+name+"$")
    require(len(ids)==1 and _ids(config,"label="+PROJECT_LABEL+"="+project,
                                "label="+SERVICE_LABEL+"="+role)==ids,"canonical running service ambiguous")
    row=_inspect(config,"container",ids[0],
        '{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Image}},'
        '"labels":{{json .Config.Labels}},"running":{{json .State.Running}},'
        '"status":{{json .State.Status}},"ports":{{json .HostConfig.PortBindings}},'
        '"networks":{{json .NetworkSettings.Networks}},"mounts":{{json .Mounts}}}')
    require(row.get("id")==ids[0] and row.get("name")=="/"+name and row.get("image")==image["image_id"]
            and row.get("running") is True and row.get("status")=="running"
            and type(row.get("labels")) is dict and row["labels"].get(PROJECT_LABEL)==project
            and row["labels"].get(SERVICE_LABEL)==role,"actual running container image/owner differs")
    require(row.get("ports")=={str(CONTAINER_PORTS[role])+"/tcp":[
        {"HostIp":"127.0.0.1","HostPort":str(ports[role])}]},"running service port scope differs")
    network=project+"_tutolage"
    networks=row.get("networks")
    require(type(networks) is dict and set(networks)=={network}
            and type(networks[network]) is dict and _hex(networks[network].get("NetworkID")),
            "network ownership unavailable")
    mounts=row.get("mounts")
    require(type(mounts) is list and all(type(mount) is dict for mount in mounts),
            "runtime mount inventory unavailable")
    permitted={
        "skeleton":{"/app/data":("volume",True,project+"_skeleton_data"),
                    "/app/local-ai":("bind",False,None)},
        "backend":{"/app/data":("volume",True,project+"_backend_data")},
        "frontend":{},
    }[role]
    received={}
    for mount in mounts:
        dest=mount.get("Destination")
        require(dest in permitted and dest not in received,"runtime source or unexpected mount shadows image")
        kind,writable,volume=permitted[dest]
        require(mount.get("Type")==kind and mount.get("RW") is writable
                and (volume is None or mount.get("Name")==volume),"runtime mount authority differs")
        received[dest]={"type":kind,"writable":writable,"named_volume":volume}
    require(set(received)==set(permitted),"required persistent runtime mount missing")
    return {"role":role,"container_id":ids[0],"image_id":image["image_id"],
            "network_id":networks[network]["NetworkID"],"mounts":received,"port":ports[role]}


def _observe(config,approved,ports):
    _verify_images(config,approved)
    values=[_running_container(config,approved,image,ports) for image in approved.receipt["images"]]
    network_id=values[0]["network_id"]
    require(all(r["network_id"]==network_id for r in values),"services do not share canonical network")
    project=approved.plan["project"]
    row=_inspect(config,"network",network_id,
        '{"id":{{json .Id}},"name":{{json .Name}},"driver":{{json .Driver}},'
        '"scope":{{json .Scope}},"labels":{{json .Labels}},"containers":{{json .Containers}}}')
    require(row.get("id")==network_id and row.get("name")==project+"_tutolage"
            and row.get("driver")=="bridge" and row.get("scope")=="local"
            and type(row.get("labels")) is dict and row["labels"].get(PROJECT_LABEL)==project
            and row["labels"].get(NETWORK_LABEL)=="tutolage"
            and type(row.get("containers")) is dict
            and all(r["container_id"] in row["containers"] for r in values),
            "actual canonical network ownership differs")
    approved.recheck()
    return values


def observe_running(approved,frontend_port):
    """Two direct identity observations; never claim application/inference health."""
    head=approved.receipt["source_head"]
    _assert_source(ROOT,head)
    ports=_ports(approved,frontend_port)
    with tempfile.TemporaryDirectory(prefix="skeleton-image-observation-") as tmp:
        config=_docker_config(Path(tmp)/"docker")
        first=_observe(config,approved,ports)
        _assert_source(ROOT,head)
        time.sleep(1.1)
        second=_observe(config,approved,ports)
        require(second==first,"running image or container identity changed between observations")
        _assert_source(ROOT,head)
        approved.recheck()
    return _receipt(OBS_SCHEMA,{"source_head":head,"project":approved.plan["project"],
        "build_receipt_sha256":approved.receipt_sha256,"authority_key_sha256":approved.authority_key_sha256,
        "approval_sha256":sha(DOMAIN+canonical(approved.plan)),
        "observed_services":second,"passes":2,"running_image_ids_verified":True,
        "source_mount_shadowing_excluded":True,"independent_build_receipt_approved":True,
        "service_health_qualified":False,"inference_qualified":False,
        "hermetic_reproducibility_qualified":False,"device_qualified":False,"release_qualified":False})


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-head",required=True)
    modes=parser.add_subparsers(dest="mode",required=True)
    builder=modes.add_parser("build")
    builder.add_argument("--work-parent",type=Path,required=True)
    builder.add_argument("--receipt",type=Path,required=True)
    builder.add_argument("--backend-origin",required=True)
    builder.add_argument("--engine-origin",required=True)
    for mode in ("prepare","observe"):
        p=modes.add_parser(mode)
        p.add_argument("--build-receipt",type=Path,required=True)
        p.add_argument("--plan",type=Path,required=True)
        p.add_argument("--signature",type=Path,required=True)
        p.add_argument("--public-key",type=Path,required=True)
        p.add_argument("--authority",required=True)
        p.add_argument("--project",required=True)
        p.add_argument("--frontend-port",type=int,required=True)
        if mode=="prepare":
            p.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.mode=="build":
            result=build(args.source_head,args.work_parent,args.receipt,args.backend_origin,args.engine_origin)
        else:
            approved=approve(read_private_file(args.build_receipt,BOUND),read_private_file(args.plan,BOUND),
                read_private_file(args.signature,64),read_private_file(args.public_key,32),
                head=args.source_head,authority=args.authority,project=args.project)
            result=(prepare(approved,args.output,args.frontend_port) if args.mode=="prepare"
                    else observe_running(approved,args.frontend_port))
        print(json.dumps(result,sort_keys=True))
        return 0
    except Exception:
        print("First-install image qualification denied; preserve all build evidence and existing resources.",
              file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
