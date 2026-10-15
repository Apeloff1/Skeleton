"""Replay-verified multi-circumstance game-rule data for Jeeves candidates.

No agent-supplied observation, score, reward or LM label is admitted. Every
scenario source and every action is reconstructed with canonical game rules.
The resulting context labels are observational training data only. Independent
evaluation holdouts and live-model promotion remain separate.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
import os
from pathlib import Path

from skeleton.jeeves.game_studio_rule_curriculum import (
    RuleCurriculumError, verify_rule_curriculum,
)
from .jeeves_studio_curriculum import (
    MAX_BYTES, MAX_EXAMPLES, StudioCurriculumError, _canonical,
    build_studio_curriculum, verify_studio_curriculum,
)

RULE_CORPUS_SCHEMA = "skeleton.jeeves.rule_based_training_corpus.v1"
MAX_RULE_EPISODES = 32


def _sha(value):
    return sha256(_canonical(value)).hexdigest()


def _context(scenario: Mapping[str, object], source: Mapping[str, object]) -> str:
    fields = []
    for key, value in sorted(source["settings"].items()):
        # Never introduce arbitrary text into synthetic instructions. Only
        # normalized numbers, bools and low-entropy allowed enum labels pass.
        if type(value) in (int, bool):
            fields.append(key + "=" + str(value).lower())
        elif type(value) is str and value.isascii() and value.replace("_","").isalnum():
            fields.append(key + "=" + value)
    return (
        "Original game training circumstance " + scenario["scenario_id"] +
        " in " + source["editor"] + ". Verified editor rules: " +
        "; ".join(fields) + ". "
    )


def build_rule_training_corpus(
    plan: Mapping[str, object], episodes: Sequence[Mapping[str, object]],
    *, authorized: bool, rights_cleared: bool,
) -> dict[str, object]:
    if authorized is not True or rights_cleared is not True:
        raise PermissionError("candidate corpus requires real operator and source rights admission")
    curriculum = verify_rule_curriculum(dict(plan))
    if type(episodes) not in (list, tuple) or not 2 <= len(episodes) <= MAX_RULE_EPISODES:
        raise StudioCurriculumError("bounded multi-condition engine episodes required")
    scenarios = {entry["scenario_id"]: entry for entry in curriculum["scenarios"]}
    entries = []
    seen_seeds = set()
    total_steps = 0
    for row in episodes:
        if type(row) is not dict or set(row) != {"scenario_id", "seed", "actions"}:
            raise StudioCurriculumError("exact rule-scenario demonstration envelope required")
        name = row["scenario_id"]
        if type(name) is not str or name not in scenarios:
            raise StudioCurriculumError("unknown or unregistered AI ruleset in corpus")
        seed = row["seed"]
        if type(seed) is not int or seed in seen_seeds:
            raise StudioCurriculumError("each game scenario requires a unique recorded seed")
        seen_seeds.add(seed)
        if seed % len(scenarios) != [
            x["scenario_id"] for x in curriculum["scenarios"]
        ].index(name):
            raise StudioCurriculumError("episode seed differs from actual scenario scheduler")
        if type(row["actions"]) is not list or not 1 <= len(row["actions"]) <= curriculum["max_steps"]:
            raise StudioCurriculumError("game rule episode exceeds authorized replay depth")
        total_steps += len(row["actions"])
        if total_steps > MAX_EXAMPLES:
            raise StudioCurriculumError("actual multi-condition training samples exceed admission")
        source = scenarios[name]["source"]
        verified = build_studio_curriculum(
            source, [{"seed": seed, "actions": row["actions"]}],
            authorized=True, rights_cleared=True,
        )
        entries.append({
            "scenario_id": name,
            "source_digest": verified["source_digest"],
            "recorded": verified,
        })
    if set(row["scenario_id"] for row in entries) != set(scenarios):
        raise StudioCurriculumError("rule curriculum cannot omit baseline or hard circumstances")
    record = {
        "schema_version": RULE_CORPUS_SCHEMA,
        "rule_plan": curriculum,
        "rule_plan_digest": curriculum["digest"],
        "episodes": entries,
        "training_only": True,
        "rights_acknowledged": True,
        "human_validation_not_replaced": True,
        "independent_holdout_supplied": False,
        "production_neural_weights_modified": False,
        "automatic_promotion": False,
    }
    _canonical(record)
    return {**record, "digest": _sha(record)}


def verify_rule_training_corpus(document: object) -> tuple[str, ...]:
    if type(document) is not dict or set(document) != {
        "schema_version", "rule_plan", "rule_plan_digest", "episodes",
        "training_only", "rights_acknowledged",
        "human_validation_not_replaced", "independent_holdout_supplied",
        "production_neural_weights_modified", "automatic_promotion", "digest",
    } or document["schema_version"] != RULE_CORPUS_SCHEMA:
        raise StudioCurriculumError("exact source-bound multi-rule corpus schema required")
    if (document["training_only"] is not True
            or document["rights_acknowledged"] is not True
            or document["human_validation_not_replaced"] is not True
            or document["independent_holdout_supplied"] is not False
            or document["production_neural_weights_modified"] is not False
            or document["automatic_promotion"] is not False):
        raise StudioCurriculumError("AI rule corpus cannot claim independent review or production promotion")
    if _sha({key: value for key,value in document.items() if key != "digest"}) != document["digest"]:
        raise StudioCurriculumError("multi-rule source or evidence digest was changed")
    plan = verify_rule_curriculum(document["rule_plan"])
    if plan["digest"] != document["rule_plan_digest"]:
        raise StudioCurriculumError("multi-rule training plan identity changed")
    entries = document["episodes"]
    if type(entries) is not list or not 2 <= len(entries) <= MAX_RULE_EPISODES:
        raise StudioCurriculumError("multi-rule episodes outside bounded transport")
    reconstructed = build_rule_training_corpus(
        plan,
        [
            {"scenario_id":entry["scenario_id"],
             "seed":entry["recorded"]["episodes"][0]["seed"],
             "actions":entry["recorded"]["episodes"][0]["actions"]}
            for entry in entries
            if type(entry) is dict and type(entry.get("recorded")) is dict
            and type(entry["recorded"].get("episodes")) is list
            and len(entry["recorded"]["episodes"]) == 1
        ],
        authorized=True, rights_cleared=True,
    )
    if reconstructed != document:
        raise StudioCurriculumError("source facts were not independently reproduced for every rule")
    verified_text = []
    scenario_lookup = {row["scenario_id"]: row for row in plan["scenarios"]}
    for entry in reconstructed["episodes"]:
        source = scenario_lookup[entry["scenario_id"]]["source"]
        context = _context(scenario_lookup[entry["scenario_id"]], source)
        checked = verify_studio_curriculum(entry["recorded"])
        verified_text.extend(context + text for text in checked)
    return tuple(verified_text)


def publish_rule_training_corpus(path: Path, document: dict[str, object]) -> str:
    verify_rule_training_corpus(document)
    raw = _canonical(document)
    destination = Path(path).expanduser().absolute()
    if destination.is_symlink() or not destination.parent.is_dir():
        raise StudioCurriculumError("rule corpus target must have existing private parent")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return sha256(raw).hexdigest()


__all__ = [
    "RULE_CORPUS_SCHEMA", "build_rule_training_corpus",
    "verify_rule_training_corpus", "publish_rule_training_corpus",
]
