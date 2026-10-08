"""Captured CrawlDocument -> exact-span evidence and provenance regressions."""
from dataclasses import replace
from hashlib import sha256

import pytest

from skeleton.ai.webcrawler.core import CrawlDocument, FetchResponse, extract_document
from skeleton.ai.webcrawler.dragon_crawl_custody import (
    CapturedSource, CustodyPolicy, LocatedReading, bind_crawl_evidence,
    assure_captured_crawl,
)
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import (
    EvidencePolicy, ProbabilisticKnowledgeDistiller,
)
from skeleton.ai.webcrawler.dragon_provenance_assurance import assure_crawler_evidence
from skeleton.ai.webcrawler.dragon_provenance_registry import ProvenanceRegistry, SourceAttestation


def captured(sid, *, body=None):
    text = body or (
        f"Measurement from {sid}: jump buffering activates on early input. "
        f"Independent measurement recorded by lab {sid}. "
    ) * 3
    url = f"https://{sid}.example/protocol"
    response = FetchResponse(
        url, 200, {"content-type": "text/plain"},
        text.encode("utf-8"), 1700000000.0,
    )
    doc = extract_document(response, url)
    assert doc is not None
    return CapturedSource(sid, doc)


def reading(sid, i, *, start=0, end=28, claim="jump"):
    return LocatedReading(
        sid, f"pass-{i}", claim, True, .9, .9,
        start, end,
    )


def fixture():
    sources = (captured("alpha"), captured("beta"))
    readings = tuple(
        reading(sid, i) for sid in ("alpha", "beta") for i in (1, 2, 3)
    )
    return sources, readings


def bind(sources=None, readings=None, **kwargs):
    a, b = fixture()
    return bind_crawl_evidence(
        "jump", a if sources is None else sources,
        b if readings is None else readings, authorized=True, **kwargs,
    )


def test_exact_spans_and_content_addressed_revisions():
    bundle = bind()
    assert len(bundle.evidence) == 6
    assert len(bundle.sources) == 2
    docs = {s.source_id: s.document for s in fixture()[0]}
    for item in bundle.evidence:
        source = docs[item.source_id]
        assert item.source_revision == source.content_hash
        assert item.observation == source.text[:28]
        assert item.evidence_locator == (
            f"sha256:{source.content_hash}@0:28"
        )
    assert all(len(x[1]) == 64 for x in bundle.document_fingerprints)


def test_end_to_end_custody_prevents_vote_inflation():
    sources, readings = fixture()
    # Both documents have different content hashes and distinct origins.
    bundle = bind(sources, readings)
    report = assure_crawler_evidence(
        "jump", bundle.evidence, bundle.sources, authorized=True,
    )
    assert report.independent_groups == 2
    assert report.candidate_for_review
    assert not report.promotion_authorized


def test_same_content_copy_is_one_independent_cluster():
    text = "One copied source sentence. " * 30
    sources = (captured("alpha", body=text), captured("beta", body=text))
    bundle = bind(sources)
    result = assure_crawler_evidence(
        "jump", bundle.evidence, bundle.sources, authorized=True,
    )
    assert result.independent_groups == 1
    assert not result.candidate_for_review


def test_custody_is_order_invariant():
    sources, readings = fixture()
    left = bind(sources, readings)
    right = bind(tuple(reversed(sources)), tuple(reversed(readings)))
    assert left == right


def test_new_text_revision_changes_fingerprint_and_locator():
    sources, readings = fixture()
    before = bind(sources, readings)
    updated = (captured("alpha", body="A newer source revision. " * 20), sources[1])
    after = bind(updated, readings)
    assert before.custody_fingerprint != after.custody_fingerprint
    assert before.evidence[0].evidence_locator != after.evidence[0].evidence_locator


def test_modified_document_text_without_digest_is_rejected():
    sources, readings = fixture()
    poisoned = replace(sources[0].document, text="Forged evidence text")
    with pytest.raises(ValueError, match="content hash mismatch"):
        bind((replace(sources[0], document=poisoned), sources[1]), readings)


def test_modified_hash_or_acquisition_receipt_is_rejected():
    sources, readings = fixture()
    forged = replace(sources[0].document, content_hash="a" * 64)
    with pytest.raises(ValueError, match="content hash mismatch"):
        bind((replace(sources[0], document=forged), sources[1]), readings)
    forged_receipt = dict(sources[0].document.provenance)
    forged_receipt["content_hash"] = "b" * 64
    forged = replace(sources[0].document, provenance=forged_receipt)
    with pytest.raises(ValueError, match="acquisition provenance mismatch"):
        bind((replace(sources[0], document=forged), sources[1]), readings)


