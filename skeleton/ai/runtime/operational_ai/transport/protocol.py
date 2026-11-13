"""Strict local API messages, cursor and response contracts."""
from __future__ import annotations
from ..authority.canonical import ContractViolation,load_json,canonical_bytes
from ..authority.identity import require_id

MAX_BODY=65_536


def parse_request(raw:bytes)->tuple[str,dict]:
    data=load_json(raw,ceiling=MAX_BODY)
    if not isinstance(data,dict) or set(data)!={"operation","payload"}:
        raise ContractViolation("invalid API request envelope")
    operation=require_id(data["operation"],field="operation")
    payload=data["payload"]
    if not isinstance(payload,dict):
        raise ContractViolation("API payload must be object")
    return operation,payload


def response(status:str,result:dict)->bytes:
    if status not in {"ok","conflict","bad-request","denied","error"}:
        raise ContractViolation("unsupported response status")
    return canonical_bytes({"status":status,"result":result},ceiling=262_144)


def schema()->dict:
    return {"schema":"skeleton.operational-ai.local-api.v1",
            "operations":{
               "create":{"request":["system?"],"result":["session_id"]},
               "turn":{"request":["session_id","request_id","question","seed?","temperature?"],
                       "result":["receipt"]},
               "history":{"request":["session_id"],"result":["messages","revision"]},
               "status":{"request":["session_id"],"result":["state"]},
               "memory_search":{"request":["question"],"result":["hits"]},
             },"model_approval":"never-from-generation","tools":"separate-authorized-call"}
