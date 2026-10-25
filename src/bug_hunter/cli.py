"""命令行界面：list / play / submit / hint / answer 五个子命令。

这个游戏的全部体验都在终端的几行字里——文案常量集中在文件顶部，
改文案不用钻进逻辑。
"""

import argparse
import os
import sys
from pathlib import Path

from bug_hunter import progress
from bug_hunter.judge import JudgeResult, JudgeStatus, judge
from bug_hunter.level import LEVELS_DIR, Level, get_level, load_all_levels

# ---- 文案（要改就改这里，不要去翻函数体） --------------------------------

_TEXT_NO_LEVELS = "还没有任何关卡。检查 src/bug_hunter/levels/ 目录。"
_TEXT_LEVEL_NOT_FOUND = "找不到这个关卡：{level_id}。运行 bug-hunter list 看看有哪些。"
_TEXT_TEST_NOT_FOUND = "找不到这个测试文件：{test_file}"
_TEXT_NEED_PY_SUFFIX = "测试文件要是 .py 结尾"
_TEXT_PLAYGROUND_RESET = "已重置 _playground/target.py"
_TEXT_PLAYGROUND_READY = "我在 _playground/target.py 里放好了代码。"
_TEXT_PLAYGROUND_TASK = "你的任务：在 _playground/ 里写一个 test_*.py，让它抓到这个 bug。"
_TEXT_PASS_EXTRA = "这正是测试该有的样子：只针对出错的那条路径。"
_TEXT_ALL_DONE = "全部关卡都过了，通关！"
_TEXT_NO_FAILURE_EXTRA = "想一想：这个函数在什么输入下会出错？换个数据再试试。"
_TEXT_FALSE_POSITIVE_EXTRA = "判题要求是：有 bug 时必须失败，没 bug 时必须通过。两个条件都要满足。"
_TEXT_NO_HINTS = "这一关没有写提示。"
_TEXT_HINT_HEADER = "提示 {index} / {total}"
_TEXT_HINT_MORE = "还想再要一条就再运行一次：\n  bug-hunter hint {level_id}"
_TEXT_HINTS_EXHAUSTED = (
    "这关的 {total} 条提示都给你了。\n\n"
    "如果还是卡着，可以看答案（bug-hunter answer {level_id}）——\n"
    "但记住，看过答案这关就不算自己解出来的了。"
)
_TEXT_ANSWER_MARKED = "（已标记为「看过答案」，这关不计入完成数）"
_TEXT_PASSED_AFTER_ANSWER = "（这关你看过答案，所以不计入完成数，但可以继续下一关）"
_TEXT_ANSWER_HEAD = "这是能过关的测试。看完之后，试着不看它自己再写一遍。"

_WIDE_LINE = "─" * 37

# list 的分组顺序和分类中文名：一张表管住，别在函数体里散落 if-else
_CATEGORY_ORDER = ("boundary", "exception", "isolation", "numeric", "contract", "sideeffect")
_CATEGORY_NAMES = {
    "boundary": "边界值",
    "exception": "异常流",
    "isolation": "测试隔离",
    "numeric": "数值精度",
    "contract": "类型与契约",
    "sideeffect": "副作用",
}

# ---- 颜色 ---------------------------------------------------------------

_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_GRAY = "\033[90m"
_RESET = "\033[0m"


