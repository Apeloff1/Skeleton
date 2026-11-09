"""Persistent civic institutions with accountable votes and material policy effects.

An original-world settlement may form one assembly, propose a policy, hear
physically present named citizens, record deterministic personal ballots, and
implement exactly one bounded mandate. Food or medical aid physically debits
warehouse goods and helps particular citizens. Conservation and exploration
govern later autonomous goals without fabricating any action outcomes.

No fictitious public consensus from an invisible population. No elections
automatically certify a country-scale democracy, legal authority or human AI.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError
from .original_world_product_agents import Person, PhysicalSociety, validate_society
from .original_world_product_terrain import TerrainState, validate_terrain

SCHEMA = "original-npc-civic-institutions.v1"
MANDATES = ("food-aid", "medical-aid", "conservation", "expedition")
MAX_ASSEMBLIES = 16
MAX_BALLOTS = 32
MAX_POLICY_CYCLES = 1000
VALID_STATUSES = ("pending", "enacted", "rejected", "expired")


@dataclass(frozen=True)
class Ballot:
    voter: int
    supports: bool
    actual_position: tuple[int, int]
    hunger: int
    health: int
    rationale: str


@dataclass(frozen=True)
class Assembly:
    number: int
    mandate: str
    proposer: int
    proposed_day: int
    finalized_day: int = -1
    status: str = "pending"
    ballots: tuple[Ballot, ...] = ()
    participating: tuple[int, ...] = ()


@dataclass(frozen=True)
class PublicService:
    day: int
    mandate: str
    resident: int
    stock_kind: str
    spent: int
    prior_value: int
    resulting_value: int


@dataclass(frozen=True)
class CivicInstitutions:
    constitution: str = SCHEMA
    proposals: tuple[Assembly, ...] = ()
    active_mandate: str = ""
    mandate_expires: int = 0
    next_assembly: int = 0
    services: tuple[PublicService, ...] = ()
    receipts: int = 0
    receipt_head: str = "0" * 64


def _hash(v: object) -> str:
    return sha256(json.dumps(v, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def validate_civics(
    civic: CivicInstitutions, society: PhysicalSociety, terrain: TerrainState,
    current_day: int,
) -> None:
    validate_society(society, terrain)
    if not isinstance(civic, CivicInstitutions) or civic.constitution != SCHEMA:
        raise FoundationError("unsupported resident civic constitution")
    if type(current_day) is not int or not 0 <= current_day <= MAX_POLICY_CYCLES:
        raise FoundationError("invalid public calendar")
    if civic.active_mandate and civic.active_mandate not in MANDATES:
        raise FoundationError("unrecognized enacted resident policy")
    for key in ("next_assembly", "mandate_expires", "receipts"):
        v = getattr(civic, key)
        if type(v) is not int or not 0 <= v <= MAX_POLICY_CYCLES:
            raise FoundationError("invalid resident assembly bookkeeping")
    if (not isinstance(civic.proposals, tuple)
            or len(civic.proposals) > MAX_ASSEMBLIES):
        raise FoundationError("unbounded public assembly docket")
    if (not isinstance(civic.services, tuple)
            or len(civic.services) > 256):
        raise FoundationError("unbounded civic service evidence")
    seen, pending = set(), 0
    for p in civic.proposals:
        if (not isinstance(p, Assembly) or p.mandate not in MANDATES
                or p.status not in VALID_STATUSES or p.number in seen):
            raise FoundationError("duplicate or corrupt civic proposal")
        seen.add(p.number)
        if (type(p.number) is not int or not 0 <= p.number < civic.next_assembly
                or type(p.proposer) is not int
                or not 0 <= p.proposer < len(society.inhabitants)
                or type(p.proposed_day) is not int
                or not 0 <= p.proposed_day <= current_day):
            raise FoundationError("unbound or future civic proposal")
        if p.status == "pending":
            pending += 1
            if p.finalized_day != -1 or p.ballots:
                raise FoundationError("unsettled assembly forged its final vote")
        elif (type(p.finalized_day) is not int
              or not p.proposed_day <= p.finalized_day <= current_day):
            raise FoundationError("vote reported future or nonexistent meeting")
        if len(p.ballots) > MAX_BALLOTS:
            raise FoundationError("illegal civic voter count")
        voter_ids = []
        for b in p.ballots:
            if (not isinstance(b, Ballot) or type(b.voter) is not int
                    or not 0 <= b.voter < len(society.inhabitants)
                    or type(b.supports) is not bool):
                raise FoundationError("invented public voter")
            if len(b.actual_position) != 2 or any(type(v) is not int for v in b.actual_position):
                raise FoundationError("imaginary resident vote location")
            if not isinstance(b.rationale, str) or not b.rationale:
                raise FoundationError("unexplained vote count")
            for v in (b.hunger, b.health):
                if type(v) is not int or not 0 <= v <= 20:
                    raise FoundationError("fabricated resident need at poll")
            voter_ids.append(b.voter)
        if voter_ids != sorted(set(voter_ids)):
            raise FoundationError("one resident voted twice")
        if p.participating != tuple(voter_ids):
            raise FoundationError("participation roll and ballots disagree")
    if pending > 1:
        raise FoundationError("two simultaneous overlapping civic deliberations")
    for receipt in civic.services:
        if (not isinstance(receipt, PublicService)
                or receipt.mandate not in ("food-aid", "medical-aid")
                or receipt.stock_kind not in ("food", "water")
                or type(receipt.resident) is not int
                or not 0 <= receipt.resident < len(society.inhabitants)
                or type(receipt.day) is not int
                or not 0 <= receipt.day <= current_day
                or receipt.spent != 1
                or any(type(x) is not int or not 0 <= x <= 20
                       for x in (receipt.prior_value, receipt.resulting_value))):
            raise FoundationError("fabricated public assistance receipt")
        if (receipt.mandate == "food-aid" and
            not receipt.resulting_value < receipt.prior_value):
            raise FoundationError("food relief did not decrease actual hunger")
        if (receipt.mandate == "medical-aid" and
            not receipt.resulting_value > receipt.prior_value):
            raise FoundationError("medical aid did not restore actual health")
    if (not isinstance(civic.receipt_head, str)
            or len(civic.receipt_head) != 64
            or any(c not in "0123456789abcdef" for c in civic.receipt_head)):
        raise FoundationError("invalid public institution receipt chain")


def _commit(before: CivicInstitutions, result: CivicInstitutions, action: str) -> CivicInstitutions:
    event = _hash({
        "schema": SCHEMA, "prior": before.receipt_head,
        "action": action, "before": asdict(before),
        "after": asdict(result),
    })
    return replace(result, receipts=before.receipts + 1, receipt_head=event)


def propose_civic(
    civic: CivicInstitutions, people: PhysicalSociety, world: TerrainState,
    *, policy: str, citizen: int, day: int,
) -> CivicInstitutions:
    validate_civics(civic, people, world, day)
    if policy not in MANDATES:
        raise FoundationError("unsupported collective charter")
    if type(citizen) is not int or not 0 <= citizen < len(people.inhabitants):
        raise FoundationError("civic proposal requires a physical resident sponsor")
    sponsor = people.inhabitants[citizen]
    if sponsor.health == 0 or abs(sponsor.x) + abs(sponsor.y) > 1:
        raise FoundationError("absent or incapacitated citizen cannot convene public assembly")
    if any(x.status == "pending" for x in civic.proposals):
        raise FoundationError("an existing deliberation must finish before another")
    if len(civic.proposals) >= MAX_ASSEMBLIES or civic.next_assembly >= MAX_ASSEMBLIES:
        raise FoundationError("bounded historic assembly docket exhausted")
    proposal = Assembly(civic.next_assembly, policy, citizen, day)
    result = _commit(
        civic, replace(
            civic, proposals=civic.proposals + (proposal,),
            next_assembly=civic.next_assembly + 1,
        ), "proposal-" + policy)
    validate_civics(result, people, world, day)
    return result


def _support(policy: str, voter: Person, temperament: object) -> tuple[bool, str]:
    empathy = getattr(temperament, "empathy", 5)
    curiosity = getattr(temperament, "curiosity", 5)
    prudence = getattr(temperament, "prudence", 5)
    if policy == "food-aid":
        support = voter.hunger >= 4 or empathy >= 5
        return support, "experienced hunger or prioritizes actual neighborhood meals"
    if policy == "medical-aid":
        support = voter.health <= 15 or empathy >= 6
        return support, "personal health need or willingness to fund actual patient care"
    if policy == "conservation":
        support = prudence >= 5 or voter.hunger > 6
        return support, "prefers preserving finite community stocks"
    support = curiosity >= 6 and voter.hunger < 7 and voter.health > 4
    return support, "exploration permitted only after acceptable survival needs"


def settle_civic(
    civic: CivicInstitutions, people: PhysicalSociety,
    terrain: TerrainState, minds: tuple[object, ...], day: int,
) -> tuple[TerrainState, PhysicalSociety, CivicInstitutions, tuple[str, ...]]:
    """One assembly/turn; service recipients MUST physically be at depot.

    Called after embodied citizen stepping. Votes reflect actual resident
    positions, current hunger/health and personality traits. Once enacted,
    an aid law pays finite local public stock and changes the specific
    recipient body. No remote phantom citizens or resource generation.
    """
    validate_civics(civic, people, terrain, day)
    if len(minds) != len(people.inhabitants):
        raise FoundationError("invalid represented local civic population")
    initial = civic
    messages: list[str] = []
    proposals = list(civic.proposals)
    active, expiry = civic.active_mandate, civic.mandate_expires
    for n, proposition in enumerate(proposals):
        if proposition.status != "pending":
            continue
        attendants = [
            p for p in people.inhabitants
            if p.health > 0 and abs(p.x) + abs(p.y) <= 1
        ]
        vote_roll = []
        for p in sorted(attendants, key=lambda p: p.id):
            yes, rationale = _support(proposition.mandate, p, minds[p.id])
            vote_roll.append(Ballot(
                p.id, yes, (p.x, p.y), p.hunger, p.health, rationale))
        quorum = max(1, min(len(people.inhabitants),
                            (len(people.inhabitants) + 2) // 3))
        approved = (
            len(vote_roll) >= quorum
            and sum(b.supports for b in vote_roll) > len(vote_roll) // 2
        )
        proposals[n] = replace(
            proposition,
            status="enacted" if approved else "rejected",
            finalized_day=day,
            ballots=tuple(vote_roll),
            participating=tuple(b.voter for b in vote_roll),
        )
        if approved:
            active, expiry = proposition.mandate, min(MAX_POLICY_CYCLES, day + 12)
        messages.append(
            "Public mandate " + proposition.mandate
            + (" enacted" if approved else " rejected")
            + f" with {sum(b.supports for b in vote_roll)} support from "
            + f"{len(vote_roll)} physically present voters"
        )
        break
    if active and day >= expiry:
        messages.append(f"Mandate {active} expired without an invented renewal")
        active, expiry = "", 0
    civil_people = list(people.inhabitants)
    village = terrain
    services = list(civic.services)
    if active in ("food-aid", "medical-aid"):
        requests = []
        for p in people.inhabitants:
            if p.health <= 0 or abs(p.x) + abs(p.y) > 1:
                continue
            if active == "food-aid" and p.hunger >= 5:
                requests.append((-(p.hunger), p.id))
            elif active == "medical-aid" and p.health <= 16:
                requests.append((p.health, p.id))
        requests.sort()
        # An actual bounded daily public service budget. One citizen per
        # tick receives at most one stocked provision or clean water unit.
        for _, recipient in requests[:1]:
            person = civil_people[recipient]
            if active == "food-aid":
                if village.provisions < 1:
                    messages.append("Public food mandate could not serve: no warehouse food")
                    break
                village = replace(village, provisions=village.provisions - 1)
                changed = replace(person, hunger=max(0, person.hunger - 5))
                kind, old, new = "food", person.hunger, changed.hunger
            else:
                if village.freshwater < 1:
                    messages.append("Public medical mandate could not serve: no water")
                    break
                village = replace(village, freshwater=village.freshwater - 1)
                changed = replace(person, health=min(20, person.health + 2))
                kind, old, new = "water", person.health, changed.health
            civil_people[recipient] = changed
            services.append(PublicService(day, active, recipient, kind, 1, old, new))
            messages.append(
                f"Public service spent one {kind} on real resident {recipient}")
    # Historical service log is capped independently of all other memory.
    # The newest 256 decisions remain available and older aggregated totals
    # are not interpreted as freshly verified ongoing services.
    result = _commit(initial, replace(
        civic, proposals=tuple(proposals), active_mandate=active,
        mandate_expires=expiry, services=tuple(services[-256:]),
    ), "civic-clock-" + str(day))
    residents = replace(people, inhabitants=tuple(civil_people))
    validate_civics(result, residents, village, day)
    return village, residents, result, tuple(messages)


def civic_save(civic: CivicInstitutions) -> dict:
    data = asdict(civic)
    return {"schema": SCHEMA, "payload": data, "checksum": _hash(data)}


def civic_restore(
    data: dict, people: PhysicalSociety, terrain: TerrainState, day: int,
) -> CivicInstitutions:
    try:
        if not isinstance(data, dict) or set(data) != {
            "schema", "payload", "checksum"
        } or data["schema"] != SCHEMA or data["checksum"] != _hash(data["payload"]):
            raise FoundationError("invalid civic institutions archive")
        raw = data["payload"]
        if set(raw) != set(CivicInstitutions.__dataclass_fields__):
            raise FoundationError("unrecognized civic archive fields")
        proposals = tuple(Assembly(
            **{**p, "ballots": tuple(Ballot(
                **{**b, "actual_position": tuple(b["actual_position"])}
            ) for b in p["ballots"]),
               "participating": tuple(p["participating"])}
        ) for p in raw["proposals"])
        services = tuple(PublicService(**r) for r in raw["services"])
        result = CivicInstitutions(**{
            **raw, "proposals": proposals, "services": services,
        })
        validate_civics(result, people, terrain, day)
        return result
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise FoundationError("civic save rejected") from exc


def civic_report(civic: CivicInstitutions) -> dict:
    return {
        "schema": SCHEMA,
        "active_mandate": civic.active_mandate,
        "expires": civic.mandate_expires,
        "assemblies": [asdict(p) for p in civic.proposals],
        "funded_services": [asdict(x) for x in civic.services],
        "services_delivered": len(civic.services),
        "has_real_voter_receipts": any(bool(p.ballots) for p in civic.proposals),
    }
