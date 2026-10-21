"""900M addressable source-grounded Saga technical books and exact rankings.

Manuscripts are rendered only when requested, never materialized as a
900-million-file tree. Grades measure objective documentation coverage, not
gameplay, originality, native certification, or legal clearance.
"""
from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
import re
from typing import Any

from .game_frontier_studio import StudioError
from .game_frontier_studio_epoch_handbooks import (
    BOOK_COUNT as PARENT_COUNT, number as parent_number,
    identity as parent_identity, render as parent_render,
)
from .game_frontier_studio_saga_production import (
    SAGAS, OBJECTIVES, SIGNALS, SAGA_ACTIONS,
)
from .game_frontier_studio_production_recipes import _DOMAINS, _slug, TREATMENTS
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_final_production import FINISHES
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_worldline_production import WORLDLINES
from .game_frontier_studio_phase_production import PHASES
from .game_frontier_studio_campaign_production import CAMPAIGNS
from .game_frontier_studio_chronicle_production import CHRONICLES
from .game_frontier_studio_epoch_production import EPOCHS

SCHEMA = "skeleton.forge.saga_handbook.v1"
RANK_SCHEMA = "skeleton.forge.saga_handbook_ranking.v1"
BOOK_COUNT = PARENT_COUNT * len(SAGAS)
if BOOK_COUNT != 900_000_000:
    raise RuntimeError("saga handbook index must contain 900M valid IDs")


def number(domain: str, treatment: str, director: str, worldline: str,
           phase: str, campaign: str, chronicle: str, epoch: str,
           saga: str) -> int:
    if saga not in SAGAS:
        raise StudioError("unregistered longform saga document")
    return parent_number(domain, treatment, director, worldline, phase,
                         campaign, chronicle, epoch) * 10 + SAGAS.index(saga)


def identity(index: int) -> tuple[str, ...]:
    if type(index) is not int or not 0 <= index < BOOK_COUNT:
        raise StudioError("saga document index outside catalogue")
    parent, axis = divmod(index, 10)
    return (*parent_identity(parent), SAGAS[axis])


class SagaBookPaths(Sequence[str]):
    __slots__ = ()

    def __len__(self) -> int:
        return BOOK_COUNT

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        d, t, r, w, p, c, h, e, s = identity(index)
        return f"game_studio_5000000000000/{d}/{t}/{r}/{w}/{p}/{c}/{h}/{e}/{s}.md"


SAGA_BOOK_PATHS = SagaBookPaths()


def metadata(*parts: str) -> dict[str, Any]:
    if len(parts) != 9:
        raise StudioError("saga manuscript requires exact nine-axis identity")
    index = number(*parts)
    d, t, director, worldline, phase, campaign, chronicle, epoch, saga = parts
    return {
        "schema": SCHEMA, "volume": 100_000_001 + index,
        "volume_index": index, "path": SAGA_BOOK_PATHS[index],
        "domain": d, "treatment": t, "director": director,
        "worldline": worldline, "phase": phase, "campaign": campaign,
        "chronicle": chronicle, "epoch": epoch, "saga": saga,
        "source_archetypes": 50, "gameplay_systems": 10,
        "finish_passes": 10, "covered_commands": 5000, "source_bound": True,
    }


def list_books(*, domain: str = "", treatment: str = "",
               director: str = "", worldline: str = "",
               phase: str = "", campaign: str = "",
               chronicle: str = "", epoch: str = "", saga: str = "",
               offset: int = 0, limit: int = 32) -> dict[str, Any]:
    values = (domain, treatment, director, worldline, phase,
              campaign, chronicle, epoch, saga)
    axes = (tuple(row[0] for row in _DOMAINS), TREATMENTS, DIRECTORS,
            WORLDLINES, PHASES, CAMPAIGNS, CHRONICLES, EPOCHS, SAGAS)
    if (any(type(v) is not str or len(v) > 40
            or (v and v not in values)
            for v, values in zip(values, axes))
            or type(offset) is not int or not 0 <= offset <= BOOK_COUNT
            or type(limit) is not int or not 1 <= limit <= 64):
        raise StudioError("invalid saga handbook search parameters")
    groups = tuple(tuple(v for v in names if not selected or v == selected)
                   for selected, names in zip(values, axes))
    matched = 1
    for group in groups:
        matched *= len(group)
    rows = []
    for rank in range(offset, min(offset + limit, matched)):
        remaining = rank
        coordinates = [0] * len(groups)
        for i in range(len(groups) - 1, -1, -1):
            remaining, coordinates[i] = divmod(remaining, len(groups[i]))
        rows.append(metadata(*(group[pos] for group, pos in zip(groups, coordinates))))
    return {
        "schema": "skeleton.forge.saga_handbook_listing.v1",
        "total_catalog": BOOK_COUNT, "matched": matched,
        "offset": offset, "limit": limit,
        "next_offset": offset + limit if offset + limit < matched else None,
        "items": rows,
    }


