"""judge_core.decide() 的判定表测试：判定表 11 行，一行一条。

decide() 是 CLI 和 Web 共用的唯一判定逻辑——这里每一条都在钉住
「两个版本行为必须一致」的那张表。
"""

from bug_hunter.judge_core import JudgeStatus, RoundOutcome, decide


def test_first_timeout():
    assert decide(RoundOutcome.TIMEOUT) == (False, JudgeStatus.TIMEOUT)


def test_first_no_tests():
    assert decide(RoundOutcome.NO_TESTS) == (False, JudgeStatus.NO_TESTS)


def test_first_syntax_error():
    assert decide(RoundOutcome.SYNTAX_ERROR) == (False, JudgeStatus.TEST_SYNTAX)


def test_first_error():
    assert decide(RoundOutcome.ERROR) == (False, JudgeStatus.INTERNAL)


def test_first_all_pass():
    assert decide(RoundOutcome.ALL_PASS) == (False, JudgeStatus.NO_FAILURE)


def test_has_failure_then_all_pass():
    assert decide(RoundOutcome.HAS_FAILURE, RoundOutcome.ALL_PASS) == (True, JudgeStatus.PASS)


def test_has_failure_then_has_failure():
    assert decide(RoundOutcome.HAS_FAILURE, RoundOutcome.HAS_FAILURE) == (
        False, JudgeStatus.FALSE_POSITIVE,
    )


def test_has_failure_then_no_tests():
    assert decide(RoundOutcome.HAS_FAILURE, RoundOutcome.NO_TESTS) == (False, JudgeStatus.NO_TESTS)


def test_has_failure_then_syntax_error():
    assert decide(RoundOutcome.HAS_FAILURE, RoundOutcome.SYNTAX_ERROR) == (
        False, JudgeStatus.TEST_SYNTAX,
    )


def test_has_failure_then_timeout():
    assert decide(RoundOutcome.HAS_FAILURE, RoundOutcome.TIMEOUT) == (False, JudgeStatus.TIMEOUT)


def test_has_failure_then_error():
    assert decide(RoundOutcome.HAS_FAILURE, RoundOutcome.ERROR) == (False, JudgeStatus.INTERNAL)
