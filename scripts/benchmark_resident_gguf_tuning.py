"""Matched local native tuning qualification; exact token parity, no promotion."""
from __future__ import annotations
import argparse
from dataclasses import fields, replace
import hashlib
import json
import math
from pathlib import Path
import statistics
import time

from skeleton.ai.runtime.inference.competitive_holdout import digest, read_holdout, text_sha
from skeleton.ai.runtime.inference.deployment import LocalModelDeployment
from skeleton.ai.runtime.inference.llama_cpp import LlamaCppModel
from skeleton.ai.runtime.inference.resident_gguf_batch import (
    NativeResidentTuning, ResidentBatchPolicy, ResidentGGUFBatch,
)


def read_candidates(path, expected):
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular local tuning configuration required")
    with path.open("rb") as handle:
        data = handle.read(65537)
    if not 1 <= len(data) <= 65536 or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("tuning configuration byte identity mismatch")
    def unique(pairs):
        value = {}
        for key, entry in pairs:
            if key in value:
                raise ValueError("duplicate tuning field")
            value[key] = entry
        return value
    raw = json.loads(data, object_pairs_hook=unique)
    if not isinstance(raw, dict) or not 1 <= len(raw) <= 7:
        raise ValueError("1..7 tuning profiles required")
    import re
    profiles = {}
    for name, values in raw.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name) or name == "baseline":
            raise ValueError("invalid tuning identifier")
        if not isinstance(values, dict) or not set(values) <= {f.name for f in fields(NativeResidentTuning)}:
            raise ValueError("unapproved tuning field")
        if "tensor_split" in values:
            if not isinstance(values["tensor_split"], list):
                raise ValueError("tensor split must be a JSON array")
            values = dict(values, tensor_split=tuple(values["tensor_split"]))
        profiles[name] = NativeResidentTuning(**values)
    if len({item.digest() for item in profiles.values()} | {NativeResidentTuning().digest()}) != len(profiles)+1:
        raise ValueError("duplicate or neutral candidate")
    return profiles


