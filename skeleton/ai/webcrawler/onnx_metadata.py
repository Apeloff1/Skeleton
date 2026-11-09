"""Minimal bounded ONNX protobuf wire scanner for graph operator statistics.

This intentionally does not import ONNX, run an inference session, decode
tensor raw_data, materialize constant payloads, open external_data locations,
resolve operator schemas or execute any graph operation. Only the embedded
top-level ModelProto->GraphProto->NodeProto wire envelopes are observed.
"""
from __future__ import annotations

from collections import Counter
import re

from .research_projection import ResearchFormatError,ResearchProjection,project_lines

ONNX_TYPES=frozenset({"application/onnx","application/x-onnx"})
_MAX_BYTES=2_097_152
_MAX_NODE_COUNT=1024
_OP=re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def _varint(data:bytes,offset:int)->tuple[int,int]:
    value=0
    for index in range(10):
        if offset>=len(data):
            raise ResearchFormatError("truncated protobuf varint")
        byte=data[offset]
        offset+=1
        if index==9 and byte>1:
            raise ResearchFormatError("protobuf integer overflows uint64")
        value|=(byte&0x7f)<<(7*index)
        if byte<128:
            return value,offset
    raise ResearchFormatError("unbounded protobuf varint")


def _fields(data:bytes,*,limit:int=8192):
    offset=0
    count=0
    while offset<len(data):
        count+=1
        if count>limit:
            raise ResearchFormatError("protobuf field count exceeded")
        tag,offset=_varint(data,offset)
        number,wire=tag>>3,tag&7
        if number<1 or number>536870911:
            raise ResearchFormatError("protobuf field identity invalid")
        if wire==0:
            value,offset=_varint(data,offset)
        elif wire in (1,5):
            end=offset+(8 if wire==1 else 4)
            if end>len(data):
                raise ResearchFormatError("protobuf fixed-width field truncated")
            value=None
            offset=end
        elif wire==2:
            width,offset=_varint(data,offset)
            if width>len(data)-offset:
                raise ResearchFormatError("protobuf length-delimited field out of bounds")
            value=data[offset:offset+width]
            offset+=width
        else:
            # Protobuf groups (3/4) are deprecated and can hide unbounded
            # recursive content. A canonical source must fail closed here.
            raise ResearchFormatError("unsupported protobuf wire type")
        yield number,wire,value


def _node(data:bytes)->str:
    operation=None
    for number,wire,value in _fields(data,limit=512):
        if number==4:
            if wire!=2 or not isinstance(value,bytes) or len(value)>64:
                raise ResearchFormatError("ONNX operator label wire type invalid")
            try:
                decoded=value.decode("ascii","strict")
            except UnicodeError as exc:
                raise ResearchFormatError("ONNX operator name encoding invalid") from exc
            if not _OP.fullmatch(decoded):
                raise ResearchFormatError("ONNX operator identifier invalid")
            if operation is not None:
                raise ResearchFormatError("duplicate ONNX operator label")
            operation=decoded
        # Attributes, domain references and node raw tensors remain inert.
    if operation is None:
        raise ResearchFormatError("ONNX graph node lacks declared operator type")
    return operation


def _graph(data:bytes)->tuple[Counter,int,int,int]:
    types=Counter()
    nodes=initializers=inputs=outputs=0
    for number,wire,value in _fields(data,limit=8192):
        if number==1:
            if wire!=2:
                raise ResearchFormatError("ONNX graph node wire framing invalid")
            nodes+=1
            if nodes>_MAX_NODE_COUNT:
                raise ResearchFormatError("ONNX graph nodes exceed finite bound")
            types[_node(value)]+=1
        elif number==5:
            if wire!=2:
                raise ResearchFormatError("ONNX initializer type invalid")
            initializers+=1
            if initializers>1024:
                raise ResearchFormatError("ONNX initializer count exceeded")
            # Not inspecting tensor metadata or raw_data on purpose.
        elif number==11:
            if wire!=2:
                raise ResearchFormatError("ONNX graph input framing invalid")
            inputs+=1
            if inputs>1024:
                raise ResearchFormatError("ONNX graph input capacity exceeded")
        elif number==12:
            if wire!=2:
                raise ResearchFormatError("ONNX graph output framing invalid")
            outputs+=1
            if outputs>1024:
                raise ResearchFormatError("ONNX graph output capacity exceeded")
    if not nodes:
        raise ResearchFormatError("ONNX graph contains no declared nodes")
    return types,initializers,inputs,outputs


def extract_onnx(
    raw:bytes,*,max_chars:int=524288,
)->ResearchProjection:
    if (type(raw) is not bytes or not 2<=len(raw)<=_MAX_BYTES
            or type(max_chars) is not int or max_chars<1):
        raise ResearchFormatError("ONNX binary source capacity exceeded")
    version=None
    graph=None
    for number,wire,value in _fields(raw,limit=8192):
        if number==1:
            if wire!=0 or version is not None:
                raise ResearchFormatError("ONNX IR version duplicated/invalid")
            version=value
        elif number==7:
            if wire!=2 or graph is not None:
                raise ResearchFormatError("ONNX model graph duplicated/invalid")
            graph=value
        # Producer labels, metadata, opset imports and external data are
        # neither resolved nor carried into the output.
    if version is None or not 1<=version<=64 or graph is None:
        raise ResearchFormatError("ONNX IR version/graph envelope missing")
    classes,weights,inputs,outputs=_graph(graph)
    lines=[
        "ML artifact: ONNX protobuf structural source inventory",
        f"Declared ONNX IR version: {version}",
        f"Top-level graph nodes: {sum(classes.values())}; "
        f"operator classes: {len(classes)}",
        f"Initializer envelopes: {weights}; graph inputs: {inputs}; "
        f"graph outputs: {outputs}",
        "Operator counts: "+", ".join(
            f"{key}={value}" for key,value in sorted(classes.items())
        ),
        "Tensor data, external references, model execution and weights: not decoded",
        "Operator classes are unverified declarations, not inference support",
    ]
    return project_lines(lines,title="ONNX graph source",max_chars=max_chars)
