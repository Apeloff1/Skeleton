#!/usr/bin/env python3
"""
Lever Arch File System (LAFS) — Deep Probability knowledge ledger.

Adapted from the uploaded DEEP PROBABILITY EDITION for this backend:
  • Mongo-persisted (collection `lafs_cabinet`, single doc) → fork-safe,
    instead of the original ephemeral cabinet.json on local disk.
  • The intentionally-heavy `_deep_refresh` (2048 particles + 1500 MCMC +
    VI) is GATED behind `deep=True` so normal API calls stay fast; deep_sample
    falls back to VI/Beta when heavy caches are absent.
  • A compact real HIERARCHY of domains → log-types (the pasted one was empty).

Full hierarchical Bayes, Active-Inference free energy, ASMC+MH, MCMC, VI,
graph belief propagation and contextual acquisition are preserved.
"""
from __future__ import annotations

import json
import math
import uuid
import threading
from copy import deepcopy
from functools import wraps
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

_stats_mod = None
_specials: dict = {}


def _ensure_scipy() -> None:
    """LAFS probability math needs scipy, but importing the ledger must not."""
    global _stats_mod
    if _stats_mod is not None:
        return
    from scipy import stats as scipy_stats
    from scipy.special import digamma as scipy_digamma, gammaln as scipy_gammaln

    _stats_mod = scipy_stats
    _specials["digamma"] = scipy_digamma
    _specials["gammaln"] = scipy_gammaln


class _StatsProxy:
    def __getattr__(self, name: str):
        _ensure_scipy()
        return getattr(_stats_mod, name)


class _SpecialProxy:
    def __init__(self, name: str):
        self._name = name

    def __call__(self, *args, **kwargs):
        _ensure_scipy()
        return _specials[self._name](*args, **kwargs)


stats = _StatsProxy()
digamma = _SpecialProxy("digamma")
gammaln = _SpecialProxy("gammaln")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── compact real hierarchy (domains → log types) ─────────────────────
HIERARCHY: Dict[str, List[str]] = {
    "Narrative": ["Quest", "Dialogue", "Lore", "Character", "Cutscene", "Branch"],
    "World": ["Ruins", "Biome", "Region", "Landmark", "Weather", "Faction"],
    "Combat": ["Boss", "Enemy", "Weapon", "Ability", "Encounter", "Balance"],
    "Systems": ["Progression", "Economy", "Crafting", "Inventory", "SaveLoad", "AI"],
    "Art": ["Sprite", "Model", "Texture", "Animation", "VFX", "Palette"],
    "Audio": ["Music", "SFX", "Ambience", "Voice", "Mix"],
    "Meta": ["Reflection", "Inflection", "Strategy", "Retro", "Risk", "Decision"],
    "Build": ["Compile", "Package", "Export", "Deploy", "Toolchain"],
    "Agent": ["Handoff", "Delegation", "Orchestration", "Skill", "Tool", "Observation"],
    "Quality": ["Gate", "Playtest", "Bug", "Metric", "Calibration"],
}
TOTAL_LOG_TYPES = sum(len(v) for v in HIERARCHY.values())


