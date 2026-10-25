"""判题器：拿玩家写的一份 pytest 测试，在两段代码上各跑一轮，按「双条件」给结论。

双条件 = broken 版本上必须至少挂一个用例，correct 版本上必须全部通过。
只满足前一条是误报，只满足后一条是空转——都不算过关。

「怎么解释结果」在 judge_core.decide()（CLI 和 Web 共用的唯一判定逻辑），
这个文件只负责「怎么跑测试」：临时目录 + pytest 子进程。
"""

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from bug_hunter.judge_core import JudgeStatus, RoundOutcome, decide

# JudgeStatus 的定义已移到 judge_core（浏览器版也要用它），在这里重新导出：
# 既有代码 `from bug_hunter.judge import JudgeStatus` 不受影响
__all__ = ["JudgeResult", "JudgeStatus", "RoundOutcome", "judge"]


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
    # 宿主环境缺 pytest 时，子进程只会返回非 0，会被误映射成「误报」——
    # 让正确的测试背锅。起子进程前先查出这种环境问题，给出能动手解决的提示
    if importlib.util.find_spec("pytest") is None:
        return JudgeResult(
            passed=False,
            status=JudgeStatus.INTERNAL,
            message="这个游戏需要一个能运行 pytest 的 Python 环境，请先安装：pip install pytest",
        )
    try:
        rc1, detail1 = _run_once(test_path, broken_code, timeout)
    except OSError as exc:
        # 判题器自己的文件操作出了问题（比如测试文件不存在），不是玩家的错
        return _internal(f"{type(exc).__name__}: {exc}", -1, -1)

    outcome1 = _outcome_from_rc(rc1)
    if outcome1 is not RoundOutcome.HAS_FAILURE:
        # 第一轮没挂用例（或超时/出错）：没有进第二轮的意义，直接定性
        passed, status = decide(outcome1)
        return JudgeResult(passed, status, _message_for(status, timeout), detail1, rc1, -1)

    # 走到这里说明第一轮有失败：去 correct 上排除误报
    try:
        rc2, detail2 = _run_once(test_path, correct_code, timeout)
    except OSError as exc:
        return _internal(f"{type(exc).__name__}: {exc}", rc1, -1)

    passed, status = decide(outcome1, _outcome_from_rc(rc2))
    return JudgeResult(passed, status, _message_for(status, timeout), detail2, rc1, rc2)


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


def _outcome_from_rc(rc: int) -> RoundOutcome:
    """pytest 返回码 → 一轮的原始结果。

    返回码语义是实测过的，不许猜：
    0 全过 / 1 有失败 / 2 收集错误 / 5 没收集到测试；
    -1 是 _run_once 的超时哨兵；3/4 等罕见码统一按运行器错误兜底。
    """
    if rc == 0:
        return RoundOutcome.ALL_PASS
    if rc == 1:
        return RoundOutcome.HAS_FAILURE
    if rc == 2:
        return RoundOutcome.SYNTAX_ERROR
    if rc == 5:
        return RoundOutcome.NO_TESTS
    if rc == -1:
        return RoundOutcome.TIMEOUT
    return RoundOutcome.ERROR


def _message_for(status: JudgeStatus, timeout: float) -> str:
    """TIMEOUT 的文案要带上秒数，其余状态用固定文案。"""
    if status is JudgeStatus.TIMEOUT:
        return f"测试跑了超过 {timeout} 秒还没结束，可能有死循环。"
    return _MESSAGES[status]


def _internal(detail: str, rc1: int, rc2: int) -> JudgeResult:
    # INTERNAL 是唯一允许玩家看到技术细节的状态，detail 要保留现场
    return JudgeResult(False, JudgeStatus.INTERNAL, _MESSAGES[JudgeStatus.INTERNAL], detail, rc1, rc2)
