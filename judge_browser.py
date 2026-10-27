"""浏览器版判题器（Pyodide 环境里加载，也被在线版自检使用）。

Pyodide 没有 subprocess，起不了 pytest 子进程，所以在当前解释器里
直接执行：把两段代码 exec 进同一个命名空间，逐个调用 test_ 函数。
只负责「怎么跑」，判定全部交给 judge_core.decide()。

浏览器里没有超时机制（杀不掉正在跑的同步代码），
所以永远不返回 "timeout"——页面文案要明示这个限制。
"""

import sys
import types


def run_tests(test_code: str, target_code: str) -> str:
    """返回 RoundOutcome 的字符串值：

    all_pass / has_failure / no_tests / syntax_error / error
    """
    namespace: dict = {}
    try:
        exec(compile(target_code, "target.py", "exec"), namespace)
    except Exception:
        # 关卡代码随包发布、经过自检，正常不会挂；挂了按运行器错误处理
        return "error"

    # 玩家测试写的是 from target import ...：把刚执行的代码登记成 target
    # 模块，浏览器里的 import 才能和 CLI（target.py 就在被测目录）行为一致
    target_module = types.ModuleType("target")
    for key, value in namespace.items():
        setattr(target_module, key, value)
    previous = sys.modules.get("target")
    sys.modules["target"] = target_module
    try:
        return _run_test_code(test_code, namespace)
    finally:
        # 不清理会污染下一次判题的 import
        if previous is None:
            sys.modules.pop("target", None)
        else:
            sys.modules["target"] = previous


def _run_test_code(test_code: str, namespace: dict) -> str:
    try:
        exec(compile(test_code, "test_player.py", "exec"), namespace)
    except (SyntaxError, ImportError):
        return "syntax_error"
    except Exception:
        # 模块层抛出的其他异常，pytest 同样按「收集错误」处理，保持一致
        return "syntax_error"

    tests = [obj for name, obj in namespace.items()
             if name.startswith("test_") and callable(obj)]
    if not tests:
        return "no_tests"

    failed = 0
    for test_fn in tests:
        # dict 保持定义顺序，与 pytest 的执行顺序一致
        try:
            test_fn()
        except Exception:
            # AssertionError 和其他异常都算这个用例失败，与 pytest 语义一致
            failed += 1
    return "has_failure" if failed else "all_pass"