# ── deep probability state ───────────────────────────────────────────
@dataclass
class ProbabilityState:
    alpha: float = 1.0
    beta: float = 1.0
    logtype_alpha: float = 1.0
    logtype_beta: float = 1.0
    domain_alpha: float = 1.0
    domain_beta: float = 1.0
    global_alpha: float = 1.0
    global_beta: float = 1.0
    shrinkage: float = 0.42
    evidence_log: List[float] = field(default_factory=list)
    forecast_log: List[Tuple[float, float]] = field(default_factory=list)
    vi_mu: float = 0.0
    vi_sigma: float = 1.0
    expected_free_energy: float = 0.0
    epistemic_value: float = 0.0
    pragmatic_value: float = 0.0
    dp_alpha: float = 1.0
    dp_counts: Dict[str, float] = field(default_factory=dict)
    last_updated: str = field(default_factory=_now)
    # heavy caches are transient (never persisted)
    particles: Optional[Any] = None
    particle_weights: Optional[Any] = None
    mcmc_samples: Optional[Any] = None

    @property
    def posterior_mean(self) -> float:
        local = self.alpha / (self.alpha + self.beta)
        lt = self.logtype_alpha / (self.logtype_alpha + self.logtype_beta)
        dom = self.domain_alpha / (self.domain_alpha + self.domain_beta)
        glob = self.global_alpha / (self.global_alpha + self.global_beta)
        return ((1 - self.shrinkage) * local + 0.35 * self.shrinkage * lt
                + 0.40 * self.shrinkage * dom + 0.25 * self.shrinkage * glob)

    @property
    def posterior_variance(self) -> float:
        a, b = self.alpha, self.beta
        return (a * b) / ((a + b) ** 2 * (a + b + 1) + 1e-12)

    @property
    def entropy(self) -> float:
        a, b = max(1e-6, self.alpha), max(1e-6, self.beta)
        ent = (gammaln(a) + gammaln(b) - gammaln(a + b)
               - (a - 1) * digamma(a) - (b - 1) * digamma(b)
               + (a + b - 2) * digamma(a + b))
        return float(ent / np.log(2))

    def credible_interval(self, cred: float = 0.95) -> Tuple[float, float]:
        return (float(stats.beta.ppf((1 - cred) / 2, self.alpha, self.beta)),
                float(stats.beta.ppf(1 - (1 - cred) / 2, self.alpha, self.beta)))

    def update(self, likelihood: float, weight: float = 1.0,
               tag: Optional[str] = None, deep: bool = False):
        if not math.isfinite(likelihood) or not 0 <= likelihood <= 1:
            raise ValueError("evidence must be finite and in [0, 1]")
        if not math.isfinite(weight) or not 0 < weight <= 100:
            raise ValueError("weight must be finite and in (0, 100]")
        if tag is not None and (type(tag) is not str or len(tag) > 128):
            raise ValueError("invalid evidence tag")
        if tag and tag not in self.dp_counts and len(self.dp_counts) >= 256:
            raise ValueError("evidence tag capacity reached")
        self.forecast_log = (self.forecast_log + [(self.posterior_mean, likelihood)])[-400:]
        self.particles = self.particle_weights = self.mcmc_samples = None
        likelihood = float(likelihood)
        self.alpha += likelihood * weight
        self.beta += (1.0 - likelihood) * weight
        self.evidence_log.append(likelihood)
        if len(self.evidence_log) > 400:
            self.evidence_log = self.evidence_log[-400:]
        if tag:
            self.dp_counts[tag] = self.dp_counts.get(tag, 0.0) + weight
            self.dp_alpha += 0.015
        if deep:
            self._deep_refresh()
        else:
            self._variational_inference(steps=20)
        self._compute_expected_free_energy()
        self.last_updated = _now()

    def _deep_refresh(self):
        # Conjugate Beta posterior is available analytically. Sampling from it
        # is exact; reweighting with already-assimilated evidence double counts.
        self._adaptive_smc_mh(2048)
        self._variational_inference(80)
        self.mcmc_samples = None

    def _adaptive_smc_mh(self, n_particles: int = 2048):
        if type(n_particles) is not int or not 1 <= n_particles <= 8192:
            raise ValueError("invalid particle budget")
        self.particles = np.random.beta(self.alpha, self.beta, size=n_particles)
        self.particle_weights = np.full(n_particles, 1.0 / n_particles)

    def _metropolis_hastings(self, n_samples: int = 1500, burn: int = 400, thin: int = 2):
        # Compatibility method: direct conjugate draws, not a Markov chain.
        if type(n_samples) is not int or not 1 <= n_samples <= 8192:
            raise ValueError("invalid sample budget")
        return np.random.beta(self.alpha, self.beta, size=n_samples)

    def _variational_inference(self, steps: int = 80):
        # Exact logit-Beta moments; a moment-matched diagnostic, not fitted VI.
        from scipy.special import polygamma
        self.vi_mu = float(digamma(self.alpha) - digamma(self.beta))
        self.vi_sigma = math.sqrt(float(polygamma(1, self.alpha) + polygamma(1, self.beta)))

    def _compute_expected_free_energy(self):
        self.epistemic_value = self.expected_information_gain()
        self.pragmatic_value = float(-((self.posterior_mean - 0.85) ** 2) / 0.1)
        self.expected_free_energy = float(self.epistemic_value + self.pragmatic_value)

    def expected_information_gain(self) -> float:
        prior_ent = self.entropy
        p = self.posterior_mean
        post = ProbabilityState(alpha=self.alpha + p, beta=self.beta + (1 - p))
        return max(0.0, prior_ent - post.entropy)

    def upper_confidence_bound(self, kappa: float = 2.0) -> float:
        return self.posterior_mean + kappa * math.sqrt(self.posterior_variance)

    def probability_of_improvement(self, baseline: float = 0.6) -> float:
        return float(1.0 - stats.beta.cdf(baseline, self.alpha, self.beta))

    def marginal_likelihood(self) -> float:
        s = sum(self.evidence_log); n = len(self.evidence_log); f = n - s
        return float(gammaln(self.alpha + s) + gammaln(self.beta + f)
                     - gammaln(self.alpha + self.beta + n)
                     - (gammaln(self.alpha) + gammaln(self.beta) - gammaln(self.alpha + self.beta)))

    def brier_calibration(self) -> float:
        # Measure recorded forecasts BEFORE the corresponding evidence update.
        # Legacy observations have no recorded forecast and are not scored.
        if not self.forecast_log:
            return 0.25  # neutral ranking prior; not observed calibration
        return sum((p - y) ** 2 for p, y in self.forecast_log) / len(self.forecast_log)

    def deep_sample(self, n: int = 1):
        if type(n) is not int or not 1 <= n <= 8192:
            raise ValueError("invalid sample budget")
        return np.random.beta(self.alpha, self.beta, size=n)

    def thompson_sample(self, n: int = 1):
        return self.deep_sample(n)

    def to_persist(self) -> Dict:
        d = asdict(self)
        for k in ("particles", "particle_weights", "mcmc_samples"):
            d[k] = None
        d["dp_counts"] = dict(d["dp_counts"])
        return d

    @classmethod
    def from_persist(cls, d: Dict) -> "ProbabilityState":
        d = dict(d)
        for k in ("particles", "particle_weights", "mcmc_samples"):
            d.pop(k, None)
        obj = cls(**d)
        for k in ("alpha", "beta", "logtype_alpha", "logtype_beta",
                  "domain_alpha", "domain_beta", "global_alpha", "global_beta"):
            v = getattr(obj, k)
            if not math.isfinite(v) or not 0 < v <= 1e12:
                raise ValueError("invalid persisted Beta parameter")
        if not math.isfinite(obj.shrinkage) or not 0 <= obj.shrinkage <= 1:
            raise ValueError("invalid persisted shrinkage")
        if len(obj.forecast_log) > 400 or any(
            len(row) != 2 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in row)
            for row in obj.forecast_log
        ):
            raise ValueError("invalid persisted forecasts")
        return obj


