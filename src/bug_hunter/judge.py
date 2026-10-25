"""判题器：拿玩家写的一份 pytest 测试，在两段代码上各跑一轮，按「双条件」给结论。

双条件 = broken 版本上必须至少挂一个用例，correct 版本上必须全部通过。
只满足前一条是误报，只满足后一条是空转——都不算过关。
"""

import enum
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


class JudgeStatus(enum.Enum):
    PASS = "pass"                      # 过关
    NO_FAILURE = "no_failure"          # broken 版本上测试全过了 → 没抓到问题
    FALSE_POSITIVE = "false_positive"  # correct 版本上测试也失败 → 误报
    NO_TESTS = "no_tests"              # 没有收集到任何测试用例
    TEST_SYNTAX = "test_syntax"        # 玩家的测试代码本身有语法或 import 错误
    TIMEOUT = "timeout"                # 执行超时
    INTERNAL = "internal"              # 运行器内部异常（返回码 3/4 等）


@dataclass
class JudgeResult:
    passed: bool
    status: JudgeStatus
    message: str            # 给玩家看的一句话中文说明，不出现 returncode / traceback 等术语
    detail: str = ""        # pytest 输出摘要，只保留最后 800 字符
    round1_rc: int = -1     # 第一轮返回码，-1 表示没跑到
    round2_rc: int = -1     # 第二轮返回码


# 给玩家看的文案集中在顶部：message 本身是产品的一部分，改文案不该翻函数体
_MESSAGES = {
    JudgeStatus.PASS: "过关 ✓ 你的测试精准地抓住了这个问题，而且没有冤枉正确代码。",
    JudgeStatus.NO_FAILURE: "测试在有 bug 的版本上全部通过了，说明没走到出问题的路径。想想它哪里会出错。",
    JudgeStatus.FALSE_POSITIVE: "你的测试在正确版本上也失败了——它可能顺带检查了不该检查的东西。",
    JudgeStatus.NO_TESTS: "没有执行到任何测试用例。检查一下函数名是不是以 test_ 开头，文件是不是 test_*.py。",
    JudgeStatus.TEST_SYNTAX: "测试代码本身有错误（语法或 import 写错了），先把它修到能跑起来。",
    JudgeStatus.INTERNAL: "判题器自己出了问题，把下面这段发给开发者看看。",
}


def judge(
    broken_code: str,
    correct_code: str,
    test_path: Path,
    timeout: float = 10.0,
) -> JudgeResult:
    """双条件判题：第一轮跑 broken，有测试失败再跑 correct 复核。

    接收两段代码（而不是关卡对象）是刻意的：判题器要在没有关卡系统的
    情况下独立运行和被测试。任何情况下都不抛异常，一律返回 JudgeResult。
    """
    try:
        rc1, detail1 = _run_once(test_path, broken_code, timeout)
    except OSError as exc:
        # 判题器自己的文件操作出了问题（比如测试文件不存在），不是玩家的错
        return _internal(f"{type(exc).__name__}: {exc}", -1, -1)

    if rc1 == -1:
        return _timeout(timeout, rc1, -1)
    if rc1 != 1:
        return _first_round_result(rc1, detail1, timeout)

    # 走到这里说明 rc1 == 1：broken 上确实挂了用例，才值得去 correct 上排除误报
    try:
        rc2, detail2 = _run_once(test_path, correct_code, timeout)
    except OSError as exc:
        return _internal(f"{type(exc).__name__}: {exc}", rc1, -1)

    if rc2 == -1:
        return _timeout(timeout, rc1, rc2)
    return _second_round_result(rc1, rc2, detail2, timeout)


def _run_once(test_path: Path, target_code: str, timeout: float) -> tuple[int, str]:
    """把 target_code 写进一个全新的临时目录，跑一轮玩家的测试。

    返回 (pytest 返回码, 输出的最后 800 字符)。超时统一返回 (-1, "")，
    由 judge() 翻译成 TIMEOUT。每轮都用全新目录，target.py 不可能
    残留上一轮的 broken/correct 内容。
    """
    with tempfile.TemporaryDirectory(prefix="bug-hunter-judge-") as tmp:
        workdir = Path(tmp)
        # 玩家的测试靠 from target import ... 拿到被测代码，
        # 所以测试副本和 target.py 必须躺在同一个目录里
        shutil.copy(test_path, workdir / test_path.name)
        # Windows 上不写 encoding 会被按本地编码解释，中文注释会炸
        (workdir / "target.py").write_text(target_code, encoding="utf-8")
        command = [
            sys.executable, "-m", "pytest", test_path.name,
            "-q", "--no-header",
            # 关掉 pytest 缓存：既不在临时目录留垃圾，也让两轮互不污染
            "-p", "no:cacheprovider",
        ]
        try:
            finished = subprocess.run(
                command,
                cwd=workdir,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            # 只捕获超时这一种异常；文件读写错误要留给 judge() 报 INTERNAL
            return -1, ""
        output = (finished.stdout or "") + (finished.stderr or "")
        return finished.returncode, output[-800:]


def _first_round_result(rc1: int, detail: str, timeout: float) -> JudgeResult:
    """第一轮状态表。rc == 1 不在这里——那是进入第二轮的唯一入口。"""
    if rc1 == 0:
        status = JudgeStatus.NO_FAILURE
    elif rc1 == 5:
        # rc == 5 是「没收集到测试」。不单独处理，空文件会被当成「抓到了」
        status = JudgeStatus.NO_TESTS
    elif rc1 == 2:
        status = JudgeStatus.TEST_SYNTAX
    else:
        # 返回码 3/4 是 pytest 内部错误；其他未知返回码也归到这里：
        # 宁可报内部错误，也不能把异常情况误判成过关
        status = JudgeStatus.INTERNAL
    return JudgeResult(False, status, _message_for(status, timeout), detail, rc1, -1)


def _second_round_result(rc1: int, rc2: int, detail: str, timeout: float) -> JudgeResult:
    """第二轮状态表：broken 上已经失败，此刻只看 correct 上的表现。"""
    if rc2 == 0:
        status, passed = JudgeStatus.PASS, True
    elif rc2 == 1:
        status, passed = JudgeStatus.FALSE_POSITIVE, False
    elif rc2 == 5:
        status, passed = JudgeStatus.NO_TESTS, False
    elif rc2 == 2:
        status, passed = JudgeStatus.TEST_SYNTAX, False
    else:
        status, passed = JudgeStatus.INTERNAL, False
    return JudgeResult(passed, status, _message_for(status, timeout), detail, rc1, rc2)


def _message_for(status: JudgeStatus, timeout: float) -> str:
    """TIMEOUT 的文案要带上秒数，其余状态用固定文案。"""
    if status is JudgeStatus.TIMEOUT:
        return f"测试跑了超过 {timeout} 秒还没结束，可能有死循环。"
    return _MESSAGES[status]


def _timeout(timeout: float, rc1: int, rc2: int) -> JudgeResult:
    return JudgeResult(
        False, JudgeStatus.TIMEOUT, _message_for(JudgeStatus.TIMEOUT, timeout), "", rc1, rc2
    )


def _internal(detail: str, rc1: int, rc2: int) -> JudgeResult:
    # INTERNAL 是唯一允许玩家看到技术细节的状态，detail 要保留现场
    return JudgeResult(False, JudgeStatus.INTERNAL, _MESSAGES[JudgeStatus.INTERNAL], detail, rc1, rc2)
