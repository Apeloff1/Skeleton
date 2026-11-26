"""Local desk model: BM25, learned token weights, programs, and a hash-chained journal."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from skeleton.local_ai import desk_model as model_module
from skeleton.local_ai import multi_turn as desk_module
from skeleton.local_ai.desk_model import (
    NO_EVIDENCE,
    DeskModel,
    ModelRejected,
)
from skeleton.local_ai.desk_journal import JournalRejected
from skeleton.local_ai.docx_ops import read_paragraphs
from skeleton.local_ai.multi_turn import MultiTurnDesk, TurnRejected
from skeleton.local_ai.pdf_ops import read_text
from skeleton.local_ai.pptx_ops import read_slides


def _bm25(tf: int, dl: int, avgdl: float, n: int, df: int) -> float:
    idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
    return idf * (tf * (1.2 + 1.0)) / (tf + 1.2 * (1.0 - 0.75 + 0.75 * dl / avgdl))


def test_bm25_matches_the_ranking_formula(tmp_path: Path) -> None:
    facts = ["alpha alpha alpha shared", "beta shared", "gamma shared"]
    model = DeskModel(tmp_path / "desk_model.json")
    ranked = model.score_facts("alpha", facts)
    assert [hit.text for hit in ranked] == facts
    assert ranked[0].index == 1
    expected = _bm25(tf=3, dl=4, avgdl=8 / 3, n=3, df=1)
    assert abs(ranked[0].score - expected) < 1e-9
    assert ranked[1].score == 0.0


def test_adjacent_query_terms_score_half_a_point_more(tmp_path: Path) -> None:
    facts = ["kettle warm extra", "kettle extra warm"]
    model = DeskModel(tmp_path / "desk_model.json")
    ranked = model.score_facts("kettle warm", facts)
    assert ranked[0].text == "kettle warm extra"
    assert abs(ranked[0].score - ranked[1].score - 0.5) < 1e-9


def test_phrase_and_exclusion_filters(tmp_path: Path) -> None:
    facts = ["the door sticks", "the door is open and the bell sticks"]
    model = DeskModel(tmp_path / "desk_model.json")
    phrase = model.score_facts('"door sticks"', facts)
    assert [hit.text for hit in phrase] == ["the door sticks"]
    excluded = model.score_facts("door -bell", ["the door sticks", "the bell rings"])
    assert [hit.text for hit in excluded] == ["the door sticks"]
    answer = model.answer("warm", ["the kettle is warm"])
    assert answer.covered is True
    assert answer.text.startswith("the kettle is warm [fact 1 score ")
    assert model.answer("the", ["the kettle is warm"]).text == NO_EVIDENCE


def test_teach_overrides_a_prior_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / "desk_model.json"
    model = DeskModel(path)
    assert model.classify("pdf archive the minutes").label == "pdf"
    assert model.classify("save the kettle is warm").label == "remember"
    assert model.status() == {
        "bound": True,
        "remote": False,
        "gguf": False,
        "weights_source": "desk-corpus",
        "updates": 0,
        "examples": 0,
        "learned_features": [],
        "classes": list(model.status()["classes"]),
    }
    assert model.status()["gguf"] is False
    model.teach("pdf archive the minutes", "remember")
    assert model.classify("pdf archive the minutes").label == "remember"
    assert model.classify("write a pdf of the agenda").label == "pdf"
    reloaded = DeskModel(path)
    assert reloaded.classify("pdf archive the minutes").label == "remember"
    assert reloaded.examples == (("pdf archive the minutes", "remember"),)
    assert list(path.parent.glob(".desk-model.*.tmp")) == []

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["weights"]["remember"]["pdf"] = -3
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ModelRejected):
        DeskModel(path)


def test_feature_cap_secret_and_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "desk_model.json"
    capped = DeskModel(path, max_features=2)
    with pytest.raises(ModelRejected):
        capped.teach("alpha beta gamma", "remember")
    assert capped.examples == ()
    with pytest.raises(ModelRejected):
        capped.teach("token=abcd", "remember")
    with pytest.raises(ModelRejected):
        capped.teach("keep this", "dance")
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ModelRejected):
        DeskModel(path)
    source = Path(model_module.__file__).read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "urllib" not in source


def test_commit_plans_a_document_and_keeps_ask_strict(tmp_path: Path) -> None:
    desk = MultiTurnDesk(tmp_path)
    missed = desk.run(
        [
            "remember notes live in the drawer",
            "remember the device is unplugged",
            "ask notes device",
            "reason notes device",
        ]
    )
    assert missed.model_called is False
    assert missed.remote_called is False
    assert missed.local_model_bound is True
    assert missed.turns[2].answer == "No note on this desk matches. No model is bound."
    assert missed.turns[2].local_model_used is False
    assert "notes live in the drawer [fact 1 score " in missed.turns[3].answer
    assert "the device is unplugged [fact 2 score " in missed.turns[3].answer
    assert missed.turns[3].local_model_used is True

    root = tmp_path / "session"
    desk = MultiTurnDesk(root)
    vague = desk.run(["commit hello there"])
    assert vague.turns[0].status == "refused"
    assert vague.turns[0].answer == "low confidence for 'hello there'"
    assert desk.memory.facts() == []

    planned = desk.run(["commit save the kettle is warm and then pdf that"])
    assert planned.turns[0].status == "ok"
    assert planned.turns[0].verified is True
    assert planned.model_called is False
    assert [step.verb for step in planned.turns[0].steps] == ["remember", "pdf"]
    assert desk.memory.facts() == ["the kettle is warm"]
    assert read_text((root / "notes.pdf").read_bytes()) == ["the kettle is warm"]
    assert len(desk.journal.entries()) == 2


def test_program_rolls_back_and_refuses_unresolved_text(tmp_path: Path) -> None:
    desk = MultiTurnDesk(tmp_path)
    secret = desk.run(["commit remember the kettle is warm and then remember api_key=nope"])
    assert secret.turns[0].status == "refused"
    assert "secret" in secret.turns[0].answer
    assert desk.memory.facts() == []

    original = desk._apply

    def fail_second(verb: str, payload: str):
        if verb == "hash":
            raise JournalRejected("boom")
        return original(verb, payload)

    desk._apply = fail_second
    blown = desk.run(["commit pdf Alpha and then hash notes.pdf"])
    assert blown.turns[0].status == "refused"
    assert blown.turns[0].answer == "boom"
    assert not (tmp_path / "notes.pdf").exists()
    desk._apply = original

    quoted = desk.run(['commit remember "keep this and then that"'])
    assert quoted.turns[0].status == "ok"
    assert desk.memory.facts() == ['"keep this and then that"']
    crowded = " and then ".join(f"remember item{index}" for index in range(5))
    too_many = desk.run([f"commit {crowded}"])
    assert too_many.turns[0].status == "refused"
    assert too_many.turns[0].answer == "too many clauses"
    assert len(desk.memory.facts()) == 1

    desk.run(["forget \"keep this and then that\""])
    unresolved = desk.run(["commit pdf that"])
    assert unresolved.turns[0].status == "refused"
    assert unresolved.turns[0].answer == "nothing to resolve"


def test_append_hash_and_journal_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "desk"
    desk = MultiTurnDesk(root)
    desk.run(["deck Opening", "append slide Closing", "docx First", "append paragraph Second"])
    assert read_slides((root / "notes.pptx").read_bytes()) == ["Opening", "Closing"]
    assert read_paragraphs((root / "notes.docx").read_bytes()) == ["First", "Second"]
    digest = hashlib.sha256((root / "notes.pptx").read_bytes()).hexdigest()
    hashed = desk.run(["hash notes.pptx"])
    assert hashed.turns[0].answer == digest
    escaped = desk.run(["hash ../notes.pptx"])
    assert escaped.turns[0].status == "refused"
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"nope")
    (root / "alias.txt").symlink_to(outside)
    assert desk.run(["hash alias.txt"]).turns[0].status == "refused"

    pages = " | ".join(f"P{index}" for index in range(32))
    desk.run([f"pdf {pages}"])
    assert len(read_text((root / "notes.pdf").read_bytes())) == 32
    overflow = desk.run(["append page Next"])
    assert overflow.turns[0].status == "refused"
    assert len(read_text((root / "notes.pdf").read_bytes())) == 32

    checked = desk.run(["recall check"])
    assert checked.turns[0].answer == "chain ok"
    journal = root / "journal.jsonl"
    lines = journal.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["answer"] = str(first["answer"]) + "!"
    lines[0] = json.dumps(first, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    journal.write_text("\n".join(lines) + "\n", encoding="utf-8")
    preserved = journal.read_text(encoding="utf-8")
    with pytest.raises(JournalRejected):
        desk.run(["recall check"])
    assert journal.read_text(encoding="utf-8") == preserved

    monkeypatch.setattr(desk_module, "_MAX_JOURNAL", 2)
    trimmed = MultiTurnDesk(tmp_path / "trim")
    trimmed.run(["remember one", "remember two", "remember three"])
    assert [row["answer"] for row in trimmed.journal.entries()] == ["two", "three"]
    assert trimmed.run(["recall 1"]).turns[0].answer == "two"
    assert list((tmp_path / "trim").glob(".journal.*.tmp")) == []


def test_judge_promotes_a_refused_utterance(tmp_path: Path) -> None:
    desk = MultiTurnDesk(tmp_path)
    with pytest.raises(TurnRejected):
        desk.run(["dance now"])
    refused = desk.run(["commit archive the minutes"])
    assert refused.turns[0].status == "refused"
    assert desk.memory.facts() == []
    judged = desk.run(["judge good"])
    assert judged.turns[0].status == "ok"
    assert judged.turns[0].answer == "judged good remember"
    stored = desk.run(["commit archive the minutes"])
    assert stored.turns[0].status == "ok"
    assert desk.memory.facts() == ["archive the minutes"]
    assert stored.turns[0].local_model_used is True
    assert stored.model_called is False


def test_empty_question_and_unknown_label_are_refused(tmp_path: Path) -> None:
    desk = MultiTurnDesk(tmp_path)
    empty = desk.run(["reason"])
    assert empty.turns[0].status == "refused"
    assert desk.run(["reason kettle"]).turns[0].answer == NO_EVIDENCE
    assert desk.run(["judge good"]).turns[0].answer == "nothing to judge"
    bad = desk.run(["judge bad"])
    assert bad.turns[0].status == "refused"
    assert bad.turns[0].answer == "judge bad needs a label"
