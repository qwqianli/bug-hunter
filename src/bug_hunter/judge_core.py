"""判题核心：只解释结果，不执行测试。

「怎么跑测试」每个平台一套实现（CLI 用 subprocess 起 pytest，
浏览器版在 Pyodide 里直接调用），但「怎么解释结果」只能有一套——
否则两个版本的判定迟早不一致。

所以这个文件只依赖标准库 enum，不许 import 任何执行层模块，
浏览器版（Pyodide）会原样加载它。
"""

import enum


class JudgeStatus(enum.Enum):
    PASS = "pass"                      # 过关
    NO_FAILURE = "no_failure"          # broken 版本上测试全过了 → 没抓到问题
    FALSE_POSITIVE = "false_positive"  # correct 版本上测试也失败 → 误报
    NO_TESTS = "no_tests"              # 没有收集到任何测试用例
    TEST_SYNTAX = "test_syntax"        # 玩家的测试代码本身有语法或 import 错误
    TIMEOUT = "timeout"                # 执行超时
    INTERNAL = "internal"              # 运行器内部异常


class RoundOutcome(enum.Enum):
    """一轮测试的原始结果。执行层负责把自己的结果映射成这个。"""

    ALL_PASS = "all_pass"          # 全部通过
    HAS_FAILURE = "has_failure"    # 至少一个用例失败
    NO_TESTS = "no_tests"          # 没收集到任何测试
    SYNTAX_ERROR = "syntax_error"  # 测试代码本身有语法/import 错误
    TIMEOUT = "timeout"
    ERROR = "error"                # 运行器内部错误


def decide(first: RoundOutcome, second: RoundOutcome | None = None) -> tuple[bool, JudgeStatus]:
    """纯函数：给定两轮的原始结果，返回 (是否过关, 最终状态)。

    这是 CLI 和 Web 共用的唯一判定逻辑，不允许有 IO、不允许 import 执行层。
    判定表与 docs/关卡设计规范.md 一致，任何改动都要两边同步验证。
    """
    # 第一轮不是「有失败」就没有进第二轮的意义：直接按第一轮定性
    if first is RoundOutcome.TIMEOUT:
        return False, JudgeStatus.TIMEOUT
    if first is RoundOutcome.NO_TESTS:
        return False, JudgeStatus.NO_TESTS
    if first is RoundOutcome.SYNTAX_ERROR:
        return False, JudgeStatus.TEST_SYNTAX
    if first is RoundOutcome.ERROR:
        return False, JudgeStatus.INTERNAL
    if first is RoundOutcome.ALL_PASS:
        # broken 上全过 = 没走到出问题的路径
        return False, JudgeStatus.NO_FAILURE

    # first is HAS_FAILURE：broken 上确实挂了，去 correct 上排除误报
    if second is RoundOutcome.ALL_PASS:
        return True, JudgeStatus.PASS
    if second is RoundOutcome.HAS_FAILURE:
        return False, JudgeStatus.FALSE_POSITIVE
    if second is RoundOutcome.NO_TESTS:
        return False, JudgeStatus.NO_TESTS
    if second is RoundOutcome.SYNTAX_ERROR:
        return False, JudgeStatus.TEST_SYNTAX
    if second is RoundOutcome.TIMEOUT:
        return False, JudgeStatus.TIMEOUT
    # ERROR，或调用方漏传 second（不该发生）：宁可报内部错误，不误判成过关
    return False, JudgeStatus.INTERNAL
