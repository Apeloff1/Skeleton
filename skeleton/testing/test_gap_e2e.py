"""End-to-end harness for the multi-gap starter packet."""
from skeleton.app.gap_cli import main as cli_main
from skeleton.app.gap_probe import probe
from skeleton.app.gap_ci import verify
from skeleton.app.gap_evidence import evidence_card
from skeleton.app.gap_status import generate_status
from skeleton.app.gap_health import health_card
from skeleton.app.gap_metrics import metrics_summary

def test_full_surface():
    assert probe() == 0
    assert verify() == 0
    e = evidence_card()
    assert e["ci_ok"] is True
    assert e["plane_count"] == 10
    s = generate_status()
    assert s["ready"] is True
    h = health_card()
    assert h["ready"] is True
    m = metrics_summary()
    assert m["plane_count"] == 10
    # CLI would print; we just confirm import and callable
    assert callable(cli_main)
