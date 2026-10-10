"""Behavioral and adversarial tests of derived research, not authority grants."""
from dataclasses import replace
from hashlib import sha256
from itertools import repeat
import json
from pathlib import Path
import zlib

import pytest

from skeleton.ai.game_builder.contracts import canonical_digest, canonical_json
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs, ProjectLearning, read_source_registry
from skeleton.ai.game_builder.dragon_source_catalog import canonical_source_url, extract_catalog, merge_catalogs
from skeleton.ai.game_builder.dragon_almanac_sequence import SequentialAlmanacWorker
from skeleton.ai.game_builder.dragon_almanac_weights import build_weight_pack, retrieve_weight_pack
from skeleton.ai.game_builder.dragon_almanac_experiment import run_original_experiment
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore, ReviewedDocument, ReviewedNote

NOW = 1791647564
TEXT = "Jump buffering can improve control responsiveness in the tested platform game."


@pytest.fixture
def library(tmp_path):
    with ReviewedKnowledgeStore(tmp_path / "library.sqlite") as store:
        yield store


def registry():
    return merge_catalogs([extract_catalog("# Games\n## Controls\n[One](https://example.com/one)\n## Audio\n[Two](https://example.com/two)\n",
        catalog_url="https://github.com/example/catalog/blob/main/README.md", blob_sha="a"*40,
        observed_at="2026-10-10T15:52:44Z")])


def document(source="one", url="https://example.com/one", stance="supports", text=TEXT, observed="2026-10-10T15:00:00Z"):
    return ReviewedDocument("owner", source, url, "Control experiment", text, observed,
        "test-license", ("design_reference",), "independent-reviewer", True,
        (ReviewedNote("note-one", "jump-buffering", "Jump buffering improves responsiveness.",
          0, len(text), stance, 800000, source),))


def test_actual_registry_has_more_than_1500_cited_candidates():
    root = Path(__file__).parents[1] / "skeleton/ai/game_builder/catalogs/dragon_sources_20261010"
    r = read_source_registry(root)
    assert r["unique_urls"] == len({s["url"] for s in r["sources"]}) > 1500
    assert len(r["catalogs"]) == 8
    assert r["individually_fetched_sources"] == r["approved_sources"] == 0
    assert all(s["discoveries"] and s["rights"] == "not_assessed" for s in r["sources"])


def test_url_normalization_preserves_video_identity():
    assert canonical_source_url("https://www.youtube.com/watch?v=abc&utm_source=x#t=3") == "https://www.youtube.com/watch?v=abc"
    assert canonical_source_url("https://example.com/A") != canonical_source_url("https://example.com/a")


@pytest.mark.parametrize("url", ["file:///tmp/x", "https://127.0.0.1/x", "https://x.local/x",
    "https://u:p@example.com/x", "https://example.com:8443/x", "https://localhost/x"])
def test_unsafe_catalog_urls_rejected(url):
    with pytest.raises(ValueError): canonical_source_url(url)


def test_source_import_idempotent_and_every_heading_is_an_almanac(library):
    a = DragonAlmanacs(library)
    assert a.ingest_sources("owner", registry(), authorized=True)["new_sources"] == 2
    assert a.ingest_sources("owner", registry(), authorized=True)["new_sources"] == 0
    report = a.report("owner", authorized=True)
    assert report["total_almanacs"] == 5
    assert any(r["headers"][-1] == "Controls" and r["discovered_sources"] == 1 for r in report["almanacs"])
    assert a.report("other", authorized=True)["total_almanacs"] == 0
    assert library._rows("owner") == []


def test_source_import_rolls_back_on_bad_late_row(library):
    a = DragonAlmanacs(library); r = registry(); r["sources"][-1]["source_id"] = "forged"
    r["catalog_digest"] = canonical_digest({k: v for k, v in r.items() if k != "catalog_digest"})
    with pytest.raises(ValueError): a.ingest_sources("owner", r, authorized=True)
    assert a.report("owner", authorized=True)["total_almanacs"] == 0


