"""Whole-history native inference receipt custody and portable-turn integrity.

These tests deliberately corrupt a private local SQLite fixture to verify that
a later turn cannot silently continue from a tampered or incompletely
attested conversation. No cloud model or production GGUF is used.
"""
from __future__ import annotations

import json
from hashlib import sha256

import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.offline_http import OfflineHTTPApplication
from skeleton.cortex.transformer import TinyTransformer


def native_model() -> NativeRuntimeLocalModel:
    return NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer",
               "local", "offline", "jeeves", "computer", ".", " "),
        dim=8, ctx=1024, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )))


def committed_two_turns(tmp_path):
    app = OfflineHTTPApplication(
        native_model(), tmp_path / "durable-integrity.sqlite3", token="a" * 64
    )
    _, created = app.dispatch("POST", "/v1/sessions", {})
    sid = created["session_id"]
    for i in range(2):
        status, answer = app.dispatch("POST", f"/v1/sessions/{sid}/turn", {
            "message": f"hello world turn {i}",
            "request_id": f"durable-receipt-{i}",
            "max_output_tokens": 2,
        })
        assert status == 200
        assert answer["revision"] == i + 1
        assert answer["local_execution_receipt"] is not None
    assert app._store.load(sid, app.model_digest, app.tokenizer_digest).revision == 2
    return app, sid


@pytest.mark.parametrize("mutation,error", [
    ("historical_output_digest", "conversation turn history/receipt mismatch"),
    ("historical_receipt_removed", "required local execution receipt is missing"),
    ("historical_receipt_model", "local execution receipt is not bound to committed"),
    ("historical_receipt_revision", "local execution receipt is not bound to committed"),
    ("historical_receipt_output", "local execution receipt is not bound to committed"),
    ("historical_receipt_digest", "local execution receipt is not bound to committed"),
    ("historical_receipt_marker", "an unverified historical turn cannot acquire"),
])
def test_any_earlier_turn_integrity_failure_blocks_entire_session(
    tmp_path, mutation, error,
):
    app, sid = committed_two_turns(tmp_path)
    try:
        rid = "durable-receipt-0"
        with app._store._transaction():
            db = app._store._db
            if mutation == "historical_output_digest":
                db.execute(
                    "UPDATE offline_turns SET output_digest=? "
                    "WHERE session_id=? AND request_id=?", ("a" * 64, sid, rid),
                )
            elif mutation == "historical_receipt_removed":
                db.execute(
                    "DELETE FROM offline_turn_execution_receipts "
                    "WHERE session_id=? AND request_id=?", (sid, rid),
                )
            elif mutation == "historical_receipt_model":
                db.execute(
                    "UPDATE offline_turn_execution_receipts SET model_digest=? "
                    "WHERE session_id=? AND request_id=?", ("f" * 64, sid, rid),
                )
            elif mutation == "historical_receipt_revision":
                db.execute(
                    "UPDATE offline_turn_execution_receipts SET revision=999 "
                    "WHERE session_id=? AND request_id=?", (sid, rid),
                )
            elif mutation == "historical_receipt_output":
                db.execute(
                    "UPDATE offline_turn_execution_receipts SET output_sha256=? "
                    "WHERE session_id=? AND request_id=?", ("b" * 64, sid, rid),
                )
            elif mutation == "historical_receipt_digest":
                db.execute(
                    "UPDATE offline_turn_execution_receipts SET execution_receipt_digest=? "
                    "WHERE session_id=? AND request_id=?", ("z" * 64, sid, rid),
                )
            elif mutation == "historical_receipt_marker":
                db.execute(
                    "UPDATE offline_turns SET runtime_receipt_required=0 "
                    "WHERE session_id=? AND request_id=?", (sid, rid),
                )

        with pytest.raises(RuntimeContractError, match=error):
            app._store.load(sid, app.model_digest, app.tokenizer_digest)
        with pytest.raises(RuntimeContractError, match=error):
            app.dispatch("GET", f"/v1/sessions/{sid}")
        # A later idempotent request must also refuse to reuse corrupted
        # history, even if its own execution receipt was untouched.
        with pytest.raises(RuntimeContractError, match=error):
            app.dispatch("POST", f"/v1/sessions/{sid}/turns", {
                "message": "new generation must not run against corrupted past",
                "request_id": "must-not-run",
                "max_output_tokens": 2,
            })
    finally:
        app.close()


