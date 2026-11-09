"""Measured evidence extension on the existing EvaluationLedger authority."""

from __future__ import annotations

import math
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict

from .evaluation import (
    EvaluationCase,
    EvaluationLedger,
    EvaluationResult,
    EvaluationSuite,
    VerifierReport,
    evaluation_case_passes,
)
from .verifier import (
    MAX_CASE_BYTES,
    MAX_CASES,
    MAX_RECORD_BYTES,
    MAX_RUN_EVIDENCE_BYTES,
    LocalVerifier,
    MeasuredVerifierError,
    MeasuredVerifierQualification,
    MeasuredVerifierReceipt,
    VerifierGatePolicy,
    _issued_writer_capability,
    canonical,
    decode,
    derive_metrics,
    digest,
    integer,
    parse_verifier_output,
    qualification_reasons,
    sha,
    text,
    validate_suite,
)


def _keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise MeasuredVerifierError(name + " has unsupported evidence fields")


def _suite(payload):
    _keys(
        payload,
        {"suite_id", "version", "cases", "population", "contamination_fingerprint", "suite_digest"},
        "suite",
    )
    if not isinstance(payload["cases"], list) or not 1 <= len(payload["cases"]) <= MAX_CASES:
        raise MeasuredVerifierError("suite case count exceeds bound")
    cases = []
    for case in payload["cases"]:
        _keys(case, {"case_id", "prompt", "expected_substring", "max_output_tokens"}, "suite case")
        cases.append(EvaluationCase(**case))
    suite = EvaluationSuite(
        **{
            **{key: value for key, value in payload.items() if key not in {"cases", "suite_digest"}},
            "cases": tuple(cases),
        }
    )
    validate_suite(suite)
    if suite.digest != payload["suite_digest"] or suite.as_dict() != payload:
        raise MeasuredVerifierError("immutable suite digest mismatch")
    return suite


def _source(payload):
    _keys(
        payload,
        {
            "model_id",
            "model_digest",
            "runtime_digest",
            "training_identity",
            "training_identity_digest",
            "document_fingerprints",
            "corpus_digests",
            "document_count",
        },
        "model source",
    )
    text(payload["model_id"], "model_id")
    for name in ("model_digest", "runtime_digest", "training_identity_digest"):
        sha(payload[name], name)
    integer(payload["document_count"], "document count", 1, 8192)
    fingerprints = payload["document_fingerprints"]
    if (
        not isinstance(fingerprints, list)
        or not 1 <= len(fingerprints) <= payload["document_count"]
        or fingerprints != sorted(set(fingerprints))
    ):
        raise MeasuredVerifierError("training document fingerprints are invalid")
    for value in fingerprints:
        sha(value, "training document fingerprint")
    corpora = payload["corpus_digests"]
    if not isinstance(corpora, list) or not 1 <= len(corpora) <= 128:
        raise MeasuredVerifierError("training corpus digest count exceeds bound")
    for value in corpora:
        sha(value, "corpus_digest")
    identity = payload["training_identity"]
    if digest(identity) != payload["training_identity_digest"]:
        raise MeasuredVerifierError("training identity digest mismatch")
    if not isinstance(identity, dict):
        raise MeasuredVerifierError("training identity is malformed")
    if identity.get("kind") == "model_program":
        from skeleton.learning.model_program import TrainingReceipt

        _keys(identity, {"kind", "receipt"}, "issued training identity")
        receipt = TrainingReceipt(**identity["receipt"])
        if (
            receipt.as_dict() != identity["receipt"]
            or list(receipt.dataset_digests) != corpora
            or receipt.model_digest != payload["model_digest"]
            or receipt.model_id != payload["model_id"]
        ):
            raise MeasuredVerifierError("training receipt source identity mismatch")
    elif identity.get("kind") == "durable_training":
        _keys(
            identity,
            {"kind", "artifact", "manifest_digest", "binding_digest", "dataset_authority_epoch"},
            "durable training identity",
        )
        sha(identity["manifest_digest"], "manifest_digest")
        sha(identity["binding_digest"], "binding_digest")
        integer(identity["dataset_authority_epoch"], "dataset authority epoch")
        artifact = identity["artifact"]
        if (
            not isinstance(artifact, dict)
            or artifact.get("model_digest") != payload["model_digest"]
            or artifact.get("model_id") != payload["model_id"]
            or artifact.get("run_manifest_digest") != identity["manifest_digest"]
            or corpora != [artifact.get("corpus_digest")]
            or artifact.get("document_count") != payload["document_count"]
        ):
            raise MeasuredVerifierError("durable artifact source identity mismatch")
        base = {
            "run_id",
            "run_manifest_digest",
            "dataset_digest",
            "model_id",
            "model_digest",
            "checkpoint_digest",
            "corpus_digest",
            "document_count",
        }
        neural = {
            "initial_model_digest",
            "initial_loss",
            "final_loss",
            "epochs",
            "update_count",
            "token_count",
            "training_bytes",
            "training_receipt_digest",
        }
        if set(artifact) not in (base, base | neural):
            raise MeasuredVerifierError("unsupported durable artifact fields")
        for key, value in artifact.items():
            if key.endswith("digest"):
                sha(value, key)
            elif key in {"run_id", "model_id"}:
                text(value, key)
            elif key in {"initial_loss", "final_loss"}:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0
                ):
                    raise MeasuredVerifierError("durable training loss is invalid")
            else:
                integer(value, key, 1)
    else:
        raise MeasuredVerifierError("unknown training authority kind")


