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

def test_changelog_escapes_untrusted_markdown_and_rejects_bad_dates():
    import pytest
    from skeleton.build.delivery._util import DeliveryError

    text = render("1.0.0", [_c("feat(ui): <script>alert(1)</script> [click](bad)")],
                  date="2026-10-31")
    assert "<script>" not in text
    assert "\\<script\\>" in text
    assert "[click](bad)" not in text
    for invalid in ("2026-02-30", "2026-13-01", "2026-11-02 trailing"):
        with pytest.raises(DeliveryError):
            render("1.0.0", [], date=invalid)


def test_changelog_rejects_unbounded_change_stream():
    import pytest
    from itertools import repeat
    from skeleton.build.delivery._util import DeliveryError
    from skeleton.build.delivery.changelog import MAX_CHANGELOG_CHANGES

    with pytest.raises(DeliveryError, match="change count exceeds"):
        render("1.0.0", repeat(_c("fix: valid"), MAX_CHANGELOG_CHANGES + 1),
               date="2026-10-31")


def test_changelog_rejects_forged_heading_and_direct_control_subjects():
    import pytest
    from skeleton.ai.build.core.delivery import changelog as mirrored
    from skeleton.build.delivery._util import DeliveryError
    from skeleton.build.delivery.changelog import Change

    for render_fn in (render, mirrored.render):
        with pytest.raises(DeliveryError):
            render_fn("1.0.0\n# forged", [], date="2026-10-31")
        with pytest.raises(DeliveryError, match="subject or scope"):
            render_fn("1.0.0", [Change("abcdef1234", "feat", None,
                                       "safe\n# injected", False)], date="2026-10-31")
        with pytest.raises(DeliveryError, match="subject or scope"):
            render_fn("1.0.0", [Change("abcdef1234", "feat", None,
                                       "x" * 513, False)], date="2026-10-31")
