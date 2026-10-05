"""Governance — charters, edicts, and the decide gate (charter law).

Port of Apeloff1/gameforge-rs ``crates/gf-gameforge/src/governance.rs``.

This is charter/edict law for consequential domains — NOT agent utility
(``agents/policy.py``), NOT organism conductor policy, NOT cognition gates.
Every consequential mutate/submit crosses ``decide``; unchartered domains
fail closed.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Rule:
    """One written rule inside a domain charter."""

    id: str
    action: str
    min_weight: int = 0
    requires_quorum: bool = False


@dataclass
class Charter:
    id: str
    domain: str
    rules: List[Rule] = field(default_factory=list)
    ratified: datetime = field(default_factory=_utcnow)
    amendments: int = 0


@dataclass
class Edict:
    id: str
    charter_id: str
    rule: Rule
    proposed_by: str
    proposed_at: datetime = field(default_factory=_utcnow)
    in_force: bool = False


@dataclass(frozen=True)
class Decision:
    permitted: bool
    cited_rule: Optional[str]
    reason: str


class Governance:
    """Charter-law registry. Thread-safe; fail-closed on missing charters."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._charters: Dict[str, Charter] = {}
        self._edicts: Dict[str, Edict] = {}

    def ratify(self, domain: str, rules: List[Rule]) -> Charter:
        """Ratify a charter for a domain (founding law needs no precedent)."""
        charter = Charter(
            id=str(uuid.uuid4()),
            domain=domain,
            rules=list(rules),
            ratified=_utcnow(),
            amendments=0,
        )
        with self._lock:
            self._charters[domain] = charter
        return charter

    def propose_edict(
        self, charter_domain: str, rule: Rule, proposed_by: str
    ) -> Optional[str]:
        """Propose an amendment held until the court enforces it."""
        with self._lock:
            charter = self._charters.get(charter_domain)
            if charter is None:
                return None
            edict = Edict(
                id=str(uuid.uuid4()),
                charter_id=charter.id,
                rule=rule,
                proposed_by=proposed_by,
                proposed_at=_utcnow(),
                in_force=False,
            )
            self._edicts[edict.id] = edict
            return f"edict:{edict.id}"

    def enforce_edict(self, edict_id: str) -> Optional[bool]:
        """Bring an edict into force after the court decided it."""
        with self._lock:
            edict = self._edicts.get(edict_id)
            if edict is None:
                return None
            if edict.in_force:
                return True
            edict.in_force = True
            charter_id = edict.charter_id
            rule = edict.rule
            for charter in self._charters.values():
                if charter.id == charter_id:
                    charter.rules.append(rule)
                    charter.amendments += 1
                    break
            return True

    def decide(self, domain: str, action: str, actor_weight: int) -> Decision:
        """Charter-law gate. Unchartered domains permit nothing."""
        with self._lock:
            charter = self._charters.get(domain)
            if charter is None:
                return Decision(
                    permitted=False,
                    cited_rule=None,
                    reason=f"no charter ratified for domain '{domain}'",
                )
            match = next((r for r in charter.rules if r.action == action), None)
            if match is None:
                return Decision(
                    permitted=False,
                    cited_rule=None,
                    reason=f"action '{action}' not written into the {domain} charter",
                )
            if actor_weight < match.min_weight:
                return Decision(
                    permitted=False,
                    cited_rule=match.id,
                    reason=(
                        f"actor weight {actor_weight} below required {match.min_weight}"
                    ),
                )
            reason = (
                "permitted by charter; quorum still required"
                if match.requires_quorum
                else "permitted by charter"
            )
            return Decision(permitted=True, cited_rule=match.id, reason=reason)

    def charters(self) -> List[Charter]:
        with self._lock:
            return list(self._charters.values())

    def edicts(self) -> List[Edict]:
        with self._lock:
            return list(self._edicts.values())

    def has_charter(self, domain: str) -> bool:
        with self._lock:
            return domain in self._charters

    def clear(self) -> None:
        """Test helper: wipe all charters/edicts."""
        with self._lock:
            self._charters.clear()
            self._edicts.clear()


# --- process singleton + founding law for forge / swarm mutate routes ---

_FOUNDING_FORGE: List[Rule] = [
    Rule(id="forge.blueprint", action="blueprint", min_weight=0),
    Rule(id="forge.materialise", action="materialise", min_weight=0),
    Rule(id="forge.archetype", action="archetype", min_weight=0),
    Rule(id="forge.run", action="run", min_weight=0),
    Rule(id="forge.intake", action="intake", min_weight=0),
]

_FOUNDING_SWARM: List[Rule] = [
    Rule(id="swarm.submit", action="submit", min_weight=0),
]

_gov: Optional[Governance] = None
_gov_lock = threading.Lock()


def reset_governance(gov: Optional[Governance] = None) -> Governance:
    """Replace the process singleton (tests). None → fresh empty Governance."""
    global _gov
    with _gov_lock:
        _gov = gov if gov is not None else Governance()
        return _gov


def ensure_founding_charters(gov: Governance) -> None:
    """Ratify forge/swarm founding law when missing (idempotent)."""
    if not gov.has_charter("forge"):
        gov.ratify("forge", list(_FOUNDING_FORGE))
    if not gov.has_charter("swarm"):
        gov.ratify("swarm", list(_FOUNDING_SWARM))


def get_governance(*, bootstrap: bool = True) -> Governance:
    """Process-wide governance. Bootstraps founding forge/swarm charters."""
    global _gov
    with _gov_lock:
        if _gov is None:
            _gov = Governance()
        if bootstrap:
            ensure_founding_charters(_gov)
        return _gov
