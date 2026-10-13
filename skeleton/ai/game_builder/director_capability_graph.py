"""Capability-graph director: explicit dependency, authority and device budgets.

Pure deterministic control plane. A registered capability only denotes an
implemented adapter contract: it does not grant filesystem/network/provider
permissions or create a functioning proprietary engine integration.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

from .contracts import canonical_digest


class CapabilityError(ValueError):
    """Unbounded engine graph, impossible dependency, or authority conflict."""


@dataclass(frozen=True, slots=True)
class DeviceTier:
    name: str
    actor_budget: int
    ambient_budget: int
    cue_budget: int
    mission_budget: int
    work_units: int

    def __post_init__(self):
        if self.name not in {"retro", "handheld", "mobile", "desktop", "high_end"}:
            raise CapabilityError("unsupported offline target tier")
        for key, low, high in (
            (self.actor_budget, 1, 512), (self.ambient_budget, 0, 512),
            (self.cue_budget, 1, 4096), (self.mission_budget, 1, 256),
            (self.work_units, 50, 100000)
        ):
            if type(key) is not int or not low <= key <= high:
                raise CapabilityError("target profile exceeds bounded hardware policy")

    def payload(self):
        return dict(name=self.name,actor_budget=self.actor_budget,
                    ambient_budget=self.ambient_budget,
                    cue_budget=self.cue_budget,mission_budget=self.mission_budget,
                    work_units=self.work_units)


TIERS = {
    "retro": DeviceTier("retro", 6, 16, 32, 8, 180),
    "handheld": DeviceTier("handheld", 18, 36, 100, 28, 600),
    "mobile": DeviceTier("mobile", 28, 64, 150, 48, 1000),
    "desktop": DeviceTier("desktop", 64, 128, 400, 128, 3000),
    "high_end": DeviceTier("high_end", 128, 256, 1200, 256, 8500),
}


@dataclass(frozen=True, slots=True)
class Capability:
    key: str
    depends: tuple[str,...]
    cost: int
    lane: str
    resource: str
    adapter: str
    implemented: bool
    privileges: tuple[str,...] = ()

    def __post_init__(self):
        if not self.key or not self.adapter or self.lane not in {
            "director", "scene", "mission", "npc", "mirror", "product"
        }:
            raise CapabilityError("unidentified engine capability")
        if not self.resource or self.resource not in {
            "cpu", "memory", "render", "review", "storage"
        }:
            raise CapabilityError("unknown engine resource channel")
        if type(self.cost) is not int or not 1 <= self.cost <= 10000:
            raise CapabilityError("invalid engine scheduling weight")
        if type(self.implemented) is not bool:
            raise CapabilityError("unsupported completion classification")
        if any(x not in {"filesystem", "network", "process", "publication",
                         "training", "model"} for x in self.privileges):
            raise CapabilityError("unknown privileged side effect")
        if self.implemented and self.privileges:
            raise CapabilityError("offline modules cannot silently claim external authority")
        if len(set(self.depends)) != len(self.depends):
            raise CapabilityError("duplicated dependency")

    def payload(self):
        return dict(key=self.key,depends=list(self.depends),cost=self.cost,
                    lane=self.lane,resource=self.resource,
                    adapter=self.adapter,implemented=self.implemented,
                    privileges=list(self.privileges))


BUILTINS = (
    Capability("scene.data",(),12,"scene","memory","quest_scene_engine.Scene",True),
    Capability("scene.cinematic",("scene.data",),25,"scene","render","quest_scene_browser_client.cinema",True),
    Capability("scene.browser",("scene.data",),16,"scene","render","quest_scene_export.render_director_browser",True),
    Capability("mission.algebra",("scene.data",),18,"mission","cpu","modular_mission_runtime.Formula",True),
    Capability("mission.solver",("mission.algebra",),36,"mission","cpu","quest_director_solver.solve_quest",True),
    Capability("mission.endings",("mission.solver",),16,"mission","cpu","quest_director_endings.evaluate_story_ending",True),
    Capability("npc.needs",("scene.data",),20,"npc","cpu","npc_society_runtime.society_tick",True),
    Capability("npc.memory",("npc.needs",),20,"npc","memory","npc_society_runtime.apply_world_event",True),
    Capability("npc.social",("npc.memory",),24,"npc","cpu","npc_society_runtime.Society",True),
    Capability("director.synergy",("npc.social","mission.algebra"),55,"director","cpu","modular_director_session.director_session_step",True),
    Capability("director.mirror",("director.synergy",),30,"mirror","review","quest_scene_mirror.review_director",True),
    Capability("product.browser",("scene.browser","mission.solver","director.mirror"),
               35,"product","storage","quest_director_studio.build_director_studio",True),
    Capability("scene.native_3d",("scene.data",),100,"scene","render","future.native_adapter",False),
    Capability("npc.language_model",("npc.memory",),100,"npc","cpu","future.reviewed_model",False,("model",)),
    Capability("product.platform_store",("product.browser",),50,"product","storage","future.platform_adapter",False,("publication",)),
)


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    target: DeviceTier
    selected: tuple[Capability,...]
    rejected: tuple[str,...]
    resource_usage: tuple[tuple[str,int],...]

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.modular_capability_plan.v1",
                    target=self.target.payload(),
                    selected=[s.payload() for s in self.selected],
                    rejected=list(self.rejected),
                    resource_usage=[list(item) for item in self.resource_usage],
                    external_adapters_executed=False,
                    capability_claims_only_for_implemented=True)


def resolve_capabilities(requested: tuple[str,...], *, tier: DeviceTier,
                         allow_partial: bool=False) -> ExecutionPlan:
    if not isinstance(tier,DeviceTier) or not isinstance(requested,tuple):
        raise CapabilityError("typed target and explicit capability selection required")
    registry={c.key:c for c in BUILTINS}
    if len(set(requested)) != len(requested) or len(requested) > len(registry):
        raise CapabilityError("invalid repeated or oversized capability request")
    selection=set()
    rejected=[]
    def visit(key, visiting):
        if key not in registry:
            raise CapabilityError("unknown or uninstalled game engine module: "+key)
        if key in visiting:
            raise CapabilityError("cycle in engine dependency chain")
        if key in selection:
            return
        current=registry[key]
        if not current.implemented:
            if allow_partial:
                rejected.append(key)
                return
            raise CapabilityError("game capability lacks a real installed executable adapter")
        visiting.add(key)
        for dep in current.depends:
            visit(dep,visiting)
        visiting.remove(key)
        selection.add(key)
    for key in requested:
        visit(key,set())
    total=sum(registry[k].cost for k in selection)
    if total > tier.work_units:
        raise CapabilityError("real engine work exceeds consumer hardware tier")
    # Stable topological ordering preserves dependencies and public receipt.
    selected=[]
    pending=set(selection)
    while pending:
        ready=sorted(k for k in pending if set(registry[k].depends) <= {
            x.key for x in selected
        })
        if not ready:
            raise CapabilityError("incomplete capability graph")
        for key in ready:
            selected.append(registry[key]);pending.remove(key)
    usage=defaultdict(int)
    for value in selected:
        usage[value.resource]+=value.cost
    return ExecutionPlan(tier,tuple(selected),tuple(sorted(set(rejected))),
                         tuple(sorted(usage.items())))


__all__ = [
    "CapabilityError","DeviceTier","Capability","TIERS","BUILTINS",
    "ExecutionPlan","resolve_capabilities",
]
