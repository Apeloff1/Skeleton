"""Canonical virtual companion: proof-derived progression, no fabricated XP."""
from __future__ import annotations

import copy
import hashlib
import unittest

from skeleton.ai.webcrawler.dragon_companion import (
    build_companion, companion_priority, _lexemes, _signature, _similarity,
)
from skeleton.ai.webcrawler.dragon_curriculum_trace import decision_receipt, validate_receipt
from skeleton.ai.webcrawler.dragon_questbook import Contribution, derive_questbook
from skeleton.ai.webcrawler.frontier_scheduler import choose_frontier
from skeleton.ai.webcrawler.operations import CrawlOperationError, CrawlRun

from tests.test_ai_webcrawler_dragon_adaptive_instruction_guard import (
    BASE, OTHER, ROBOTS, ScriptedFetcher, make_run, resign, step,
)

A = ("Orbital mechanics uses eccentricity, angular momentum and gravitational constants "
     "to calculate trajectories. Measurements include velocity vectors, inclination, "
     "periapsis coordinates, observation uncertainties and numerical integration.")
B = ("Orbital mechanics observations compare spacecraft rendezvous maneuvers with "
     "restricted three body systems. Engineers estimate transfer windows, atmospheric "
     "drag, resonance, perturbation and long duration navigation using calibrated instruments.")
C = ("Orbital mechanics experiments evaluate conservation laws in a rotating frame. "
     "Researchers compare mass ratios, acceleration components, reference epochs, "
     "numerical residuals, spatial coordinates and telescope calibration.")
LIMITS = {"max_requests": 16, "max_total_bytes": 262144, "max_documents": 8}


def source(url, text, sequence, *, media="text/html"):
    digest = hashlib.sha256(text.encode()).hexdigest()
    identifier = hashlib.sha256((url + digest).encode()).hexdigest()
    return {"source_id": identifier, "content_hash": digest, "canonical_url": url,
            "fetched_url": url, "text": text, "fetched_at": float(sequence),
            "content_type": media, "provenance": {"capture_sequence": sequence}}


def measurement(index, row=None, *, host="example.com", kind="captured"):
    return {"request": index, "kind": kind, "host": host, "uncertain_bytes": 64 if kind == "error" else 0,
            "event_sequence": row["provenance"]["capture_sequence"] if row else index*2}


def profile(rows, *, state="ready", style="balanced", due=True, consent=True,
            extra=(), requests=None):
    observations = [measurement(i+1, row, host=row["fetched_url"].split("/")[2])
                    for i, row in enumerate(rows)] + list(extra)
    count = requests if requests is not None else len(observations)
    return build_companion(sources={row["source_id"]: row for row in rows},
        measurements=observations, query="orbital mechanics",
        usage={"requests": count, "bytes": 512*len(rows), "reserved_bytes": 0, "documents": len(rows)},
        limits=LIMITS, state=state, frontier_count=2, consent_current=consent, due=due, style=style)


def page(text):
    return (200, "text/html", ("<html><title>Research</title><p>" + text + "</p></html>").encode(), {})


class CompanionGrowthTests(unittest.TestCase):
    def test_repeated_words_and_exact_duplicates_do_not_farm_growth(self):
        first = source(BASE+"/one", A, 2)
        mirrored = source(OTHER+"/copy", A, 4)
        padded = source(OTHER+"/padded", "orbital mechanics " * 40, 6)
        primary = profile([first]).projection
        replica = profile([first, mirrored]).projection
        noisy = profile([first, padded]).projection
        self.assertEqual(replica["growth"], primary["growth"])
        self.assertEqual(replica["questbook"]["credited_sources"], 1)
        self.assertEqual(noisy["growth"], primary["growth"])
        self.assertEqual(noisy["questbook"]["credited_sources"], 1)

    def test_novel_distinct_origin_and_format_yield_more_than_mirror(self):
        first = source(BASE+"/one", A, 2)
        second = source(OTHER+"/two", B, 4, media="text/plain")
        result = profile([first, second]).projection
        self.assertGreater(result["growth"], profile([first]).projection["growth"])
        self.assertEqual(result["novel_origins"], 2)
        self.assertEqual(result["multi_origin_terms"], 2)
        self.assertEqual(result["habitats"], {"text": 1, "web": 1})
        achievements = {q["code"]: q for q in result["questbook"]["quests"]}
        self.assertEqual(achievements["new_habitat"]["state"], "completed")
        self.assertEqual(achievements["first_insight"]["source_ids"], [first["source_id"]])
        self.assertEqual(achievements["novel_trail"]["state"], "active")

    def test_rest_and_failure_never_remove_evidence_growth(self):
        first = source(BASE+"/one", A, 2)
        active = profile([first]).projection
        resting = profile([first], consent=False, due=False).projection
        failed = profile([first], state="failed", extra=[
            measurement(2, kind="error"), measurement(3, kind="error")]).projection
        self.assertEqual(resting["quest"], "rest")
        self.assertEqual(resting["growth"], active["growth"])
        self.assertEqual(failed["growth"], active["growth"])
        self.assertFalse(resting["inactivity_penalty"])
        self.assertFalse(failed["training_permission"])

    def test_continuous_script_tokenization_is_finite_and_nonempty(self):
        text = "轨道力学研究空间飞行器引力作用速度方向变化和科学实验观测结果"
        self.assertGreater(len(_lexemes(text)), 10)
        self.assertTrue(_signature(text))
        self.assertEqual(_similarity(_signature(text), _signature(text)), 1)
        self.assertLessEqual(len(_lexemes(text * 800)), 2048)

    def test_budget_and_guardian_cannot_amplify_exploration(self):
        candidate = {"url": OTHER+"/orbital/mechanics", "depth": 0, "attempts": 0, "ready_at": 0}
        healthy = profile([], style="curious")
        low = profile([], style="curious", requests=15)
        guardian = profile([], style="guardian")
        self.assertEqual(low.quest, "conserve")
        self.assertEqual(companion_priority(candidate, profile=low, base=.4, query="orbital mechanics"), .4)
        for model in (healthy, guardian):
            score = companion_priority(candidate, profile=model, base=.4, query="orbital mechanics")
            self.assertLessEqual(abs(score-.4), .120001)
        chosen, decision = choose_frontier([candidate], sources={}, host_ready={"example.org": 8},
            query="orbital mechanics", now=1, strategy="companion_curiosity", companion=healthy)
        self.assertIsNone(chosen)
        self.assertIsNone(decision)


