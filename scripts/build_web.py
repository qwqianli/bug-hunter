"""读 YAML 关卡，生成 web/levels.json，并把 judge_core.py 复制到 web/ 目录。

用法：python scripts/build_web.py（GitHub Pages 部署前由 CI 执行）
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bug_hunter.level import LEVELS_DIR, load_all_levels  # noqa: E402

WEB_DIR = ROOT / "web"


def main() -> int:
    levels = load_all_levels(LEVELS_DIR)
    yaml_count = len(list(LEVELS_DIR.glob("*.yaml")))
    # 数量对不上说明有 YAML 没被加载（比如 id 重复被拦下），先吵再走
    if len(levels) != yaml_count:
        print(f"[FAIL] 关卡数不一致：加载 {len(levels)} 个，目录里有 {yaml_count} 个 YAML")
        return 1

    payload = [
        {
            "id": lv.id,
            "title": lv.title,
            "difficulty": lv.difficulty,
            "tags": list(lv.tags),
            "intro": lv.intro,
            "broken_code": lv.broken_code,
            "correct_code": lv.correct_code,
            "hints": list(lv.hints),
            "reference_test": lv.reference_test,
        }
        for lv in levels
    ]
    WEB_DIR.mkdir(exist_ok=True)
    (WEB_DIR / "levels.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # 浏览器版要原样加载 judge_core：copy 而不是 import，保证线上文件和包内一致
    shutil.copy2(ROOT / "src" / "bug_hunter" / "judge_core.py", WEB_DIR / "judge_core.py")
    # 一致性 fixture 两侧共用：CLI 的参数化测试和页面的 ?selftest=1 读同一份
    shutil.copy2(ROOT / "tests" / "fixtures" / "judge_cases.json", WEB_DIR / "judge_cases.json")

    info = {"built_at": datetime.now().isoformat(timespec="seconds"), "commit": _git_short()}
    (WEB_DIR / "build-info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"levels: {len(levels)} -> web/levels.json")
    print(f"build-info: {info['built_at']} commit={info['commit']}")
    return 0


def _git_short() -> str:
    # CI 和本地都有 git；万一没有（比如源码包解压），页脚显示 unknown 而不是崩
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=ROOT,
        )
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