def validate_binding(binding):
    _keys(
        binding,
        {
            "schema_version",
            "candidate",
            "baseline",
            "verifier",
            "suite",
            "seed",
            "policy",
            "shared_training_fingerprints",
        },
        "measured run binding",
    )
    if integer(binding["schema_version"], "binding schema", 1, 1) != 1:
        raise MeasuredVerifierError("unsupported binding schema")
    integer(binding["seed"], "seed", maximum=(1 << 63) - 1 - MAX_CASES * 4)
    for role in ("candidate", "baseline", "verifier"):
        _source(binding[role])
    if len({binding[role]["model_digest"] for role in ("candidate", "baseline", "verifier")}) != 3:
        raise MeasuredVerifierError("local verifier must be independent of both generators")
    _keys(binding["policy"], asdict(VerifierGatePolicy()), "gate policy")
    policy = VerifierGatePolicy(**binding["policy"])
    if asdict(policy) != binding["policy"]:
        raise MeasuredVerifierError("gate policy must be normalized")
    suite = _suite(binding["suite"])
    import hashlib

    def fingerprint(value):
        return hashlib.sha256(" ".join(value.casefold().split()).encode("utf-8")).hexdigest()

    heldout = {fingerprint(case.prompt) for case in suite.cases} | {
        fingerprint(case.prompt + "\n" + case.expected_substring) for case in suite.cases
    }
    if any(
        heldout.intersection(binding[role]["document_fingerprints"])
        for role in ("candidate", "baseline", "verifier")
    ):
        raise MeasuredVerifierError("stored run has held-out training contamination")
    shared = sorted(
        set(binding["verifier"]["document_fingerprints"])
        & (
            set(binding["candidate"]["document_fingerprints"])
            | set(binding["baseline"]["document_fingerprints"])
        )
    )
    if shared != binding["shared_training_fingerprints"]:
        raise MeasuredVerifierError("shared training fingerprint evidence mismatch")
    return suite, policy


