"""progress 存档的验收测试。

全部用 monkeypatch 把 PROGRESS_PATH 指到 tmp_path——
测试绝不允许碰真实的 ~/.bug-hunter/。
"""

import json

import pytest

from bug_hunter import progress

EMPTY = {"version": 1, "completed": [], "hint_index": {}, "viewed_answer": []}


@pytest.fixture
def store(tmp_path, monkeypatch):
    """把存档路径指到临时目录，返回这个路径。"""
    path = tmp_path / "progress.json"
    monkeypatch.setattr(progress, "PROGRESS_PATH", path)
    return path


def test_load_missing_file_returns_empty(store):
    assert progress.load() == EMPTY


def test_record_pass_roundtrip(store):
    progress.record_pass("001-off-by-one")
    assert progress.load()["completed"] == ["001-off-by-one"]


def test_record_pass_is_idempotent(store):
    progress.record_pass("001-off-by-one")
    progress.record_pass("001-off-by-one")
    assert progress.load()["completed"] == ["001-off-by-one"]


def test_record_hint_never_decreases(store):
    progress.record_hint("014-today", 2)
    progress.record_hint("014-today", 1)
    assert progress.load()["hint_index"]["014-today"] == 2


def test_record_answer_removes_completed(store):
    progress.record_pass("001-off-by-one")
    progress.record_answer("001-off-by-one")
    data = progress.load()
    assert data["completed"] == []
    assert data["viewed_answer"] == ["001-off-by-one"]


def test_record_pass_skips_viewed_level(store):
    # 诚实规则：看过答案的关，之后过关也不再计入完成数
    progress.record_answer("004-is-zero")
    progress.record_pass("004-is-zero")
    assert progress.load()["completed"] == []


def test_corrupted_file_returns_empty(store):
    store.write_text("这不是JSON", encoding="utf-8")
    assert progress.load() == EMPTY


def test_json_array_returns_empty(store):
    store.write_text("[]", encoding="utf-8")
    assert progress.load() == EMPTY


def test_unknown_version_returns_empty(store):
    store.write_text(json.dumps({"version": 2, "completed": ["x"]}), encoding="utf-8")
    assert progress.load() == EMPTY


def test_save_creates_missing_dir_and_writes_valid_json(tmp_path, monkeypatch):
    path = tmp_path / "deep" / "nested" / "progress.json"
    monkeypatch.setattr(progress, "PROGRESS_PATH", path)
    progress.save(EMPTY)
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8")) == EMPTY


def test_get_state_three_states(store):
    assert progress.get_state("001-off-by-one") == "new"
    progress.record_pass("001-off-by-one")
    assert progress.get_state("001-off-by-one") == "done"
    progress.record_answer("001-off-by-one")
    assert progress.get_state("001-off-by-one") == "answered"


def test_clamp_hint_index(store):
    # 存档说看过 5 条，但关卡现在只有 2 条：clamp 到 2
    progress.record_hint("014-today", 5)
    assert progress.clamp_hint_index("014-today", 2) == 2
    assert progress.clamp_hint_index("never-seen", 2) == 0
