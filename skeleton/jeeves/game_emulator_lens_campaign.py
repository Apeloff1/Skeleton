"""Assemble bounded, exact-coverage campaigns from canonical emulator lens-review pages.

All pages remain review proposals; aggregation is not replay authentication,
Dragon observation, adversarial validation or model-weight promotion.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from .game_learning import _digest
from .game_emulator_lens_review import (
    SCHEMA, EmulatorLensReviewError, _all_review_specs,
    review_verified_training_report, validate_training_receipts,
)

MAX_CAMPAIGN_PAGES = 128


class LensCampaignError(EmulatorLensReviewError):
    """A lens page is missing, altered, repeated or has an untrusted outcome."""


def audit_lens_campaign(
    pages: Sequence[dict[str, Any]], *, source_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit full ordered coverage, source pinning, page digests and open lanes.

    Review receipts are structurally checked but cannot independently prove that
    a native core ran or that an observer actually saw the game. No authority
    is granted by a valid review campaign.
    """
    if (not isinstance(pages, (list, tuple)) or not pages
            or len(pages) > MAX_CAMPAIGN_PAGES):
        raise LensCampaignError("bounded, nonempty review page sequence required")

    specs = _all_review_specs()
    expected_keys = tuple(spec.key for spec in specs)
    if len(set(expected_keys)) != len(expected_keys):
        raise LensCampaignError("registered lens identities are duplicated")
    catalog = pages[0].get("catalog_digest") if type(pages[0]) is dict else None
    source = pages[0].get("source_report_digest") if type(pages[0]) is dict else None
    if (type(catalog) is not str or len(catalog) != 64
            or type(source) is not str or len(source) != 64):
        raise LensCampaignError("source and catalog digests are required")

    # Check against the CURRENT canonical catalog. Stale pages cannot
    # masquerade as full coverage after new lenses have been registered.
    canonical_catalog = _digest([
        [spec.key, spec.family.value, spec.role.value, spec.lineage_year,
         spec.minimum_observations, spec.pairwise, spec.sequential]
        for spec in specs
    ])
    if catalog != canonical_catalog:
        raise LensCampaignError("review catalog changed since page generation")

    seen = []
    counts: Counter[str] = Counter()
    page_digests = []
    if source_report is not None:
        validated = validate_training_receipts(source_report)
        if validated["report_digest"] != source:
            raise LensCampaignError("source report differs from reviewed campaign")
    for page in pages:
        if type(page) is not dict:
            raise LensCampaignError("each page must be a canonical object")
        if source_report is not None:
            expected = review_verified_training_report(
                source_report, offset=len(seen), limit=page.get("page_size", 0),
            )
            if page != expected:
                raise LensCampaignError("review page differs from exact source and catalog")
        reported_digest = page.get("review_digest")
        if (type(reported_digest) is not str
                or reported_digest != _digest({
                    key: value for key, value in page.items()
                    if key != "review_digest"
                })):
            raise LensCampaignError("review page digest mismatch")
        records = page.get("reviews")
        if (type(records) is not list or not records or len(records) > 512
                or page.get("offset") != len(seen)
                or page.get("page_size") != len(records)
                or page.get("review_lens_count") != len(records)
                or page.get("catalog_lens_count") != len(expected_keys)
                or page.get("catalog_digest") != catalog
                or page.get("source_report_digest") != source):
            raise LensCampaignError("review page bounds/order/source mismatch")
        if (page.get("independent_dragon_observations") != 0
                or page.get("independent_adversarial_reviews") != 0
                or page.get("actual_neural_parameter_updates_by_review") != 0
                or page.get("production_model_promotion_authorized") is not False):
            raise LensCampaignError("review page claims unverified authority")
        provenance = page.get("source_integrity")
        if (type(provenance) is not dict
                or provenance.get("native_runtime_reexecuted") is not False
                or provenance.get("operator_report_authenticated") is not False):
            raise LensCampaignError("review authenticity cannot be inferred")
        for record in records:
            index = len(seen)
            if type(record) is not dict or index >= len(specs):
                raise LensCampaignError("review campaign exceeds registered lens catalog")
            spec = specs[index]
            if (record.get("lens_key") != spec.key
                    or record.get("family") != spec.family.value
                    or record.get("role") != spec.role.value
                    or record.get("source_report_digest") != source
                    or record.get("review_id") != _digest(
                        [SCHEMA, catalog, source, spec.key]
                    )):
                raise LensCampaignError("lens identity or source evidence diverged")
            dragon = record.get("dragon_observation")
            adversary = record.get("adversarial_review")
            if (type(dragon) is not dict or type(adversary) is not dict
                    or dragon.get("status") !=
                        "awaiting_independent_consent_scoped_observation"
                    or adversary.get("status") !=
                        "awaiting_independent_counterexample_execution"
                    or record.get("evidence_triangulation_complete") is not False
                    or record.get("semantic_interpretation_asserted") is not False
                    or record.get("ai_gradient_updates_by_review") != 0):
                raise LensCampaignError("unreviewed lane cannot claim completion")
            seen.append(spec.key)
            counts[spec.family.value] += 1
        if page.get("next_offset") != (
            len(seen) if len(seen) < len(expected_keys) else None
        ):
            raise LensCampaignError("page continuation is missing or inconsistent")
        page_digests.append(reported_digest)

    if tuple(seen) != expected_keys:
        raise LensCampaignError("lens catalog review campaign is incomplete")
    outcome = {
        "schema_version": "skeleton.game.emulator_lens_campaign_audit.v1",
        "source_report_digest": source,
        "catalog_digest": catalog,
        "lens_count": len(seen),
        "page_count": len(pages),
        "page_digests": page_digests,
        "family_counts": dict(sorted(counts.items())),
        "full_registered_catalog_covered": True,
        "all_review_pages_reconstructed_from_source": source_report is not None,
        "independent_native_replay_verified": False,
        "independent_dragon_observations_verified": 0,
        "independent_adversarial_reviews_verified": 0,
        "model_weights_updated": False,
        "production_model_promotion_authorized": False,
    }
    outcome["audit_digest"] = _digest(outcome)
    return outcome



def assemble_source_pinned_lens_campaign(
    source_report: dict[str, Any], *, page_size: int = 64,
) -> dict[str, Any]:
    """Build + independently reconstruct the entire canonical lens catalog.

    The bounded iterator does not persist review tasks, observe screenshots,
    synthesize independent Dragon testimony, or update model parameters.
    Every generated page is re-derived from the original source report before
    its digest can contribute to the final read-only campaign projection.
    """
    if type(page_size) is not int or not 1 <= page_size <= 512:
        raise LensCampaignError("full lens campaign requires page size 1..512")
    validate_training_receipts(source_report)
    pages = []
    cursor = 0
    while True:
        if len(pages) >= MAX_CAMPAIGN_PAGES:
            raise LensCampaignError("canonical lens catalog exceeds bounded review pages")
        page = review_verified_training_report(
            source_report, offset=cursor, limit=page_size,
        )
        pages.append(page)
        next_offset = page.get("next_offset")
        if next_offset is None:
            break
        if type(next_offset) is not int or next_offset <= cursor:
            raise LensCampaignError("canonical review pagination stalled or moved backward")
        cursor = next_offset
    return audit_lens_campaign(pages, source_report=source_report)