def _measurement(payload, *, prompt, max_tokens, seed, model_digest):
    _keys(
        payload,
        {"input_digest", "output", "input_tokens", "output_tokens", "elapsed_ns", "model_digest"},
        "actual inference measurement",
    )
    if (
        payload["input_digest"] != digest({"prompt": prompt, "max_output_tokens": max_tokens, "seed": seed})
        or payload["model_digest"] != model_digest
    ):
        raise MeasuredVerifierError("actual inference input/model identity mismatch")
    if not isinstance(payload["output"], str) or len(payload["output"].encode("utf-8")) > 65536:
        raise MeasuredVerifierError("actual answer exceeds byte bound")
    integer(payload["input_tokens"], "actual input tokens", maximum=1_000_000)
    integer(payload["output_tokens"], "actual output tokens", maximum=max_tokens)
    integer(payload["elapsed_ns"], "actual elapsed nanoseconds")


def validate_case(row, index, binding, suite):
    _keys(row, {"case_id", "index", "candidate", "baseline"}, "measured case")
    case = suite.cases[index]
    if integer(row["index"], "case index", maximum=MAX_CASES - 1) != index or row["case_id"] != case.case_id:
        raise MeasuredVerifierError("measured case sequence/identity mismatch")
    for offset, role in enumerate(("candidate", "baseline")):
        sample = row[role]
        _keys(sample, {"answer", "judgment", "gold"}, "labeled measured sample")
        _measurement(
            sample["answer"],
            prompt=case.prompt,
            max_tokens=case.max_output_tokens,
            seed=binding["seed"] + index * 4 + offset,
            model_digest=binding[role]["model_digest"],
        )
        if not isinstance(sample["gold"], bool) or sample["gold"] != evaluation_case_passes(
            case, sample["answer"]["output"]
        ):
            raise MeasuredVerifierError("measured gold classification mismatch")
        judgment = sample["judgment"]
        _keys(
            judgment,
            {
                "input_digest",
                "output",
                "input_tokens",
                "output_tokens",
                "elapsed_ns",
                "model_digest",
                "decision",
                "confidence",
            },
            "measured verifier judgment",
        )
        parsed = parse_verifier_output(judgment["output"])
        if parsed != {"decision": judgment["decision"], "confidence": judgment["confidence"]} or isinstance(
            judgment["confidence"], bool
        ):
            raise MeasuredVerifierError("stored verifier decision/confidence mismatch")
        _measurement(
            {key: value for key, value in judgment.items() if key not in {"decision", "confidence"}},
            prompt=LocalVerifier.prompt(case.prompt, sample["answer"]["output"]),
            max_tokens=256,
            seed=binding["seed"] + index * 4 + offset + 2,
            model_digest=binding["verifier"]["model_digest"],
        )


def _results(binding, suite, cases):
    results = []
    for role in ("candidate", "baseline"):
        results.append(
            EvaluationResult(
                candidate_model_digest=binding[role]["model_digest"],
                suite_digest=suite.digest,
                passed_case_ids=tuple(row["case_id"] for row in cases if row[role]["gold"]),
                failed_case_ids=tuple(row["case_id"] for row in cases if not row[role]["gold"]),
                outputs={row["case_id"]: row[role]["answer"]["output"] for row in cases},
            )
        )
    return results


def _receipt(run_id, binding, suite, cases):
    metrics = derive_metrics(cases)
    candidate, baseline = _results(binding, suite, cases)
    report = VerifierReport(
        verifier_id="measured-local:" + run_id,
        verifier_model_digest=binding["verifier"]["model_digest"],
        candidate_model_digest=binding["candidate"]["model_digest"],
        calibration_error=metrics["calibration_error"],
        false_accept_rate=metrics["false_accept_rate"],
        false_reject_rate=metrics["false_reject_rate"],
        sample_count=metrics["sample_count"],
    )
    metrics.update(
        candidate_result_digest=candidate.digest,
        baseline_result_digest=baseline.digest,
        verifier_report_digest=report.digest,
    )
    return (
        MeasuredVerifierReceipt(run_id, digest(binding), digest(cases), canonical(metrics)),
        (candidate, baseline),
        report,
    )


