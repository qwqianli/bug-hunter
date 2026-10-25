"""内容质量测试：测的是关卡本身，不是加载代码。

代码错了会报错，内容错了不会——一关教的东西和另一关重复，
测试照样全绿，但玩家会觉得游戏很水。这组测试就是给内容兜底的。
"""

import re

import pytest

from bug_hunter.judge import JudgeStatus, judge
from bug_hunter.level import LEVELS_DIR, load_all_levels

ALL_LEVELS = load_all_levels(LEVELS_DIR)

# 关卡 id 的格式约定：三位数字 + 短横线 + 小写名（见 docs/关卡设计规范.md）
ID_PATTERN = re.compile(r"\d{3}-[a-z-]+")


@pytest.mark.parametrize("level", ALL_LEVELS, ids=lambda lv: lv.id)
def test_reference_test_really_catches_the_bug(level, tmp_path):
    """第 1 条：参考测试必须在 broken 上失败、在 correct 上通过。"""
    test_file = tmp_path / "test_reference.py"
    test_file.write_text(level.reference_test, encoding="utf-8")
    result = judge(level.broken_code, level.correct_code, test_file)
    assert result.status is JudgeStatus.PASS, f"{level.id}: {result.message}"


def test_ids_are_unique():
    ids = [lv.id for lv in ALL_LEVELS]
    assert len(ids) == len(set(ids)), "有重复的关卡 id"


def test_ids_follow_naming_convention():
    for lv in ALL_LEVELS:
        assert ID_PATTERN.fullmatch(lv.id), f"{lv.id} 不符合 999-name 的格式"


def test_difficulty_is_between_1_and_5():
    for lv in ALL_LEVELS:
        assert 1 <= lv.difficulty <= 5, lv.id


def test_difficulty_spans_at_least_three_values():
    # 全是 1 或全是 5 的难度曲线是假的曲线
    distinct = {lv.difficulty for lv in ALL_LEVELS}
    assert len(distinct) >= 3, f"只覆盖了难度 {distinct}"


def test_hints_count_is_1_to_3():
    for lv in ALL_LEVELS:
        assert 1 <= len(lv.hints) <= 3, f"{lv.id} 的提示条数不在 1-3"
        assert all(h.strip() for h in lv.hints), f"{lv.id} 有空提示"


def test_reference_test_has_assert():
    for lv in ALL_LEVELS:
        assert "assert" in lv.reference_test, f"{lv.id} 的参考测试没有断言"


def test_broken_codes_are_all_different():
    codes = [lv.broken_code for lv in ALL_LEVELS]
    assert len(codes) == len(set(codes)), "有两个关卡的 broken_code 完全相同（复制粘贴凑数）"
