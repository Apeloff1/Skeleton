from __future__ import annotations
"""
Synergy / coherence engine — single entrypoint that fires triggers in order
and keeps calendar, neuro, decade logs, and Jeeves aligned.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional
import logging
import re

from gameforge.personal.synergy.triggers import TriggerId, trigger_matrix, specs_by_id
from gameforge.personal.neuro.orchestrator import NeuroOrchestrator
from gameforge.personal.neuro.salience import SalienceNetwork
from gameforge.personal.calendar.year_calendar import YearCalendar
from gameforge.personal.calendar.decade_logs import DecadeLogHub
from gameforge.personal.calendar.era_log import EraLog
from gameforge.personal.synergy.reliability import ReliableTriggerExecutor, TriggerExecutionError, TriggerError, TriggerErrorCode

logger = logging.getLogger("gameforge.coherence")

GUEST_HINT = re.compile(
    r"\b(he|she|they|barista|neighbor|colleague|stranger|friend|waiter|driver)\b",
    re.I,
)


@dataclass
class CoherenceEvent:
    trigger: str
    ok: bool
    actions: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class CoherenceEngine:
    """
    Wires subsystems so one event produces a coherent cascade.
    """

    def __init__(
        self,
        user_id: str,
        *,
        neuro: Optional[NeuroOrchestrator] = None,
        calendar: Optional[YearCalendar] = None,
        decade: Optional[DecadeLogHub] = None,
        era: Optional[EraLog] = None,
        salience: Optional[SalienceNetwork] = None,
    ):
        self.user_id = user_id
        self.neuro = neuro or NeuroOrchestrator(user_id)
        self.calendar = calendar or YearCalendar(user_id)
        self.decade = decade or DecadeLogHub(user_id)
        self.era = era or EraLog(user_id)
        self.salience = salience or self.neuro.salience
        self._sleep_hours = 7.0
        self._pain = 0.0
        self._last_control: Dict[str, Any] = {}
        self.history: List[CoherenceEvent] = []
        self.executor = ReliableTriggerExecutor()

    # ----- public trigger API -------------------------------------------------

    def on_transcript(self, segment: str) -> CoherenceEvent:
        actions = []
        data: Dict[str, Any] = {}
        errors: List[str] = []
        try:
            result = self.salience.score(segment)
            data["salience"] = result.to_dict()
            actions.append("salience.score")
            if not result.keep:
                return self._emit(TriggerId.T_TRANSCRIPT_SEGMENT, True, actions + ["drop"], data)

            # ledger path is via personal logs if bound; fisherman for high value
            if result.score >= 0.75 or result.category in ("health", "command", "insight"):
                entry = self.decade.fisherman.catch(
                    date.today(),
                    segment,
                    title=f"Catch ({result.category})",
                    importance=min(1.0, result.score),
                    tags=["salience", result.category] + result.keywords_hit[:4],
                )
                actions.append("fisherman.catch")
                data["catch_id"] = entry.entry_id

            if result.category == "command":
                actions.append("route_command_pending")

            if GUEST_HINT.search(segment) and result.keep:
                # light guest extract — label unknown unless user tags later
                g = self.decade.guest.note_guest(
                    date.today(),
                    person_label="ambient_person",
                    body=segment[:400],
                    relationship="ambient",
                )
                actions.append("guest_log.note")
                data["guest_id"] = g.entry_id

            # health pain spike
            if result.category == "health" and any(
                k in (segment or "").lower() for k in ("pain", "chest", "heart")
            ):
                self._pain = max(self._pain, 0.65)
                actions.append("pain_spike_flag")
                self.on_pain(self._pain)

        except Exception as e:
            errors.append(str(e))
            return self._emit(TriggerId.T_TRANSCRIPT_SEGMENT, False, actions, data, errors)

        return self._emit(TriggerId.T_TRANSCRIPT_SEGMENT, True, actions, data, errors)

    def on_day_start(self) -> CoherenceEvent:
        actions = []
        data: Dict[str, Any] = {}
        try:
            day = self.calendar.get_day(date.today(), enrich=True)
            actions.append("calendar.enrich")
            data["occasions"] = day.occasions
            data["affect"] = day.affect
            data["weather"] = day.weather
            control = self._run_control(day)
            data["control"] = {
                "max_tasks": control.get("neuromodulators", {}).get("max_tasks"),
                "homeostasis": control.get("homeostasis", {}).get("status"),
                "predictive": control.get("predictive_homeostasis", {}).get("risk_level"),
                "plasticity": control.get("plasticity", {}).get("active"),
            }
            actions.extend(
                ["neuro.daily_control_plane", "predictive.forecast", "plasticity.intervene"]
            )
        except Exception as e:
            return self._emit(TriggerId.T_DAY_START, False, actions, data, [str(e)])
        return self._emit(TriggerId.T_DAY_START, True, actions, data)

    def on_sleep(self, sleep_hours: float) -> CoherenceEvent:
        self._sleep_hours = sleep_hours
        day = self.calendar.get_day(date.today(), enrich=True)
        control = self._run_control(day)
        return self._emit(
            TriggerId.T_SLEEP_REPORTED,
            True,
            ["neuromod.compute", "homeostasis.evaluate", "predictive.forecast"],
            {
                "sleep_hours": sleep_hours,
                "max_tasks": control["neuromodulators"]["max_tasks"],
                "capacity_notes": control["neuromodulators"]["notes"],
                "predictive_risk": control.get("predictive_homeostasis", {}).get("risk_level"),
            },
        )

    def on_schedule_add(
        self,
        title: str,
        *,
        day: Optional[date] = None,
        kind: str = "task",
        project_id: Optional[str] = None,
    ) -> CoherenceEvent:
        day = day or date.today()
        actions = []
        data: Dict[str, Any] = {}
        # refresh control
        daylog = self.calendar.get_day(day, enrich=True)
        control = self._run_control(daylog)
        gate = control.get("schedule_gate") or {}
        actions.append("homeostasis.assert_can_schedule")
        if not gate.get("allowed", True):
            return self._emit(
                TriggerId.T_SCHEDULE_ADD_REQUEST,
                False,
                actions + ["reject_locked"],
                {"reason": gate.get("reason"), "gate": gate},
            )

        scheduled = len(daylog.schedule or [])
        max_tasks = control.get("neuromodulators", {}).get("max_tasks", 8)
        pred = control.get("predictive_homeostasis") or {}
        if scheduled >= max_tasks:
            return self._emit(
                TriggerId.T_SCHEDULE_ADD_REQUEST,
                False,
                actions + ["reject_over_capacity"],
                {
                    "scheduled": scheduled,
                    "max_tasks": max_tasks,
                    "suggestion": f"At capacity ({max_tasks}). Defer or swap a task.",
                    "predictive_risk": pred.get("risk_level"),
                },
            )

        warnings = []
        if pred.get("risk_level") in ("high", "critical"):
            warnings.append("Predictive risk elevated — consider recovery block instead.")
            actions.append("predictive_warn")

        self.calendar.add_schedule(day, title, kind=kind, project_id=project_id)
        actions.append("calendar.add_schedule")
        data.update(
            {
                "title": title,
                "day": day.isoformat(),
                "max_tasks": max_tasks,
                "scheduled_after": scheduled + 1,
                "warnings": warnings,
            }
        )
        return self._emit(TriggerId.T_SCHEDULE_ADD_REQUEST, True, actions, data)

    def on_progress(
        self, project_id: str, name: str, percent: float, *, day: Optional[date] = None, note: str = ""
    ) -> CoherenceEvent:
        day = day or date.today()
        prev = 0.0
        daylog = self.calendar.get_day(day, enrich=False)
        for p in daylog.project_progress or []:
            if p.get("project_id") == project_id:
                prev = float(p.get("percent") or 0)
        delta = percent - prev
        self.calendar.set_project_progress(day, project_id, name, percent, note)
        actions = ["calendar.set_project_progress"]
        if delta > 0:
            self.neuro.neuromod.register_reward(min(1.0, delta / 25.0))
            actions.append("neuromod.register_reward")
        if percent >= 100:
            self.decade.fisherman.catch(
                day,
                f"Milestone complete: {name}",
                title="Catch: milestone",
                importance=0.95,
                tags=["milestone", project_id],
            )
            actions.append("fisherman.catch")
        # plasticity observation
        w = self.calendar.get_day(day, enrich=True)
        wx = (w.weather or {}).get("condition", "clear")
        noise = float((w.weather or {}).get("noise_db") or 45)
        valence = float((w.affect or {}).get("valence") or 0)
        self.neuro.plasticity.observe_day(
            day, weather_condition=wx, noise_db=noise, progress_delta=delta, valence=valence
        )
        actions.append("plasticity.observe_day")
        return self._emit(
            TriggerId.T_PROGRESS_UPDATE,
            True,
            actions,
            {"project_id": project_id, "percent": percent, "delta": delta},
        )

    def on_pain(self, pain_level: float) -> CoherenceEvent:
        self._pain = pain_level
        day = self.calendar.get_day(date.today(), enrich=True)
        control = self._run_control(day)
        locked = control.get("homeostasis", {}).get("schedule_locked")
        return self._emit(
            TriggerId.T_PAIN_SPIKE if pain_level >= 0.6 else TriggerId.T_AFFECT_REFRESH,
            True,
            ["homeostasis.evaluate", "predictive.forecast"],
            {
                "pain": pain_level,
                "schedule_locked": locked,
                "status": control.get("homeostasis", {}).get("status"),
            },
        )

    def on_midnight(self, transcript_segments: List[str]) -> CoherenceEvent:
        actions = []
        data: Dict[str, Any] = {}
        cons = self.neuro.midnight_consolidation(transcript_segments)
        actions.append("consolidation.consolidate")
        data["consolidation"] = {
            "kept": cons.get("kept_segments"),
            "dropped": cons.get("dropped_segments"),
            "summary": cons.get("summary"),
        }
        # promote lessons to fisherman
        for lesson in (cons.get("lessons") or [])[:5]:
            self.decade.fisherman.catch(
                date.today(),
                lesson,
                title="Catch: consolidated lesson",
                importance=0.85,
                tags=["consolidated", "lesson"],
            )
            actions.append("fisherman.catch_lesson")
        # era check
        rec = self.era.distill_year(
            self.calendar, self.decade, year=date.today().year, min_filled_ratio=0.12
        )
        if rec:
            actions.append("era.distill_year")
            data["era_id"] = rec.era_id
            data["era_summary"] = rec.summary
        else:
            actions.append("era.skip_insufficient")
        return self._emit(TriggerId.T_MIDNIGHT_CONSOLIDATION, True, actions, data)

    def on_location(self, country: str, city: str, latitude: float = 59.95) -> CoherenceEvent:
        self.calendar.set_location(country, city, latitude)
        day = self.calendar.get_day(date.today(), enrich=True)
        return self._emit(
            TriggerId.T_LOCATION_CHANGE,
            True,
            ["calendar.set_location", "holidays.refresh", "weather.reseed"],
            {"country": country, "city": city, "occasions": day.occasions},
        )

    # ----- context for Jeeves -------------------------------------------------

    def jeeves_context_block(self) -> str:
        parts = []
        try:
            parts.append(self.calendar.jeeves_context_block())
        except Exception:
            pass
        try:
            if not self._last_control:
                day = self.calendar.get_day(date.today(), enrich=True)
                self._run_control(day)
            parts.append(self.neuro.jeeves_context_block(self._last_control))
        except Exception:
            pass
        try:
            parts.append(self.era.chain_summary())
        except Exception:
            pass
        # recent coherence
        if self.history:
            last = self.history[-3:]
            parts.append("[COHERENCE RECENT]")
            for e in last:
                parts.append(f"- {e.trigger}: ok={e.ok} actions={','.join(e.actions[:5])}")
        return "\n\n".join(p for p in parts if p)

    def matrix(self) -> List[dict]:
        return trigger_matrix()

    # ----- internals ----------------------------------------------------------

    def _run_control(self, daylog) -> Dict[str, Any]:
        wx = (daylog.weather or {}) if hasattr(daylog, "weather") else {}
        aff = (daylog.affect or {}) if hasattr(daylog, "affect") else {}
        if isinstance(daylog, dict):
            wx = daylog.get("weather") or {}
            aff = daylog.get("affect") or {}
            scheduled = len(daylog.get("schedule") or [])
        else:
            scheduled = len(daylog.schedule or [])
        control = self.neuro.daily_control_plane(
            sleep_hours=self._sleep_hours,
            weather_condition=(wx or {}).get("condition") or "clear",
            noise_db=float((wx or {}).get("noise_db") or 45),
            affect_energy=float((aff or {}).get("energy") or 0.55),
            affect_valence=float((aff or {}).get("valence") or 0.1),
            pain_level=self._pain,
            progress_delta=0.0,
            scheduled_count=scheduled,
            stress_hints=0,
        )
        self._last_control = control
        return control

    def _emit(
        self,
        trigger: TriggerId,
        ok: bool,
        actions: List[str],
        data: Optional[Dict[str, Any]] = None,
        errors: Optional[List[str]] = None,
    ) -> CoherenceEvent:
        ev = CoherenceEvent(
            trigger=trigger.value if isinstance(trigger, TriggerId) else str(trigger),
            ok=ok,
            actions=actions,
            data=data or {},
            errors=errors or [],
        )
        self.history.append(ev)
        if len(self.history) > 200:
            self.history = self.history[-200:]
        logger.debug("coherence %s ok=%s actions=%s", ev.trigger, ok, actions)
        return ev


    def reliable_day_start(self):
        return self.executor.run_sync("day_start", lambda: self.on_day_start().to_dict())

    def reliable_transcript(self, segment: str):
        return self.executor.run_sync("transcript_segment", lambda: self.on_transcript(segment).to_dict())

    def reliable_schedule(self, title: str, **kw):
        def _fn():
            ev = self.on_schedule_add(title, **kw)
            if not ev.ok:
                raise TriggerExecutionError(
                    TriggerError(
                        TriggerErrorCode.LOCKED if "reject_locked" in ev.actions else TriggerErrorCode.CAPACITY,
                        ev.data.get("reason") or ev.data.get("suggestion") or "schedule rejected",
                        retryable=False,
                        details=ev.data,
                    )
                )
            return ev.to_dict()
        return self.executor.run_sync("schedule_add_request", _fn)

    def trigger_logs(self, n: int = 50):
        return self.executor.log.recent(n)

    def trigger_stats(self):
        return {"log": self.executor.log.stats(), "dead_letter": self.executor.dead_letter[-20:]}
