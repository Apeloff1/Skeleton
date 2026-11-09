"""STU-ERAS slice 4: canonical serialization, digests, diffs, canon CLI."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from skeleton.simulation.era.scripting import (
    EraSpec,
    SchemaError,
    canonical_dict,
    diff_eras,
    digest,
    dumps_canonical,
    equivalent,
    is_canonical_text,
    load_era,
    load_era_json,
    roundtrip,
)
from skeleton.simulation.era.scripting.canonical import main as canon_main

FIXTURES = Path(__file__).parent / "fixtures" / "stu_eras"


def _raw(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _shuffled(raw: dict) -> dict:
    """Same era, different spelling: reversed rooms/exits/tags, explicit defaults."""
    out = copy.deepcopy(raw)
    out["rooms"] = list(reversed(out["rooms"]))
    out["tags"] = list(reversed(out.get("tags", [])))
    for room in out["rooms"]:
        room["exits"] = list(reversed(room.get("exits", [])))
        room.setdefault("depth", 0)
        room.setdefault("tags", [])
        for ex in room["exits"]:
            ex.setdefault("locked", False)
    out = {k: out[k] for k in reversed(list(out))}
    return out


def test_canonical_dict_orders_rooms_exits_and_tags():
    raw = _raw("bronze")
    raw["rooms"][0]["exits"] = list(reversed(raw["rooms"][0]["exits"]))
    raw["tags"] = ["zeta", "ancient"]
    data = canonical_dict(load_era(raw))
    assert [r["id"] for r in data["rooms"]] == ["forum", "gate", "smithy", "vault"]
    gate = next(r for r in data["rooms"] if r["id"] == "gate")
    assert [e["direction"] for e in gate["exits"]] == ["north", "east"]
    assert data["tags"] == ["ancient", "zeta"]
    assert "locked" not in gate["exits"][0]


@pytest.mark.parametrize("name", ["bronze", "iron"])
def test_equivalent_spellings_share_text_and_digest(name):
    a = load_era(_raw(name))
    b = load_era(_shuffled(_raw(name)))
    assert equivalent(a, b)
    assert dumps_canonical(a) == dumps_canonical(b)
    assert dumps_canonical(a, pretty=True) == dumps_canonical(b, pretty=True)
    assert digest(a) == digest(b)


def test_digest_format_and_sensitivity():
    a = load_era(_raw("bronze"))
    d = digest(a)
    assert d.startswith("sha256:") and len(d) == len("sha256:") + 64
    raw = _raw("bronze")
    raw["rooms"][2]["name"] = "Forge Hall"
    assert digest(load_era(raw)) != d
    assert digest(load_era(_raw("iron"))) != d


def test_compact_and_pretty_forms():
    era = load_era(_raw("bronze"))
    compact = dumps_canonical(era)
    pretty = dumps_canonical(era, pretty=True)
    assert "\n" not in compact and ": " not in compact
    assert pretty.endswith("}\n") and pretty.startswith("{\n  ")
    assert json.loads(compact) == json.loads(pretty) == canonical_dict(era)


def test_non_ascii_kept_verbatim():
    raw = _raw("bronze")
    raw["title"] = "Bronzealder – Ø"
    text = dumps_canonical(load_era(raw))
    assert "Bronzealder – Ø" in text and "\\u" not in text


@pytest.mark.parametrize("name", ["bronze", "iron"])
def test_roundtrip_revalidates_and_is_idempotent(name):
    era = load_era(_shuffled(_raw(name)))
    back = roundtrip(era)
    assert isinstance(back, EraSpec)
    assert equivalent(era, back)
    assert dumps_canonical(roundtrip(back)) == dumps_canonical(back)
    assert back.room_ids == tuple(sorted(era.room_ids))


def test_bad_type_rejected():
    with pytest.raises(SchemaError) as exc:
        canonical_dict({"id": "bronze"})  # type: ignore[arg-type]
    assert exc.value.code == "bad-type"


def test_is_canonical_text():
    era = load_era(_raw("bronze"))
    pretty = dumps_canonical(era, pretty=True)
    assert is_canonical_text(pretty)
    assert is_canonical_text(pretty.encode("utf-8"))
    assert not is_canonical_text(dumps_canonical(era))
    assert not is_canonical_text((FIXTURES / "bronze.json").read_text())
    assert not is_canonical_text("{not json")
    assert not is_canonical_text(b"\xff\xfe")
    assert not is_canonical_text(json.dumps({"id": "x"}))


def test_diff_same_for_spelling_only_changes():
    d = diff_eras(load_era(_raw("bronze")), load_era(_shuffled(_raw("bronze"))))
    assert d == {"same": True, "era": [], "added": [], "removed": [], "changed": {}}


def test_diff_reports_room_and_era_changes():
    old = _raw("bronze")
    new = copy.deepcopy(old)
    new["title"] = "Late Bronze Age"
    new["order"] = 3
    new["rooms"] = [r for r in new["rooms"] if r["id"] != "smithy"]
    new["rooms"][0]["exits"] = [{"direction": "north", "target": "forum"},
                                {"direction": "west", "target": "harbor"}]
    new["rooms"].append({"id": "harbor", "name": "Harbor", "kind": "safe",
                         "exits": [{"direction": "east", "target": "gate"}]})
    new["rooms"][1]["depth"] = 4
    new["rooms"][1]["tags"] = ["dim"]
    d = diff_eras(load_era(old), load_era(new))
    assert d["same"] is False
    assert d["era"] == ["title", "order"]
    assert d["added"] == ["harbor"]
    assert d["removed"] == ["smithy"]
    assert d["changed"] == {"forum": ["depth", "tags"], "gate": ["exits"]}
    json.dumps(d)  # JSON-ready


def test_cli_digest_and_check(tmp_path, capsys):
    era = load_era_json(FIXTURES / "bronze.json")
    canon = tmp_path / "bronze.json"
    canon.write_text(dumps_canonical(era, pretty=True), encoding="utf-8")
    assert canon_main([str(FIXTURES / "bronze.json")]) == 0
    line = json.loads(capsys.readouterr().out.strip())
    assert line["ok"] is True and line["digest"] == digest(era)
    assert canon_main(["--check", str(canon)]) == 0
    assert json.loads(capsys.readouterr().out.strip())["canonical"] is True
    assert canon_main(["--check", str(canon), str(FIXTURES / "bronze.json")]) == 1
    lines = [json.loads(x) for x in capsys.readouterr().out.strip().splitlines()]
    assert [x["canonical"] for x in lines] == [True, False]


def test_cli_reports_errors_and_never_rewrites(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    src = (FIXTURES / "iron.json").read_bytes()
    assert canon_main([str(bad), str(tmp_path / "missing.json"), str(FIXTURES / "iron.json")]) == 1
    lines = [json.loads(x) for x in capsys.readouterr().out.strip().splitlines()]
    assert [x["ok"] for x in lines] == [False, False, True]
    assert lines[0]["error"]["code"] == "bad-json"
    assert lines[1]["error"]["code"] == "missing-file"
    assert (FIXTURES / "iron.json").read_bytes() == src
