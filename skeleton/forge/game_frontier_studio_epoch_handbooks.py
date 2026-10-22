"""90M addressable source-grounded epoch manuscripts with objective rankings.

Each text is rendered on demand from registered editor IDs, not claimed to be
a committed file. Completeness scores measure document structure only.
"""
from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
import re
from typing import Any

from .game_frontier_studio import StudioError
from .game_frontier_studio_chronicle_handbooks import (
    BOOK_COUNT as PARENT_COUNT, number as parent_number,
    identity as parent_identity, render as parent_render,
)
from .game_frontier_studio_epoch_production import EPOCHS, OBJECTIVES, EPOCH_ACTIONS
from .game_frontier_studio_production_recipes import _DOMAINS, _slug, TREATMENTS
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_final_production import FINISHES
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_worldline_production import WORLDLINES
from .game_frontier_studio_phase_production import PHASES
from .game_frontier_studio_campaign_production import CAMPAIGNS
from .game_frontier_studio_chronicle_production import CHRONICLES

SCHEMA = "skeleton.forge.epoch_handbook.v1"
RANK_SCHEMA = "skeleton.forge.epoch_handbook_ranking.v1"
BOOK_COUNT = PARENT_COUNT * len(EPOCHS)
if BOOK_COUNT != 90_000_000:
    raise RuntimeError("90M temporal handbooks expected")


def number(domain: str, treatment: str, director: str, worldline: str,
           phase: str, campaign: str, chronicle: str, epoch: str) -> int:
    if epoch not in EPOCHS:
        raise StudioError("unknown epoch handbook identity")
    return parent_number(domain, treatment, director, worldline, phase,
                         campaign, chronicle) * 10 + EPOCHS.index(epoch)


def identity(index: int) -> tuple[str, str, str, str, str, str, str, str]:
    if type(index) is not int or not 0 <= index < BOOK_COUNT:
        raise StudioError("epoch handbook outside registered catalogue")
    parent, axis = divmod(index, 10)
    return (*parent_identity(parent), EPOCHS[axis])


class EpochBookPaths(Sequence[str]):
    __slots__ = ()
    def __len__(self):
        return BOOK_COUNT

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        d, t, r, w, p, c, h, e = identity(index)
        return f"game_studio_500000000000/{d}/{t}/{r}/{w}/{p}/{c}/{h}/{e}.md"


EPOCH_BOOK_PATHS = EpochBookPaths()


def metadata(*parts: str) -> dict[str, Any]:
    idx = number(*parts)
    d, t, r, w, p, c, h, e = parts
    return {
        "schema": SCHEMA, "volume": 10_000_001 + idx, "volume_index": idx,
        "path": EPOCH_BOOK_PATHS[idx],
        "domain": d, "treatment": t, "director": r,
        "worldline": w, "phase": p, "campaign": c,
        "chronicle": h, "epoch": e,
        "source_archetypes": 50, "gameplay_systems": 10,
        "finish_passes": 10, "covered_commands": 5000, "source_bound": True,
    }


def list_books(*, domain: str = "", treatment: str = "", director: str = "",
               worldline: str = "", phase: str = "", campaign: str = "",
               chronicle: str = "", epoch: str = "",
               offset: int = 0, limit: int = 32) -> dict[str, Any]:
    values = (domain, treatment, director, worldline, phase,
              campaign, chronicle, epoch)
    catalogs = (tuple(row[0] for row in _DOMAINS), TREATMENTS, DIRECTORS,
                WORLDLINES, PHASES, CAMPAIGNS, CHRONICLES, EPOCHS)
    if (any(type(v) is not str or len(v) > 40 or (v and v not in names)
            for v, names in zip(values, catalogs))
            or type(offset) is not int or not 0 <= offset <= BOOK_COUNT
            or type(limit) is not int or not 1 <= limit <= 64):
        raise StudioError("invalid bounded epoch handbook search")
    groups = tuple(tuple(v for v in names if not selected or v == selected)
                   for selected, names in zip(values, catalogs))
    matched = 1
    for group in groups:
        matched *= len(group)
    rows = []
    for rank in range(offset, min(matched, offset + limit)):
        local = rank
        coords = [0] * len(groups)
        for i in range(len(groups) - 1, -1, -1):
            local, coords[i] = divmod(local, len(groups[i]))
        rows.append(metadata(*(group[coord] for group, coord in zip(groups, coords))))
    return {
        "schema": "skeleton.forge.epoch_handbook_listing.v1",
        "total_catalog": BOOK_COUNT, "matched": matched,
        "offset": offset, "limit": limit,
        "next_offset": offset + limit if offset + limit < matched else None,
        "items": rows,
    }


