"""Explicit, offline-first admission of fixed public pretrained semantic artifacts.

Network acquisition is a separate operator/CI action. The installed search
and generation runtimes never download models. No remote repository code is
checked out or imported. Public source commits bind tokenizer bytes and LFS
pointers; weights also match the independently recorded publisher SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from skeleton.retrieval.learned_embeddings import _read_pinned
from skeleton.retrieval.semantic_config import load_semantic_ranker

CATALOG={
    "bge-small-f32":{
        "repo":"Xenova/bge-small-en-v1.5","revision":"ea104dacec62c0de699686887e3f920caeb4f3e3",
        "weight":"onnx/model.onnx","sha256":"828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35",
        "max_bytes":150*1024**2,"base":"BAAI/bge-small-en-v1.5","license":"MIT (base model)",
        "kind":"encoder",
    },
    "bge-small-int8":{
        "repo":"Xenova/bge-small-en-v1.5","revision":"ea104dacec62c0de699686887e3f920caeb4f3e3",
        "weight":"onnx/model_quantized.onnx","sha256":"6c9c6101a956d62dfb5e7190c538226c0c5bb9cb27b651234b6df063ee7dbfe4",
        "max_bytes":40*1024**2,"base":"BAAI/bge-small-en-v1.5","license":"MIT (base model)",
        "kind":"encoder",
    },
    "bge-reranker-int8":{
        "repo":"Xenova/bge-reranker-base","revision":"cbd4c47f870c4bb77534e06b8853de9c6e958b82",
        "weight":"onnx/model_quantized.onnx","sha256":"dd98f3e67837d23210a6b7550c08cced4f61845b940ac45be3565840a10f3244",
        "max_bytes":310*1024**2,"base":"BAAI/bge-reranker-base","license":"MIT (base model)",
        "kind":"reranker",
    },
}


def digest(raw):return hashlib.sha256(raw).hexdigest()


def _gate_env():
    # No inherited HF tokens, proxy credentials, Git credential helpers,
    # user hooks or repository config. Standard trusted executable PATH.
    return {"PATH":os.environ.get("PATH","/usr/bin:/bin"),"LANG":"C","LC_ALL":"C",
            "GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":os.devnull,
            "GIT_TERMINAL_PROMPT":"0","GIT_LFS_SKIP_SMUDGE":"1"}


def _git(directory,*args):
    result=subprocess.run(["git","-C",str(directory),"-c","credential.helper=",
        "-c","core.hooksPath="+os.devnull,"-c","protocol.file.allow=never",
        *args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        env=_gate_env(),timeout=180,check=False)
    if result.returncode:raise RuntimeError("fixed public Git artifact custody operation failed")
    return result.stdout


def _lfs_pointer(raw,entry):
    if not isinstance(raw,bytes) or len(raw)>1024:
        raise ValueError("upstream artifact lacks bounded Git LFS pointer")
    lines=raw.decode("ascii").splitlines()
    if len(lines)!=3 or lines[0]!="version https://git-lfs.github.com/spec/v1":
        raise ValueError("unsupported Git LFS pointer schema")
    if lines[1]!="oid sha256:"+entry["sha256"] or not re.fullmatch(r"size [1-9][0-9]*",lines[2]):
        raise ValueError("upstream LFS pointer differs from reviewed artifact")
    size=int(lines[2].split()[1])
    if size>entry["max_bytes"]:
        raise ValueError("upstream artifact exceeds reviewed byte ceiling")
    return size


def _blob(repo,revision,path,cap):
    locator=revision+":"+path
    length=int(_git(repo,"cat-file","-s",locator))
    if not 1<=length<=cap:raise ValueError("upstream Git blob outside admitted bytes")
    data=_git(repo,"cat-file","blob",locator)
    if len(data)!=length:raise ValueError("upstream Git blob length mismatch")
    git_sha=hashlib.sha1(b"blob "+str(length).encode()+b"\0"+data).hexdigest()
    if _git(repo,"rev-parse",locator).decode().strip()!=git_sha:
        raise ValueError("upstream Git blob content pin mismatch")
    return data,git_sha


def _download(entry,target,size):
    # Fixed public URL, no caller-provided endpoints. Redirects must remain
    # HTTPS; received bytes must match the immutable LFS content identity.
    url="https://huggingface.co/"+entry["repo"]+"/resolve/"+entry["revision"]+"/"+entry["weight"]
    result=subprocess.run(["curl","--disable","--fail","--silent","--show-error","--location",
        "--proto","=https","--proto-redir","=https","--max-redirs","5",
        "--connect-timeout","15","--max-time","240","--max-filesize",str(size),
        "--output",str(target),url],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,env=_gate_env(),timeout=260,check=False)
    if result.returncode:raise RuntimeError("fixed public weight acquisition failed")


def _copy_verified(path,target,entry,size):
    raw=_read_pinned(path,entry["sha256"],entry["max_bytes"])
    if len(raw)!=size:raise ValueError("weight length differs from immutable pointer")
    with target.open("xb") as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())


def _prepare(profile,stage,*,source_root,acquire):
    entry=CATALOG[profile]
    artifact_dir=stage/profile
    artifact_dir.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".source-",dir=stage) as tmp:
        # Offline route uses a trusted local bare Git snapshot; no checkout.
        if acquire:
            repo=Path(tmp)
            _git(repo,"init","--bare","--quiet")
            _git(repo,"fetch","--no-tags","--depth=1",
                 "https://huggingface.co/"+entry["repo"],entry["revision"])
            if _git(repo,"rev-parse","FETCH_HEAD").decode().strip()!=entry["revision"]:
                raise ValueError("received source commit differs from fixed catalog")
        else:
            repo=source_root/profile/"source.git"
            if not repo.is_dir() or repo.is_symlink():
                raise ValueError("offline profile requires trusted bare source Git snapshot")
        revision=entry["revision"]
        if _git(repo,"rev-parse",revision+"^{commit}").decode().strip()!=revision:
            raise ValueError("source revision mismatch")
        pointer,pointer_git=_blob(repo,revision,entry["weight"],1024)
        size=_lfs_pointer(pointer,entry)
        tokenizer,tokenizer_git=_blob(repo,revision,"tokenizer.json",32*1024**2)
        if tokenizer.startswith(b"version https://git-lfs.github.com/"):
            raise ValueError("tokenizer requires inline exact committed Git blob")
        if not isinstance(json.loads(tokenizer),dict):
            raise ValueError("unsupported tokenizer JSON")
        weight=artifact_dir/"model.onnx"
        if acquire:
            downloaded=Path(tmp)/"weight.download"
            _download(entry,downloaded,size)
        else:
            downloaded=source_root/profile/"model.onnx"
        _copy_verified(downloaded,weight,entry,size)
        token_path=artifact_dir/"tokenizer.json"
        with token_path.open("xb") as stream:
            stream.write(tokenizer);stream.flush();os.fsync(stream.fileno())
        return {"profile":profile,"repository":entry["repo"],"revision":revision,
                "base_model":entry["base"],"license_notice":entry["license"],
                "weight_git_blob":pointer_git,"weight_sha256":entry["sha256"],
                "weight_bytes":size,"tokenizer_git_blob":tokenizer_git,
                "tokenizer_sha256":digest(tokenizer)}


def provision(destination,*,encoder="bge-small-f32",reranker=None,source_root=None,acquire=False):
    if encoder not in CATALOG or CATALOG[encoder]["kind"]!="encoder" or (reranker is not None and (reranker not in CATALOG or CATALOG[reranker]["kind"]!="reranker")):
        raise ValueError("select explicit reviewed semantic profile")
    if type(acquire) is not bool or acquire==(source_root is not None):
        raise ValueError("select exactly one offline snapshot or explicit public acquisition")
    destination=Path(destination).absolute()
    parent=destination.parent
    if parent.resolve(strict=True)!=parent or destination.exists() or destination.is_symlink():
        raise ValueError("new non-symlinked artifact destination required")
    if os.name=="posix" and (parent.stat().st_uid!=os.geteuid() or parent.stat().st_mode&0o077):
        raise PermissionError("semantic package root must be owner-private")
    stage=Path(tempfile.mkdtemp(prefix=".semantic-admit-",dir=parent))
    try:
        records=[_prepare(encoder,stage,source_root=source_root,acquire=acquire)]
        enc=records[0]
        config={"schema":"skeleton.local.semantic-config.v1",
            "encoder_path":encoder+"/model.onnx","encoder_sha256":enc["weight_sha256"],
            "tokenizer_path":encoder+"/tokenizer.json","tokenizer_sha256":enc["tokenizer_sha256"],
            "encoder_policy":{"dimension":384,"max_tokens":512,
                "query_prefix":"Represent this sentence for searching relevant passages: "},
            "retrieval_policy":{"context_chars":1200,"candidate_pool":64}}
        if reranker:
            cross=_prepare(reranker,stage,source_root=source_root,acquire=acquire)
            records.append(cross)
            config["reranker"]={"model_path":reranker+"/model.onnx","model_sha256":cross["weight_sha256"],
                "tokenizer_path":reranker+"/tokenizer.json","tokenizer_sha256":cross["tokenizer_sha256"],
                "policy":{"max_tokens":512,"max_pairs":16}}
        raw=json.dumps(config,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
        cfg=stage/"semantic.json"
        cfg.write_bytes(raw)
        pin=digest(raw)
        ranker=load_semantic_ranker(cfg,pin)
        # Execute actual pretrained weights, not a hash-only receipt.
        query=ranker.encoder.query("How can I recover a damaged save?")
        sample="Restore an earlier backup of the game state."
        document=ranker.encoder.spans(sample,[(0,len(sample))])[0]
        if len(query.dense)!=384 or len(document.dense)!=384:
            raise RuntimeError("pretrained token output geometry invalid")
        observed=float(sum(a*b for a,b in zip(query.dense,document.dense)))
        cross_scores=ranker.reranker.score("How can I recover a damaged save?",[sample,"The sky is blue."]) if ranker.reranker else None
        receipt={"schema":"skeleton.semantic.pretrained-admission.v1","source_artifacts":records,
            "config_sha256":pin,"ranker_sha256":ranker.identity,"native_cpu_execution":True,
            "diagnostic_cosine":observed,"diagnostic_cross_scores":cross_scores,
            "network_acquisition":acquire,"activation_authorized":False,
            "quality_certified":False,"license_review_required_for_redistribution":True}
        receipt["receipt_sha256"]=digest(json.dumps(receipt,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
        (stage/"receipt.json").write_text(json.dumps(receipt,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        if destination.exists() or destination.is_symlink():raise FileExistsError("candidate package already exists")
        os.rename(stage,destination)
        return receipt
    finally:
        if stage.exists():shutil.rmtree(stage)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--destination",type=Path,required=True)
    p.add_argument("--encoder",choices=("bge-small-f32","bge-small-int8"),default="bge-small-f32")
    p.add_argument("--reranker",choices=("bge-reranker-int8",))
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument("--offline-snapshot",type=Path)
    source.add_argument("--acquire-reviewed-public-models",action="store_true")
    a=p.parse_args(argv)
    result=provision(a.destination,encoder=a.encoder,reranker=a.reranker,
        source_root=a.offline_snapshot,acquire=a.acquire_reviewed_public_models)
    print(json.dumps(result,sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
