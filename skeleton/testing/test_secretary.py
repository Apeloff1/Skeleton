from skeleton.automation.advanced_bots import ADVANCED_BOTS
from skeleton.automation.secretary import route


def test_secretary_knows_every_registered_specialist():
    names = {bot.name for bot in ADVANCED_BOTS}
    assert len(names) == 12
    assert {"security-auditor", "dependency-guardian", "api-contract", "release-guardian"} <= names


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