def test_forked_and_imported_history_is_explicitly_unverified_not_reexecuted(tmp_path):
    """Portable or forked replies remain readable, not relabelled as freshly run."""
    app, sid = committed_two_turns(tmp_path)
    try:
        status, forked = app.dispatch("POST", f"/v1/sessions/{sid}/fork", {
            "after_turn": 1,
        })
        assert status == 201
        fork_sid = forked["session_id"]
        assert app._store.load(
            fork_sid, app.model_digest, app.tokenizer_digest
        ).revision == 1
        _, result = app.dispatch(
            "GET", f"/v1/sessions/{fork_sid}/turns/durable-receipt-0",
        )
        assert result["result"]["local_execution_receipt"] is None

        status, imported = app.dispatch(
            "POST", "/v1/sessions/import",
            raw_body=app._store.export_bundle(
                sid, app.model_digest, app.tokenizer_digest,
            ),
        )
        assert status == 201
        imported_sid = imported["session_id"]
        assert app._store.load(
            imported_sid, app.model_digest, app.tokenizer_digest
        ).revision == 2
        _, imported_result = app.dispatch(
            "GET", f"/v1/sessions/{imported_sid}/turns/durable-receipt-0",
        )
        assert imported_result["result"]["local_execution_receipt"] is None
    finally:
        app.close()


def test_portable_bundle_refuses_forged_nested_output_digest_even_when_resigned(
    tmp_path,
):
    """A recomputed bundle checksum cannot excuse an inconsistent turn digest."""
    app, sid = committed_two_turns(tmp_path)
    try:
        raw = app._store.export_bundle(
            sid, app.model_digest, app.tokenizer_digest,
        )
        bundle = json.loads(raw)
        assert bundle["body"]["turns"]
        bundle["body"]["turns"][0]["output_digest"] = "a" * 64
        # Attacker can recompute this unkeyed envelope hash, but cannot make
        # the recorded digest consistent with the archived assistant bytes.
        body = bundle["body"]
        bundle["sha256"] = sha256(json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")).hexdigest()
        modified = json.dumps(bundle, separators=(",", ":")).encode("utf-8")
        with pytest.raises(
            RuntimeContractError, match="conversation turn history/receipt mismatch",
        ):
            app._store.import_bundle(
                modified, app.model_digest, app.tokenizer_digest,
            )
        assert app._store.load(
            sid, app.model_digest, app.tokenizer_digest,
        ).revision == 2
    finally:
        app.close()


def test_historical_unverified_turn_cannot_gain_a_fabricated_receipt(tmp_path):
    app, sid = committed_two_turns(tmp_path)
    try:
        _, forked = app.dispatch("POST", f"/v1/sessions/{sid}/fork", {
            "after_turn": 1,
        })
        fork_sid = forked["session_id"]
        with app._store._transaction():
            rows = app._store._db.execute(
                "SELECT revision, output_digest FROM offline_turns "
                "WHERE session_id=? AND request_id=?",
                (fork_sid, "durable-receipt-0"),
            ).fetchone()
            assert rows is not None
            app._store._db.execute(
                "INSERT INTO offline_turn_execution_receipts "
                "(session_id, request_id, revision, model_digest, "
                "tokenizer_digest, output_sha256, execution_receipt_digest) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (fork_sid, "durable-receipt-0", rows[0], app.model_digest,
                 app.tokenizer_digest, rows[1], "c" * 64),
            )
        with pytest.raises(
            RuntimeContractError, match="an unverified historical turn cannot acquire",
        ):
            app._store.load(fork_sid, app.model_digest, app.tokenizer_digest)
    finally:
        app.close()


@pytest.mark.parametrize("invalid_digest", [
    "a" * 64,
    "A" * 64,
    "a" * 63,
    "z" * 64,
])
def test_commit_rejects_inconsistent_output_hash_before_any_cas_write(
    tmp_path, invalid_digest,
):
    """A defective native adapter cannot persist internally corrupt output."""
    model = native_model()
    app = OfflineHTTPApplication(
        model, tmp_path / "bad-commit.sqlite3", token="a" * 64
    )
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        current = app._store.load(sid, app.model_digest, app.tokenizer_digest)
        next_transcript = current.transcript.append("user", "hello").append(
            "assistant", "real model output"
        )
        with pytest.raises(
            RuntimeContractError, match="invalid native generation output digest",
        ):
            app._store.commit(
                session=current,
                request_id="reject-bad-digest",
                request_digest="b" * 64,
                transcript=next_transcript,
                text="real model output",
                output_digest=invalid_digest,
                prompt_tokens=4,
                generated_tokens=4,
                execution_receipt_digest="c" * 64,
            )
        after = app._store.load(sid, app.model_digest, app.tokenizer_digest)
        assert after.revision == 0
        assert after.transcript.messages == ()
        assert app._store.replay(sid, "reject-bad-digest", "b" * 64) is None
        count = app._store._db.execute(
            "SELECT COUNT(*) FROM offline_turn_execution_receipts WHERE session_id=?",
            (sid,),
        ).fetchone()[0]
        assert count == 0
    finally:
        app.close()