def summarize(rows, names, repeats, offsets, slots):
    expected = {(n, r, o) for n in names for r in range(repeats) for o in offsets}
    indexed = {}
    for row in rows:
        key = (row["profile"], row["repeat"], row["offset"])
        if (key in indexed or key not in expected or len(row["cases"]) != slots
            or not math.isfinite(row["seconds"]) or row["seconds"] <= 0):
            raise ValueError("invalid measurement row")
        indexed[key] = row
    if set(indexed) != expected or names[0] != "baseline":
        raise ValueError("incomplete matched measurements")
    stable = all(indexed["baseline", r, o]["cases"] == indexed["baseline", 0, o]["cases"]
                 for r in range(repeats) for o in offsets)
    summaries = {}
    for name in names:
        batches = [indexed[name, r, o] for r in range(repeats) for o in offsets]
        times = sorted(b["seconds"] for b in batches)
        mismatches = sum(a != b
                         for row in batches
                         for a, b in zip(row["cases"],
                             indexed["baseline", row["repeat"], row["offset"]]["cases"], strict=True))
        speed = [indexed["baseline", row["repeat"], row["offset"]]["seconds"]/row["seconds"]
                 for row in batches]
        summaries[name] = {"attempts": len(batches)*slots, "parity_eligible": stable and mismatches == 0,
            "output_or_token_mismatches": mismatches,
            "exact": sum(c["exact"] for row in batches for c in row["cases"]),
            "median_paired_wall_speedup": statistics.median(speed),
            "minimum_paired_wall_speedup": min(speed),
            "p95_batch_seconds": times[math.ceil(len(times)*.95)-1]}
    return {"baseline_stable": stable, "summaries": summaries, "rows": rows}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "server", "holdout", "tuning"):
        p.add_argument("--"+name, type=Path, required=True)
        p.add_argument("--"+name+"-sha256", required=True)
    p.add_argument("--server-library", action="append", default=[])
    p.add_argument("--slots", type=int, default=2)
    p.add_argument("--context-per-slot", type=int, required=True)
    p.add_argument("--gpu-layers", type=int, required=True)
    p.add_argument("--memory-bytes", type=int, required=True)
    p.add_argument("--repeats", type=int, choices=(2, 3, 4, 5), default=3)
    p.add_argument("--max-new-tokens", type=int, default=128)
    p.add_argument("--deadline-seconds", type=int, default=3600)
    a = p.parse_args(argv)
    candidates = read_candidates(a.tuning, a.tuning_sha256)
    holdout = read_holdout(a.holdout, a.holdout_sha256)
    policy = ResidentBatchPolicy(a.slots, a.context_per_slot, a.gpu_layers, a.memory_bytes)
    if (len(holdout)%policy.slots or 1+len(holdout)//policy.slots > policy.max_batches
        or len(holdout)*(len(candidates)+1)*a.repeats > 4096
        or not 1 <= a.max_new_tokens <= min(8192, policy.context_per_slot-1)
        or not 1 <= a.deadline_seconds <= 14400):
        p.error("campaign exceeds explicit limits")
    profiles = {"baseline": policy}
    profiles.update({name: replace(policy, tuning=value) for name, value in candidates.items()})
    dep = LocalModelDeployment.load(a.manifest, expected_sha256=a.manifest_sha256)
    model = LlamaCppModel(dep.llama_cpp_config(rehash_artifacts_each_run=True))
    if model.model_digest != dep.execution_model_sha256:
        raise RuntimeError("model identity drift")
    deadline = time.monotonic()+a.deadline_seconds
    names = list(profiles)
    offsets = list(range(0, len(holdout), policy.slots))
    libraries = tuple(tuple(x.split("=", 1)) for x in a.server_library)
    rows = []
    for repeat in range(a.repeats):
        rotation = repeat%len(names)
        for name in names[rotation:]+names[:rotation]:
            if time.monotonic() >= deadline:
                raise TimeoutError("incomplete tuning campaign")
            with ResidentGGUFBatch(model, a.server, a.server_sha256, profiles[name],
                                   runtime_libraries=libraries) as session:
                session.generate(["Output a short readiness response."]*policy.slots, max_new_tokens=1)
                for offset in offsets:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("incomplete tuning campaign")
                    group = holdout[offset:offset+policy.slots]
                    output = session.generate([x["prompt"] for x in group], max_new_tokens=a.max_new_tokens)
                    if (output["model_sha256"] != model.model_digest
                        or output["server_sha256"] != a.server_sha256
                        or output["requested_tuning_sha256"] != profiles[name].tuning.digest()
                        or len(output["results"]) != len(group)):
                        raise RuntimeError("matched native identity mismatch")
                    cases = [{"case_sha256": digest({"id": case["id"], "category": case["category"]}),
                              "exact": result["text"] == case["exact"],
                              "output_sha256": text_sha(result["text"]),
                              "token_ids_sha256": digest(result["token_ids"])}
                             for case, result in zip(group, output["results"], strict=True)]
                    rows.append({"profile": name, "repeat": repeat, "offset": offset,
                        "seconds": output["batch_wall_seconds"], "cases": cases})
    if time.monotonic() >= deadline:
        raise TimeoutError("incomplete tuning campaign")
    report = summarize(rows, names, a.repeats, offsets, policy.slots)
    report.update(schema="skeleton.gguf.matched-tuning.v1", status="operator_measured_not_certified",
        model_sha256=model.model_digest, server_sha256=a.server_sha256,
        manifest_sha256=dep.manifest_digest, holdout_sha256=a.holdout_sha256,
        tuning_file_sha256=a.tuning_sha256, tuning_sha256={n: x.tuning.digest() for n,x in profiles.items()},
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        activation_authorized=False,
        limits=["same model and native binary", "operator holdout", "wall time not kernel speed",
                "deadline stops new admission; individual calls use resident timeout",
                "no physical memory qualification or automatic promotion"])
    report["report_sha256"] = digest(report)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
