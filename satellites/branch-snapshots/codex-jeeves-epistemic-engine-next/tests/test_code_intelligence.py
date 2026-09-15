from skeleton.school.code_intelligence import CodeIntelligenceEngine, CodeSignalKind, CodeTaskKind


def test_security_signal_and_priority():
    report = CodeIntelligenceEngine().analyze("password = 'secret'\neval(user_input)")
    assert any(signal.kind == CodeSignalKind.SECURITY for signal in report.signals)
    assert report.tasks[0].kind == CodeTaskKind.REVIEW


def test_missing_tests_drive_test_task():
    report = CodeIntelligenceEngine().analyze("def one(x):\n    return x + 1\n\ndef two(x):\n    return x * 2\n")
    assert any(signal.kind == CodeSignalKind.TEST_GAP for signal in report.signals)
    assert any(task.kind == CodeTaskKind.TEST for task in report.tasks)
