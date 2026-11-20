"""Offline, paired confidence calibration with independent binary labels.

Input contains only pinned IDs, confidence, abstentions and metric labels.
It does not import models, prompts, network libraries or activate anything.
Labels and evaluator/model provenance are operator assertions, not signatures.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import statistics

SCHEMA = "skeleton.jeeves.paired-calibration.v1"
MAX_CASES = 4096
MAX_BYTES = 4 * 1024 * 1024
PIN = re.compile(r"[0-9a-f]{64}\Z")


def _pin(value):
    return type(value) is str and PIN.fullmatch(value) is not None


def _hash(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                             allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON field")
        out[key] = value
    return out


def _reject_constant(value):
    raise ValueError("non-finite JSON constant")


def load_pinned(path, expected_sha256):
    if not _pin(expected_sha256) or path.is_symlink() or not path.is_file():
        raise ValueError("explicit pinned local calibration file required")
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("calibration input identity mismatch")
    return json.loads(raw, object_pairs_hook=_unique, parse_constant=_reject_constant)


def _validate(data):
    keys = {"holdout_sha256", "evaluator_sha256", "profiles", "cases"}
    if type(data) is not dict or set(data) != keys:
        raise ValueError("invalid calibration input schema")
    if not all(_pin(data[k]) for k in ("holdout_sha256", "evaluator_sha256")):
        raise ValueError("holdout and independent evaluator pins required")
    profiles = data["profiles"]
    if type(profiles) is not list or len(profiles) != 2:
        raise ValueError("exactly two paired profiles required")
    ids = set()
    for p in profiles:
        if type(p) is not dict or set(p) != {"profile_sha256", "model_sha256", "policy_sha256"}:
            raise ValueError("invalid profile identity")
        if not all(_pin(p[k]) for k in p) or p["profile_sha256"] != _hash({
            "model_sha256": p["model_sha256"], "policy_sha256": p["policy_sha256"]
        }) or p["profile_sha256"] in ids:
            raise ValueError("profile pin mismatch or duplicate")
        ids.add(p["profile_sha256"])
    if data["evaluator_sha256"] in ids or data["evaluator_sha256"] in {
            p["model_sha256"] for p in profiles}:
        raise ValueError("evaluator must be identified separately from generators")
    cases = data["cases"]
    if type(cases) is not list or not 16 <= len(cases) <= MAX_CASES:
        raise ValueError("16–4096 paired holdout cases required")
    seen = set()
    for case in cases:
        if type(case) is not dict or set(case) != {"case_sha256", "stratum", "results"}:
            raise ValueError("invalid calibration case")
        cid = case["case_sha256"]
        if not _pin(cid) or cid in seen or type(case["stratum"]) is not str or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,48}", case["stratum"]):
            raise ValueError("invalid or duplicate holdout case identity")
        seen.add(cid)
        if type(case["results"]) is not dict or set(case["results"]) != ids:
            raise ValueError("complete paired observations required")
        for result in case["results"].values():
            if type(result) is not dict or set(result) != {
                "response_sha256", "confidence_ppm", "correct", "abstained", "elapsed_ms"
            }:
                raise ValueError("invalid labeled outcome")
            if not _pin(result["response_sha256"]):
                raise ValueError("response pin required")
            ppm, correct, abstained, ms = (result[k] for k in (
                "confidence_ppm", "correct", "abstained", "elapsed_ms"))
            if (type(ppm) is not int or not 0 <= ppm <= 1_000_000
                    or type(correct) is not bool or type(abstained) is not bool
                    or type(ms) is not int or not 1 <= ms <= 86_400_000
                    or (abstained and (correct or ppm != 0))):
                raise ValueError("invalid confidence, abstention or measurement")
    if len({c["stratum"] for c in cases}) > 32:
        raise ValueError("too many evaluation strata")
    return profiles, cases


def _wilson(success, count):
    if count == 0:
        return None
    p, z = success/count, 1.95996398454
    denom = 1+z*z/count
    mid = (p+z*z/(2*count))/denom
    radius = z*math.sqrt(p*(1-p)/count+z*z/(4*count*count))/denom
    return [max(0., mid-radius), min(1., mid+radius)]


def _metrics(rows):
    answered = [r for r in rows if not r["abstained"]]
    total = len(rows)
    hit = sum(r["correct"] for r in answered)
    bins = []
    for i in range(10):
        bucket = [r for r in answered
                  if min(9, r["confidence_ppm"]//100_000) == i]
        n = len(bucket)
        bins.append({"bin": i, "count": n, "accuracy": None if not n else
                     sum(r["correct"] for r in bucket)/n,
                     "mean_confidence": None if not n else
                     sum(r["confidence_ppm"] for r in bucket)/(1_000_000*n)})
    ece = (sum(b["count"]*abs(b["accuracy"]-b["mean_confidence"])
               for b in bins if b["count"])/len(answered) if answered else None)
    brier = (statistics.fmean((r["confidence_ppm"]/1_000_000-int(r["correct"]))**2
                             for r in answered) if answered else None)
    curve = []
    for threshold in (0, 250_000, 500_000, 750_000, 900_000, 950_000, 1_000_000):
        selected = [r for r in answered if r["confidence_ppm"] >= threshold]
        right = sum(r["correct"] for r in selected)
        curve.append({"threshold_ppm": threshold, "accepted": len(selected),
                      "coverage": len(selected)/total,
                      "selective_accuracy": right/len(selected) if selected else None,
                      "accuracy_wilson95": _wilson(right, len(selected))})
    latency = sorted(r["elapsed_ms"] for r in rows)
    return {"cases": total, "answered": len(answered), "correct": hit,
            "coverage": len(answered)/total, "all_case_accuracy": hit/total,
            "answered_accuracy": hit/len(answered) if answered else None,
            "answered_accuracy_wilson95": _wilson(hit, len(answered)),
            "brier_answered": brier, "ece10_answered": ece,
            "bins": bins, "risk_coverage": curve,
            "median_ms": statistics.median(latency),
            "p95_ms": latency[math.ceil(.95*total)-1]}


def _pair(a, b):
    # Exact McNemar two-sided test on discordant correctness (abstentions
    # count as unsuccessful); no normal approximation, no unpaired mixing.
    left = sum(x["correct"] and not y["correct"] for x, y in zip(a, b))
    right = sum(y["correct"] and not x["correct"] for x, y in zip(a, b))
    n = left + right
    p = 1.0 if not n else min(1.0, 2*sum(
        math.comb(n, k) for k in range(min(left, right)+1))/(2**n))
    return {"left_only_correct": left, "right_only_correct": right,
            "all_case_accuracy_delta_right_minus_left": (right-left)/len(a),
            "mcnemar_two_sided_exact_p": p,
            "descriptive_only_no_promotion": True}


def evaluate(data):
    profiles, cases = _validate(data)
    labels = [p["profile_sha256"] for p in profiles]
    groups = sorted({c["stratum"] for c in cases})
    all_rows = [[c["results"][label] for c in cases] for label in labels]
    report = {"schema": SCHEMA, "input_sha256": _hash(data),
              "holdout_sha256": data["holdout_sha256"],
              "evaluator_sha256": data["evaluator_sha256"],
              "profiles": profiles,
              "overall": {label: _metrics(rows) for label, rows in zip(labels, all_rows)},
              "paired": _pair(*all_rows),
              "strata": {group: {
                  label: _metrics([c["results"][label] for c in cases if c["stratum"] == group])
                  for label in labels} for group in groups},
              "independent_labels_attested_not_verified": True,
              "production_quality_certified": False, "activation_authorized": False,
              "confidence_not_truth": True}
    report["report_sha256"] = _hash(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args(argv)
    report = evaluate(load_pinned(args.input, args.sha256))
    print(json.dumps(report, sort_keys=True, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