def test_rejected_status_and_wrong_receipt_location():
    sources, readings = fixture()
    receipt = dict(sources[0].document.provenance)
    receipt["status"] = 403
    forged = replace(sources[0].document, provenance=receipt)
    with pytest.raises(ValueError, match="acquisition provenance mismatch"):
        bind((replace(sources[0], document=forged), sources[1]), readings)
    receipt = dict(sources[0].document.provenance)
    receipt["canonical_url"] = "https://wrong.example/"
    forged = replace(sources[0].document, provenance=receipt)
    with pytest.raises(ValueError, match="acquisition provenance mismatch"):
        bind((replace(sources[0], document=forged), sources[1]), readings)


def test_noncanonical_url_and_userinfo_refused():
    sources, readings = fixture()
    mutated = replace(sources[0].document,
                      canonical_url="https://alpha.example/a/../protocol")
    with pytest.raises(ValueError, match="noncanonical"):
        bind((replace(sources[0], document=mutated), sources[1]), readings)
    mutated = replace(sources[0].document,
                      canonical_url="https://alice:secret@alpha.example/protocol")
    with pytest.raises(ValueError, match="credentialed"):
        bind((replace(sources[0], document=mutated), sources[1]), readings)


def test_missing_source_and_cross_claim_fail_closed():
    sources, _ = fixture()
    with pytest.raises(ValueError, match="missing captured"):
        bind(sources, (reading("ghost", 1),))
    with pytest.raises(ValueError, match="cross-claim"):
        bind(sources, (reading("alpha", 1, claim="other"),))


@pytest.mark.parametrize("start,end", [
    (-1, 5), (0, 0), (4, 3), (0, 100000), (True, 5),
])
def test_invalid_spans_rejected(start, end):
    with pytest.raises(ValueError, match="evidence span"):
        bind(readings=(reading("alpha", 1, start=start, end=end),))


def test_duplicate_lens_and_empty_quote_rejected():
    with pytest.raises(ValueError, match="duplicate located"):
        bind(readings=(reading("alpha", 1), reading("alpha", 1)))
    sources, _ = fixture()
    with pytest.raises(ValueError, match="anchored excerpt"):
        bind(
            (captured("alpha", body="  letters " * 20), sources[1]),
            (reading("alpha", 1, start=7, end=8),),
        )


def test_evidence_policy_rejects_nonfinite_confidence():
    sources, _ = fixture()
    evidence = (replace(reading("alpha", 1), confidence=float("nan")),)
    with pytest.raises(ValueError, match="confidence"):
        bind(sources, evidence)


def test_document_bytes_and_quote_boundaries():
    sources, readings = fixture()
    with pytest.raises(ValueError, match="byte budget"):
        bind(sources, readings, policy=CustodyPolicy(max_document_bytes=20))
    with pytest.raises(ValueError, match="anchored excerpt"):
        bind(sources, readings, policy=CustodyPolicy(max_quote_chars=2))


def test_source_and_evidence_budget_boundaries():
    sources, readings = fixture()
    with pytest.raises(ValueError, match="capacity"):
        bind(sources, readings, policy=CustodyPolicy(max_sources=1))
    with pytest.raises(ValueError, match="capacity"):
        bind(sources, readings, policy=CustodyPolicy(max_evidence=3))
    with pytest.raises(ValueError, match="capacity"):
        bind(sources, readings, evidence_policy=EvidencePolicy(max_evidence=5))


def test_per_source_reread_limit_and_parent_custody():
    sources, readings = fixture()
    with pytest.raises(ValueError, match="reread budget"):
        bind(
            sources, readings,
            evidence_policy=EvidencePolicy(max_passes_per_source=2),
        )
    broken = replace(sources[0], parent_source_ids=("missing-parent",))
    with pytest.raises(ValueError, match="undeclared captured source parent"):
        bind((broken, sources[1]), readings)


def test_duplicate_source_and_relationships_fails_closed():
    sources, readings = fixture()
    with pytest.raises(ValueError, match="duplicate captured source"):
        bind((sources[0], sources[0]), readings)
    with pytest.raises(ValueError, match="duplicate source relationship"):
        bind(
            (replace(sources[0], lineage_tokens=("copy", "copy")), sources[1]),
            readings,
        )


def test_no_captured_source_cannot_emit_unverified_reading():
    with pytest.raises(ValueError, match="missing captured source"):
        bind((), (reading("alpha", 1),))
    empty = bind((), ())
    assert empty.evidence == ()
    assert empty.sources == ()


def test_reading_requires_authorized_ingestion_boundary():
    sources, readings = fixture()
    with pytest.raises(PermissionError):
        bind_crawl_evidence(
            "jump", sources, readings, authorized=False,
        )


