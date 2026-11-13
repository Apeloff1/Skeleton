"""Finite GraphQL introspection type topology from already fetched JSON.

Never issues an introspection query, authenticates to an endpoint, executes
a mutation, subscribes, loads schema directives or resolves source URLs.
The declared type graph is external unreviewed documentation, not a
compiler-verified contract or permission to use a remote API.
"""
from __future__ import annotations

import hashlib
import json
import re

from .research_projection import ResearchFormatError,ResearchProjection,check_text,project_lines
from .sbom_graph import SBOMComponent,SBOMEdge,make_sbom_graph
from .sbom_topology import inspect_sbom_topology
from .sbom_parsing import unique,nonfinite

GRAPHQL_MEDIA_TYPES=frozenset({
    "application/vnd.graphql.introspection+json",
    "application/graphql-response+json",
})
_NAME=re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,100}$")
_TYPES=frozenset({"OBJECT","INTERFACE","UNION","ENUM","INPUT_OBJECT","SCALAR"})
_BUILTIN=frozenset({"String","ID","Int","Float","Boolean"})


def _type_ref(node:object)->str:
    for _ in range(12):
        if not isinstance(node,dict):
            raise ResearchFormatError("GraphQL type-ref envelope invalid")
        kind=node.get("kind")
        if kind in ("LIST","NON_NULL"):
            node=node.get("ofType")
            continue
        name=node.get("name")
        if not isinstance(name,str) or not _NAME.fullmatch(name):
            raise ResearchFormatError("GraphQL named type reference invalid")
        return name
    raise ResearchFormatError("GraphQL list/non-null wrapper depth exceeded")


def _json(raw:str,*,max_chars:int)->dict:
    check_text(raw,max_chars=max_chars)
    try:
        body=json.loads(raw,object_pairs_hook=unique,parse_constant=nonfinite)
    except (ValueError,RecursionError) as exc:
        raise ResearchFormatError("invalid GraphQL introspection JSON") from exc
    if not isinstance(body,dict) or not isinstance(body.get("data"),dict):
        raise ResearchFormatError("GraphQL introspection data envelope absent")
    schema=body["data"].get("__schema")
    if not isinstance(schema,dict):
        raise ResearchFormatError("GraphQL introspection schema object missing")
    return schema


def extract_graphql_schema(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    schema=_json(raw,max_chars=max_chars)
    types=schema.get("types")
    if not isinstance(types,list) or not 1<=len(types)<=256:
        raise ResearchFormatError("GraphQL type capacity exceeded")
    entries={}
    for row in types:
        if not isinstance(row,dict):
            raise ResearchFormatError("malformed GraphQL introspection type")
        name=row.get("name")
        kind=row.get("kind")
        if not isinstance(name,str) or not _NAME.fullmatch(name) or kind not in _TYPES:
            raise ResearchFormatError("unsupported GraphQL type identity/kind")
        if name in entries:
            raise ResearchFormatError("duplicate GraphQL type")
        if not name.startswith("__"):
            entries[name]=row
    if not entries:
        raise ResearchFormatError("GraphQL schema has no user-declared types")
    nodes=[]
    edges=[]
    unknown=set()
    relation_counts={}
    self_references=set()
    field_count=arg_count=0
    for name,row in sorted(entries.items()):
        nodes.append(SBOMComponent(
            identity="gql_"+name,name=name,version="",ecosystem="graphql",
        ))
        targets=set()
        for field_key in ("fields","inputFields"):
            fields=row.get(field_key,[])
            if fields is None:
                fields=[]
            if not isinstance(fields,list) or len(fields)>128:
                raise ResearchFormatError("GraphQL field capacity exceeded")
            for field in fields:
                if not isinstance(field,dict) or not isinstance(field.get("name"),str):
                    raise ResearchFormatError("GraphQL field object invalid")
                if not _NAME.fullmatch(field["name"]):
                    raise ResearchFormatError("invalid GraphQL field label")
                field_count+=1
                if field_count>8192:
                    raise ResearchFormatError("GraphQL aggregate field capacity exceeded")
                targets.add(_type_ref(field.get("type")))
                args=field.get("args",[])
                if not isinstance(args,list) or len(args)>32:
                    raise ResearchFormatError("GraphQL arguments per field exceeded")
                for arg in args:
                    if not isinstance(arg,dict):
                        raise ResearchFormatError("malformed GraphQL field argument")
                    arg_count+=1
                    if arg_count>8192:
                        raise ResearchFormatError("GraphQL aggregate arguments exceeded")
                    targets.add(_type_ref(arg.get("type")))
        for field_key in ("interfaces","possibleTypes"):
            fields=row.get(field_key,[])
            if fields is None:
                fields=[]
            if not isinstance(fields,list) or len(fields)>128:
                raise ResearchFormatError("GraphQL interface/union bound exceeded")
            for related in fields:
                targets.add(_type_ref(related))
        for target in sorted(targets):
            if target==name:
                self_references.add(name)
            elif target in entries:
                edges.append(SBOMEdge("gql_"+name,"gql_"+target))
            elif target not in _BUILTIN and not target.startswith("__"):
                unknown.add(target)
            if len(edges)>2048:
                raise ResearchFormatError("GraphQL graph edge bound exceeded")
        relation_counts[name]=len(targets)
    graph=make_sbom_graph(nodes,edges,max_components=256)
    topology=inspect_sbom_topology(graph)
    roots=[]
    for label in ("queryType","mutationType","subscriptionType"):
        item=schema.get(label)
        if item is not None:
            if not isinstance(item,dict) or not isinstance(item.get("name"),str):
                raise ResearchFormatError("GraphQL root type invalid")
            name=item["name"]
            if name not in entries:
                raise ResearchFormatError("GraphQL root references unknown declared type")
            roots.append(label.replace("Type",""))
    # Root names are not surfaced as operator commands or endpoints.
    stats=[
        "GraphQL schema: external introspection source only",
        f"Declared types: {len(entries)}; user fields: {field_count}; args: {arg_count}",
        f"Named type graph relations: {len(edges)}; unknown type names: {len(unknown)}",
        f"Direct recursive types: {len(self_references)}",
        f"Strong cyclic type groups: {topology.cyclic_strong_components}; "
        f"cycle member types: {topology.truly_cyclic_nodes}",
        f"Maximum reverse type impact: {topology.maximum_reverse_impact}; "
        f"longest condensed type chain: {topology.longest_condensed_chain}",
        f"Declared root categories: {', '.join(roots) or '[none]'}",
        f"GraphQL source graph SHA256: {graph.graph_digest}",
        "Operations, subscriptions, directives and remote schemas: not executed",
    ]
    return project_lines(stats,title="GraphQL introspection topology",max_chars=max_chars)
