from skeleton.automation.advanced_bots import ADVANCED_BOTS
from skeleton.automation.secretary import route


def test_secretary_knows_every_registered_specialist():
    names = {bot.name for bot in ADVANCED_BOTS}
    assert len(names) == 13
    assert {
        "security-auditor",
        "dependency-guardian",
        "api-contract",
        "release-guardian",
        "feature-builder",
    } <= names


def test_secretary_routes_security_plan_to_security_specialist():
    due = [bot.name for bot in ADVANCED_BOTS]
    selected = route("Code scanning reports a CORS authentication vulnerability and SSRF risk", due)
    assert "security-auditor" in selected


def test_secretary_routes_dependency_plan_to_dependency_specialist():
    due = [bot.name for bot in ADVANCED_BOTS]
    selected = route("Dependabot found a vulnerable dependency and lockfile needs repair", due)
    assert "dependency-guardian" in selected


def test_secretary_caps_parallel_specialists():
    due = [bot.name for bot in ADVANCED_BOTS]
    selected = route("security dependency CI regression performance release API docs coverage", due)
    assert len(selected) <= 3


def test_secretary_routes_approved_builder_without_model_keyword_dependency():
    due = [bot.name for bot in ADVANCED_BOTS]
    selected = route(
        "routine repository state with no feature words",
        due,
        build_authorization=object(),
    )
    assert "feature-builder" in selected


def test_secretary_never_routes_builder_without_exact_build_authority():
    due = [bot.name for bot in ADVANCED_BOTS]
    selected = route(
        "build-approved feature implement enhancement",
        due,
        build_authorization=None,
    )
    assert "feature-builder" not in selected