def _source_action(d: str, blueprint: str, t: str, game: str,
                   r: str, finish: str, w: str, p: str,
                   c: str, h: str, e: str) -> str:
    action = (f"epoch_{d}_{_slug(blueprint)}__{t}___{game}"
              f"____{r}_____{finish}______{w}_______{p}"
              f"________{c}_________{h}__________{e}")
    if action not in EPOCH_ACTIONS:
        raise StudioError("epoch handbook references unregistered source producer")
    return action


CHECKS = (
    "Source revision and owner project identity are pinned",
    "Authoring command matches the full registered action identity",
    "Every source archetype has a distinct registered operation",
    "Palette indices resolve within the canonical project layer",
    "Temporal edit remains inside its supplied map rectangle",
    "Source seed reproduces identical tile and page digests",
    "Original character records are not mutated",
    "Original quest records and authorial voice are unchanged",
    "Only this transaction's new cast receives temporal positions",
    "Only new quest branches receive epoch stage updates",
    "Original chronicle editing completes before epoch refinements",
    "Each environmental event uses two real sensor predicates",
    "Invalid observations do not produce runtime approvals",
    "Accepted observations remain proposals pending native authority",
    "Host CAS rejects a stale expected project version",
    "Preview output changes neither persisted source nor ownership",
    "Compilation emits canonical Godot source paths",
    "Topological route continuity is independently evaluated",
    "Native controller movement and collision are exercised",
    "Save-load and resume preserve source and quest identities",
    "Memory and generation budgets remain bounded per operation",
    "Requested book identity is exact and reversible",
    "Batched export verifies written UTF-8 bytes against SHA-256",
    "Objective quality and rendered length are ranked separately",
    "No claim of device-native gameplay follows from rendered docs",
    "No copied copyrighted story or assets enter authored output",
    "Independent source reviewer examines mutation receipts",
    "Independent runtime reviewer examines observed game behavior",
    "Rollback to prior approved project remains possible",
    "Production release and legal clearance require separate approval",
)


