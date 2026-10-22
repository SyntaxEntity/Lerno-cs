#!/usr/bin/env node
/* 练习页行为测试（validate.py 的 F32）。
 *
 * 为什么要有
 * ----------
 * 练习闭环的状态机（判分、掌握度、错题连对、模拟交卷、持久化）全在
 * `assets/practice.js` 里。它不能只是"看起来对"：这里用 jsdom 起一个真实的
 * `练习.html`（连同 quiz-data.js / practice.css），把整条回环点一遍并逐条断言。
 *
 * 与 `test_site_js.mjs` 的分工
 * ---------------------------
 * 那个脚本测**共用件** site.js（两站逐字相同）；本脚本测**408 独有**的练习页，
 * 不进共用件清单，属于本项目自己的门禁。
 *
 * 用法
 * ----
 *   node scripts/test_quiz.mjs            # stdout 输出 JSON，stderr 输出人读摘要
 *   node scripts/test_quiz.mjs --strict   # 有失败时退出码 1
 *
 * 退出码
 * ------
 *   0  断言跑完（失败项写在 JSON 的 failed 里，由 validate.py 报错）
 *   1  --strict 且有失败
 *   2  环境缺少 jsdom（不是"跳过"：validate.py 会因此直接报错）
 *   3  内部错误（找不到 练习.html、静态服务器起不来等）
 */
import { readFileSync, existsSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import http from 'node:http';

const HERE = dirname(fileURLToPath(import.meta.url));       // scripts/
const ROOT = resolve(HERE, '..');                           // 仓库根
const TOOLS = join(ROOT, '.tools', 'node_modules');
const PAGE_FILE = join(ROOT, '练习.html');
const PRACTICE_JS = join(ROOT, 'assets', 'practice.js');
const PRACTICE_CSS = join(ROOT, 'assets', 'practice.css');

const INSTALL = 'mkdir -p .tools && cp scripts/tools-package.json .tools/package.json && '
  + 'npm install --prefix .tools --cache /tmp/npm-cache --no-audit --no-fund';

function fail(code, msg) {
  process.stdout.write(JSON.stringify({ total: 0, ok: 0, failed: [], error: msg }) + '\n');
  process.stderr.write('✗ ' + msg + '\n');
  process.exit(code);
}

if (!existsSync(PAGE_FILE)) fail(3, '找不到被测页面：练习.html（先跑 scripts/build_html.py）');
if (!existsSync(PRACTICE_JS)) fail(3, '找不到被测脚本：assets/practice.js');
if (!existsSync(join(TOOLS, 'jsdom'))) {
  fail(2, `未安装 jsdom（版本见 scripts/tools-package.json）。安装：\n  ${INSTALL}`);
}

const { JSDOM, VirtualConsole } = await import(join(TOOLS, 'jsdom', 'lib', 'api.js'));

// ---------------------------------------------------------------------------
// 静态断言：练习页与脚本的硬约束（离线、无内联、无六段锚点）
// ---------------------------------------------------------------------------
const results = [];
function record(name, ok, detail) {
  results.push({ name, ok, detail: ok ? '' : (detail || '') });
  if (!ok) process.stderr.write(`  ✗ ${name}${detail ? '：' + detail : ''}\n`);
}
function check(name, fn) {
  try {
    const r = fn();
    if (r === true) record(name, true);
    else record(name, false, String(r || '断言不成立'));
  } catch (e) {
    record(name, false, String((e && e.message) || e));
  }
}

const pageText = readFileSync(PAGE_FILE, 'utf8');
const jsText = readFileSync(PRACTICE_JS, 'utf8');

check('练习页没有内联 <style>', () => !/<style[\s>]/i.test(pageText));
check('练习页没有六段锚点（§2.3.1.A）', () => !/id="sec-(freq|core|key|fig|err|real)"/.test(pageText));
check('练习页不参与 prev/next 翻章', () => !/data-prev=|data-next=/.test(pageText));
check('练习页引用 practice.css / practice.js / quiz-data.js', () =>
  ['assets/practice.css', 'assets/practice.js', 'assets/quiz-data.js'].every((x) => pageText.includes(x)));
// 注意：判据只看**代码**，先剥注释——文件头注释里写着"不写 fetch / WebSocket"，
// 不剥注释会把"声明"当成"违规"（与 F24/F29 踩过的坑同一类）。
function stripJsComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}
check('practice.js 不含网络调用（离线承诺）', () => {
  const code = stripJsComments(jsText);
  const bad = [/\bfetch\s*\(/, /XMLHttpRequest/, /WebSocket/, /sendBeacon/, /https?:\/\//];
  const hit = bad.filter((re) => re.test(code));
  return hit.length ? '发现：' + hit.map(String).join('、') : true;
});
check('practice.css 存在且非空', () => existsSync(PRACTICE_CSS) && readFileSync(PRACTICE_CSS, 'utf8').length > 500);

// ---------------------------------------------------------------------------
// 起一个只读静态服务器：练习页需要 localStorage（http 源），file:// 会被 jsdom 拒绝
// ---------------------------------------------------------------------------
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml'
};
const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://127.0.0.1');
  const file = join(ROOT, decodeURIComponent(u.pathname));
  if (!file.startsWith(ROOT)) { res.writeHead(403); res.end('forbidden'); return; }
  try {
    const buf = readFileSync(file);
    res.writeHead(200, { 'Content-Type': MIME[file.slice(file.lastIndexOf('.'))] || 'application/octet-stream' });
    res.end(buf);
  } catch (e) {
    res.writeHead(404); res.end('not found');
  }
});
const port = await new Promise((res) => server.listen(0, '127.0.0.1', () => res(server.address().port)));
const BASE = `http://127.0.0.1:${port}/`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const consoleErrors = [];

