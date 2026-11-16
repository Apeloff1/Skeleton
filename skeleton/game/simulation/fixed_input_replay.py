"""Source-level deterministic input -> fixed clock -> swept collision -> rollback.

Device input is provided explicitly as integer samples; no OS input capture,
rendering or physics-engine execution is asserted. Canonical owners remain
the authority for bindings, clock advances, and collision transitions.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from skeleton.app.recovered_evidence import (
    EvidenceError, array, fields, identifier, integer, digest, seal, verify, text,
)
from skeleton.game.presentation.input_actions import Action, ActionMap, Binding, Control, InputState
from skeleton.simulation.game.fixed_clock import ClockState, advance_clock, MAX_ELAPSED_US
from skeleton.game.simulation.input_collision import MovementInput, step_character
from skeleton.game.simulation.flgb_simulation_runtime import (
    AABB, CharacterController, SimulationSnapshot, RollbackBuffer,
    RollbackReplayReceipt, narrowphase_aabb, MAX_COORD,
)

SCHEMA="skeleton.fixed-input-replay.order.v1"
SAVE="skeleton.fixed-input-replay.save.v1"
MAX_FRAMES=2048
MAX_OBSTACLES=256
MAX_STEPS=8
MAX_WORK=2_000_000


def vec(value):
    return tuple(integer(x,-MAX_COORD,MAX_COORD) for x in array(value,3,3))


def _binding(row):
    fields(row,{"control","axis","scale_milli","deadzone_milli","modifiers"})
    control=Control.parse(text(row["control"],96))
    scale=integer(row["scale_milli"],-16_000,16_000)/1000.0
    deadzone=integer(row["deadzone_milli"],0,999)/1000.0
    mods=tuple(text(x,12) for x in array(row["modifiers"],0,4))
    return Binding("move",control,mods,scale,row["axis"],deadzone)


def _input_map(order):
    controls=fields(order,{"defaults","overrides"})
    bindings=[_binding(row) for row in array(controls["defaults"],1,64)]
    mapping=ActionMap([Action("move","axis2d")],bindings)
    replacements=controls["overrides"]
    if replacements is not None:
        normalized=[_binding(row) for row in array(replacements,1,64)]
        mapping.import_overrides({"move":[
            {"control":str(b.control),"modifiers":list(b.modifiers),"scale":b.scale,
             "axis":b.axis,"deadzone":b.deadzone} for b in normalized
        ]})
    if not mapping.bindings("move"):
        raise EvidenceError("no movement controls")
    return mapping


@dataclass
class Simulation:
    order: dict
    clock: ClockState
    controller: CharacterController
    obstacles: tuple
    extent: int
    inputs: InputState
    records: list
    trace: list
    rollback: RollbackBuffer

    @classmethod
    def start(cls,order,*,authorized):
        if authorized is not True:
            raise PermissionError("explicit simulation operator required")
        fields(order,{"schema","project_id","step_us","max_steps","player","obstacles","controls","frames"})
        if order["schema"]!=SCHEMA:
            raise EvidenceError("unsupported simulation order")
        identifier(order["project_id"])
        step=integer(order["step_us"],1000,100_000)
        max_steps=integer(order["max_steps"],1,MAX_STEPS)
        frames=array(order["frames"],1,MAX_FRAMES)
        player=fields(order["player"],{"id","position","speed","half_extent"})
        position=vec(player["position"])
        extent=integer(player["half_extent"],1,10000)
        if any(abs(x)+extent+1>MAX_COORD for x in position):
            raise EvidenceError("initial position edge")
        controller=CharacterController(identifier(player["id"]),position,
                                       integer(player["speed"],1,1000000),True)
        obstacles=[]
        ids={controller.entity_id}
        for row in array(order["obstacles"],0,MAX_OBSTACLES):
            fields(row,{"id","min","max"})
            cid=identifier(row["id"])
            if cid in ids:
                raise EvidenceError("collider identity collision")
            ids.add(cid)
            obstacles.append(AABB(cid,vec(row["min"]),vec(row["max"])))
        if len(frames)*max_steps*max(1,len(obstacles))>MAX_WORK:
            raise EvidenceError("simulation work ceiling")
        player_box=AABB(controller.entity_id,tuple(x-extent for x in position),
                        tuple(x+extent+1 for x in position))
        if any(narrowphase_aabb(player_box,box) is not None for box in obstacles):
            raise EvidenceError("player starts inside obstacle")
        mapping=_input_map(order["controls"])
        for frame in frames:
            fields(frame,{"elapsed_us","samples"})
            integer(frame["elapsed_us"],0,MAX_ELAPSED_US)
            seen=set()
            for row in array(frame["samples"],0,64):
                fields(row,{"control","value"})
                control=str(Control.parse(text(row["control"],96)))
                integer(row["value"],-1000,1000)
                if control in seen:
                    raise EvidenceError("duplicate control sample in frame")
                seen.add(control)
        return cls(deepcopy(order),ClockState(step_us=step),controller,
                   tuple(obstacles),extent,InputState(mapping),[],[],
                   RollbackBuffer(max_snapshots=128))

    def _state(self):
        return {"clock":self.clock.to_record(),"position":list(self.controller.position),
                "entity":self.controller.entity_id,"max_speed":self.controller.max_speed_per_sec,
                "grounded":self.controller.grounded}

    def _capture(self):
        state=self._state()
        # No stochastic system participates; this is an explicit absence marker.
        return SimulationSnapshot(self.clock.tick,digest(state),
                                  digest({"entity":self.controller.entity_id}),
                                  digest({"position":state["position"],"obstacles":self.order["obstacles"]}),
                                  digest({"rng":"not_used"}))

    def frame(self):
        index=len(self.records)
        if index>=len(self.order["frames"]):
            raise EvidenceError("frame sequence exhausted")
        frame=self.order["frames"][index]
        for row in frame["samples"]:
            self.inputs.feed(row["control"],row["value"]/1000.0)
        self.inputs.update()
        x,y=self.inputs.value("move")
        command=MovementInput(round(x*1000),round(y*1000))
        advance=advance_clock(self.clock,frame["elapsed_us"],max_steps=self.order["max_steps"])
        blocked_x=blocked_y=0
        position_before=list(self.controller.position)
        for tick in advance.ticks:
            moved=step_character(self.controller,command,self.clock.step_us*1000,
                                 self.obstacles,half_extent=self.extent)
            self.controller=moved.controller
            blocked_x+=int(moved.blocked_x)
            blocked_y+=int(moved.blocked_y)
            self.trace.append({"tick":tick,"position":list(self.controller.position),
                               "blocked_x":moved.blocked_x,"blocked_y":moved.blocked_y})
        self.clock=advance.after
        if advance.ticks:
            self.rollback=self.rollback.append(self._capture())
        self.records.append({"frame":index,"sample_digest":digest(frame),
                             "clock_advance_digest":advance.replay_digest,
                             "ticks":list(advance.ticks),"dropped_us":advance.dropped_this_advance_us,
                             "axes":[command.horizontal,command.vertical],
                             "position_before":position_before,
                             "position_after":list(self.controller.position),
                             "blocked_x":blocked_x,"blocked_y":blocked_y})

    def snapshot(self):
        return seal({"schema":SAVE,"order_digest":digest(self.order),"frames":len(self.records),
                     "state":self._state(),"frame_records":deepcopy(self.records),
                     "trace_digest":digest(self.trace),
                     "trace_ticks":len(self.trace),"buffered_ticks":[s.tick for s in self.rollback.snapshots],
                     "native_engine_executed":False,"release_certified":False})

    @classmethod
    def restore(cls,order,snapshot,*,expected_digest,authorized):
        if authorized is not True:
            raise PermissionError("explicit simulation operator required")
        verify(snapshot,expected_digest)
        if snapshot.get("schema")!=SAVE:
            raise EvidenceError("unsupported replay snapshot")
        instance=cls.start(order,authorized=True)
        count=integer(snapshot.get("frames"),0,len(order["frames"]))
        for _ in range(count):
            instance.frame()
        if instance.snapshot()!=snapshot:
            raise EvidenceError("snapshot differs from canonical replay")
        return instance


def qualify_motion(order,*,authorized):
    sim=Simulation.start(order,authorized=authorized)
    split=len(order["frames"])//2
    for _ in range(split):
        sim.frame()
    checkpoint=sim.snapshot()
    midpoint=sim.rollback.restore(sim.clock.tick) if sim.clock.tick else None
    restored=Simulation.restore(order,checkpoint,expected_digest=checkpoint["digest"],authorized=True)
    for _ in range(split,len(order["frames"])):
        sim.frame()
        restored.frame()
    final=sim.snapshot()
    if restored.snapshot()!=final:
        raise EvidenceError("input/collision replay failed")
    receipt=None
    if midpoint is not None:
        receipt=RollbackReplayReceipt(midpoint.digest,sim.clock.tick,
                                      digest(order["frames"][split:]),digest(final["state"])).digest
    return seal({"schema":"skeleton.fixed-input-replay.qualification.v1",
                 "checkpoint":checkpoint,"final":final,"rollback_receipt_digest":receipt,
                 "blocked_x_steps":sum(x["blocked_x"] for x in final["frame_records"]),
                 "blocked_y_steps":sum(x["blocked_y"] for x in final["frame_records"]),
                 "fixed_clock_executed":True,"input_action_owner_executed":True,
                 "collision_owner_executed":True,"prefix_reconstructed":True,
                 "native_engine_executed":False,"device_tested":False,"release_certified":False})
