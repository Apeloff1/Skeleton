"""Tests for skeleton.ops.cockpit (port of hyperforge-cockpit-sota scripts/*.test.mjs)."""

from __future__ import annotations

import asyncio
import json
import math
import sys

import pytest

from skeleton.ops.cockpit import (
    app_env,
    brand_check,
    browser_guard,
    migration_plan,
    qa_flight,
    sign_out_plan,
    smoke_verdict,
)
from skeleton.ops.cockpit.__main__ import main as cli


# ---------------------------------------------------------------- brand_check
def _site(root, **kw):
    p = root / brand_check.OG_SITE_REL_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(kw))


def _file(root, rel, size=10):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)


def codes(findings):
    return [f.code for f in findings]


def test_brand_utility_without_card_is_note_only(tmp_path):
    f = brand_check.compute_brand_warnings(has_canvas=False, workspace_root=tmp_path)
    assert codes(f) == ["placeholder-card"] and brand_check.brand_ok(f)


def test_brand_canvas_without_card_warns_card_and_type(tmp_path):
    f = brand_check.compute_brand_warnings(has_canvas=True, workspace_root=tmp_path)
    assert codes(f) == ["game-card-missing", "og-type-missing"]
    assert not brand_check.brand_ok(f)


def test_brand_canvas_full_kit_is_clean(tmp_path):
    _site(tmp_path, card="custom", type="x:game")
    _file(tmp_path, "public/og.jpg")
    _file(tmp_path, "public/x-banner.jpg")
    assert (
        brand_check.compute_brand_warnings(has_canvas=True, workspace_root=tmp_path)
        == []
    )


def test_brand_card_without_custom_flag(tmp_path):
    _file(tmp_path, "public/og.png")
    assert codes(
        brand_check.compute_brand_warnings(has_canvas=False, workspace_root=tmp_path)
    ) == ["card-flag-missing"]


def test_brand_heavy_card_and_banner(tmp_path):
    _site(tmp_path, card="custom", type="X:GAME")
    _file(tmp_path, "public/og.jpg", brand_check.MAX_CARD_BYTES + 1)
    _file(tmp_path, "public/x-banner.jpg", brand_check.MAX_CARD_BYTES + 1)
    assert codes(
        brand_check.compute_brand_warnings(has_canvas=True, workspace_root=tmp_path)
    ) == ["card-too-heavy", "banner-too-heavy"]


def test_brand_card_at_limit_is_fine(tmp_path):
    _site(tmp_path, card="custom")
    _file(tmp_path, "public/og.jpg", brand_check.MAX_CARD_BYTES)
    assert (
        brand_check.compute_brand_warnings(has_canvas=False, workspace_root=tmp_path)
        == []
    )


def test_brand_canvas_banner_missing(tmp_path):
    _site(tmp_path, card="custom", type="x:game")
    _file(tmp_path, "public/og.jpg")
    assert codes(
        brand_check.compute_brand_warnings(has_canvas=True, workspace_root=tmp_path)
    ) == ["banner-missing"]


def test_brand_jpg_preferred_over_png(tmp_path):
    _file(tmp_path, "public/og.jpg")
    _file(tmp_path, "public/og.png")
    assert brand_check.find_card(tmp_path).name == "og.jpg"


@pytest.mark.parametrize("text", ["not json", "[1,2]", "null", '"s"'])
def test_brand_malformed_site_is_empty(tmp_path, text):
    p = tmp_path / brand_check.OG_SITE_REL_PATH
    p.parent.mkdir(parents=True)
    p.write_text(text)
    assert brand_check.read_og_site(tmp_path) == {}


def test_brand_type_none_not_game():
    assert not brand_check.site_declares_og_type_game({"type": None})


# --------------------------------------------------------------- browser_guard
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/",
        "https://localhost/x",
        "http://[::1]:3000/",
        "http://localhost",
    ],
)
def test_guard_loopback_ok(url):
    assert browser_guard.checked_url(url, env={}) == url