def test_topics_bound_infinite_input_and_full_path_identity(library):
    a = DragonAlmanacs(library)
    with pytest.raises(ValueError): a.ensure_topic("owner", repeat("topic"), authorized=True)
    assert a.ensure_topic("owner", ["A", "Rules"], authorized=True) != a.ensure_topic("owner", ["B", "Rules"], authorized=True)


def test_project_cascade_preserves_machine_origin_and_unknown_status(library):
    a = DragonAlmanacs(library); topic = a.ensure_topic("owner", ["AI", "Search"], authorized=True)
    first = ProjectLearning("prototype", "a"*64, topic, "steppingstone", "measured_experiment",
        "A scoped observation", "A reproducible experiment", "A synthetic workload", ("b"*64,))
    parent = a.record_learning("owner", first, now=NOW, authorized=True)
    child = replace(first, project_id="product", stage="product", parent_learning=(parent,))
    digest = a.record_learning("owner", child, now=NOW+1, authorized=True)
    body = json.loads(library.db.execute("SELECT body FROM dragon_almanac_learning WHERE digest=?", (digest,)).fetchone()[0])
    assert body["epistemic_state"] == "unreviewed"
    assert body["independent_external_support_added"] == 0
    assert not body["training_authorized"]
    with pytest.raises(ValueError): a.record_learning("owner", child, now=NOW-1, authorized=True)
    with pytest.raises(ValueError): a.record_learning("other", child, now=NOW+1, authorized=True)


def test_learning_rejects_stale_canonical_source(library):
    a = DragonAlmanacs(library); topic = a.ensure_topic("owner", ["Controls"], authorized=True)
    rec = library.import_document(document(), expected_parent_digest=None, authorized=True)
    learning = ProjectLearning("prototype", "a"*64, topic, "research", "source_synthesis", "Scoped", "Method", "Limits",
                               ("b"*64,), source_refs=(("one", rec.revision_digest, "note-one"),))
    a.record_learning("owner", learning, now=NOW, authorized=True)
    library.import_document(document(observed="2026-10-10T15:01:00Z"), expected_parent_digest=rec.revision_digest, authorized=True)
    with pytest.raises(ValueError): a.record_learning("owner", learning, now=NOW+1, authorized=True)
    view = a.learning_view("owner", topic, authorized=True)
    assert view["findings"][0]["stale_source_dependencies"] == ["one"]


def test_entity_editions_are_versioned_not_collapsed(library):
    a = DragonAlmanacs(library); m = {"title": "Original Game", "source_url": "https://example.com/game", "edition": "1990"}
    def put(eid, metadata): return a.upsert_entity("owner", kind="edition", provider="catalog", entity_id=eid, metadata=metadata, authorized=True)
    first = put("edition-one", m)
    assert put("edition-one", m) == first
    assert put("edition-two", m) != first
    assert put("edition-one", {**m, "region": "JP"}) != first
    assert library.db.execute("SELECT COUNT(*) FROM dragon_almanac_entities").fetchone()[0] == 3


def setup_worker(library):
    a = DragonAlmanacs(library); a.ingest_sources("owner", registry(), authorized=True)
    worker = SequentialAlmanacWorker(a); assert worker.seed("owner", authorized=True) == 2
    return worker


def claim(worker, now=NOW): return worker.claim("owner", now=now, authorized=True, trusted_worker=True)


def finish(worker, job, now=NOW+1, output="b"*64, **extra):
    evidence = {"url": job.url, "input_digest": job.input_digest, "output_digest": output, **extra}
    return worker.finish(job, now=now, output_digest=output, evidence=evidence, authorized=True, trusted_worker=True)


def policy(worker, job, now=NOW+1):
    return finish(worker, job, now=now, robots_permitted=True, terms_permitted=True,
                  reference_use_permitted=True, ssrf_checked=True, expires_at=now+100)


def test_sequential_lease_fences_replay_and_expired_worker(library):
    w = setup_worker(library); first = claim(w)
    assert claim(w, NOW+1) is None
    reclaimed = claim(w, NOW+121)
    assert reclaimed.source_id == first.source_id and reclaimed.token != first.token
    with pytest.raises(ValueError): policy(w, first, NOW+122)
    policy(w, reclaimed, NOW+122)
    with pytest.raises(ValueError): policy(w, reclaimed, NOW+123)
    nxt = claim(w, NOW+123)
    assert nxt.source_id == first.source_id and nxt.stage == "fetch"


