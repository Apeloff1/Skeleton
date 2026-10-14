"""Integrated persistent play session joining original world and NPC simulation."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_world_campaign import (
    CampaignAction, CampaignError, create_campaign, export_save,
    import_save, step, validate_state,
)
from .original_world_society import (
    SCHEMA as SOCIETY_SCHEMA, Resident, Village, SocietyAction, SocietyState,
    LivingSession, create_society, society_action, society_tick,
    validate_society,
)

SESSION_SCHEMA = "original-living-session.v1"
MAX_SESSION_EVENTS = 1024


@dataclass(frozen=True)
class LivingReceipt:
    kind: str
    event_number: int
    event_hash: str
    campaign_receipt: str
    society_receipt: str
    messages: tuple[str, ...]


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def create_living_session(world_id: str, seed: str = "living-world") -> LivingSession:
    campaign = create_campaign(world_id, seed)
    session = LivingSession(campaign, create_society(campaign))
    validate_living_session(session)
    return session


def validate_living_session(session: LivingSession) -> None:
    if not isinstance(session, LivingSession):
        raise CampaignError("invalid living session type")
    validate_state(session.campaign)
    validate_society(session.society, session.campaign)
    if type(session.event_count) is not int or not 0 <= session.event_count <= MAX_SESSION_EVENTS:
        raise CampaignError("invalid session event counter")
    if (not isinstance(session.event_head, str) or len(session.event_head) != 64
            or any(c not in "0123456789abcdef" for c in session.event_head)):
        raise CampaignError("invalid session event chain")


def _record(previous: LivingSession, campaign, society,
            kind: str, campaign_receipt: str, society_receipt: str,
            messages: tuple[str, ...]) -> tuple[LivingSession, LivingReceipt]:
    if previous.event_count >= MAX_SESSION_EVENTS:
        raise CampaignError("living session event budget exhausted")
    next_data = {"campaign": asdict(campaign), "society": asdict(society)}
    evidence = _digest({
        "schema": SESSION_SCHEMA, "prior_head": previous.event_head,
        "before": _digest(asdict(previous)), "new_state": next_data,
        "kind": kind, "campaign_receipt": campaign_receipt,
        "society_receipt": society_receipt, "messages": messages,
    })
    session = LivingSession(
        campaign, society, previous.event_count + 1, evidence,
    )
    validate_living_session(session)
    return session, LivingReceipt(
        kind, session.event_count, evidence,
        campaign_receipt, society_receipt, messages,
    )


def living_step(
    session: LivingSession, action: CampaignAction | SocietyAction
) -> tuple[LivingSession, LivingReceipt]:
    """Transactional application of gameplay actions and individual NPC interactions."""
    validate_living_session(session)
    old_campaign, old_society = session.campaign, session.society
    if isinstance(action, CampaignAction):
        world, receipt = step(old_campaign, action)
        society = old_society
        society_receipt = ""
        messages = receipt.messages
        if action.verb == "move":
            # Existing escorts follow only an actually traversed adjacent
            # route. We do not teleport other residents or world populations.
            residents = tuple(replace(resident, location=world.position)
                              if resident.following else resident
                              for resident in society.residents)
            society = replace(society, residents=residents)
            messages += ("Consenting expedition companions followed",) if any(
                resident.following for resident in society.residents) else ()
        if action.verb == "end_turn":
            world, society, social = society_tick(world, society)
            society_receipt = social.event_id
            messages += social.consequences
        return _record(session, world, society,
                       "campaign-action:" + action.verb,
                       receipt.event_id, society_receipt, messages)
    if isinstance(action, SocietyAction):
        world, society, receipt = society_action(old_campaign, old_society, action)
        return _record(session, world, society,
                       "society-action:" + action.verb, "",
                       receipt.event_id, receipt.consequences)
    raise CampaignError("unknown integrated session operation")


def replay_living(world_id: str, seed: str,
                  actions: tuple[CampaignAction | SocietyAction, ...]
                  ) -> tuple[LivingSession, tuple[LivingReceipt, ...]]:
    if not isinstance(actions, tuple) or len(actions) > MAX_SESSION_EVENTS:
        raise CampaignError("integrated replay must be a bounded tuple")
    session = create_living_session(world_id, seed)
    receipts = []
    for action in actions:
        session, receipt = living_step(session, action)
        receipts.append(receipt)
    return session, tuple(receipts)


def living_save(session: LivingSession) -> str:
    validate_living_session(session)
    payload = {
        "schema": SESSION_SCHEMA,
        "campaign": json.loads(export_save(session.campaign)),
        "society": asdict(session.society),
        "event_count": session.event_count,
        "event_head": session.event_head,
    }
    return json.dumps({"payload": payload, "checksum": _digest(payload)},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def living_restore(serialized: str) -> LivingSession:
    if not isinstance(serialized, str) or len(serialized.encode("utf-8")) > 524288:
        raise CampaignError("invalid or oversized living session")
    try:
        wrapped = json.loads(serialized)
        if set(wrapped) != {"payload", "checksum"}:
            raise CampaignError("invalid living save envelope")
        payload = wrapped["payload"]
        if payload["schema"] != SESSION_SCHEMA or _digest(payload) != wrapped["checksum"]:
            raise CampaignError("living session checksum mismatch")
        if set(payload) != {
            "schema", "campaign", "society", "event_count", "event_head",
        }:
            raise CampaignError("unknown living save fields")
        campaign = import_save(json.dumps(payload["campaign"]))
        raw = payload["society"]
        if set(raw) != set(SocietyState.__dataclass_fields__):
            raise CampaignError("unknown society fields")
        raw["residents"] = tuple(Resident(**entry) for entry in raw["residents"])
        raw["villages"] = tuple(Village(**entry) for entry in raw["villages"])
        society = SocietyState(**raw)
        result = LivingSession(
            campaign, society, payload["event_count"], payload["event_head"],
        )
        validate_living_session(result)
        return result
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CampaignError("living save validation failed") from exc
