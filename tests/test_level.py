"""关卡加载测试：正常加载 + 每一类格式错误。

格式错误的用例都断言「报错信息里带文件名和字段名」——
定位不到出错的字段，报错就等于没报。
"""

import dataclasses
from pathlib import Path

import pytest

from bug_hunter.level import (
    LEVELS_DIR,
    LevelError,
    get_level,
    load_all_levels,
    load_level,
)

# 一份各字段都合法的最小关卡，下面的错误用例都在它基础上改出问题
MINIMAL_YAML = """\
id: t-001
title: 测试关
difficulty: 1
tags:
  - 边界值
intro: 这是一个介绍。
broken_code: |
  def f():
      return 1
correct_code: |
  def f():
      return 2
"""


def write_level(tmp_path: Path, content: str, name: str = "t-001.yaml") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_load_minimal_level(tmp_path):
    level = load_level(write_level(tmp_path, MINIMAL_YAML))
    assert level.id == "t-001"
    assert level.title == "测试关"
    assert level.difficulty == 1
    assert level.tags == ("边界值",)
    assert level.broken_code != level.correct_code
    assert level.hints == ()          # 没写的可选字段拿到默认值
    assert level.reference_test == ""


def test_builtin_levels_all_load():
    levels = load_all_levels(LEVELS_DIR)
    ids = [lv.id for lv in levels]
    # 扩到 15 关后这里不再钉死完整清单：只要求老三关还在，
    # 顺序永远符合 (difficulty, id) 升序
    for old_id in ("001-off-by-one", "002-empty-input", "003-stateful"):
        assert old_id in ids
    keys = [(lv.difficulty, lv.id) for lv in levels]
    assert keys == sorted(keys)
    # 每一关的两段代码必须真的有差异，否则关卡无解
    for lv in levels:
        assert lv.broken_code != lv.correct_code
        assert lv.hints  # 每一关都至少给了一条提示


def test_missing_dir_returns_empty_list(tmp_path):
    assert load_all_levels(tmp_path / "no-such-dir") == []


def test_ordering_by_difficulty_then_id(tmp_path):
    write_level(tmp_path,
                MINIMAL_YAML.replace("id: t-001", "id: 000-a").replace(
                    "difficulty: 1", "difficulty: 3"),
                name="000-a.yaml")
    write_level(tmp_path,
                MINIMAL_YAML.replace("id: t-001", "id: 999-z").replace(
                    "difficulty: 1", "difficulty: 2"),
                name="999-z.yaml")
    levels = load_all_levels(tmp_path)
    # 999-z 难度低，要排在 000-a 前面：难度优先，id 只是同难度时的决胜键
    assert [lv.id for lv in levels] == ["999-z", "000-a"]


def test_missing_field(tmp_path):
    path = write_level(tmp_path, MINIMAL_YAML.replace("intro: 这是一个介绍。\n", ""))
    with pytest.raises(LevelError) as err:
        load_level(path)
    assert "intro" in str(err.value)
    assert path.name in str(err.value)


def test_difficulty_string_rejected(tmp_path):
    # YAML 里 difficulty: "1" 得到的是字符串，必须报错而不是静默转换，
    # 否则写关卡的人永远不知道自己写错了
    path = write_level(tmp_path, MINIMAL_YAML.replace("difficulty: 1", 'difficulty: "1"'))
    with pytest.raises(LevelError) as err:
        load_level(path)
    assert "difficulty" in str(err.value)


def test_difficulty_bool_rejected(tmp_path):
    # true 读进来是 bool；bool 是 int 的子类，校验要能识破它
    path = write_level(tmp_path, MINIMAL_YAML.replace("difficulty: 1", "difficulty: true"))
    with pytest.raises(LevelError) as err:
        load_level(path)
    assert "difficulty" in str(err.value)


def test_difficulty_out_of_range(tmp_path):
    path = write_level(tmp_path, MINIMAL_YAML.replace("difficulty: 1", "difficulty: 6"))
    with pytest.raises(LevelError) as err:
        load_level(path)
    assert "1-5" in str(err.value)


def test_tags_not_list_rejected(tmp_path):
    path = write_level(tmp_path, MINIMAL_YAML.replace("tags:\n  - 边界值\n", "tags: 边界值\n"))
    with pytest.raises(LevelError) as err:
        load_level(path)
    assert "tags" in str(err.value)


def test_identical_codes_rejected(tmp_path):
    path = write_level(tmp_path, MINIMAL_YAML.replace("      return 2", "      return 1"))
    with pytest.raises(LevelError) as err:
        load_level(path)
    assert "没有 bug" in str(err.value)


def test_both_codes_empty_rejected(tmp_path):
    content = MINIMAL_YAML.replace("broken_code: |\n  def f():\n      return 1\n",
                                   'broken_code: ""\n')
    content = content.replace("correct_code: |\n  def f():\n      return 2\n",
                              'correct_code: ""\n')
    path = write_level(tmp_path, content)
    with pytest.raises(LevelError) as err:
        load_level(path)
    assert "空" in str(err.value)


def test_broken_yaml_syntax_rejected(tmp_path):
    path = write_level(tmp_path, "id: [没闭合的列表\n")
    with pytest.raises(LevelError):
        load_level(path)


def test_get_level_found():
    level = get_level("001-off-by-one")
    assert level is not None
    assert level.title == "差一"
    assert level.difficulty == 1
    assert len(level.hints) == 2


def test_get_level_not_found():
    assert get_level("999-not-exist") is None


def test_level_is_frozen():
    level = get_level("001-off-by-one")
    with pytest.raises(dataclasses.FrozenInstanceError):
        level.title = "改名"  # type: ignore[misc]