def test_three_attempts_block_and_do_not_starve_other_sources(library):
    w = setup_worker(library); first = claim(w)
    assert claim(w, NOW+121).attempt == 2
    assert claim(w, NOW+242).attempt == 3
    nxt = claim(w, NOW+363)
    assert nxt.source_id != first.source_id
    assert w.status("owner", authorized=True)["jobs"]["blocked"] == 1


def test_policy_denial_does_not_advance(library):
    w = setup_worker(library); job = claim(w)
    with pytest.raises(ValueError): finish(w, job)
    assert w.block(job, now=NOW+2, authorized=True)
    assert w.status("owner", authorized=True)["jobs"]["blocked"] == 1


def test_worker_url_forgery_and_clock_rollback_rejected(library):
    w = setup_worker(library); job = claim(w)
    with pytest.raises(ValueError): policy(w, replace(job, url="https://different.example/source"))
    with pytest.raises(ValueError): policy(w, job, NOW-1)


def test_blocked_recovery_archives_evidence_and_restarts_policy(library):
    w = setup_worker(library); p = claim(w); policy(w, p)
    f = claim(w, NOW+2); assert w.block(f, now=NOW+3, authorized=True)
    w.restart_blocked("owner", f.source_id, expected_input_digest=f.input_digest,
                      now=NOW+4, authorized=True, trusted_worker=True)
    assert claim(w, NOW+5).stage == "policy"
    assert library.db.execute("SELECT COUNT(*) FROM dragon_almanac_archived_steps").fetchone()[0] == 1


def test_fetch_requires_unexpired_policy(library):
    w = setup_worker(library); job = claim(w); policy(w, job)
    fetched = claim(w, NOW+2)
    with pytest.raises(ValueError): finish(w, fetched, now=NOW+102, http_status=200, redirects_rechecked=True, body_bytes=100)


def test_full_sequence_requires_exact_reviewed_body(library):
    w = setup_worker(library); p = claim(w); policy(w, p)
    f = claim(w, NOW+2); body_digest = sha256(TEXT.encode()).hexdigest()
    finish(w, f, now=NOW+3, output=body_digest, http_status=200, redirects_rechecked=True, body_bytes=len(TEXT))
    e = claim(w, NOW+4); finish(w, e, now=NOW+5, parser_version="test-v1", span_map_digest="c"*64)
    a = claim(w, NOW+6); finish(w, a, now=NOW+7, derived_claims_are_unreviewed=True, claim_count=1)
    review = claim(w, NOW+8)
    with pytest.raises(ValueError): finish(w, review, now=NOW+9)
    rec = library.import_document(document(source=p.source_id, url=p.url), expected_parent_digest=None, authorized=True)
    finish(w, review, now=NOW+9, output=rec.revision_digest)
    assert w.status("owner", authorized=True)["jobs"]["reviewed"] == 1


def test_weight_pack_retains_conflicts_and_rejects_stale_sources(library):
    first = library.import_document(document(), expected_parent_digest=None, authorized=True)
    library.import_document(document(source="two", url="https://example.com/two", stance="challenges"), expected_parent_digest=None, authorized=True)
    pack = build_weight_pack(library, "owner", authorized=True)
    result = retrieve_weight_pack(pack, library, "owner", "jump", authorized=True)
    assert result["conflicting_mechanics"] == ["jump-buffering"]
    assert not result["neural_weights"] and not result["training_authorized"]
    library.import_document(document(observed="2026-10-10T15:02:00Z"), expected_parent_digest=first.revision_digest, authorized=True)
    with pytest.raises(ValueError): retrieve_weight_pack(pack, library, "owner", "jump", authorized=True)


