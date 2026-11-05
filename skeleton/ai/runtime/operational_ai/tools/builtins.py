"""Auditable zero-network built-in tools; no process execution or shells."""
from __future__ import annotations
import hashlib
from .catalog import ToolCatalog,ToolDefinition
from .filesystem import ReadOnlyWorkspace
from ..authority.canonical import ContractViolation,sha256


def register_builtins(catalog:ToolCatalog,*,workspace:ReadOnlyWorkspace|None=None)->None:
    catalog.register(ToolDefinition("hash_text",{"type":"object",
        "properties":{"text":{"type":"string","maxLength":8192,"allowEmpty":True}},
        "required":["text"]},"readonly",description="SHA-256 of supplied UTF-8 text"),
        lambda data:{"sha256":sha256(data["text"].encode("utf-8")),"bytes":len(data["text"].encode("utf-8"))})
    catalog.register(ToolDefinition("count_text",{"type":"object",
        "properties":{"text":{"type":"string","maxLength":8192,"allowEmpty":True}},
        "required":["text"]},"readonly",description="Bounded local word and character counts"),
        lambda data:{"characters":len(data["text"]),"words":len(data["text"].split()),
                     "bytes":len(data["text"].encode("utf-8"))})
    if workspace is not None:
        catalog.register(workspace.definition(),workspace.execute)