@pytest.mark.parametrize(
    "url",
    [
        "file:///root/.grok/auth.json",
        "data:text/html,hi",
        "chrome://settings",
        "view-source:http://127.0.0.1/",
        "javascript:alert(1)",
        "not a url",
    ],
)
def test_guard_rejects_non_http(url):
    with pytest.raises(browser_guard.GuardError):
        browser_guard.checked_url(url, env={})


def test_guard_external_host_needs_opt_in():
    with pytest.raises(browser_guard.GuardError, match="not a loopback host"):
        browser_guard.checked_url("https://example.com/", env={})
    assert browser_guard.checked_url(
        "https://example.com/", env={"BROWSER_ALLOW_EXTERNAL_HOST": "1"}
    )
    with pytest.raises(browser_guard.GuardError):
        browser_guard.checked_url(
            "https://example.com/", env={"BROWSER_ALLOW_EXTERNAL_HOST": "true"}
        )


def test_guard_lookalike_host_rejected():
    with pytest.raises(browser_guard.GuardError):
        browser_guard.checked_url("http://127.0.0.1.evil.com/", env={})
    with pytest.raises(browser_guard.GuardError):
        browser_guard.checked_url("http://localhost@evil.com/", env={})


def test_guard_output_inside(tmp_path):
    out = browser_guard.checked_output_path(tmp_path / "shots" / "a.png", [tmp_path])
    assert out.name == "a.png"


def test_guard_output_traversal_and_sibling_prefix(tmp_path):
    allowed = tmp_path / "shots"
    allowed.mkdir()
    with pytest.raises(browser_guard.GuardError):
        browser_guard.checked_output_path(allowed / ".." / "x.png", [allowed])
    with pytest.raises(browser_guard.GuardError):
        browser_guard.checked_output_path(tmp_path / "shots-evil" / "x.png", [allowed])
    with pytest.raises(browser_guard.GuardError):
        browser_guard.checked_output_path(allowed, [allowed])


def test_guard_output_symlink_escape(tmp_path):
    allowed = tmp_path / "shots"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (allowed / "link").symlink_to(outside)
    with pytest.raises(browser_guard.GuardError):
        browser_guard.checked_output_path(allowed / "link" / "x.png", [allowed])


