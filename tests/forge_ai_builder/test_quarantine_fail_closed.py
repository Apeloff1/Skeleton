"""Quarantine recovery security and durability boundaries."""
from __future__ import annotations
import asyncio
import math
from dataclasses import dataclass
import pytest
from skeleton.forge.ai_builder.validate.scoring import Thresholds
from skeleton.forge.ai_builder.validate.qa_hook import plan_qa_hook
from skeleton.forge.ai_builder.model_planner import grant_providers
from skeleton.forge.ai_builder.procgen.completability import ProcgenCompletabilitySolver
from skeleton.forge.ai_builder.procgen.rng import root_digest, gauss
from skeleton.forge.ai_builder.procgen.errors import ProcgenError
from skeleton.forge.ai_builder.procgen.keys import solve
from skeleton.forge.ai_builder.edit.session import EditSession

from .fakes import FakeRouter, gate_and_issuer
from .plan_fixtures import good_plan
from .test_edit_session import editor
from .history_fake import FakeHistory


def test_scoring_cannot_accept_nonfinite_or_negative_penalties():
    for field in ("accept","repair","error_penalty","warning_penalty"):
        with pytest.raises(ValueError):
            Thresholds(**{field: float("nan")})
        with pytest.raises(ValueError):
            Thresholds(**{field: float("inf")})
    with pytest.raises(ValueError):
        Thresholds(error_penalty=-1)


def test_qa_hook_absent_plan_requires_repair():
    r = plan_qa_hook()({})
    assert r["repair_requested"] is True and r["issues"] and not r["release_certified"]


def test_procedural_seeds_and_provider_list_are_bounded():
    with pytest.raises(ProcgenError): root_digest("x" * 1025)
    with pytest.raises(ProcgenError): root_digest(1 << 300)
    gate, issuer = gate_and_issuer()
    with pytest.raises(ValueError):
        grant_providers(issuer, ("p" + str(i) for i in range(65)))


def test_lock_solver_rejects_unbounded_room_graph():
    with pytest.raises(ProcgenError):
        solve({str(i): [] for i in range(4097)}, "0", "1", {}, {})


@dataclass(frozen=True)
class Room:
    key: str
    doors: tuple = ()
    keys: tuple = ()
    goal: bool = False


def test_completability_duplicate_and_oversized_input_fail_closed():
    solver = ProcgenCompletabilitySolver()
    assert not solver.check([Room("same"), Room("same",goal=True)],"same",frozenset()).completable
    assert solver.check([Room("a")] * 4097,"a",frozenset()).softlocked


def test_gauss_refuses_infinite_zero_rng():
    class Zero:
        def random(self): return 0.0
    with pytest.raises(ProcgenError):
        gauss(Zero())


def test_failed_history_save_does_not_publish_unsaved_edit():
    hist=FakeHistory()
    session=EditSession(good_plan(),editor(grant=("none",)),history=hist,project_id="p1")
    original=dict(session.plan)
    def failure(*args,**kwargs):
        raise OSError("simulated durable store failure")
    hist.saver.save_files=failure
    with pytest.raises(OSError):
        asyncio.run(session.edit("set player hp to 120"))
    assert session.plan == original and not session.undo_stack and session._held


def test_failed_history_undo_preserves_stacks():
    hist=FakeHistory()
    session=EditSession(good_plan(),editor(grant=("none",)),history=hist,project_id="p1")
    asyncio.run(session.edit("set player hp to 120"))
    before=dict(session.plan)
    hist.rollback=lambda *a,**kw: (_ for _ in ()).throw(OSError("simulated rollback failure"))
    with pytest.raises(OSError):
        session.undo()
    assert session.plan == before and len(session.undo_stack)==1 and not session.redo_stack
    assert session._held


def test_terrain_parameters_are_bounded_before_any_generation():
    from skeleton.forge.ai_builder.procgen.terrain import TerrainConfig, generate_terrain
    from skeleton.forge.ai_builder.procgen.rng import Streams
    invalid = (
        {"island": True}, {"octaves": True}, {"octaves": 0},
        {"thermal_iterations": 201}, {"droplets": 100001},
        {"persistence": float("nan")}, {"roughness": float("inf")},
        {"moisture_scale": 0}, {"talus": "0.05"},
        {"biomes": None}, {"world_id": "../escape"},
        {"width": 512, "height": 512, "thermal_iterations": 200},
    )
    for kwargs in invalid:
        with pytest.raises(ProcgenError):
            TerrainConfig(**kwargs)
    with pytest.raises(ProcgenError, match="typed"):
        generate_terrain(object(), TerrainConfig(width=8,height=8))


def test_stream_name_newline_and_provenance_inventory_limit_rejected():
    from skeleton.forge.ai_builder.procgen.rng import Streams
    streams = Streams(123)
    for bad in ("terrain\n", "terrain/rooms\n"):
        with pytest.raises(ProcgenError):
            streams.digest(bad)
    streams._issued = {f"n{i}": "0" * 64 for i in range(4096)}
    with pytest.raises(ProcgenError, match="budget"):
        streams.digest("newstream")


def test_gaussian_overflow_refused_even_if_parameters_are_finite():
    class Samples:
        def __init__(self):
            self._samples = iter((0.5, 0.0))
        def random(self):
            return next(self._samples)
    with pytest.raises(ProcgenError, match="finite"):
        gauss(Samples(), mu=1.7e308, sigma=1.7e308)