def _paint(text: str, color: str) -> str:
    """按需上色。两个开关：设了 NO_COLOR 就不上色（通用约定）；
    输出被重定向到管道/文件时也不上色，免得日志里混进看不见的转义码。"""
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return text
    return color + text + _RESET


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。返回值就是退出码：过关 0，不过关 1，参数错误 2。"""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        # 只敲 bug-hunter 不带子命令：用户想学怎么用，不是犯错
        parser.print_help()
        return 0
    if args.command == "list":
        return cmd_list()
    if args.command == "play":
        return cmd_play(args.level_id)
    if args.command == "submit":
        return cmd_submit(args.level_id, args.test_file)
    if args.command == "hint":
        return cmd_hint(args.level_id)
    return cmd_answer(args.level_id)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bug-hunter",
        description="读代码、找 bug、只能靠写 pytest 测试通关的小游戏",
    )
    # 子命令不设 required：缺子命令时 main() 要打印用法并返回 0
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("list", help="列出所有关卡")
    play = sub.add_parser("play", help="进入一关")
    play.add_argument("level_id")
    submit = sub.add_parser("submit", help="提交测试文件，判题")
    submit.add_argument("level_id")
    submit.add_argument("test_file")
    hint = sub.add_parser("hint", help="看这一关的提示")
    hint.add_argument("level_id")
    answer = sub.add_parser("answer", help="看这一关的参考测试")
    answer.add_argument("level_id")
    return parser


def cmd_list() -> int:
    levels = load_all_levels(LEVELS_DIR)
    if not levels:
        print(_TEXT_NO_LEVELS)
        return 0
    progress_data = progress.load()
    known_ids = {lv.id for lv in levels}
    # 存档里可能留着已下架关卡的 id，统计完成数时忽略它们
    done = len([i for i in progress_data["completed"] if i in known_ids])
    print(f"共 {len(levels)} 关 · 已完成 {done} / {len(levels)}")
    for category in _CATEGORY_ORDER:
        group = [lv for lv in levels if lv.tags and lv.tags[0] == category]
        if not group:
            continue
        print()
        print(f"{category} {_CATEGORY_NAMES[category]}")
        for lv in group:
            print(_render_level_row(lv, progress_data))
    return 0


def _render_level_row(lv: Level, progress_data: dict) -> str:
    """一行一关：难度、id、标题、完成标记。

    「看过答案」优先于「完成」显示：这个状态最该被玩家看见，
    她才会记得这关不算自己解出来的。
    """
    if lv.id in progress_data["viewed_answer"]:
        mark = _paint("（看过答案）", _GRAY)
    elif lv.id in progress_data["completed"]:
        mark = _paint("✓", _GREEN)
    else:
        mark = ""
    # 中文显示宽度不固定，✓ 那一列会有一点歪，接受它
    return f"  [{lv.difficulty}] {lv.id:<24}{lv.title:<6}{mark}"


def cmd_play(level_id: str) -> int:
    level = get_level(level_id)
    if level is None:
        print(_TEXT_LEVEL_NOT_FOUND.format(level_id=level_id))
        return 1
    print(f"{level.title}  ·  难度 {level.difficulty}")
    print()
    print(level.intro)
    print()
    print(_WIDE_LINE)
    _prepare_playground(level)
    print(_TEXT_PLAYGROUND_READY)
    print(_TEXT_PLAYGROUND_TASK)
    print()
    print("写完运行：")
    print(f"  bug-hunter submit {level.id} _playground/test_你的名字.py")
    print()
    print("卡住了就运行：")
    print(f"  bug-hunter hint {level.id}")
    return 0


def _prepare_playground(level: Level) -> None:
    """把 broken_code 写进当前目录的 _playground/target.py。

    建在当前工作目录而不是藏进用户主目录：教学产品要让玩家
    看得见、打得开、删得掉。
    """
    playground = Path.cwd() / "_playground"
    playground.mkdir(exist_ok=True)
    target = playground / "target.py"
    if target.exists() and target.read_text(encoding="utf-8") != level.broken_code:
        # 里面是玩家上次玩别的关留下的代码，覆盖前说一声
        print(_TEXT_PLAYGROUND_RESET)
    target.write_text(level.broken_code, encoding="utf-8")


def cmd_submit(level_id: str, test_file: str) -> int:
    level = get_level(level_id)
    if level is None:
        print(_TEXT_LEVEL_NOT_FOUND.format(level_id=level_id))
        return 1
    path = Path(test_file)  # 相对路径天然相对当前工作目录，不做多余拼接
    if not path.is_file():
        print(_TEXT_TEST_NOT_FOUND.format(test_file=test_file))
        return 1
    if path.suffix != ".py":
        print(_TEXT_NEED_PY_SUFFIX)
        return 1
    result = judge(level.broken_code, level.correct_code, path)
    viewed_before = level_id in progress.load()["viewed_answer"]
    if result.passed:
        progress.record_pass(level_id)
    print(_render_result(result, level))
    if result.passed and viewed_before:
        print()
        print(_TEXT_PASSED_AFTER_ANSWER)
    return 0 if result.passed else 1


def cmd_hint(level_id: str) -> int:
    level = get_level(level_id)
    if level is None:
        print(_TEXT_LEVEL_NOT_FOUND.format(level_id=level_id))
        return 1
    if not level.hints:
        print(_TEXT_NO_HINTS)
        return 0
    total = len(level.hints)  # 不写死 2：关卡可能有 1 条或 3 条提示
    seen = progress.clamp_hint_index(level_id, total)
    if seen >= total:
        print(_TEXT_HINTS_EXHAUSTED.format(total=total, level_id=level_id))
        return 0
    index = seen + 1
    progress.record_hint(level_id, index)
    print(_TEXT_HINT_HEADER.format(index=index, total=total))
    print()
    print(level.hints[index - 1])
    print()
    print(_TEXT_HINT_MORE.format(level_id=level_id))
    return 0


def cmd_answer(level_id: str) -> int:
    level = get_level(level_id)
    if level is None:
        print(_TEXT_LEVEL_NOT_FOUND.format(level_id=level_id))
        return 1
    print("参考答案")
    print()
    print(_TEXT_ANSWER_HEAD)
    print()
    print(_WIDE_LINE)
    # YAML 块标量末尾自带换行，去掉再包上下边框，视觉才对称
    progress.record_answer(level_id)  # 先记再看：玩家看完关掉终端，这次「看过」也不丢
    print(level.reference_test.rstrip("\n"))
    print(_WIDE_LINE)
    print()
    print(_TEXT_ANSWER_MARKED)
    return 0


def _render_result(result: JudgeResult, level: Level) -> str:
    """把判题结果翻译成玩家在终端看到的一段话——这是产品的门面。"""
    if result.status is JudgeStatus.PASS:
        return _render_pass(result, level)
    return _render_non_pass(result)


def _render_pass(result: JudgeResult, level: Level) -> str:
    next_level = _next_level_after(level)
    tail = f"下一关：bug-hunter play {next_level.id}" if next_level else _TEXT_ALL_DONE
    # 判题器的 message 自带「过关 ✓」开头，彩色标题已经说过了，去掉避免重复
    body = result.message.removeprefix("过关 ✓ ")
    return "\n".join([
        _paint("过关 ✓", _GREEN),
        "",
        body,
        _TEXT_PASS_EXTRA,
        "",
        tail,
    ])


def _render_non_pass(result: JudgeResult) -> str:
    status = result.status
    if status is JudgeStatus.NO_FAILURE:
        headline, color, extra = "没抓到", _YELLOW, _TEXT_NO_FAILURE_EXTRA
    elif status is JudgeStatus.FALSE_POSITIVE:
        headline, color, extra = "误报了", _YELLOW, _TEXT_FALSE_POSITIVE_EXTRA
    elif status is JudgeStatus.NO_TESTS:
        headline, color, extra = "没有测试被执行", _YELLOW, ""
    elif status is JudgeStatus.TEST_SYNTAX:
        headline, color, extra = "测试代码有问题", _RED, ""
    elif status is JudgeStatus.TIMEOUT:
        headline, color, extra = "超时", _RED, ""
    else:  # INTERNAL
        headline, color, extra = "判题器出错了", _RED, ""
    lines = [_paint(headline, color), "", result.message]
    if extra:
        lines.extend(["", extra])
    if status in (JudgeStatus.TEST_SYNTAX, JudgeStatus.INTERNAL):
        # 玩家只需要能定位问题的头几行，不需要整屏 pytest 输出
        lines.append("")
        lines.extend(result.detail.strip().splitlines()[:5])
    return "\n".join(lines)


def _next_level_after(level: Level) -> Level | None:
    """关卡列表已按 (difficulty, id) 排好序，下一关就是排在后面的那个。"""
    levels = load_all_levels(LEVELS_DIR)
    for index, current in enumerate(levels):
        if current.id == level.id:
            next_index = index + 1
            return levels[next_index] if next_index < len(levels) else None
    return None


if __name__ == "__main__":
    sys.exit(main())
