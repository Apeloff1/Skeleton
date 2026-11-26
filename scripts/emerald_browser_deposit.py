"""Recover exact original Emerald assets from a browser deposit, without LFS."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import urllib.request
import zlib
from contextlib import contextmanager, nullcontext

MANIFEST=Path(__file__).with_name("emerald_browser_deposit.json")
MANIFEST_SHA="076db86e235b2e578d300fa9f04f822f316c1fa65b26b5f34f4625dfb955a7f5"
RAW="https://raw.githubusercontent.com/Apeloff1/Skeleton/"
DIRECTORY="/artifacts/emerald/deposit-r1/"
PIN={
    "model":("emerald_continuum.glb",463149740,"c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a"),
    "source":("emerald-atelier-fold-source.zip",194733639,"093feccb25846b39eefe94a4385873e25df125371544545042c3d34b3fe879f5"),
    "web":("emerald-skeleton-web-assets.zip",48249605,"354b7d1dadc02f7919aa6b9b802f949894d2cb6ea0e0e493db9ba9d819d22851"),
}
MAX_SHARD=25_000_000
CHUNK=24_000_000


def read_exact(stream,size):
    data=bytearray()
    while len(data)<size:
        block=stream.read(min(1024*1024,size-len(data)))
        if not block: raise ValueError("truncated shard")
        data.extend(block)
    if stream.read(1): raise ValueError("oversized shard")
    return data


def sha(data): return hashlib.sha256(data).hexdigest()


def load_manifest(raw, digest=MANIFEST_SHA, pin=PIN):
    if len(raw)>64*1024 or sha(raw)!=digest: raise ValueError("manifest identity mismatch")
    m=json.loads(raw)
    if (m["schema"],m["asset_set"],m["encoding"],m["chunk_bytes"])!=("skeleton.emerald.browser-deposit.v1","emerald-20261117-r1","zlib",CHUNK):
        raise ValueError("invalid manifest schema")
    if [a["role"] for a in m["assets"]]!=list(pin): raise ValueError("invalid asset roles")
    for a in m["assets"]:
        if (a["name"],a["bytes"],a["sha256"])!=pin[a["role"]]: raise ValueError("asset pin mismatch")
        expected_count=(a["bytes"]+CHUNK-1)//CHUNK
        if len(a["shards"])!=expected_count: raise ValueError("shard count mismatch")
        for i,s in enumerate(a["shards"]):
            if s["name"]!=f'{a["role"]}-{i+1:03}.bin':raise ValueError("shard name mismatch")
            if type(s["bytes"]) is not int or not 0<s["bytes"]<MAX_SHARD:raise ValueError("shard size outside policy")
            if s["raw_bytes"]!=min(CHUNK,a["bytes"]-i*CHUNK):raise ValueError("raw shard size mismatch")
            if not re.fullmatch("[a-f0-9]{64}",s["sha256"]):raise ValueError("invalid shard digest")
    return m


def inflate(stream,s):
    compressed=read_exact(stream,s["bytes"])
    if sha(compressed)!=s["sha256"]:raise ValueError("shard digest mismatch: "+s["name"])
    decoder=zlib.decompressobj()
    data=decoder.decompress(compressed,s["raw_bytes"]+1)
    if len(data)!=s["raw_bytes"] or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("shard expansion mismatch: "+s["name"])
    return data


@contextmanager
def local_file(directory,s):
    path=directory/s["name"]
    initial=path.lstat()
    if not stat.S_ISREG(initial.st_mode) or initial.st_size!=s["bytes"]:raise ValueError("invalid local shard: "+s["name"])
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)|getattr(os,"O_BINARY",0)
    with os.fdopen(os.open(path,flags),"rb") as stream:
        before=os.fstat(stream.fileno())
        identity=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        if identity(initial)!=identity(before):raise ValueError("shard replaced")
        yield stream
        if identity(before)!=identity(os.fstat(stream.fileno())):raise ValueError("shard changed")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise ValueError("unexpected raw-object redirect")


@contextmanager
def remote_file(commit,s):
    if not re.fullmatch("[a-f0-9]{40}",commit): raise ValueError("exact uploaded commit SHA required")
    url=RAW+commit+DIRECTORY+s["name"]
    request=urllib.request.Request(url,headers={"Accept-Encoding":"identity","User-Agent":"Skeleton-Emerald-Deposit/1"})
    with urllib.request.build_opener(NoRedirect()).open(request,timeout=90) as stream:
        if stream.status!=200:raise ValueError("remote shard unavailable")
        if stream.headers.get("Content-Length") is not None and int(stream.headers["Content-Length"])!=s["bytes"]:
            raise ValueError("remote size mismatch")
        yield stream


def reconstruct(manifest,opener,output=None):
    def build(a,sink):
        whole=hashlib.sha256(); total=0
        for s in a["shards"]:
            with opener(s) as stream: data=inflate(stream,s)
            whole.update(data);total+=len(data)
            if sink is not None:sink.write(data)
        if total!=a["bytes"] or whole.hexdigest()!=a["sha256"]:raise ValueError("original asset identity mismatch: "+a["name"])
    if output is None:
        for a in manifest["assets"]:build(a,None)
        return
    if not output.is_dir() or output.is_symlink():raise ValueError("existing trusted output directory required")
    for a in manifest["assets"]:
        if os.path.lexists(output/a["name"]):raise FileExistsError(output/a["name"])
    with tempfile.TemporaryDirectory(prefix=".emerald-deposit-",dir=output) as tmp:
        staging=Path(tmp)
        for a in manifest["assets"]:
            with (staging/a["name"]).open("xb") as sink:
                build(a,sink);sink.flush();os.fsync(sink.fileno())
        created=[]
        try:
            for a in manifest["assets"]:
                name=a["name"];target=output/name;os.link(staging/name,target);created.append(target)
        except OSError:
            for target in reversed(created):
                if os.path.samefile(staging/target.name,target):target.unlink()
            raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument("--local",type=Path,help="directory with the extracted .bin shards")
    source.add_argument("--commit",help="immutable browser upload commit SHA")
    p.add_argument("--output",type=Path,help="existing empty destination; omitted means verify only")
    args=p.parse_args()
    try:
        m=load_manifest(MANIFEST.read_bytes())
        opener=(lambda s:local_file(args.local,s)) if args.local else (lambda s:remote_file(args.commit,s))
        reconstruct(m,opener,args.output)
    except (OSError,ValueError,zlib.error) as error:
        p.exit(2,"Deposit not qualified: "+str(error)+"\n")
    print(json.dumps({"schema":"skeleton.emerald.deposit-receipt.v1","manifest_sha256":MANIFEST_SHA,
                      "asset_set":m["asset_set"],"original_bytes_verified":True,"remote_commit":args.commit,
                      "remote_readback_verified":bool(args.commit),"published_local":args.output is not None,
                      "assets":[{k:a[k] for k in ("name","bytes","sha256")} for a in m["assets"]],
                      "unreal_compiled":False,"physical_rtx_verified":False},indent=2))


if __name__=="__main__":main()
