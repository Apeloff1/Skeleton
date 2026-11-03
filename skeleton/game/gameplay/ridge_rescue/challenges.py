"""Original hand-authored playable rescue challenge collection.

Each scenario is independent source content with a unique terrain puzzle,
survivor and canonical action trace. Loading a scenario replays its actions
through the game engine before making it available to players.
"""
from __future__ import annotations

from pathlib import Path
import re

from .custody import canonical, digest, export_run, verify_run
from .io import read_bounded
from .routebook import _document
from .schema import parse_world, world_dict

SCHEMA = "ridge.rescue.challenge.v1"
CATALOG_SCHEMA = "ridge.rescue.challenge.catalog.v1"
ID = re.compile(r"[a-z][a-z0-9-]{1,47}\Z")
HERE = Path(__file__).resolve().parent
MAX_CHALLENGES = 32


class ChallengeError(ValueError):
    pass


def parse_challenge(source: dict | str | bytes) -> dict:
    data = _document(source, 96_000)
    if set(data) != {"schema", "id", "title", "ending", "world", "actions"} or data["schema"] != SCHEMA:
        raise ChallengeError("invalid challenge source")
    if not isinstance(data["id"], str) or not ID.fullmatch(data["id"]):
        raise ChallengeError("invalid challenge id")
    if not isinstance(data["title"], str) or not 1 <= len(data["title"]) <= 96 or any(ord(c) < 32 for c in data["title"]):
        raise ChallengeError("invalid challenge title")
    if data["ending"] not in ("protect", "salvage"):
        raise ChallengeError("invalid challenge ending")
    try:
        world = parse_world(data["world"])
        bundle = export_run(world, data["actions"])
        verified = verify_run(bundle)
    except (ValueError, TypeError, KeyError) as exc:
        raise ChallengeError("challenge actions are not playable") from exc
    if verified["state"]["status"] != "won:" + data["ending"]:
        raise ChallengeError("challenge does not earn declared ending")
    if any(status != "rescued" for status in verified["state"]["civilians"].values()):
        raise ChallengeError("challenge left survivors behind")
    result = {"schema": SCHEMA, "id": data["id"], "title": data["title"],
              "ending": data["ending"], "world": world_dict(world),
              "actions": verified["actions"]}
    if len(canonical(result)) > 96_000:
        raise ChallengeError("challenge source too large")
    return result


def load_catalog() -> dict:
    data = _document(read_bounded(HERE / "cinder_ridge_challenges.json", 16_384), 16_384)
    if set(data) != {"schema", "title", "ids"} or data["schema"] != CATALOG_SCHEMA:
        raise ChallengeError("invalid challenge catalog")
    if not isinstance(data["title"], str) or not 1 <= len(data["title"]) <= 96:
        raise ChallengeError("invalid catalog title")
    ids = data["ids"]
    if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_CHALLENGES:
        raise ChallengeError("invalid challenge count")
    if any(not isinstance(ident, str) or not ID.fullmatch(ident) for ident in ids) or len(set(ids)) != len(ids):
        raise ChallengeError("duplicate or unsafe challenge id")
    return {"schema": CATALOG_SCHEMA, "title": data["title"], "ids": list(ids)}


def load_challenge(ident: str) -> dict:
    catalog = load_catalog()
    if not isinstance(ident, str) or ident not in catalog["ids"]:
        raise ChallengeError("unknown challenge")
    source = read_bounded(HERE / "challenges" / (ident + ".json"), 96_000)
    challenge = parse_challenge(source)
    if challenge["id"] != ident:
        raise ChallengeError("challenge file identity mismatch")
    return challenge


def list_challenges() -> dict:
    catalog = load_catalog()
    entries = []
    for ident in catalog["ids"]:
        challenge = load_challenge(ident)
        entries.append({"id": ident, "title": challenge["title"], "ending": challenge["ending"],
                        "source_sha256": digest(challenge), "turns": len(challenge["actions"])})
    return {"schema": "ridge.rescue.challenge.list.v1", "title": catalog["title"],
            "challenges": entries, "count": len(entries)}


def play_challenge(ident: str) -> dict:
    challenge = load_challenge(ident)
    world = parse_world(challenge["world"])
    bundle = export_run(world, challenge["actions"])
    if verify_run(bundle)["state"]["status"] != "won:" + challenge["ending"]:
        raise ChallengeError("challenge replay diverged")
    return bundle
