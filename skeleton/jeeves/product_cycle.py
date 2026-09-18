"""Jeeves product cycle — pointer parse plus lazy doctor / nervous / product.

This plane is the GB-12 direction: keep tutor Jeeves and plan_build intact,
split stimulus into pointer clauses only, and run a fail-closed readiness
cycle without importing organism.doctor at module load.

Cards never carry stored prose. Extra pointer clauses drop with hit=0
instead of spilling the source sentence into the mesh.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

N_CAP = 8
CYCLE_VERSION = "product-cycle.v1"

_URL_RE = re.compile(
    r"https?://[^\s<>\"')\]]+",
    re.IGNORECASE,
)
_BARE_GITHUB_RE = re.compile(
    r"(?<![\w./])github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
    re.IGNORECASE,
)
_ARXIV_ABS_RE = re.compile(
    r"(?:arxiv\.org/abs/|arxiv:)([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)",
    re.IGNORECASE,
)


def _fingerprint(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError("expected mapping or None")


def parse_pointers(stimulus: Any) -> dict[str, Any]:
    """Split stimulus into at most N_CAP pointer clauses. No stored sentence."""
    if stimulus is None:
        text = ""
    elif isinstance(stimulus, str):
        text = stimulus
    else:
        raise TypeError("stimulus must be a string")

    seen: list[str] = []
    dropped = 0

    def _admit(pointer: str) -> None:
        nonlocal dropped
        clean = pointer.rstrip(").,;:]")
        if not clean:
            return
        if clean in seen:
            return
        if len(seen) >= N_CAP:
            dropped += 1
            return
        seen.append(clean)

    for match in _URL_RE.finditer(text):
        _admit(match.group(0))
    for match in _BARE_GITHUB_RE.finditer(text):
        _admit(match.group(0))
    for match in _ARXIV_ABS_RE.finditer(text):
        _admit(f"https://arxiv.org/abs/{match.group(1)}")

    hit = 1 if seen and dropped == 0 else (1 if seen else 0)
    if dropped:
        hit = 0
    card = {
        "kind": "parse",
        "n": len(seen),
        "pointers": tuple(seen),
        "dropped": dropped,
        "n_cap": N_CAP,
        "hit": hit,
        "law": "ok" if dropped == 0 else "n-cap",
        "stored_prose": 0,
    }
    card["fingerprint"] = _fingerprint(
        {"kind": "parse", "pointers": list(seen), "dropped": dropped}
    )
    return card


def _gap_codes(pack: Mapping[str, Any], plan: Mapping[str, Any], walk: Mapping[str, Any]) -> list[str]:
    gaps: list[str] = []
    era = str(pack.get("era") or plan.get("era") or walk.get("era") or "").strip()
    if not era:
        gaps.append("era-unbound")
    if pack and "primary_dps" in pack:
        try:
            dps = float(pack.get("primary_dps") or 0)
        except (TypeError, ValueError):
            dps = 0.0
        if dps <= 0:
            gaps.append("dps-missing")
    seed = plan.get("seed")
    if plan and not seed:
        gaps.append("plan-seed-missing")
    if walk:
        extracted = bool(walk.get("extracted"))
        collapsed = bool(walk.get("collapsed"))
        if collapsed:
            gaps.append("walk-collapsed")
        if not extracted and not collapsed:
            gaps.append("walk-unextracted")
    return gaps


def _slack(walk: Mapping[str, Any]) -> float:
    raw = walk.get("slack")
    if raw is None:
        t = float(walk.get("t") or 0)
        collapse = float(walk.get("collapse_max") or 0)
        extracted = bool(walk.get("extracted"))
        collapsed = bool(walk.get("collapsed"))
        if extracted and collapse > 0 and t > 0:
            raw = (collapse - t) / collapse
        elif collapsed or not extracted:
            raw = 0.0
        else:
            raw = 1.0
    try:
        slack = float(raw)
    except (TypeError, ValueError):
        slack = 0.0
    if slack < 0.0:
        return 0.0
    if slack > 1.0:
        return 1.0
    return slack


class ProductCycle:
    """Lazy doctor → nervous → product conductor bound to a Jeeves host."""

    def __init__(self, host: Any | None = None) -> None:
        self._host = host

    def _host_state(self) -> tuple[Any, dict[str, Any], dict[str, Any], str]:
        host = self._host
        pack: dict[str, Any] = {}
        walk: dict[str, Any] = {}
        era = "extraction_now"
        if host is not None:
            era = str(getattr(host, "era", era) or era)
            last_walk = getattr(host, "last_walk", None)
            if isinstance(last_walk, Mapping):
                walk = dict(last_walk)
            last_plan = getattr(host, "last_plan", None)
            if last_plan is not None and hasattr(last_plan, "to_dict"):
                pack_or_plan = last_plan.to_dict()
                if isinstance(pack_or_plan, Mapping):
                    pack = dict(pack_or_plan)
            elif isinstance(last_plan, Mapping):
                pack = dict(last_plan)
        return host, pack, walk, era

    def doctor(
        self,
        stimulus: str = "",
        *,
        pack: Mapping[str, Any] | None = None,
        plan: Mapping[str, Any] | None = None,
        walk: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Diagnose readiness. Never imports organism.doctor."""
        parsed = parse_pointers(stimulus)
        host, host_plan, host_walk, era = self._host_state()
        pack_map = _as_mapping(pack) if pack is not None else {}
        plan_map = _as_mapping(plan) if plan is not None else host_plan
        walk_map = _as_mapping(walk) if walk is not None else host_walk
        if not pack_map and host is not None:
            bound_era = str(getattr(host, "era", "") or era)
            pack_map = {"era": bound_era}
        era = str(pack_map.get("era") or plan_map.get("era") or walk_map.get("era") or era)
        gaps = _gap_codes(pack_map, plan_map, walk_map)
        if parsed["dropped"]:
            gaps.append("pointer-overflow")
        ready = not gaps
        law = "ok" if ready else "gaps"
        card = {
            "kind": "doctor",
            "hit": 1 if ready else 0,
            "law": law,
            "era": era,
            "gaps": tuple(gaps),
            "ready": ready,
            "pointers": parsed["pointers"],
            "parse": {
                "n": parsed["n"],
                "dropped": parsed["dropped"],
                "fingerprint": parsed["fingerprint"],
            },
            "stored_prose": 0,
            "version": CYCLE_VERSION,
        }
        card["fingerprint"] = _fingerprint(
            {"kind": "doctor", "era": era, "gaps": list(gaps), "pointers": list(parsed["pointers"])}
        )
        return card

    def nervous(
        self,
        stimulus: str = "",
        *,
        pack: Mapping[str, Any] | None = None,
        plan: Mapping[str, Any] | None = None,
        walk: Mapping[str, Any] | None = None,
        doctor_card: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Score strain from doctor gaps and last-walk slack."""
        diagnosis = dict(doctor_card) if doctor_card is not None else self.doctor(
            stimulus, pack=pack, plan=plan, walk=walk
        )
        _host, _host_plan, host_walk, _era = self._host_state()
        walk_map = _as_mapping(walk) if walk is not None else host_walk
        slack = _slack(walk_map) if walk_map else 1.0
        gaps = tuple(diagnosis.get("gaps") or ())
        gap_load = min(1.0, 0.2 * len(gaps))
        jitter = round(min(1.0, gap_load + (1.0 - slack) * 0.5), 6)
        if "walk-collapsed" in gaps or jitter >= 0.85:
            law = "halt"
            hit = 0
        elif gaps or jitter >= 0.45:
            law = "strained"
            hit = 1
        else:
            law = "ok"
            hit = 1
        card = {
            "kind": "nervous",
            "hit": hit,
            "law": law,
            "jitter": jitter,
            "slack": round(slack, 6),
            "gaps": gaps,
            "era": diagnosis.get("era"),
            "ready": bool(diagnosis.get("ready")) and law != "halt",
            "doctor_fp": diagnosis.get("fingerprint"),
            "pointers": tuple(diagnosis.get("pointers") or ()),
            "stored_prose": 0,
            "version": CYCLE_VERSION,
        }
        card["fingerprint"] = _fingerprint(
            {
                "kind": "nervous",
                "law": law,
                "jitter": jitter,
                "gaps": list(gaps),
                "doctor_fp": diagnosis.get("fingerprint"),
            }
        )
        return card

    def product(
        self,
        stimulus: str = "",
        *,
        pack: Mapping[str, Any] | None = None,
        plan: Mapping[str, Any] | None = None,
        walk: Mapping[str, Any] | None = None,
        nervous_card: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Emit a shippable product card. Halted nerves cannot ship."""
        nerves = dict(nervous_card) if nervous_card is not None else self.nervous(
            stimulus, pack=pack, plan=plan, walk=walk
        )
        _host, host_plan, _walk, era = self._host_state()
        plan_map = _as_mapping(plan) if plan is not None else host_plan
        law = str(nerves.get("law") or "ok")
        ship = law != "halt"
        product_law = "ok" if ship and law == "ok" else ("hold" if ship else "halt")
        card = {
            "kind": "product",
            "hit": 1 if ship else 0,
            "law": product_law,
            "ship": ship,
            "era": nerves.get("era") or era,
            "seed": plan_map.get("seed"),
            "bias": plan_map.get("room_bias") or plan_map.get("bias"),
            "jitter": nerves.get("jitter"),
            "gaps": tuple(nerves.get("gaps") or ()),
            "pointers": tuple(nerves.get("pointers") or ()),
            "nervous_fp": nerves.get("fingerprint"),
            "stored_prose": 0,
            "version": CYCLE_VERSION,
        }
        card["fingerprint"] = _fingerprint(
            {
                "kind": "product",
                "ship": ship,
                "law": product_law,
                "era": card["era"],
                "seed": card["seed"],
                "pointers": list(card["pointers"]),
            }
        )
        return card

    def cycle(
        self,
        stimulus: str = "",
        *,
        pack: Mapping[str, Any] | None = None,
        plan: Mapping[str, Any] | None = None,
        walk: Mapping[str, Any] | None = None,
        build: bool = False,
    ) -> dict[str, Any]:
        """Run parse → doctor → nervous → product. Optional plan_build."""
        parsed = parse_pointers(stimulus)
        host, host_plan, host_walk, era = self._host_state()
        built = None
        if build and host is not None and callable(getattr(host, "plan_build", None)):
            vision = ""
            built = host.plan_build(pack if isinstance(pack, dict) else None, vision=vision)
            if isinstance(built, Mapping):
                plan = dict(built)
                era = str(built.get("era") or era)
        diagnosis = self.doctor(stimulus, pack=pack, plan=plan, walk=walk)
        nerves = self.nervous(
            stimulus, pack=pack, plan=plan, walk=walk, doctor_card=diagnosis
        )
        artifact = self.product(
            stimulus, pack=pack, plan=plan, walk=walk, nervous_card=nerves
        )
        stages = ("parse", "doctor", "nervous", "product")
        card = {
            "kind": "cycle",
            "hit": int(bool(artifact.get("ship"))),
            "law": artifact.get("law") or nerves.get("law") or "ok",
            "era": artifact.get("era") or era,
            "stages": stages,
            "parse": parsed,
            "doctor": diagnosis,
            "nervous": nerves,
            "product": artifact,
            "plan": dict(plan) if isinstance(plan, Mapping) else (
                dict(built) if isinstance(built, Mapping) else dict(host_plan)
            ),
            "walk_present": bool(walk or host_walk),
            "stored_prose": 0,
            "version": CYCLE_VERSION,
        }
        card["fingerprint"] = _fingerprint(
            {
                "kind": "cycle",
                "parse": parsed.get("fingerprint"),
                "doctor": diagnosis.get("fingerprint"),
                "nervous": nerves.get("fingerprint"),
                "product": artifact.get("fingerprint"),
            }
        )
        return card


def run_cycle(stimulus: str = "", *, host: Any | None = None, **kwargs: Any) -> dict[str, Any]:
    return ProductCycle(host).cycle(stimulus, **kwargs)


def _cycle_method(name: str):
    def _method(self, stimulus: str = "", **kwargs: Any) -> dict[str, Any]:
        cycle = ProductCycle(self)
        card = getattr(cycle, name)(stimulus, **kwargs)
        bus = getattr(self, "_bus", None)
        if bus is not None and hasattr(bus, "emit"):
            bus.emit(f"jeeves.{name}", {
                "kind": card.get("kind"),
                "law": card.get("law"),
                "hit": card.get("hit"),
            })
        return card
    _method.__name__ = name
    _method.__doc__ = f"Lazy GB-12 {name} on tutor Jeeves."
    return _method


def bind_product_cycle(cls: Any | None = None) -> Any:
    """Attach doctor/nervous/product/cycle onto tutor Jeeves without rewriting organs."""
    if cls is None:
        from skeleton.jeeves.core import Jeeves as cls
    if getattr(cls, "_product_cycle_bound", False):
        return cls
    def _parse(self, stimulus: str = "") -> dict[str, Any]:
        card = parse_pointers(stimulus)
        bus = getattr(self, "_bus", None)
        if bus is not None and hasattr(bus, "emit"):
            bus.emit("jeeves.parse.pointers", {
                "n": card.get("n"), "hit": card.get("hit"), "law": card.get("law"),
            })
        return card
    cls.parse_pointers = _parse
    for name in ("doctor", "nervous", "product", "cycle"):
        setattr(cls, name, _cycle_method(name))
    cls._product_cycle_bound = True
    return cls


bind_product_cycle()


__all__ = (
    "CYCLE_VERSION",
    "N_CAP",
    "ProductCycle",
    "bind_product_cycle",
    "parse_pointers",
    "run_cycle",
)
