"""Persistent, opt-in crash recovery for cooperating checkout installers.

Append-only, redacted phase journal with exact source, private configuration,
stable root and bounded operation identity. A resume re-runs the existing
idempotent installer, never skips old steps, rotates credentials, removes
containers, restores volumes, or silently resolves an uncertain mutation.
This is local POSIX custody, not cross-host exclusion or device evidence.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from uuid import uuid4

from skeleton.app.setup_runtime import runtime_source_fingerprint

SCHEMA="skeleton.application.install-session-event.v1"
_REPORT="skeleton.application.install-session-observation.v1"
_ID=re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z",re.ASCII)
_SHA=re.compile(r"[0-9a-f]{40}\Z",re.ASCII)
_HEX=re.compile(r"[0-9a-f]{64}\Z",re.ASCII)
_MAX_EVENTS=4096
_MAX_ENTRIES=65536
_MAX_EVENT=8192
_OPTIONS=frozenset(("start","full","production","hot","install_python",
                    "bundled_runtime","require_strict","require_protected","require_ai"))
_PHASES=frozenset(("arguments","preload","setup-runtime","configuration-note","python-install",
                   "runtime-source-epoch","runtime-preflight","runtime-manifest","compose-config",
                   "public-endpoints","start","setup-ui-recovery","setup-ui-availability",
                   "readiness","critical-api-routes","strict-live-qualification","chroma-persistence",
                   "qualification-input","qualification-source","install-session"))
_INTENTS=frozenset(("setup-runtime","python-install","compose-config","start","setup-ui-recovery"))
_STATES=frozenset(("OPEN","ATTEMPT_BEGIN","PHASE_INTENT","PHASE_RESULT","ATTEMPT_END"))
_OUTCOMES=frozenset(("passed","blocked","interrupted"))


class InstallSessionDenied(RuntimeError):
    pass


def require(value,detail="install session custody unavailable"):
    if value is not True:
        raise InstallSessionDenied(detail)


def _canon(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _hex(value):
    return type(value) is str and _HEX.fullmatch(value) is not None


def _valid_id(value):
    return type(value) is str and _ID.fullmatch(value) is not None


def _snapshot(root):
    # Absence is distinct from unverifiable or unsafe configuration.
    path=root/".env"
    if not path.exists() and not path.is_symlink():
        return None
    try:
        result=runtime_source_fingerprint(root)
        require(_hex(result),"private runtime source fingerprint unavailable")
        return result
    except (OSError,ValueError,UnicodeError):
        raise InstallSessionDenied("private runtime source unsafe; preserve original") from None


def _root_identity(root):
    require(isinstance(root,Path) and root.is_absolute() and ".." not in root.parts)
    before=root.lstat()
    require(stat.S_ISDIR(before.st_mode) and not root.is_symlink())
    # Root identity is independent of mutable .env or source-tree content.
    return _sha(_canon({"path":str(root),"dev":before.st_dev,"ino":before.st_ino}))


def _current_source(root,head):
    from skeleton.app.strict_install_qualification import assert_source_head,QualificationDenied
    try:
        assert_source_head(root,head)
    except QualificationDenied:
        raise InstallSessionDenied("reviewed checkout identity unavailable") from None


def _stamp(info):
    return info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns


def _dir_identity(fd):
    info=os.fstat(fd)
    return info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode)


@contextmanager
def _private_directory(path):
    require(os.name=="posix" and hasattr(os,"O_NOFOLLOW"),"persistent install recovery requires POSIX custody")
    require(isinstance(path,Path) and path.is_absolute() and path!=Path("/") and ".." not in path.parts)
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
    fd=os.open("/",flags)
    try:
        for index,part in enumerate(path.parts[1:]):
            child=os.open(part,flags,dir_fd=fd)
            os.close(fd)
            fd=child
            info=os.fstat(fd)
            if index==len(path.parts)-2:
                require(info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o700,
                        "install session directory must be private mode 0700")
            else:
                require(info.st_uid in (0,os.geteuid()) and (not info.st_mode&0o022 or
                        (info.st_uid==0 and info.st_mode&stat.S_ISVTX)),
                        "untrusted install session ancestor")
        yield fd
    finally:
        os.close(fd)


def _same_directory(path,fd):
    with _private_directory(path) as actual:
        require(_dir_identity(actual)==_dir_identity(fd),"install custody directory changed")


def _regular_named(handle,fd,name):
    info=os.fstat(handle)
    named=os.stat(name,dir_fd=fd,follow_symlinks=False)
    require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid()
            and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1
            and _stamp(info)==_stamp(named),"install custody record identity invalid")
    return info


def _read(fd,name):
    handle=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd)
    try:
        before=_regular_named(handle,fd,name)
        require(0<before.st_size<=_MAX_EVENT,"install custody record size invalid")
        raw=bytearray()
        while len(raw)<before.st_size:
            chunk=os.read(handle,before.st_size-len(raw))
            require(bool(chunk),"install custody record truncated")
            raw.extend(chunk)
        require(not os.read(handle,1) and _stamp(before)==_stamp(_regular_named(handle,fd,name)),
                "install custody record changed")
        return bytes(raw)
    finally:
        os.close(handle)


def _unique(pairs):
    row={}
    for key,value in pairs:
        require(key not in row,"duplicate install journal field")
        row[key]=value
    return row


def _constant(_):
    raise InstallSessionDenied("nonfinite install journal value")


def _options(value):
    require(type(value) is dict and set(value)==_OPTIONS
            and all(type(v) is bool for v in value.values()),"invalid install operation identity")
    return dict(value)


def _event_digest(row):
    return _sha(b"skeleton.install-session-chain.v1\0"+_canon(row))


def _parse(raw,*,session_id,sequence):
    try:
        row=json.loads(raw.decode("ascii"),object_pairs_hook=_unique,parse_constant=_constant)
        require(type(row) is dict and set(row)=={"schema","session_id","sequence","kind","previous_sha256","data"}
                and raw==_canon(row)+b"\n" and row["schema"]==SCHEMA and row["session_id"]==session_id
                and type(row["sequence"]) is int and row["sequence"]==sequence
                and row["kind"] in _STATES and type(row["data"]) is dict)
        require(row["previous_sha256"] is None if sequence==1 else _hex(row["previous_sha256"]))
        require(_validate_data(row["kind"],row["data"]))
        return row
    except InstallSessionDenied:
        raise
    except (ValueError,TypeError,UnicodeError,RecursionError):
        raise InstallSessionDenied("invalid install journal data") from None


def _validate_data(kind,data):
    if kind=="OPEN":
        return (set(data)=={"root_sha256","source_head","options","initial_configuration"}
                and _hex(data["root_sha256"]) and type(data["source_head"]) is str
                and _SHA.fullmatch(data["source_head"]) is not None
                and _options(data["options"])==data["options"]
                and (data["initial_configuration"] is None or _hex(data["initial_configuration"])))
    if kind=="ATTEMPT_BEGIN":
        return set(data)=={"attempt"} and type(data["attempt"]) is int and 1<=data["attempt"]<=_MAX_EVENTS
    if kind=="PHASE_INTENT":
        return set(data)=={"name"} and data["name"] in _INTENTS
    if kind=="PHASE_RESULT":
        fields={"name","ok","required","configuration_after"}
        return (set(data)==fields and data["name"] in _PHASES
                and type(data["ok"]) is bool and type(data["required"]) is bool
                and (data["configuration_after"] is None or _hex(data["configuration_after"]))
                and (data["name"]=="setup-runtime" and data["ok"]
                    or data["configuration_after"] is None))
    if kind=="ATTEMPT_END":
        return set(data)=={"outcome"} and data["outcome"] in _OUTCOMES
    return False


def _filename(session_id,sequence):
    return f"install-{session_id}-{sequence:06d}.json"


def _scan(fd,session_id):
    require(_valid_id(session_id))
    prefix=f"install-{session_id}-"
    sequences=[]
    count=0
    with os.scandir(fd) as entries:
        for item in entries:
            count+=1
            require(count<=_MAX_ENTRIES,"install custody directory entry bound exceeded")
            if not item.name.startswith(prefix):
                continue
            suffix=item.name[len(prefix):]
            require(re.fullmatch(r"[0-9]{6}\.json",suffix) is not None and len(sequences)<_MAX_EVENTS,
                    "install session record name or capacity invalid")
            sequences.append(int(suffix[:-5]))
    sequences.sort()
    require(sequences==list(range(1,len(sequences)+1)),"install journal sequence is incomplete")
    rows=[]
    previous=None
    for seq in sequences:
        row=_parse(_read(fd,_filename(session_id,seq)),session_id=session_id,sequence=seq)
        require(row["previous_sha256"]==previous,"install journal hash chain diverged")
        previous=_event_digest(row)
        rows.append(row)
    return rows


@dataclass
class JournalState:
    source_head: str
    root_sha256: str
    options: dict
    configuration: str | None
    attempt: int=0
    active: bool=False
    outcome: str | None=None
    pending: str | None=None
    failed_required: bool=False
    phase_results: tuple=()


def _reduce(rows):
    if not rows:
        return None
    require(rows[0]["kind"]=="OPEN")
    opening=rows[0]["data"]
    state=JournalState(opening["source_head"],opening["root_sha256"],
                       opening["options"],opening["initial_configuration"])
    for event in rows[1:]:
        kind,data=event["kind"],event["data"]
        if kind=="ATTEMPT_BEGIN":
            # Restart cannot hide a previous uncertain attempt. Its separate
            # interrupted terminal event is appended before another attempt.
            require(not state.active and state.outcome!="passed" and data["attempt"]==state.attempt+1)
            state.attempt=data["attempt"]
            state.active=True
            state.outcome=None
            state.pending=None
            state.failed_required=False
            state.phase_results=()
        elif kind=="PHASE_INTENT":
            require(state.active and state.pending is None and (not state.failed_required or data["name"]=="setup-ui-recovery"))
            state.pending=data["name"]
        elif kind=="PHASE_RESULT":
            require(state.active)
            name=data["name"]
            if name in _INTENTS and state.pending==name:
                state.pending=None
            elif name in _INTENTS:
                # An optional skipped Python install records no intent.
                require(name=="python-install" and not data["required"] and data["ok"]
                        or name=="setup-ui-recovery" and not data["required"] and not data["ok"])
            else:
                require(state.pending is None or (name=="runtime-source-epoch" and not data["ok"]))
            if name=="setup-runtime" and data["ok"]:
                require(_hex(data["configuration_after"]))
                state.configuration=data["configuration_after"]
            if not data["ok"] and data["required"]:
                state.failed_required=True
            state.phase_results+=((name,data["ok"],data["required"]),)
        elif kind=="ATTEMPT_END":
            require(state.active)
            if data["outcome"]=="passed":
                require(state.pending is None and not state.failed_required)
            if data["outcome"]=="blocked":
                require(state.pending is None)
            state.outcome=data["outcome"]
            state.active=False
            state.pending=None
        else:
            raise InstallSessionDenied("invalid install journal transition")
    return state


class InstallSession:
    def __init__(self,root,path,session_id,head,options,fd,lock_fd,lock_name):
        self.root,self.path,self.id,self.head=root,path,session_id,head
        self.options=_options(options)
        self.fd,self.lock_fd,self.lock_name=fd,lock_fd,lock_name
        self.root_hash=_root_identity(root)
        self.rows=_scan(fd,session_id)
        self.state=_reduce(self.rows)
        self.closed=False

    def _check_owner(self):
        require(not self.closed)
        _same_directory(self.path,self.fd)
        _regular_named(self.lock_fd,self.fd,self.lock_name)
        require(_root_identity(self.root)==self.root_hash,"install checkout root replaced")
        observed=_scan(self.fd,self.id)
        require(observed==self.rows,"install journal changed during operation")

    def _append(self,kind,data):
        self._check_owner()
        require(len(self.rows)<_MAX_EVENTS,"install session journal exhausted")
        sequence=len(self.rows)+1
        row={"schema":SCHEMA,"session_id":self.id,"sequence":sequence,"kind":kind,
             "previous_sha256":_event_digest(self.rows[-1]) if self.rows else None,"data":data}
        raw=_canon(row)+b"\n"
        require(len(raw)<=_MAX_EVENT)
        _parse(raw,session_id=self.id,sequence=sequence)
        new=self.rows+[row]
        state=_reduce(new)
        name=_filename(self.id,sequence)
        fd=None
        try:
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK,
                       0o600,dir_fd=self.fd)
            _regular_named(fd,self.fd,name)
            pending=memoryview(raw)
            while pending:
                written=os.write(fd,pending)
                require(written>0,"install phase record publication incomplete")
                pending=pending[written:]
            os.fsync(fd)
            os.fsync(self.fd)
            _regular_named(fd,self.fd,name)
            _same_directory(self.path,self.fd)
            require(_read(self.fd,name)==raw,"install phase record publication unverified")
            self.rows,self.state=new,state
        finally:
            if fd is not None:
                os.close(fd)

    def start(self,*,resume):
        _current_source(self.root,self.head)
        current=_snapshot(self.root)
        if self.state is None:
            require(not resume,"unknown install session cannot resume")
            self._append("OPEN",{"root_sha256":self.root_hash,"source_head":self.head,
                         "options":self.options,"initial_configuration":current})
        else:
            require(resume,"existing install session requires explicit resume")
            require(self.state.root_sha256==self.root_hash and self.state.source_head==self.head
                    and self.state.options==self.options,"install resume source or operation identity changed")
            require(self.state.outcome!="passed","completed installation session cannot replay")
            require(self.state.configuration==current,
                    "private configuration changed across interrupted installation; inspect before new session")
            if self.state.active:
                # The prior owner is absent (exclusive lock acquired).
                # Persist uncertainty instead of pretending the prior intent
                # was completed. No operation is skipped or reversed.
                self._append("ATTEMPT_END",{"outcome":"interrupted"})
        self._append("ATTEMPT_BEGIN",{"attempt":self.state.attempt+1})

    def begin_phase(self,name):
        require(name in _INTENTS)
        _current_source(self.root,self.head)
        require(_snapshot(self.root)==self.state.configuration,
                "private runtime source changed before next side effect")
        self._append("PHASE_INTENT",{"name":name})

    def complete_phase(self,phase):
        name=phase.name
        require(name in _PHASES and type(phase.ok) is bool and type(phase.required) is bool)
        current=_snapshot(self.root) if name=="setup-runtime" and phase.ok else None
        if name=="setup-runtime" and phase.ok:
            require(_hex(current),"runtime setup did not publish stable private configuration")
        self._append("PHASE_RESULT",{"name":name,"ok":phase.ok,"required":phase.required,
                                     "configuration_after":current})

    def finish(self,receipt):
        _current_source(self.root,self.head)
        require(_snapshot(self.root)==self.state.configuration,
                "private runtime source changed before completion")
        # Ensure the journal saw all phases, including fast early returns
        # which did not enter the recorder list.
        observed=self.state.phase_results
        actual=tuple((phase.name,phase.ok,phase.required) for phase in receipt.phases)
        require(actual[:len(observed)]==observed,"installer phase journal diverged")
        for phase in receipt.phases[len(observed):]:
            self.complete_phase(phase)
        outcome="passed" if receipt.ok else ("interrupted" if self.state.pending is not None else "blocked")
        self._append("ATTEMPT_END",{"outcome":outcome})

    def report(self):
        require(self.state is not None)
        s=self.state
        return {"schema":_REPORT,"session_id":self.id,"source_head":s.source_head,
                "attempt":s.attempt,"active_or_interrupted":s.active,
                "outcome":s.outcome,"uncertain_phase":s.pending,
                "phase_results":[{"name":name,"ok":ok,"required":required}
                                 for name,ok,required in s.phase_results],
                "journal_head_sha256":_event_digest(self.rows[-1]),
                "configuration_observed_but_redacted":True,
                "runtime_requalified":False,"release_qualified":False}


@contextmanager
def open_session(root,directory,session_id,head,options,*,resume=False):
    root=Path(root).resolve()
    require(_valid_id(session_id) and type(head) is str and _SHA.fullmatch(head) is not None
            and type(resume) is bool)
    directory=Path(directory)
    require(directory!=root and root not in directory.parents,"session state must be outside checkout")
    import fcntl
    lock=None
    session=None
    try:
        with _private_directory(directory) as fd:
            root_hash=_root_identity(root)
            key="install-root-"+root_hash+".lock"
            lock=os.open(key,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,0o600,dir_fd=fd)
            try:
                _regular_named(lock,fd,key)
                try:
                    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except OSError:
                    raise InstallSessionDenied("another cooperating installer owns this checkout") from None
                session=InstallSession(root,directory,session_id,head,options,fd,lock,key)
                session.start(resume=resume)
                yield session
            finally:
                if session is not None:
                    session.closed=True
                os.close(lock)
                lock=None
    except InstallSessionDenied:
        raise
    except (OSError,ValueError,UnicodeError):
        raise InstallSessionDenied("private install journal unavailable or uncertain") from None


def inspect_session(directory,session_id):
    """Read-only redacted observation; does not acquire a writer lock."""
    require(_valid_id(session_id))
    try:
        with _private_directory(Path(directory)) as fd:
            first=_scan(fd,session_id)
            state=_reduce(first)
            require(state is not None,"install session not found")
            require(first==_scan(fd,session_id),"install session changed during inspection")
            return {"schema":_REPORT,"session_id":session_id,"source_head":state.source_head,
                    "attempt":state.attempt,"active_or_interrupted":state.active,
                    "outcome":state.outcome,"uncertain_phase":state.pending,
                    "phase_results":[{"name":n,"ok":o,"required":r} for n,o,r in state.phase_results],
                    "journal_head_sha256":_event_digest(first[-1]),
                    "configuration_observed_but_redacted":True,
                    "runtime_requalified":False,"release_qualified":False}
    except (OSError,ValueError,UnicodeError):
        raise InstallSessionDenied("install session unavailable or changing") from None


def generated_session_id():
    return uuid4().hex