async function boot(seed) {
  const vc = new VirtualConsole();
  vc.on('jsdomError', (e) => {
    const msg = String((e && e.message) || e);
    if (!/Not implemented/.test(msg)) consoleErrors.push(msg);
  });
  const dom = await JSDOM.fromURL(BASE + encodeURIComponent('练习.html'), {
    runScripts: 'dangerously',
    resources: 'usable',
    pretendToBeVisual: true,
    virtualConsole: vc,
    beforeParse(w) {
      w.matchMedia = () => ({
        matches: false, addEventListener() {}, removeEventListener() {},
        addListener() {}, removeListener() {}
      });
      w.scrollTo = () => {};
      w.confirm = () => true;
      w.Element.prototype.scrollIntoView = function () {};
      if (seed) {
        try { w.localStorage.setItem('lerno-quiz-v1', seed); } catch (e) { /* 由持久化断言暴露 */ }
      }
    }
  });
  const w = dom.window;
  await new Promise((r) => w.addEventListener('load', r, { once: true }));
  await sleep(120);
  return w;
}

const textOf = (w) => (w.document.getElementById('practice-view')?.textContent || '').replace(/\s+/g, ' ').trim();
const storeOf = (w) => JSON.parse(w.localStorage.getItem('lerno-quiz-v1') || '{}');
async function click(w, sel) {
  const el = w.document.querySelector(sel);
  if (!el) return false;
  el.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }));
  await sleep(30);
  return true;
}
async function go(w, hash) {
  w.location.hash = hash;
  await sleep(60);
}
function currentQuestion(w) {
  const stem = w.document.querySelector('.pv-stem');
  if (!stem) return null;
  const s = stem.textContent;
  return (w.LERNO_QUIZ.questions || []).find((q) => q.stem === s) || null;
}

// ---------------------------------------------------------------------------
// 场景一：主流程（练习 10 题 → 结果 → 错题本 → 报告 → 设置 → 模拟 → 持久化）
// ---------------------------------------------------------------------------
let w;
try {
  w = await boot(null);
} catch (e) {
  server.close();
  fail(3, '启动 jsdom 失败：' + String((e && e.message) || e));
}

