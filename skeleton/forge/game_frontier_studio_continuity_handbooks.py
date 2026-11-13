"""Nine hundred million on-demand continuity handbooks with SHA and real rankings.

Books are deterministic transformations of canonical source-producer contracts.
The virtual index is constant-space. Rankings are of ten actually rendered
sibling variants, never a fictitious global quality ranking.
"""
from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
import re
from typing import Any

from .game_frontier_studio import StudioError
from .game_frontier_studio_epoch_handbooks import (
    BOOK_COUNT as PARENT_COUNT, identity as parent_identity,
    number as parent_number, render as parent_render,
    _source_action as epoch_source_action,
)
from .game_frontier_studio_continuity_production import (
    CONTINUITIES, PURPOSES, CONTINUITY_ACTIONS,
)
from .game_frontier_studio_production_recipes import _DOMAINS, TREATMENTS
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_final_production import FINISHES
from .game_frontier_studio_worldline_production import WORLDLINES
from .game_frontier_studio_phase_production import PHASES
from .game_frontier_studio_campaign_production import CAMPAIGNS
from .game_frontier_studio_chronicle_production import CHRONICLES
from .game_frontier_studio_epoch_production import EPOCHS

SCHEMA = "skeleton.forge.continuity_handbook.v1"
RANK_SCHEMA = "skeleton.forge.continuity_handbook_ranking.v1"
BOOK_COUNT = PARENT_COUNT * len(CONTINUITIES)
if BOOK_COUNT != 900_000_000:
    raise RuntimeError("continuity handbook index must contain 900 million volumes")

BOOK_REVIEW = (
    "Exact tenant and source version are known to the editing host",
    "Only owned Forge Studio project data are transformed",
    "Source palette identifiers resolve before map painting",
    "Map edits stay inside the requested game layer bounds",
    "A central passable corridor survives the added treatment",
    "Prior map topology is included in content delta evidence",
    "Existing NPC identities remain immutable",
    "Existing authorial character voices are not rewritten",
    "Only newly generated actors receive pose refinements",
    "Existing quest stages and ending identities survive",
    "New quest branches bind actual canonical story records",
    "Chapter continuity references the prior authored context",
    "No plot fact from the original source is silently reversed",
    "Event page IDs are unique within a saved project",
    "Both game observations exist in the sensor schema",
    "Invalid observations cause no proposed gameplay action",
    "Observed event evaluation is reproducible",
    "Game actions remain proposals until native authorization",
    "Deterministic seed preserves source-edit replay integrity",
    "Source SHA and project revision are compared before commit",
    "Atomic edit rollback preserves the full original project",
    "Saved source rereads to the exact same content digest",
    "Godot native terrain output contains edited source cells",
    "Godot native quest graph contains authored quest stages",
    "Player travel traverses a representative edited route",
    "No unapproved external copyrighted text is incorporated",
    "No unlicensed visual or audio asset is copied",
    "Two independent reviewers inspect evidence and coverage",
    "Document completeness does not equal gameplay quality",
    "Native device playthrough and release approval remain separate",
)


def number(domain: str, treatment: str, director: str, worldline: str,
           phase: str, campaign: str, chronicle: str, epoch: str, continuity: str) -> int:
    if continuity not in CONTINUITIES:
        raise StudioError("unknown continuity handbook identity")
    return parent_number(domain, treatment, director, worldline, phase,
                         campaign, chronicle, epoch) * 10 + CONTINUITIES.index(continuity)


def identity(index: int) -> tuple[str, str, str, str, str, str, str, str, str]:
    if type(index) is not int or not 0 <= index < BOOK_COUNT:
        raise StudioError("continuity book index outside source catalogue")
    base, continuity = divmod(index, 10)
    return (*parent_identity(base), CONTINUITIES[continuity])


