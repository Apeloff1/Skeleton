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
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from scipy import stats
from scipy.special import digamma, gammaln


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
        likelihood = float(np.clip(likelihood, 1e-6, 1 - 1e-6))
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
        self._adaptive_smc_mh(2048)
        self._variational_inference(80)
        self.mcmc_samples = self._metropolis_hastings(1500, 400)

    def _adaptive_smc_mh(self, n_particles: int = 2048):
        if not self.evidence_log:
            self.particles = stats.beta.rvs(self.alpha, self.beta, size=n_particles)
            self.particle_weights = np.ones(n_particles) / n_particles
            return
        particles = stats.beta.rvs(self.alpha, self.beta, size=n_particles)
        weights = np.ones(n_particles)
        for lik in self.evidence_log[-120:]:
            weights *= stats.beta.pdf(particles, 1 + lik, 1 + (1 - lik)) + 1e-300
            weights /= weights.sum() + 1e-300
            ess = 1.0 / (np.sum(weights ** 2) + 1e-300)
            if ess < n_particles * 0.35:
                idx = np.searchsorted(np.cumsum(weights),
                                      (np.arange(n_particles) + np.random.random()) / n_particles)
                idx = np.clip(idx, 0, n_particles - 1)
                particles = particles[idx]
                weights.fill(1.0 / n_particles)
                for _ in range(3):
                    prop = np.clip(particles + np.random.normal(0, 0.04, n_particles), 1e-6, 1 - 1e-6)
                    log_r = (stats.beta.logpdf(prop, self.alpha, self.beta)
                             - stats.beta.logpdf(particles, self.alpha, self.beta))
                    accept = np.log(np.random.random(n_particles)) < log_r
                    particles = np.where(accept, prop, particles)
        self.particles = particles
        self.particle_weights = weights

    def _metropolis_hastings(self, n_samples: int = 1500, burn: int = 400, thin: int = 2):
        samples, current = [], self.posterior_mean
        for i in range(n_samples + burn):
            prop = float(np.clip(current + np.random.normal(0, 0.08), 1e-6, 1 - 1e-6))
            log_r = (stats.beta.logpdf(prop, self.alpha, self.beta)
                     - stats.beta.logpdf(current, self.alpha, self.beta))
            if np.log(np.random.random()) < log_r:
                current = prop
            if i >= burn and (i - burn) % thin == 0:
                samples.append(current)
        return np.array(samples)

    def _variational_inference(self, steps: int = 80):
        mu = np.log(self.posterior_mean / (1 - self.posterior_mean + 1e-12))
        sigma = 0.8
        for _ in range(steps):
            samples = mu + sigma * np.random.randn(64)
            p = 1 / (1 + np.exp(-samples))
            log_p = stats.beta.logpdf(np.clip(p, 1e-6, 1 - 1e-6), self.alpha, self.beta)
            grad_mu = np.mean((log_p - samples) * (p * (1 - p)))
            grad_sigma = np.mean((log_p - samples) * ((samples - mu) / sigma)) - 1 / sigma
            mu += 0.05 * grad_mu
            sigma = max(0.05, sigma + 0.03 * grad_sigma)
        self.vi_mu, self.vi_sigma = float(mu), float(sigma)

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
        if len(self.evidence_log) < 2:
            return 0.25
        preds = np.full(len(self.evidence_log), self.posterior_mean)
        return float(np.mean((preds - np.asarray(self.evidence_log)) ** 2))

    def deep_sample(self, n: int = 1):
        if self.mcmc_samples is not None and len(self.mcmc_samples) > 10:
            return np.random.choice(self.mcmc_samples, size=n)
        if self.particles is not None:
            idx = np.random.choice(len(self.particles), size=n, p=self.particle_weights)
            return self.particles[idx]
        logit = self.vi_mu + self.vi_sigma * np.random.randn(n)
        return 1 / (1 + np.exp(-logit))

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
        return cls(**d)


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

    def brief(self) -> Dict:
        p = self.prob
        return {"id": self.id, "path": self.path, "log_type": self.log_type,
                "author": self.author, "tags": self.tags,
                "posterior": round(p.posterior_mean, 4), "entropy": round(p.entropy, 3),
                "efe": round(p.expected_free_energy, 4), "payload": self.payload}