def test_forged_pack_statement_and_citation_fail_even_with_rehashed_payload(library):
    library.import_document(document(), expected_parent_digest=None, authorized=True)
    pack = build_weight_pack(library, "owner", authorized=True)
    for key, value in (("statement", "Forged claim"), ("source_url", "https://evil.example/"), ("span", [0, 1])):
        body = json.loads(zlib.decompress(pack.payload)); body["documents"][0][key] = value
        raw = canonical_json(body).encode(); payload = zlib.compress(raw)
        forged = replace(pack, payload=payload, raw_bytes=len(raw), payload_digest=sha256(payload).hexdigest())
        with pytest.raises(ValueError): retrieve_weight_pack(forged, library, "owner", "jump", authorized=True)


@pytest.mark.parametrize("tamper", ["inflate", "suppress", "rights", "duplicate"])
def test_rehashed_weight_pack_cannot_change_rank_or_claim_authority(library, tamper):
    library.import_document(document(), expected_parent_digest=None, authorized=True)
    pack = build_weight_pack(library, "owner", authorized=True)
    raw = zlib.decompress(pack.payload)
    if tamper == "duplicate":
        raw = raw.replace(b'"schema":', b'"schema":"forged","schema":', 1)
    else:
        body = json.loads(raw)
        if tamper == "inflate":
            body["postings"]["jump"][0][1] = 255
        elif tamper == "suppress":
            body["postings"]["jump"] = []
        else:
            body["training_authorized"] = True
        raw = canonical_json(body).encode("utf-8")
    payload = zlib.compress(raw)
    forged = replace(pack, payload=payload, raw_bytes=len(raw),
                     payload_digest=sha256(payload).hexdigest())
    with pytest.raises(ValueError):
        retrieve_weight_pack(forged, library, "owner", "jump", authorized=True)


@pytest.mark.parametrize("change", ["omit", "duplicate", "reorder"])
def test_rehashed_weight_pack_must_preserve_full_canonical_note_sequence(library, change):
    library.import_document(document(), expected_parent_digest=None, authorized=True)
    library.import_document(
        document(source="two", url="https://example.com/two", stance="challenges"),
        expected_parent_digest=None, authorized=True,
    )
    pack = build_weight_pack(library, "owner", authorized=True)
    body = json.loads(zlib.decompress(pack.payload))
    assert len(body["documents"]) == 2
    if change == "omit":
        body["documents"].pop()
        body["postings"] = {
            term: [pair for pair in entries if pair[0] < 1]
            for term, entries in body["postings"].items()
        }
    elif change == "duplicate":
        body["documents"].append(dict(body["documents"][0]))
        for entries in body["postings"].values():
            match = next((weight for number, weight in entries if number == 0), None)
            if match is not None:
                entries.append([2, match])
    else:
        body["documents"].reverse()
        for entries in body["postings"].values():
            entries[:] = sorted(([1-number, weight] for number, weight in entries))
    raw = canonical_json(body).encode("utf-8")
    payload = zlib.compress(raw)
    forged = replace(
        pack, payload=payload, raw_bytes=len(raw),
        payload_digest=sha256(payload).hexdigest(),
        documents=len(body["documents"]),
    )
    with pytest.raises(ValueError, match="document sequence differs"):
        retrieve_weight_pack(forged, library, "owner", "jump", authorized=True)


def test_corrupted_weight_pack_compression_is_a_safe_rejection(library):
    library.import_document(document(), expected_parent_digest=None, authorized=True)
    pack = build_weight_pack(library, "owner", authorized=True)
    payload = b"not-a-zlib-stream"
    forged = replace(pack, payload=payload,
                     payload_digest=sha256(payload).hexdigest())
    with pytest.raises(ValueError, match="compression stream invalid"):
        retrieve_weight_pack(forged, library, "owner", "jump", authorized=True)


def test_original_experiment_is_reproducible_and_holdout_disjoint():
    result = run_original_experiment(samples=40)
    assert result == run_original_experiment(samples=40)
    train = {r["seed"] for r in result["records"] if r["split"] == "train"}
    test = {r["seed"] for r in result["records"] if r["split"] == "holdout"}
    assert not train & test and len(train) == 32 and len(test) == 8
    assert result["summary"]["path_cost_parity"]
    assert not result["memory_promotion_authorized"]


