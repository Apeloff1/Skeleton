"""Source-bound multi-episode rescue campaign with deterministic CAS custody.

Each accepted chapter must be won with its declared ending. Journals are replayed
against the original chapter source on every transition, not trusted from clients.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

from .authoring import validate_reachability
from .custody import canonical, digest
from .engine import available_actions
from .journal import append_journal, open_journal, verify_journal
from .schema import parse_world, world_dict

SCHEMA = "ridge.rescue.campaign.v1"
SESSION_SCHEMA = "ridge.rescue.campaign.session.v1"
EXPORT_SCHEMA = "ridge.rescue.campaign.export.v1"
MAX_EPISODES = 8
MAX_CAMPAIGN_BYTES = 96_000
MAX_SESSION_BYTES = 1_000_000
MAX_RETRIES = 3
IDENT = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")


class CampaignError(ValueError):
    """Invalid campaign, tampered custody or unavailable state transition."""


def _decode(value: Any, limit: int) -> dict:
    if isinstance(value, bytes):
        if len(value) > limit:
            raise CampaignError("document byte budget exceeded")
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CampaignError("document is not UTF-8") from exc
    if isinstance(value, str):
        if len(value.encode("utf-8")) > limit:
            raise CampaignError("document byte budget exceeded")
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise CampaignError("invalid JSON") from exc
    if not isinstance(value, dict):
        raise CampaignError("expected JSON object")
    if len(canonical(value)) > limit:
        raise CampaignError("document byte budget exceeded")
    return value


def parse_campaign(source: dict | str | bytes) -> dict:
    data = _decode(source, MAX_CAMPAIGN_BYTES)
    if set(data) != {"schema", "id", "title", "episodes"} or data["schema"] != SCHEMA:
        raise CampaignError("unsupported campaign contract")
    if not isinstance(data["id"], str) or not IDENT.fullmatch(data["id"]):
        raise CampaignError("invalid campaign id")
    if not isinstance(data["title"], str) or not 1 <= len(data["title"]) <= 96 or any(ord(c) < 32 for c in data["title"]):
        raise CampaignError("invalid campaign title")
    episodes = data["episodes"]
    if not isinstance(episodes, list) or not 1 <= len(episodes) <= MAX_EPISODES:
        raise CampaignError("invalid episode count")
    result = []
    seen = set()
    for episode in episodes:
        if not isinstance(episode, dict) or set(episode) != {"id", "title", "ending", "world"}:
            raise CampaignError("invalid episode fields")
        ident = episode["id"]
        if not isinstance(ident, str) or not IDENT.fullmatch(ident) or ident in seen:
            raise CampaignError("invalid or duplicate episode id")
        seen.add(ident)
        title = episode["title"]
        if not isinstance(title, str) or not 1 <= len(title) <= 96 or any(ord(c) < 32 for c in title):
            raise CampaignError("invalid episode title")
        if episode["ending"] not in ("protect", "salvage"):
            raise CampaignError("unsupported earned ending")
        try:
            world = parse_world(episode["world"])
            validate_reachability(world)
        except (ValueError, TypeError, KeyError) as exc:
            raise CampaignError("invalid or unreachable episode world") from exc
        result.append({"id": ident, "title": title, "ending": episode["ending"], "world": world_dict(world)})
    canonical_source = {"schema": SCHEMA, "id": data["id"], "title": data["title"], "episodes": result}
    if len(canonical(canonical_source)) > MAX_CAMPAIGN_BYTES:
        raise CampaignError("campaign byte budget exceeded")
    return canonical_source


def _head(session: dict) -> str:
    return digest({key: value for key, value in session.items() if key != "head"})


def _bounded(session: dict) -> dict:
    if len(canonical(session)) > MAX_SESSION_BYTES:
        raise CampaignError("session byte budget exceeded")
    return session


def open_campaign(source: dict | str | bytes) -> dict:
    campaign = parse_campaign(source)
    first = parse_world(campaign["episodes"][0]["world"])
    session = {
        "schema": SESSION_SCHEMA,
        "campaign": campaign,
        "source_sha256": digest(campaign),
        "index": 0,
        "completed": [],
        "active": open_journal(first),
        "retries": [0] * len(campaign["episodes"]),
    }
    session["head"] = _head(session)
    return _bounded(session)


def verify_campaign(value: dict | str | bytes) -> dict:
    session = _decode(value, MAX_SESSION_BYTES)
    if set(session) != {"schema", "campaign", "source_sha256", "index", "completed", "active", "retries", "head"}:
        raise CampaignError("invalid session fields")
    if session["schema"] != SESSION_SCHEMA:
        raise CampaignError("unsupported session schema")
    campaign = parse_campaign(session["campaign"])
    if canonical(campaign) != canonical(session["campaign"]) or session["source_sha256"] != digest(campaign):
        raise CampaignError("campaign source changed")
    episodes = campaign["episodes"]
    index = session["index"]
    if type(index) is not int or not 0 <= index <= len(episodes):
        raise CampaignError("invalid chapter index")
    if not isinstance(session["completed"], list) or len(session["completed"]) != index:
        raise CampaignError("completed chapters are not contiguous")
    retries = session["retries"]
    if not isinstance(retries, list) or len(retries) != len(episodes) or any(type(n) is not int or not 0 <= n <= MAX_RETRIES for n in retries):
        raise CampaignError("invalid retry ledger")
    if not isinstance(session["head"], str) or session["head"] != _head(session):
        raise CampaignError("session CAS head mismatch")
    try:
        for number, journal in enumerate(session["completed"]):
            verified = verify_journal(journal)
            if canonical(world_dict(verified["world"])) != canonical(episodes[number]["world"]):
                raise CampaignError("completed episode source mismatch")
            if verified["state"]["status"] != "won:" + episodes[number]["ending"]:
                raise CampaignError("unearned chapter completion")
        if index == len(episodes):
            if session["active"] is not None:
                raise CampaignError("completed campaign has active chapter")
            status = "completed"
            state = None
            actions = []
        else:
            if not isinstance(session["active"], dict):
                raise CampaignError("missing active chapter")
            active = verify_journal(session["active"])
            if canonical(world_dict(active["world"])) != canonical(episodes[index]["world"]):
                raise CampaignError("active episode source mismatch")
            status = active["state"]["status"]
            state = active["state"]
            actions = available_actions(active["world"], state)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise CampaignError("campaign replay rejected") from exc
    return {"session": deepcopy(session), "campaign": campaign, "index": index,
            "status": status, "state": state, "actions": actions, "head": session["head"]}


def step_campaign(value: dict, action: dict, *, expected_head: str) -> dict:
    verified = verify_campaign(value)
    if expected_head != verified["head"]:
        raise CampaignError("stale campaign revision")
    if verified["index"] >= len(verified["campaign"]["episodes"]):
        raise CampaignError("campaign already completed")
    if verified["status"] != "playing":
        raise CampaignError("chapter ended; retry if ending was not earned")
    result = verified["session"]
    active = result["active"]
    try:
        next_journal = append_journal(active, action, expected_head=active["head"])
    except (ValueError, TypeError, KeyError) as exc:
        raise CampaignError("unavailable chapter action") from exc
    result["active"] = next_journal
    index = result["index"]
    required = result["campaign"]["episodes"][index]["ending"]
    if next_journal["state"]["status"] == "won:" + required:
        result["completed"].append(next_journal)
        result["index"] += 1
        if result["index"] == len(result["campaign"]["episodes"]):
            result["active"] = None
        else:
            next_world = parse_world(result["campaign"]["episodes"][result["index"]]["world"])
            result["active"] = open_journal(next_world)
    result["head"] = _head(result)
    return _bounded(result)


def retry_campaign(value: dict, *, expected_head: str) -> dict:
    verified = verify_campaign(value)
    if expected_head != verified["head"]:
        raise CampaignError("stale campaign revision")
    index = verified["index"]
    if index == len(verified["campaign"]["episodes"]) or verified["status"] == "playing":
        raise CampaignError("no failed or mismatched chapter to retry")
    result = verified["session"]
    if result["retries"][index] >= MAX_RETRIES:
        raise CampaignError("retry budget exhausted")
    result["retries"][index] += 1
    result["active"] = open_journal(parse_world(result["campaign"]["episodes"][index]["world"]))
    result["head"] = _head(result)
    return _bounded(result)


def export_campaign(value: dict) -> dict:
    verified = verify_campaign(value)
    payload = {"schema": EXPORT_SCHEMA, "session": verified["session"]}
    return {"payload": payload, "sha256": digest(payload)}


def verify_export(value: dict | bytes | str) -> dict:
    document = _decode(value, MAX_SESSION_BYTES)
    if set(document) != {"payload", "sha256"} or not isinstance(document["payload"], dict):
        raise CampaignError("invalid export envelope")
    payload = document["payload"]
    if set(payload) != {"schema", "session"} or payload["schema"] != EXPORT_SCHEMA:
        raise CampaignError("unsupported export schema")
    if document["sha256"] != digest(payload):
        raise CampaignError("export digest mismatch")
    return verify_campaign(payload["session"])