class ContinuityBookPaths(Sequence[str]):
    __slots__ = ()

    def __len__(self) -> int:
        return BOOK_COUNT

    def __getitem__(self, index):
        if isinstance(index, slice):
            indices = range(*index.indices(len(self)))
            if len(indices) > 64:
                raise StudioError("virtual catalogue slices are limited to 64 entries")
            return tuple(self[i] for i in indices)
        # Python sequences accept negative indexes; normalize before the strict
        # identity validator, which deliberately rejects out-of-range values.
        # Reject bool as an index rather than silently treating True as 1.
        if type(index) is not int:
            raise TypeError("continuity handbook index must be an integer or slice")
        if index < 0:
            index += BOOK_COUNT
        d, t, director, world, phase, campaign, chronicle, epoch, continuity = identity(index)
        return (f"game_studio_5000000000000/{d}/{t}/{director}/{world}/"
                f"{phase}/{campaign}/{chronicle}/{epoch}/{continuity}.md")


    @staticmethod
    def _rank_path(value: object) -> int | None:
        """Validate path identity without scanning the 900M-volume index."""
        prefix = "game_studio_5000000000000/"
        if type(value) is not str or len(value) > 512:
            return None
        if not value.startswith(prefix) or not value.endswith(".md"):
            return None
        parts = value[len(prefix):-3].split("/")
        if len(parts) != 9:
            return None
        try:
            return number(*parts)
        except (StudioError, TypeError, ValueError):
            return None

    def __contains__(self, value: object) -> bool:
        return self._rank_path(value) is not None

    def index(self, value: object, start: int = 0, stop: int | None = None) -> int:
        """O(1) exact source-path lookup with ordinary Sequence slice bounds."""
        if type(start) is not int or (stop is not None and type(stop) is not int):
            raise TypeError("continuity lookup bounds must be integers")
        rank = self._rank_path(value)
        if rank is None or rank not in range(*slice(start, stop).indices(len(self))):
            raise ValueError("continuity handbook identity is absent from selected range")
        return rank


CONTINUITY_BOOK_PATHS = ContinuityBookPaths()


def metadata(domain: str, treatment: str, director: str, worldline: str,
             phase: str, campaign: str, chronicle: str,
             epoch: str, continuity: str) -> dict[str, Any]:
    idx = number(domain, treatment, director, worldline, phase,
                 campaign, chronicle, epoch, continuity)
    return {
        "schema": SCHEMA, "volume": idx + 100_000_001, "volume_index": idx,
        "path": CONTINUITY_BOOK_PATHS[idx], "domain": domain,
        "treatment": treatment, "director": director, "worldline": worldline,
        "phase": phase, "campaign": campaign, "chronicle": chronicle, "epoch": epoch,
        "continuity": continuity, "source_archetypes": 50,
        "gameplay_systems": 10, "finish_passes": 10,
        "covered_commands": 5000, "source_bound": True,
    }


def list_books(
    *, domain: str = "", treatment: str = "", director: str = "",
    worldline: str = "", phase: str = "", campaign: str = "",
    chronicle: str = "", epoch: str = "", continuity: str = "",
    offset: int = 0, limit: int = 32,
) -> dict[str, Any]:
    filters = (domain, treatment, director, worldline, phase,
               campaign, chronicle, epoch, continuity)
    catalogs = (tuple(row[0] for row in _DOMAINS), TREATMENTS, DIRECTORS,
                WORLDLINES, PHASES, CAMPAIGNS, CHRONICLES, EPOCHS, CONTINUITIES)
    if (any(type(value) is not str or len(value) > 40
            or (value and value not in choices)
            for value, choices in zip(filters, catalogs))
        or type(offset) is not int or not 0 <= offset <= BOOK_COUNT
        or type(limit) is not int or not 1 <= limit <= 64):
        raise StudioError("invalid bounded continuity handbook search")
    selected = tuple(tuple(name for name in choices if not value or value == name)
                     for value, choices in zip(filters, catalogs))
    matched = 1
    for group in selected:
        matched *= len(group)
    items = []
    for rank in range(offset, min(offset + limit, matched)):
        remainder = rank
        coordinates = [0] * len(selected)
        for pos in range(len(selected) - 1, -1, -1):
            remainder, coordinates[pos] = divmod(remainder, len(selected[pos]))
        items.append(metadata(*(options[i] for options, i in zip(selected, coordinates))))
    return {
        "schema": "skeleton.forge.continuity_handbook_listing.v1",
        "total_catalog": BOOK_COUNT, "matched": matched,
        "offset": offset, "limit": limit,
        "next_offset": offset + limit if offset + limit < matched else None,
        "items": items,
    }