def _reach_extract(worker):
    first = claim(worker)
    policy(worker, first)
    fetched = claim(worker, NOW+2)
    finish(worker, fetched, now=NOW+3, output=sha256(TEXT.encode()).hexdigest(),
           http_status=200, redirects_rechecked=True, body_bytes=len(TEXT))
    return first, claim(worker, NOW+4)


@pytest.mark.parametrize('change', ['owner', 'source_id', 'input_digest', 'output_digest', 'stage', 'at', 'training_authorized', 'evidence_url'])
def test_rehashed_earlier_receipt_cannot_advance_later_stage(library, change):
    worker = setup_worker(library)
    first, extraction = _reach_extract(worker)
    body = json.loads(library.db.execute('SELECT body FROM dragon_almanac_steps WHERE source=? AND stage=0', (first.source_id,)).fetchone()[0])
    if change == 'evidence_url':
        body['evidence']['url'] = 'https://foreign.example/'
    else:
        body[change] = {'at': NOW+100, 'training_authorized': True, 'stage': 'extract',
                       'input_digest': 'f'*64, 'output_digest': 'e'*64}.get(change, 'foreign')
    library.db.execute('UPDATE dragon_almanac_steps SET body=?,digest=? WHERE source=? AND stage=0',
                       (canonical_json(body), canonical_digest(body), first.source_id))
    with pytest.raises(ValueError):
        finish(worker, extraction, now=NOW+5, parser_version='test-v1', span_map_digest='c'*64)
    assert library.db.execute('SELECT stage FROM dragon_almanac_jobs WHERE source=?', (first.source_id,)).fetchone()[0] == 2
    assert library.db.execute('SELECT count(*) FROM dragon_almanac_steps WHERE source=?', (first.source_id,)).fetchone()[0] == 2


def test_corrupt_prefix_denies_new_lease_atomically(library):
    worker = setup_worker(library)
    first = claim(worker); policy(worker, first)
    library.db.execute('DELETE FROM dragon_almanac_steps WHERE source=?', (first.source_id,))
    with pytest.raises(ValueError, match='lineage'):
        claim(worker, NOW+2)
    assert library.db.execute('SELECT state,attempts FROM dragon_almanac_jobs WHERE source=?', (first.source_id,)).fetchone() == ('pending', 0)


def test_registry_metadata_drift_invalidates_active_pipeline(library):
    worker = setup_worker(library)
    first, extraction = _reach_extract(worker)
    raw = library.db.execute('SELECT body FROM dragon_almanac_sources WHERE source=?', (first.source_id,)).fetchone()[0]
    source = json.loads(raw); source['rights'] = 'revoked'
    library.db.execute('UPDATE dragon_almanac_sources SET body=?,digest=? WHERE source=?',
                       (canonical_json(source), canonical_digest(source), first.source_id))
    with pytest.raises(ValueError, match='lineage'):
        finish(worker, extraction, now=NOW+5, parser_version='test-v1', span_map_digest='c'*64)


def test_receipt_prefix_size_and_clock_rollback_are_bounded(library):
    worker = setup_worker(library)
    first = claim(worker); policy(worker, first, NOW+5)
    with pytest.raises(ValueError): claim(worker, NOW+4)
    library.db.execute('UPDATE dragon_almanac_steps SET body=? WHERE source=?', ('x'*32769, first.source_id))
    with pytest.raises(ValueError, match='budget'): claim(worker, NOW+6)


def test_rehashed_denied_policy_cannot_be_laundered_through_extract(library):
    worker = setup_worker(library)
    first, extraction = _reach_extract(worker)
    body = json.loads(library.db.execute('SELECT body FROM dragon_almanac_steps WHERE source=? AND stage=0', (first.source_id,)).fetchone()[0])
    body['evidence']['terms_permitted'] = False
    library.db.execute('UPDATE dragon_almanac_steps SET body=?,digest=? WHERE source=? AND stage=0',
                       (canonical_json(body), canonical_digest(body), first.source_id))
    with pytest.raises(ValueError, match='policy'):
        finish(worker, extraction, now=NOW+5, parser_version='test-v1', span_map_digest='c'*64)
