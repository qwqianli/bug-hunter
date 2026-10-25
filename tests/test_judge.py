"""judge() 的验收测试：任务书表格里的 9 个场景，外加 1 条内部错误路径。

每个场景都断言 status、passed 和两轮的 pytest 返回码，
这样判题器状态机一旦走错分支，测试能精确指出是哪一格错了。
"""

import tempfile
from pathlib import Path

from bug_hunter.judge import JudgeStatus, judge

# 差一 bug：循环少走最后一个元素，只有最大值在末尾时才会暴露
BROKEN_FIND_MAX = (
    "def find_max(nums):\n"
    "    r = nums[0]\n"
    "    for i in range(1, len(nums)-1):\n"
    "        if nums[i] > r: r = nums[i]\n"
    "    return r\n"
)

CORRECT_FIND_MAX = (
    "def find_max(nums):\n"
    "    r = nums[0]\n"
    "    for i in range(1, len(nums)):\n"
    "        if nums[i] > r: r = nums[i]\n"
    "    return r\n"
)


def make_test_file(tmp_path: Path, content: str) -> Path:
    """写一个玩家测试文件。文件名遵守 pytest 收集规则，问题只可能出在内容上。"""
    path = tmp_path / "test_player.py"
    path.write_text(content, encoding="utf-8")
    return path


def test_good_test_passes(tmp_path):
    test_file = make_test_file(
        tmp_path,
        "from target import find_max\n"
        "def test_max_at_last():\n"
        "    assert find_max([1, 3, 5]) == 5\n",
    )
    result = judge(BROKEN_FIND_MAX, CORRECT_FIND_MAX, test_file)
    assert result.status is JudgeStatus.PASS
    assert result.passed is True
    assert result.round1_rc == 1
    assert result.round2_rc == 0


def test_idle_test_is_no_failure(tmp_path):
    # 空转：只断言函数存在，在两版代码上都会通过
    test_file = make_test_file(
        tmp_path,
        "from target import find_max\n"
        "def test_something():\n"
        "    assert find_max is not None\n",
    )
    result = judge(BROKEN_FIND_MAX, CORRECT_FIND_MAX, test_file)
    assert result.status is JudgeStatus.NO_FAILURE
    assert result.passed is False
    assert result.round1_rc == 0
    assert result.round2_rc == -1  # 第一轮全过，第二轮根本不用跑


def test_false_positive(tmp_path):
    # assert False 在两版代码上都会挂：broken 上挂 ≠ 抓到了 bug
    test_file = make_test_file(tmp_path, "def test_always_fails():\n    assert False\n")
    result = judge(BROKEN_FIND_MAX, CORRECT_FIND_MAX, test_file)
    assert result.status is JudgeStatus.FALSE_POSITIVE
    assert result.passed is False
    assert result.round1_rc == 1
    assert result.round2_rc == 1


def test_empty_file_is_no_tests(tmp_path):
    test_file = make_test_file(tmp_path, "")
    result = judge(BROKEN_FIND_MAX, CORRECT_FIND_MAX, test_file)
    assert result.status is JudgeStatus.NO_TESTS
    assert result.round1_rc == 5  # pytest「没收集到测试」的专用返回码


def test_non_test_function_is_no_tests(tmp_path):
    # 有函数但名字不是 test_ 开头，pytest 一样收集不到
    test_file = make_test_file(tmp_path, "def helper():\n    return 1\n")
    result = judge(BROKEN_FIND_MAX, CORRECT_FIND_MAX, test_file)
    assert result.status is JudgeStatus.NO_TESTS
    assert result.round1_rc == 5


def test_syntax_error_is_test_syntax(tmp_path):
    test_file = make_test_file(tmp_path, "def test_a(:\n    pass\n")
    result = judge(BROKEN_FIND_MAX, CORRECT_FIND_MAX, test_file)
    assert result.status is JudgeStatus.TEST_SYNTAX
    assert result.round1_rc == 2


def test_bad_import_is_test_syntax(tmp_path):
    test_file = make_test_file(
        tmp_path,
        "from target import no_such_name\n"
        "def test_a():\n"
        "    assert no_such_name == 1\n",
    )
    result = judge(BROKEN_FIND_MAX, CORRECT_FIND_MAX, test_file)
    assert result.status is JudgeStatus.TEST_SYNTAX
    assert result.round1_rc == 2