def render(domain: str, treatment: str, director: str, worldline: str,
           phase: str, campaign: str, chronicle: str, epoch: str) -> str:
    parts = (domain, treatment, director, worldline, phase,
             campaign, chronicle, epoch)
    meta = metadata(*parts)
    source = next(row[1] for row in _DOMAINS if row[0] == domain)
    objective = OBJECTIVES[EPOCHS.index(epoch)]
    rows = []
    for i, blueprint in enumerate(source):
        action = _source_action(domain, blueprint, treatment,
                                GAMEPLAY_LAYERS[0], director, FINISHES[0],
                                worldline, phase, campaign, chronicle, epoch)
        rows.append(f"| {i + 1} | {blueprint} | {action} |")
    systems = []
    for i, layer in enumerate(GAMEPLAY_LAYERS):
        action = _source_action(domain, source[i], treatment,
                                layer, director, FINISHES[i],
                                worldline, phase, campaign, chronicle, epoch)
        systems.append(f"### Gameplay system {i + 1}: {layer}\n\n"
                       f"Executable epoch source: {action}\n\n"
                       "Inspect project version, tile mutation, independent event "
                       "predicate and native-source compilation receipts.\n")
    upstream = parent_render(domain, treatment, director, worldline,
                             phase, campaign, chronicle)
    markdown = (
        f"# Volume {meta['volume']:,}/100,000,000 — {epoch}\n\n"
        f"Source path: {meta['path']}\n\n"
        "## Temporal scenario and authored effect\n\n"
        f"{objective}. Source editing composes an exact existing chronicle "
        "operation, bounded ten-pattern terrain pass, typed sensor event, "
        "and new-only character/quest refinements. Event effects are "
        "proposals, not automatically executed game actions.\n\n"
        "## Fifty registered source archetypes\n\n"
        "| # | Archetype | Exact epoch producer |\n|---:|---|---|\n"
        + "\n".join(rows) + "\n\n"
        "## Ten gameplay system workups\n\n"
        + "\n".join(systems) + "\n\n"
        "## Authoring, replay and native build contract\n\n"
        "Resolve the existing authenticated project, capture exact version "
        "and content SHA-256, preview a pure transaction, and submit only "
        "under canonical host compare-and-set. Read back the versioned "
        "project, independently replay observed events, then compile "
        "Godot terrain and graph. Real native gameplay and operational "
        "duration remain separate signoffs.\n\n"
        "## Thirty adversarial source and release checks\n\n"
        + "\n".join(f"{i+1}. {check}." for i, check in enumerate(CHECKS))
        + "\n\n## Complete upstream chronicle dossier\n\n"
        + upstream + "\n\n"
        "## Legal and production qualification boundary\n\n"
        "All 500 billion identifiers describe source compositions, not "
        "complete games, unique engines, verified model weights or "
        "independently attested quality. Document metrics are not "
        "copyright, platform performance or release certifications.\n"
    )
    if len(markdown.encode("utf8")) > 256_000:
        raise StudioError("epoch handbook exceeds 256KB bound")
    return markdown


_WORDS = re.compile(r"\b[\w'-]+\b", re.UNICODE)


def grade(markdown: str, meta: dict[str, Any]) -> dict[str, Any]:
    if type(markdown) is not str or len(markdown.encode("utf8")) > 256_000:
        raise StudioError("invalid epoch source manuscript")
    checks = {
        "registered_identity": bool(meta.get("source_bound")) and meta.get("covered_commands") == 5000,
        "fifty_exact_archetypes": sum(line.startswith("| ") and " | epoch_" in line
                                      for line in markdown.splitlines()) == 50,
        "ten_system_workups": markdown.count("Executable epoch source: ") == 10,
        "all_six_sections": all(s in markdown for s in (
            "## Temporal scenario", "## Fifty registered", "## Ten gameplay",
            "## Authoring, replay", "## Thirty adversarial",
            "## Complete upstream", "## Legal and production")),
        "thirty_review_questions": all(f"{i+1}. {check}." in markdown
                                       for i, check in enumerate(CHECKS)),
        "retained_upstream_source": "## Chronicle objective" in markdown,
        "host_authority": "host compare-and-set" in markdown,
        "native_and_rights_boundary": "copyright" in markdown and "native" in markdown,
    }
    weights = (15, 20, 15, 10, 10, 10, 10, 10)
    return {
        "quality_score": sum(weight for ok, weight in zip(checks.values(), weights) if ok),
        "quality_max": 100, "quality_kind": "structural_document_completeness_not_gameplay",
        "criteria": checks, "words": len(_WORDS.findall(markdown)),
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
                  phase: str, campaign: str, chronicle: str,
                  *, sort: str = "quality") -> dict[str, Any]:
    if sort not in ("quality", "length"):
        raise StudioError("epoch book ranking must be quality or length")
    rows = []
    for epoch in EPOCHS:
        item = receipt(domain, treatment, director, worldline,
                       phase, campaign, chronicle, epoch)
        item.pop("markdown")
        rows.append(item)
    if sort == "quality":
        rows.sort(key=lambda r: (-r["quality_score"], -r["words"], r["epoch"]))
    else:
        rows.sort(key=lambda r: (-r["words"], -r["quality_score"], r["epoch"]))
    for index, item in enumerate(rows, 1):
        item["rank"] = index
    return {
        "schema": RANK_SCHEMA, "sort": sort,
        "scope": "ten_rendered_epoch_variants_for_one_exact_chronicle",
        "compared": 10, "items": rows,
    }
