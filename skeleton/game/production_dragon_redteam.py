"""Dragon challenger for game quality verifiers and allegedly clean evidence."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from .production_quality import QualityGateError, _digest
from .production_deep_gates import audit_deep_candidate


def challenge_quality_verifiers(bundle: Mapping) -> dict:
    """Run independent mutation challenges against every candidate gate.

    The red team does NOT alter real game sources or train model weights.
    Its pass condition is that all mutated candidates become ineligible.
    """
    if not isinstance(bundle, Mapping):
        raise QualityGateError("source-bound quality candidate required")
    original = audit_deep_candidate(bundle)
    if not original["candidate_passed"]:
        raise QualityGateError("Dragon challenger needs a clean baseline, not known failures")
    attacks = (
        ("world_reachability", lambda d: d["world"].update(victory="absent")),
        ("canon_foreign_actor", lambda d: d["story"]["scenes"][0].update(speakers=["forged"])),
        ("asset_digest", lambda d: d["assets"][0].update(sha256="0" * 64) if d["assets"][0]["sha256"] != "0" * 64 else d["assets"][0].update(sha256="1" * 64)),
        ("build_divergence", lambda d: d["builds"][1].update(source_sha256="f" * 64) if d["builds"][1]["source_sha256"] != "f" * 64 else d["builds"][1].update(source_sha256="e" * 64)),
        ("frame_pressure", lambda d: d["frames"][0].update(draw_calls=10_000_000)),
        ("copyright_laundering", lambda d: d["sources"][0].update(reviewed=False)),
        ("gdd_unproven", lambda d: d["design"]["proofs"].clear()),
        ("quest_ending_unearned", lambda d: d["campaign"]["playthroughs"].clear()),
        ("accessibility_omission", lambda d: d["screens"][0].update(subtitles=False)),
        ("controller_parity", lambda d: d["profiles"].pop()),
        ("memory_excess", lambda d: d["envelopes"][0].update(ram_mb=1e9)),
        ("session_chain", lambda d: d["session"].update(head="0" * 64)),
        ("package_missing_entry", lambda d: d["package"].update(entry="forged")),
    )
    evidence = []
    for label, attack in attacks:
        mutated = deepcopy(dict(bundle))
        try:
            attack(mutated)
            result = audit_deep_candidate(mutated)
        except (KeyError, IndexError, QualityGateError) as exc:
            raise QualityGateError("red-team fixture missing attackable source: " + label) from exc
        rejected = not result["candidate_passed"]
        evidence.append({
            "attack": label, "rejected": rejected,
            "candidate_evidence_sha256": result["evidence_digest"],
            "finding_codes": sorted({f["code"] for f in result["findings"]}),
        })
        if not rejected:
            raise QualityGateError("adversarial reviewer accepted forged " + label)
    # Adversary additionally attacks the verifier's own summary rather than source.
    forged = deepcopy(original)
    forged["gates"][0]["passed"] = False
    false_digest = _digest(forged["gates"])
    summary_attack_rejected = false_digest != forged["evidence_digest"]
    if not summary_attack_rejected:
        raise QualityGateError("quality reviewer summary digest did not bind its gates")
    report = {
        "schema": "dragon.production_quality_redteam.v1",
        "source_sha256": bundle["source_sha256"],
        "baseline_digest": original["evidence_digest"],
        "attacks": evidence,
        "summary_tamper_rejected": summary_attack_rejected,
        "all_challenges_rejected": all(x["rejected"] for x in evidence),
        "weights_trained": False,
        "copyright_certified": False,
        "native_engine_executed": False,
        "external_signoff": False,
    }
    return {**report, "receipt_digest": _digest(report)}