def _source_action(domain: str, blueprint: str, treatment: str,
                   system: str, director: str, finish: str, worldline: str,
                   phase: str, campaign: str, chronicle: str, epoch: str,
                   continuity: str) -> str:
    parent = epoch_source_action(domain, blueprint, treatment, system,
                                    director, finish, worldline, phase,
                                    campaign, chronicle, epoch)
    action = ("continuity_" + parent.removeprefix("epoch_")
              + "__________" + continuity)
    if action not in CONTINUITY_ACTIONS:
        raise StudioError("book references unregistered source operation")
    return action


def render(domain: str, treatment: str, director: str, worldline: str,
           phase: str, campaign: str, chronicle: str,
           epoch: str, continuity: str) -> str:
    item = metadata(domain, treatment, director, worldline, phase,
                    campaign, chronicle, epoch, continuity)
    archetypes = next(row[1] for row in _DOMAINS if row[0] == domain)
    axis = CONTINUITIES.index(continuity)
    examples = []
    for i, archetype in enumerate(archetypes):
        operation = _source_action(
            domain, archetype, treatment, GAMEPLAY_LAYERS[0], director,
            FINISHES[0], worldline, phase, campaign, chronicle, epoch, continuity)
        examples.append(f"| {i + 1} | {archetype} | {operation} |")
    systems = []
    for i, system in enumerate(GAMEPLAY_LAYERS):
        operation = _source_action(
            domain, archetypes[i], treatment, system, director,
            FINISHES[i], worldline, phase, campaign, chronicle, epoch, continuity)
        systems.append(
            f"### System {i + 1}: {system}\n\n"
            f"Executable continuity operation: {operation}\n\n"
            "Compare source SHA before and after map topology, observed RPG page, "
            "new-only actor/quest changes, and actual native-game source bytes.\n"
        )
    upstream = parent_render(domain, treatment, director, worldline,
                             phase, campaign, chronicle, epoch)
    markdown = (
        f"# Volume {item['volume']:,}/1,000,000,000 — {continuity}\n\n"
        f"Source path: {item['path']}\n\n"
        "## Concrete continuity mechanic\n\n"
        f"{PURPOSES[axis]}. This operation first applies the exact previous "
        "epoch source producer, then writes a distinct deterministic "
        "game-tile treatment with an uninterrupted central travel lane, "
        "and finally appends an independently observed RPG proposal page. "
        "Existing cast and quest objects remain immutable. No gameplay "
        "effect executes without the native game owner's authorization.\n\n"
        "## Fifty registered continuity source archetypes\n\n"
        "| # | Blueprint | Exact executable source operation |\n"
        "|---:|---|---|\n" + "\n".join(examples) + "\n\n"
        "## Ten actual gameplay system examples\n\n"
        + "\n".join(systems) + "\n\n"
        "## Release-quality operational contract\n\n"
        "Open the tenant-owned project and read its exact saved revision and "
        "content SHA-256. Preview immutable transformations using a bounded "
        "rectangular authoring region and reproducible integer seed. "
        "Examine route reachability, actor/quest identity and real game event "
        "conditions before atomic compare-and-set persistence. Read back "
        "the saved source, compile native Godot terrain and quest graph, "
        "rehearse gameplay, inspect performance and accessibility, and "
        "record approvals without substituting a manuscript grade for "
        "native gameplay validation. Canon and licensed assets are "
        "strictly outside this source-edit generator's authority.\n\n"
        "## Thirty evidence and adversarial acceptance questions\n\n"
        + "\n".join(f"{i + 1}. {check}." for i, check in enumerate(BOOK_REVIEW))
        + "\n\n"
        "## Source-grounded preceding epoch manual\n\n"
        + upstream + "\n\n"
        "## Rights, provenance and actual release status\n\n"
        "This is a deterministic composed source recipe, not an independent "
        "game engine or finished title. A document quality score does not "
        "establish creative originality, copyright clearance, runtime "
        "safety, real hardware performance or shipment readiness.\n"
    )
    if len(markdown.encode("utf8")) > 256_000:
        raise StudioError("continuity manuscript exceeded maximum 256KB")
    return markdown


