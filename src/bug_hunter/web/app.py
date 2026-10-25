"""本地 Web 界面。

判题复用 CLI 的 judge()，这里只做 HTTP 壳：收代码、落临时文件、
把结果转成 JSON。判定逻辑绝不重写第二份。
"""

import tempfile
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

from bug_hunter import progress
# 分类顺序与中文名以 CLI 为单一来源，两个界面不许各排各的
from bug_hunter.cli import _CATEGORY_NAMES, _CATEGORY_ORDER
from bug_hunter.judge import judge
from bug_hunter.level import LEVELS_DIR, get_level, load_all_levels

app = Flask(__name__)


@app.route("/")
def index():
    levels = load_all_levels(LEVELS_DIR)
    progress_data = progress.load()
    known = {lv.id for lv in levels}
    # 存档里可能留着已下架的关卡 id，统计完成数时忽略它们
    done = len([i for i in progress_data["completed"] if i in known])
    groups = []
    for category in _CATEGORY_ORDER:
        members = [lv for lv in levels if lv.tags and lv.tags[0] == category]
        if not members:
            continue
        groups.append({
            "category": category,
            "name": _CATEGORY_NAMES[category],
            "levels": [
                {"id": lv.id, "title": lv.title, "difficulty": lv.difficulty,
                 "state": progress.get_state(lv.id)}
                for lv in members
            ],
        })
    return render_template("index.html", total=len(levels), done=done, groups=groups)


@app.route("/level/<level_id>")
def level_page(level_id):
    lv = get_level(level_id)
    if lv is None:
        abort(404)
    return render_template("level.html", level=lv)


@app.route("/api/submit", methods=["POST"])
def api_submit():
    data = request.get_json(silent=True) or {}
    level_id = data.get("level_id", "")
    code = data.get("code", "")
    lv = get_level(level_id)
    if lv is None:
        return jsonify({"error": f"找不到这个关卡：{level_id}"}), 404
    if not code.strip():
        # 空代码多半是误点提交：给提示，而不是判成「没写测试」吓玩家一跳
        return jsonify({"error": "代码是空的，先写一个 test_ 开头的函数再提交。"}), 400
    with tempfile.TemporaryDirectory(prefix="bug-hunter-web-") as tmp:
        test_path = Path(tmp) / "test_player.py"
        test_path.write_text(code, encoding="utf-8")
        result = judge(lv.broken_code, lv.correct_code, test_path)
    if result.passed:
        progress.record_pass(level_id)
    return jsonify({
        "passed": result.passed,
        "status": result.status.name,
        "message": result.message,
        "detail": result.detail,
    })


@app.route("/api/hint", methods=["POST"])
def api_hint():
    data = request.get_json(silent=True) or {}
    lv = get_level(data.get("level_id", ""))
    if lv is None:
        return jsonify({"error": "找不到这个关卡。"}), 404
    total = len(lv.hints)
    seen = progress.clamp_hint_index(lv.id, total)
    if seen >= total:
        return jsonify({"exhausted": True, "total": total})
    index = seen + 1
    progress.record_hint(lv.id, index)
    return jsonify({"index": index, "total": total, "hint": lv.hints[index - 1]})


@app.route("/api/answer", methods=["POST"])
def api_answer():
    data = request.get_json(silent=True) or {}
    lv = get_level(data.get("level_id", ""))
    if lv is None:
        return jsonify({"error": "找不到这个关卡。"}), 404
    # 先记再看：玩家看完就关页面，这次「看过」也不丢
    progress.record_answer(lv.id)
    return jsonify({"reference_test": lv.reference_test})


def run_web(port: int, open_browser: bool) -> int:
    """启动本地服务。只绑 127.0.0.1：判题会执行玩家代码，绝不能暴露给局域网。"""
    import socket
    import webbrowser

    # 先试探性 bind 一次：端口被占用时给一句话提示，比让 Flask 抛 traceback 友好
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", port))
    except OSError:
        print(f"端口 {port} 已被占用。换一个试试：bug-hunter web --port 9000")
        return 1
    finally:
        probe.close()

    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}/")
    print(f"Bug 猎人已启动：http://127.0.0.1:{port}/  （按 Ctrl+C 退出）")
    app.run(host="127.0.0.1", port=port)
    return 0
