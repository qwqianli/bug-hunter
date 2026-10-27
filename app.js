// 在线版前端逻辑：加载 Pyodide + 关卡数据，判题全部交给 Pyodide 里跑的
// judge_browser.run_tests() 和 judge_core.decide()，前端只做渲染。

// 与 judge.py 的 _MESSAGES 保持一致（JS 复用不了 Python 字符串，改文案要两边同步）
const MESSAGES = {
  PASS: "过关 ✓ 你的测试精准地抓住了这个问题，而且没有冤枉正确代码。",
  NO_FAILURE: "测试在有 bug 的版本上全部通过了，说明没走到出问题的路径。想想它哪里会出错。",
  FALSE_POSITIVE: "你的测试在正确版本上也失败了——它可能顺带检查了不该检查的东西。",
  NO_TESTS: "没有执行到任何测试用例。检查一下函数名是不是以 test_ 开头，文件是不是 test_*.py。",
  TEST_SYNTAX: "测试代码本身有错误（语法或 import 写错了），先把它修到能跑起来。",
  INTERNAL: "判题器自己出了问题。",
};

const CATEGORY_ORDER = ["boundary", "exception", "isolation", "numeric", "contract", "sideeffect"];
const CATEGORY_NAMES = {
  boundary: "边界值", exception: "异常流", isolation: "测试隔离",
  numeric: "数值精度", contract: "类型与契约", sideeffect: "副作用",
};

let pyodide = null;
let levels = [];
let current = null;
const progress = loadProgress();

// ---- 进度（localStorage；在线版没有 CLI 的 progress.json） --------------------

function emptyProgress() {
  return { completed: [], viewed_answer: [], hint_index: {} };
}

function loadProgress() {
  try {
    return JSON.parse(localStorage.getItem("bug-hunter-progress")) || emptyProgress();
  } catch {
    // 存档坏了当作没有进度，不能让游戏打不开
    return emptyProgress();
  }
}

function saveProgress() {
  try {
    localStorage.setItem("bug-hunter-progress", JSON.stringify(progress));
  } catch (e) {
    // 存储满了只能放弃持久化，游戏本身还能玩
    console.warn("进度保存失败（存储已满？）", e);
  }
}

// ---- 启动 --------------------------------------------------------------------

async function boot() {
  try {
    pyodide = await loadPyodide();
    const [coreSrc, browserSrc] = await Promise.all([
      fetchText("judge_core.py"),
      fetchText("judge_browser.py"),
    ]);
    await pyodide.runPythonAsync(coreSrc);
    await pyodide.runPythonAsync(browserSrc);
    const resp = await fetch("levels.json");
    if (!resp.ok) {
      throw new Error("levels.json 不存在——需要先运行 python scripts/build_web.py");
    }
    levels = await resp.json();
    document.getElementById("status").hidden = true;
    if (new URLSearchParams(location.search).get("selftest") === "1") {
      runSelftest();
    } else {
      showHome();
    }
  } catch (e) {
    showError("加载失败，请刷新重试。（" + e.message + "）");
  }
}

async function fetchText(name) {
  const resp = await fetch(name);
  if (!resp.ok) throw new Error(name + " 缺失（HTTP " + resp.status + "）");
  return resp.text();
}

function showError(text) {
  document.getElementById("status").hidden = true;
  const box = document.getElementById("error");
  box.hidden = false;
  box.textContent = text;
}

// ---- 判题（两轮 run_tests + decide，语义与 CLI 完全一致） ----------------------

async function judgeInBrowser(testCode, brokenCode, correctCode) {
  pyodide.globals.set("bh_test", testCode);
  pyodide.globals.set("bh_target", brokenCode);
  const first = await pyodide.runPythonAsync("run_tests(bh_test, bh_target)");
  let second = "";
  if (first === "has_failure") {
    pyodide.globals.set("bh_target", correctCode);
    second = await pyodide.runPythonAsync("run_tests(bh_test, bh_target)");
  }
  // 不传 JS null：Pyodide 0.28 里它会变成 JsNull 包装，is not None 判不出来。
  // 用空字符串表示「没有第二轮」，Python 侧按真值判断
  pyodide.globals.set("bh_first", first);
  pyodide.globals.set("bh_second", second);
  return await pyodide.runPythonAsync(
    "second = RoundOutcome(bh_second) if bh_second else None\n" +
    "passed, status = decide(RoundOutcome(bh_first), second)\n" +
    "status.name"
  );
}

// ---- 关卡列表 / 关卡页 --------------------------------------------------------