def _registered_action(domain: str, blueprint: str, treatment: str,
                       layer: str, director: str, finish: str, worldline: str,
                       phase: str, campaign: str, chronicle: str,
                       epoch: str, saga: str) -> str:
    source = (f"saga_{domain}_{_slug(blueprint)}__{treatment}___{layer}"
              f"____{director}_____{finish}______{worldline}"
              f"_______{phase}________{campaign}_________{chronicle}"
              f"__________{epoch}___________{saga}")
    if source not in SAGA_ACTIONS:
        raise StudioError("handbook references an unregistered real source operation")
    return source


REVIEW = (
    "Exact owner, tenant and versioned project source are authenticated",
    "Original GDD digest and chapter intent are pinned before editing",
    "The registered saga action passes exact membership verification",
    "All 50 source archetypes resolve to registered source builders",
    "Each terrain edit is bounded by canonical layer coordinates",
    "Authored floor and wall indices exist in that map palette",
    "The deterministic seed produces identical replay hashes",
    "Prior chapter dialogue remains verbatim without forced rewriting",
    "Earlier actor identities and placements remain unchanged",
    "Only cast members introduced in this transaction are staged",
    "Previously authored quests and alternate endings are preserved",
    "New quest branches have an independently reachable terminal",
    "Saga choice branch IDs are collision-free and hash-addressed",
    "All RPG pages have two independently observed runtime predicates",
    "Missing or invalid observation suppresses the event proposal",
    "Accepted proposals never bypass native game ownership",
    "Cinematic camera events do not silently modify gameworld state",
    "Quest promotion does not invent approvals or player progress",
    "Environmental cues are physically coherent with source facts",
    "Routes remain navigable after every source topology mutation",
    "Native collision and camera traversal are tested separately",
    "Every staged action produces an immutable source digest",
    "The host enforces compare-and-set on persisted project revision",
    "Stale edits and malformed payloads fail without partial saves",
    "An interrupted build can replay from the previous source hash",
    "Versioned project reopen restores canon and stage graph",
    "Generated scene/quest files compile in the real Godot toolchain",
    "Observed playthrough and save/load are separately signed",
    "Controller layouts and accessibility paths retain parity",
    "Native platform budgets are profiled rather than assumed",
    "No copied third-party graphics, ROM code or script is embedded",
    "Exact design rights and licenses remain independently cleared",
    "Rendered manuscript and registered operations match",
    "Document ranking measures words and structure, not creativity",
    "Two independent quality reviewers inspect failure cases",
    "Final adversarial reviewer examines reviewer disagreements",
    "Copyright and creative rewrite review occurs before release",
    "Long-form canonical narrative continuity is explicitly checked",
    "Operator can restore an earlier approved version and receipts",
    "Production promotion requires external native and rights signoff",
)


def render(domain: str, treatment: str, director: str, worldline: str,
           phase: str, campaign: str, chronicle: str, epoch: str,
           saga: str) -> str:
    parts = (domain, treatment, director, worldline, phase,
             campaign, chronicle, epoch, saga)
    meta = metadata(*parts)
    blueprints = next(row[1] for row in _DOMAINS if row[0] == domain)
    axis = SAGAS.index(saga)
    rows = []
    for i, blueprint in enumerate(blueprints):
        operation = _registered_action(
            domain, blueprint, treatment, GAMEPLAY_LAYERS[0], director,
            FINISHES[0], worldline, phase, campaign, chronicle, epoch, saga,
        )
        rows.append(f"| {i + 1} | {blueprint} | {operation} |")
    system_sections = []
    for i, system in enumerate(GAMEPLAY_LAYERS):
        operation = _registered_action(
            domain, blueprints[i], treatment, system, director,
            FINISHES[i], worldline, phase, campaign, chronicle, epoch, saga,
        )
        system_sections.append(
            f"### Production system {i + 1}: {system}\n\n"
            f"Verified registered saga edit: {operation}\n\n"
            "Preview canonical map and event changes, review the new-only "
            "story branch, then compile and replay with actual runtime evidence.\n"
        )
    conditions = SIGNALS[axis]
    upstream = parent_render(domain, treatment, director, worldline,
                             phase, campaign, chronicle, epoch)
    markdown = (
        f"# Volume {meta['volume']:,}/1,000,000,000 — {saga}\n\n"
        f"Exact reproducible source: {meta['path']}\n\n"
        "## Narrative continuity and authored world treatment\n\n"
        f"{OBJECTIVES[axis]}. The registered source operation first executes "
        "its preceding epoch. This saga then authors a further distinguishable "
        "map-topology arrangement, an evidence-gated event and a new-only "
        "quest branch. Original voices and established plot remain immutable.\n\n"
        "## Real observed gameplay signals and proposal-only effects\n\n"
        f"Trigger A: {conditions[0]} {conditions[1]} {conditions[2]}; "
        f"trigger B: {conditions[3]} {conditions[4]} {conditions[5]}. "
        f"Proposed native action: {conditions[6]} / {conditions[7]} / "
        f"{conditions[8]} / {conditions[9]}. "
        "A source event is not a runtime action until the host approves it.\n\n"
        "## Fifty distinct registered source archetypes\n\n"
        "| # | Original source archetype | Executable saga operation |\n"
        "|---:|---|---|\n" + "\n".join(rows) + "\n\n"
        "## Ten gameplay-system authoring workups\n\n"
        + "\n".join(system_sections) + "\n\n"
        "## Persistent canonical authoring and playable native build\n\n"
        "Authenticate the project and its canonical source SHA-256. Pin the "
        "exact world version, preview pure source edits, audit source and "
        "story deltas, then submit an authorized compare-and-set to the "
        "existing host. Reopen the saved typed StudioProject, export original "
        "Godot terrain and quest source, run controller simulation and "
        "native playthrough, and verify chapter state on save/reload. "
        "Do not treat authored source as proof of a native executable.\n\n"
        "## Forty objective, adversarial and rights review conditions\n\n"
        + "\n".join(f"{i + 1}. {check}." for i, check in enumerate(REVIEW))
        + "\n\n## Inherited complete temporal production dossier\n\n"
        + upstream + "\n\n"
        "## Release boundary and epistemic limitations\n\n"
        "Five trillion combinations are not five trillion independent games. "
        "One billion addressable manuals are not one billion checked-in files. "
        "Source completeness and word counts do not establish playable "
        "quality, legal originality, licensed content, model training, "
        "GPU validation or production-release approval.\n"
    )
    if len(markdown.encode("utf8")) > 384_000:
        raise StudioError("rendered saga handbook exceeds bounded payload")
    return markdown


