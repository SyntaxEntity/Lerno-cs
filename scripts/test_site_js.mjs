// 来源：Lerno-math/数学二/scripts/test_site_js.mjs（**逐字复制**，正文 sha256 a08d6d4df3cf4379）。
// 这是两个项目共用的外壳行为测试（PLAN-对齐与改版 §2.4.1-D），不要就地改；
// 要改先改契约再同步两边。默认被测文件已改为本仓库的 assets/site.js。
// 外壳脚本 `数学二/assets/site.js` 的**行为测试**（node + jsdom）。
//
// 为什么必须有
// ------------
// `assets/site.js` 是两个项目**共用同一份**的外壳脚本（PLAN-对齐与改版 §2.4），
// 408 直接复制本文件。所以它不能只是"看起来对"：主题类、筛选、键盘翻章这些
// 行为必须在真实 DOM 上跑一遍。这里用 jsdom 造一个符合契约的最小页面，
// 把 site.js 真跑起来逐条断言——**校验器不是摆设**这条规矩，对外置脚本同样适用。
//
// 用法
// ----
//   node 数学二/scripts/test_site_js.mjs          # stdout 输出 JSON，stderr 输出人读摘要
//   node 数学二/scripts/test_site_js.mjs --strict # 有失败时退出码 1
//   node 数学二/scripts/test_site_js.mjs --site-js <path>   # 换被测文件（408 复用本测试用）
//
// 依赖：jsdom（版本见 数学二/scripts/tools-package.json，与 F3 用的是同一份）
//
// 退出码
// ------
//   0  断言跑完（失败项写在 JSON 的 failed 里，由 validate.py 报错）
//   1  --strict 且有失败
//   2  环境缺少 jsdom（不是"跳过"：validate.py 会因此直接报错）
//   3  内部错误
import { readFileSync, existsSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));       // scripts/
const ROOT = resolve(HERE, '..');                           // 仓库根
const argv = process.argv.slice(2);
const ji = argv.indexOf('--site-js');
const SITE_JS = ji >= 0 && argv[ji + 1]
  ? resolve(argv[ji + 1])
  : join(ROOT, 'assets', 'site.js');              // 408 复用时可传自己的路径
const TOOLS = join(ROOT, '.tools', 'node_modules');

const INSTALL = 'mkdir -p .tools && cp 数学二/scripts/tools-package.json .tools/package.json && '
  + 'npm install --prefix .tools --cache /tmp/npm-cache --no-audit --no-fund';

function fail(code, msg) {
  process.stdout.write(JSON.stringify({ total: 0, ok: 0, failed: [], error: msg }) + '\n');
  process.stderr.write('✗ ' + msg + '\n');
  process.exit(code);
}

if (!existsSync(SITE_JS)) fail(3, `找不到被测文件：${SITE_JS}`);
if (!existsSync(join(TOOLS, 'jsdom'))) {
  fail(2, `未安装 jsdom（版本见 数学二/scripts/tools-package.json）。安装：\n  ${INSTALL}`);
}

const { JSDOM, VirtualConsole } = await import(join(TOOLS, 'jsdom', 'lib', 'api.js'));
const SRC = readFileSync(SITE_JS, 'utf8');

// 符合契约的最小页面：顶栏 + 侧栏（两组）+ 正文 + 页脚 + 翻章数据
const PAGE = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"></head><body
  data-prev="../高等数学/01-函数极限与连续.html" data-next="../线性代数/01-行列式.html">
  <header class="site-topbar">
    <a class="tb-brand" href="../index.html">高等数学</a>
    <nav class="tb-crumbs"><a href="../index.html">首页</a><span class="tb-sep">›</span>
      <a href="./index.html">高等数学</a><span class="tb-sep">›</span>
      <span aria-current="page">导数与微分</span></nav>
    <button class="tb-search" type="button">搜索</button>
  </header>
  <button class="nav-toggle" type="button">☰ 目录</button>
  <div class="read-progress"></div>
  <div class="site-body">
    <nav class="site-sidebar">
      <input class="sb-filter" placeholder="筛选章节">
      <div class="sb-group"><div class="sb-group-t">高等数学</div>
        <a class="sb-chap" href="01-函数极限与连续.html">函数极限与连续</a>
        <a class="sb-chap" href="02-导数与微分.html">导数与微分</a></div>
      <div class="sb-group"><div class="sb-group-t">线性代数</div>
        <a class="sb-chap" href="../线性代数/01-行列式.html">行列式</a></div>
      <div class="tocbox">
        <a class="toclink" href="#sec-core">核心讲解</a>
        <a class="toclink" href="#sec-err">易错点</a></div>
    </nav>
    <main>
      <h1>导数与微分</h1>
      <section class="sec sec-core" id="sec-core"><div class="box">$f'(x)=2x$</div></section>
      <section class="sec sec-err" id="sec-err"><div class="box">易错点</div></section>
      <div class="mermaid">flowchart TD
  A["起点"] --&gt; B["终点"]</div>
      <nav class="chapter-nav">
        <a class="cn-prev" href="../高等数学/01-函数极限与连续.html">← 上一章</a>
        <a class="cn-next" href="../线性代数/01-行列式.html">下一章 →</a></nav>
    </main>
  </div>
  <footer class="site-footer">数据口径 · 返回顶部</footer>
  <button class="to-top" type="button">↑ 顶部</button>
  <button class="theme-toggle" type="button">◐ 主题</button>
