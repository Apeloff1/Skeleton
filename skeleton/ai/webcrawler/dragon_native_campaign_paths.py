"""Original game *campaign* graph: genuine branching, optional levels, endings.

Different from per-level route diversity: a player makes meaningful decisions
about which actual stage to play next. This is a finite, auditable DAG with
reachable nodes, alternate endings, no cycles and no impossible progression
gates. Every ending and alternate stage route is individually enumerated.

The generated C99 engine reads this exact graph and uses actual branching
input rather than silently continuing along index+1.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from hashlib import sha256
import json

SCHEMA="skeleton.ai.dragon.native_branching_campaign.v1"
MAX_STAGES=8
MAX_ROUTES=96

@dataclass(frozen=True)
class Chapter:
    stage:int
    exits:tuple[int,...]
    ending:str|None
    role:str
    option_labels:tuple[str,...]

@dataclass(frozen=True)
class Campaign:
    schema:str
    mode:str
    chapters:tuple[Chapter,...]
    complete_routes:tuple[tuple[int,...],...]
    ending_count:int
    choice_nodes:int
    measured_difficulty:tuple[int,...]
    digest:str
    claim:str

def _enumerate(chapters:tuple[Chapter,...])->tuple[tuple[int,...],...]:
    total=len(chapters)
    paths=[]
    def visit(node,path):
        if node in path:
            raise ValueError("original campaign graph has cycle")
        route=(*path,node)
        if len(route)>total:
            raise ValueError("game route exceeds chapter count")
        if not chapters[node].exits:
            paths.append(route)
            if len(paths)>MAX_ROUTES:
                raise ValueError("original campaign route count exceeds budget")
            return
        for follower in chapters[node].exits:
            visit(follower,route)
    visit(0,())
    return tuple(paths)

def _digest(chapters,measured_difficulty):
    material={"chapters":[asdict(chapter) for chapter in chapters],
              "measured_difficulty":measured_difficulty}
    return sha256(json.dumps(material,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True).encode("ascii")).hexdigest()

def validate_campaign(campaign:Campaign)->Campaign:
    if not isinstance(campaign,Campaign) or campaign.schema!=SCHEMA:
        raise ValueError("unknown native game progression graph")
    nodes=campaign.chapters
    if not 1<=len(nodes)<=MAX_STAGES:
        raise ValueError("original game chapter count outside bounds")
    if campaign.mode not in ("linear","branching"):
        raise ValueError("unrecognized original game progression mode")
    if (not isinstance(campaign.measured_difficulty,tuple) or
            len(campaign.measured_difficulty)!=len(nodes) or
            any(type(x) is not int or not 0<=x<=100
                for x in campaign.measured_difficulty)):
        raise ValueError("native branch tension is not measured in valid bounds")
    endings=set()
    choices=0
    for index,chapter in enumerate(nodes):
        if chapter.stage!=index or len(chapter.exits)>2 or len(chapter.exits)!=len(chapter.option_labels):
            raise ValueError("uncanonical game choice node")
        if any(type(next_stage) is not int or
               next_stage<=index or next_stage>=len(nodes)
               for next_stage in chapter.exits):
            raise ValueError("nonforward, invalid or cyclic game progression")
        if len(set(chapter.exits))!=len(chapter.exits):
            raise ValueError("same game chapter cannot be a duplicate option")
        if chapter.exits and chapter.ending is not None:
            raise ValueError("game chapter cannot be both ending and connector")
        if not chapter.exits and chapter.ending not in ("discovery","mastery","finale"):
            raise ValueError("terminal game chapter must declare a real ending")
        if chapter.ending:
            endings.add(index)
        choices+=len(chapter.exits)>1
    routes=_enumerate(nodes)
    reachable={node for route in routes for node in route}
    if len(reachable)!=len(nodes):
        raise ValueError("original campaign has an unreachable or dead stage")
    if campaign.mode=="linear":
        if routes!=(tuple(range(len(nodes))),):
            raise ValueError("linear game path must be explicit single chain")
    elif len(nodes)>=3:
        if len(endings)<2 or len(routes)<2 or choices<1:
            raise ValueError("branching original game needs real choices and two endings")
    if (campaign.complete_routes!=routes or
            campaign.ending_count!=len(endings) or
            campaign.choice_nodes!=choices or
            campaign.digest!=_digest(nodes,campaign.measured_difficulty)):
        raise ValueError("native branching game progression receipt forged")
    return campaign

def design_campaign(stages:int,*,seed:int=0,
                    mode:str="branching",intensity:str="balanced",
                    stage_difficulty:tuple[int,...]|None=None)->Campaign:
    if type(stages) is not int or not 1<=stages<=MAX_STAGES:
        raise ValueError("original campaign requires one to eight actual stages")
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("original campaign routing seed invalid")
    if mode not in ("linear","branching") or intensity not in (
        "gentle","balanced","challenging","spicy"):
        raise ValueError("original branching style or challenge profile unrecognized")
    if stage_difficulty is not None:
        if (not isinstance(stage_difficulty,tuple) or
                len(stage_difficulty)!=stages or
                any(type(score) is not int or not 0<=score<=100
                    for score in stage_difficulty)):
            raise ValueError("campaign path difficulty must be measured for each real chapter")
    chapters=[]
    for n in range(stages):
        if mode=="linear" or stages<3:
            targets=(n+1,) if n+1<stages else ()
        elif n>=stages-2:
            targets=()
        else:
            # The next stage is the exploration path; the skip edge is a
            # deliberate faster but more demanding shortcut. Both end in
            # reachable playable authored stages. Prefer neither by force.
            targets=(n+1,n+2) if n+2<stages else (n+1,)
        if not targets:
            ending=("discovery" if n==stages-2 and mode=="branching" and
                    stages>=3 else
                    "mastery" if mode=="branching" and stages>=3 else "finale")
        else:
            ending=None
        if len(targets)==2 and stage_difficulty is not None:
            pair=sorted(targets,key=lambda target:
                        (stage_difficulty[target],target))
            if intensity in ("challenging","spicy"):
                pair.reverse()
            targets=tuple(pair)
            names=tuple(
                ("higher tension" if stage_difficulty[target]>=50 else
                 "lower tension")+
                f" route (measured {stage_difficulty[target]}/100)"
                for target in targets
            )
        else:
            names=("explore next chapter","take optional chapter shortcut")[:len(targets)]
        role=("ending" if ending else
              "fork" if len(targets)>1 else "connector")
        chapters.append(Chapter(n,targets,ending,role,names))
    nodes=tuple(chapters)
    ratings=stage_difficulty if stage_difficulty is not None else (0,)*stages
    routes=_enumerate(nodes)
    result=Campaign(
        schema=SCHEMA,mode=mode,chapters=nodes,complete_routes=routes,
        ending_count=sum(not chapter.exits for chapter in nodes),
        choice_nodes=sum(len(chapter.exits)>1 for chapter in nodes),
        measured_difficulty=ratings,
        digest=_digest(nodes,ratings),
        claim=("original branching level progression; player enjoyment and "
               "relative shortcut challenge not certified by human playtests"),
    )
    return validate_campaign(result)

def graph_header(graph:Campaign)->str:
    validate_campaign(graph)
    count=len(graph.chapters)
    counts=",".join(str(len(x.exits)) for x in graph.chapters)
    destinations=",\n".join(
        "  {"+",".join(str(v) for v in (chapter.exits+(-1,)*(2-len(chapter.exits))))+"}"
        for chapter in graph.chapters
    )
    terminal=",".join(str(int(not chapter.exits)) for chapter in graph.chapters)
    complexity=",".join(str(x) for x in graph.measured_difficulty)
    return (
        "/* Original game campaign graph: zero-based stage destinations. */\n"
        "static const int dragon_branch_count[LEVEL_COUNT]={"+counts+"};\n"
        "static const int dragon_branch_next[LEVEL_COUNT][2]={\n"+
        destinations+"\n};\n"
        "static const int dragon_branch_ending[LEVEL_COUNT]={"+terminal+"};\n"
        "static const int dragon_stage_tension[LEVEL_COUNT]={"+complexity+"};\n"
    )

def graph_report(graph:Campaign)->dict:
    validate_campaign(graph)
    return asdict(graph)

def verify_graph_report(doc:dict)->Campaign:
    if not isinstance(doc,dict) or doc.get("schema")!=SCHEMA:
        raise ValueError("unknown game campaign graph document")
    rows=doc.get("chapters")
    if not isinstance(rows,list):
        raise ValueError("campaign graph chapters must be an array")
    try:
        chapters=tuple(Chapter(
            stage=x["stage"],exits=tuple(x["exits"]),
            ending=x["ending"],role=x["role"],
            option_labels=tuple(x["option_labels"]),
        ) for x in rows)
        candidate=Campaign(
            schema=doc["schema"],mode=doc["mode"],chapters=chapters,
            complete_routes=tuple(tuple(x) for x in doc["complete_routes"]),
            ending_count=doc["ending_count"],choice_nodes=doc["choice_nodes"],
            measured_difficulty=tuple(doc["measured_difficulty"]),
            digest=doc["digest"],claim=doc["claim"],
        )
    except (TypeError,KeyError,ValueError) as exc:
        raise ValueError("invalid original game graph shape") from exc
    return validate_campaign(candidate)
