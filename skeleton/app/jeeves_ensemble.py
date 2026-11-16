"""Explicit local specialist registry and sequential generator ensemble.

Specialists are isolated review generators, never selectable chat providers.
The canonical Jeeves model remains the only durable transcript authority.
Each native checkpoint is independently pinned and loaded lazily, one at
a time. The report preserves disagreement rather than inventing consensus.
"""
from __future__ import annotations

import asyncio
from hashlib import sha256
import json
from pathlib import Path
import re
import time

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import DevicePolicy, RuntimeContractError
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.local_ai import OfflineAISession, _model_tokenizer_digest
from skeleton.retrieval.learned_embeddings import _read_pinned

MAX_MODELS=3
MAX_MODEL_BYTES=256*1024**2
MAX_PER_CANDIDATE=128
MAX_RESERVED=384
_ID=re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_PIN=re.compile(r"[0-9a-f]{64}\Z")
_ROLES={"reasoning","coding","research","creative","draft"}
_INSTRUCTIONS={
    "reasoning":"Check assumptions and derive an independent answer.",
    "coding":"Check correctness, edge cases and implementation constraints.",
    "research":"Separate supported findings from uncertainty.",
    "creative":"Consider alternative approaches without asserting unsupported facts.",
    "draft":"Answer independently and concisely.",
}


def digest(obj):
    return sha256(json.dumps(obj,sort_keys=True,ensure_ascii=True,
        separators=(",",":"),allow_nan=False).encode()).hexdigest()


def _sha(s):
    return sha256(s.encode("utf-8")).hexdigest()


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError("duplicate specialist config field")
        result[key]=value
    return result


class SpecialistRegistry:
    def __init__(self,path,expected_sha256):
        path=Path(path)
        cfg=json.loads(_read_pinned(path,expected_sha256,65536),object_pairs_hook=_unique)
        if type(cfg) is not dict or set(cfg)!={"schema","profiles"} or cfg["schema"]!="skeleton.jeeves.specialists.v1":
            raise ValueError("invalid local specialist registry")
        if type(cfg["profiles"]) is not list or not 1<=len(cfg["profiles"])<=MAX_MODELS:
            raise ValueError("bounded explicit specialist inventory required")
        profiles={}
        seen=set()
        for row in cfg["profiles"]:
            if type(row) is not dict or set(row)!={"id","role","path","file_sha256","model_digest","tokenizer_digest","max_bytes"}:
                raise ValueError("invalid specialist profile shape")
            name=row["id"]
            if (type(name) is not str or not _ID.fullmatch(name) or name=="jeeves" or name in profiles
                    or type(row["role"]) is not str or row["role"] not in _ROLES
                    or any(type(row[k]) is not str or not _PIN.fullmatch(row[k]) for k in ("file_sha256","model_digest","tokenizer_digest"))
                    or row["model_digest"] in seen or type(row["max_bytes"]) is not int
                    or not 1<=row["max_bytes"]<=MAX_MODEL_BYTES):
                raise ValueError("invalid or duplicate specialist identity")
            src=row["path"]
            if type(src) is not str or not src or Path(src).is_absolute() or ".." in Path(src).parts:
                raise ValueError("specialist artifact must be relative")
            profiles[name]=dict(row)
            seen.add(row["model_digest"])
        self._root=path.parent
        self._profiles=profiles
        self.identity=expected_sha256

    def inventory(self):
        return [{k:row[k] for k in ("id","role","model_digest","tokenizer_digest","max_bytes")}
                for row in self._profiles.values()]

    def load(self,name,*,primary_digest,required_role=None):
        if type(name) is not str or name not in self._profiles:
            raise ValueError("unknown local specialist")
        spec=self._profiles[name]
        if spec["model_digest"]==primary_digest or (required_role is not None and spec["role"]!=required_role):
            raise ValueError("specialist cannot alias the primary or another role")
        raw=_read_pinned(self._root/spec["path"],spec["file_sha256"],spec["max_bytes"])
        runtime=NativeLLMRuntime.restore_json(raw,device_policy=DevicePolicy(requested="cpu",allow_fallback=False))
        if runtime.model_digest!=spec["model_digest"] or runtime.tokenizer.digest!=spec["tokenizer_digest"]:
            raise ValueError("restored specialist identity mismatch")
        runtime.assert_model_unchanged()
        return runtime

    def role(self,name):
        return self._profiles[name]["role"]