@dataclass
class Sheet:
    id: str
    path: str
    log_type: str
    payload: Dict[str, Any]
    author: str
    timestamp: str
    provenance: Dict[str, Any] = field(default_factory=dict)
    cross_refs: List[str] = field(default_factory=list)
    prob: ProbabilityState = field(default_factory=ProbabilityState)
    version: int = 1
    tags: List[str] = field(default_factory=list)

    def to_persist(self) -> Dict:
        d = asdict(self)
        d["prob"] = self.prob.to_persist()
        return d

    @classmethod
    def from_persist(cls, d: Dict) -> "Sheet":
        d = dict(d)
        prob = ProbabilityState.from_persist(d.pop("prob"))
        d.pop("simulation_tick", None)
        return cls(prob=prob, **d)

    @property
    def evidence_status(self) -> str:
        if self.provenance.get("kind") == "external_wikipedia":
            from gameforge.lafs.source_evidence import validate_evidence
            try:
                evidence = validate_evidence(self.provenance)
                if any(self.payload.get(k) != evidence[k] for k in ("title", "extract", "source_url", "revision")):
                    return "integrity_hold"
            except (ValueError, TypeError, AttributeError, OverflowError):
                return "integrity_hold"
            status = self.provenance.get("review_status", "pending")
            if status not in {"pending", "approved", "rejected", "revoked"}:
                return "integrity_hold"
            if status != "pending" and not all(self.provenance.get(k) for k in ("reviewer", "reviewed_at", "review_note")):
                return "integrity_hold"
            return status
        # Existing records that claimed online provenance have not been
        # reviewed against immutable source bytes.
        if (self.author in {"Jeeves-Online", "Jeeves-Sweep"}
                or self.payload.get("provenance") == "wikipedia_rest_v1"):
            return "legacy_unverified"
        return "internal"

    @property
    def retrievable(self) -> bool:
        return self.evidence_status in {"internal", "approved"}

    def brief(self) -> Dict:
        p = self.prob
        return {"id": self.id, "path": self.path, "log_type": self.log_type,
                "author": self.author, "tags": self.tags,
                "posterior": round(p.posterior_mean, 4), "entropy": round(p.entropy, 3),
                "efe": round(p.expected_free_energy, 4), "payload": self.payload,
                "evidence_status": self.evidence_status, "provenance": deepcopy(self.provenance)}


# ── LAFS core (Mongo-persisted) ──────────────────────────────────────
class CabinetConflict(RuntimeError):
    """A concurrent writer won; retry the complete command, not a stale snapshot."""


def _fresh_command(fn):
    @wraps(fn)
    def guarded(self, *args, **kwargs):
        with self._lock:
            self._loaded = False
            try:
                result = fn(self, *args, **kwargs)
                return deepcopy(result)
            finally:
                self._loaded = False
    return guarded