class MeasuredEvaluationStore:
    """Transaction/fencing extension; EvaluationLedger remains the durable owner."""

    def __init__(self, ledger: EvaluationLedger, *, _writer_token=None):
        if not isinstance(ledger, EvaluationLedger):
            raise TypeError("existing EvaluationLedger is required")
        if _writer_token is not None and not _issued_writer_capability(_writer_token):
            raise MeasuredVerifierError("evaluation writer capability was not issued by the local runner")
        self.ledger = ledger
        self._writer_token = _writer_token
        self._db = ledger._db
        self._receipts = {}
        self._qualifications = {}
        self._known = {}
        with ledger._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
        with self._transaction():
            expected_tables = {
                "measured_eval_metadata",
                "measured_eval_run",
                "measured_eval_case",
                "measured_eval_qualification",
            }
            present_tables = {
                row[0]
                for row in self._db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'measured_eval_%'"
                )
            }
            if present_tables and present_tables != expected_tables:
                raise MeasuredVerifierError("measured evaluation schema is incomplete")
            for statement in (
                "CREATE TABLE IF NOT EXISTS measured_eval_metadata(singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version INTEGER NOT NULL)",
                "CREATE TABLE IF NOT EXISTS measured_eval_run(run_id TEXT PRIMARY KEY,binding_json TEXT NOT NULL,binding_digest TEXT NOT NULL,state TEXT NOT NULL,completed_cases INTEGER NOT NULL,owner TEXT,epoch INTEGER NOT NULL,expires REAL,receipt_json TEXT,receipt_digest TEXT)",
                "CREATE TABLE IF NOT EXISTS measured_eval_case(run_id TEXT NOT NULL,case_index INTEGER NOT NULL,payload TEXT NOT NULL,case_digest TEXT NOT NULL,PRIMARY KEY(run_id,case_index))",
                "CREATE TABLE IF NOT EXISTS measured_eval_qualification(receipt_digest TEXT PRIMARY KEY,payload TEXT NOT NULL,qualification_digest TEXT NOT NULL)",
            ):
                self._db.execute(statement)
            if not present_tables:
                self._db.execute("INSERT INTO measured_eval_metadata VALUES(1,1)")
            if self._db.execute("SELECT singleton,schema_version FROM measured_eval_metadata").fetchall() != [
                (1, 1)
            ]:
                raise MeasuredVerifierError("unsupported measured evaluation schema")
            if self._db.execute("SELECT count(*) FROM measured_eval_run").fetchone()[0] > 4096:
                raise MeasuredVerifierError("measured run count exceeds bound")
            if self._db.execute(
                "SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') AND (name LIKE 'measured_eval_%' OR tbl_name LIKE 'measured_eval_%') LIMIT 1"
            ).fetchone():
                raise MeasuredVerifierError("measured authority does not admit triggers or views")
            columns = {
                "measured_eval_metadata": ("singleton", "schema_version"),
                "measured_eval_run": (
                    "run_id",
                    "binding_json",
                    "binding_digest",
                    "state",
                    "completed_cases",
                    "owner",
                    "epoch",
                    "expires",
                    "receipt_json",
                    "receipt_digest",
                ),
                "measured_eval_case": ("run_id", "case_index", "payload", "case_digest"),
                "measured_eval_qualification": ("receipt_digest", "payload", "qualification_digest"),
            }
            for table, expected in columns.items():
                if tuple(row[1] for row in self._db.execute("PRAGMA table_info(" + table + ")")) != expected:
                    raise MeasuredVerifierError("measured schema columns are unsupported")
            if (
                self._db.execute(
                    "SELECT 1 FROM measured_eval_case c LEFT JOIN measured_eval_run r ON c.run_id=r.run_id WHERE r.run_id IS NULL LIMIT 1"
                ).fetchone()
                or self._db.execute(
                    "SELECT 1 FROM measured_eval_qualification q LEFT JOIN measured_eval_run r ON q.receipt_digest=r.receipt_digest WHERE r.state IS NULL OR r.state!='complete' LIMIT 1"
                ).fetchone()
            ):
                raise MeasuredVerifierError("measured evidence contains orphaned records")
            if (
                self._db.execute("SELECT count(*) FROM measured_eval_case").fetchone()[0] > MAX_CASES * 4096
                or self._db.execute("SELECT count(*) FROM measured_eval_qualification").fetchone()[0] > 4096
            ):
                raise MeasuredVerifierError("measured evidence record count exceeds bound")

    @contextmanager
    def _transaction(self):
        with self.ledger._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                yield
                self._db.commit()
            except BaseException as exc:
                self._db.rollback()
                if isinstance(exc, (ValueError, TypeError, KeyError, sqlite3.Error)):
                    raise MeasuredVerifierError("measured evidence transaction failed validation") from exc
                raise

    def _load(self, run_id):
        text(run_id, "run_id", 256)
        row = self._db.execute(
            "SELECT CASE WHEN length(CAST(binding_json AS BLOB))<=? THEN binding_json END,binding_digest,state,completed_cases,owner,epoch,expires,CASE WHEN length(CAST(receipt_json AS BLOB))<=? THEN receipt_json END,receipt_digest FROM measured_eval_run WHERE run_id=?",
            (MAX_RECORD_BYTES, MAX_RECORD_BYTES, run_id),
        ).fetchone()
        if row is None:
            return None
        binding_raw, binding_hash, state, count, owner, epoch, expires, receipt_raw, receipt_hash = row
        binding = decode(binding_raw)
        suite, policy = validate_binding(binding)
        if digest(binding) != binding_hash or state not in {"pending", "complete"}:
            raise MeasuredVerifierError("stored measured run identity/state mismatch")
        integer(count, "completed cases", maximum=len(suite.cases))
        integer(epoch, "worker epoch", 1)
        if (owner is None) != (expires is None):
            raise MeasuredVerifierError("worker lease state is malformed")
        if owner is not None:
            text(owner, "worker owner")
            if (
                isinstance(expires, bool)
                or not isinstance(expires, (int, float))
                or not math.isfinite(expires)
            ):
                raise MeasuredVerifierError("worker lease expiry is malformed")
        stored_suite = self._db.execute(
            "SELECT suite_key,CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload END FROM eval_suite WHERE suite_digest=?",
            (MAX_RECORD_BYTES, suite.digest),
        ).fetchone()
        if stored_suite != (suite.suite_id + "@" + suite.version, canonical(suite.as_dict())):
            raise MeasuredVerifierError("canonical registered suite identity mismatch")
        aggregate = self._db.execute(
            "SELECT count(*),coalesce(sum(length(CAST(payload AS BLOB))),0),coalesce(max(length(CAST(payload AS BLOB))),0) FROM measured_eval_case WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if (
            aggregate[0] > MAX_CASES
            or aggregate[1] + max(aggregate[0] - 1, 0) + 2 > MAX_RUN_EVIDENCE_BYTES
            or aggregate[2] > MAX_CASE_BYTES
        ):
            raise MeasuredVerifierError("measured case evidence exceeds aggregate or per-case byte bound")
        rows = self._db.execute(
            "SELECT case_index,payload,case_digest FROM measured_eval_case WHERE run_id=? ORDER BY case_index LIMIT ?",
            (run_id, MAX_CASES + 1),
        ).fetchall()
        if len(rows) != count:
            raise MeasuredVerifierError("measured case history is incomplete or oversized")
        cases = []
        case_hashes = []
        for index, (case_index, raw, case_hash) in enumerate(rows):
            if case_index != index:
                raise MeasuredVerifierError("measured case history is not contiguous")
            case = decode(raw)
            validate_case(case, index, binding, suite)
            if digest(case) != case_hash:
                raise MeasuredVerifierError("measured case digest mismatch")
            cases.append(case)
            case_hashes.append(case_hash)
        prior = self._known.get(run_id)
        if prior is not None and (
            prior[0] != binding_raw
            or tuple(case_hashes[: len(prior[1])]) != prior[1]
            or len(case_hashes) < len(prior[1])
        ):
            raise MeasuredVerifierError("immutable measured evidence history changed")
        receipt = None
        if state == "complete":
            if count != len(suite.cases) or owner is not None or receipt_raw is None:
                raise MeasuredVerifierError("completed run lacks full drained measured evidence")
            expected, results, report = _receipt(run_id, binding, suite, cases)
            if canonical(asdict(expected)) != receipt_raw or expected.digest != receipt_hash:
                raise MeasuredVerifierError("measured receipt or derived metrics were tampered")
            for result in results:
                evidence = self._db.execute(
                    "SELECT candidate_model_digest,suite_digest,CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload END FROM eval_result WHERE result_digest=?",
                    (MAX_RECORD_BYTES, result.digest),
                ).fetchone()
                if evidence != (
                    result.candidate_model_digest,
                    result.suite_digest,
                    canonical(result.as_dict()),
                ):
                    raise MeasuredVerifierError("canonical measured evaluation result identity mismatch")
            evidence = self._db.execute(
                "SELECT verifier_id,verifier_model_digest,candidate_model_digest,CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload END FROM verifier_report WHERE report_digest=?",
                (MAX_RECORD_BYTES, report.digest),
            ).fetchone()
            if evidence != (
                report.verifier_id,
                report.verifier_model_digest,
                report.candidate_model_digest,
                canonical(report.as_dict()),
            ):
                raise MeasuredVerifierError("canonical measured verifier report identity mismatch")
            cached = self._receipts.get(receipt_hash)
            receipt = cached if cached == expected else expected
            self._receipts[receipt_hash] = receipt
        elif receipt_raw is not None or receipt_hash is not None:
            raise MeasuredVerifierError("pending run carries a forged completed receipt")
        self._known[run_id] = (binding_raw, tuple(case_hashes))
        return binding, suite, policy, cases, receipt, (owner, epoch, expires)

    def start(self, run_id, binding, worker_id, lease_seconds):
        text(run_id, "run_id", 256)
        text(worker_id, "worker_id")
        integer(lease_seconds, "lease seconds", 1, 3600)
        suite, _policy = validate_binding(binding)
        self.ledger.register_suite(suite)
        encoded = canonical(binding)
        with self._transaction():
            prior = self._load(run_id)
            now = time.time()
            if prior is None:
                if self._db.execute("SELECT count(*) FROM measured_eval_run").fetchone()[0] >= 4096:
                    raise MeasuredVerifierError("measured run count exceeds bound")
                epoch = 1
                self._db.execute(
                    "INSERT INTO measured_eval_run VALUES(?,?,?,'pending',0,?,?,?,NULL,NULL)",
                    (run_id, encoded, digest(binding), worker_id, epoch, now + lease_seconds),
                )
                return epoch
            if canonical(prior[0]) != encoded:
                raise MeasuredVerifierError("run identity is immutable")
            if prior[4] is not None:
                return None
            owner, epoch, expires = prior[5]
            if owner is not None and expires > now:
                raise MeasuredVerifierError("measured run already has an active worker")
            integer(epoch + 1, "next worker epoch", 1)
            self._db.execute(
                "UPDATE measured_eval_run SET owner=?,epoch=?,expires=? WHERE run_id=?",
                (worker_id, epoch + 1, now + lease_seconds, run_id),
            )
            return epoch + 1

    def _owned(self, run_id, worker_id, epoch):
        state = self._load(run_id)
        if (
            state is None
            or state[4] is not None
            or state[5][0] != worker_id
            or state[5][1] != epoch
            or state[5][2] <= time.time()
        ):
            raise MeasuredVerifierError("measured worker ownership is stale or expired")
        return state

    def _fence_commit(self, run_id, worker_id, epoch):
        lease = self._db.execute(
            "SELECT state,owner,epoch,expires FROM measured_eval_run WHERE run_id=?", (run_id,)
        ).fetchone()
        if (
            lease is None
            or lease[:3] != ("pending", worker_id, epoch)
            or lease[3] is None
            or lease[3] <= time.time()
        ):
            raise MeasuredVerifierError("measured worker expired before evidence commit")

    def renew(self, run_id, worker_id, epoch, lease_seconds):
        integer(lease_seconds, "lease seconds", 1, 3600)
        with self._transaction():
            self._owned(run_id, worker_id, epoch)
            self._db.execute(
                "UPDATE measured_eval_run SET expires=? WHERE run_id=? AND owner=? AND epoch=?",
                (time.time() + lease_seconds, run_id, worker_id, epoch),
            )

    def case(self, run_id, index):
        with self._transaction():
            state = self._load(run_id)
            integer(index, "case index", maximum=len(state[1].cases) - 1)
            return state[3][index] if len(state[3]) > index else None

    def _require_writer(self, token):
        if not _issued_writer_capability(token) or token is not self._writer_token:
            raise MeasuredVerifierError(
                "measured publication requires the executing runner's issued capability"
            )

    def record_case(self, run_id, index, row, worker_id, epoch, *, _token=None):
        self._require_writer(_token)
        with self._transaction():
            binding, suite, _policy, cases, _receipt_value, _lease = self._owned(run_id, worker_id, epoch)
            integer(index, "case index", maximum=len(suite.cases) - 1)
            if index != len(cases):
                raise MeasuredVerifierError("completed case append sequence conflict")
            validate_case(row, index, binding, suite)
            encoded = canonical(row)
            if (
                len(encoded.encode("utf-8")) > MAX_CASE_BYTES
                or len(canonical([*cases, row]).encode("utf-8")) > MAX_RUN_EVIDENCE_BYTES
            ):
                raise MeasuredVerifierError("measured case exceeds evidence byte bound")
            self._fence_commit(run_id, worker_id, epoch)
            self._db.execute(
                "INSERT INTO measured_eval_case VALUES(?,?,?,?)", (run_id, index, encoded, digest(row))
            )
            cursor = self._db.execute(
                "UPDATE measured_eval_run SET completed_cases=completed_cases+1 WHERE run_id=? AND completed_cases=? AND owner=? AND epoch=?",
                (run_id, index, worker_id, epoch),
            )
            if cursor.rowcount != 1:
                raise MeasuredVerifierError("measured case compare-and-swap failed")

    def complete(self, run_id, worker_id, epoch, *, _token=None):
        self._require_writer(_token)
        with self._transaction():
            binding, suite, _policy, cases, _old_receipt, _lease = self._owned(run_id, worker_id, epoch)
            if len(cases) != len(suite.cases):
                raise MeasuredVerifierError("measured run lacks complete case coverage")
            receipt, results, report = _receipt(run_id, binding, suite, cases)
            for result in results:
                encoded = canonical(result.as_dict())
                prior = self._db.execute(
                    "SELECT CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload END FROM eval_result WHERE result_digest=?",
                    (MAX_RECORD_BYTES, result.digest),
                ).fetchone()
                if prior is not None and prior[0] != encoded:
                    raise MeasuredVerifierError("canonical evaluation result digest collision")
                self._db.execute(
                    "INSERT OR IGNORE INTO eval_result VALUES(?,?,?,?)",
                    (result.digest, result.candidate_model_digest, result.suite_digest, encoded),
                )
            encoded = canonical(report.as_dict())
            prior = self._db.execute(
                "SELECT CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload END FROM verifier_report WHERE report_digest=?",
                (MAX_RECORD_BYTES, report.digest),
            ).fetchone()
            if prior is not None and prior[0] != encoded:
                raise MeasuredVerifierError("canonical verifier report digest collision")
            self._db.execute(
                "INSERT OR IGNORE INTO verifier_report VALUES(?,?,?,?,?)",
                (
                    report.digest,
                    report.verifier_id,
                    report.verifier_model_digest,
                    report.candidate_model_digest,
                    encoded,
                ),
            )
            self._fence_commit(run_id, worker_id, epoch)
            self._db.execute(
                "UPDATE measured_eval_run SET state='complete',owner=NULL,expires=NULL,receipt_json=?,receipt_digest=? WHERE run_id=? AND owner=? AND epoch=?",
                (canonical(asdict(receipt)), receipt.digest, run_id, worker_id, epoch),
            )
        return self.receipt(run_id)

    def release(self, run_id, worker_id, epoch):
        with self._transaction():
            self._db.execute(
                "UPDATE measured_eval_run SET owner=NULL,expires=NULL WHERE run_id=? AND state='pending' AND owner=? AND epoch=?",
                (run_id, worker_id, epoch),
            )

    def receipt(self, run_id):
        with self._transaction():
            state = self._load(run_id)
            if state is None or state[4] is None:
                raise MeasuredVerifierError("run has no issued completed measured receipt")
            return state[4]

    def qualify(self, receipt, *, sources=None, _token=None):
        self._require_writer(_token)
        if (
            not isinstance(receipt, MeasuredVerifierReceipt)
            or self._receipts.get(receipt.digest) is not receipt
        ):
            raise MeasuredVerifierError("qualification requires an issued measured receipt handle")
        with self._transaction():
            state = self._load(receipt.run_id)
            if state is None or state[4] is not receipt:
                raise MeasuredVerifierError("measured receipt is stale or forged")
            binding, _suite_value, policy, _cases, _receipt_value, _lease = state
            if sources is None or [source.payload for source in sources] != [
                binding[role] for role in ("candidate", "baseline", "verifier")
            ]:
                raise MeasuredVerifierError(
                    "current qualification model/training identities differ from measured evidence"
                )
            reasons = qualification_reasons(receipt.metrics, policy, binding)
            expected = MeasuredVerifierQualification(
                receipt.digest,
                receipt.binding_digest,
                binding["verifier"]["model_digest"],
                "qualified_verifier_candidate" if not reasons else "rejected",
                reasons,
            )
            prior = self._db.execute(
                "SELECT CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload END,qualification_digest FROM measured_eval_qualification WHERE receipt_digest=?",
                (MAX_RECORD_BYTES, receipt.digest),
            ).fetchone()
            if prior is not None and prior != (canonical(asdict(expected)), expected.digest):
                raise MeasuredVerifierError("measured qualification evidence was tampered")
            self._db.execute(
                "INSERT OR IGNORE INTO measured_eval_qualification VALUES(?,?,?)",
                (receipt.digest, canonical(asdict(expected)), expected.digest),
            )
            cached = self._qualifications.get(expected.digest)
            qualification = cached if cached == expected else expected
        self._qualifications[expected.digest] = qualification
        return qualification

    def require_qualification(self, qualification):
        if (
            not isinstance(qualification, MeasuredVerifierQualification)
            or self._qualifications.get(qualification.digest) is not qualification
        ):
            raise MeasuredVerifierError("reusable verifier requires an issued qualification handle")
        with self._transaction():
            row = self._db.execute(
                "SELECT run_id FROM measured_eval_run WHERE receipt_digest=?", (qualification.receipt_digest,)
            ).fetchone()
            if row is None:
                raise MeasuredVerifierError("qualification receipt is unavailable")
            state = self._load(row[0])
            reasons = qualification_reasons(state[4].metrics, state[2], state[0])
            expected = MeasuredVerifierQualification(
                state[4].digest,
                digest(state[0]),
                state[0]["verifier"]["model_digest"],
                "qualified_verifier_candidate" if not reasons else "rejected",
                reasons,
            )
            stored = self._db.execute(
                "SELECT CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload END,qualification_digest FROM measured_eval_qualification WHERE receipt_digest=?",
                (MAX_RECORD_BYTES, qualification.receipt_digest),
            ).fetchone()
            if (
                expected != qualification
                or stored != (canonical(asdict(expected)), expected.digest)
                or reasons
            ):
                raise MeasuredVerifierError("verifier qualification is rejected or corrupt")
            return state[0]