def test_infinite_loop_times_out_and_cleans_up(tmp_path):
    test_file = make_test_file(
        tmp_path,
        "from target import find_max\n"
        "def test_loop_forever():\n"
        "    while True:\n"
        "        pass\n",
    )
    result = judge(BROKEN_FIND_MAX, CORRECT_FIND_MAX, test_file, timeout=2)
    assert result.status is JudgeStatus.TIMEOUT
    assert result.round1_rc == -1
    assert "2" in result.message  # 文案里要告诉玩家卡了多少秒
    # 超时路径也必须清理临时目录：靠 TemporaryDirectory 的上下文管理器兜底
    leftovers = list(Path(tempfile.gettempdir()).glob("bug-hunter-judge-*"))
    assert leftovers == []


def test_source_test_file_is_untouched(tmp_path):
    content = (
        "from target import find_max\n"
        "def test_max_at_last():\n"
        "    assert find_max([1, 3, 5]) == 5\n"
    )
    test_file = make_test_file(tmp_path, content)
    mtime_before = test_file.stat().st_mtime_ns
    judge(BROKEN_FIND_MAX, CORRECT_FIND_MAX, test_file)
    assert test_file.read_text(encoding="utf-8") == content
    assert test_file.stat().st_mtime_ns == mtime_before


def test_missing_test_file_is_internal(tmp_path):
    # 判题器自己找不到文件：不算玩家的失败，也不许抛异常
    result = judge(BROKEN_FIND_MAX, CORRECT_FIND_MAX, tmp_path / "no_such_test.py")
    assert result.status is JudgeStatus.INTERNAL
    assert result.passed is False
    assert "FileNotFoundError" in result.detail


# ---- P5 追加：三条错误分支。只追加，上面 10 条原样不动 -----------------------
# 这些分支要造出「pytest 自己出错」的现场，真实复现成本高而且不可重复，
# 所以用假 _run_once 替身：这里测的是状态机映射，不是 pytest 本身


def test_round2_runner_error_is_internal(monkeypatch, tmp_path):
    """第一轮正常失败、第二轮判题器自己出错 → INTERNAL，而不是误报。"""
    import bug_hunter.judge as judge_module

    def fake_run_once(test_path, target_code, timeout):
        if target_code == "CORRECT":
            raise FileNotFoundError("第二轮复制测试文件失败")
        return 1, "1 failed"

    monkeypatch.setattr(judge_module, "_run_once", fake_run_once)
    result = judge_module.judge("BROKEN", "CORRECT", tmp_path / "test_x.py")
    assert result.status is JudgeStatus.INTERNAL
    assert result.round1_rc == 1


def test_round2_timeout_keeps_round1_rc(monkeypatch, tmp_path):
    """第一轮有失败（rc=1）、第二轮超时 → TIMEOUT，round1_rc 保持 1。"""
    import bug_hunter.judge as judge_module

    def fake_run_once(test_path, target_code, timeout):
        if target_code == "CORRECT":
            return -1, ""
        return 1, "1 failed"

    monkeypatch.setattr(judge_module, "_run_once", fake_run_once)
    result = judge_module.judge("BROKEN", "CORRECT", tmp_path / "test_x.py")
    assert result.status is JudgeStatus.TIMEOUT
    assert result.round1_rc == 1
    assert result.round2_rc == -1


def test_pytest_error_returncodes_map_to_internal(monkeypatch, tmp_path):
    """rc 3/4（pytest 内部错误/被中断）→ INTERNAL；第二轮的非零非一同样要映射对。"""
    import bug_hunter.judge as judge_module

    # 第一轮就返回 3/4：绝不能误判成过关
    for rc in (3, 4):
        def fake_round1(test_path, target_code, timeout, rc=rc):
            return rc, ""
        monkeypatch.setattr(judge_module, "_run_once", fake_round1)
        result = judge_module.judge("BROKEN", "CORRECT", tmp_path / "test_x.py")
        assert result.status is JudgeStatus.INTERNAL, f"第一轮 rc={rc} 应映射为 INTERNAL"
        assert result.passed is False

    # 第一轮正常失败后，第二轮的 2/5/3/4 分别对应什么状态
    for rc2, expected in [
        (2, JudgeStatus.TEST_SYNTAX),
        (5, JudgeStatus.NO_TESTS),
        (3, JudgeStatus.INTERNAL),
        (4, JudgeStatus.INTERNAL),
    ]:
        def fake_round2(test_path, target_code, timeout, rc2=rc2):
            return (1, "1 failed") if target_code == "BROKEN" else (rc2, "")
        monkeypatch.setattr(judge_module, "_run_once", fake_round2)
        result = judge_module.judge("BROKEN", "CORRECT", tmp_path / "test_x.py")
        assert result.status is expected, f"第二轮 rc={rc2} 应映射为 {expected}"
        assert result.passed is False