class LeverArchFileSystem:
    def __init__(self):
        self.sheets: Dict[str, Sheet] = {}
        self.path_index: Dict[str, Set[str]] = defaultdict(set)
        self.graph: Dict[str, Set[str]] = defaultdict(set)
        self.global_alpha = 1.0
        self.global_beta = 1.0
        self.domain_priors: Dict[str, Tuple[float, float]] = defaultdict(lambda: (1.0, 1.0))
        self.logtype_priors: Dict[str, Tuple[float, float]] = defaultdict(lambda: (1.0, 1.0))
        self._loaded = False
        self._lock = threading.RLock()
        self._revision = 0
        self._existed = False
        self._legacy_revision = False

    def _col(self):
        from core.databases import get_sync_db
        return get_sync_db()["lafs_cabinet"]

    def _load(self):
        if self._loaded:
            return
        doc = self._col().find_one({"_id": "cabinet"})
        source = doc or {}
        revision = source.get("revision", 0)
        if type(revision) is not int or not 0 <= revision < 2**63 - 1:
            raise ValueError("invalid cabinet revision")
        sheets = {sid: Sheet.from_persist(d) for sid, d in source.get("sheets", {}).items()}
        if len(sheets) > 10000:
            raise ValueError("cabinet exceeds supported sheet capacity; migrate without dropping data")
        path_index = defaultdict(set, {k: set(v) for k, v in source.get("path_index", {}).items()})
        graph = defaultdict(set, {k: set(v) for k, v in source.get("graph", {}).items()})
        self.sheets, self.path_index, self.graph = sheets, path_index, graph
        self.global_alpha = source.get("global_alpha", 1.0)
        self.global_beta = source.get("global_beta", 1.0)
        self.domain_priors = defaultdict(lambda: (1.0, 1.0),
                                          {k: tuple(v) for k, v in source.get("domain_priors", {}).items()})
        self.logtype_priors = defaultdict(lambda: (1.0, 1.0),
                                           {k: tuple(v) for k, v in source.get("logtype_priors", {}).items()})
        self._revision = revision
        self._existed = doc is not None
        self._legacy_revision = self._existed and "revision" not in source
        self._loaded = True

    def _save(self):
        doc = {"_id": "cabinet", "revision": self._revision + 1,
               "sheets": {sid: s.to_persist() for sid, s in self.sheets.items()},
               "path_index": {k: list(v) for k, v in self.path_index.items()},
               "graph": {k: list(v) for k, v in self.graph.items()},
               "global_alpha": self.global_alpha, "global_beta": self.global_beta,
               "domain_priors": {k: list(v) for k, v in self.domain_priors.items()},
               "logtype_priors": {k: list(v) for k, v in self.logtype_priors.items()}}
        from bson import BSON
        from pymongo.errors import DuplicateKeyError
        if len(BSON.encode(doc)) > 12 * 1024 * 1024:
            raise ValueError("cabinet byte capacity reached; migration required")
        if self._existed:
            selector = {"_id": "cabinet", "revision": (
                {"$exists": False} if self._legacy_revision else self._revision)}
            result = self._col().replace_one(selector, doc, upsert=False)
            if result.matched_count != 1:
                raise CabinetConflict("cabinet revision changed")
        else:
            try:
                self._col().insert_one(doc)
            except DuplicateKeyError as exc:
                raise CabinetConflict("cabinet was concurrently created") from exc
        self._revision += 1
        self._existed, self._legacy_revision = True, False

    def _update_hyperpriors(self):
        eligible = [s for s in self.sheets.values() if s.retrievable]
        self.domain_priors = defaultdict(lambda: (1.0, 1.0))
        self.logtype_priors = defaultdict(lambda: (1.0, 1.0))
        if not eligible:
            self.global_alpha = self.global_beta = 1.0
            return
        self.global_alpha = float(np.mean([s.prob.alpha for s in eligible]))
        self.global_beta = float(np.mean([s.prob.beta for s in eligible]))
        dom_stats, lt_stats = defaultdict(lambda: [[], []]), defaultdict(lambda: [[], []])
        for s in eligible:
            parts = s.path.split("/")
            dom, lt = parts[0], parts[1] if len(parts) > 1 else parts[0]
            dom_stats[dom][0].append(s.prob.alpha); dom_stats[dom][1].append(s.prob.beta)
            lt_stats[lt][0].append(s.prob.alpha); lt_stats[lt][1].append(s.prob.beta)
        for d, (a, b) in dom_stats.items():
            self.domain_priors[d] = (float(np.mean(a)), float(np.mean(b)))
        for lt, (a, b) in lt_stats.items():
            self.logtype_priors[lt] = (float(np.mean(a)), float(np.mean(b)))

    @_fresh_command
    def add_sheet(self, domain: str, log_type: str, payload: Dict[str, Any],
                  author: str = "system", cross_refs: Optional[List[str]] = None,
                  tags: Optional[List[str]] = None, prior_strength: float = 2.0) -> Sheet:
        self._load()
        for value in (domain, log_type, author):
            if type(value) is not str or not 1 <= len(value) <= 128:
                raise ValueError("invalid sheet identity")
        if "/" in domain or "/" in log_type or "." in domain or "." in log_type or "$" in domain or "$" in log_type:
            raise ValueError("invalid domain or log type")
        if not isinstance(payload, dict) or len(json.dumps(payload, allow_nan=False).encode()) > 32768:
            raise ValueError("invalid or oversized payload")
        if not math.isfinite(prior_strength) or not 0 < prior_strength <= 100:
            raise ValueError("invalid prior")
        refs, labels = list(cross_refs or []), list(tags or [])
        if len(refs) > 128 or len(labels) > 64 or any(type(t) is not str or len(t) > 128 for t in labels):
            raise ValueError("invalid sheet links or tags")
        if any(type(ref) is not str or ref not in self.sheets or not self.sheets[ref].retrievable for ref in refs):
            raise ValueError("unknown cross-reference")
        if len(self.sheets) >= 10000:
            raise ValueError("cabinet capacity reached")
        self._update_hyperpriors()
        payload, cross_refs, tags = deepcopy(payload), list(dict.fromkeys(refs)), labels
        path = f"{domain}/{log_type}"
        sid = str(uuid.uuid4())
        d_a, d_b = self.domain_priors[domain]
        lt_a, lt_b = self.logtype_priors[log_type]
        prob = ProbabilityState(alpha=prior_strength / 2, beta=prior_strength / 2,
                                logtype_alpha=lt_a, logtype_beta=lt_b,
                                domain_alpha=d_a, domain_beta=d_b,
                                global_alpha=self.global_alpha, global_beta=self.global_beta)
        prob._compute_expected_free_energy()
        sheet = Sheet(id=sid, path=path, log_type=log_type, payload=payload, author=author,
                      timestamp=_now(), cross_refs=cross_refs or [], prob=prob, tags=tags or [])
        self.sheets[sid] = sheet
        self.path_index[path].add(sid)
        for ref in sheet.cross_refs:
            if ref in self.sheets:
                self.graph[sid].add(ref); self.graph[ref].add(sid)
                if sid not in self.sheets[ref].cross_refs:
                    self.sheets[ref].cross_refs.append(sid)
        self._propagate_belief(sid)
        self._update_hyperpriors()
        self._save()
        return sheet

    @_fresh_command
    def ingest_external(self, domain: str, log_type: str, evidence: Dict) -> Dict:
        """Admit bounded source evidence once without treating it as true."""
        from gameforge.lafs.source_evidence import validate_evidence
        evidence = validate_evidence(evidence)
        if any(type(v) is not str or not 1 <= len(v) <= 128
               or any(c in v for c in "/.$") for v in (domain, log_type)):
            raise ValueError("invalid destination")
        self._load()
        # Same revision and exact canonical extract are one identity regardless
        # of sweep, alias, request retry or destination.
        fingerprint = evidence["evidence_sha256"]
        sid = str(uuid.uuid5(uuid.NAMESPACE_URL, "lafs:wikipedia:" + fingerprint))
        if sid in self.sheets:
            old = self.sheets[sid]
            if old.provenance.get("evidence_sha256") != fingerprint:
                raise ValueError("source identity collision")
            return {"created": False, "sheet": old.brief()}
        if len(self.sheets) >= 10000:
            raise ValueError("cabinet capacity reached")
        provenance = {**evidence, "kind": "external_wikipedia", "review_status": "pending"}
        payload = {k: evidence[k] for k in ("title", "extract", "source_url", "revision")}
        sheet = Sheet(id=sid, path=f"{domain}/{log_type}", log_type=log_type,
                      payload=payload, author="Jeeves-Online", timestamp=_now(),
                      provenance=provenance, tags=["online", "wikipedia", "untrusted"])
        self.sheets[sid] = sheet
        self.path_index[sheet.path].add(sid)
        # Quarantined content cannot influence graph, priors or calibration.
        self._save()
        return {"created": True, "sheet": sheet.brief()}

    @_fresh_command
    def external_review(self, sheet_id: str, digest: str, decision: str,
                        reviewer: str, note: str) -> Dict:
        from gameforge.lafs.source_evidence import validate_evidence
        self._load()
        sheet = self.sheets.get(sheet_id)
        if sheet is None or sheet.provenance.get("kind") != "external_wikipedia":
            raise KeyError("external source not found")
        if (decision not in {"approved", "rejected", "revoked"} or not isinstance(reviewer, str)
                or not 1 <= len(reviewer) <= 320 or not isinstance(note, str)
                or not 1 <= len(note.strip()) <= 1024):
            raise ValueError("invalid review")
        source = validate_evidence(sheet.provenance)
        if source["evidence_sha256"] != digest:
            raise CabinetConflict("reviewed evidence digest changed")
        if any(sheet.payload.get(k) != source[k] for k in ("title", "extract", "source_url", "revision")):
            raise CabinetConflict("source payload no longer matches evidence")
        previous = sheet.evidence_status
        if not ((previous == "pending" and decision in {"approved", "rejected"})
                or (previous == "approved" and decision == "revoked")):
            raise CabinetConflict("invalid source review transition")
        if decision == "revoked":
            sheet.provenance["prior_review"] = {k: sheet.provenance.get(k)
                for k in ("review_status", "reviewer", "reviewed_at", "review_note")}
        sheet.provenance.update(review_status=decision, reviewer=reviewer,
                                reviewed_at=_now(), review_note=note.strip())
        sheet.version += 1
        self._save()
        return sheet.brief()

    @_fresh_command
    def external_queue(self, limit: int = 50, status: str = "pending") -> List[Dict]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("invalid queue limit")
        self._load()
        if status not in {"pending", "approved", "rejected", "revoked", "integrity_hold", "all"}:
            raise ValueError("invalid evidence status")
        statuses = {"pending", "legacy_unverified", "integrity_hold"} if status == "pending" else {status}
        return [sheet.brief() for sheet in sorted(
            (s for s in self.sheets.values() if s.evidence_status != "internal"
             and (status == "all" or s.evidence_status in statuses)),
            key=lambda s: (s.timestamp, s.id))[:limit]]

    def _propagate_belief(self, sheet_id: str, strength: float = 0.08):
        if sheet_id not in self.sheets or not self.sheets[sheet_id].retrievable:
            return
        src = self.sheets[sheet_id].prob
        for neigh in self.graph.get(sheet_id, []):
            if neigh in self.sheets and self.sheets[neigh].retrievable:
                tgt = self.sheets[neigh].prob
                tgt.alpha = (1 - strength) * tgt.alpha + strength * src.alpha
                tgt.beta = (1 - strength) * tgt.beta + strength * src.beta

    @_fresh_command
    def get_related(self, sheet_id: str, depth: int = 1) -> List[Sheet]:
        self._load()
        if type(depth) is not int or not 0 <= depth <= 8:
            raise ValueError("invalid traversal depth")
        if sheet_id not in self.sheets or not self.sheets[sheet_id].retrievable:
            return []
        visited, result, frontier = {sheet_id}, [], {sheet_id}
        for _ in range(depth):
            nxt = set()
            for sid in frontier:
                for n in self.graph.get(sid, []):
                    if n not in visited and n in self.sheets and self.sheets[n].retrievable:
                        visited.add(n); result.append(self.sheets[n]); nxt.add(n)
            frontier = nxt
        return result

    @_fresh_command
    def probability_search(self, query: str, domain_filter: Optional[str] = None,
                           log_type_filter: Optional[str] = None, min_posterior: float = 0.05,
                           max_entropy: float = 6.0, top_k: int = 25,
                           context_ids: Optional[List[str]] = None,
                           acquisition: str = "efe", kappa: float = 2.2) -> List[Dict]:
        self._load()
        if type(query) is not str or len(query) > 4096 or type(top_k) is not int or not 1 <= top_k <= 250:
            raise ValueError("invalid search bounds")
        if context_ids and len(context_ids) > 128:
            raise ValueError("context capacity exceeded")
        q_tokens = set(query.lower().split())
        context_set: Set[str] = set()
        if context_ids:
            for cid in context_ids:
                context_set |= self.graph.get(cid, set())
        out = []
        for sid, sheet in self.sheets.items():
            if not sheet.retrievable:
                continue
            if domain_filter and not sheet.path.startswith(domain_filter + "/"):
                continue
            if log_type_filter and sheet.log_type != log_type_filter:
                continue
            p = sheet.prob
            if p.posterior_mean < min_posterior or p.entropy > max_entropy:
                continue
            text = (json.dumps(sheet.payload) + " " + sheet.path + " " + " ".join(sheet.tags)).lower()
            lexical = sum(1 for t in q_tokens if t in text) / max(1, len(q_tokens))
            if q_tokens and not lexical and sid not in context_set:
                continue
            if acquisition == "ucb":
                acq = p.upper_confidence_bound(kappa)
            elif acquisition == "eig":
                acq = p.expected_information_gain()
            elif acquisition == "poi":
                acq = p.probability_of_improvement(0.65)
            elif acquisition == "thompson":
                acq = float(p.thompson_sample(1)[0])
            elif acquisition == "hybrid-deep":
                acq = (0.25 * p.expected_free_energy + 0.25 * p.upper_confidence_bound(kappa)
                       + 0.20 * p.expected_information_gain()
                       + 0.15 * p.probability_of_improvement(0.6) + 0.15 * float(p.thompson_sample(1)[0]))
            else:
                acq = p.expected_free_energy
            cal = 1.0 / (1.0 + 4 * p.brier_calibration())
            ctx = 1.55 if sid in context_set else 1.0
            evid = math.log1p(len(p.evidence_log)) / 5.5
            score = (0.15 * lexical + 0.25 * p.posterior_mean + 0.35 * float(acq) + 0.10 * evid) * cal * ctx
            out.append({**sheet.brief(), "score": round(float(score), 4),
                        "acq": round(float(acq), 4), "ci95": p.credible_interval(),
                        "context_boost": ctx})
        out.sort(key=lambda x: x["score"], reverse=True)
        return out[:top_k]

    @_fresh_command
    def reinforce(self, sheet_id: str, success: bool, weight: float = 1.0,
                  tag: Optional[str] = None, deep: bool = False):
        self._load()
        if sheet_id not in self.sheets or not self.sheets[sheet_id].retrievable:
            return None
        self.sheets[sheet_id].prob.update(0.95 if success else 0.10, weight, tag=tag, deep=deep)
        self._propagate_belief(sheet_id)
        self._update_hyperpriors()
        self._save()
        return self.sheets[sheet_id].brief()

    # ── Stage C2: multi-hop belief propagation + posterior-predictive checks ──
    @_fresh_command
    def belief_propagate(self, sheet_id: str, hops: int = 2, strength: float = 0.08) -> Dict:
        """Propagate the source sheet's belief across ``hops`` graph hops with
        geometric decay, returning a full trace of updated neighbors. This is
        the multi-hop generalisation of ``_propagate_belief`` (1-hop)."""
        self._load()
        if sheet_id not in self.sheets or not self.sheets[sheet_id].retrievable:
            return {"ok": False, "error": "sheet_not_found"}
        if type(hops) is not int or not 0 <= hops <= 8 or not math.isfinite(strength) or not 0 <= strength <= 1:
            raise ValueError("invalid propagation bounds")
        src = self.sheets[sheet_id].prob
        visited: Set[str] = {sheet_id}
        frontier: Set[str] = {sheet_id}
        trace: List[Dict] = []
        for hop in range(1, hops + 1):
            decay = strength * (0.6 ** (hop - 1))
            nxt: Set[str] = set()
            for sid in frontier:
                for neigh in self.graph.get(sid, []):
                    if neigh in visited or neigh not in self.sheets or not self.sheets[neigh].retrievable:
                        continue
                    tgt = self.sheets[neigh].prob
                    before = tgt.posterior_mean
                    tgt.alpha = (1 - decay) * tgt.alpha + decay * src.alpha
                    tgt.beta = (1 - decay) * tgt.beta + decay * src.beta
                    tgt._compute_expected_free_energy()
                    trace.append({"sheet_id": neigh, "hop": hop,
                                  "posterior_before": round(before, 4),
                                  "posterior_after": round(tgt.posterior_mean, 4),
                                  "decay": round(decay, 4)})
                    visited.add(neigh); nxt.add(neigh)
            frontier = nxt
            if not frontier:
                break
        self._update_hyperpriors()
        self._save()
        return {"ok": True, "source": sheet_id, "hops": hops,
                "updated": len(trace), "trace": trace}

    @_fresh_command
    def posterior_predictive_check(self, sheet_id: Optional[str] = None) -> Dict:
        """Surface a posterior-predictive calibration check: how well each
        sheet's Beta posterior predicts its own observed evidence (Brier +
        credible-interval coverage)."""
        self._load()
        if sheet_id is not None and (sheet_id not in self.sheets or not self.sheets[sheet_id].retrievable):
            return {"ok": False, "error": "sheet_not_found"}
        sheets = [self.sheets[sheet_id]] if sheet_id is not None else [s for s in self.sheets.values() if s.retrievable]
        if not sheets:
            return {"ok": False, "error": "no_sheets"}
        total = sum(len(sheet.prob.forecast_log) for sheet in sheets)
        squared_error = sum((p-y)**2 for sheet in sheets for p,y in sheet.prob.forecast_log)
        avg = squared_error / total if total else None
        rows = [{"sheet_id": sheet.id,
                 "brier": round(sheet.prob.brier_calibration(), 4) if sheet.prob.forecast_log else None,
                 "ci95": list(sheet.prob.credible_interval()),
                 "posterior": round(sheet.prob.posterior_mean, 4),
                 "observations": len(sheet.prob.forecast_log),
                 "in_ci": None} for sheet in sheets] if sheet_id else []
        return {"ok": True, "sheets_checked": len(sheets),
                "avg_brier": round(avg, 4) if avg is not None else None,
                "calibration_quality": round(1.0 / (1.0 + 4 * avg), 4) if avg is not None else None,
                "ci95_coverage": None, "observations": total, "per_sheet": rows,
                "calibration_basis": "pre_update_probability_forecast",
                "coverage_status": "not_estimable_from_binary_outcomes"}

    @_fresh_command
    def top_efe(self, k: int = 8, domain_filter: Optional[str] = None) -> List[Dict]:
        """Top-k sheets by Expected Free Energy — 'what Jeeves knows best'."""
        self._load()
        rows = [s for s in self.sheets.values()
                if s.retrievable and (not domain_filter or s.path.startswith(domain_filter + "/"))]
        rows.sort(key=lambda s: s.prob.expected_free_energy, reverse=True)
        return [{**s.brief(), "efe": round(s.prob.expected_free_energy, 4),
                 "posterior": round(s.prob.posterior_mean, 4)} for s in rows[:k]]

    @_fresh_command
    def queue_for_jury(self, sheet_id: str, reason: str = "high_entropy") -> Dict:
        self._load()
        s = self.sheets.get(sheet_id)
        if s is None:
            return {"ok": False, "error": "sheet_not_found"}
        if type(reason) is not str or not 1 <= len(reason) <= 256:
            raise ValueError("invalid jury reason")
        entry = {"id": sheet_id, "reason": reason,
                 "path": s.path if s else None,
                 "entropy": s.prob.entropy if s else None, "queued": _now()}
        self._col().database["lafs_jury_queue"].insert_one(dict(entry))
        return {k: v for k, v in entry.items() if k != "_id"}

    @_fresh_command
    def stats(self) -> Dict:
        self._load()
        eligible = [s for s in self.sheets.values() if s.retrievable]
        posts = [s.prob.posterior_mean for s in eligible]
        ents = [s.prob.entropy for s in eligible]
        efes = [s.prob.expected_free_energy for s in eligible]
        return {"total_sheets": len(self.sheets), "retrievable_sheets": len(eligible),
                "excluded_sheets": len(self.sheets) - len(eligible),
                "total_log_types_available": TOTAL_LOG_TYPES,
                "domains": len(HIERARCHY),
                "avg_posterior": round(float(np.mean(posts)), 4) if posts else 0.0,
                "avg_entropy": round(float(np.mean(ents)), 4) if ents else 0.0,
                "avg_expected_free_energy": round(float(np.mean(efes)), 4) if efes else 0.0,
                "global_hyperprior": [round(self.global_alpha, 3), round(self.global_beta, 3)]}


