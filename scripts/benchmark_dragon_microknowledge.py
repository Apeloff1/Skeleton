"""Reproducible local lexical retrieval comparison; no SOTA/device qualification."""
from __future__ import annotations
from dataclasses import replace
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skeleton.ai.webcrawler.dragon_knowledge_graph import DragonKnowledgeGraph, KnowledgeConcept
from skeleton.ai.webcrawler.dragon_microknowledge import DragonMicroKnowledge
from skeleton.ai.webcrawler.dragon_knowledge_retrieval import retrieve_knowledge
from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample, plan_resources


def main() -> None:
    conn = sqlite3.connect(':memory:')
    graph = DragonKnowledgeGraph(conn)
    index = DragonMicroKnowledge(graph)
    for i in range(1000):
        concept = KnowledgeConcept(f'concept_{i}', 'gameplay', 'Original jump physics with bounded velocity. ' + str(i))
        graph.put_concept('bench', concept, authorized=True)
        index.index('bench', concept.concept_id, {'era': '1990', 'engine': 'nes'},
                    evidence_ref='synthetic_reference', expires_at=30, authorized=True)
    plan = replace(plan_resources(HardwareSample(256 * 1024**2, 4, .1, .9, True, False, 10),
                                  now=10, foreground=True), retrieval_candidates=20)
    funcs = {'full_scan': lambda: retrieve_knowledge(graph, 'bench', 'jump physics', authorized=True, limit=20),
             'micro_index': lambda: index.retrieve('bench', 'jump physics', {}, plan, now=10, authorized=True)}
    assert [h.concept_id for h in funcs['full_scan']().hits] == [h.concept_id for h in funcs['micro_index']().hits]
    samples = {key: [] for key in funcs}
    # Interleave methods to reduce systematic cache/order bias.
    for _ in range(40):
        for key, fn in funcs.items():
            start = time.perf_counter()
            fn()
            samples[key].append((time.perf_counter() - start) * 1000)
    results = {}
    for key, values in samples.items():
        ordered = sorted(values)
        results[key] = {'p50_ms': round(statistics.median(values), 3),
                        'p95_ms': round(ordered[37], 3), 'p99_ms': round(ordered[39], 3)}
    print(json.dumps({'platform': platform.platform(), 'python': platform.python_version(),
                      'sqlite': sqlite3.sqlite_version, 'concepts': 1000,
                      'queries_per_method': 40, 'top_k': 20, 'matching_ids': True,
                      'fixture': 'synthetic_common_terms', 'results': results}, sort_keys=True))
    conn.close()


if __name__ == '__main__':
    main()