class CanonicalReplayTests(unittest.TestCase):
    def test_reservation_and_settlement_preserve_same_curriculum_and_source_id(self):
        one = BASE+"/first"
        fetch = ScriptedFetcher({BASE+"/robots.txt": (200, "text/plain", ROBOTS, {}), one: page(A)})
        run, at = make_run(fetch, strategy="companion_curiosity")
        committed = []
        def checkpoint(snapshot, event):
            committed.append((copy.deepcopy(snapshot), copy.deepcopy(event)))
        step(run, at+1, checkpoint=checkpoint)
        step(run, at+4, checkpoint=checkpoint)
        snapshot = run.snapshot()
        self.assertEqual(len(snapshot["sources"]), 1)
        settled = snapshot["acquisition_measurements"]
        self.assertEqual(len(settled), 2)
        self.assertEqual(settled[0]["curriculum"]["phase"], "policy")
        self.assertEqual(settled[1]["curriculum"]["phase"], "content")
        self.assertEqual(settled[1]["source_id"], next(iter(snapshot["sources"])))
        reservations = [s["pending_dispatch"]["curriculum"] for s,e in committed
                        if e["kind"] == "dispatch_reserved"]
        self.assertEqual(reservations, [row["curriculum"] for row in settled])
        for value, _ in committed:
            restored = CrawlRun.from_snapshot(value, fetcher=fetch)
            self.assertEqual(restored.snapshot(), value)
        restored = CrawlRun.from_snapshot(snapshot, fetcher=fetch)
        self.assertEqual(restored.status()["companion"]["questbook"], run.status()["companion"]["questbook"])
        self.assertEqual(restored.status()["curriculum_trace"], run.status()["curriculum_trace"])
        tampered = copy.deepcopy(snapshot)
        tampered["acquisition_measurements"][1]["source_id"] = "a"*64
        with self.assertRaises(CrawlOperationError):
            CrawlRun.from_snapshot(resign(tampered), fetcher=fetch)

    def test_pending_unknown_outcome_replays_without_double_fetch_or_credit(self):
        one = BASE+"/first"
        fetch = ScriptedFetcher({BASE+"/robots.txt": (200, "text/plain", ROBOTS, {}), one: page(A)})
        run, at = make_run(fetch, strategy="companion_guardian")
        committed = []
        step(run, at+1, checkpoint=lambda s,e: committed.append(copy.deepcopy(s)))
        pending = next(s for s in committed if s["pending_dispatch"] is not None)
        original = pending["pending_dispatch"]["curriculum"]
        before = len(fetch.calls)
        recovered = CrawlRun.from_snapshot(pending, fetcher=fetch)
        step(recovered, at+2)
        snap = recovered.snapshot()
        self.assertEqual(len(fetch.calls), before)
        self.assertEqual(snap["usage"]["requests"], 1)
        self.assertEqual(snap["acquisition_measurements"][0]["kind"], "interrupted_dispatch")
        self.assertEqual(snap["acquisition_measurements"][0]["curriculum"], original)
        self.assertEqual(recovered.status()["companion"]["growth"], 0)
        self.assertGreater(snap["usage"]["reserved_bytes"], 0)

    def test_forged_decision_does_not_validate(self):
        record = decision_receipt(mode="companion", quest="explore", candidate=BASE+"/one",
                                  eligible=1, base=.4, priority=.45, policy=False)
        validate_receipt(record, mode="companion", candidate=BASE+"/one")
        for forged in ({**record, "priority_milli": 900}, {**record, "network_authority_expanded": True},
                       {**record, "quest": "rest"}):
            with self.assertRaises(ValueError):
                validate_receipt(forged)
        with self.assertRaises(ValueError):
            validate_receipt(record, candidate=OTHER+"/one")


if __name__ == "__main__":
    unittest.main()