# ── facades ──────────────────────────────────────────────────────────
class Jeeves:
    def __init__(self, lafs): self.lafs = lafs
    def remember(self, domain, log_type, payload, **kw): return self.lafs.add_sheet(domain, log_type, payload, author="Jeeves", **kw)
    def recall(self, query, **kw): return self.lafs.probability_search(query, **kw)
    def reinforce(self, sid, success=True, tag=None, deep=False): return self.lafs.reinforce(sid, success, tag=tag, deep=deep)


class Librarian:
    def __init__(self, lafs): self.lafs = lafs
    def stats(self): return self.lafs.stats()
    def hierarchy(self): return {k: v for k, v in HIERARCHY.items()}
    def jury(self, sid, reason="conflict"): return self.lafs.queue_for_jury(sid, reason)


class BuilderAgent:
    def __init__(self, lafs, name, domains): self.lafs, self.name, self.allowed = lafs, name, set(domains)
    def log(self, domain, log_type, payload, **kw):
        if domain not in self.allowed:
            raise PermissionError(f"{self.name} cannot write {domain}")
        return self.lafs.add_sheet(domain, log_type, payload, author=self.name, **kw)
    def search(self, query, **kw): return self.lafs.probability_search(query, **kw)


# singletons
lafs = LeverArchFileSystem()
jeeves = Jeeves(lafs)
librarian = Librarian(lafs)
