"""进度存档：记玩家玩到哪了、看过几条提示、看过哪些答案。

存档是玩家的数据，不是代码的一部分——坏了要能当没有，
绝不能让游戏打不开。
"""

import json
import os
from pathlib import Path

PROGRESS_DIR = Path.home() / ".bug-hunter"
PROGRESS_PATH = PROGRESS_DIR / "progress.json"


def load() -> dict:
    """读存档。

    文件不存在、读不了、乱码、不是字典、version 不是 1——
    一律返回空进度。任何情况下都不抛异常。
    """
    try:
        raw = PROGRESS_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        # OSError：文件还不存在（第一次玩）；ValueError：编码不对或不是合法 JSON。
        # 捕获范围到此为止：别的异常说明程序本身有 bug，不该被吞掉
        return _empty_progress()
    if not isinstance(data, dict) or data.get("version") != 1:
        # 结构不对，或是不认识的格式版本：为以后的升级留后路
        return _empty_progress()
    progress = _empty_progress()
    # 逐字段过滤而不是整份接受：缺了某个字段的旧存档也不至于带崩程序
    if isinstance(data.get("completed"), list):
        progress["completed"] = data["completed"]
    if isinstance(data.get("hint_index"), dict):
        progress["hint_index"] = data["hint_index"]
    if isinstance(data.get("viewed_answer"), list):
        progress["viewed_answer"] = data["viewed_answer"]
    return progress


def save(progress: dict) -> None:
    """原子写入：先写 .tmp 再 os.replace。

    直接覆盖时如果断电，会留下半个 JSON，下次启动直接崩；
    os.replace 是原子的，最坏也只是丢这一版进度。
    """
    tmp_path = PROGRESS_PATH.parent / (PROGRESS_PATH.name + ".tmp")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    os.replace(tmp_path, PROGRESS_PATH)


def record_pass(level_id: str) -> None:
    """记为完成。幂等：同一关重复记录不出现两次。

    看过答案的关直接跳过——record_answer 的「诚实」设计要求这里
    配合，否则看答案后再过关又会被算回完成数。
    """
    progress = load()
    if level_id in progress["viewed_answer"]:
        return
    if level_id not in progress["completed"]:
        progress["completed"].append(level_id)
        save(progress)


def record_hint(level_id: str, index: int) -> None:
    """记录已看到第 index 条。只增不减：原值 2、传入 1，结果保持 2。"""
    progress = load()
    if index > progress["hint_index"].get(level_id, 0):
        progress["hint_index"][level_id] = index
        save(progress)


def record_answer(level_id: str) -> None:
    """记录看过答案，同时把该关从 completed 里移除。

    看过答案再照着写测试过关，不算自己解出来的。
    """
    progress = load()
    if level_id not in progress["viewed_answer"]:
        progress["viewed_answer"].append(level_id)
    if level_id in progress["completed"]:
        progress["completed"].remove(level_id)
    save(progress)


def get_state(level_id: str) -> str:
    """返回 'done' / 'answered' / 'new'，供 cli 渲染用。"""
    progress = load()
    if level_id in progress["viewed_answer"]:
        return "answered"
    if level_id in progress["completed"]:
        return "done"
    return "new"


def clamp_hint_index(level_id: str, total: int) -> int:
    """把「已看过几条提示」限制在 0..total。

    关卡以后可能删提示：存档说看过 3 条、现在只剩 2 条时，
    cmd_hint 必须拿到 2，否则永远进不了「都给完了」的分支。
    """
    seen = load()["hint_index"].get(level_id, 0)
    return max(0, min(seen, total))


def _empty_progress() -> dict:
    # 每次都造新的：空进度是可变 dict，共享同一份会被意外改坏
    return {"version": 1, "completed": [], "hint_index": {}, "viewed_answer": []}