</body></html>`;

const results = [];
async function check(name, fn) {
  try {
    const detail = await fn();
    results.push({ name, ok: true, detail: detail || '' });
  } catch (e) {
    results.push({ name, ok: false, detail: String((e && e.message) || e) });
  }
}
function assert(cond, msg) { if (!cond) throw new Error(msg); }

/** 造一个页面、设好前置条件、把 site.js 真跑起来，返回窗口。
 *
 * 注意要**等 DOMContentLoaded 真的跑完**再断言：site.js 的同步段（主题）在 eval 时
 * 就生效，但其余行为挂在 DOMContentLoaded 上，而 jsdom 在构造完成后才异步触发它。
 * 早期版本 assess 时立刻断言，于是 8 条用例齐刷刷失败——那是测试写错，不是脚本坏了。
 */
async function boot({ stored = null, systemDark = null, navigations = [] } = {}) {
  const vc = new VirtualConsole();
  vc.on('jsdomError', (e) => {
    if (/Not implemented: navigation/.test(String(e && e.message))) navigations.push('(navigation)');
  });
  const dom = new JSDOM(PAGE, { url: 'https://example.com/高等数学/02-导数与微分.html',
                                runScripts: 'dangerously', pretendToBeVisual: true,
                                virtualConsole: vc });
  const win = dom.window;
  if (stored) win.localStorage.setItem('kaoyan-theme', stored);
  if (systemDark !== null) {
    win.matchMedia = () => ({ matches: systemDark, addEventListener() {}, removeEventListener() {} });
  }
  win.scrollTo = (...a) => { win.__scrolled = a; };
  await new Promise((res) => {
    if (win.document.readyState !== 'loading') return res();
    win.document.addEventListener('DOMContentLoaded', () => res());
  });
  win.eval(SRC);                       // 在页面上下文里执行 site.js
  await new Promise((res) => win.setTimeout(res, 0));   // 让已注册的处理器有时间跑
  return win;
}

// 1) 没有存过偏好 + 系统浅色 → 不加 dark
await check('未存偏好且系统为浅色时，html 无 dark 类', async () => {
  const w = await boot({ systemDark: false });
  assert(!w.document.documentElement.classList.contains('dark'), '意外出现了 dark 类');
});

// 2) 没存过偏好 + 系统深色 → 跟随系统
await check('未存偏好但系统为深色时，跟随系统加 dark 类', async () => {
  const w = await boot({ systemDark: true });
  assert(w.document.documentElement.classList.contains('dark'), '没有跟随系统加 dark 类');
});

// 3) 存过 dark → 首屏即 dark（类在 DOMContentLoaded 之前就加好）
await check('存过 dark 偏好时，直接进深色', async () => {
  const w = await boot({ stored: 'dark', systemDark: false });
  assert(w.document.documentElement.classList.contains('dark'), '没有应用已存偏好');
});

// 4) 点击切换按钮 → 翻转类 + 写入 localStorage
await check('点 .theme-toggle 会翻转主题并记住', async () => {
  const w = await boot({ systemDark: false });
  w.document.querySelector('.theme-toggle').dispatchEvent(new w.Event('click', { bubbles: true }));
  assert(w.document.documentElement.classList.contains('dark'), '点击后没有变深色');
  assert(w.localStorage.getItem('kaoyan-theme') === 'dark', '没有写入 localStorage');
  w.document.querySelector('.theme-toggle').dispatchEvent(new w.Event('click', { bubbles: true }));
  assert(!w.document.documentElement.classList.contains('dark'), '再点没有变回浅色');
  assert(w.localStorage.getItem('kaoyan-theme') === 'light', '第二次没有写入');
});

// 5) 抽屉开关
await check('点 .nav-toggle 会给 body 加/去 navopen', async () => {
  const w = await boot({});
  const b = w.document.querySelector('.nav-toggle');
  b.dispatchEvent(new w.Event('click', { bubbles: true }));
  assert(w.document.body.classList.contains('navopen'), '没有加 navopen');
  b.dispatchEvent(new w.Event('click', { bubbles: true }));
  assert(!w.document.body.classList.contains('navopen'), '没有去掉 navopen');
});

// 6) 侧栏筛选：命中保留，整组落空则连组一起收起
await check('侧栏筛选按关键词过滤 .sb-chap，并收起空组', async () => {
  const w = await boot({});
  const f = w.document.querySelector('.sb-filter');
  f.value = '行列式';
  f.dispatchEvent(new w.Event('input', { bubbles: true }));
  const chaps = [...w.document.querySelectorAll('.sb-chap')];
  const shown = chaps.filter((a) => a.style.display !== 'none');
  assert(shown.length === 1 && shown[0].textContent.includes('行列式'),
    `应只剩 1 条命中，实为 ${shown.length}`);
  const groups = [...w.document.querySelectorAll('.sb-group')];
  assert(groups[0].style.display === 'none', '整组落空时没有收起组标题');
  assert(groups[1].style.display !== 'none', '命中的组被误收起');
});

// 7) 顶栏搜索按钮不是死按钮：聚焦侧栏筛选框
await check('点 .tb-search 会聚焦侧栏筛选框', async () => {
  const w = await boot({});
  w.document.querySelector('.tb-search').dispatchEvent(new w.Event('click', { bubbles: true }));
  assert(w.document.activeElement === w.document.querySelector('.sb-filter'),
    '焦点不在 .sb-filter 上');
});

// 8) 键盘翻章：→/j 与 ←/k 触发导航（jsdom 不支持真跳转，这里只确认真的发起了）
await check('键盘 j / k 触发翻章导航', async () => {
  const navs = [];
  const w = await boot({ navigations: navs });
  const press = (key) => w.document.dispatchEvent(
    new w.KeyboardEvent('keydown', { key, bubbles: true }));
  press('j');
  press('k');
  await new Promise((res) => w.setTimeout(res, 0));
  assert(navs.length >= 2, `应至少发起 2 次导航，实为 ${navs.length}`);
});

// 9) 输入框里按键不触发翻章（否则在筛选框里打字就跳页）
await check('在输入框内按键不触发翻章', async () => {
  const navs = [];
  const w = await boot({ navigations: navs });
  const f = w.document.querySelector('.sb-filter');
  f.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'j', bubbles: true }));
  await new Promise((res) => w.setTimeout(res, 0));
  assert(navs.length === 0, `输入框内不应触发导航，实测 ${navs.length} 次`);
});

// 10) 回到顶部：调用 scrollTo
await check('点 .to-top 会滚到顶部', async () => {
  const w = await boot({});
  w.document.querySelector('.to-top').dispatchEvent(new w.Event('click', { bubbles: true }));
  assert(Array.isArray(w.__scrolled), '没有调用 window.scrollTo');
});

// 11) KaTeX 缺失时给出明确提示（不许静默留白）
await check('缺 KaTeX 时插入 .missing 提示', async () => {
  const w = await boot({});
  const miss = [...w.document.querySelectorAll('main .missing')];
  assert(miss.some((p) => p.textContent.includes('公式渲染器')),
    '页面有 $…$ 但缺少公式渲染器时没有提示');
});

// 12) mermaid 缺失时回退为源码 + 提示（不许静默留白）
await check('缺 mermaid 时回退为源码并提示', async () => {
  const w = await boot({});
  const box = w.document.querySelector('.mermaid');
  assert(box.querySelector('pre code'), '没有把图回退成源码块');
  assert(w.document.querySelector('.missing'), '没有给出提示');
});

const failed = results.filter((r) => !r.ok);
process.stdout.write(JSON.stringify({ total: results.length, ok: results.length - failed.length,
                                      failed: failed.map((r) => ({ name: r.name, error: r.detail })) }) + '\n');
process.stderr.write(`site.js 行为测试：${results.length - failed.length}/${results.length} 通过\n`);
for (const r of failed) process.stderr.write(`  ✗ ${r.name}：${r.detail}\n`);

if (process.argv.includes('--strict') && failed.length) process.exit(1);
process.exit(0);
