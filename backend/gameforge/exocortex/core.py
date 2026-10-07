from __future__ import annotations
"""
Exocortex core — bilateral hemispheres + full neuro stack, coherent cascade.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from gameforge.exocortex.hemispheres import BilateralBridge
from gameforge.exocortex.neuro_layers import (
    ReticularActivatingSystem,
    CerebellumAutomator,
    AnteriorCingulateMonitor,
    NucleusAccumbensTokens,
    CognitiveLoadGovernor,
    SemanticMemoryMesh,
    ForgettingAlgorithm,
    FeedForwardLoop,
    SovereigntyVault,
)
from gameforge.personal.neuro.salience import SalienceNetwork
from gameforge.math_exocortex.hub import MathExocortex
from gameforge.exocortex.twin_logs import TwinHub
from gameforge.exocortex.pfc import PrefrontalCortex
from gameforge.exocortex.twin_memory import TwinMemoryService
from gameforge.exocortex.judgement import LogicJudgementSandbox
from gameforge.exocortex.handoff import HandoffBus
from gameforge.exocortex.conglomerate import ConglomerateControlPlane
from gameforge.exocortex.zaibatsu import JeevesZaibatsu
from gameforge.persistence.marathon_store import MarathonStore
from gameforge.mobile.s20_shell import S20ShellGuard
from gameforge.exocortex.quality import score_project
from gameforge.persistence.spine import PersistenceSpine


class Exocortex:
    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.hemispheres = BilateralBridge()
        self.ras = ReticularActivatingSystem()
        self.math = MathExocortex(pow_difficulty=1, certainty_mode=True)
        self.cerebellum = CerebellumAutomator(math_hub=self.math)
        self.acc = AnteriorCingulateMonitor()
        self.reward = NucleusAccumbensTokens()
        self.governor = CognitiveLoadGovernor()
        self.semantic = SemanticMemoryMesh(user_id)
        self.forgetting = ForgettingAlgorithm(retention_days=30)
        self.feedforward = FeedForwardLoop()
        self.sovereignty = SovereigntyVault()
        self.salience = SalienceNetwork()
        self.twins = TwinHub(user_id)
        self.twin_memory = TwinMemoryService(user_id)
        self.pfc = PrefrontalCortex()
        self.judgement = LogicJudgementSandbox(twin_memory=None)
        self.handoffs = HandoffBus(twin_memory=None)
        self.conglomerate = ConglomerateControlPlane()
        self.zaibatsu = JeevesZaibatsu(user_id)
        self.store = MarathonStore(user_id)
        self.s20 = S20ShellGuard()
        self.zaibatsu.bind_twins(self.twin_memory)
        self.zaibatsu.masterlog.twin_write = lambda surface, payload, **kw: self.twin_memory.twin_write(surface, payload, **kw)
        self.zaibatsu.masterlog.store_event = lambda surface, event, payload: self.store.event(surface, event, payload)
        self.subject_unit = self.conglomerate.attach_subject(user_id)
        self.unit_id = self.subject_unit.unit_id
        self.persistence = PersistenceSpine(user_id)
        self.logs: List[dict] = []

    def _log(self, event: str, **kw):
        self.logs.append({"ts": datetime.utcnow().isoformat(), "event": event, **kw})
        if len(self.logs) > 3000:
            self.logs = self.logs[-3000:]

    def ingest(self, text: str) -> Dict[str, Any]:
        """
        Full pipeline:
          raw → RAS → bilateral parse → salience → semantic mesh → optional auto math
        """
        sal = self.salience.score(text)
        ras = self.ras.filter(text, salience_score=sal.score)
        # twin always keeps full account
        self.conglomerate.consume_quota(self.unit_id, "twin_writes")
        twin = self.twins.mirror(
            "transcript",
            {"salience": sal.to_dict(), "ras": ras},
            raw_text=text,
            original_filtered=not ras["passed"],
            original_kept=ras["passed"],
            tags=["ingest"],
        )
        if not ras["passed"]:
            self._log("ingest_dropped", ras=ras, twin_id=twin.twin_id)
            return {"ok": True, "dropped": True, "ras": ras, "twin_id": twin.twin_id}

        bilateral = self.hemispheres.parse_both(text)
        # governor may raise RAS for next items
        if "raise_ras_threshold" in bilateral["bridge"]["actions"]:
            self.ras.raise_threshold()

        # semantic store for continuity
        self.semantic.add(text, meta={"source": "ingest", "cues": bilateral["right"]["tone_cues"]})

        # left-brain math route via cerebellum automation
        auto = None
        if "route_math_exocortex" in bilateral["bridge"]["actions"]:
            # extract numbers if present
            nums = bilateral["left"]["structures"].get("numbers") or []
            try:
                floats = [float(n.strip("%")) for n in nums[:32]]
            except Exception:
                floats = []
            if len(floats) >= 2:
                auto = self.cerebellum.enqueue_pow_sum(floats)

        # reward for adverse-condition work signal
        reward = None
        if "strain" in bilateral["right"]["tone_cues"] and bilateral["left"]["structures"].get("commands"):
            reward = self.reward.mint(1.0, "work_under_strain", adverse=True)

        out = {
            "ok": True,
            "dropped": False,
            "ras": ras,
            "bilateral": bilateral,
            "salience": sal.to_dict(),
            "auto_job": auto,
            "reward": reward,
            "jeeves_tone": bilateral["bridge"]["jeeves_tone"],
        }
        # Zaibatsu counsel layer
        strain = "strain" in (bilateral.get("right") or {}).get("tone_cues", [])
        z = self.zaibatsu.counsel(text, energy=0.55, strain=strain)
        out["zaibatsu"] = z
        if z.get("blocked"):
            out["dropped"] = True
            out["jeeves_tone"] = "security_lock"
        elif z.get("jeeves_say"):
            out["jeeves_say"] = z["jeeves_say"]
        self.twin_memory.twin_write("jeeves", z, raw_text=text, tags=["zaibatsu"])
        self._log("ingest_pass", tone=out["jeeves_tone"])
        return out

    def progress_check(self, scheduled_pct: float, actual_pct: float, project_id: str = "") -> Dict[str, Any]:
        alarm = self.acc.check(scheduled_pct, actual_pct, project_id)
        if alarm["fired"]:
            self.semantic.add(
                f"ACC alarm {project_id}: scheduled {scheduled_pct} actual {actual_pct}",
                meta={"type": "acc_alarm"},
            )
            self.reward.mint(0.2, "detected_roadblock_honesty")
        return alarm

    def regulate(self, energy: float, noise_db: float, valence: float = 0.0) -> Dict[str, Any]:
        gov = self.governor.evaluate(energy, noise_db, valence)
        if gov["mode"] == "conservation":
            self.ras.raise_threshold(0.1)
        elif gov["mode"] == "deep_focus":
            self.ras.reset_threshold()
        return gov

    def feed_forward(
        self,
        upcoming_weather: List[str],
        planned_load: int,
        capacity: int,
        plasticity_risk: bool = False,
        energy: float = 0.55,
    ) -> Dict[str, Any]:
        return self.feedforward.project(
            upcoming_weather=upcoming_weather,
            planned_load=planned_load,
            capacity=capacity,
            plasticity_risk=plasticity_risk,
            energy=energy,
        )

    def recall(self, query: str, k: int = 5) -> Dict[str, Any]:
        hits = self.semantic.search(query, k=k)
        return {"query": query, "hits": hits}

    def prune_memory(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.forgetting.prune(records)

    def jeeves_context(self) -> str:
        lines = ["[EXOCORTEX]"]
        lines.append(f"Sovereignty: {self.sovereignty.status()}")
        lines.append(f"Governor mode: {self.governor.mode}")
        lines.append(f"RAS threshold: {self.ras.threshold}")
        lines.append(f"Cognitive tokens: {self.reward.balance}")
        if self.acc.alarms:
            lines.append(f"ACC alarms: {len(self.acc.alarms)} (last delta={self.acc.alarms[-1].get('delta')})")
        lines.append(f"Semantic nodes: {len(self.semantic.store)}")
        lines.append(f"PFC protocol: {self.pfc.ofc.status()}")
        if self.pfc.dlpfc.active():
            lines.append(f"dlPFC goal: {self.pfc.dlpfc.active().goal}")
        if self.hemispheres.logs:
            lines.append(f"Last bridge: {self.hemispheres.logs[-1].get('bridge')}")
        return "\n".join(lines)

    def status(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "ras_threshold": self.ras.threshold,
            "governor": self.governor.mode,
            "tokens": self.reward.status(),
            "acc_alarms": len(self.acc.alarms),
            "semantic_nodes": len(self.semantic.store),
            "cerebellum_queue": len(self.cerebellum.queue),
            "sovereignty": self.sovereignty.status(),
            "math": self.math.status(),
            "twins": self.twins.overview(),
            "pfc": self.pfc.status(),
            "twin_policy": self.twin_memory.assert_unfiltered_policy(),
            "judgement_rules": self.judgement.rules(),
            "handoffs": self.handoffs.status(),
            "conglomerate": self.conglomerate.status(),
            "persistence": self.persistence.status(),
            "quality": score_project(self),
        }

    def twin_query(self, stream: str = "transcript", **kwargs):
        return self.twins.query(stream, **kwargs)

    def twin_query_all(self, contains: str, n: int = 20):
        return self.twins.query_all(contains, n=n)

    def pfc_decide(self, goal: str, **kwargs):
        # pull semantic history into dlPFC
        hist = [{"text": h.get("text"), "score": h.get("score")} for h in self.semantic.search(goal, k=3)]
        kwargs.setdefault("historical", hist)
        enforcement = self.conglomerate.enforce_action(self.unit_id, "schedule_heavy" if kwargs.get("task_cost", 0) >= 0.5 else "ingest")
        if not enforcement.get("allowed"):
            self.twin_memory.twin_write("system", {"blocked": enforcement}, raw_text=goal, tags=["quota_block"])
            return {"pfc": None, "judgement": None, "handoff": None, "enforcement": enforcement, "blocked": True}
        decision = self.pfc.executive_decide(goal, **kwargs)
        self.twin_memory.twin_write("pfc", decision, raw_text=goal, tags=["pfc"])
        ctx = {
            "governor_mode": self.governor.mode,
            "acc_alarm": bool(self.acc.alarms),
        }
        # bind twin into judgement/handoff if needed
        self.judgement.twin = self.twin_memory
        self.handoffs.twin = self.twin_memory
        judgement = self.judgement.judge(goal, decision, context=ctx)
        handoff = None
        if judgement.verdict in ("approve", "approve_with_constraints"):
            handoff = self.handoffs.create(
                "judgement",
                "jeeves_executor",
                intent="execute_or_schedule",
                payload={"goal": goal, "decision": decision, "judgement_id": judgement.judgement_id},
                constraints=judgement.constraints,
            )
        self.conglomerate.consume_quota(self.unit_id, "judgements")
        return {
            "pfc": decision,
            "judgement": judgement.to_dict(),
            "handoff": handoff.to_dict() if handoff else None,
            "enforcement": enforcement,
            "blocked": False,
        }

    def pfc_register_goal(self, title: str, horizon: str = "10y", subgoals=None):
        g = self.pfc.apfc.register(title, horizon=horizon, subgoals=subgoals)
        self.twins.mirror("system", g.to_dict(), tags=["meta_goal"])
        return g.to_dict()

    def zaibatsu_counsel(self, text: str, **kwargs):
        return self.zaibatsu.counsel(text, **kwargs)

    def vox_agent(self, agent_id: str, subject: str, body=None):
        return self.zaibatsu.order_agent(agent_id, subject, body)

    def vox_boardroom(self, subject: str, body=None):
        return self.zaibatsu.boardroom(subject, body)

    def room_rep(self, room_id: str, delta: float, reason: str = ""):
        return self.zaibatsu.room_rep(room_id, delta, reason)

    def master_wire(self, domain: str):
        return self.zaibatsu.master_wire(domain)

    def self_heal(self):
        probes = {
            "frozen": self.zaibatsu.security.frozen,
            "handoff_dead_letter": len(self.handoffs.dead_letter),
            "ras_threshold": self.ras.threshold,
        }
        return self.zaibatsu.auto_heal(probes, {"ras": self.ras, "governor": self.governor, "handoffs": self.handoffs})

    # ----- DNA Board / Boardroom planning ------------------------------------
    def dna_issue(self, room_id: str, directions: list, tier_hints=None):
        """directions: list of 3 (title, brief) tuples/lists"""
        norm = []
        for d in directions:
            if isinstance(d, (list, tuple)) and len(d) >= 2:
                norm.append((str(d[0]), str(d[1])))
            elif isinstance(d, dict):
                norm.append((d.get("title", ""), d.get("brief", "")))
        r = self.zaibatsu.dna.issue_directions(room_id, norm, tier_hints)
        if r.get("ok"):
            self.zaibatsu.boardroom(f"DNA directions -> {room_id}", r)
            self.twin_memory.twin_write("system", r, tags=["dna", "boardroom"])
        return r

    def dna_complete_direction(self, room_id: str, direction_id: str, result=None):
        return self.zaibatsu.dna.complete_direction(room_id, direction_id, result)

    def dna_create_task(self, room_id: str, title: str):
        task = self.zaibatsu.dna.create_task(room_id, title)
        return task.to_dict()

    def dna_advance(self, task_id: str, tier: str, note: str = "", score_delta: float = 10.0):
        return self.zaibatsu.dna.advance_branch(task_id, tier, note, score_delta)

    def dna_vote_open(self, subject: str, options: list, room_ids: list):
        v = self.zaibatsu.dna.open_vote(subject, options, room_ids)
        self.zaibatsu.boardroom(f"Vote open: {subject}", v.to_dict())
        return v.to_dict()

    def dna_vote_cast(self, vote_id: str, room_id: str, option: str):
        return self.zaibatsu.dna.cast_vote(vote_id, room_id, option)

    def dna_vote_close(self, vote_id: str):
        return self.zaibatsu.dna.close_vote(vote_id)

    def dna_sandbox_open(self, room_ids: list):
        m = self.zaibatsu.dna.open_sandbox(room_ids)
        return m.to_dict()

    def dna_sandbox_propose(self, meld_id: str, room_id: str, idea: str):
        return self.zaibatsu.dna.propose(meld_id, room_id, idea)

    def dna_sandbox_meld(self, meld_id: str, strategy: str = "concatenate"):
        return self.zaibatsu.dna.meld(meld_id, strategy)

    def dna_progress(self):
        return self.zaibatsu.dna.room_to_room_progress()

    # ----- Conglomerate Studio -----------------------------------------------
    def studio_bootstrap(self):
        return self.zaibatsu.studio.bootstrap_room_directions()

    def studio_start(self, goal: str, max_iterations: int = 8):
        c = self.zaibatsu.studio.start_cycle(goal, max_iterations=max_iterations)
        self.zaibatsu.boardroom(f"Studio cycle {c.build_id}", c.to_dict())
        return c.to_dict()

    def studio_build(self, build_id: str, notes: str, source_room: str = "build_room"):
        r = self.zaibatsu.studio.run_build_iteration(build_id, notes, source_room=source_room)
        self.twin_memory.twin_write("system", r, tags=["studio", "eval"])
        if r.get("next") == "boardroom_consensus":
            self.zaibatsu.boardroom("Eval passed — consensus required", r)
        return r

    def studio_vote(self, build_id: str, room_id: str, option: str):
        return self.zaibatsu.studio.cast_consensus(build_id, room_id, option)

    def studio_seal(self, build_id: str):
        r = self.zaibatsu.studio.seal_consensus(build_id)
        self.zaibatsu.boardroom("Consensus sealed", r)
        self.twin_memory.twin_write("system", r, tags=["studio", "consensus"])
        return r

    def studio_run_until_passed(self, goal: str, notes_list: list, board_votes=None):
        return self.zaibatsu.studio.run_until_passed(goal, notes_list, board_votes)

    def studio_status(self):
        return self.zaibatsu.studio.status()

    def studio_best_features(self, n: int = 15):
        return self.zaibatsu.studio.eval_room.best_features(n)

    def room_log(self, room_id: str, event: str, payload=None, raw_text: str = ""):
        r = self.zaibatsu.log_room(room_id, event, payload, raw_text)
        try:
            self.store.room_log(room_id, event, payload, raw_text)
        except Exception:
            pass
        try:
            self.zaibatsu.masterlog.write(room_id, "log", event, payload, raw_text or event, tags=["room"])
            self.zaibatsu.mesh.route_to_boardroom(room_id, event, payload)
        except Exception:
            pass
        return r

    def room_log_all(self, event: str, payload=None, raw_text: str = ""):
        return self.zaibatsu.room_logs.log_all(event, payload, raw_text)

    def idle_train(self, recursive_depth: int = 2):
        self.zaibatsu.idle_training.set_idle(True)
        r = self.zaibatsu.idle_train(recursive_depth=recursive_depth)
        self.twin_memory.twin_write("system", r, tags=["idle_training"])
        return r

    def idle_suggest(self, context: str, n: int = 8):
        return self.zaibatsu.idle_training.suggest(context, n=n)

    def store_stats(self):
        return self.store.stats()

    def cover_all_rooms(self):
        """Ensure every registry room is logged, DNA-tracked, and reputation-initialized."""
        from gameforge.rooms.full_room_registry import all_rooms, rooms_by_division
        covered = []
        for rid, meta in all_rooms().items():
            self.zaibatsu.room_logs._book(rid)
            self.zaibatsu.dna.ensure_room(rid)
            self.zaibatsu.rep.room(rid)
            self.room_log(rid, "zaibatsu_cover", {"meta": meta}, raw_text=f"cover {rid} {meta.get('role','')}")
            covered.append(rid)
        self.store.event("system", "cover_all_rooms", {"count": len(covered)})
        return {"ok": True, "rooms": covered, "by_division": rooms_by_division(), "count": len(covered)}

    def interconnect_boardroom(self):
        from gameforge.rooms.full_room_registry import all_rooms
        rooms = all_rooms()
        self.zaibatsu.mesh.register_many(rooms)
        for rid in rooms:
            self.zaibatsu.room_logs._book(rid)
            self.zaibatsu.dna.ensure_room(rid)
        self.zaibatsu.masterlog.write("boardroom", "audit", "mesh_interconnect", {"nodes": len(rooms)}, tags=["mesh"])
        self.zaibatsu.boardroom("Mesh interconnect complete", {"rooms": len(rooms)})
        return self.zaibatsu.mesh.status()

    def master_write(self, source: str, category: str, event: str, payload=None, raw_text: str = ""):
        return self.zaibatsu.masterlog.write(source, category, event, payload, raw_text).to_dict()

    def master_tail(self, n: int = 50, source=None, category=None):
        return self.zaibatsu.masterlog.tail(n, source=source, category=category)

    def chronoback_now(self):
        """Backup masterlog, marathon db, room logs, manifest."""
        paths = [
            self.zaibatsu.masterlog.path,
            self.store.db_path,
        ]
        # room log dir
        import os
        from pathlib import Path
        base = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        paths.append(base / "room_logs" / self.zaibatsu.user_id)
        paths.append(base / "masterlog" / self.zaibatsu.user_id)
        result = self.zaibatsu.chronoback.backup_critical_paths(paths)
        zipped = self.zaibatsu.chronoback.self_zip()
        healed = self.zaibatsu.chronoback.heal()
        self.zaibatsu.masterlog.write("system", "backup", "chronoback", {"backup": result, "zip": zipped, "heal": healed})
        return {"backup": result, "zip": zipped, "heal": healed, "status": self.zaibatsu.chronoback.status()}

    def chronoback_verify(self):
        return self.zaibatsu.chronoback.verify()

    def chronoback_heal(self):
        return self.zaibatsu.chronoback.heal()

    def structure(self):
        from gameforge.rooms.structure_map import structure_map
        return structure_map()

    def structure_ascii(self):
        from gameforge.rooms.structure_map import ascii_map
        return ascii_map()

    def s20_status(self):
        return self.s20.status()

    def s20_boot(self):
        stages = self.s20.boot_sequence()
        self.zaibatsu.masterlog.write("platform_android", "audit", "boot", {"stages": stages})
        return {"stages": stages, "status": self.s20.status()}

    def s20_throttle(self, work_minutes: float = 10.0, ambient_c: float = 28.0):
        return self.s20.predictive_throttle(work_minutes, ambient_c)

    def s20_memory_guard(self, planned_alloc_mb: float):
        return self.s20.memory_guard(planned_alloc_mb)

    def ensure_all_rooms_coherent(self):
        return self.zaibatsu.ensure_all_rooms_coherent()

    def synergy_counsel(self, text: str, energy: float = 0.55, strain: bool = False):
        return self.zaibatsu.synergy_counsel(text, energy=energy, strain=strain)