function showHome() {
  document.getElementById("level").hidden = true;
  document.getElementById("home").hidden = false;
  const done = levels.filter(l => progress.completed.includes(l.id)).length;
  document.getElementById("progress").textContent = `共 ${levels.length} 关 · 已完成 ${done} / ${levels.length}`;
  const pct = levels.length ? Math.round(done / levels.length * 100) : 0;
  document.getElementById("progress-fill").style.width = pct + "%";
  const groups = document.getElementById("groups");
  groups.textContent = "";
  for (const category of CATEGORY_ORDER) {
    const members = levels.filter(l => l.tags.length > 0 && l.tags[0] === category);
    if (members.length === 0) continue;
    const section = document.createElement("section");
    const h2 = document.createElement("h2");
    h2.textContent = `${category} ${CATEGORY_NAMES[category]}`;
    section.appendChild(h2);
    const ul = document.createElement("ul");
    ul.className = "level-list";
    for (const lv of members) {
      const state = progress.viewed_answer.includes(lv.id)
        ? "answered"
        : (progress.completed.includes(lv.id) ? "done" : "");

      const li = document.createElement("li");
      if (state) li.className = state;

      const a = document.createElement("a");
      a.href = "#" + lv.id;

      const idEl = document.createElement("span");
      idEl.className = "lv-id";
      idEl.textContent = lv.id;

      const titleEl = document.createElement("span");
      titleEl.className = "lv-title";
      titleEl.textContent = lv.title;

      const meta = document.createElement("span");
      meta.className = "lv-meta";

      const badge = document.createElement("span");
      badge.className = "badge diff-" + lv.difficulty;
      badge.textContent = "难度 " + lv.difficulty;
      meta.appendChild(badge);

      const stateEl = document.createElement("span");
      stateEl.className = "state";
      stateEl.textContent =
        state === "answered" ? "看过答案" : (state === "done" ? "✓ 已通关" : "未通关");
      meta.appendChild(stateEl);

      a.appendChild(idEl);
      a.appendChild(titleEl);
      a.appendChild(meta);
      a.addEventListener("click", () => showLevel(lv));

      li.appendChild(a);
      ul.appendChild(li);
    }
    section.appendChild(ul);
    groups.appendChild(section);
  }
}

function showLevel(lv) {
  current = lv;
  document.getElementById("home").hidden = true;
  document.getElementById("level").hidden = false;
  document.getElementById("lv-title").textContent = `${lv.title} · 难度 ${lv.difficulty}`;
  document.getElementById("lv-intro").textContent = lv.intro;
  document.getElementById("lv-code").textContent = lv.broken_code;
  document.getElementById("code").value = "";
  for (const id of ["result", "hintbox", "answerbox"]) {
    const box = document.getElementById(id);
    box.hidden = true;
    box.textContent = "";
  }
}

async function submit() {
  const code = document.getElementById("code").value;
  if (!code.trim()) {
    showResult("fail", "代码是空的，先写一个 test_ 开头的函数再提交。");
    return;
  }
  showResult("", "判题中……");
  const statusName = await judgeInBrowser(code, current.broken_code, current.correct_code);
  if (statusName === "PASS" && !progress.viewed_answer.includes(current.id)
      && !progress.completed.includes(current.id)) {
    // 看过答案的关不计入完成数（与 CLI 的诚实规则一致）
    progress.completed.push(current.id);
    saveProgress();
  }
  showResult(statusName === "PASS" ? "ok" : "fail", MESSAGES[statusName] || statusName);
}

function hint() {
  const box = document.getElementById("hintbox");
  box.hidden = false;
  const total = current.hints.length;
  const seen = Math.min(progress.hint_index[current.id] || 0, total);
  if (seen >= total) {
    box.textContent = `这关的 ${total} 条提示都给完了。还是卡着的话可以看参考答案——看过答案这关就不算自己解出来的了。`;
    return;
  }
  const index = seen + 1;
  progress.hint_index[current.id] = index;
  saveProgress();
  box.textContent = `提示 ${index} / ${total}：${current.hints[index - 1]}`;
}

function answer() {
  const box = document.getElementById("answerbox");
  box.hidden = false;
  if (!progress.viewed_answer.includes(current.id)) {
    progress.viewed_answer.push(current.id);
    const at = progress.completed.indexOf(current.id);
    if (at >= 0) progress.completed.splice(at, 1);
    saveProgress();
  }
  box.textContent = "参考答案（这关不计入完成数）：\n\n" + current.reference_test;
}

function showResult(kind, text) {
  const box = document.getElementById("result");
  box.hidden = false;
  box.className = "result " + kind;
  box.textContent = text;
}

// ---- 自检（?selftest=1）：与 CLI 用同一份 judge_cases.json ---------------------

async function runSelftest() {
  const out = document.getElementById("selftest");
  out.hidden = false;
  const pre = document.getElementById("selftest-out");
  try {
    const resp = await fetch("judge_cases.json");
    if (!resp.ok) throw new Error("judge_cases.json 缺失");
    const cases = await resp.json();
    const lv = levels.find(l => l.id === "001-off-by-one");
    if (!lv) throw new Error("缺少 001-off-by-one 关卡数据");
    const lines = [];
    let ok = 0;
    for (const c of cases) {
      const final = await judgeInBrowser(c.test_code, lv.broken_code, lv.correct_code);
      const pass = final === c.expect_final;
      if (pass) ok++;
      lines.push(`${pass ? "OK  " : "FAIL"} ${c.name}: got ${final}, want ${c.expect_final}`);
    }
    lines.push("");
    lines.push(ok === cases.length ? "SELFTEST OK" : "SELFTEST FAILED");
    pre.textContent = lines.join("\n");
  } catch (e) {
    pre.textContent = "SELFTEST FAILED\n" + e.message;
  }
}

// ---- 页脚与入口 ----------------------------------------------------------------

async function showBuildInfo() {
  try {
    const info = await (await fetch("build-info.json")).json();
    document.getElementById("buildinfo").textContent =
      `构建时间 ${info.built_at} · commit ${info.commit}`;
  } catch {
    document.getElementById("buildinfo").textContent = "构建信息缺失";
  }
}

document.getElementById("back").addEventListener("click", e => {
  e.preventDefault();
  showHome();
});
document.getElementById("submit").addEventListener("click", submit);
document.getElementById("hint").addEventListener("click", hint);
document.getElementById("answer").addEventListener("click", answer);

boot();
showBuildInfo();
