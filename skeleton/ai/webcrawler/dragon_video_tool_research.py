"""Video hatchling: separately reviewed, frame-bookmarked tool/editor leads.

Builds a deterministic index of software/engine/editor observations from real
previously consented visual-bookmark packets. It neither sees new pixels nor
downloads a video. A distinct external reviewer signs every source packet.
A tool appearing on-screen remains an inspirational research lead, not a
claim that the product is legal, installed, compatible or industry-leading.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from skeleton.ai.game_builder.contracts import canonical_digest, canonical_json

HASH = re.compile(r"[0-9a-f]{64}\Z")
SOURCE = re.compile(r"source-[0-9a-f]{64}\Z")
TOPIC = re.compile(r"[a-z0-9][a-z0-9-]{1,39}\Z")
FAMILIES = {
    "editors": ("editor", "tilemap", "pixel", "sprite", "blender", "ui"),
    "engines": ("engine", "godot", "unity", "unreal", "physics"),
    "build_tools": ("compiler", "debugger", "testing", "profiling"),
    "art_pipeline": ("animation", "rigging", "vfx", "shader", "lighting"),
    "audio": ("audio",),
    "accessibility": ("accessibility",),
}
TOOL_GROUP = {
    tool: group for group, tags in FAMILIES.items() for tool in tags
}


@dataclass(frozen=True)
class SignedVisualPacketReview:
    owner: str
    source_id: str
    packet_digest: str
    reviewer: str
    key_id: str
    issued_at: int
    expires_at: int
    decision: str
    signature_hex: str

    def body(self) -> dict:
        return {
            "schema": "skeleton.dragon.external_visual_packet_review.v1",
            "owner": self.owner,
            "source_id": self.source_id,
            "packet_digest": self.packet_digest,
            "reviewer": self.reviewer,
            "key_id": self.key_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "decision": self.decision,
        }


def index_video_tool_research(
    owner: str,
    reviewed_packets: tuple[tuple[dict, SignedVisualPacketReview], ...], *,
    reviewer_public_key: bytes,
    reviewer: str,
    key_id: str,
    now: int,
    task_terms: tuple[str, ...] = (),
    limit: int = 40,
) -> dict:
    if (type(owner) is not str or not 1 <= len(owner) <= 128
        or type(reviewed_packets) is not tuple or len(reviewed_packets) > 64
        or type(reviewer_public_key) is not bytes or len(reviewer_public_key) != 32
        or type(reviewer) is not str or not reviewer
        or type(key_id) is not str or not key_id
        or type(now) is not int or now < 0
        or type(limit) is not int or not 1 <= limit <= 100
        or type(task_terms) is not tuple or len(task_terms) > 8
        or len(set(task_terms)) != len(task_terms)
        or any(type(t) is not str or not TOPIC.fullmatch(t) for t in task_terms)):
        raise ValueError("bounded externally reviewed visual research required")
    verifier = Ed25519PublicKey.from_public_bytes(reviewer_public_key)
    seen_sources = set()
    seen_clips = set()
    leads = {}
    reviewed_sources = 0
    review_rejections = 0
    for packet, review in reviewed_packets:
        if not isinstance(packet, dict) or not isinstance(review, SignedVisualPacketReview):
            raise TypeError("canonical video packet and signed reviewer decision required")
        if (packet.get("schema") != "skeleton.dragon.visual_inspiration_bookmarks.v1"
            or type(packet.get("source_id")) is not str
            or not SOURCE.fullmatch(packet["source_id"])
            or type(packet.get("bookmark_digest")) is not str
            or not HASH.fullmatch(packet["bookmark_digest"])
            or canonical_digest({
                k:v for k,v in packet.items() if k != "bookmark_digest"
            }) != packet["bookmark_digest"]):
            raise ValueError("visual source custody packet corrupted")
        if (review.owner != owner or review.source_id != packet["source_id"]
            or review.packet_digest != packet["bookmark_digest"]
            or review.reviewer != reviewer or review.key_id != key_id):
            raise PermissionError("wrong tenant, source or visual-review identity")
        if (type(review.issued_at) is not int or type(review.expires_at) is not int
            or not 0 <= review.issued_at <= now < review.expires_at
            or review.expires_at - review.issued_at > 30*86400
            or review.decision not in ("research", "reject")):
            raise ValueError("stale or unsupported visual review decision")
        try:
            raw = bytes.fromhex(review.signature_hex)
            if len(raw) != 64:
                raise ValueError("Ed25519 signature length invalid")
            verifier.verify(raw, canonical_json(review.body()).encode())
        except (ValueError, TypeError, InvalidSignature) as exc:
            raise PermissionError("unsigned or forged visual review") from exc
        if packet["source_id"] in seen_sources:
            raise ValueError("repeated video packet cannot create new sources")
        seen_sources.add(packet["source_id"])
        if review.decision == "reject":
            review_rejections += 1
            continue
        reviewed_sources += 1
        if (packet.get("independent_visual_fact_review_required") is not True
            or packet.get("neural_training_authorized") is not False
            or packet.get("normal_weight_promotion_authorized") is not False):
            raise ValueError("unsafe video bookmark promotion status")
        notes = packet.get("notes")
        if type(notes) is not list or len(notes) > 128:
            raise ValueError("bounded reviewed visual bookmark list required")
        for note in notes:
            if not isinstance(note, dict):
                raise ValueError("invalid visual tool observation")
            clip = note.get("clip_digest")
            frame = note.get("frame_digest")
            tags = note.get("inspiring_tool_leads")
            if (type(clip) is not str or not HASH.fullmatch(clip)
                or type(frame) is not str or not HASH.fullmatch(frame)
                or type(tags) not in (tuple, list)
                or len(tags) > 24
                or type(note.get("start_ms")) is not int
                or type(note.get("end_ms")) is not int
                or not 0 <= note["start_ms"] < note["end_ms"]
                or any(type(t) is not str for t in tags)
                or len(set(tags)) != len(tags)):
                raise ValueError("unbound or malformed visual tool bookmark")
            identity = (packet["source_id"], clip)
            if identity in seen_clips:
                raise ValueError("duplicated visual evidence clip")
            seen_clips.add(identity)
            for tag in tags:
                if type(tag) is not str or tag not in TOOL_GROUP:
                    raise ValueError("unrecognized or unreviewed tool category")
                leads.setdefault(tag, []).append({
                    "source_id": packet["source_id"],
                    "video_packet_digest": packet["bookmark_digest"],
                    "clip_digest": clip,
                    "frame_digest": frame,
                    "start_ms": note["start_ms"],
                    "end_ms": note["end_ms"],
                    "source_url": packet["source_url"],
                })
    tasks = set(task_terms)
    entries = []
    for tag, matches in leads.items():
        matches.sort(key=lambda x: (
            x["source_id"], x["start_ms"], x["clip_digest"]))
        sources = len({m["source_id"] for m in matches})
        score = len(matches) + 4 * sources + (10 if tag in tasks else 0)
        entries.append({
            "tool_topic": tag, "tool_family": TOOL_GROUP[tag],
            "lexical_priority_signal": score,
            "task_topic_match": tag in tasks,
            "evidence_bookmark_count": len(matches),
            "observed_video_sources": sources,
            "bookmarks": matches[:40],
            "bookmarks_truncated": len(matches) > 40,
            "independent_product_fitness_unverified": True,
            "copyright_and_distribution_review_required": True,
            "next_step": "Investigate license, version, workflow, editor features and game-platform fit",
            "approved_software_recommendation": False,
            "weight_promotion_authorized": False,
        })
    entries.sort(key=lambda x: (
        -x["lexical_priority_signal"], x["tool_family"], x["tool_topic"]))
    core = {
        "schema": "skeleton.dragon.video_tool_research_index.v1",
        "owner": owner, "checked_at": now,
        "task_terms": list(task_terms),
        "reviewed_video_sources": reviewed_sources,
        "review_rejections": review_rejections,
        "distinct_tool_topics": len(entries),
        "entries": entries[:limit],
        "truncated": len(entries) > limit,
        "network_requests": 0,
        "bookmarks_are_unverified_inspiration": True,
        "approved_software_recommendation": False,
        "weight_promotion_authorized": False,
        "hyperweight_promotion_authorized": False,
        "neural_training_authorized": False,
    }
    return {**core, "index_digest": canonical_digest(core)}
