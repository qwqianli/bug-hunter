"""关卡自检：确保每一关的 reference_test 真的能过关。

任何一关没过，说明关卡设计有问题（bug 不成立、或参考测试本身是错的）。
发布前必须跑通这个脚本——否则你会发布出去一堆玩家永远过不了的关卡。

用法：
    python scripts/check_levels.py
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bug_hunter.judge import judge  # noqa: E402
from bug_hunter.level import load_all_levels  # noqa: E402

# 六类教学点的展示顺序（定义见 docs/关卡设计规范.md），汇总按这个顺序打印
_CATEGORY_ORDER = ["boundary", "exception", "isolation", "numeric", "contract", "sideeffect"]


def main() -> int:
    levels_dir = ROOT / "src" / "bug_hunter" / "levels"
    levels = load_all_levels(levels_dir)
    print(f"共 {len(levels)} 关\n")

    failed = 0
    category_count: dict[str, int] = {}
    for lv in levels:
        with tempfile.TemporaryDirectory() as tmp:
            test_file = Path(tmp) / "test_reference.py"
            test_file.write_text(lv.reference_test, encoding="utf-8")
            # judge 已是严格三参数签名；这里显式取 Level 的两段代码传入
            result = judge(lv.broken_code, lv.correct_code, test_file)

        # 分类代号约定写在 tags 第一位（见 docs/关卡设计规范.md）
        category = lv.tags[0] if lv.tags else "uncategorized"
        category_count[category] = category_count.get(category, 0) + 1
        print(f"[{category:<10}] {lv.id:<20} {lv.title:<8} -> {result.status.name}")

        if not result.passed:
            failed += 1
            print(f"        原因: {result.message}")
            if result.detail:
                first_lines = "\n".join(result.detail.strip().splitlines()[:6])
                print(f"        输出:\n{first_lines}\n")

    print()
    print(_summary(category_count))
    if failed:
        print(f"[FAIL] {failed} 个关卡不合格，修完再发布")
        return 1
    print("[OK] 所有关卡自检通过")
    return 0


def _summary(category_count: dict[str, int]) -> str:
    """按规范里六类的顺序汇总；不在六类里的代号排在最后，不被静默吞掉。"""
    known = [name for name in _CATEGORY_ORDER if name in category_count]
    extra = sorted(set(category_count) - set(_CATEGORY_ORDER))
    parts = [f"{name} {category_count[name]}" for name in known + extra]
    return "按分类汇总：" + " / ".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