def test_guard_output_any_of_dirs(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert browser_guard.checked_output_path(b / "x.png", [a, b]).parent == b.resolve()


# -------------------------------------------------------------- migration_plan
def test_migration_name_basename():
    assert (
        migration_plan.migration_name("migrations/auth/0001_auth.sql")
        == "0001_auth.sql"
    )
    assert migration_plan.migration_name("0002.sql") == "0002.sql"
    assert migration_plan.migration_name("a\\b\\c.sql") == "c.sql"


def test_pending_sorted_filtered():
    p = migration_plan.pending_migrations(
        [
            "migrations/0003_c.sql",
            "migrations/auth",
            "migrations/0001_a.sql",
            "migrations/README.md",
            "migrations/0002_b.sql",
        ],
        ["0002_b.sql"],
    )
    assert [m.name for m in p] == ["0001_a.sql", "0003_c.sql"]


def test_pending_keyed_by_basename_across_dirs():
    p = migration_plan.pending_migrations(
        ["migrations/0001_auth.sql"], ["0001_auth.sql"]
    )
    assert p == []


def test_pending_dedupes_same_basename():
    p = migration_plan.pending_migrations(
        ["migrations/0001.sql", "migrations/auth/0001.sql"], []
    )
    assert len(p) == 1


def test_pending_empty():
    assert migration_plan.pending_migrations([], []) == []


def test_scan_dir_no_recursion(tmp_path):
    (tmp_path / "auth").mkdir()
    (tmp_path / "auth" / "0001_auth.sql").write_text("")
    (tmp_path / "0002.sql").write_text("")
    (tmp_path / "notes.txt").write_text("")
    assert [
        migration_plan.migration_name(p) for p in migration_plan.scan_dir(tmp_path)
    ] == ["0002.sql"]
    assert migration_plan.scan_dir(tmp_path / "missing") == []


def test_duplicate_basenames():
    d = migration_plan.duplicate_basenames(
        ["m/1.sql", "m/auth/1.sql", "m/2.sql", "m/x.md"]
    )
    assert d == {"1.sql": ["m/1.sql", "m/auth/1.sql"]}


# --------------------------------------------------------------- smoke_verdict
def vp(**kw):
    base = dict(status=200, title="App", body_text="hello world " * 20)
    base.update(kw)
    return smoke_verdict.viewport_record(**base)


def test_normalize_and_hash():
    assert smoke_verdict.normalize_body_text("  a \n\t b  ") == "a b"
    assert smoke_verdict.normalize_body_text(None) == ""
    assert smoke_verdict.normalized_body_text_hash(
        "a  b"
    ) == smoke_verdict.normalized_body_text_hash("a b")
    assert len(smoke_verdict.body_text_prefix("x" * 200)) == 64


def test_parse_args_defaults_and_flags():
    a = smoke_verdict.parse_smoke_args([])
    assert (
        a.url == smoke_verdict.DEFAULT_URL
        and a.out_png == smoke_verdict.DEFAULT_OUT_PNG
        and a.baseline == ""
    )
    a = smoke_verdict.parse_smoke_args(
        ["http://localhost:1/", "/o.png", "--baseline", "b.json"]
    )
    assert (a.url, a.out_png, a.baseline) == ("http://localhost:1/", "/o.png", "b.json")
    assert smoke_verdict.parse_smoke_args(["--baseline=x.json"]).baseline == "x.json"
    assert (
        smoke_verdict.parse_smoke_args(
            [], {"BROWSER_SMOKE_BASELINE": "e.json"}
        ).baseline
        == "e.json"
    )
    assert "requires" in smoke_verdict.parse_smoke_args(["--baseline"]).error
    assert "requires" in smoke_verdict.parse_smoke_args(["--baseline="]).error
    assert "unknown flag" in smoke_verdict.parse_smoke_args(["--nope"]).error


def test_derived_paths():
    assert smoke_verdict.derived_paths("/s/a.PNG") == {
        "mobilePng": "/s/a-mobile.png",
        "verdictJson": "/s/a.json",
    }


def test_compare_identical_clean():
    v = {"viewports": {"desktop": vp(), "mobile": vp()}}
    assert not smoke_verdict.compare_to_baseline(v, v).diverges_from_baseline


def test_compare_no_current():
    c = smoke_verdict.compare_to_baseline({"viewports": {}}, {"viewports": {"d": vp()}})
    assert c.diverges_from_baseline and "no viewport data" in c.reasons[0]


@pytest.mark.parametrize(
    "cur,needle",
    [
        (dict(status=500), "HTTP status changed"),
        (dict(title="Other"), "title changed"),
        (dict(horizontal_overflow=True), "overflow appeared"),
        (dict(console_errors=["boom"]), "errors appeared"),
        (dict(body_text="hi"), "collapsed"),
        (dict(body_text="hello world " * 40), "body text changed"),
        (dict(body_text="HELLO" + ("hello world " * 20)[5:]), "replaced"),
    ],
)
def test_compare_regressions(cur, needle):
    c = smoke_verdict.compare_to_baseline(
        {"viewports": {"d": vp(**cur)}}, {"viewports": {"d": vp()}}
    )
    assert c.diverges_from_baseline and any(needle in r for r in c.reasons), c.reasons


def test_compare_canvas_disappeared_and_missing_viewport():
    c = smoke_verdict.compare_to_baseline(
        {"viewports": {"d": vp(), "m": vp()}}, {"viewports": {"d": vp(has_canvas=True)}}
    )
    assert "d: canvas disappeared" in c.reasons
    assert "m: no baseline data for this viewport" in c.reasons


def test_compare_trivial_tail_change_ok():
    base = vp(body_text="hello world " * 20)
    cur = vp(body_text="hello world " * 20 + "!")
    assert not smoke_verdict.compare_to_baseline(
        {"viewports": {"d": cur}}, {"viewports": {"d": base}}
    ).diverges_from_baseline


def test_compare_errors_already_present_not_flagged():
    c = smoke_verdict.compare_to_baseline(
        {"viewports": {"d": vp(page_errors=["e"])}},
        {"viewports": {"d": vp(console_errors=["e"])}},
    )
    assert not c.diverges_from_baseline


@pytest.mark.parametrize(
    "raw,needle",
    [
        ("{", "invalid JSON"),
        ("null", "not a verdict"),
        ("[]", "not a verdict"),
        ('{"viewports": null}', "not a verdict"),
        ('{"viewports": []}', "not a verdict"),
    ],
)
def test_baseline_unreadable(raw, needle):
    c = smoke_verdict.baseline_comparison({"viewports": {"d": vp()}}, raw)
    assert c.diverges_from_baseline and needle in c.reasons[0]


def test_baseline_ok_roundtrip():
    v = {"viewports": {"d": vp()}}
    c = smoke_verdict.baseline_comparison(v, json.dumps(v))
    assert c.to_dict() == {"divergesFromBaseline": False, "reasons": []}


def test_exit_codes():
    assert smoke_verdict.exit_code_for({}) == 1
    assert smoke_verdict.exit_code_for(None) == 1
    assert smoke_verdict.exit_code_for({"d": vp()}) == 0
    assert smoke_verdict.exit_code_for({"d": vp(status=404)}) == 1
    assert smoke_verdict.exit_code_for({"d": vp(status=0)}) == 1
    assert smoke_verdict.exit_code_for({"d": vp(console_errors=["x"])}) == 2
    assert smoke_verdict.exit_code_for({"d": vp(status=500, console_errors=["x"])}) == 1


# --------------------------------------------------------------- sign_out_plan
def run(coro):
    return asyncio.run(coro)


class Rec:
    def __init__(self):
        self.calls = []

    def clear(self):
        self.calls.append("clear")

    def redirect(self):
        self.calls.append("redirect")


async def ok_req():
    return None


async def fail_req():
    raise RuntimeError("500")


async def hang_req():
    await asyncio.sleep(10)


def test_timeouts():
    assert sign_out_plan.sign_out_timeout_s(True) == 1.5
    assert sign_out_plan.sign_out_timeout_s(False) == 10.0


@pytest.mark.parametrize(
    "start,expected",
    [
        (ok_req, "ok"),
        (fail_req, "failed"),
        (hang_req, "timeout"),
        (lambda: 1, "ok"),
        (lambda: 1 / 0, "failed"),
    ],
)
def test_settle_within(start, expected):
    assert run(sign_out_plan.settle_within(start, 0.05)) == expected


@pytest.mark.parametrize("req", [ok_req, fail_req, hang_req])
def test_preview_always_clears_and_redirects(req):
    r = Rec()
    run(
        sign_out_plan.run_sign_out(
            live_preview=True,
            has_bearer=True,
            request_sign_out=req,
            clear_token=r.clear,
            redirect=r.redirect,
            timeout_s=0.05,
        )
    )
    assert r.calls == ["clear", "redirect"]


def test_preview_without_bearer_skips_request():
    r, hit = Rec(), []
    out = run(
        sign_out_plan.run_sign_out(
            live_preview=True,
            has_bearer=False,
            request_sign_out=lambda: hit.append(1),
            clear_token=r.clear,
            redirect=r.redirect,
        )
    )
    assert out is None and hit == [] and r.calls == ["clear", "redirect"]


def test_deployed_ok():
    r = Rec()
    assert (
        run(
            sign_out_plan.run_sign_out(
                live_preview=False,
                has_bearer=False,
                request_sign_out=ok_req,
                clear_token=r.clear,
                redirect=r.redirect,
            )
        )
        == "ok"
    )
    assert r.calls == ["clear", "redirect"]


@pytest.mark.parametrize(
    "req,outcome,msg",
    [(fail_req, "failed", "failed"), (hang_req, "timeout", "timed out")],
)
def test_deployed_failure_raises_and_keeps_session(req, outcome, msg):
    r = Rec()
    with pytest.raises(sign_out_plan.SignOutError, match=msg) as ei:
        run(
            sign_out_plan.run_sign_out(
                live_preview=False,
                has_bearer=True,
                request_sign_out=req,
                clear_token=r.clear,
                redirect=r.redirect,
                timeout_s=0.05,
            )
        )
    assert ei.value.outcome == outcome and r.calls == []


@pytest.mark.parametrize(
    "live,bearer,expect_req",
    [
        (True, False, False),
        (True, True, True),
        (False, False, True),
        (False, True, True),
    ],
)
def test_pre_sign_in_matrix(live, bearer, expect_req):
    r, hit = Rec(), []

    async def req():
        hit.append(1)
        raise RuntimeError("never fatal")

    run(
        sign_out_plan.run_pre_sign_in_sign_out(
            live_preview=live,
            has_bearer=bearer,
            request_sign_out=req,
            clear_token=r.clear,
            timeout_s=0.05,
        )
    )
    assert bool(hit) == expect_req and r.calls == ["clear"]


def test_pre_sign_in_timeout_never_raises():
    r = Rec()
    out = run(
        sign_out_plan.run_pre_sign_in_sign_out(
            live_preview=False,
            has_bearer=False,
            request_sign_out=hang_req,
            clear_token=r.clear,
            timeout_s=0.05,
        )
    )
    assert out == "timeout" and r.calls == ["clear"]


# --------------------------------------------------------------------- app_env
def test_parse_app_env_filters():
    env = app_env.parse_app_env(
        json.dumps(
            {
                "VITE_AUTH_ENABLED": "false",
                "SECRET": "x",
                "VITE_N": 1,
                "VITE_B": True,
                "VITE_OK": "",
            }
        )
    )
    assert env == {"VITE_AUTH_ENABLED": "false", "VITE_OK": ""}


@pytest.mark.parametrize("text", ["", "{", "[]", "null", '"x"', "3"])
def test_parse_app_env_garbage(text):
    assert app_env.parse_app_env(text) == {}


def test_read_app_env(tmp_path):
    assert app_env.read_app_env(tmp_path) == {}
    p = tmp_path / app_env.APP_ENV_REL_PATH
    p.parent.mkdir()
    p.write_text('{"VITE_X": "1"}')
    assert app_env.read_app_env(tmp_path) == {"VITE_X": "1"}


def test_merge_process_env_wins():
    assert app_env.merge_app_env(
        {"VITE_A": "file", "VITE_B": "file"}, {"VITE_A": "env"}
    ) == {"VITE_A": "env", "VITE_B": "file"}


def test_run_with_app_env_passes_env_and_code(tmp_path):
    p = tmp_path / app_env.APP_ENV_REL_PATH
    p.parent.mkdir()
    p.write_text('{"VITE_FLAG": "on"}')
    code = app_env.run_with_app_env(
        [
            sys.executable,
            "-c",
            "import os,sys; sys.exit(0 if os.environ.get('VITE_FLAG')=='on' else 5)",
        ],
        tmp_path,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert code == 0
    assert (
        app_env.run_with_app_env(
            [sys.executable, "-c", "raise SystemExit(7)"], tmp_path, env={}
        )
        == 7
    )


def test_run_with_app_env_missing_command(tmp_path):
    assert (
        app_env.run_with_app_env(["/nonexistent/definitely-not-here"], tmp_path, env={})
        == 127
    )
    with pytest.raises(ValueError):
        app_env.run_with_app_env([], tmp_path)


def test_run_with_app_env_signal_death(tmp_path):
    code = app_env.run_with_app_env(
        [
            sys.executable,
            "-c",
            "import os,signal; os.kill(os.getpid(), signal.SIGTERM)",
        ],
        tmp_path,
        env={},
    )
    assert code == 128 + 15


# ------------------------------------------------------------------- qa_flight
def test_wrap_angle():
    assert math.isclose(qa_flight.wrap_angle(2 * math.pi + 0.1), 0.1, abs_tol=1e-9)
    assert math.isclose(qa_flight.wrap_angle(-2 * math.pi - 0.1), -0.1, abs_tol=1e-9)


def test_flight_pass():
    p = qa_flight.FlightProbe.from_dict(
        {"ok": True, "y0": 0, "yA": 0.4, "y1": 0.4, "yD": 0.0, "speed": 20}
    )
    v = qa_flight.evaluate_flight(p, [])
    assert v.passed and v.d_a > 0 and v.d_d < 0


def test_flight_wraps_across_pi():
    p = qa_flight.FlightProbe(
        ok=True,
        y0=math.pi - 0.05,
        y_a=-math.pi + 0.1,
        y1=-math.pi + 0.1,
        y_d=math.pi - 0.1,
    )
    v = qa_flight.evaluate_flight(p)
    assert v.passed, v.failures


def test_flight_failures():
    p = qa_flight.FlightProbe(ok=True, y0=0, y_a=0.01, y1=0.01, y_d=0.02, speed=1)
    v = qa_flight.evaluate_flight(p, ["err"], min_speed=5)
    assert not v.passed and len(v.failures) == 4


def test_flight_no_probe():
    v = qa_flight.evaluate_flight(
        qa_flight.FlightProbe.from_dict({"ok": False, "reason": "no probe"})
    )
    assert not v.passed and "no probe" in v.failures[0]
    assert not qa_flight.FlightProbe.from_dict(None).ok


def test_flight_from_dict_y1_falls_back_to_yA():
    p = qa_flight.FlightProbe.from_dict({"ok": True, "y0": 0, "yA": 0.3, "yD": 0.1})
    assert p.y1 == 0.3


# ------------------------------------------------------------------------- CLI
def test_cli_brand_check(tmp_path, capsys):
    assert cli(["brand-check", "--root", str(tmp_path)]) == 0
    assert cli(["brand-check", "--root", str(tmp_path), "--canvas"]) == 1
    assert "game-card-missing" in capsys.readouterr().out


def test_cli_smoke_compare(tmp_path, capsys):
    v = {"viewports": {"d": vp()}}
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(v))
    b.write_text(json.dumps(v))
    assert cli(["smoke-compare", str(a), str(b)]) == 0
    a.write_text(json.dumps({"viewports": {"d": vp(status=500)}}))
    assert cli(["smoke-compare", str(a), str(b)]) == 3


def test_cli_migrations(tmp_path, capsys):
    (tmp_path / "0001.sql").write_text("")
    (tmp_path / "0002.sql").write_text("")
    assert cli(["migrations-pending", str(tmp_path), "--applied", "0001.sql"]) == 0
    assert [m["name"] for m in json.loads(capsys.readouterr().out)] == ["0002.sql"]


def test_cli_guard_url(monkeypatch, capsys):
    monkeypatch.delenv("BROWSER_ALLOW_EXTERNAL_HOST", raising=False)
    assert cli(["guard-url", "http://127.0.0.1/"]) == 0
    assert cli(["guard-url", "file:///etc/passwd"]) == 1


def test_cli_flight(tmp_path, capsys):
    f = tmp_path / "p.json"
    f.write_text(
        json.dumps(
            {
                "probe": {"ok": True, "y0": 0, "yA": 0.3, "y1": 0.3, "yD": 0},
                "errors": [],
            }
        )
    )
    assert cli(["flight", str(f)]) == 0
    f.write_text(
        json.dumps(
            {
                "probe": {"ok": True, "y0": 0, "yA": 0.3, "y1": 0.3, "yD": 0},
                "errors": ["x"],
            }
        )
    )
    assert cli(["flight", str(f)]) == 1


def test_cli_with_app_env(tmp_path):
    assert cli(["with-app-env"]) == 2
    assert (
        cli(
            [
                "with-app-env",
                "--root",
                str(tmp_path),
                "--",
                sys.executable,
                "-c",
                "pass",
            ]
        )
        == 0
    )