_WORDS = re.compile(r"\b[\w'-]+\b", re.UNICODE)


def grade(markdown: str, meta: dict[str, Any]) -> dict[str, Any]:
    if type(markdown) is not str or len(markdown.encode("utf8")) > 384_000:
        raise StudioError("invalid source-grounded saga handbook")
    criteria = {
        "registered_source": bool(meta.get("source_bound")) and meta.get("covered_commands") == 5000,
        "fifty_exact_registered_archetypes":
            sum(line.startswith("| ") and " | saga_" in line
                for line in markdown.splitlines()) == 50,
        "ten_gameplay_workups": markdown.count("Verified registered saga edit: ") == 10,
        "seven_saga_sections": all(text in markdown for text in (
            "## Narrative continuity", "## Real observed",
            "## Fifty distinct", "## Ten gameplay-system",
            "## Persistent canonical", "## Forty objective",
            "## Inherited complete", "## Release boundary",
        )),
        "forty_adversarial_review_checks":
            all(f"{i + 1}. {condition}." in markdown
                for i, condition in enumerate(REVIEW)),
        "physical_environment_observations": "Trigger A:" in markdown and "trigger B:" in markdown,
        "authorized_persistence": "authorized compare-and-set" in markdown and "SHA-256" in markdown,
        "native_and_copyright_limits": "Godot" in markdown and "licensed content" in markdown,
    }
    weights = (15, 20, 15, 10, 10, 10, 10, 10)
    return {
        "quality_score": sum(weight for enabled, weight in zip(criteria.values(), weights)
                             if enabled),
        "quality_max": 100,
        "quality_kind": "objective_document_structure_not_gameplay_merit",
        "criteria": criteria, "words": len(_WORDS.findall(markdown)),
        "characters": len(markdown), "bytes": len(markdown.encode("utf8")),
    }


def receipt(*parts: str) -> dict[str, Any]:
    meta = metadata(*parts)
    markdown = render(*parts)
    return {
        **meta, **grade(markdown, meta),
        "content_sha256": sha256(markdown.encode("utf8")).hexdigest(),
        "markdown": markdown,
    }


def rank_variants(domain: str, treatment: str, director: str, worldline: str,
                  phase: str, campaign: str, chronicle: str, epoch: str,
                  *, sort: str = "quality") -> dict[str, Any]:
    if sort not in ("quality", "length"):
        raise StudioError("saga ranking needs quality or length")
    rows = []
    for saga in SAGAS:
        item = receipt(domain, treatment, director, worldline,
                       phase, campaign, chronicle, epoch, saga)
        item.pop("markdown")
        rows.append(item)
    if sort == "quality":
        rows.sort(key=lambda item: (-item["quality_score"],
                                    -item["words"], item["saga"]))
    else:
        rows.sort(key=lambda item: (-item["words"],
                                    -item["quality_score"], item["saga"]))
    for i, item in enumerate(rows, 1):
        item["rank"] = i
    return {
        "schema": RANK_SCHEMA, "sort": sort,
        "scope": "ten_rendered_saga_variants_for_one_exact_epoch_context",
        "compared": 10, "items": rows,
    }
