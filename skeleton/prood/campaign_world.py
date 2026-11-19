"""Virtual, source-bound campaign addressing at chapter/act/scene scale.

Only the region traversal and partition arithmetic are retained. Scene data
is derived on demand; no enormous scene-object graph or provider is required.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from skeleton.prood.design_campaign import collect_package
from skeleton.prood.design_contract import DesignRequest, digest, integer
from skeleton.prood.world_design import validate_world, validate_quest


@dataclass(frozen=True, slots=True)
class CampaignScale:
    chapters: int = 100
    acts: int = 1000
    scenes: int = 9999

    def __post_init__(self):
        integer(self.chapters,"chapter count",1,100)
        integer(self.acts,"act count",self.chapters,1000)
        integer(self.scenes,"scene count",self.acts,9999)


def _start(index, total, count):
    """Zero-based boundary of an evenly partitioned nonempty sequence."""
    return (index*total+count-1)//count


def _partition(index,total,count):
    return index*count//total


@dataclass(frozen=True, slots=True)
class SceneAddress:
    ordinal: int
    chapter: int
    act: int
    scene_in_act: int
    scene_count: int
    chapter_act: int
    chapter_act_count: int

    @property
    def key(self):
        return f"C{self.chapter:03d}-A{self.act:04d}-S{self.ordinal:04d}"


@dataclass(frozen=True, slots=True)
class Region:
    key: str
    biome: str
    threat: int
    reward: int
    neighbours: tuple[str,...]


@dataclass(frozen=True, slots=True)
class Scene:
    address: SceneAddress
    region: str
    kind: str
    objective: str
    risk: int
    reward: int
    paths: tuple[str,...]
    chapter_end: bool
    campaign_end: bool


def _tour(graph,entry):
    # Stable DFS walk includes a return edge to every parent. Consecutive
    # locations (including the wrap) remain physically adjacent.
    route=[entry]
    seen={entry}
    stack=[(entry,iter(sorted(graph[entry])))]
    while stack:
        here,it=stack[-1]
        nxt=next(it,None)
        if nxt is None:
            stack.pop()
            if stack:
                route.append(stack[-1][0])
            continue
        if nxt not in seen:
            route.append(nxt)
            seen.add(nxt)
            stack.append((nxt,iter(sorted(graph[nxt]))))
    if len(seen)!=len(graph):
        raise ValueError("campaign graph is disconnected")
    return tuple(route[:-1])


@dataclass(frozen=True,slots=True)
class VirtualCampaign:
    package_digest: str
    campaign_id: str
    title: str
    seed: int
    variant: int
    scale: CampaignScale
    regions: tuple[Region,...]
    route: tuple[str,...]
    objectives: tuple[str,...]

    def address(self,ordinal:int)->SceneAddress:
        integer(ordinal,"scene ordinal",1,self.scale.scenes)
        index=ordinal-1
        ai=_partition(index,self.scale.scenes,self.scale.acts)
        ci=_partition(ai,self.scale.acts,self.scale.chapters)
        first=_start(ai,self.scale.scenes,self.scale.acts)
        final=_start(ai+1,self.scale.scenes,self.scale.acts)
        chapter_first=_start(ci,self.scale.acts,self.scale.chapters)
        chapter_final=_start(ci+1,self.scale.acts,self.scale.chapters)
        return SceneAddress(ordinal,ci+1,ai+1,index-first+1,final-first,
                            ai-chapter_first+1,chapter_final-chapter_first)

    def ordinal(self,*,chapter:int,act:int,scene:int)->int:
        """Convert chapter-local act and act-local scene back to an ordinal."""
        integer(chapter,"chapter",1,self.scale.chapters)
        first=_start(chapter-1,self.scale.acts,self.scale.chapters)
        last=_start(chapter,self.scale.acts,self.scale.chapters)
        integer(act,"chapter-local act",1,last-first)
        ai=first+act-1
        start=_start(ai,self.scale.scenes,self.scale.acts)
        end=_start(ai+1,self.scale.scenes,self.scale.acts)
        integer(scene,"act-local scene",1,end-start)
        return start+scene

    def region(self,key:str)->Region:
        for item in self.regions:
            if item.key==key:
                return item
        raise ValueError("unknown campaign region")

    def scene(self,ordinal:int)->Scene:
        address=self.address(ordinal)
        region=self.region(self.route[(ordinal-1)%len(self.route)])
        raw=sha256(f"{self.campaign_id}:{ordinal}".encode("ascii")).digest()
        arc_end=address.scene_in_act==address.scene_count
        chapter_end=arc_end and address.chapter_act==address.chapter_act_count
        kind="finale" if ordinal==self.scale.scenes else "chapter_climax" if chapter_end else (
            "act_climax" if arc_end else ("encounter","discovery","trade","rescue","survey")[raw[0]%5])
        objective=self.objectives[(ordinal-1+raw[1])%len(self.objectives)]
        risk=min(90,max(5,region.threat//2+address.chapter//4+raw[2]%12))
        reward=min(100,max(8,region.reward//2+raw[3]%17))
        return Scene(address,region.key,kind,objective,risk,reward,region.neighbours,
                     chapter_end,ordinal==self.scale.scenes)

    def page(self,start:int=1,*,limit:int=64)->tuple[Scene,...]:
        integer(start,"scene page start",1,self.scale.scenes)
        integer(limit,"scene page limit",1,256)
        return tuple(self.scene(index) for index in range(start,min(start+limit,self.scale.scenes+1)))


def campaign_from_results(journal,results,request:DesignRequest,*,variant:int=1,
                          scale:CampaignScale=CampaignScale())->VirtualCampaign:
    """Build only from the independently reconstructed complete design package."""
    if type(request) is not DesignRequest or type(scale) is not CampaignScale:
        raise TypeError("canonical request and campaign scale required")
    integer(variant,"design variant",1,request.variants)
    package=collect_package(journal,results,request)
    prefix=f"variants/{variant:02d}/"
    world=json.loads(package.files[prefix+"world.json"])
    quest=json.loads(package.files[prefix+"quest.json"])
    graph=validate_world(world)
    validate_quest(quest,world)
    route=_tour(graph,world["entry"])
    rows=tuple(Region(row["id"],row["biome"],row["threat"],row["reward"],
                      tuple(sorted(graph[row["id"]]))) for row in sorted(world["regions"],key=lambda x:x["id"]))
    objectives=tuple(step["objective"] for step in quest["steps"])
    identity=digest(["prood.virtual-campaign.v1",package.package_digest,variant,
                     [scale.chapters,scale.acts,scale.scenes]])
    return VirtualCampaign(package.package_digest,identity,request.context()["spec"]["title"],
                           request.seed,variant,scale,rows,route,objectives)
