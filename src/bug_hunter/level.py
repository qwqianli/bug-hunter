"""关卡系统：从 YAML 文件读出「一段有 bug 的代码 + 一段正确的代码」。

校验失败一律抛 LevelError，错误信息永远带文件名和字段名——
写关卡的人要能一眼看出是哪个文件的哪个字段错了。
"""

from dataclasses import dataclass
from pathlib import Path

import yaml


class LevelError(ValueError):
    """关卡文件格式错误。错误信息必须包含文件名和出错的字段名。"""


@dataclass(frozen=True)
class Level:
    id: str
    title: str
    difficulty: int            # 1-5
    tags: tuple[str, ...]      # 用 tuple 配合 frozen，加载时把 YAML 的 list 转过来
    intro: str
    broken_code: str
    correct_code: str
    hints: tuple[str, ...] = ()
    reference_test: str = ""


# 关卡文件跟代码打包在一起，从包自身定位，不依赖玩家当前在哪个目录
LEVELS_DIR = Path(__file__).parent / "levels"

_REQUIRED_FIELDS = ("id", "title", "difficulty", "tags", "intro",
                    "broken_code", "correct_code")


def load_level(path: Path) -> Level:
    """从单个 YAML 文件加载并校验，任何格式问题都抛 LevelError。"""
    data = _read_yaml(path)
    _check_required(data, path)
    _check_codes(data, path)
    return Level(
        id=data["id"],
        title=data["title"],
        difficulty=_check_difficulty(data, path),
        tags=_check_tags(data, path),
        intro=data["intro"],
        broken_code=data["broken_code"],
        correct_code=data["correct_code"],
        hints=_check_hints(data, path),
        reference_test=data.get("reference_test", ""),
    )  # 先校验后构造：宁可让 Level 一出生就是合法的，也不要「带病加载」


def load_all_levels(levels_dir: Path) -> list[Level]:
    """加载目录下所有 *.yaml，按 (difficulty, id) 升序排序。

    目录不存在 → 返回空列表（没装关卡不算错误）；
    任何一个文件格式错误 → 直接抛 LevelError，绝不静默跳过坏关卡。
    """
    if not levels_dir.is_dir():
        return []
    levels = [load_level(path) for path in sorted(levels_dir.glob("*.yaml"))]
    # 排序键是二元组：同难度时按 id 排，玩家看到的关卡顺序才稳定
    levels.sort(key=lambda level: (level.difficulty, level.id))
    return levels


def get_level(level_id: str) -> Level | None:
    """从包内置的 levels 目录按 id 查找。找不到返回 None。"""
    for level in load_all_levels(LEVELS_DIR):
        if level.id == level_id:
            return level
    return None


def _read_yaml(path: Path) -> dict:
    # safe_load 只认数据不执行代码；yaml.load 能执行任意代码，是安全漏洞
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LevelError(f"YAML 语法错误：{exc}（文件：{path.name}）") from exc
    if not isinstance(data, dict):
        raise LevelError(f"文件内容不是「字段: 值」的结构（文件：{path.name}）")
    return data


def _check_required(data: dict, path: Path) -> None:
    for field_name in _REQUIRED_FIELDS:
        if field_name not in data:
            raise LevelError(f"缺少字段 {field_name}（文件：{path.name}）")
    for field_name in ("broken_code", "correct_code"):
        # YAML 里写 broken_code:（冒号后面空着）得到的是 None，先拦下来
        if not isinstance(data[field_name], str):
            raise LevelError(f"字段 {field_name} 必须是字符串（文件：{path.name}）")


def _check_difficulty(data: dict, path: Path) -> int:
    # 用 type() 而不是 isinstance()：YAML 的 true 读进来是 bool，
    # bool 是 int 的子类，isinstance 会把它放过去
    if type(data["difficulty"]) is not int:
        raise LevelError(
            f"字段 difficulty 必须是整数，现在是 {type(data['difficulty']).__name__}"
            f"（文件：{path.name}）"
        )
    if not 1 <= data["difficulty"] <= 5:
        raise LevelError(
            f"字段 difficulty 必须在 1-5 之间，现在是 {data['difficulty']}（文件：{path.name}）"
        )
    return data["difficulty"]


def _check_tags(data: dict, path: Path) -> tuple[str, ...]:
    if not isinstance(data["tags"], list):
        raise LevelError(f"字段 tags 必须是列表（文件：{path.name}）")
    return tuple(data["tags"])


def _check_hints(data: dict, path: Path) -> tuple[str, ...]:
    hints = data.get("hints", [])
    if not isinstance(hints, list):
        raise LevelError(f"可选字段 hints 如果要写，必须是列表（文件：{path.name}）")
    return tuple(hints)


def _check_codes(data: dict, path: Path) -> None:
    # 先查「都为空」再查「完全相同」：两段都空时，报「是空的」比报「没有 bug」更接近真相
    if not data["broken_code"].strip() and not data["correct_code"].strip():
        raise LevelError(f"broken_code 和 correct_code 都是空的（文件：{path.name}）")
    if data["broken_code"] == data["correct_code"]:
        raise LevelError(
            f"broken_code 和 correct_code 完全相同，这一关根本没有 bug（文件：{path.name}）"
        )
