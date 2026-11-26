"""Proof-carrying planner for desk notes.

The desk does not call a model. Notes are compiled into a STRIPS problem:

* a positive atom is a fact (``the stove is cold``)
* ``not <atom>`` forbids that atom
* ``if <atoms> then <atom>`` is a zero-cost Horn rule, re-closed after every step
* ``to <name>: need <atoms>; gain <atoms>; lose <atoms>; cost <n>`` is an action
* ``never both <atom> and <atom>`` is a mutex
* ``budget is <n>`` is a cost ceiling

Search is forward A* with the admissible delete-relaxation heuristic h_max.
The cheapest plan is simulated again, then lifted into a partial order whose
edges are causal links and threat orderings. A goal with no producer is
infeasible. A secret-shaped note is refused and is not copied into the error.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import re
from dataclasses import dataclass

_SECRET = re.compile(r"(?i)\b(api[_-]?key|secret|password|token|bearer)\b\s*[:=]")
_ACTION = re.compile(
    r"^to (?P<name>.+?): need (?P<need>.+?); gain (?P<gain>.+?)"
    r"(?:; lose (?P<lose>.+?))?(?:; cost (?P<cost>\d+))?$"
)
_RULE = re.compile(r"^if (?P<need>.+) then (?P<gain>.+)$")
_NEVER = re.compile(r"^never both (?P<left>.+) and (?P<right>.+)$")
_BUDGET = re.compile(r"^budget(?: is)? (?P<n>\d+)$")
_NOT = re.compile(r"^not\s+(.+)$", re.IGNORECASE)
_CONJ = re.compile(r"\s+and\s+|,\s*")

_MAX_FACTS = 128
_MAX_ACTIONS = 40
_MAX_RULES = 40
_MAX_ATOM = 120
_MAX_NAME = 80
_MAX_COST = 100
_MAX_BUDGET = 10000
_MAX_EXPAND = 2000
_MAX_CLOSURE = 256
_INF = 10**9


class PlanRejected(ValueError):
    """The notes are not a planning problem."""


@dataclass(frozen=True)
class _Op:
    name: str
    need: frozenset[str]
    gain: frozenset[str]
    lose: frozenset[str]
    cost: int
    source: int
    kind: str


@dataclass(frozen=True)
class _Domain:
    primitive: frozenset[str]
    forbidden: frozenset[str]
    mutex: tuple[tuple[str, str], ...]
    actions: tuple[_Op, ...]
    rules: tuple[_Op, ...]
    budget: int | None


@dataclass(frozen=True)
class Step:
    name: str
    cost: int
    support: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Proof:
    status: str
    goal: tuple[str, ...]
    steps: tuple[Step, ...]
    cost: int
    budget: int | None
    heuristic: int | None
    critical_path: tuple[str, ...]
    parallel: tuple[tuple[str, ...], ...]
    missing: tuple[str, ...]
    conflict: tuple[str, str] | None
    expansions: int
    digest: str

    def render(self) -> str:
        lines = [f"{self.status} " + " and ".join(self.goal)]
        budget = "" if self.budget is None else f" budget {self.budget}"
        lines.append(f"cost {self.cost}{budget}")
        if self.budget is not None and self.steps and self.cost > self.budget:
            lines.append("cost exceeds budget")
        if self.heuristic is not None:
            lines.append(f"heuristic {self.heuristic}")
        if self.conflict is not None:
            lines.append(f"conflict {self.conflict[0]} / {self.conflict[1]}")
        if self.missing:
            lines.append("missing " + "; ".join(self.missing))
        for index, step in enumerate(self.steps, start=1):
            lines.append(f"{index}. {step.name} cost {step.cost}")
            for atom, producer in step.support:
                lines.append(f"   need {atom} <= {producer}")
        if self.critical_path:
            lines.append("critical " + " -> ".join(self.critical_path))
        if self.parallel:
            levels = " | ".join("(" + ", ".join(level) + ")" for level in self.parallel)
            lines.append(f"parallel {levels}")
        lines.append(f"expansions {self.expansions}")
        lines.append(f"digest {self.digest}")
        return "\n".join(lines)


def prove(facts: object, goal: object) -> Proof:
    """Compile ``facts`` and search for a proved plan for ``goal``."""
    domain, goal_atoms = _compile(facts, goal)
    return _solve(domain, goal_atoms)


def _compile(facts: object, goal: object) -> tuple[_Domain, tuple[str, ...]]:
    if not isinstance(facts, (list, tuple)):
        raise PlanRejected("facts must be a list")
    if len(facts) > _MAX_FACTS:
        raise PlanRejected("too many facts")
    if not isinstance(goal, str):
        raise PlanRejected("goal must be text")
    _screen(goal)
    positive: list[str] = []
    forbidden: list[str] = []
    mutex: list[tuple[str, str]] = []
    actions: list[_Op] = []
    rules: list[_Op] = []
    budget: int | None = None
    names: set[str] = set()
    for index, fact in enumerate(facts):
        if not isinstance(fact, str):
            raise PlanRejected("fact must be text")
        _screen(fact)
        text = " ".join(fact.strip().split())
        if not text:
            continue
        folded = text.casefold()
        action = _ACTION.fullmatch(folded)
        if action is not None:
            actions.append(_action(action, index, names))
            continue
        rule = _RULE.fullmatch(folded)
        if rule is not None:
            rules.append(_rule(rule, index))
            continue
        never = _NEVER.fullmatch(folded)
        if never is not None:
            left = _atom(never.group("left"))
            right = _atom(never.group("right"))
            if left == right:
                raise PlanRejected("mutex is invalid")
            mutex.append(tuple(sorted((left, right))))
            continue
        money = _BUDGET.fullmatch(folded)
        if money is not None:
            if budget is not None:
                raise PlanRejected("budget is repeated")
            budget = _bound(int(money.group("n")), _MAX_BUDGET, "budget is invalid")
            continue
        if folded.startswith("to ") or folded.startswith("if ") or folded.startswith("never both "):
            raise PlanRejected("note is invalid")
        negated = _NOT.fullmatch(text)
        if negated is not None:
            forbidden.append(_atom(negated.group(1)))
            continue
        positive.append(_atom(text))
    if len(actions) > _MAX_ACTIONS:
        raise PlanRejected("too many actions")
    if len(rules) > _MAX_RULES:
        raise PlanRejected("too many rules")
    goal_atoms = tuple(sorted(_conjunction(goal)))
    if not goal_atoms:
        raise PlanRejected("goal is empty")
    return (
        _Domain(
            primitive=frozenset(positive),
            forbidden=frozenset(forbidden),
            mutex=tuple(mutex),
            actions=tuple(sorted(actions, key=lambda op: op.name)),
            rules=tuple(rules),
            budget=budget,
        ),
        goal_atoms,
    )


def _solve(domain: _Domain, goal: tuple[str, ...]) -> Proof:
    start_closed = _closure(domain.primitive, domain.rules)
    conflict = _conflict(start_closed, domain.forbidden, domain.mutex)
    if conflict is not None:
        return _proof(domain, goal, "contradicted", (), 0, None, (), (), (), conflict, 0)
    for left, right in domain.mutex:
        if left in goal and right in goal:
            return _proof(
                domain, goal, "contradicted", (), 0, None, (), (), (), (left, right), 0
            )
    heuristic = _h_max(domain.primitive, goal, domain)
    if heuristic is None:
        missing = _missing(domain.primitive, goal, domain)
        return _proof(domain, goal, "infeasible", (), 0, None, (), (), missing, None, 0)
    if set(goal) <= start_closed:
        return _proof(domain, goal, "proved", (), 0, 0, (), (), (), None, 0)

    best: dict[frozenset[str], tuple[int, tuple[int, ...]]] = {domain.primitive: (0, ())}
    heap: list[tuple[int, int, tuple[str, ...], tuple[int, ...], frozenset[str]]] = [
        (heuristic, 0, (), (), domain.primitive)
    ]
    expansions = 0
    while heap:
        _estimate, cost, _labels, path, state = heapq.heappop(heap)
        if best.get(state) != (cost, path):
            continue
        expansions += 1
        if expansions > _MAX_EXPAND:
            return _proof(domain, goal, "bounded", (), 0, heuristic, (), (), (), None, expansions)
        if set(goal) <= _closure(state, domain.rules):
            chosen = tuple(domain.actions[index] for index in path)
            return _explained(domain, goal, chosen, heuristic, expansions)
        for index, action in enumerate(domain.actions):
            nxt = _apply(state, action, domain)
            if nxt is None or nxt == state:
                continue
            nxt_cost = cost + action.cost
            if nxt_cost > _MAX_BUDGET:
                continue
            nxt_path = path + (index,)
            previous = best.get(nxt)
            if previous is not None and (previous[0] < nxt_cost or previous[0] == nxt_cost and previous[1] <= nxt_path):
                continue
            estimate = _h_max(nxt, goal, domain)
            if estimate is None:
                continue
            best[nxt] = (nxt_cost, nxt_path)
            labels = tuple(domain.actions[item].name for item in nxt_path)
            heapq.heappush(heap, (nxt_cost + estimate, nxt_cost, labels, nxt_path, nxt))
    return _proof(domain, goal, "infeasible", (), 0, heuristic, (), (), (), None, expansions)


def _explained(
    domain: _Domain,
    goal: tuple[str, ...],
    actions: tuple[_Op, ...],
    heuristic: int,
    expansions: int,
) -> Proof:
    steps, links, goal_links = _simulate(domain, actions, goal)
    critical, parallel = _order(actions, links, goal_links)
    cost = sum(action.cost for action in actions)
    status = "proved"
    if domain.budget is not None and cost > domain.budget:
        status = "infeasible"
    return _proof(
        domain,
        goal,
        status,
        steps,
        cost,
        heuristic,
        critical,
        parallel,
        (),
        None,
        expansions,
    )


def _simulate(
    domain: _Domain, actions: tuple[_Op, ...], goal: tuple[str, ...]
) -> tuple[tuple[Step, ...], tuple[tuple[int, int, str], ...], tuple[tuple[int, str], ...]]:
    primitive = domain.primitive
    producers: dict[str, int | None] = {
        atom: None for atom in _closure(primitive, domain.rules)
    }
    steps: list[Step] = []
    links: list[tuple[int, int, str]] = []
    for index, action in enumerate(actions):
        before = _closure(primitive, domain.rules)
        if not action.need <= before:
            raise PlanRejected("plan failed simulation")
        support = []
        for atom in sorted(action.need):
            producer = producers.get(atom)
            label = "init" if producer is None else actions[producer].name
            support.append((atom, label))
            links.append((-1 if producer is None else producer, index, atom))
        steps.append(Step(action.name, action.cost, tuple(support)))
        primitive = (primitive - action.lose) | action.gain
        after = _closure(primitive, domain.rules)
        if action.lose & after or not action.gain <= after:
            raise PlanRejected("plan failed simulation")
        if _conflict(after, domain.forbidden, domain.mutex) is not None:
            raise PlanRejected("plan failed simulation")
        producers = {
            atom: index if atom not in before else producers.get(atom)
            for atom in after
        }
    closed = _closure(primitive, domain.rules)
    if not set(goal) <= closed:
        raise PlanRejected("plan failed simulation")
    goal_links = tuple(
        (-1 if producers.get(atom) is None else producers[atom], atom) for atom in goal
    )
    return tuple(steps), tuple(links), goal_links


def _order(
    actions: tuple[_Op, ...],
    links: tuple[tuple[int, int, str], ...],
    goal_links: tuple[tuple[int, str], ...],
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    count = len(actions)
    goal_node = count
    edges: set[tuple[int, int]] = set()
    for producer, consumer, _atom in links:
        edges.add((producer, consumer))
    for producer, _atom in goal_links:
        edges.add((producer, goal_node))
    for index, action in enumerate(actions):
        for _producer, consumer, atom in links:
            if index in {_producer, consumer} or atom not in action.lose:
                continue
            if index > consumer:
                edges.add((consumer, index))
            elif _producer != -1 and index < _producer:
                edges.add((index, _producer))
    if _cyclic(count, edges):
        edges = {(-1, 0)} if count else {(-1, goal_node)}
        for index in range(count - 1):
            edges.add((index, index + 1))
        if count:
            edges.add((count - 1, goal_node))
    ranks = _ranks(count, edges)
    levels: dict[int, list[str]] = {}
    for index, action in enumerate(actions):
        levels.setdefault(ranks[index], []).append(action.name)
    parallel = tuple(tuple(sorted(levels[rank])) for rank in sorted(levels))
    critical = _critical(actions, edges, ranks)
    return critical, parallel


def _ranks(count: int, edges: set[tuple[int, int]]) -> dict[int, int]:
    nodes = [-1, *range(count), count]
    preds: dict[int, list[int]] = {node: [] for node in nodes}
    succs: dict[int, list[int]] = {node: [] for node in nodes}
    indeg = {node: 0 for node in nodes}
    for source, target in edges:
        succs[source].append(target)
        preds[target].append(source)
        indeg[target] += 1
    ready = sorted(node for node in nodes if indeg[node] == 0)
    ranks = {node: 0 for node in nodes}
    seen = 0
    while ready:
        node = ready.pop(0)
        seen += 1
        if preds[node]:
            ranks[node] = max(ranks[source] for source in preds[node]) + 1
        for target in sorted(succs[node]):
            indeg[target] -= 1
            if indeg[target] == 0:
                ready.append(target)
                ready.sort()
    if seen != len(nodes):
        return {index: index + 1 for index in range(count)}
    return ranks


def _critical(
    actions: tuple[_Op, ...], edges: set[tuple[int, int]], ranks: dict[int, int]
) -> tuple[str, ...]:
    count = len(actions)
    succs: dict[int, list[int]] = {node: [] for node in (-1, *range(count), count)}
    for source, target in edges:
        succs[source].append(target)
    order = sorted(succs, key=lambda node: (ranks.get(node, 0), node))
    best: dict[int, tuple[int, tuple[str, ...]]] = {node: (0, ()) for node in succs}
    for node in order:
        prefix_cost, prefix = best[node]
        node_cost = actions[node].cost if 0 <= node < count else 0
        walked = prefix + ((actions[node].name,) if 0 <= node < count else ())
        total = prefix_cost + node_cost
        for target in succs[node]:
            other_cost, other_path = best[target]
            if total > other_cost or (total == other_cost and walked < other_path):
                best[target] = (total, walked)
    return best[count][1]


def _cyclic(count: int, edges: set[tuple[int, int]]) -> bool:
    nodes = [-1, *range(count), count]
    succs: dict[int, list[int]] = {node: [] for node in nodes}
    indeg = {node: 0 for node in nodes}
    for source, target in edges:
        succs[source].append(target)
        indeg[target] += 1
    ready = [node for node in nodes if indeg[node] == 0]
    seen = 0
    while ready:
        node = ready.pop()
        seen += 1
        for target in succs[node]:
            indeg[target] -= 1
            if indeg[target] == 0:
                ready.append(target)
    return seen != len(nodes)


def _proof(
    domain: _Domain,
    goal: tuple[str, ...],
    status: str,
    steps: tuple[Step, ...],
    cost: int,
    heuristic: int | None,
    critical: tuple[str, ...],
    parallel: tuple[tuple[str, ...], ...],
    missing: tuple[str, ...],
    conflict: tuple[str, str] | None,
    expansions: int,
) -> Proof:
    body = {
        "budget": domain.budget,
        "conflict": list(conflict) if conflict is not None else [],
        "cost": cost,
        "critical": list(critical),
        "goal": list(goal),
        "heuristic": heuristic,
        "missing": list(missing),
        "parallel": [list(level) for level in parallel],
        "status": status,
        "steps": [
            {
                "cost": step.cost,
                "name": step.name,
                "need": [[atom, producer] for atom, producer in step.support],
            }
            for step in steps
        ],
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(encoded.encode("ascii")).hexdigest()
    return Proof(
        status=status,
        goal=goal,
        steps=steps,
        cost=cost,
        budget=domain.budget,
        heuristic=heuristic,
        critical_path=critical,
        parallel=parallel,
        missing=missing,
        conflict=conflict,
        expansions=expansions,
        digest=digest,
    )


def _apply(state: frozenset[str], action: _Op, domain: _Domain) -> frozenset[str] | None:
    closed = _closure(state, domain.rules)
    if not action.need <= closed:
        return None
    nxt = frozenset((state - action.lose) | action.gain)
    after = _closure(nxt, domain.rules)
    if action.lose & after or not action.gain <= after:
        return None
    if _conflict(after, domain.forbidden, domain.mutex) is not None:
        return None
    return nxt


def _closure(primitive: frozenset[str], rules: tuple[_Op, ...]) -> frozenset[str]:
    have = set(primitive)
    for _ in range(64):
        changed = False
        for rule in rules:
            if rule.need <= have and not rule.gain <= have:
                have.update(rule.gain)
                changed = True
        if len(have) > _MAX_CLOSURE:
            raise PlanRejected("closure did not settle")
        if not changed:
            return frozenset(have)
    raise PlanRejected("closure did not settle")


def _conflict(
    closed: frozenset[str], forbidden: frozenset[str], mutex: tuple[tuple[str, str], ...]
) -> tuple[str, str] | None:
    hit = sorted(closed & forbidden)
    if hit:
        return (hit[0], f"not {hit[0]}")
    for left, right in mutex:
        if left in closed and right in closed:
            return (left, right)
    return None


def _h_max(state: frozenset[str], goal: tuple[str, ...], domain: _Domain) -> int | None:
    dist = {atom: 0 for atom in _closure(state, domain.rules)}
    ops = domain.rules + domain.actions
    for _ in range(max(1, len(ops) * 4)):
        changed = False
        for op in ops:
            if not set(op.need) <= dist.keys():
                continue
            step = op.cost + max((dist[atom] for atom in op.need), default=0)
            for atom in op.gain:
                if step < dist.get(atom, _INF):
                    dist[atom] = step
                    changed = True
        if not changed:
            break
    else:
        raise PlanRejected("heuristic did not settle")
    if not set(goal) <= dist.keys():
        return None
    return max(dist[atom] for atom in goal)


def _missing(state: frozenset[str], goal: tuple[str, ...], domain: _Domain) -> tuple[str, ...]:
    dist = {atom: 0 for atom in _closure(state, domain.rules)}
    ops = domain.rules + domain.actions
    for _ in range(max(1, len(ops) * 4)):
        changed = False
        for op in ops:
            if not set(op.need) <= dist.keys():
                continue
            for atom in op.gain:
                if atom not in dist:
                    dist[atom] = 0
                    changed = True
        if not changed:
            break
    return tuple(sorted(atom for atom in goal if atom not in dist))


def _action(match: re.Match[str], source: int, names: set[str]) -> _Op:
    name = " ".join(match.group("name").split())
    if not name or len(name) > _MAX_NAME or name in names:
        raise PlanRejected("action is invalid")
    names.add(name)
    need = _conjunction(match.group("need"))
    gain = _conjunction(match.group("gain"))
    lose = _conjunction(match.group("lose") or "")
    if not need or not gain or gain & lose:
        raise PlanRejected("action is invalid")
    cost = 1 if match.group("cost") is None else int(match.group("cost"))
    if not 1 <= cost <= _MAX_COST:
        raise PlanRejected("action cost is invalid")
    return _Op(name, need, gain, lose, cost, source, "action")


def _rule(match: re.Match[str], source: int) -> _Op:
    need = _conjunction(match.group("need"))
    gain = _conjunction(match.group("gain"))
    if not need or not gain:
        raise PlanRejected("rule is invalid")
    return _Op("rule", need, gain, frozenset(), 0, source, "rule")


def _conjunction(text: str) -> frozenset[str]:
    parts = [part for part in _CONJ.split(text) if part.strip()]
    return frozenset(_atom(part) for part in parts)


def _atom(text: str) -> str:
    cleaned = " ".join(text.strip().casefold().split())
    if cleaned.startswith("the "):
        cleaned = cleaned[4:]
    if (
        not cleaned
        or len(cleaned) > _MAX_ATOM
        or ";" in cleaned
        or any(ord(char) < 32 for char in cleaned)
    ):
        raise PlanRejected("atom is invalid")
    return cleaned


def _bound(value: int, limit: int, message: str) -> int:
    if value > limit:
        raise PlanRejected(message)
    return value


def _screen(text: str) -> None:
    if _SECRET.search(text):
        raise PlanRejected("payload refused")
