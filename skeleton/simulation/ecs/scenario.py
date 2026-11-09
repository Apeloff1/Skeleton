"""Small deterministic reference scenario used by smoke tests and benchmarks."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import digest
from .query import FieldPredicate,CompareOp,QueryEngine,QuerySpec
from .runtime import SimulationRuntime
from .schedule import SystemPhase,SystemSpec
from .schema import FieldKind,FieldSpec,SchemaRegistry,make_schema
from .store import EntityStore
@dataclass(frozen=True)
class ScenarioDefinition:seed:str="reference";entities:int=4;ticks:int=10
@dataclass(frozen=True)
class ScenarioResult:definition:ScenarioDefinition;initial_digest:str;final_digest:str;ticks:int;living_entities:tuple[str,...];result_digest:str
def reference_registry():
    r=SchemaRegistry();r.register(make_schema("position",1,[FieldSpec("x",FieldKind.FLOAT,default=0.0),FieldSpec("y",FieldKind.FLOAT,default=0.0)]));r.register(make_schema("velocity",1,[FieldSpec("dx",FieldKind.FLOAT,default=0.0),FieldSpec("dy",FieldKind.FLOAT,default=0.0)]));r.register(make_schema("health",1,[FieldSpec("hp",FieldKind.INT,minimum=0,maximum=100)]));return r
def build_reference_store(definition=None):
    d=definition or ScenarioDefinition();store=EntityStore(reference_registry())
    for i in range(d.entities):
        e=store.create_entity(hint=f"unit-{i}");store.set_component(e.entity_id,"position",{"x":float(i),"y":0.0});store.set_component(e.entity_id,"velocity",{"dx":1.0+0.1*i,"dy":0.25});store.set_component(e.entity_id,"health",{"hp":100-i*5})
    return store
def build_reference_runtime(definition=None):
    d=definition or ScenarioDefinition();rt=SimulationRuntime(build_reference_store(d));move=SystemSpec("movement",SystemPhase.UPDATE,reads=("velocity",),writes=("position",));decay=SystemSpec("decay",SystemPhase.POST,writes=("health",),after=("movement",))
    def movement(ctx):
        for eid in QueryEngine(ctx.store).ids(QuerySpec(all_of=("position","velocity"))):
            p=ctx.store.get_component(eid,"position").data;v=ctx.store.get_component(eid,"velocity").data;ctx.commands.add("set_component",{"entity_id":eid,"schema_id":"position","data":{"x":p["x"]+v["dx"],"y":p["y"]+v["dy"]}})
    def health_decay(ctx):
        for eid in QueryEngine(ctx.store).ids(QuerySpec(all_of=("health",))):
            hp=ctx.store.get_component(eid,"health").data["hp"];ctx.commands.add("set_component",{"entity_id":eid,"schema_id":"health","data":{"hp":max(0,hp-1)}})
    rt.register(move,movement);rt.register(decay,health_decay);return rt
def run_reference_scenario(definition=None):
    d=definition or ScenarioDefinition();rt=build_reference_runtime(d);initial=rt.store.state_digest
    for _ in range(d.ticks):rt.step()
    living=QueryEngine(rt.store).ids(QuerySpec(all_of=("health",),predicates=(FieldPredicate("health","hp",CompareOp.GT,0),)));material={"definition":d.__dict__,"initial":initial,"final":rt.store.state_digest,"ticks":rt.clock.tick,"living":living};return ScenarioResult(d,initial,rt.store.state_digest,rt.clock.tick,living,digest(material))
def compare_reference_runs(definition=None):return run_reference_scenario(definition)==run_reference_scenario(definition)