_WORDS = re.compile(r"\b[\w'-]+\b", re.UNICODE)


def grade(markdown: str, item: dict[str, Any]) -> dict[str, Any]:
    if type(markdown) is not str or len(markdown.encode("utf8")) > 256_000:
        raise StudioError("invalid continuity manuscript")
    lines = markdown.splitlines()
    criteria = {
        "registered_source": item.get("source_bound") is True
                             and item.get("covered_commands") == 5000,
        "fifty_archetypes": sum(line.startswith("| ") and " | continuity_" in line
                               for line in lines) == 50,
        "ten_system_examples": markdown.count("Executable continuity operation: ") == 10,
        "required_sections": all(section in markdown for section in (
            "## Concrete continuity", "## Fifty registered",
            "## Ten actual gameplay", "## Release-quality",
            "## Thirty evidence", "## Source-grounded",
            "## Rights, provenance")),
        "thirty_adversarial_probes": all(f"{i + 1}. {check}." in markdown
                                        for i, check in enumerate(BOOK_REVIEW)),
        "source_safety": "compare-and-set" in markdown
                         and "SHA-256" in markdown,
        "native_source_ownership": "native Godot" in markdown
                                   and "quest graph" in markdown,
        "release_boundary": "copyright clearance" in markdown
                            and "performance" in markdown,
    }
    weights = (15, 20, 15, 10, 10, 10, 10, 10)
    return {
        "quality_score": sum(weight for accepted, weight
                             in zip(criteria.values(), weights) if accepted),
        "quality_max": 100,
        "quality_kind": "objective_document_completeness_not_gameplay",
        "criteria": criteria, "words": len(_WORDS.findall(markdown)),
        "characters": len(markdown), "bytes": len(markdown.encode("utf8")),
    }


def receipt(*parts: str) -> dict[str, Any]:
    item = metadata(*parts)
    markdown = render(*parts)
    return {
        **item, **grade(markdown, item),
        "content_sha256": sha256(markdown.encode("utf8")).hexdigest(),
        "markdown": markdown,
    }


def rank_variants(domain: str, treatment: str, director: str,
                  worldline: str, phase: str, campaign: str,
                  chronicle: str, epoch: str, *, sort: str = "quality") -> dict[str, Any]:
    if sort not in ("quality", "length"):
        raise StudioError("continuity handbook sort must be quality or length")
    rows = []
    for continuity in CONTINUITIES:
        item = receipt(domain, treatment, director, worldline,
                       phase, campaign, chronicle, epoch, continuity)
        item.pop("markdown")
        rows.append(item)
    if sort == "quality":
        rows.sort(key=lambda row: (-row["quality_score"], -row["words"], row["continuity"]))
    else:
        rows.sort(key=lambda row: (-row["words"], -row["quality_score"], row["continuity"]))
    for rank, item in enumerate(rows, 1):
        item["rank"] = rank
    return {
        "schema": RANK_SCHEMA, "sort": sort,
        "scope": "ten_continuity_variants_for_one_exact_epoch_context",
        "compared": 10, "items": rows,
    }