def test_end_to_end_captured_review_binds_two_receipts():
    sources, readings = fixture()
    review = assure_captured_crawl(
        "jump", sources, readings, authorized=True,
    )
    assert review.assurance.candidate_for_review
    assert review.assurance.belief.readings == len(readings)
    assert review.custody.claim_id == review.assurance.claim_id
    assert review.custody.custody_fingerprint != review.assurance.fingerprint


def test_end_to_end_captured_review_rejects_poisoned_source():
    sources, readings = fixture()
    altered = replace(sources[0].document, text="Poisoned")
    with pytest.raises(ValueError, match="content hash"):
        assure_captured_crawl(
            "jump", (replace(sources[0], document=altered), sources[1]),
            readings, authorized=True,
        )


def test_captured_review_ownership_attestation_merges_copies():
    sources, readings = fixture()
    registry = ProvenanceRegistry((
        SourceAttestation("alpha.example", "single-owner", "",
                          "auditor", "receipt-alpha"),
        SourceAttestation("beta.example", "single-owner", "",
                          "auditor", "receipt-beta"),
    ))
    review = assure_captured_crawl(
        "jump", sources, readings, authorized=True,
        attestation_registry=registry,
    )
    assert review.assurance.independent_groups == 1
    assert not review.assurance.candidate_for_review


def test_public_crawler_api_exposes_captured_audit_without_eager_model_imports():
    from skeleton.ai import webcrawler
    assert webcrawler.bind_crawl_evidence is bind_crawl_evidence
    assert webcrawler.assure_captured_crawl is assure_captured_crawl


@pytest.mark.parametrize("bad_host", [
    "https://metadata.internal/private",
    "https://host.local/private",
    "https://top.test/private",
    "https://unknown.invalid/private",
    "https://localhost.localhost/admin",
    "https://singlelabel/private",
])
def test_captured_origin_disallows_internal_or_test_hosts(bad_host):
    sources, readings = fixture()
    changed = replace(sources[0].document, canonical_url=bad_host)
    with pytest.raises(ValueError, match="untrusted document URL"):
        bind((replace(sources[0], document=changed), sources[1]), readings)


def test_fetched_redirect_to_internal_host_rejected_even_when_receipt_agrees():
    sources, readings = fixture()
    doc = sources[0].document
    bad = "https://metadata.internal/private"
    changed = replace(
        doc, fetched_url=bad,
        provenance={**doc.provenance, "fetched_url": bad},
    )
    with pytest.raises(ValueError, match="untrusted fetched URL"):
        bind((replace(sources[0], document=changed), sources[1]), readings)


@pytest.mark.parametrize("attribute", ["fetched_at", "source_score"])
def test_boolean_acquisition_numbers_are_rejected(attribute):
    sources, readings = fixture()
    bad = replace(sources[0].document, **{attribute: True})
    if attribute == "fetched_at":
        bad = replace(
            bad, provenance={**bad.provenance, "fetched_at": True},
        )
    with pytest.raises(ValueError, match="invalid"):
        bind((replace(sources[0], document=bad), sources[1]), readings)


def test_acquisition_receipt_changes_invalidate_custody_digest():
    sources, readings = fixture()
    initial = bind(sources, readings)
    doc = sources[0].document
    revised = replace(
        doc, fetched_at=doc.fetched_at + 30.0,
        provenance={**doc.provenance, "fetched_at": doc.fetched_at + 30.0},
    )
    rebind = bind((replace(sources[0], document=revised), sources[1]), readings)
    assert initial.document_fingerprints == rebind.document_fingerprints
    assert initial.acquisition_fingerprints != rebind.acquisition_fingerprints
    assert initial.custody_fingerprint != rebind.custody_fingerprint
    assert initial.evidence == rebind.evidence


def test_fetched_url_change_invalidate_custody_digest():
    sources, readings = fixture()
    doc = sources[0].document
    new_url = "https://cdn.example/updated-copy"
    new_doc = replace(
        doc, fetched_url=new_url,
        provenance={**doc.provenance, "fetched_url": new_url},
    )
    changed = bind((replace(sources[0], document=new_doc), sources[1]), readings)
    initial = bind(sources, readings)
    assert changed.custody_fingerprint != initial.custody_fingerprint


def test_noncanonical_or_non_json_acquisition_receipt_fails_closed():
    sources, readings = fixture()
    doc = sources[0].document
    changed = replace(
        doc, provenance={**doc.provenance, "unexpected_object": object()},
    )
    with pytest.raises((TypeError, ValueError)):
        bind((replace(sources[0], document=changed), sources[1]), readings)