// 不钉死条数：题库会增长（M5 补题），条数一致性由 F31 负责；这里只证明"加载到了"。
check('题库已加载（非空 / 4 科）', () => {
  const d = w.LERNO_QUIZ;
  return !!d && Array.isArray(d.questions) && d.questions.length > 0 && d.subjects.length === 4
    ? true : `questions=${d && d.questions && d.questions.length} subjects=${d && d.subjects && d.subjects.length}`;
});
check('练习页外壳齐全（顶栏/侧栏/页脚）', () =>
  !!w.document.querySelector('.site-topbar') && !!w.document.querySelector('.site-sidebar') &&
  !!w.document.querySelector('.site-footer'));
check('今日视图含「今日三件事」', () => textOf(w).includes('今日三件事'));

const routes = ['today', 'practice', 'quiz', 'result', 'wrong', 'mock', 'stats', 'settings'];
let routeOk = true;
for (const r of routes) {
  await go(w, '#/' + r);
  if (!textOf(w).length) { routeOk = false; record(`路由 #/${r} 渲染非空`, false, '视图为空'); }
}
check('8 个路由都能渲染非空', () => routeOk);

await go(w, '#/today');
check('侧栏高亮跟随视图', () => {
  const cur = w.document.querySelector('.site-sidebar .sb-chap.cur');
  return cur && cur.getAttribute('data-view') === 'today' ? true : '高亮不是 today';
});

await go(w, '#/practice');
const started = await click(w, '[data-action="start-practice"]');
record('开始练习进入答题（第 1/10 题）', started && /第 1 \/ 10 题/.test(textOf(w)),
  started ? '没有进入答题：' + textOf(w).slice(0, 60) : '找不到「开始练习」按钮');

let answeredCorrect = 0;
let answeredWrong = 0;
for (let i = 0; i < 10; i++) {
  const q = currentQuestion(w);
  if (!q) { record(`第 ${i + 1} 题可见`, false, '找不到当前题'); break; }
  const wantWrong = i < 2;                       // 前两题故意答错，制造错题本数据
  const idx = wantWrong ? (q.answer + 1) % q.options.length : q.answer;
  await click(w, `[data-action="pick"][data-index="${idx}"]`);
  if (wantWrong) answeredWrong++; else answeredCorrect++;
  if (!w.document.querySelector('.pv-explain')) {
    record(`第 ${i + 1} 题作答后显示解析`, false, '没有 .pv-explain');
    break;
  }
  await click(w, '[data-action="next"]');
}
record('10 题作答完成并显示解析', answeredCorrect + answeredWrong === 10,
  `完成 ${answeredCorrect + answeredWrong}/10`);
record('结果页出现且正确率为 80%', /练习结果/.test(textOf(w)) && /80%/.test(textOf(w)),
  '结果为：' + textOf(w).slice(0, 60));

await go(w, '#/wrong');
const wrongRows = w.document.querySelectorAll('[data-action="retry-wrong"]').length;
record('错题本收录 2 道答错的题', wrongRows === 2, `实际 ${wrongRows} 条`);

await go(w, '#/stats');
record('学习报告累计作答 = 10 题', /10 题\s*累计作答/.test(textOf(w)),
  '报告：' + textOf(w).slice(0, 80));

await go(w, '#/settings');
const goalEl = w.document.querySelector('[data-role="set-goal"]');
if (goalEl) goalEl.value = '30';
await click(w, '[data-action="save-settings"]');
record('设置保存生效（每日目标 30）', storeOf(w).profile && storeOf(w).profile.dailyGoal === 30,
  '存档：' + JSON.stringify(storeOf(w).profile || {}));

await go(w, '#/settings');
const dateEl = w.document.querySelector('[data-role="set-date"]');
if (dateEl) dateEl.value = '2026-13-99';
await click(w, '[data-action="save-settings"]');
record('非法考试日期被拒绝（不静默保存）', storeOf(w).profile.examDate === '2026-12-19',
  '存档日期：' + (storeOf(w).profile || {}).examDate);

