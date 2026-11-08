"""Finite AsyncAPI v2.6/3.x service-event contract inventory, no broker calls.

Source-published channels, servers, message schemas, auth strategies and
operation descriptions are untrusted declarations. They cannot subscribe,
publish, perform authentication or widen any canonical crawler authority.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
from typing import Any

from .research_projection import ResearchFormatError,ResearchProjection,check_text,project_lines
from .sbom_parsing import unique,nonfinite

ASYNCAPI_MEDIA_TYPES=frozenset({
    "application/vnd.asyncapi+json",
    "application/asyncapi+json",
})
_NAME=re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_LOCAL_MESSAGE=re.compile(r"^#/components/messages/([A-Za-z_][A-Za-z0-9_.-]{0,127})$")
_LOCAL_CHANNEL=re.compile(r"^#/channels/([A-Za-z_][A-Za-z0-9_.-]{0,127})$")


def _map(value:object,*,maximum:int,label:str)->dict:
    if not isinstance(value,dict) or len(value)>maximum:
        raise ResearchFormatError("AsyncAPI "+label+" map capacity invalid")
    return value


def _json(raw:str,*,max_chars:int)->dict:
    check_text(raw,max_chars=max_chars)
    try:
        root=json.loads(raw,object_pairs_hook=unique,parse_constant=nonfinite)
    except (ValueError,RecursionError) as exc:
        raise ResearchFormatError("AsyncAPI JSON malformed") from exc
    if not isinstance(root,dict):
        raise ResearchFormatError("AsyncAPI root must be an object")
    return root


def _message_ref(item:object,known:set[str])->tuple[int,int]:
    if not isinstance(item,dict):
        raise ResearchFormatError("AsyncAPI message reference must be an object")
    if "$ref" not in item:
        # Inlined messages contain arbitrary untrusted schema bodies;
        # no external payload schema is interpreted or fetched.
        return 0,0
    ref=item["$ref"]
    if not isinstance(ref,str) or len(ref)>4096:
        raise ResearchFormatError("AsyncAPI message reference invalid")
    match=_LOCAL_MESSAGE.fullmatch(ref)
    if match is None:
        return 0,1
    return (1,0) if match.group(1) in known else (0,1)


def extract_asyncapi(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    root=_json(raw,max_chars=max_chars)
    version=root.get("asyncapi")
    if not isinstance(version,str) or not (
        version.startswith("2.6.") or version.startswith("3.")
    ) or len(version)>16:
        raise ResearchFormatError("unsupported AsyncAPI version")
    channels=_map(root.get("channels"),maximum=256,label="channel")
    if not channels:
        raise ResearchFormatError("AsyncAPI document has no channels")
    components=_map(root.get("components",{}),maximum=64,label="component")
    messages=_map(components.get("messages",{}),maximum=256,label="message")
    known=set(messages)
    for name,item in messages.items():
        if not isinstance(name,str) or not _NAME.fullmatch(name):
            raise ResearchFormatError("AsyncAPI message identity invalid")
        if not isinstance(item,dict):
            raise ResearchFormatError("AsyncAPI message object invalid")
    operations=Counter()
    refs=missing=0
    for path,channel in channels.items():
        if (not isinstance(path,str) or not path or len(path)>256
                or any(ord(c)<32 for c in path)):
            raise ResearchFormatError("AsyncAPI channel identifier invalid")
        if not isinstance(channel,dict):
            raise ResearchFormatError("AsyncAPI channel record invalid")
        if "$ref" in channel:
            # Local and remote channel aliases cannot create subscriptions.
            missing+=1
            continue
        if version.startswith("2.6."):
            for direction in ("publish","subscribe"):
                if direction not in channel:
                    continue
                op=channel[direction]
                if not isinstance(op,dict):
                    raise ResearchFormatError("AsyncAPI operation object invalid")
                operations[direction]+=1
                message=op.get("message")
                if message is not None:
                    if isinstance(message,dict) and "oneOf" in message:
                        options=message["oneOf"]
                        if not isinstance(options,list) or len(options)>64:
                            raise ResearchFormatError("AsyncAPI message variant limit")
                        for option in options:
                            yes,no=_message_ref(option,known)
                            refs+=yes
                            missing+=no
                    else:
                        yes,no=_message_ref(message,known)
                        refs+=yes
                        missing+=no
        else:
            channel_messages=_map(
                channel.get("messages",{}),maximum=64,label="channel message",
            )
            for entry in channel_messages.values():
                yes,no=_message_ref(entry,known)
                refs+=yes
                missing+=no
    if version.startswith("3."):
        declared_ops=_map(root.get("operations",{}),
                          maximum=512,label="operation")
        for name,op in declared_ops.items():
            if not isinstance(name,str) or len(name)>128 or not isinstance(op,dict):
                raise ResearchFormatError("AsyncAPI operation identity invalid")
            action=op.get("action")
            if action not in ("send","receive"):
                raise ResearchFormatError("AsyncAPI 3 operation action invalid")
            ch=op.get("channel")
            if not isinstance(ch,dict):
                raise ResearchFormatError("AsyncAPI operation channel ref invalid")
            ref=ch.get("$ref")
            match=_LOCAL_CHANNEL.fullmatch(ref) if isinstance(ref,str) else None
            if match is None or match.group(1) not in channels:
                missing+=1
            operations[action]+=1
            messages_ref=op.get("messages",[])
            if not isinstance(messages_ref,list) or len(messages_ref)>64:
                raise ResearchFormatError("AsyncAPI operation messages cap exceeded")
            for entry in messages_ref:
                yes,no=_message_ref(entry,known)
                refs+=yes
                missing+=no
    total=sum(operations.values())
    if total>512:
        raise ResearchFormatError("AsyncAPI operation capacity exceeded")
    digest=hashlib.sha256(
        json.dumps({
            "version":version,"channels":sorted(channels),
            "messages":sorted(messages),"operations":sorted(operations.items()),
            "refs":refs,"unknown":missing,
        },sort_keys=True,separators=(",",":")).encode()
    ).hexdigest()
    lines=[
        "Asynchronous API: inert source-side event topology",
        f"AsyncAPI declared version: {version}",
        f"Channels: {len(channels)}; declared messages: {len(messages)}",
        f"Declared event operations: {total}",
        "Action distribution: "+", ".join(
            f"{kind}={amount}" for kind,amount in sorted(operations.items())
        ),
        f"Resolved local message refs: {refs}; "
        f"unresolved/remote references ignored: {missing}",
        f"Async event contract SHA256: {digest}",
        "Channel, broker, auth and message actions: not executed",
    ]
    return project_lines(lines,title="AsyncAPI event source",max_chars=max_chars)