# ── LAFS core (Mongo-persisted) ──────────────────────────────────────
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

    def _col(self):
        from core.databases import get_sync_db
        return get_sync_db()["lafs_cabinet"]

    def _load(self):
        if self._loaded:
            return
        doc = self._col().find_one({"_id": "cabinet"})
        if doc:
            self.sheets = {sid: Sheet.from_persist(d) for sid, d in doc.get("sheets", {}).items()}
            self.path_index = defaultdict(set, {k: set(v) for k, v in doc.get("path_index", {}).items()})
            self.graph = defaultdict(set, {k: set(v) for k, v in doc.get("graph", {}).items()})
            self.global_alpha = doc.get("global_alpha", 1.0)
            self.global_beta = doc.get("global_beta", 1.0)
            self.domain_priors = defaultdict(lambda: (1.0, 1.0),
                                             {k: tuple(v) for k, v in doc.get("domain_priors", {}).items()})
            self.logtype_priors = defaultdict(lambda: (1.0, 1.0),
                                              {k: tuple(v) for k, v in doc.get("logtype_priors", {}).items()})
        self._loaded = True

    def _save(self):
        doc = {"_id": "cabinet",
               "sheets": {sid: s.to_persist() for sid, s in self.sheets.items()},
               "path_index": {k: list(v) for k, v in self.path_index.items()},
               "graph": {k: list(v) for k, v in self.graph.items()},
               "global_alpha": self.global_alpha, "global_beta": self.global_beta,
               "domain_priors": {k: list(v) for k, v in self.domain_priors.items()},
               "logtype_priors": {k: list(v) for k, v in self.logtype_priors.items()}}
        self._col().replace_one({"_id": "cabinet"}, doc, upsert=True)

    def _update_hyperpriors(self):
        if not self.sheets:
            return
        self.global_alpha = float(np.mean([s.prob.alpha for s in self.sheets.values()]))
        self.global_beta = float(np.mean([s.prob.beta for s in self.sheets.values()]))
        dom_stats, lt_stats = defaultdict(lambda: [[], []]), defaultdict(lambda: [[], []])
        for s in self.sheets.values():
            parts = s.path.split("/")
            dom, lt = parts[0], parts[1] if len(parts) > 1 else parts[0]
            dom_stats[dom][0].append(s.prob.alpha); dom_stats[dom][1].append(s.prob.beta)
            lt_stats[lt][0].append(s.prob.alpha); lt_stats[lt][1].append(s.prob.beta)
        for d, (a, b) in dom_stats.items():
            self.domain_priors[d] = (float(np.mean(a)), float(np.mean(b)))
        for lt, (a, b) in lt_stats.items():
            self.logtype_priors[lt] = (float(np.mean(a)), float(np.mean(b)))

    def add_sheet(self, domain: str, log_type: str, payload: Dict[str, Any],
                  author: str = "system", cross_refs: Optional[List[str]] = None,
                  tags: Optional[List[str]] = None, prior_strength: float = 2.0) -> Sheet:
        self._load()
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

    def _propagate_belief(self, sheet_id: str, strength: float = 0.08):
        if sheet_id not in self.sheets:
            return
        src = self.sheets[sheet_id].prob
        for neigh in self.graph.get(sheet_id, []):
            if neigh in self.sheets:
                tgt = self.sheets[neigh].prob
                tgt.alpha = (1 - strength) * tgt.alpha + strength * src.alpha
                tgt.beta = (1 - strength) * tgt.beta + strength * src.beta

    def get_related(self, sheet_id: str, depth: int = 1) -> List[Sheet]:
        self._load()
        visited, result, frontier = set(), [], {sheet_id}
        for _ in range(depth):
            nxt = set()
            for sid in frontier:
                for n in self.graph.get(sid, []):
                    if n not in visited and n in self.sheets:
                        visited.add(n); result.append(self.sheets[n]); nxt.add(n)
            frontier = nxt
        return result

    def probability_search(self, query: str, domain_filter: Optional[str] = None,
                           log_type_filter: Optional[str] = None, min_posterior: float = 0.05,
                           max_entropy: float = 6.0, top_k: int = 25,
                           context_ids: Optional[List[str]] = None,
                           acquisition: str = "efe", kappa: float = 2.2) -> List[Dict]:
        self._load()
        q_tokens = set(query.lower().split())
        context_set: Set[str] = set()
        if context_ids:
            for cid in context_ids:
                context_set |= self.graph.get(cid, set())
        out = []
        for sid, sheet in self.sheets.items():
            if domain_filter and not sheet.path.startswith(domain_filter + "/"):
                continue
            if log_type_filter and sheet.log_type != log_type_filter:
                continue
            p = sheet.prob
            if p.posterior_mean < min_posterior or p.entropy > max_entropy:
                continue
            text = (json.dumps(sheet.payload) + " " + sheet.path + " " + " ".join(sheet.tags)).lower()
            lexical = sum(1 for t in q_tokens if t in text) / max(1, len(q_tokens))
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

    def reinforce(self, sheet_id: str, success: bool, weight: float = 1.0,
                  tag: Optional[str] = None, deep: bool = False):
        self._load()
        if sheet_id not in self.sheets:
            return None
        self.sheets[sheet_id].prob.update(0.95 if success else 0.10, weight, tag=tag, deep=deep)
        self._propagate_belief(sheet_id)
        self._update_hyperpriors()
        self._save()
        return self.sheets[sheet_id].brief()

    # ── Stage C2: multi-hop belief propagation + posterior-predictive checks ──
    def belief_propagate(self, sheet_id: str, hops: int = 2, strength: float = 0.08) -> Dict:
        """Propagate the source sheet's belief across ``hops`` graph hops with
        geometric decay, returning a full trace of updated neighbors. This is
        the multi-hop generalisation of ``_propagate_belief`` (1-hop)."""
        self._load()
        if sheet_id not in self.sheets:
            return {"ok": False, "error": "sheet_not_found"}
        src = self.sheets[sheet_id].prob
        visited: Set[str] = {sheet_id}
        frontier: Set[str] = {sheet_id}
        trace: List[Dict] = []
        for hop in range(1, hops + 1):
            decay = strength * (0.6 ** (hop - 1))
            nxt: Set[str] = set()
            for sid in frontier:
                for neigh in self.graph.get(sid, []):
                    if neigh in visited or neigh not in self.sheets:
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

    def posterior_predictive_check(self, sheet_id: Optional[str] = None) -> Dict:
        """Surface a posterior-predictive calibration check: how well each
        sheet's Beta posterior predicts its own observed evidence (Brier +
        credible-interval coverage)."""
        self._load()
        sheets = ([self.sheets[sheet_id]] if sheet_id and sheet_id in self.sheets
                  else list(self.sheets.values()))
        if not sheets:
            return {"ok": False, "error": "no_sheets"}
        briers, covered, total_obs = [], 0, 0
        per_sheet = []
        for s in sheets:
            p = s.prob
            brier = p.brier_calibration()
            lo, hi = p.credible_interval()
            obs = [1.0 if float(e) >= 0.5 else 0.0
                   for e in getattr(p, "evidence_log", []) if isinstance(e, (int, float))]
            in_ci = sum(1 for o in obs if lo <= o <= hi)
            covered += in_ci
            total_obs += len(obs)
            briers.append(brier)
            if sheet_id:
                per_sheet.append({"sheet_id": s.id, "brier": round(brier, 4),
                                  "ci95": [round(lo, 4), round(hi, 4)],
                                  "posterior": round(p.posterior_mean, 4),
                                  "observations": len(obs), "in_ci": in_ci})
        avg_brier = float(np.mean(briers)) if briers else 0.0
        coverage = (covered / total_obs) if total_obs else 0.0
        return {"ok": True, "sheets_checked": len(sheets),
                "avg_brier": round(avg_brier, 4),
                "calibration_quality": round(1.0 / (1.0 + 4 * avg_brier), 4),
                "ci95_coverage": round(coverage, 4), "observations": total_obs,
                "per_sheet": per_sheet}

    def top_efe(self, k: int = 8, domain_filter: Optional[str] = None) -> List[Dict]:
        """Top-k sheets by Expected Free Energy — 'what Jeeves knows best'."""
        self._load()
        rows = [s for s in self.sheets.values()
                if not domain_filter or s.path.startswith(domain_filter + "/")]
        rows.sort(key=lambda s: s.prob.expected_free_energy, reverse=True)
        return [{**s.brief(), "efe": round(s.prob.expected_free_energy, 4),
                 "posterior": round(s.prob.posterior_mean, 4)} for s in rows[:k]]

    def queue_for_jury(self, sheet_id: str, reason: str = "high_entropy") -> Dict:
        self._load()
        s = self.sheets.get(sheet_id)
        entry = {"id": sheet_id, "reason": reason,
                 "path": s.path if s else None,
                 "entropy": s.prob.entropy if s else None, "queued": _now()}
        self._col().database["lafs_jury_queue"].insert_one(dict(entry))
        return {k: v for k, v in entry.items() if k != "_id"}

    def stats(self) -> Dict:
        self._load()
        posts = [s.prob.posterior_mean for s in self.sheets.values()]
        ents = [s.prob.entropy for s in self.sheets.values()]
        efes = [s.prob.expected_free_energy for s in self.sheets.values()]
        return {"total_sheets": len(self.sheets),
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
