"""Deterministic generic executable kernel for 10,240 original-law crossings.

A shared 12-sector causal prototype implements one mechanically distinct
domain intervention and one of ten real consequence operators per foundation.
This proves stateful interactions, not full realization of each root's
handwritten fictional law, level design, NPCs, 3D physics or console builds.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_foundation_compiler import (
    FoundationError, FoundationLaw, foundation_at,
    foundation_by_id, REGIME_COUNT,
    STRUCTURED_FOUNDATIONS, FOUNDATION_VERSION,
)

ENGINE_SCHEMA = "original-foundation-causal-kernel.v1"
WORLD_ROOMS = 12
MAX_EVENTS = 1000
ACTIONS = frozenset({
    "intervene", "study", "restore", "negotiate", "donate",
    "move", "survey", "trade", "build", "rest",
    "choose", "end_turn", "salvage",
})
DOMAINS = {
    "geometry": ("passages", "isolation"),
    "chronology": ("epochs", "paradox"),
    "ecosphere": ("habitat", "collapse"),
    "materials": ("material", "entropy"),
    "governance": ("mandate", "legitimacy"),
    "community": ("community", "fracture"),
    "commerce": ("credit", "insolvency"),
    "memory": ("memory", "amnesia"),
    "language": ("meaning", "ambiguity"),
    "metaphysics": ("myth", "contradiction"),
    "navigation": ("voyage", "stranding"),
    "discovery": ("discovery", "ignorance"),
    "simulation": ("agency", "control"),
    "craft": ("craft", "scarcity"),
    "affection": ("affinity", "alienation"),
    "survival": ("survival", "extinction"),
}
if len(DOMAINS) != 16:
    raise RuntimeError("missing executable causal domain")


@dataclass(frozen=True)
class CausalAction:
    verb: str
    amount: int = 1
    option: str = ""
    target: int = -1


@dataclass(frozen=True)
class CausalState:
    foundation_id: str
    tick: int = 0
    action_points: int = 4
    position: int = 0
    energy: int = 12
    supplies: int = 12
    reserve: int = 6
    trust: int = 9
    evidence: int = 2
    primary: int = 0
    remote: int = 0
    hazard: int = 0
    duty: int = 0
    echo_due: int = 0
    momentum: int = 0
    milestones: int = 0
    outposts: int = 0
    investigated: tuple[int, ...] = (0,)
    branch: str = ""
    chapter_complete: bool = False
    event_count: int = 0
    event_head: str = "0" * 64


@dataclass(frozen=True)
class CausalReceipt:
    action: CausalAction
    before: str
    after: str
    event_hash: str
    changes: tuple[str, ...]
    number: int


def _digest(data: object) -> str:
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                             allow_nan=False, ensure_ascii=False).encode("utf-8")).hexdigest()


def _bounds(value: int, low: int, high: int, field: str) -> None:
    if type(value) is not int or not low <= value <= high:
        raise FoundationError("invalid causal state " + field)


def _variant(law: FoundationLaw) -> int:
    return law.foundation_index // REGIME_COUNT % 8


def _params(law: FoundationLaw) -> tuple[int, int, int]:
    """Each authored root has a distinct measurable cost/strength profile."""
    variant = _variant(law)
    return 1 + variant % 4, 1 + variant // 4, 1 + variant % 3


def _law(state: CausalState) -> FoundationLaw:
    try:
        return foundation_by_id(state.foundation_id)
    except FoundationError as exc:
        raise FoundationError("save references unknown original foundation") from exc


def validate_causal(state: CausalState) -> FoundationLaw:
    if not isinstance(state, CausalState):
        raise FoundationError("invalid causal state type")
    law = _law(state)
    bounds = {
        "tick": (0, 1000000), "action_points": (0, 4),
        "position": (0, WORLD_ROOMS - 1),
        "energy": (0, 20), "supplies": (0, 10000),
        "reserve": (0, 10000), "trust": (0, 100),
        "evidence": (0, 100), "primary": (0, 1000),
        "remote": (0, 1000), "hazard": (0, 100),
        "duty": (0, 1000), "echo_due": (0, 1000),
        "momentum": (0, 100), "milestones": (0, 100),
        "outposts": (0, WORLD_ROOMS),
        "event_count": (0, MAX_EVENTS),
    }
    for name, (low, high) in bounds.items():
        _bounds(getattr(state, name), low, high, name)
    if state.branch not in {"", "care", "power"}:
        raise FoundationError("unrecognized causal branch")
    if not isinstance(state.chapter_complete, bool):
        raise FoundationError("invalid chapter completion flag")
    if (state.chapter_complete and law.ending_policy == "unwinnable"):
        raise FoundationError("nonwinnable world cannot be marked completed")
    if (not isinstance(state.investigated, tuple) or
            len(set(state.investigated)) != len(state.investigated) or
            0 not in state.investigated or state.position not in state.investigated or
            any(type(i) is not int or not 0 <= i < WORLD_ROOMS
                for i in state.investigated)):
        raise FoundationError("invalid discovered sector ledger")
    if not isinstance(state.event_head, str) or len(state.event_head) != 64 or any(
        c not in "0123456789abcdef" for c in state.event_head
    ):
        raise FoundationError("invalid causal event chain digest")
    return law


def create_causal(foundation: int | str) -> CausalState:
    if type(foundation) is int:
        law = foundation_at(foundation)
    elif isinstance(foundation, str):
        law = foundation_by_id(foundation)
    else:
        raise FoundationError("invalid foundation selector")
    state = CausalState(foundation_id=law.foundation_id)
    validate_causal(state)
    return state


def paths(state: CausalState) -> tuple[tuple[int, int], ...]:
    law = validate_causal(state)
    # All foundations have a connected backbone, even when geometry mutates.
    routes = {tuple(sorted((i, (i + 1) % WORLD_ROOMS)))
              for i in range(WORLD_ROOMS)}
    phase = state.tick if law.domain == "geometry" else state.primary
    a = (phase + _variant(law)) % WORLD_ROOMS
    b = (a + 5) % WORLD_ROOMS
    routes.add(tuple(sorted((a, b))))
    if law.regime.operator == "reverse" and state.event_count % 2:
        u = (a + 3) % WORLD_ROOMS
        routes.add(tuple(sorted((u, (u + 6) % WORLD_ROOMS))))
    return tuple(sorted(routes))


def available_exits(state: CausalState) -> tuple[int, ...]:
    return tuple(sorted({
        right if left == state.position else left
        for left, right in paths(state) if state.position in (left, right)
    }))


def _alter(state: CausalState, **deltas: int) -> CausalState:
    fields = {}
    for field, difference in deltas.items():
        if type(difference) is not int:
            raise FoundationError("noninteger causal delta")
        result = getattr(state, field) + difference
        if result < 0:
            raise FoundationError("insufficient " + field)
        limit = {
            "primary": 1000, "remote": 1000,
            "duty": 1000, "echo_due": 1000,
            "energy": 20, "hazard": 100, "momentum": 100,
            "trust": 100, "evidence": 100, "reserve": 10000,
            "supplies": 10000, "milestones": 100,
            "outposts": WORLD_ROOMS,
        }.get(field, 1000)
        fields[field] = min(limit, result)
    return replace(state, **fields)


def _domain_effect(state: CausalState, law: FoundationLaw,
                   amount: int, costs: int, power: int,
                   hazard: int) -> tuple[CausalState, tuple[str, ...]]:
    domain = law.domain
    if state.energy < costs or state.supplies < amount:
        raise FoundationError("primary causal intervention lacks physical resources")
    if domain == "governance" and state.trust < 5:
        raise FoundationError("civic action requires proven legitimacy")
    if domain == "metaphysics" and state.trust < 6:
        raise FoundationError("invented ritual requires communal consent")
    if domain == "discovery" and state.evidence < 2:
        raise FoundationError("research requires independent evidence")
    if domain == "simulation" and state.reserve < 2:
        raise FoundationError("automated systems need a failsafe reserve")
    if domain == "navigation" and state.position == 0 and state.evidence < 2:
        raise FoundationError("departure requires a verified route")
    if domain == "craft" and state.supplies < amount + 1:
        raise FoundationError("craft needs a repair reserve")
    before = state.primary
    state = _alter(state, energy=-costs, supplies=-amount,
                   primary=power * amount,
                   hazard=hazard, duty=amount)
    messages = [f"Intervened in {law.root.meter}: {before} -> {state.primary}"]
    if domain == "ecosphere":
        state = _alter(state, reserve=amount)
        messages.append("Restoration stored a future ecological reserve")
    elif domain == "chronology":
        state = _alter(state, echo_due=amount)
        messages.append("Borrowed time will mature on the next world turn")
    elif domain == "geometry":
        messages.append("Transit graph must be recomputed after this decision")
    elif domain == "materials":
        state = _alter(state, hazard=amount)
        messages.append("Manufacturing accrued tangible fatigue")
    elif domain in ("community", "affection"):
        state = _alter(state, trust=amount)
        messages.append("Consent-based cooperation strengthened communal trust")
    elif domain == "commerce":
        state = _alter(state, reserve=amount)
        messages.append("Trade margin was assigned to a solvency reserve")
    elif domain in ("memory", "language"):
        state = _alter(state, evidence=-1)
        messages.append("Interpretation spent one verified evidence token")
    elif domain == "metaphysics":
        state = _alter(state, reserve=amount)
        messages.append("Invented ritual transferred tangible offerings")
    elif domain in ("navigation", "discovery"):
        state = _alter(state, evidence=1)
        messages.append("Field work generated a usable public observation")
    elif domain == "simulation":
        state = _alter(state, reserve=-1)
        messages.append("Machine action consumed one safety resource")
    elif domain == "craft":
        state = _alter(state, remote=amount)
        messages.append("Craft produced a tangible independent part")
    elif domain == "survival":
        state = _alter(state, energy=min(amount, 20 - state.energy))
        messages.append("Survival action converted supplies into recovery")
    elif domain == "governance":
        state = _alter(state, trust=-1)
        messages.append("Using authority incurs public review pressure")
    return state, tuple(messages)


def _regime_effect(state: CausalState, law: FoundationLaw,
                   n: int, power: int) -> tuple[CausalState, tuple[str, ...]]:
    regime = law.regime
    intensity = regime.intensity
    op = regime.operator
    messages = [f"Activated causal overlay: {regime.title}"]
    if op == "echo":
        state = _alter(state, echo_due=n + intensity // 3,
                       duty=1)
        messages.append("Extra effects are scheduled for a later world turn")
    elif op == "levy":
        cost = 1 + intensity // 3
        if state.supplies < cost:
            raise FoundationError("public causal levy cannot be paid")
        state = _alter(state, supplies=-cost, reserve=cost)
        messages.append("Public commons received a real levy transfer")
    elif op == "reverse":
        if state.momentum % 2 == 0:
            state = _alter(state, primary=-min(state.primary, power * n),
                           remote=1)
            messages.append("Alternate intervention reversed prior progress")
        else:
            messages.append("Current alternating phase preserves progress")
        state = _alter(state, momentum=1)
    elif op == "threshold":
        gate = 3 + intensity
        if state.primary >= gate and state.milestones == 0:
            state = _alter(state, milestones=1, hazard=1 + intensity // 2)
            messages.append("Threshold unlocked one new capability and risk")
        else:
            messages.append("Threshold remains a measurable causal goal")
    elif op == "migration":
        transferred = min(state.primary, 1 + intensity // 2)
        state = _alter(state, primary=-transferred, remote=transferred,
                       duty=1)
        messages.append("Benefit migrated from the local system to a remote one")
    elif op == "veto":
        minimum = 5 + intensity // 2
        if state.trust < minimum:
            raise FoundationError("independent social consent blocked this intervention")
        state = _alter(state, trust=-1, reserve=1)
        messages.append("Public consent authorized a bounded change")
    elif op == "cascade":
        charge = min(10, state.momentum + 1 + intensity // 4)
        state = _alter(state, momentum=1, primary=charge,
                       hazard=charge, duty=charge)
        messages.append("Coupled systems amplified benefits and obligations")
    elif op == "exchange":
        charge = 1 + intensity // 3
        if state.reserve < charge:
            raise FoundationError("shared exchange pool lacks real reserves")
        state = _alter(state, reserve=-charge, supplies=charge,
                       hazard=1)
        messages.append("Real commons resources were exchanged for private supply")
    elif op == "auction":
        bid = 1 + intensity // 2
        if state.supplies < bid:
            raise FoundationError("cannot place an unfunded public bid")
        state = _alter(state, supplies=-bid, reserve=bid,
                       evidence=1)
        messages.append("Verified resource bid transferred into public escrow")
    elif op == "fork":
        if not state.branch:
            state = replace(state, branch="care")
            messages.append("A continuing care branch emerged; alternative retained")
        elif state.branch == "care":
            state = _alter(state, remote=1, trust=1)
            messages.append("Care branch preserved vulnerable remote communities")
        else:
            state = _alter(state, primary=1, hazard=2)
            messages.append("Power branch accelerated change with additional risk")
    else:
        raise FoundationError("unimplemented causal overlay")
    return state, tuple(messages)


def _action(state: CausalState, law: FoundationLaw,
            action: CausalAction) -> tuple[CausalState, tuple[str, ...]]:
    if state.action_points == 0:
        raise FoundationError("end turn to refresh action points")
    state = replace(state, action_points=state.action_points - 1)
    n, verb = action.amount, action.verb
    power, costs, hazard = _params(law)
    messages = []
    if verb == "intervene":
        if law.regime.operator == "veto":
            threshold = 5 + law.regime.intensity // 2
            if state.trust < threshold:
                raise FoundationError("veto: build genuine trust before intervention")
        # Worst-case auction and levy costs are deducted transactionally.
        state, effect = _domain_effect(state, law, n, costs, power, hazard)
        state, overlay = _regime_effect(state, law, n, power)
        messages.extend((*effect, *overlay, "Joint causal law: " + law.coupling))
    elif verb == "study":
        if state.energy < n:
            raise FoundationError("investigation requires energy")
        state = _alter(state, energy=-n, evidence=2 * n)
        messages.append("Collected independently reviewable evidence")
    elif verb == "restore":
        if state.supplies < n:
            raise FoundationError("restoration requires stored supplies")
        state = _alter(state, supplies=-n, hazard=-min(state.hazard, 3 * n),
                       reserve=n, duty=-min(state.duty, n))
        messages.append("Paid the public cost of restoring damaged systems")
    elif verb == "negotiate":
        if state.energy < n:
            raise FoundationError("negotiation requires care and energy")
        state = _alter(state, energy=-n, trust=2 * n,
                       hazard=-min(state.hazard, n))
        messages.append("Built reciprocal consent and reduced risk")
    elif verb == "donate":
        if state.supplies < n:
            raise FoundationError("cannot contribute unavailable supplies")
        state = _alter(state, supplies=-n, reserve=n, trust=n)
        messages.append("Contributed real materials to the commons")
    elif verb == "move":
        if n != 1 or action.target not in available_exits(state):
            raise FoundationError("destination is not reachable via a current route")
        if state.energy < 1:
            raise FoundationError("travel requires energy")
        state = _alter(state, energy=-1)
        old_position = state.position
        state = replace(state, position=action.target,
                        investigated=tuple(sorted(set(state.investigated) |
                                                   {action.target})))
        messages.append(f"Traveled from {old_position} to {action.target}")
    elif verb == "survey":
        reachable = [i for i in available_exits(state)
                     if i not in state.investigated]
        if not reachable or state.energy < 1:
            raise FoundationError("no new reachable sector or insufficient energy")
        state = _alter(state, energy=-1, evidence=1)
        state = replace(state,
                        investigated=tuple(sorted(state.investigated + (reachable[0],))))
        messages.append(f"Survey revealed reachable sector {reachable[0]}")
    elif verb == "trade":
        if state.reserve < n:
            raise FoundationError("commons has insufficient available supplies")
        state = _alter(state, reserve=-n, supplies=n,
                       trust=-min(state.trust, 1))
        messages.append("Acquired supplies from a finite communal warehouse")
    elif verb == "build":
        if state.supplies < 3 or state.primary < 2 or state.outposts >= WORLD_ROOMS:
            raise FoundationError("construction lacks resources, progress or space")
        state = _alter(state, supplies=-3, outposts=1, reserve=1)
        messages.append("Established a lasting settlement with real material cost")
    elif verb == "rest":
        state = _alter(state, energy=min(3 * n, 20 - state.energy))
        messages.append("Recovered finite physical stamina")
    elif verb == "salvage":
        if state.energy < n or state.reserve < n:
            raise FoundationError("salvage needs effort and available scrap")
        state = _alter(state, energy=-n, reserve=-n, supplies=n)
        messages.append("Recovered real material from the commons' scrap reserve")
    elif verb == "choose":
        if law.regime.operator != "fork" or action.option not in {"care", "power"}:
            raise FoundationError("branch choice unavailable")
        if state.branch:
            raise FoundationError("persistent fork already selected")
        state = replace(state, branch=action.option)
        if action.option == "care":
            state = _alter(state, trust=2)
        else:
            state = _alter(state, primary=2, hazard=2)
        messages.append("Locked in distinct persistent branch: " + action.option)
    else:
        raise FoundationError("unsupported player action")
    return state, tuple(messages)


def _turn(state: CausalState, law: FoundationLaw
          ) -> tuple[CausalState, tuple[str, ...]]:
    if state.tick >= 1000000:
        raise FoundationError("bounded world turn horizon reached")
    messages = []
    state = replace(state, tick=state.tick + 1,
                    action_points=4,
                    energy=min(20, state.energy + 2))
    if state.echo_due:
        value = min(1000 - state.primary, state.echo_due)
        state = _alter(state, primary=value,
                       hazard=min(100 - state.hazard, state.echo_due // 2),
                       echo_due=-state.echo_due)
        messages.append("Delayed causal effects matured; material debts remain")
    if state.duty and state.tick % 3 == 0:
        # Unpaid common obligations decay available public resilience.
        state = _alter(state, reserve=-min(state.reserve, 1),
                       hazard=min(100 - state.hazard, 1))
        messages.append("Unpaid duties weakened communal reserves")
    if law.domain == "ecosphere" and state.tick % 4 == 0:
        state = _alter(state, reserve=1)
        messages.append("Habitat regeneration restored one public unit")
    if law.domain == "survival" and state.tick % 2 == 0:
        if state.supplies > 0:
            state = _alter(state, supplies=-1)
            messages.append("Sustenance consumed one finite ration")
        else:
            state = _alter(state, hazard=min(100 - state.hazard, 2))
    if law.domain == "chronology" and state.tick % 5 == 0:
        state = _alter(state, duty=1)
        messages.append("Temporal audit introduced future-action obligations")
    if state.chapter_complete:
        messages.append("Chapter closed but persistent postgame obligations continue")
    return state, tuple(messages or ("World advanced with bounded ecological/social clocks",))


def step_causal(state: CausalState, action: CausalAction
                ) -> tuple[CausalState, CausalReceipt]:
    law = validate_causal(state)
    if state.event_count >= MAX_EVENTS:
        raise FoundationError("causal event history limit reached")
    if not isinstance(action, CausalAction) or action.verb not in ACTIONS:
        raise FoundationError("unrecognized causal action")
    _bounds(action.amount, 1, 3, "action quantity")
    _bounds(action.target, -1, WORLD_ROOMS - 1, "action destination")
    if not isinstance(action.option, str) or len(action.option) > 32:
        raise FoundationError("invalid action option")
    if (state.chapter_complete and law.ending_policy == "closed"
            and action.verb != "end_turn"):
        raise FoundationError("this authored world has a closed ending")
    if action.verb == "end_turn":
        updated, messages = _turn(state, law)
    else:
        updated, messages = _action(state, law, action)
    if (not updated.chapter_complete and law.ending_policy != "unwinnable" and
            updated.primary >= 12 + _variant(law) and
            updated.trust >= 4 and updated.hazard < 50):
        updated = replace(updated, chapter_complete=True)
        messages += ("An authored chapter milestone was completed",)
    before = _digest(asdict(state))
    after = _digest(asdict(updated))
    event_id = _digest({
        "schema": ENGINE_SCHEMA, "foundation": law.design_id,
        "prior_head": state.event_head, "before": before,
        "after": after, "action": asdict(action), "changes": messages,
    })
    result = replace(updated, event_count=state.event_count + 1,
                     event_head=event_id)
    validate_causal(result)
    receipt = CausalReceipt(
        action, before, _digest(asdict(result)),
        event_id, tuple(messages), result.event_count,
    )
    return result, receipt


def replay_causal(index: int, actions: tuple[CausalAction, ...]):
    if not isinstance(actions, tuple) or len(actions) > MAX_EVENTS:
        raise FoundationError("causal replay requires a bounded tuple")
    state = create_causal(index)
    receipts = []
    for action in actions:
        state, receipt = step_causal(state, action)
        receipts.append(receipt)
    return state, tuple(receipts)


def save_causal(state: CausalState) -> str:
    law = validate_causal(state)
    data = {
        "schema": ENGINE_SCHEMA,
        "foundation": law.design_id,
        "state": asdict(state),
    }
    return json.dumps(
        {"payload": data, "checksum": _digest(data)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def restore_causal(serialized: str) -> CausalState:
    if not isinstance(serialized, str) or len(serialized.encode("utf-8")) > 65536:
        raise FoundationError("invalid or oversized causal save")
    try:
        envelope = json.loads(serialized)
        if set(envelope) != {"payload", "checksum"}:
            raise FoundationError("unknown save envelope")
        payload = envelope["payload"]
        if (set(payload) != {"schema", "foundation", "state"} or
                payload["schema"] != ENGINE_SCHEMA or
                False):
            raise FoundationError("unknown causal save schema")
        if _digest(payload) != envelope["checksum"]:
            raise FoundationError("causal save integrity failed")
        raw = payload["state"]
        if set(raw) != set(CausalState.__dataclass_fields__):
            raise FoundationError("unexpected causal save fields")
        raw["investigated"] = tuple(raw["investigated"])
        state = CausalState(**raw)
        law = validate_causal(state)
        if law.design_id != payload["foundation"]:
            raise FoundationError("causal law changed across save")
        return state
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise FoundationError("invalid causal save") from exc
