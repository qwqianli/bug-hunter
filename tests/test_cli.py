"""CLI 的验收测试：直接调 main([...])，不起子进程跑命令行。

capsys 抓的是 CLI 自己打印的摘要；判题轮次里 pytest 子进程的原始输出
不会（也不该）出现在这里。

硬约束：所有测试都 monkeypatch.chdir 到 tmp_path、存档指到 tmp_path，
绝不在项目目录里留 _playground/，绝不碰真实的 ~/.bug-hunter/。
"""

from pathlib import Path

import pytest

from bug_hunter import cli, progress
from bug_hunter.judge import judge as real_judge

GOOD_TEST = (
    "from target import find_max\n"
    "def test_max_at_last():\n"
    "    assert find_max([1, 3, 5]) == 5\n"
)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """每个测试都在空目录、空存档下跑，结束后不留任何痕迹。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(progress, "PROGRESS_PATH", tmp_path / "progress.json")


@pytest.fixture
def fast_judge(monkeypatch):
    """把判题超时压到 3 秒：这里测的是 CLI 分支，不是等待。"""
    monkeypatch.setattr(
        cli, "judge",
        lambda broken, correct, path, timeout=10.0: real_judge(broken, correct, path, timeout=3),
    )


def run(capsys, argv):
    """跑一次 CLI，返回 (退出码, stdout)。"""
    code = cli.main(argv)
    return code, capsys.readouterr().out


def test_list_shows_total(capsys):
    code, out = run(capsys, ["list"])
    assert code == 0
    assert "共 15 关" in out


def test_list_groups_by_category(capsys):
    # 分组顺序固定，第一组一定是 boundary
    code, out = run(capsys, ["list"])
    assert code == 0
    assert "boundary 边界值" in out
    assert out.index("boundary") < out.index("exception") < out.index("sideeffect")


def test_no_subcommand_prints_help_with_exit_zero(capsys):
    # 不带子命令是想学用法，不是错误
    code, out = run(capsys, [])
    assert code == 0
    assert "usage" in out


def test_play_unknown_level(capsys):
    code, out = run(capsys, ["play", "999-nope"])
    assert code == 1
    assert "找不到" in out


def test_play_creates_target_in_playground(tmp_path, capsys):
    code, out = run(capsys, ["play", "001-off-by-one"])
    assert code == 0
    target = tmp_path / "_playground" / "target.py"
    assert target.is_file()
    assert "find_max" in target.read_text(encoding="utf-8")


def test_submit_missing_file(capsys):
    code, out = run(capsys, ["submit", "001-off-by-one", "nope.py"])
    assert code == 1
    assert "找不到这个测试文件" in out


def test_submit_rejects_non_py(tmp_path, capsys):
    (tmp_path / "note.txt").write_text("不是测试", encoding="utf-8")
    code, out = run(capsys, ["submit", "001-off-by-one", "note.txt"])
    assert code == 1
    assert ".py" in out


def test_submit_good_test_passes_and_records(tmp_path, capsys, fast_judge):
    (tmp_path / "test_ok.py").write_text(GOOD_TEST, encoding="utf-8")
    code, out = run(capsys, ["submit", "001-off-by-one", "test_ok.py"])
    assert code == 0
    assert "过关" in out
    # 过关要落进存档
    assert "001-off-by-one" in progress.load()["completed"]


def test_submit_false_positive(tmp_path, capsys, fast_judge):
    (tmp_path / "test_bad.py").write_text("def test_a():\n    assert False\n", encoding="utf-8")
    code, out = run(capsys, ["submit", "001-off-by-one", "test_bad.py"])
    assert code == 1
    assert "误报" in out


def test_submit_empty_file(tmp_path, capsys, fast_judge):
    (tmp_path / "test_empty.py").write_text("", encoding="utf-8")
    code, out = run(capsys, ["submit", "001-off-by-one", "test_empty.py"])
    assert code == 1
    assert "没有测试" in out


def test_hint_second_call_gives_second(capsys):
    run(capsys, ["hint", "001-off-by-one"])
    code, out = run(capsys, ["hint", "001-off-by-one"])
    assert code == 0
    assert "提示 2 /" in out


def test_hint_third_call_says_exhausted(capsys):
    run(capsys, ["hint", "001-off-by-one"])
    run(capsys, ["hint", "001-off-by-one"])
    code, out = run(capsys, ["hint", "001-off-by-one"])
    assert code == 0
    assert "都给你了" in out


def test_answer_shows_reference_and_marks_viewed(capsys):
    code, out = run(capsys, ["answer", "001-off-by-one"])
    assert code == 0
    assert "def test_" in out
    assert "看过答案" in out
    assert progress.get_state("001-off-by-one") == "answered"


def test_no_color_suppresses_ansi(monkeypatch, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    code, out = run(capsys, ["list"])
    assert code == 0
    assert "\x1b[" not in out
