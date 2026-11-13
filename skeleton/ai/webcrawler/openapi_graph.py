"""Bounded, nonexecuting OpenAPI operation/schema dependency projection.

A source document's HTTP verbs, security schemes, examples and remote
servers are *descriptions*, not authority. This module never performs
HTTP methods, resolves remote refs, imports clients or trusts licenses.
Local schema pointers are counted structurally, not evaluated as a validator.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
import hashlib
import json
import re
from typing import Any

from .research_projection import ResearchFormatError
from .sbom_graph import SBOMComponent, SBOMEdge, make_sbom_graph
from .sbom_topology import inspect_sbom_topology

_METHODS=("get","head","post","put","patch","delete","options","trace")
_SCHEMA_NAME=re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_LOCAL_REF=re.compile(r"^#/components/schemas/([A-Za-z_][A-Za-z0-9_.-]{0,127})$")
_MAX_NODES=8192
_MAX_DEPTH=24
_MAX_SCHEMAS=256
_MAX_OPERATIONS=512


@dataclass(frozen=True)
class APIOperationAnalysis:
    method:str
    path:str
    request_schema_refs:int
    response_schema_refs:int
    security_requirement_sets:int
    declared_status_codes:int
    unverified:bool=True


@dataclass(frozen=True)
class APIContractTopology:
    version:str
    path_count:int
    operation_count:int
    declared_schema_count:int
    local_schema_references:int
    unresolved_local_references:int
    ignored_external_references:int
    cyclic_schema_nodes:int
    schema_cycles:int
    longest_schema_dependency_chain:int
    maximum_schema_reverse_impact:int
    operations_with_security_requirements:int
    operations:tuple[APIOperationAnalysis,...]
    method_counts:tuple[tuple[str,int],...]
    topology_digest:str
    remote_schema_resolved:bool=False
    HTTP_executed:bool=False
    schema_validated:bool=False


def _digest(body:object)->str:
    return hashlib.sha256(
        json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    ).hexdigest()


def _ref_targets(obj:Any,*,max_nodes:int=_MAX_NODES)->tuple[list[str],int]:
    """Inspect known structural child positions, not arbitrary $ref-ish keys."""
    stack=[(obj,0)]
    local=[]
    external=0
    visited=0
    while stack:
        node,depth=stack.pop()
        visited+=1
        if visited>max_nodes or depth>_MAX_DEPTH:
            raise ResearchFormatError("OpenAPI schema traversal limit exceeded")
        if not isinstance(node,dict):
            if isinstance(node,bool):
                continue
            raise ResearchFormatError("OpenAPI schema node invalid")
        if "$ref" in node:
            value=node["$ref"]
            if not isinstance(value,str) or len(value)>4096:
                raise ResearchFormatError("OpenAPI reference syntax invalid")
            match=_LOCAL_REF.fullmatch(value)
            if match:
                local.append(match.group(1))
            else:
                external+=1
            # Adjacent local or remote ref properties cannot be followed.
            continue
        for field in ("properties","patternProperties","dependentSchemas"):
            value=node.get(field,{})
            if not isinstance(value,dict) or len(value)>256:
                raise ResearchFormatError("OpenAPI schema child map invalid")
            stack.extend((child,depth+1) for child in value.values())
        for field in ("allOf","anyOf","oneOf","prefixItems"):
            value=node.get(field,[])
            if not isinstance(value,list) or len(value)>128:
                raise ResearchFormatError("OpenAPI combinator width exceeded")
            stack.extend((child,depth+1) for child in value)
        for field in ("items","additionalProperties","not","contains"):
            value=node.get(field)
            if value is not None:
                stack.append((value,depth+1))
    return local,external


def _operation_refs(op:dict)->tuple[int,int,int,int,int]:
    req=0
    resp=0
    ignored=0
    body=op.get("requestBody")
    if isinstance(body,dict) and "$ref" not in body:
        content=body.get("content",{})
        if not isinstance(content,dict) or len(content)>32:
            raise ResearchFormatError("OpenAPI request content map invalid")
        for media in content.values():
            if not isinstance(media,dict):
                raise ResearchFormatError("OpenAPI request media invalid")
            if "schema" in media:
                a,b=_ref_targets(media["schema"])
                req+=len(a)
                ignored+=b
    responses=op.get("responses",{})
    if not isinstance(responses,dict) or len(responses)>64:
        raise ResearchFormatError("OpenAPI response map invalid")
    valid_codes=0
    for code,reply in responses.items():
        if not isinstance(code,str):
            raise ResearchFormatError("OpenAPI response key invalid")
        if not re.fullmatch(r"(?:[1-5][0-9]{2}|default)",code):
            continue
        valid_codes+=1
        if not isinstance(reply,dict):
            raise ResearchFormatError("OpenAPI response value invalid")
        if "$ref" in reply:
            ignored+=1
            continue
        content=reply.get("content",{})
        if not isinstance(content,dict) or len(content)>32:
            raise ResearchFormatError("OpenAPI response media map invalid")
        for media in content.values():
            if not isinstance(media,dict):
                raise ResearchFormatError("OpenAPI response media invalid")
            if "schema" in media:
                a,b=_ref_targets(media["schema"])
                resp+=len(a)
                ignored+=b
    security=op.get("security",[])
    if not isinstance(security,list) or len(security)>64:
        raise ResearchFormatError("OpenAPI security list capacity exceeded")
    return req,resp,ignored,len(security),valid_codes


def inspect_openapi_graph(source:dict)->APIContractTopology:
    if not isinstance(source,dict):
        raise ResearchFormatError("OpenAPI graph requires a parsed source object")
    version=source.get("openapi")
    if not isinstance(version,str) or not version.startswith("3.") or len(version)>16:
        raise ResearchFormatError("OpenAPI 3.x only")
    paths=source.get("paths")
    if not isinstance(paths,dict) or not 1<=len(paths)<=256:
        raise ResearchFormatError("OpenAPI operation path count invalid")
    components=source.get("components",{})
    if not isinstance(components,dict):
        raise ResearchFormatError("OpenAPI components must be a mapping")
    schemas=components.get("schemas",{})
    if not isinstance(schemas,dict) or len(schemas)>_MAX_SCHEMAS:
        raise ResearchFormatError("OpenAPI schema catalog too large")
    nodes=[]
    links=[]
    unresolved=set()
    external=0
    local_refs=0
    known=set(schemas)
    for name in sorted(schemas):
        if not isinstance(name,str) or not _SCHEMA_NAME.fullmatch(name):
            raise ResearchFormatError("OpenAPI schema identity invalid")
        nodes.append(SBOMComponent(
            identity="schema_"+name,name=name,version="",ecosystem="openapi",
        ))
    for name,body in sorted(schemas.items()):
        targets,ext=_ref_targets(body)
        external+=ext
        for target in sorted(set(targets)):
            local_refs+=targets.count(target)
            if target in known:
                if target==name:
                    # Cyclic self-schema references are recorded below via
                    # cycle-marking, not followed or unrolled.
                    unresolved.add(target)
                else:
                    links.append(SBOMEdge("schema_"+name,"schema_"+target))
            else:
                unresolved.add(target)
    operations=[]
    kinds=Counter()
    for path,endpoint in sorted(paths.items()):
        if not isinstance(path,str) or not path.startswith("/") or len(path)>256:
            raise ResearchFormatError("OpenAPI path syntax invalid")
        if not isinstance(endpoint,dict):
            raise ResearchFormatError("OpenAPI endpoint mapping invalid")
        for method in _METHODS:
            if method not in endpoint:
                continue
            op=endpoint[method]
            if not isinstance(op,dict):
                raise ResearchFormatError("OpenAPI operation mapping invalid")
            request_count,response_count,ignored,security_count,codes=_operation_refs(op)
            external+=ignored
            kinds[method]+=1
            operations.append(APIOperationAnalysis(
                method=method.upper(),path=path,
                request_schema_refs=request_count,
                response_schema_refs=response_count,
                security_requirement_sets=security_count,
                declared_status_codes=codes,
            ))
            if len(operations)>_MAX_OPERATIONS:
                raise ResearchFormatError("OpenAPI operation count exceeded")
    # Reuse the exact finite SBOM SCC/reverse-impact algorithm. This is
    # only graph mathematics; an API schema is NOT a software bill of materials.
    topology=None
    if nodes:
        graph=make_sbom_graph(nodes,links,max_components=256,max_edges=2048)
        topology=inspect_sbom_topology(graph)
    payload={
        "version":version,"paths":len(paths),
        "operations":[(x.method,x.path,x.request_schema_refs,
                       x.response_schema_refs,x.security_requirement_sets,
                       x.declared_status_codes) for x in operations],
        "schemas":sorted(schemas),
        "links":sorted((x.source,x.target) for x in links),
        "unknown":sorted(unresolved),"remote":external,
    }
    return APIContractTopology(
        version=version,path_count=len(paths),operation_count=len(operations),
        declared_schema_count=len(nodes),local_schema_references=local_refs,
        unresolved_local_references=len(unresolved),
        ignored_external_references=external,
        cyclic_schema_nodes=topology.truly_cyclic_nodes if topology else 0,
        schema_cycles=topology.cyclic_strong_components if topology else 0,
        longest_schema_dependency_chain=topology.longest_condensed_chain if topology else 0,
        maximum_schema_reverse_impact=topology.maximum_reverse_impact if topology else 0,
        operations_with_security_requirements=sum(x.security_requirement_sets>0 for x in operations),
        operations=tuple(operations),
        method_counts=tuple(sorted(kinds.items())),
        topology_digest=_digest(payload),
    )


def summarize_openapi_graph(topology:APIContractTopology)->tuple[str,...]:
    if not isinstance(topology,APIContractTopology):
        raise ResearchFormatError("typed OpenAPI topology required")
    methods=", ".join(f"{k.upper()}={v}" for k,v in topology.method_counts)
    return (
        f"API contract graph: paths={topology.path_count}; operations={topology.operation_count}",
        f"API operation methods: {methods or '[none]'}",
        f"Schema catalog: {topology.declared_schema_count}; "
        f"local references: {topology.local_schema_references}; "
        f"unresolved local references: {topology.unresolved_local_references}",
        f"External source reference declarations ignored: {topology.ignored_external_references}",
        f"Schema cycles: {topology.schema_cycles}; true cyclic schemas: {topology.cyclic_schema_nodes}",
        f"Schema longest condensed chain: {topology.longest_schema_dependency_chain}; "
        f"maximum reverse impact: {topology.maximum_schema_reverse_impact}",
        f"Operation security lists declared: {topology.operations_with_security_requirements}",
        f"API schema graph SHA256: {topology.topology_digest}",
        "API methods, remote references and security grants: NOT executed or verified",
    )
