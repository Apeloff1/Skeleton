"""Explicit live competitive qualification with independently read local custody.

This is a paired test of actual installed model artifacts on identical cases
and protocol. It does not authorize promotion or certify general intelligence.
The caller supplies dedicated local model services and their private DBs.
No synthetic replies, hosted inference, or leaderboard substitutions.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from hashlib import sha256
import math
from pathlib import Path
import re
import secrets
import sqlite3
import statistics
import sys
from urllib.parse import quote

from skeleton.ai.model_runtime.offline_chat import _digest_request,_validate_private_sqlite_path
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
from skeleton.app.jeeves_chat_benchmark import (
    LocalChatClient,CaptureRejected,read_token,run,_write_new,_REPORT_LIMIT,
)
from skeleton.app.jeeves_chat_quality import qualify,compare,_hash,_stable,_strict_json
from skeleton.app.jeeves_chat_eval_scenarios import build_suite,inventory
from skeleton.app.jeeves_deliberation import Selection,bind_request,validate_receipt
from skeleton.app.local_ai import _strict_context_digest

SHA=re.compile(r"[a-f0-9]{64}\Z")
ID=re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
HEX=lambda value: type(value) is str and SHA.fullmatch(value) is not None
IDENT=lambda value: type(value) is str and ID.fullmatch(value) is not None
MAX_TURNS=4000


class CompetitiveRejected(ValueError):
    pass


def _fail(condition,message):
    if condition:
        raise CompetitiveRejected(message)


def _integer(value,lower,upper):
    return type(value) is int and lower<=value<=upper


def _read(path):
    with Path(path).open("rb") as handle:
        raw=handle.read(_REPORT_LIMIT+1)
    _fail(len(raw)>_REPORT_LIMIT,"capture exceeds qualification byte limit")
    try:
        data=_strict_json(raw.decode("utf-8"))
    except (ValueError,UnicodeError,RecursionError):
        raise CompetitiveRejected("invalid capture JSON") from None
    _fail(type(data) is not dict,"capture must be an object")
    return data


def _index(rows,fields,maximum):
    _fail(type(rows) is not list or len(rows)>maximum,"invalid qualification inventory")
    result={}
    for row in rows:
        _fail(type(row) is not dict,"invalid qualification row")
        try:
            key=tuple(row[name] for name in fields)
            _fail(key in result,"duplicate qualification row")
            result[key]=row
        except (KeyError,TypeError):
            raise CompetitiveRejected("invalid qualification row identity") from None
    return result


def validate_capture(cases,capture):
    """Recompute the whole deterministic score from exact captured answers."""
    cases=tuple(cases)
    expected=inventory(cases)
    _fail(capture.get("schema")!="skeleton.jeeves.local-benchmark-capture.v1"
          or capture.get("live_endpoint_observed") is not True
          or capture.get("independent_receipt_verification") is not False
          or capture.get("suite_inventory")!=expected,
          "not a complete captured live inventory")
    model=capture.get("model_digest");tokenizer=capture.get("tokenizer_digest")
    protocol=capture.get("protocol_descriptor")
    _fail(not HEX(model) or not HEX(tokenizer) or type(protocol) is not dict,"missing model/protocol identity")
    fields={"schema","max_output_tokens","require_full_history","grounded",
            "one_clean_session_per_case","system_prompt","retries"}
    if "deliberation" in protocol:fields.add("deliberation")
    _fail(set(protocol)!=fields or protocol["schema"]!="skeleton.jeeves.local-benchmark-protocol.v1"
          or not _integer(protocol["max_output_tokens"],1,8192)
          or type(protocol["require_full_history"]) is not bool
          or protocol["grounded"] is not False or protocol["one_clean_session_per_case"] is not True
          or protocol["system_prompt"] is not None or type(protocol["retries"]) is not int
          or protocol["retries"]!=0 or _hash(_stable(protocol))!=capture.get("protocol_digest"),
          "unmatched or unsafe competitive protocol")
    if "deliberation" in protocol:
        from skeleton.app.jeeves_deliberation import Policy
        policy=Policy.parse(protocol["deliberation"])
        _fail(bool(policy.memory_pins) or protocol["require_full_history"]!=(policy.history_mode=="preserve"),
              "benchmark protocol contains inappropriate memory or retention")
        policy.stages(protocol["max_output_tokens"])
    else:
        _fail(protocol["require_full_history"] is not True,"ordinary benchmark must preserve full history")
    registry={case.case_id:case for case in cases}
    expected_turns={(case.case_id,i) for case in cases for i in range(len(case.turns))}
    _fail(len(expected_turns)>MAX_TURNS,"use disjoint bounded benchmark shards")
    captured=_index(capture.get("captures"),("case_id","turn_index"),MAX_TURNS)
    actual=_index(capture.get("turn_custody"),("case_id","turn_index"),MAX_TURNS)
    sessions=_index(capture.get("sessions"),("case_id",),MAX_TURNS)
    _fail(set(captured)!=expected_turns or set(actual)!=expected_turns
          or set(sessions)!={(key,) for key in registry},"incomplete paired source inventory")
    ids=set();request_ids=set()
    for (case_id,),item in sessions.items():
        sid=item.get("session_id")
        _fail(set(item)!={"case_id","session_id"} or not IDENT(sid) or sid in ids,
              "duplicate or invalid benchmark session")
        ids.add(sid)
    for key,row in actual.items():
        observed=captured[key]
        _fail(set(row)!={"case_id","turn_index","session_id","request_id","revision",
                        "input_tokens","output_tokens","elapsed_ns","answer_sha256","execution_receipt_digest"}
              or row["session_id"]!=sessions[(key[0],)]["session_id"]
              or not IDENT(row["request_id"]) or row["request_id"] in request_ids
              or type(row["revision"]) is not int or row["revision"]!=key[1]+1
              or not _integer(row["input_tokens"],1,2**31-1)
              or not _integer(row["output_tokens"],1,protocol["max_output_tokens"])
              or not _integer(row["elapsed_ns"],1,86400*10**9)
              or row["answer_sha256"]!=observed["answer_sha256"]
              or row["execution_receipt_digest"]!=observed["execution_receipt_digest"],
              "invalid measured turn identity or usage")
        request_ids.add(row["request_id"])
    report=qualify(cases,capture["captures"],model_digest=model,protocol_digest=capture["protocol_digest"])
    _fail(report!=capture.get("report"),"captured score does not reproduce from answers")
    return registry,captured,actual,sessions,report


def _database(path):
    path=Path(path).absolute()
    _fail(not path.is_file(),"existing private benchmark database required")
    # Reuse canonical owner-only SQLite path/journal validation. Unlike
    # OfflineChatStore construction, this path never creates/migrates tables.
    for sidecar,required in ((path,True),(Path(str(path)+"-wal"),False),
                            (Path(str(path)+"-shm"),False),(Path(str(path)+"-journal"),False)):
        _validate_private_sqlite_path(sidecar,main=required)
    connection=sqlite3.connect("file:"+quote(str(path),safe="/:")+"?mode=ro",uri=True,timeout=5)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("BEGIN")
        return connection
    except BaseException:
        connection.close()
        raise


def audit_database(cases,capture,database):
    """Match every turn against a separate read-only SQLite snapshot.

    Custody verifies exactly what the application committed; an attacker
    with write access to all records could forge them. It is not a hardware
    signature or independent inference attestation.
    """
    registry,captured,actual,sessions,report=validate_capture(cases,capture)
    model=capture["model_digest"];tokenizer=capture["tokenizer_digest"]
    protocol=capture["protocol_descriptor"]
    use_deliberation="deliberation" in protocol
    declared_sidecars={ }
    if use_deliberation:
        declared_sidecars=_index(capture.get("deliberation_receipts"),("case_id","turn_index"),MAX_TURNS)
        _fail(set(declared_sidecars)!=set(actual),"missing declared deliberation receipt inventory")
    else:
        _fail(bool(capture.get("deliberation_receipts")),"unexpected deliberation receipt inventory")
    connection=_database(database)
    bound=[]
    try:
        for (case_id,),session in sorted(sessions.items()):
            sid=session["session_id"];case=registry[case_id]
            saved=connection.execute(
                "SELECT model_digest,tokenizer_digest,revision,transcript_json "
                "FROM offline_sessions WHERE session_id=?",(sid,)).fetchone()
            _fail(saved is None or saved[:3]!=(model,tokenizer,len(case.turns)),
                  "database session/model identity differs from capture")
            from skeleton.ai.model_runtime.chat_protocol import ChatTranscript
            transcript=ChatTranscript.from_json(saved[3])
            transcript.validate_turn_order()
            messages=transcript.to_list()
            expected=[]
            for i,spec in enumerate(case.turns):
                answer=captured[(case_id,i)]["answer"]
                expected.extend([{"role":"user","content":spec.prompt},{"role":"assistant","content":answer}])
            _fail(messages!=expected,"exact database transcript differs from captured conversation")
            rows=connection.execute(
                "SELECT t.request_id,t.request_digest,t.revision,t.text,t.output_digest,t.prompt_tokens,"
                "t.generated_tokens,t.grounded,t.runtime_receipt_required,t.deliberation_required,"
                "e.model_digest,e.tokenizer_digest,e.revision,e.output_sha256,e.execution_receipt_digest,"
                "d.receipt_json,d.receipt_sha256 "
                "FROM offline_turns t LEFT JOIN offline_turn_execution_receipts e "
                "ON t.session_id=e.session_id AND t.request_id=e.request_id "
                "LEFT JOIN offline_turn_deliberation d ON t.session_id=d.session_id AND t.request_id=d.request_id "
                "WHERE t.session_id=? ORDER BY t.revision",(sid,)).fetchall()
            _fail(len(rows)!=len(case.turns),"database turn inventory differs")
            extra=connection.execute("SELECT count(*) FROM offline_turn_evidence WHERE session_id=?",(sid,)).fetchone()[0]
            _fail(extra!=0,"unexpected grounded evidence in controlled ungrounded benchmark")
            prior=()
            for i,(row,spec) in enumerate(zip(rows,case.turns)):
                captured_row=captured[(case_id,i)];observed=actual[(case_id,i)]
                rid,request,rev,answer,output,prompt_tokens,generated,grounded,required,deliberated,em,et,er,eo,execution,encoded,sidecar_sha=row
                _fail((rid,rev,answer,output,prompt_tokens,generated)!=(observed["request_id"],i+1,
                    captured_row["answer"],observed["answer_sha256"],observed["input_tokens"],observed["output_tokens"])
                    or grounded!=0 or required!=1 or deliberated!=int(use_deliberation)
                    or (em,et,er,eo,execution)!=(model,tokenizer,rev,output,observed["execution_receipt_digest"])
                    or _hash(answer)!=output,"database execution receipt or usage mismatch")
                base=_strict_context_digest(_digest_request(spec.prompt,
                    GenerationConfig(max_new_tokens=protocol["max_output_tokens"])),protocol["require_full_history"])
                if use_deliberation:
                    from skeleton.app.jeeves_deliberation import Policy
                    _fail(type(encoded) is not str or _hash(encoded)!=sidecar_sha,
                          "database deliberation sidecar corruption")
                    sidecar=_strict_json(encoded)
                    selected=Selection(Policy.parse(protocol["deliberation"]),i,sidecar["plan"]["plan_sha256"])
                    _fail(bind_request(base,selected)!=request,"database deliberation request mismatch")
                    validate_receipt(sidecar,session_id=sid,request_id=rid,revision=rev,
                        model_digest=model,tokenizer_digest=tokenizer,request_digest=request,
                        output_digest=output,execution_digest=execution,question=spec.prompt,
                        history=prior,instructions="",prompt_tokens=prompt_tokens,generated_tokens=generated)
                    declared=declared_sidecars[(case_id,i)]
                    _fail(declared.get("receipt_sha256")!=sidecar["sha256"]
                          or declared.get("plan_sha256")!=selected.plan_sha256
                          or declared.get("total_input_tokens")!=sidecar["total_input_tokens"]
                          or declared.get("total_output_tokens")!=sidecar["total_output_tokens"],
                          "capture deliberation usage or receipt differs from durable authority")
                else:
                    _fail(base!=request or encoded is not None or sidecar_sha is not None,
                          "ordinary benchmark request identity mismatch")
                bound.append({"case_id":case_id,"turn_index":i,"session_id":sid,"request_id":rid,
                              "request_digest":request,"execution_receipt_digest":execution,
                              "output_sha256":output})
                prior+=(("user",spec.prompt),("assistant",answer))
    finally:
        connection.rollback();connection.close()
    result={"schema":"skeleton.jeeves.competitive-db-audit.v1","model_digest":model,
            "tokenizer_digest":tokenizer,"protocol_digest":capture["protocol_digest"],
            "suite_sha256":report["suite_sha256"],"report_sha256":report["report_sha256"],
            "capture_sha256":_hash(_stable(capture)),"verified_turn_count":len(bound),
            "bound_turns_sha256":_hash(_stable(bound)),
            "read_only_sqlite_custody_verified":True,
            "independent_physical_inference_attestation":False,"semantic_quality_certified":False}
    result["sha256"]=_hash(_stable(result))
    return result


def _quantiles(values):
    ordered=sorted(values)
    def nearest(q):
        return ordered[max(0,math.ceil(len(ordered)*q)-1)]
    return {"count":len(ordered),"min":ordered[0],"median":statistics.median(ordered),
            "p95":nearest(.95),"max":ordered[-1]}


def _mcnemar(left_only,right_only):
    # Paired two-sided exact sign/binomial test restricted to discordant
    # independent case outcomes. Multi-turn within a case is not IID.
    n=left_only+right_only
    if not n:return 1.0
    k=min(left_only,right_only)
    # Exact integer numerators avoid overflow/underflow of binomial terms.
    return min(1.0,(2*sum(math.comb(n,i) for i in range(k+1)))/(1<<n))


def compare_audited(cases,left,right,left_db,right_db):
    cases=tuple(cases)
    _fail(left.get("model_digest")==right.get("model_digest"),
          "competitive models must have distinct exact artifact identities")
    _fail(Path(left_db).resolve()==Path(right_db).resolve(),
          "use separate dedicated model workspaces")
    left_audit=audit_database(cases,left,left_db)
    right_audit=audit_database(cases,right,right_db)
    # The established compare routine refuses cross-suite/protocol deltas.
    basic=compare(left["report"],right["report"])
    lrows=_index(left["report"]["turn_results"],("case_id","turn_index"),MAX_TURNS)
    rrows=_index(right["report"]["turn_results"],("case_id","turn_index"),MAX_TURNS)
    counts={"both_pass":0,"left_only":0,"right_only":0,"both_fail":0,"unscored":0}
    for case in cases:
        l=[lrows[(case.case_id,i)]["deterministic_passed"] for i in range(len(case.turns))]
        r=[rrows[(case.case_id,i)]["deterministic_passed"] for i in range(len(case.turns))]
        if not any(x is not None for x in l):
            counts["unscored"]+=1;continue
        lp=all(x is not False for x in l);rp=all(x is not False for x in r)
        counts["both_pass" if lp and rp else "left_only" if lp else "right_only" if rp else "both_fail"]+=1
    def measured(capture):
        rows=capture["turn_custody"]
        tokens=sum(row["output_tokens"] for row in rows)
        elapsed=sum(row["elapsed_ns"] for row in rows)
        return {"turns":len(rows),"input_tokens":sum(row["input_tokens"] for row in rows),
                "final_output_tokens":tokens,"total_wall_seconds":elapsed/1e9,
                "turn_latency_ms":_quantiles([row["elapsed_ns"]/1e6 for row in rows]),
                "final_output_tokens_per_wall_second":tokens*1e9/elapsed,
                "hardware_equivalence_certified":False,
                "timing_independently_attested":False}
    result={"schema":"skeleton.jeeves.competitive-qualification.v1",
            "matched_scores":basic,"left_database_audit":left_audit,"right_database_audit":right_audit,
            "case_level_outcomes":counts,
            "paired_case_exact_two_sided_p":_mcnemar(counts["left_only"],counts["right_only"]),
            "statistical_independence_of_generated_case_variants_certified":False,
            "left_measurements":measured(left),"right_measurements":measured(right),
            "scope":"matched deterministic checks; blind semantic review still required",
            "human_semantic_review_complete":False,"general_competitive_superiority_certified":False,
            "model_promotion_authorized":False}
    result["sha256"]=_hash(_stable(result))
    return result


def blind_package(cases,left,right):
    """Prepare blind semantic review questions; separate secret mapping.
    No rating is fabricated; the reviewer may abstain.
    """
    registry,lrows,_,_,lreport=validate_capture(cases,left)
    _,rrows,_,_,rreport=validate_capture(cases,right)
    compare(lreport,rreport)
    _fail(left["model_digest"]==right["model_digest"],"distinct models required")
    review=[];mapping=[];package_bytes=0
    for case_id,case in sorted(registry.items()):
        for index,spec in enumerate(case.turns):
            if not spec.human_rubric:
                continue
            key=(case_id,index)
            swapped=bool(secrets.randbits(1))
            a,b=(rrows[key],lrows[key]) if swapped else (lrows[key],rrows[key])
            review_id=secrets.token_hex(16)
            review.append({"review_id":review_id,"case_id":case_id,"turn_index":index,
                           "prior_prompts":[t.prompt for t in case.turns[:index]],
                           "question":spec.prompt,"rubric":spec.human_rubric,
                           "answer_a":a["answer"],"answer_b":b["answer"],
                           "answer_history_a":[(rrows if swapped else lrows)[(case_id,i)]["answer"]
                                                 for i in range(index)],
                           "answer_history_b":[(lrows if swapped else rrows)[(case_id,i)]["answer"]
                                                 for i in range(index)]})
            package_bytes+=len(_stable(review[-1]).encode("utf-8"))
            _fail(package_bytes>32*1024*1024,"blind review exceeds private package size; use smaller case shards")
            mapping.append({"review_id":review_id,"a_model_digest":a["model_digest"],
                            "b_model_digest":b["model_digest"],
                            "a_answer_sha256":a["answer_sha256"],"b_answer_sha256":b["answer_sha256"]})
    _fail(not review,"suite has no human rubric turns")
    public={"schema":"skeleton.jeeves.blind-review-package.v1","items":review}
    public["sha256"]=_hash(_stable(public))
    private={"schema":"skeleton.jeeves.blind-review-map.v1",
             "package_sha256":public["sha256"],"left_report_sha256":lreport["report_sha256"],
             "right_report_sha256":rreport["report_sha256"],"mapping":mapping}
    private["sha256"]=_hash(_stable(private))
    return public,private


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left-db",type=Path,required=True)
    parser.add_argument("--right-db",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--left-capture",type=Path,required=True)
    parser.add_argument("--right-capture",type=Path,required=True)
    parser.add_argument("--seed",type=int,default=0)
    parser.add_argument("--generated-start",type=int,default=0)
    parser.add_argument("--generated-count",type=int,default=0)
    parser.add_argument("--long-turns",type=int,default=0)
    parser.add_argument("--no-baseline",action="store_true")
    parser.add_argument("--execute",action="store_true",
                        help="Perform actual live inference on both local dedicated services.")
    parser.add_argument("--left-port",type=int)
    parser.add_argument("--right-port",type=int)
    parser.add_argument("--left-token",type=Path)
    parser.add_argument("--right-token",type=Path)
    parser.add_argument("--left-model-digest")
    parser.add_argument("--right-model-digest")
    parser.add_argument("--output-tokens",type=int,default=512)
    parser.add_argument("--model-timeout",type=int,default=900)
    parser.add_argument("--max-seconds",type=int,default=7200)
    parser.add_argument("--blind-package",type=Path)
    parser.add_argument("--blind-map",type=Path)
    args=parser.parse_args(argv)
    try:
        cases=build_suite(seed=args.seed,start=args.generated_start,count=args.generated_count,
                          include_baseline=not args.no_baseline,long_turns=args.long_turns)
        _fail(args.output.exists() or (args.blind_package is None)!=(args.blind_map is None),
              "explicit new report and paired blind destinations required")
        if args.execute:
            _fail(not all((args.left_port,args.right_port,args.left_token,args.right_token))
                  or args.left_port==args.right_port or not HEX(args.left_model_digest)
                  or not HEX(args.right_model_digest) or args.left_model_digest==args.right_model_digest
                  or args.left_capture.exists() or args.right_capture.exists(),
                  "two distinct live local model services and new capture files required")
            for db in (args.left_db,args.right_db):
                test=_database(db);test.close()
            _fail(args.left_db.resolve()==args.right_db.resolve(),"dedicated independent workspaces required")
            # Alternate whole-model run order by seed; no timing-equivalence
            # claim because endpoint hardware and thermal state may differ.
            endpoints=[
                (args.left_port,args.left_token,args.left_model_digest,args.left_capture),
                (args.right_port,args.right_token,args.right_model_digest,args.right_capture)]
            if args.seed%2:endpoints.reverse()
            for port,token,model,destination in endpoints:
                client=LocalChatClient(port,read_token(token),args.model_timeout)
                captured=run(client,output_tokens=args.output_tokens,max_seconds=args.max_seconds,
                             model_digest=model,cases=cases)
                _write_new(destination,captured)
        left,right=_read(args.left_capture),_read(args.right_capture)
        result=compare_audited(cases,left,right,args.left_db,args.right_db)
        _write_new(args.output,result)
        if args.blind_package is not None:
            public,private=blind_package(cases,left,right)
            _write_new(args.blind_package,public);_write_new(args.blind_map,private)
        print("Matched real-capture custody comparison written; no general superiority or promotion claim.")
        return 0
    except (CompetitiveRejected,CaptureRejected,OSError,ValueError,RuntimeError,KeyError,TypeError,sqlite3.Error):
        print("Competitive qualification held: live models, matched complete suite, database custody or report unavailable.",
              file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
