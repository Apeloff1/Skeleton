from skeleton.build.delivery.changelog import next_version, parse_commit, render, required_bump


def _c(msg, sha="abcdef1234"):
    return parse_commit(sha, msg)


def test_parse():
    c = _c("feat(api): add thing")
    assert (c.type, c.scope, c.subject, c.breaking) == ("feat", "api", "add thing", False)
    assert _c("fix!: drop it").breaking
    assert _c("chore: x\n\nBREAKING CHANGE: y").breaking
    assert _c("random words").type == "other"
    assert parse_commit("s", "  ") is None


def test_bumps():
    assert required_bump([_c("fix: a")]) == "patch"
    assert required_bump([_c("fix: a"), _c("feat: b")]) == "minor"
    assert required_bump([_c("feat!: b")]) == "major"
    assert required_bump([_c("chore: x")]) is None
    assert str(next_version("1.2.3", [_c("feat: b")])) == "1.3.0"
    assert str(next_version("0.4.0", [_c("feat!: b")])) == "0.5.0"


def test_render():
    text = render("1.3.0", [_c("feat(ui): shiny"), _c("fix: bug"), _c("ci: hidden")], date="2026-10-31")
    assert text.startswith("## 1.3.0 (2026-10-31)")
    assert "- **ui:** shiny (abcdef1)" in text
    assert "hidden" not in text
    assert "_No user-facing changes._" in render("1.0.0", [_c("ci: x")], date="2026-10-31")