async def run_ensemble(primary,registry,names,question,*,history,instructions,revision,
                       budget,maximum_reserved,recheck,deadline_seconds=45):
    if (not isinstance(registry,SpecialistRegistry) or type(names) is not list
            or not 1<=len(names)<=MAX_MODELS or any(type(n) is not str for n in names)
            or len(set(names))!=len(names) or type(question) is not str or not question.strip()
            or len(question.encode())>1024 or type(budget) is not int or not 1<=budget<=MAX_PER_CANDIDATE
            or type(maximum_reserved) is not int or not budget*(1+len(names))<=maximum_reserved<=MAX_RESERVED
            or type(history) is not tuple or type(instructions) is not str or not callable(recheck)
            or type(deadline_seconds) is not int or not 1<=deadline_seconds<=45):
        raise ValueError("invalid bounded ensemble request")
    inventory={row["id"]:row for row in registry.inventory()}
    if any(n not in inventory for n in names):
        raise ValueError("unknown specialist selection")
    if any(inventory[n]["model_digest"]==primary.model_digest for n in names):
        raise ValueError("primary cannot also be a specialist")
    deadline=time.monotonic()+deadline_seconds
    candidates=[]
    # All generators see the same original question/history; no generated
    # output becomes instructions for another generator.
    for name in ["jeeves"]+names:
        recheck()
        if time.monotonic()>=deadline:
            raise TimeoutError("ensemble deadline exceeded")
        runtime=None
        backend=primary
        role="primary"
        if name!="jeeves":
            runtime=registry.load(name,primary_digest=primary.model_digest)
            backend=NativeRuntimeLocalModel(runtime)
            role=registry.role(name)
        try:
            local=OfflineAISession(backend)
            local.history=history
            # Preserve system authority identically. Role hints are explicit
            # appended user-prompt text, not a replacement system prompt.
            local.instructions=instructions
            prompt=question.strip()
            if role!="primary":
                prompt+="\n\nIndependent review approach: "+_INSTRUCTIONS[role]
            local.preview_context(prompt,budget)
            remaining=deadline-time.monotonic()
            if remaining<=0:
                raise TimeoutError("ensemble deadline exceeded")
            answer=await asyncio.wait_for(local.ask(prompt,max_output_tokens=budget,
                require_full_history=True),timeout=remaining)
            recheck()
            if (answer.model_digest!=backend.model_digest or type(answer.output_tokens) is not int
                    or not 0<=answer.output_tokens<=budget
                    or type(answer.text) is not str or not answer.text.strip()
                    or len(answer.text.encode())>16384
                    or type(answer.execution_receipt_digest) is not str
                    or not _PIN.fullmatch(answer.execution_receipt_digest)):
                raise RuntimeContractError("unbound specialist execution result")
            candidates.append({"profile":name,"role":role,"model_digest":backend.model_digest,
                "tokenizer_digest":_model_tokenizer_digest(backend),"prompt_sha256":_sha(prompt),
                "text":answer.text,"output_sha256":_sha(answer.text),
                "execution_receipt_digest":answer.execution_receipt_digest,
                "input_tokens":answer.input_tokens,"output_tokens":answer.output_tokens,
                "citation_audit":None,"faithfulness":None})
        finally:
            # Drop the specialist references prior to opening another artifact.
            if runtime is not None:
                del runtime
            del backend
            if "local" in locals():
                del local
    recheck()
    if time.monotonic()>deadline:
        raise TimeoutError("ensemble deadline exceeded")
    from skeleton.app.jeeves_candidate_challenge import examine
    report={"schema":"skeleton.jeeves.generator-ensemble.v1","session_revision":revision,
            "question_sha256":_sha(question.strip()),"registry_sha256":registry.identity,
            "primary_model_digest":primary.model_digest,
            "independent_model_count":len({r["model_digest"] for r in candidates}),
            "reserved_output_tokens":len(candidates)*budget,
            "actual_output_tokens":sum(r["output_tokens"] for r in candidates),
            "candidates":candidates,"challenge":examine(candidates),
            "winner_selected":False,"primary_model_changed":False,"semantic_truth_verified":False,
            "transcript_committed":False,"tool_execution_authorized":False}
    report["receipt_sha256"]=digest(report)
    return report
