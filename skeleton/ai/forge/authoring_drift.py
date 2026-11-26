"""Conflict and drift detection for simultaneous authoring passes.

GF-P1-42. Each pass freezes the live canon digest from
``EnvironmentalLedger.canon_digest`` and the live ``SaveState.revision``.
A pass is drifted when either base no longer matches, and a drifted pass
cannot promote. Two fresh passes that write different values for the same
quest id or flag contest that key, and neither is promoted.

``project_patch`` is pure: it returns the next ``SaveState`` and does not
store it. ``AuthoringGate.promote`` assigns that save, on the ledger that
already owns it, only after a named reviewer id is present. Anonymous and
blank reviewers are rejected. An immutable flag edit is rejected. The same
patch id promotes once; a second promotion is a double-submit and leaves
the revision unchanged. Promotion does not enroll a commit actor and does
not call ``EnvironmentalLedger.commit``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Mapping

from skeleton.forge.game_frontier_event_authority import (
    CanonRules,
    EnvironmentalLedger,
    EventAuthorityError,
    SaveState,
)


class AuthoringDriftError(EventAuthorityError):
    def __init__(self, message: str, *, contested_keys: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.contested_keys = contested_keys


def _freeze(mapping: Mapping) -> Mapping:
    return MappingProxyType(dict(sorted(mapping.items())))


def _edits(raw: Mapping, *, label: str, value_type: type) -> Mapping:
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Mapping):
        raise AuthoringDriftError(f"{label} edits must be a mapping")
    cleaned = {}
    for key, value in raw.items():
        if type(key) is not str or not key.strip():
            raise AuthoringDriftError(f"{label} id required")
        if type(value) is not value_type:
            raise AuthoringDriftError(f"{label} {key} value must be {value_type.__name__}")
        cleaned[key] = value
    return _freeze(cleaned)


@dataclass(frozen=True)
class AuthoringPatch:
    """Quest-stage edits, flag edits, and immutable-flag attempts."""

    patch_id: str
    quest_stages: Mapping[str, int] = field(default_factory=dict)
    flags: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.patch_id) is not str or not self.patch_id.strip():
            raise AuthoringDriftError("patch id required")
        object.__setattr__(self, "patch_id", self.patch_id.strip())
        object.__setattr__(self, "quest_stages", _edits(self.quest_stages, label="quest", value_type=int))
        object.__setattr__(self, "flags", _edits(self.flags, label="flag", value_type=bool))


@dataclass(frozen=True)
class AuthoringPass:
    """One authoring pass bound to the canon digest and save revision it saw."""

    base_canon_digest: str
    base_save_revision: int
    patch: AuthoringPatch

    def __post_init__(self) -> None:
        if type(self.base_canon_digest) is not str or not self.base_canon_digest.strip():
            raise AuthoringDriftError("base canon digest required")
        if type(self.base_save_revision) is not int:
            raise AuthoringDriftError("base save revision required")
        if not isinstance(self.patch, AuthoringPatch):
            raise AuthoringDriftError("authoring patch required")


@dataclass(frozen=True)
class AuthoringVerdict:
    patch_id: str
    drifted: bool
    drift_reasons: tuple[str, ...]
    contested_keys: tuple[str, ...]
    contested_quests: tuple[str, ...]
    contested_flags: tuple[str, ...]
    immutable_flags: tuple[str, ...]
    can_promote: bool


@dataclass(frozen=True)
class AuthoringReview:
    verdicts: tuple[AuthoringVerdict, ...]
    contested_keys: tuple[str, ...]
    contested_quests: tuple[str, ...]
    contested_flags: tuple[str, ...]


def live_canon_digest(ledger: EnvironmentalLedger) -> str:
    """The existing ledger digest. This module does not hash canon itself."""
    return ledger.canon_digest()


def live_save_revision(ledger: EnvironmentalLedger) -> int:
    return ledger.state.revision


def capture_pass(ledger: EnvironmentalLedger, patch: AuthoringPatch) -> AuthoringPass:
    return AuthoringPass(live_canon_digest(ledger), live_save_revision(ledger), patch)


def _require_reviewer(reviewer_id: object) -> str:
    if type(reviewer_id) is not str:
        raise AuthoringDriftError("reviewer id required")
    who = reviewer_id.strip()
    if not who:
        raise AuthoringDriftError("reviewer id required")
    if who.casefold() == "anonymous":
        raise AuthoringDriftError("anonymous reviewer rejected")
    return who


def _drift_reasons(candidate: AuthoringPass, digest: str, revision: int) -> tuple[str, ...]:
    reasons = []
    if candidate.base_canon_digest != digest:
        reasons.append("canon_digest")
    if candidate.base_save_revision != revision:
        reasons.append("save_revision")
    return tuple(reasons)


def _drift_message(reasons: tuple[str, ...]) -> str:
    parts = []
    if "canon_digest" in reasons:
        parts.append("canon digest")
    if "save_revision" in reasons:
        parts.append("save revision")
    return "drifted " + " and ".join(parts)


def review_authoring_passes(
    ledger: EnvironmentalLedger,
    passes: tuple[AuthoringPass, ...] | list[AuthoringPass],
) -> AuthoringReview:
    """Classify simultaneous passes. Review does not write the save."""
    ordered = tuple(passes)
    ids = [item.patch.patch_id for item in ordered]
    if len(ids) != len(set(ids)):
        raise AuthoringDriftError("duplicate patch id")
    digest = live_canon_digest(ledger)
    revision = live_save_revision(ledger)
    fresh: list[AuthoringPass] = []
    reasons_of: dict[str, tuple[str, ...]] = {}
    for item in ordered:
        reasons = _drift_reasons(item, digest, revision)
        reasons_of[item.patch.patch_id] = reasons
        if not reasons:
            fresh.append(item)
    quest_values: dict[str, dict[str, int]] = {}
    flag_values: dict[str, dict[str, bool]] = {}
    for item in fresh:
        for quest_id, stage in item.patch.quest_stages.items():
            quest_values.setdefault(quest_id, {})[item.patch.patch_id] = stage
        for flag, value in item.patch.flags.items():
            flag_values.setdefault(flag, {})[item.patch.patch_id] = value
    contested_quests = tuple(
        sorted(quest_id for quest_id, values in quest_values.items() if len(set(values.values())) > 1)
    )
    contested_flags = tuple(
        sorted(flag for flag, values in flag_values.items() if len(set(values.values())) > 1)
    )
    contested_keys = tuple(
        [f"quest:{quest_id}" for quest_id in contested_quests] + [f"flag:{flag}" for flag in contested_flags]
    )
    contested_keys = tuple(sorted(contested_keys))
    by_patch_quests: dict[str, list[str]] = {}
    by_patch_flags: dict[str, list[str]] = {}
    for quest_id in contested_quests:
        for patch_id in quest_values[quest_id]:
            by_patch_quests.setdefault(patch_id, []).append(quest_id)
    for flag in contested_flags:
        for patch_id in flag_values[flag]:
            by_patch_flags.setdefault(patch_id, []).append(flag)
    verdicts = []
    for item in sorted(ordered, key=lambda candidate: candidate.patch.patch_id):
        patch_id = item.patch.patch_id
        reasons = reasons_of[patch_id]
        quests = tuple(sorted(by_patch_quests.get(patch_id, ())))
        flags = tuple(sorted(by_patch_flags.get(patch_id, ())))
        keys = tuple(
            sorted([f"quest:{quest_id}" for quest_id in quests] + [f"flag:{flag}" for flag in flags])
        )
        immutable = tuple(sorted(flag for flag in item.patch.flags if flag in ledger.canon.immutable_flags))
        has_edit = bool(item.patch.quest_stages or item.patch.flags)
        can_promote = not reasons and not keys and not immutable and has_edit
        verdicts.append(
            AuthoringVerdict(
                patch_id,
                bool(reasons),
                reasons,
                keys,
                quests,
                flags,
                immutable,
                can_promote,
            )
        )
    return AuthoringReview(tuple(verdicts), contested_keys, contested_quests, contested_flags)


def project_patch(state: SaveState, canon: CanonRules, patch: AuthoringPatch) -> SaveState:
    """Return the next save for one patch. The live save is not assigned."""
    if not isinstance(patch, AuthoringPatch):
        raise AuthoringDriftError("authoring patch required")
    if not patch.quest_stages and not patch.flags:
        raise AuthoringDriftError("empty authoring patch")
    for flag in patch.flags:
        if flag in canon.immutable_flags:
            raise AuthoringDriftError(f"immutable flag {flag}")
    stages = dict(state.quest_stage)
    for quest_id, index in patch.quest_stages.items():
        quest = canon.quests.get(quest_id)
        if quest is None:
            raise AuthoringDriftError(f"quest {quest_id} not in canon")
        if quest.era_engines and state.era_engine not in quest.era_engines:
            raise AuthoringDriftError(f"quest {quest_id} not in era {state.era_engine}")
        if quest_id in state.completed_quests:
            raise AuthoringDriftError("quest already completed in canon")
        if not 0 <= index < len(quest.stages):
            raise AuthoringDriftError("quest stage out of range")
        stages[quest_id] = index
    flags = dict(state.flags)
    flags.update(patch.flags)
    return replace(
        state,
        flags=_freeze(flags),
        quest_stage=_freeze(stages),
        revision=state.revision + 1,
    )


class AuthoringGate:
    """Hold simultaneous passes against one ledger and promote with a reviewer.

    The ledger's ``SaveState`` is the only save. Submit and review do not
    change it. Promote assigns the object returned by ``project_patch``.
    """

    def __init__(self, ledger: EnvironmentalLedger) -> None:
        if not isinstance(ledger, EnvironmentalLedger):
            raise AuthoringDriftError("environmental ledger required")
        self.ledger = ledger
        self._passes: dict[str, AuthoringPass] = {}
        self._promoted: set[str] = set()

    def hold(self, candidate: AuthoringPass) -> AuthoringPass:
        """Remember a pass that already carries its own base digest and revision."""
        if not isinstance(candidate, AuthoringPass):
            raise AuthoringDriftError("authoring pass required")
        existing = self._passes.get(candidate.patch.patch_id)
        if existing is not None:
            if existing != candidate:
                raise AuthoringDriftError("duplicate patch id")
            return existing
        if candidate.patch.patch_id in self._promoted:
            raise AuthoringDriftError("double-submit")
        revision = live_save_revision(self.ledger)
        digest = live_canon_digest(self.ledger)
        self._passes[candidate.patch.patch_id] = candidate
        if live_save_revision(self.ledger) != revision or live_canon_digest(self.ledger) != digest:
            self._passes.pop(candidate.patch.patch_id, None)
            raise AuthoringDriftError("submit mutated the live save")
        return candidate

    def submit(self, patch: AuthoringPatch) -> AuthoringPass:
        if not isinstance(patch, AuthoringPatch):
            raise AuthoringDriftError("authoring patch required")
        existing = self._passes.get(patch.patch_id)
        if existing is not None:
            if existing.patch != patch:
                raise AuthoringDriftError("duplicate patch id")
            return existing
        return self.hold(capture_pass(self.ledger, patch))

    def passes(self) -> tuple[AuthoringPass, ...]:
        return tuple(self._passes[key] for key in sorted(self._passes))

    def review(self) -> AuthoringReview:
        revision = live_save_revision(self.ledger)
        digest = live_canon_digest(self.ledger)
        report = review_authoring_passes(self.ledger, self.passes())
        if live_save_revision(self.ledger) != revision or live_canon_digest(self.ledger) != digest:
            raise AuthoringDriftError("review mutated the live save")
        return report

    def promote(self, patch_id: str, *, reviewer_id: str) -> SaveState:
        _require_reviewer(reviewer_id)
        if type(patch_id) is not str or not patch_id.strip():
            raise AuthoringDriftError("patch id required")
        patch_id = patch_id.strip()
        if patch_id in self._promoted:
            raise AuthoringDriftError("double-submit")
        candidate = self._passes.get(patch_id)
        if candidate is None:
            raise AuthoringDriftError("unknown authoring patch")
        previous = self.ledger.state
        revision = previous.revision
        digest = live_canon_digest(self.ledger)
        keys = dict(self.ledger.keys)
        try:
            report = review_authoring_passes(self.ledger, self.passes())
            verdict = next(item for item in report.verdicts if item.patch_id == patch_id)
            if verdict.drifted:
                raise AuthoringDriftError(_drift_message(verdict.drift_reasons))
            if verdict.contested_keys:
                raise AuthoringDriftError(
                    "contested keys: " + ", ".join(verdict.contested_keys),
                    contested_keys=verdict.contested_keys,
                )
            if live_canon_digest(self.ledger) != digest or live_save_revision(self.ledger) != revision:
                raise AuthoringDriftError("drifted canon digest and save revision")
            projected = project_patch(self.ledger.state, self.ledger.canon, candidate.patch)
            if self.ledger.state is not previous or live_save_revision(self.ledger) != revision:
                raise AuthoringDriftError("authoring preview mutated the live save")
            if live_canon_digest(self.ledger) != digest:
                raise AuthoringDriftError("authoring preview mutated the live save")
            if dict(self.ledger.keys) != keys:
                raise AuthoringDriftError("authoring promotion enrolled a commit actor")
            self.ledger.state = projected
            self._promoted.add(patch_id)
            if dict(self.ledger.keys) != keys:
                self.ledger.state = previous
                self._promoted.discard(patch_id)
                raise AuthoringDriftError("authoring promotion enrolled a commit actor")
            return self.ledger.state
        except AuthoringDriftError:
            if (
                self.ledger.state is not previous
                or live_save_revision(self.ledger) != revision
                or live_canon_digest(self.ledger) != digest
                or dict(self.ledger.keys) != keys
                or patch_id in self._promoted
            ):
                self.ledger.state = previous
                self._promoted.discard(patch_id)
                raise AuthoringDriftError("rejected authoring pass mutated the live save") from None
            raise
