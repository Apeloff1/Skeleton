"""Adapters from source-domain NPC records into the frontier NPC contract."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from skeleton.frontier.npc import NPCSpec


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (text.lower(),) if text else ()
    if isinstance(value, Sequence):
        return tuple(
            str(item).strip().lower()
            for item in value
            if str(item).strip()
        )
    return ()


def npc_spec_from_domain_record(record: Mapping[str, Any]) -> NPCSpec:
    """Normalize a Lorebuffa/Openworld-style NPC record.

    The source catalogs contain useful domain fields (faction, schedule,
    quests, shops, voice style, disposition). They are carried as metadata
    rather than copied into a second frontier NPC hierarchy.
    """

    name = str(record.get("name") or "").strip()
    if not name:
        raise ValueError("domain NPC record requires a name")

    description = str(record.get("description") or "").strip()
    if not description:
        description = name

    archetype = str(
        record.get("archetype") or record.get("role") or "citizen"
    ).strip().lower()
    traits = list(_strings(record.get("traits")))
    personality = str(record.get("personality") or "").strip().lower()
    if personality and personality not in traits:
        traits.append(personality)

    tags = list(_strings(record.get("tags")))
    for key in ("faction", "title", "voice_style"):
        value = str(record.get(key) or "").strip().lower()
        if value:
            tags.append(f"{key}:{value}")

    stats = dict(record.get("stats") or {})
    disposition = record.get("initial_disposition")
    if disposition is not None:
        try:
            stats.setdefault("disposition", int(disposition))
        except (TypeError, ValueError):
            pass

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
        tags=tuple(dict.fromkeys(tags)),
        stats=stats,
        metadata=metadata,
    )
