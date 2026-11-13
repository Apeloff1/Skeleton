"""Execute all repository-controlled adversarial cases against Python production gates."""
from __future__ import annotations
from importlib import resources
from types import SimpleNamespace
import json
from ..contracts import ContractViolation,refuse,safe_json
from ..inputs import normalize
from ..operations import operations
from ..contracts import token,identifier,utf8,number,nonnegative
from ..deployment_profile import LaptopProfile
from ..result_protocol import verify_turn_receipt
from ..health_levels import classify
from ..runtime_state import RuntimeState
from ..privacy import safe_record
from ..request_custody import RequestCustody
from ..native_identity import verify as verify_native
from ..postcommit_stream import chunks
from ..client import LaptopClient

OPERATIONS=operations()
DOMAINS=OPERATIONS+("token","identifier","text","seed","temperature",
    "profile","receipt","health","state","strict_json","privacy",
    "request_custody","native_identity","consent","client","postcommit_stream")
if len(DOMAINS)!=26:raise RuntimeError("laptop qualification boundary inventory changed")

class _Backend:
    def __init__(self,item):
        self.model_digest=item["runtime"]
        self.tokenizer_digest=item["runtime_tokenizer"]
        self.generate=(lambda *args,**kwargs:None) if item["callable"] is True else None

def execute(domain,payload):
    if domain in OPERATIONS:
        return normalize(domain,payload,SimpleNamespace(input_bytes=32768))
    if domain=="token":return token(payload)
    if domain=="identifier":return identifier(payload)
    if domain=="text":return utf8(payload,maximum=64)
    if domain=="seed":return nonnegative(payload,maximum=2**32-1)
    if domain=="temperature":return number(payload,minimum=0.000000001,maximum=2)
    if domain=="profile":return LaptopProfile(**payload).to_record()
    if domain=="receipt":return verify_turn_receipt(payload,
                                  model_sha256="a"*64,tokenizer_sha256="b"*64)
    if domain=="health":return classify(payload)
    if domain=="state":
        if type(payload) is not dict or set(payload)!={"next","digest"}:
            refuse("wrong state transition fixture shape")
        return RuntimeState().transition(payload["next"],
                                         evidence_sha256=payload["digest"])
    if domain=="strict_json":
        if type(payload) is not dict or set(payload)!={"raw"} or type(payload["raw"]) is not str:
            refuse("untrusted JSON fixture")
        return safe_json(payload["raw"].encode("utf-8","strict"))
    if domain=="privacy":return safe_record(payload)
    if domain=="request_custody":return RequestCustody(**payload).sha256()
    if domain=="native_identity":
        if type(payload) is not dict or set(payload)!={"approved","tokenizer",
            "runtime","runtime_tokenizer","callable"}:refuse("unbound model identity")
        return verify_native(_Backend(payload),payload["approved"],payload["tokenizer"])
    if domain=="consent":
        from skeleton.ai.runtime.operational_ai.trust_gates.control.consent import ConsentAuthority
        if type(payload) is not dict or set(payload)!={"tenant","source","operator",
            "now","expires","approved","verify_now","target_tenant","target_source","repeat"}:
            refuse("unbound consent scenario")
        authority=ConsentAuthority(b"X"*32)
        grant=authority.issue(tenant=payload["tenant"],source_id=payload["source"],
                 operator=payload["operator"],now=payload["now"],
                 expires=payload["expires"],approved=payload["approved"])
        result=authority.verify(grant,tenant=payload["target_tenant"],
                   source_id=payload["target_source"],now=payload["verify_now"])
        if payload["repeat"] is True:
            authority.verify(grant,tenant=payload["target_tenant"],
                source_id=payload["target_source"],now=payload["verify_now"])
        elif payload["repeat"] is not False:refuse("invalid consent replay toggle")
        return result
    if domain=="client":
        if type(payload) is not dict or set(payload)!={"host","port","bearer","timeout"}:
            refuse("client setup shape mismatch")
        return LaptopClient(**payload).address
    if domain=="postcommit_stream":
        if type(payload) is not dict or set(payload)!={"receipt","chunk_bytes","max_chunks"}:
            refuse("stream fixture fields mismatch")
        return chunks(payload["receipt"],chunk_bytes=payload["chunk_bytes"],
                      max_chunks=payload["max_chunks"])
    refuse("unknown source-backed AI gate")

def run_domain(name):
    if name not in DOMAINS:refuse("unregistered laptop assurance domain")
    base=resources.files(__package__).joinpath("scenarios",name)
    entries=sorted(x for x in base.iterdir() if x.name.endswith(".json"))
    if len(entries)!=14:refuse("missing source qualification cases")
    result={"domain":name,"cases":0,"accepted":0,"rejected":0,"redacted":0}
    identifiers=set()
    for file in entries:
        if not file.is_file() or file.is_symlink():refuse("fixture path not regular")
        raw=file.read_bytes()
        if not 1<=len(raw)<=131072:refuse("source fixture byte ceiling")
        case=safe_json(raw,ceiling=131072)
        if type(case) is not dict or set(case)!={"schema","id","domain","expected",
            "payload","reason","threat","authority_boundary","operator_proof",
            "release_claim"}:refuse("source fixture is not exact schema")
        if (case["schema"]!="laptop-qualification-case.v1" or
            case["domain"]!=name or case["id"] in identifiers or
            case["expected"] not in ("accept","reject","no_leak") or
            case["release_claim"] is not False):
            refuse("ambiguous scenario identifier or qualification authority")
        identifiers.add(case["id"])
        result["cases"]+=1
        try:out=execute(name,case["payload"])
        except (ContractViolation,TypeError,ValueError):
            if case["expected"]!="reject":raise
            result["rejected"]+=1
        else:
            if case["expected"]=="reject":refuse("insecure fixture admitted")
            if case["expected"]=="no_leak":
                if "SENSITIVE_NEVER_ECHO" in json.dumps(out,ensure_ascii=True,sort_keys=True):
                    refuse("telemetry leaked untrusted sensitive input")
                result["redacted"]+=1
            else:result["accepted"]+=1
    if result["cases"]!=14 or result["accepted"]+result["rejected"]+result["redacted"]!=14:
        refuse("expected casebook accounting not met")
    return result

def run_all():
    return tuple(run_domain(name) for name in DOMAINS)
