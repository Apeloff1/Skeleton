"""Report excludes prompt, completion, tokens, private paths and secret material."""
from __future__ import annotations
from .errors import reject

PRIVATE=frozenset((
    "prompt","completion","raw_model_output","private_path",
    "checkpoint_bytes","checkpoint_json","access_token",
    "secret","api_key","password","bearer","system_prompt",
    "unredacted_text","raw_token_ids","raw_prompt_ids",
))


def inspect_public(value:object,*,max_nodes:int=100000)->dict:
    if type(max_nodes) is not int or not 1<=max_nodes<=1000000:
        reject("privacy-node-budget")
    count=0
    denied=[]
    def walk(node,path):
        nonlocal count
        count+=1
        if count>max_nodes:
            reject("privacy-walk-budget")
        if type(node) is dict:
            for key,val in node.items():
                if type(key) is not str:
                    reject("privacy-nontext-key")
                if key.lower() in PRIVATE:
                    denied.append(path+"."+key)
                walk(val,path+"."+key)
        elif type(node) in (tuple,list):
            for index,val in enumerate(node):
                walk(val,path+f"[{index}]")
        elif node is not None and type(node) not in (str,int,float,bool):
            reject("privacy-unknown-value")
    walk(value,"root")
    return {
        "nodes_inspected":count,
        "private_fields":tuple(denied),
        "publishable":not denied,
    }


def require_public(value:object)->None:
    if not inspect_public(value)["publishable"]:
        reject("privacy-report-private-fields")
