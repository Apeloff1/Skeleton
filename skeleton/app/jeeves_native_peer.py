"""Explicitly installed auxiliary GGUF inference using a private llama-server.

This is a local native process adapter, not a provider or a sandbox. Only a
trusted, operator-reviewed server build and compatible local GGUF artifacts
may be configured. No remote host, arbitrary native flags, tools, downloads,
shell commands, or untrusted artifact paths are accepted from chat requests.
The Unix-socket adapter is intentionally held on Windows pending native
process containment and equivalent socket qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import stat
import subprocess
import tempfile
import threading
import time

SCHEMA="skeleton.jeeves.native-peer.v1"
MAX_MANIFEST=16384
MAX_ARTIFACT=64*1024**3
MAX_BINARY=256*1024**2
MAX_REQUEST=12*1024**2
MAX_RESPONSE=1024**2
_SHA=re.compile(r"[a-f0-9]{64}\Z")


class PeerRejected(ValueError):
    """Native auxiliary model is unconfigured, incompatible or unqualified."""


def stable(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode("utf-8","strict")).hexdigest()


def sha(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        raise PeerRejected("invalid expected artifact digest")
    return value


def integer(value,lo,hi):
    if type(value) is not int or not lo<=value<=hi:
        raise PeerRejected("invalid bounded peer integer")
    return value


def text(value,limit,*,empty=False):
    if type(value) is not str or "\x00" in value or (not empty and not value.strip()):
        raise PeerRejected("invalid peer text")
    try:
        if len(value.encode("utf-8","strict"))>limit:
            raise PeerRejected("peer text exceeds byte bound")
    except UnicodeError:
        raise PeerRejected("invalid peer Unicode") from None
    return value


def closed(value,fields):
    if type(value) is not dict or value.keys()!=set(fields):
        raise PeerRejected("unexpected peer fields")
    return value


def strict_json(raw):
    def pairs(items):
        value={}
        for k,v in items:
            if k in value:
                raise PeerRejected("duplicate JSON field")
            value[k]=v
        return value
    def constant(_):
        raise PeerRejected("nonfinite JSON value")
    try:
        return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
    except (ValueError,UnicodeError,RecursionError):
        raise PeerRejected("invalid bounded JSON") from None


def file_stamp(st):
    return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)


def absolute_path(value):
    path=Path(text(value,2048))
    if not path.is_absolute() or ".." in path.parts or str(path).startswith("//"):
        raise PeerRejected("absolute local canonical file path required")
    return path


def _regular(path,limit):
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or not 1<=st.st_size<=limit:
        raise PeerRejected("artifact must be a bounded regular file")
    if os.name!="posix" or st.st_uid not in {0,os.getuid()} or st.st_mode&0o022:
        raise PeerRejected("artifact must be owner/root controlled on qualified POSIX")
    # Refuse symlinks and group/world-writable parents. Operator-controlled
    # path custody is essential because native processes reopen their inputs.
    for parent in path.parents:
        info=parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0,os.getuid()}
                or info.st_mode&0o022):
            raise PeerRejected("unsafe artifact parent directory")
    return st


def pinned_file(path,expected,limit,*,magic=None,deadline=None,read=False):
    sha(expected)
    try:
        before=_regular(path,limit)
        flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)
        raw=bytearray() if read else None
        h=hashlib.sha256();count=0
        with os.fdopen(os.open(path,flags),"rb") as handle:
            if file_stamp(os.fstat(handle.fileno()))!=file_stamp(before):
                raise PeerRejected("artifact changed at open")
            while True:
                if deadline is not None and time.monotonic()>=deadline:
                    raise PeerRejected("artifact verification deadline")
                block=handle.read(1024*1024)
                if not block:
                    break
                if count==0 and magic is not None and not block.startswith(magic):
                    raise PeerRejected("invalid GGUF artifact header")
                count+=len(block)
                if count>limit:
                    raise PeerRejected("artifact exceeds byte bound")
                h.update(block)
                if raw is not None:
                    raw.extend(block)
            if (count!=before.st_size or h.hexdigest()!=expected
                    or file_stamp(os.fstat(handle.fileno()))!=file_stamp(before)
                    or file_stamp(_regular(path,limit))!=file_stamp(before)):
                raise PeerRejected("artifact identity changed or SHA-256 mismatch")
        return file_stamp(before),bytes(raw) if raw is not None else None
    except OSError:
        raise PeerRejected("local artifact unavailable") from None


@dataclass(frozen=True,slots=True)
class Artifact:
    path: Path
    sha256: str

    @classmethod
    def parse(cls,value):
        closed(value,{"path","sha256"})
        return cls(absolute_path(value["path"]),sha(value["sha256"]))

    def as_dict(self):
        return {"path":str(self.path),"sha256":self.sha256}


@dataclass(frozen=True,slots=True)
class PeerSpec:
    binary: Artifact
    model: Artifact
    projector: Artifact|None
    modalities: tuple[str,...]
    context_tokens: int
    max_output_tokens: int
    threads: int
    timeout_seconds: int

    @classmethod
    def parse(cls,value):
        closed(value,{"schema","binary","model","projector","modalities",
                      "context_tokens","max_output_tokens","threads","timeout_seconds"})
        if value["schema"]!=SCHEMA:
            raise PeerRejected("unsupported peer manifest schema")
        modes=value["modalities"]
        if (type(modes) is not list or not modes or len(modes)>3
                or any(type(x) is not str or x not in {"text","image","audio"} for x in modes)
                or len(set(modes))!=len(modes) or "text" not in modes):
            raise PeerRejected("unsupported auxiliary modalities")
        binary=Artifact.parse(value["binary"]);model=Artifact.parse(value["model"])
        projector=None if value["projector"] is None else Artifact.parse(value["projector"])
        if (bool(set(modes)-{"text"})!=(projector is not None)
                or len({binary.path,model.path}|({projector.path} if projector else set()))!=2+int(projector is not None)
                or (projector is not None and projector.sha256==model.sha256)):
            raise PeerRejected("invalid model/projector identity or modality configuration")
        context=integer(value["context_tokens"],1024,32768)
        output=integer(value["max_output_tokens"],32,min(4096,context//2))
        return cls(binary,model,projector,tuple(sorted(modes)),context,output,
                   integer(value["threads"],1,16),integer(value["timeout_seconds"],10,900))

    def as_dict(self):
        return {"schema":SCHEMA,"binary":self.binary.as_dict(),"model":self.model.as_dict(),
                "projector":self.projector.as_dict() if self.projector else None,
                "modalities":list(self.modalities),"context_tokens":self.context_tokens,
                "max_output_tokens":self.max_output_tokens,"threads":self.threads,
                "timeout_seconds":self.timeout_seconds}

    @property
    def identity(self):
        # Artifact bytes, not local filesystem location, define configuration.
        config=self.as_dict()
        for key in ("binary","model","projector"):
            if config[key] is not None:
                config[key]=config[key]["sha256"]
        return digest(stable(config))

    @classmethod
    def load(cls,path,expected):
        _,raw=pinned_file(absolute_path(str(Path(path).absolute())),expected,MAX_MANIFEST,read=True)
        return cls.parse(strict_json(raw))

    def public(self):
        return {"peer_identity":self.identity,"model_sha256":self.model.sha256,
                "server_sha256":self.binary.sha256,"projector_sha256":self.projector.sha256 if self.projector else None,
                "declared_modalities":list(self.modalities),"context_tokens":self.context_tokens,
                "max_output_tokens":self.max_output_tokens,"timeout_seconds":self.timeout_seconds,
                "runtime_execution_verified":False,"native_process_sandboxed":False}

    def verify_files(self,deadline):
        pins=[(self.binary,MAX_BINARY,None),(self.model,MAX_ARTIFACT,b"GGUF")]
        if self.projector:
            pins.append((self.projector,MAX_ARTIFACT,b"GGUF"))
        stamps=[]
        for artifact,limit,magic in pins:
            stamp,_=pinned_file(artifact.path,artifact.sha256,limit,magic=magic,deadline=deadline)
            stamps.append((artifact.path,stamp,limit))
        if not os.access(self.binary.path,os.X_OK):
            raise PeerRejected("configured native server is not executable")
        # Auto-discovered sibling GGUF shards would not be bound by this
        # single-file manifest. Reject split naming instead of loading them.
        if re.search(r"-\d{5}-of-\d{5}\.gguf$",self.model.path.name,re.I):
            raise PeerRejected("split GGUF requires explicit shard-aware peer custody")
        return stamps


class _UnixHTTP(http.client.HTTPConnection):
    def __init__(self,path,timeout):
        super().__init__("localhost",timeout=timeout)
        self.path=str(path)

    def connect(self):
        sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            sock.settimeout(self.timeout)
            sock.connect(self.path)
            self.sock=sock
        except BaseException:
            sock.close()
            raise


def _remaining(deadline):
    remaining=deadline-time.monotonic()
    if remaining<=0:
        raise PeerRejected("native peer execution deadline exceeded")
    return remaining


def _http(path,token,method,route,payload,deadline):
    conn=_UnixHTTP(path,_remaining(deadline) if method=="POST" else min(5,_remaining(deadline)))
    try:
        raw=None if payload is None else stable(payload).encode()
        if raw is not None and len(raw)>MAX_REQUEST:
            raise PeerRejected("native peer request exceeds byte bound")
        conn.request(method,route,body=raw,headers={
            "Authorization":"Bearer "+token,"Content-Type":"application/json",
            "Accept":"application/json","Connection":"close"})
        response=conn.getresponse()
        if response.status not in {200,503}:
            raise PeerRejected("native peer rejected request")
        length=response.getheader("Content-Length")
        if length is not None and (not length.isdecimal() or int(length)>MAX_RESPONSE):
            raise PeerRejected("native peer response exceeds bound")
        chunks=[];total=0
        while True:
            if conn.sock is not None:
                conn.sock.settimeout(_remaining(deadline) if method=="POST" else min(5,_remaining(deadline)))
            block=response.read(min(65536,MAX_RESPONSE+1-total))
            if not block:
                break
            total+=len(block)
            if total>MAX_RESPONSE:
                raise PeerRejected("native peer response exceeds bound")
            chunks.append(block)
        return response.status,strict_json(b"".join(chunks))
    finally:
        conn.close()


def _stop(process):
    # New session, owned process group; no shell or descendants intentionally
    # launched by the configured single-model server. Child escape remains
    # outside this trusted-binary adapter's guarantees.
    if process.poll() is None:
        try:
            os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    else:
        process.wait(timeout=1)


def _validate_messages(messages,spec):
    if type(messages) is not list or not 1<=len(messages)<=66:
        raise PeerRejected("invalid bounded native messages")
    for item in messages:
        closed(item,{"role","content"})
        if item["role"] not in {"system","user","assistant"}:
            raise PeerRejected("unsupported native message role")
        content=item["content"]
        if type(content) is str:
            text(content,65536)
            continue
        if item["role"]!="user" or type(content) is not list or not 1<=len(content)<=20:
            raise PeerRejected("invalid multimodal content inventory")
        for part in content:
            if type(part) is not dict or type(part.get("type")) is not str:
                raise PeerRejected("invalid multimodal block")
            kind=part["type"]
            if kind=="text":
                closed(part,{"type","text"});text(part["text"],16384)
            elif kind=="image_url":
                closed(part,{"type","image_url"});closed(part["image_url"],{"url"})
                url=part["image_url"]["url"]
                if ("image" not in spec.modalities or type(url) is not str
                        or not url.startswith("data:image/jpeg;base64,")
                        or len(url)>MAX_REQUEST or not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}",url.split(",",1)[1])):
                    raise PeerRejected("only bounded inline canonical image bytes permitted")
            elif kind=="input_audio":
                closed(part,{"type","input_audio"});closed(part["input_audio"],{"format","data"})
                audio=part["input_audio"]
                if ("audio" not in spec.modalities or audio["format"]!="wav"
                        or type(audio["data"]) is not str or len(audio["data"])>MAX_REQUEST
                        or not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}",audio["data"])):
                    raise PeerRejected("only bounded inline PCM WAV permitted")
            else:
                raise PeerRejected("remote or unsupported media block denied")


class NativePeer:
    def __init__(self,spec):
        if not isinstance(spec,PeerSpec) or PeerSpec.parse(spec.as_dict())!=spec:
            raise PeerRejected("canonical owner-provided peer spec required")
        self.spec=spec
        self._lock=threading.Lock()

    def generate(self,messages,*,max_output_tokens,deadline=None):
        if os.name!="posix" or not hasattr(socket,"AF_UNIX"):
            raise PeerRejected("native peer process/socket custody not qualified on this platform")
        _validate_messages(messages,self.spec)
        budget=integer(max_output_tokens,1,self.spec.max_output_tokens)
        deadline=min(time.monotonic()+self.spec.timeout_seconds,
                     deadline if deadline is not None else float("inf"))
        if not self._lock.acquire(blocking=False):
            raise PeerRejected("native peer execution is already active")
        try:
            return self._generate(messages,budget,deadline)
        finally:
            self._lock.release()

    def _generate(self,messages,budget,deadline):
        stamps=self.spec.verify_files(deadline)
        from skeleton.app.offline_resources import probe_local_resources
        try:
            # Advisory conservative RAM floor; not an exact architecture/KV
            # measurement or hard kernel memory cap. Fail closed if telemetry
            # is unavailable. Avoid deliberately overcommitting native CPU RAM.
            observed=probe_local_resources(self.spec.model.path)
            weights=sum(stamp[2] for path,stamp,_ in stamps if path!=self.spec.binary.path)
            floor=2*weights+2*1024**3+self.spec.context_tokens*65536
            if (observed.available_ram_bytes<floor or observed.memory_pressure_ratio>=0.85):
                raise PeerRejected("insufficient measured host headroom for auxiliary inference")
        except PeerRejected:
            raise
        except Exception:
            raise PeerRejected("native peer resource telemetry unavailable") from None
        started=time.monotonic()
        # The socket is in an owner-only temporary directory. No TCP bind,
        # public listener, inherited proxy/LLAMA_ARG options or cloud token.
        with tempfile.TemporaryDirectory(prefix="jv-peer-",dir="/tmp") as folder:
            root=Path(folder);os.chmod(root,0o700)
            endpoint=root/"peer.sock"
            token=secrets.token_urlsafe(48)
            secret=root/"key"
            fd=os.open(secret,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,"w",encoding="ascii") as handle:
                handle.write(token+"\n")
            alias="jeeves-peer-"+self.spec.identity
            args=[str(self.spec.binary.path),"-m",str(self.spec.model.path),
                  "--host",str(endpoint),"--api-key-file",str(secret),
                  "--alias",alias,"--ctx-size",str(self.spec.context_tokens),
                  "--threads",str(self.spec.threads),"--parallel","1",
                  "--n-gpu-layers","0","--no-ui","--no-slots","--no-context-shift",
                  "--no-cache-prompt","--log-disable"]
            if self.spec.projector:
                args.extend(["--mmproj",str(self.spec.projector.path),"--no-mmproj-offload"])
            env={"PATH":"/usr/bin:/bin","HOME":folder,"TMPDIR":folder,"LC_ALL":"C",
                 "HF_HUB_OFFLINE":"1","TRANSFORMERS_OFFLINE":"1"}
            for path,stamp,limit in stamps:
                if file_stamp(_regular(path,limit))!=stamp:
                    raise PeerRejected("native peer artifact changed before dispatch")
            process=subprocess.Popen(args,cwd=folder,env=env,shell=False,start_new_session=True,
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                close_fds=True)
            def expire():
                # Deadline also bounds a blocking socket read. No answer may
                # publish after the watchdog terminates the child.
                try:
                    if process.poll() is None:
                        os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:
                    pass
            watchdog=None
            try:
                watchdog=threading.Timer(_remaining(deadline),expire)
                watchdog.daemon=True;watchdog.start()
                while True:
                    _remaining(deadline)
                    if process.poll() is not None:
                        raise PeerRejected("native peer exited before readiness")
                    try:
                        status,health=_http(endpoint,token,"GET","/health",None,deadline)
                    except (OSError,http.client.HTTPException):
                        time.sleep(min(.15,_remaining(deadline)));continue
                    if status==200 and type(health) is dict and health.get("status")=="ok":
                        break
                    time.sleep(min(.15,_remaining(deadline)))
                request={"model":alias,"messages":messages,"temperature":0,
                         "seed":0,"max_tokens":budget,"stream":False}
                request_digest=digest(stable(request))
                # The completion may take longer than a health request. The
                # subprocess watchdog is the hard deadline instead.
                status,result=_http(endpoint,token,"POST","/v1/chat/completions",request,deadline)
                _remaining(deadline)
                if status!=200 or type(result) is not dict or result.get("model")!=alias:
                    raise PeerRejected("native peer model response identity mismatch")
                choices=result.get("choices");usage=result.get("usage")
                if (type(choices) is not list or len(choices)!=1
                        or type(choices[0]) is not dict or type(usage) is not dict):
                    raise PeerRejected("invalid native peer completion envelope")
                choice=choices[0];message=choice.get("message")
                response_id=text(result.get("id"),256)
                if (type(message) is not dict or message.get("role")!="assistant"
                        or message.get("tool_calls") or message.get("function_call")
                        or choice.get("finish_reason") not in {"stop","length"}):
                    raise PeerRejected("native peer did not produce a terminal text answer")
                answer=text(message.get("content"),65536)
                inp=integer(usage.get("prompt_tokens"),1,self.spec.context_tokens)
                out=integer(usage.get("completion_tokens"),1,budget)
                if inp+out>self.spec.context_tokens or usage.get("total_tokens")!=inp+out:
                    raise PeerRejected("native peer token usage exceeds configured window")
                if process.poll() is not None:
                    raise PeerRejected("native peer lost process custody")
                for path,stamp,limit in stamps:
                    if file_stamp(_regular(path,limit))!=stamp:
                        raise PeerRejected("native peer artifact changed during execution")
                receipt={"schema":"skeleton.jeeves.native-peer-execution.v1",
                         "peer_identity":self.spec.identity,"model_sha256":self.spec.model.sha256,
                         "request_sha256":request_digest,"response_id":response_id,
                         "output_sha256":digest(answer),"prompt_tokens":inp,"completion_tokens":out,
                         "finish_reason":choice["finish_reason"],
                         "elapsed_ms":int((time.monotonic()-started)*1000),
                         "independent_runtime_attestation":False}
                receipt["sha256"]=digest(stable(receipt))
                return {"text":answer,"receipt":receipt}
            except (OSError,http.client.HTTPException,subprocess.SubprocessError):
                raise PeerRejected("native peer execution unavailable") from None
            finally:
                if watchdog is not None:
                    watchdog.cancel()
                    if watchdog.ident is not None:
                        watchdog.join()
                _stop(process)