await go(w, '#/mock');
await click(w, '[data-action="start-mock"]');
record('模拟考可开始（20 题）', /第 1 \/ 20 题/.test(textOf(w)), textOf(w).slice(0, 60));
for (let i = 0; i < 3; i++) {
  await click(w, '[data-action="pick"][data-index="1"]');
  await click(w, '[data-action="next"]');
}
await click(w, '[data-action="submit-mock"]');
record('模拟交卷出现结果页', /模拟结果/.test(textOf(w)), textOf(w).slice(0, 60));

const seed = w.localStorage.getItem('lerno-quiz-v1');
const saved = JSON.parse(seed || '{}');
record('存档：30 条作答 / 2 组会话', (saved.attempts || []).length === 30 && (saved.sessions || []).length === 2,
  `attempts=${(saved.attempts || []).length} sessions=${(saved.sessions || []).length}`);

const w2 = await boot(seed);
await go(w2, '#/stats');
record('重新打开后数据恢复（累计 30 题）', /30 题\s*累计作答/.test(textOf(w2)),
  '报告：' + textOf(w2).slice(0, 80));
w.close();
w2.close();

// ---------------------------------------------------------------------------
// 场景二：掌握度语义（累计 vs 连续）——用种子数据直接驱动
// ---------------------------------------------------------------------------
const now = new Date();
const today = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' +
  String(now.getDate()).padStart(2, '0');
const seed2 = JSON.stringify({
  v: 1,
  profile: { name: '测试', examDate: '2026-12-19', dailyGoal: 20 },
  points: { 'ds/01-线性表': { level: 1, correct: 2, wrong: 1, lastSeen: null, lastReviewed: null } },
  attempts: [],
  wrong: { 'ds-01': { count: 1, streak: 1, mastered: false, lastAt: null, lastSelected: 2 } },
  activity: { [today]: { answered: 0, reviews: 0, sessions: 0 } },
  sessions: []
});
const w3 = await boot(seed2);
await go(w3, '#/wrong');
await click(w3, '[data-action="retry-wrong"]');
const q3 = (w3.LERNO_QUIZ.questions || []).find((q) => q.id === 'ds-01');
await click(w3, `[data-action="pick"][data-index="${q3.answer}"]`);
const afterOne = JSON.parse(w3.localStorage.getItem('lerno-quiz-v1') || '{}');
record('错题连对 2 次 → 已掌握', afterOne.wrong['ds-01'] && afterOne.wrong['ds-01'].mastered === true,
  JSON.stringify(afterOne.wrong['ds-01'] || {}));
record('累计答对 3 次 → 复习中（level 2）', (afterOne.points['ds/01-线性表'] || {}).level === 2,
  'level=' + (afterOne.points['ds/01-线性表'] || {}).level);
await click(w3, '[data-action="next"]');
await go(w3, '#/wrong');
await click(w3, '[data-action="wrong-tab"][data-tab="mastered"]');
await click(w3, '[data-action="retry-wrong"]');
await click(w3, `[data-action="pick"][data-index="${q3.answer}"]`);
const afterTwo = JSON.parse(w3.localStorage.getItem('lerno-quiz-v1') || '{}');
record('累计答对 4 次 → 已掌握（level 3）', (afterTwo.points['ds/01-线性表'] || {}).level === 3,
  'level=' + (afterTwo.points['ds/01-线性表'] || {}).level);
w3.close();

record('运行期无控制台错误', consoleErrors.length === 0,
  consoleErrors.slice(0, 2).join(' | '));

// ---------------------------------------------------------------------------
// 汇总
// ---------------------------------------------------------------------------
server.close();
const failed = results.filter((r) => !r.ok);
process.stdout.write(JSON.stringify({
  total: results.length,
  ok: results.length - failed.length,
  failed: failed.map((r) => ({ name: r.name, error: r.detail }))
}) + '\n');
process.stderr.write(`练习闭环行为测试：${results.length - failed.length}/${results.length} 通过\n`);
for (const r of failed) process.stderr.write(`  ✗ ${r.name}：${r.detail}\n`);

if (process.argv.includes('--strict') && failed.length) process.exit(1);
process.exit(0);
