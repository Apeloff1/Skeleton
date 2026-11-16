"""Execute real pretrained semantic and disk-index diagnostics on a fixed public fixture.

This small, repository-authored diagnostic is not a third-party holdout or
certified benchmark. It reports all observations and no claimed superiority.
"""
from __future__ import annotations
import argparse,hashlib,json,tempfile
from pathlib import Path

from skeleton.retrieval.semantic_config import load_semantic_ranker
from skeleton.retrieval.semantic_long_context import document_spans
from skeleton.retrieval.semantic_eval import evaluate
from skeleton.retrieval.disk_semantic_ann import DiskANNPolicy,build_generation,DiskANN


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    admission=json.loads((a.package/"receipt.json").read_text(encoding="utf-8"))
    cfg=a.package/"semantic.json"
    ranker=load_semantic_ranker(cfg,admission["config_sha256"])
    if admission["ranker_sha256"]!=ranker.identity:
        raise RuntimeError("pretrained profile changed after admission")
    raw=(Path(__file__).resolve().parents[1]/"tests"/"fixtures"/"semantic_public_diagnostic.json").read_bytes()
    dataset=json.loads(raw)
    spans=[]
    for row in dataset["documents"]:
        text=row["text"]
        spans.extend(document_spans(row["id"],hashlib.sha256(text.encode()).hexdigest(),text,
             [(0,0,len(text),text)],ranker.policy))
    report=evaluate(ranker,spans,dataset["questions"],holdout_sha256=hashlib.sha256(raw).hexdigest(),k=3,repeats=2)
    features,_=ranker._features(spans,None,None)
    with tempfile.TemporaryDirectory(prefix="semantic-real-ann-") as tmp:
        root=Path(tmp)
        source=hashlib.sha256(raw).hexdigest()
        created=build_generation(root,"fixture",((s,features[s.identity]) for s in spans),
                 space=ranker.identity,source_snapshot=source,dimension=ranker.encoder.policy.dimension,
                 policy=DiskANNPolicy(shards=4,workers=2,bits=8,bands=8,probes=5,global_candidate_limit=16))
        index=DiskANN(root/"fixture",created["manifest_sha256"],expected_space=ranker.identity,expected_snapshot=source)
        metrics=[]
        for row in dataset["questions"]:
            q=ranker.encoder.query(row["question"])
            hits,proof=index.search(row["question"],q.dense)
            expected={tuple(x) for x in row["expected"]}
            selected={(x.source_id,x.ordinal) for x in hits}
            metrics.append({"case":row["id"],"candidate_recall":len(expected&selected)/len(expected),
                 "shards_searched":proof["shards_searched"],"candidate_count":len(hits)})
    a.output.parent.mkdir(parents=True,exist_ok=True)
    out={"schema":"skeleton.pretrained-semantic-diagnostic.v1","admission":admission,"paired_report":report,
         "ann_candidate_recall":metrics,"third_party_benchmark":False,"production_ready":False}
    with a.output.open("x",encoding="utf-8") as handle:
        json.dump(out,handle,sort_keys=True,indent=2,allow_nan=False);handle.write("\n")
    print(json.dumps({"status":"measured_not_certified","semantic":report["aggregate"]["semantic"],
          "lexical":report["aggregate"]["lexical"],"ann_cases":len(metrics)},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
