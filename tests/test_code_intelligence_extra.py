from skeleton.school.code_intelligence import CodeIntelligenceEngine, CodeSignalKind, CodeTaskKind


def test_security_and_test_gap_are_prioritized():
    code = "password = 'secret'\neval(user_input)\n\ndef a(x):\n    return x\n\ndef b(x):\n    return x + 1\n"
    report = CodeIntelligenceEngine().analyze(code)
    assert any(s.kind == CodeSignalKind.SECURITY for s in report.signals)
    assert any(s.kind == CodeSignalKind.TEST_GAP for s in report.signals)
    assert report.tasks[0].kind == CodeTaskKind.REVIEW
