"""Adapters from source-domain NPC records into the frontier NPC contract."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from skeleton.frontier.npc import NPCSpec


def _strings(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip().lower()
        return (text,) if text else ()
    if not isinstance(value, Sequence) or isinstance(value, bytes):
        raise TypeError(f"{field_name} must be a string or sequence")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip().lower()
        if text and text not in seen:
            seen.add(text)
            normalized.append(text)
    return tuple(normalized)


def _stats(value: Any) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("domain NPC stats must be a mapping")

    normalized: dict[str, int] = {}
    for key, raw_value in value.items():
        stat_name = str(key).strip()
        if not stat_name:
            raise ValueError("domain NPC stat names must not be empty")
        try:
            normalized[stat_name] = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"domain NPC stat {stat_name!r} must be an integer") from exc
    return normalized


def npc_spec_from_domain_record(record: Mapping[str, Any]) -> NPCSpec:
    """Normalize a Lorebuffa/Openworld-style NPC record.

    The source catalogs contain useful domain fields (faction, schedule,
    quests, shops, voice style, disposition). They are carried as metadata
    rather than copied into a second frontier NPC hierarchy. Malformed source
    fields fail closed so adapters cannot silently erase domain information.
    """

    if not isinstance(record, Mapping):
        raise TypeError("domain NPC record must be a mapping")

    name = str(record.get("name") or "").strip()
    if not name:
        raise ValueError("domain NPC record requires a name")

    description = str(record.get("description") or "").strip()
    if not description:
        description = name

    archetype = str(
        record.get("archetype") or record.get("role") or "citizen"
    ).strip().lower()
    traits = list(_strings(record.get("traits"), field_name="traits"))
    personality = str(record.get("personality") or "").strip().lower()
    if personality and personality not in traits:
        traits.append(personality)

    tags = list(_strings(record.get("tags"), field_name="tags"))
    for key in ("faction", "title", "voice_style"):
        value = str(record.get(key) or "").strip().lower()
        if value:
            tag = f"{key}:{value}"
            if tag not in tags:
                tags.append(tag)

    stats = _stats(record.get("stats"))
    disposition = record.get("initial_disposition")
    if disposition is not None:
        try:
            normalized_disposition = int(disposition)
        except (TypeError, ValueError) as exc:
            raise ValueError("domain NPC initial_disposition must be an integer") from exc
        if (
            "disposition" in stats
            and stats["disposition"] != normalized_disposition
        ):
            raise ValueError("domain NPC disposition conflicts with stats.disposition")
        stats["disposition"] = normalized_disposition

    consumed = {
        "name",
        "description",
        "archetype",
        "role",
        "traits",
        "personality",
        "tags",
        "stats",
        "initial_disposition",
    }
    metadata = {key: value for key, value in record.items() if key not in consumed}

    return NPCSpec(
        name=name,
        archetype=archetype or "citizen",
        description=description,
        traits=tuple(traits),
        tags=tuple(tags),
        stats=stats,
        metadata=metadata,
    )
