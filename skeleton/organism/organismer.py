"""Organismer — the process that multiplies the organism toward 10×.

Organism  = cortex + galaxy + genos + social pointers.
Organismer = one bounded step that compounds all four.

Extended gene (house, not a paper copy):

    G' = G * (1 + η * M * H * C * S * (1 - ε))

S is source density from social ingest + seeded field pointers.
Per-step growth is clipped to [1.00, 1.22] so a single speak cannot
overshoot the 10× trajectory. Target remains G=10.

Decentralized memory pattern (private brain shelves + shared wiki
nucleus) is already the galaxy; organismer only scores it and
advances G.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.cortex.attn import cosine_lr
from skeleton.cortex.genos import Genos
from skeleton.galaxy.system import GalaxySystem, live_galaxy
from skeleton.galaxy.shelf import save as galaxy_save
from skeleton.organism.ledger import append as ledger_append, count as ledger_count
from skeleton.organism.router import card as route_card_of, route as write_route, should_pulse
from skeleton.organism.shelf import load as shelf_load, save as shelf_save
from skeleton.galaxy.banks import card as banks_card
from skeleton.organism.idle import due as idle_due, run as idle_run
from skeleton.organism.teachers import glean_rule, sync as teacher_sync
from skeleton.organism.writeback import absorb as wb_absorb, should_suppress, topics as wb_topics
from skeleton.social.ingest import ingest
from skeleton.social.sota import sota_card


def _clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


class Organismer:
    TARGET = 10.0

    def __init__(
        self,
        *,
        genos: Optional[Genos] = None,
        galaxy: Optional[GalaxySystem] = None,
        persist: bool = False,
        root: Optional[Path] = None,
    ) -> None:
        self.genos = genos or Genos()
        self.galaxy = galaxy or live_galaxy()
        self.steps = 0
        self.errors = 0
        self.log: List[Dict[str, Any]] = []
        self.last_dream_step = 0
        self.persist_on = persist
        self.root = root
        if persist:
            shelf_load(self, root=root)

    @property
    def G(self) -> float:
        return float(self.genos.G)

    @property
    def toward(self) -> float:
        return min(100.0, max(0.0, (self.G - 1.0) / (self.TARGET - 1.0) * 100.0))

    def _S(self, social: Dict[str, Any]) -> float:
        n = len(social.get("houses") or [])
        x = int(social.get("x_posts") or 0)
        p = int(social.get("papers") or 0)
        cov = float((social.get("coverage_score") or 0) or 0)
        if cov <= 0:
            try:
                from skeleton.social.coverage import coverage_card
                cov = float(coverage_card("").get("score") or 0)
            except Exception:
                cov = 0.0
        raw = 1.0 + 0.14 * n + 0.10 * x + 0.12 * p + 0.20 * cov
        return _clip(raw, 1.0, 2.2)

    def step(
        self,
        stimulus: str,
        *,
        neo: Any = None,
        sleep: bool = False,
        citation: str = "",
        url: str = "",
        live_cdx: bool = False,
    ) -> Dict[str, Any]:
        self.steps += 1
        eta = cosine_lr(min(self.steps, 64), 64, base=0.28, floor=0.08)
        social = ingest(stimulus, live=live_cdx)
        first = (social.get("cards") or [{}])[0] if social.get("cards") else {}
        cite = citation or str(first.get("url") or "")
        try:
            from skeleton.organism.caps import adapt as caps_adapt, trim_mesh
            adapt_card = caps_adapt()
            trim_card = trim_mesh(self.galaxy.mesh)
            topics = (self.galaxy.mesh.wiki.catalog().get("topics") or {})
            decision, score, hit = write_route(stimulus, topics.keys())
            if decision == "new" and should_suppress(stimulus, wb_topics(self.galaxy.mesh)):
                decision, hit = "skip", (hit or "internalized")
            route_card = route_card_of(decision, score, hit)
            gxy: Dict[str, Any]
            if should_pulse(decision):
                gxy = self.galaxy.pulse(stimulus, citation=cite, url=url or cite, sleep=sleep)
            else:
                gxy = {
                    "route": "skip",
                    "memory": {},
                    "principle": None,
                    "wiki": self.galaxy.mesh.wiki.catalog(),
                    "stored_prose": 0,
                }
            if social.get("cards"):
                for card in social["cards"][:6]:
                    topic = str(card.get("kind") or "url") + " " + str(card.get("url") or "")[:80]
                    self.galaxy.editor.index_topic(
                        self.galaxy.codec.encode(
                            topic, kind="citation", brain="editor",
                            citation=str(card.get("url") or ""), url=str(card.get("url") or ""),
                            depth_hint=5, tags=("social", str(card.get("house") or "web")),
                        )
                    )
            genos_card = None
            bound = neo is not None and (
                hasattr(neo, "elect_mouth") or hasattr(neo, "transformer") or bool(getattr(neo, "slots", None))
            )
            contact = teacher_sync(neo, stimulus)
            if bound:
                genos_card = self.genos.pulse(neo, stimulus=stimulus)
            else:
                # organismer-local gene when no neo mouth is bound
                S = self._S(social)
                M, H, C, eps = 1.0, 0.7, 0.12, self.errors / max(1, self.steps)
                try:
                    from skeleton.organism.caps import live as live_caps
                    gclip = float(live_caps().growth_clip)
                except Exception:
                    gclip = 1.22
                growth = _clip(1.0 + eta * M * H * C * S * (1.0 - eps), 1.0, gclip)
                self.genos.G = float(self.genos.G * growth)
                self.genos.pulses += 1
                if self.genos.G > self.genos.peak:
                    self.genos.peak = self.genos.G
                genos_card = {
                    "ok": 1, "M": M, "H": H, "C": C, "S": S,
                    "G": round(self.genos.G, 6), "growth": round(growth, 6),
                    "eta": round(eta, 4), "path": "organismer-local",
                }
            S = self._S(social)
            if genos_card and "S" not in genos_card:
                # fold S into an already-pulsed G without double-counting hard:
                # apply a small residual S-boost, still clipped
                residual = _clip(1.0 + 0.04 * (S - 1.0), 1.0, 1.08)
                self.genos.G = float(self.genos.G * residual)
                genos_card = {**genos_card, "S": S, "S_residual": round(residual, 4),
                              "G": round(self.genos.G, 6)}
            rule = glean_rule(self.galaxy, stimulus=stimulus, contact=contact, genos=genos_card)
            card = {
                "kind": "organismer",
                "step": self.steps,
                "G": round(self.G, 6),
                "target": self.TARGET,
                "toward_10x_pct": round(self.toward, 2),
                "eta": round(eta, 4),
                "S": S,
                "social": social,
                "galaxy": {
                    "route": gxy.get("route"),
                    "memory_id": (gxy.get("memory") or {}).get("id"),
                    "principle": (gxy.get("principle") or {}).get("id") if gxy.get("principle") else None,
                    "wiki_topics": len((gxy.get("wiki") or {}).get("topics") or {}),
                    "atom_ids": list(gxy.get("atom_ids") or []),
                    "audit": gxy.get("audit"),
                },
                "genos": genos_card,
                "sota": sota_card(stimulus, G=self.G),
                "write": route_card,
                "contact": contact,
                "rule": rule,
                "stored_prose": 0,
            }
            if sleep or idle_due(self.steps, self.last_dream_step):
                card["idle"] = idle_run(self.galaxy, neo)
                self.last_dream_step = self.steps
            card["audit"] = self.galaxy.editor.audit()
            card["writeback"] = wb_absorb(self.galaxy.mesh)
            card["banks"] = banks_card(self.galaxy.mesh, neo=neo)
            card["caps"] = adapt_card
            card["trim"] = trim_card
            from skeleton.galaxy.kv import archive as kv_archive
            from skeleton.galaxy.lattice import card as lattice_card
            card["lattice"] = lattice_card(self.galaxy.mesh, neo=neo).get("ascii")
            card["kv"] = kv_archive(self.galaxy.mesh, neo=neo)
            from skeleton.organism.path10 import path_card
            from skeleton.social.coverage import coverage_card
            card["path10"] = path_card(self, last_growth=(genos_card or {}).get("growth"))
            card["coverage"] = coverage_card(stimulus)
            card["fresh"] = self.galaxy.editor.freshness()
            self.last_health = {
                "ok": int(float((adapt_card or {}).get("pressure") or 0) < 0.90),
                "pressure": (adapt_card or {}).get("pressure"),
                "coverage": card["coverage"]["score"],
            }
            line: Dict[str, Any] = {}
            if self.persist_on:
                ids = list(gxy.get("atom_ids") or [])
                line = ledger_append({
                    "kind": "organism-write",
                    "decision": decision,
                    "url": cite,
                    "topic": (hit or stimulus)[:80],
                    "G": self.G,
                    "atoms": ",".join(ids)[:160],
                }, root=self.root)
                card["saved"] = shelf_save(self, root=self.root)
                card["galaxy_saved"] = galaxy_save(self.galaxy, root=self.root)
            card["ledger"] = {
                "sha": line.get("sha"),
                "prev": line.get("prev"),
                "n": ledger_count(self.root) if self.persist_on else 0,
            }
            from skeleton.organism.next import hint as next_hint
            card["next"] = next_hint(self, neo=neo)
            if self.persist_on:
                from skeleton.organism.journal import append as journal_append
                journal_append({
                    "step": self.steps,
                    "G": card["G"],
                    "decision": decision,
                    "coverage": card["coverage"]["score"],
                    "pressure": (adapt_card or {}).get("pressure"),
                }, root=self.root)
            self.log.append({"step": self.steps, "G": card["G"], "S": S, "decision": decision})
            return card
        except Exception as exc:
            self.errors += 1
            return {
                "kind": "organismer",
                "ok": 0,
                "error": type(exc).__name__,
                "G": round(self.G, 6),
                "stored_prose": 0,
            }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": "organism",
            "G": round(self.G, 6),
            "target": self.TARGET,
            "toward_10x_pct": round(self.toward, 2),
            "steps": self.steps,
            "errors": self.errors,
            "galaxy_pulses": self.galaxy.pulses,
            "sota": sota_card("", G=self.G),
            "log": list(self.log[-24:]),
            "stored_prose": 0,
        }


_LIVE: Optional[Organismer] = None


def live_organismer() -> Organismer:
    global _LIVE
    if _LIVE is None:
        _LIVE = Organismer(persist=True)
    return _LIVE


def reset_organismer() -> None:
    global _LIVE
    _LIVE = None
