#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 408/ 下的 Markdown 渲染成「为阅读而设计」的 HTML。

与普通 Markdown→HTML 的区别（这就是本文件存在的理由）：
  1. 不做「Markdown 原样搬进网页」，而是把模板结构**重组成语义化组件**：
     考频统计 → 信息条；结论速记 → 公式卡；易错点 → 卡片；真题解析 → 引用块。
  2. 公式与代码分开排版（行内 chip / 行间块），不再一律塞进 <code>。
  3. ASCII 示意图用深色面板 + 复制按钮；Mermaid 用本地运行时渲染（离线可用）。
  4. 侧栏是可折叠三级目录树 + 筛选；正文有阅读进度条、主题切换、回到顶部。

产出：
  408/<科目>/<章节>.html      每章一页
  408/<科目>/index.html       科目首页
  408/index.html              全科单页合集（四科全部内容）
  408/README.html             总览
  408/mermaid.min.js          本地 mermaid 运行时

用法： python3 scripts/build_html.py
"""
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import topics as T  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, ".docs")     # Markdown 归档（输入）
SITE = ROOT                            # HTML 站点（输出，仓库根即可被静态托管）

try:
    import markdown
except ImportError:
    sys.exit("需要 python-markdown：pip install markdown")

# ---------------------------------------------------------------------------
# 样式系统
# ---------------------------------------------------------------------------
CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --bg:#f7f7f5; --panel:#ffffff; --fg:#1a1d21; --fg2:#4a5058; --mut:#767e88;
  --line:#e3e6ea; --line2:#eef0f3; --acc:#1f6feb; --acc-soft:#e8f0fe;
  --warn:#fff5d6; --warn-line:#e6c34a; --ok:#1a7f37;
  --code-bg:#f4f6f8; --dark:#11151a; --dark-fg:#dfe6ee;
  --radius:10px; --mw:780px;
}
html[data-theme="dark"]{
  --bg:#0e1116; --panel:#151a21; --fg:#e7edf3; --fg2:#b8c2cc; --mut:#8b949e;
  --line:#252c35; --line2:#1c232b; --acc:#6cb0ff; --acc-soft:#16233a;
  --warn:#2c2712; --warn-line:#7a6a1f; --ok:#4ac26b;
  --code-bg:#171d24; --dark:#0b0f14; --dark-fg:#dfe6ee;
}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;background:var(--bg);color:var(--fg);
  font:16.5px/1.9 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
       "Hiragino Sans GB","Microsoft YaHei",sans-serif;
  text-rendering:optimizeLegibility;
}
/* ---------- 布局 ---------- */
#wrap{display:flex;align-items:flex-start;min-height:100vh}
nav{
  width:306px;flex:0 0 306px;height:100vh;position:sticky;top:0;overflow-y:auto;
  background:var(--panel);border-right:1px solid var(--line);padding:20px 14px 70px;
}
nav::-webkit-scrollbar{width:9px}
nav::-webkit-scrollbar-thumb{background:var(--line);border-radius:9px}
nav .brand{font-size:15px;font-weight:700;margin:0 6px 4px;letter-spacing:.2px}
nav .brand small{display:block;font-weight:400;color:var(--mut);font-size:12px;margin-top:3px}
#q{
  width:100%;margin:12px 0 8px;padding:8px 11px;border:1px solid var(--line);
  border-radius:8px;background:var(--bg);color:var(--fg);font-size:13.5px;
}
#q:focus{outline:2px solid var(--acc-soft);border-color:var(--acc)}
nav .home{
  display:block;margin:4px 0 12px;padding:7px 11px;font-size:13.5px;font-weight:600;
  color:var(--acc);text-decoration:none;background:var(--acc-soft);border-radius:8px;
}
nav .home:hover{filter:brightness(.97)}
details.grp{margin:2px 0}
details.grp>summary{
  cursor:pointer;list-style:none;padding:8px 10px;font-size:13.5px;font-weight:650;
  border-radius:8px;display:flex;justify-content:space-between;align-items:center;gap:8px;
}
details.grp>summary::-webkit-details-marker{display:none}
details.grp>summary:hover{background:var(--line2)}
details.grp>summary .n{color:var(--mut);font-weight:400;font-size:11.5px;white-space:nowrap}
details.grp[open]>summary{color:var(--acc)}
nav a.item{
  display:block;padding:6px 10px 6px 20px;font-size:13.5px;color:var(--fg2);
  text-decoration:none;border-radius:7px;border-left:2px solid transparent;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
nav a.item:hover{background:var(--line2);color:var(--fg)}
nav a.item.cur{background:var(--acc-soft);color:var(--acc);border-left-color:var(--acc);font-weight:600}
main{flex:1;min-width:0;max-width:calc(var(--mw) + 120px);margin:0 auto;padding:38px 60px 150px}
/* ---------- 进度条 ---------- */
#bar{position:fixed;top:0;left:0;height:3px;width:0;background:var(--acc);z-index:50}
/* ---------- 标题 ---------- */
h1{font-size:29px;line-height:1.35;margin:0 0 26px;letter-spacing:-.2px}
h2{
  font-size:23px;line-height:1.4;margin:52px 0 20px;padding-bottom:10px;
  border-bottom:2px solid var(--line);letter-spacing:-.2px;scroll-margin-top:16px;
}
h3{font-size:18px;margin:28px 0 12px}
p{margin:0 0 14px}
/* ---------- 知识点卡片 ---------- */
.kp{
  background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:26px 30px 30px;margin:0 0 28px;box-shadow:0 1px 2px rgba(16,22,26,.04);
}
.kp>h2{margin-top:0;border-bottom:none;padding-bottom:0}
/* ---------- 字段 ---------- */
.fld{margin:24px 0 0}
.lab{
  display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:700;
  letter-spacing:.6px;color:var(--mut);margin:0 0 10px;
}
.lab::before{content:"";width:4px;height:14px;border-radius:2px;background:var(--acc)}
.freq{
  background:var(--warn);border:1px solid var(--warn-line);border-left:4px solid var(--warn-line);
  border-radius:8px;padding:12px 16px;font-size:14.5px;margin:0;
}
.freq b{color:var(--fg)}
html[data-theme="dark"] .freq{color:#f2e8cc}
/* 结论速记 → 公式卡 */
ul.facts{list-style:none;margin:0;padding:0;display:grid;gap:10px}
ul.facts li{
  background:var(--code-bg);border-left:3px solid var(--acc);border-radius:0 8px 8px 0;
  padding:11px 15px;font-size:15px;margin:0;
}
ul.facts li code{background:none;padding:0;color:var(--acc);font-weight:600;font-size:14.5px}
/* 易错点 → 卡片 */
ul.errs{list-style:none;margin:0;padding:0;display:grid;gap:10px}
ul.errs li{
  position:relative;background:var(--panel);border:1px solid var(--line);
  border-radius:8px;padding:12px 15px 12px 46px;font-size:15px;margin:0;
}
ul.errs li::before{
  content:"易错";position:absolute;left:12px;top:12px;font-size:10.5px;font-weight:800;
  color:#b42318;background:#fee4e2;border-radius:5px;padding:2px 5px;letter-spacing:.5px;
}
html[data-theme="dark"] ul.errs li::before{color:#ffb4ab;background:#3d1a17}
/* 解析 */
blockquote{
  margin:14px 0 0;padding:14px 18px;background:var(--code-bg);
  border-left:4px solid var(--ok);border-radius:0 8px 8px 0;font-size:15px;color:var(--fg2);
}
blockquote p:last-child{margin-bottom:0}
blockquote strong{color:var(--fg)}
/* 真题题干 */
.q-stem{
  background:var(--acc-soft);border-radius:8px;padding:14px 18px;font-size:15.5px;
}
.q-src{display:block;font-weight:700;color:var(--acc);font-size:13.5px;margin-bottom:7px}
/* ---------- 代码 ---------- */
code{
  background:var(--code-bg);padding:.14em .4em;border-radius:5px;
  font:14px/1.55 ui-monospace,SFMono-Regular,"SF Mono",Consolas,"Liberation Mono",monospace;
  word-break:break-word;
}
.codebox{margin:14px 0}
.codebox .bar{
  display:flex;justify-content:space-between;align-items:center;gap:8px;
  font-size:11.5px;color:var(--mut);padding:0 2px 5px;letter-spacing:.4px;
}
.codebox button{
  border:1px solid var(--line);background:var(--panel);color:var(--fg2);cursor:pointer;
  border-radius:6px;padding:2px 9px;font-size:11.5px;
}
.codebox button:hover{border-color:var(--acc);color:var(--acc)}
pre{
  background:var(--code-bg);border:1px solid var(--line);border-radius:8px;
  padding:14px 16px;overflow:auto;margin:0;
}
pre code{background:none;padding:0;font-size:13px;line-height:1.5}
/* ASCII 示意图：深色面板，保证等宽对齐可读 */
.codebox.ascii .bar{color:var(--fg2);font-weight:600}
.codebox.ascii pre{
  background:var(--dark);border-color:#000;color:var(--dark-fg);
  font-size:12.5px;line-height:1.45;padding:18px;
}
.codebox.ascii pre code{color:var(--dark-fg)}
/* Mermaid */
.fig{margin:16px 0}
.mermaid{
  background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:16px;overflow:auto;text-align:center;min-height:44px;
}
.mermaid svg{max-width:100%;height:auto}
.fig details{margin-top:8px}
.fig summary{cursor:pointer;font-size:12.5px;color:var(--mut);padding:4px 0;user-select:none}
.fig summary:hover{color:var(--acc)}
/* ---------- 表格 ---------- */
.tw{overflow-x:auto;margin:16px 0;border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:14.5px;background:var(--panel)}
th,td{border-bottom:1px solid var(--line2);padding:9px 13px;text-align:left;vertical-align:top}
th{background:var(--code-bg);font-weight:650;font-size:13.5px;white-space:nowrap}
tr:last-child td{border-bottom:none}
tbody tr:hover{background:var(--line2)}
/* ---------- 杂项 ---------- */
.warn{
  background:var(--warn);border:1px solid var(--warn-line);border-radius:8px;
  padding:11px 15px;font-size:14px;margin:14px 0;
}
.tag{font-size:11.5px;padding:2px 9px;border-radius:20px;background:var(--code-bg);color:var(--mut)}
.totop{
  position:fixed;right:26px;bottom:26px;width:42px;height:42px;border-radius:50%;
  border:1px solid var(--line);background:var(--panel);color:var(--fg2);cursor:pointer;
  font-size:17px;box-shadow:0 2px 10px rgba(16,22,26,.1);opacity:0;pointer-events:none;
  transition:opacity .2s;z-index:40;
}
.totop.on{opacity:1;pointer-events:auto}
.totop:hover,#theme:hover{border-color:var(--acc);color:var(--acc)}
#theme{
  position:fixed;right:26px;bottom:78px;width:42px;height:42px;border-radius:50%;
  border:1px solid var(--line);background:var(--panel);color:var(--fg2);cursor:pointer;
  font-size:16px;box-shadow:0 2px 10px rgba(16,22,26,.1);z-index:40;
}
#menu{
  display:none;position:fixed;left:14px;top:14px;z-index:70;width:40px;height:40px;
  border-radius:9px;border:1px solid var(--line);background:var(--panel);color:var(--fg);
  cursor:pointer;align-items:center;justify-content:center;font-size:17px;
}
hr{border:none;border-top:1px solid var(--line);margin:32px 0}
/* ---------- 窄屏 ---------- */
@media (max-width:1000px){
  nav{position:fixed;z-index:60;transform:translateX(-100%);transition:transform .22s;
      box-shadow:4px 0 22px rgba(0,0,0,.12)}
  nav.open{transform:none}
  main{padding:22px 18px 130px;max-width:none}
  #menu{display:flex}
  .kp{padding:20px 18px 24px}
}
/* ---------- 打印 ---------- */
@media print{
  nav,#bar,.totop,#theme,#menu,.codebox .bar,.fig details{display:none!important}
  body{background:#fff;font-size:11pt}
  main{max-width:none;padding:0}
  .kp{border:none;padding:0;margin:0 0 16pt;box-shadow:none}
  h2{break-after:avoid}
  .codebox.ascii pre{background:#f5f5f5;color:#111;border-color:#ccc}
  .mermaid{border-color:#ccc}
  a{color:#000;text-decoration:none}
}
"""

JS = """
// 侧栏筛选
var q = document.getElementById('q');
if (q) q.addEventListener('input', function () {
  var v = this.value.trim().toLowerCase();
  document.querySelectorAll('nav details.grp').forEach(function (d) {
    var any = false;
    d.querySelectorAll('a.item').forEach(function (a) {
      var hit = !v || a.textContent.toLowerCase().indexOf(v) >= 0;
      a.style.display = hit ? '' : 'none';
      if (hit) any = true;
    });
    d.style.display = (any || !v) ? '' : 'none';
    if (v && any) d.open = true;
  });
});
// 进度条 + 回到顶部
var bar = document.getElementById('bar'), top = document.querySelector('.totop');
function onScroll() {
  var h = document.documentElement, y = h.scrollTop || document.body.scrollTop || 0;
  var max = h.scrollHeight - h.clientHeight;
  if (bar) bar.style.width = (max > 0 ? (y / max) * 100 : 0) + '%';
  if (top) top.classList.toggle('on', y > 500);
}
addEventListener('scroll', onScroll, { passive: true }); onScroll();
if (top) top.addEventListener('click', function () { scrollTo({ top: 0, behavior: 'smooth' }); });
// 复制
document.querySelectorAll('.codebox').forEach(function (box) {
  var btn = box.querySelector('button'), pre = box.querySelector('pre');
  if (!btn || !pre) return;
  btn.addEventListener('click', function () {
    var t = pre.innerText;
    var done = function () {
      btn.textContent = '已复制';
      setTimeout(function () { btn.textContent = '复制'; }, 1200);
    };
    if (navigator.clipboard) navigator.clipboard.writeText(t).then(done, done);
    else {
      var ta = document.createElement('textarea'); ta.value = t;
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch (e) {} ta.remove(); done();
    }
  });
});
// 主题（记住选择 + 跟随系统）
var tb = document.getElementById('theme'), saved = null;
try { saved = localStorage.getItem('dsh-408-theme'); } catch (e) {}
if (!saved && matchMedia && matchMedia('(prefers-color-scheme:dark)').matches) saved = 'dark';
if (saved) document.documentElement.setAttribute('data-theme', saved);
function syncThemeBtn() {
  if (tb) tb.textContent = document.documentElement.getAttribute('data-theme') === 'dark' ? '☀' : '☾';
}
syncThemeBtn();
if (tb) tb.addEventListener('click', function () {
  var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  syncThemeBtn();
  try { localStorage.setItem('dsh-408-theme', next); } catch (e) {}
});
// 窄屏抽屉
var mb = document.getElementById('menu');
if (mb) {
  mb.addEventListener('click', function () { document.querySelector('nav').classList.toggle('open'); });
  document.querySelector('nav').addEventListener('click', function (e) {
    if (e.target.tagName === 'A' && innerWidth <= 1000) this.classList.remove('open');
  });
}
// 目录高亮当前章节
(function () {
  var links = [].slice.call(document.querySelectorAll('nav a.item'));
  var targets = links.map(function (a) {
    var h = a.getAttribute('href') || '';
    var id = h.indexOf('#') >= 0 ? h.split('#')[1] : (a.dataset.anchor || '');
    return id ? document.getElementById(id) : null;
  });
  if (!targets.some(Boolean)) return;
  function mark() {
    var y = scrollY + 130, idx = -1;
    targets.forEach(function (el, i) { if (el && el.offsetTop <= y) idx = i; });
    links.forEach(function (a, i) { a.classList.toggle('cur', i === idx); });
  }
  addEventListener('scroll', mark, { passive: true }); mark();
})();
"""

MERMAID_INIT = """
(function () {
  var nodes = document.querySelectorAll('.mermaid');
  if (!nodes.length) return;
  if (!window.mermaid) {
    nodes.forEach(function (el) {
      el.insertAdjacentHTML('beforebegin',
        '<p class="warn">未加载到 mermaid 运行时（mermaid.min.js 不在预期位置），' +
        '下图以源码显示，可复制到任意 mermaid 编辑器查看。</p>');
      var pre = document.createElement('pre'), code = document.createElement('code');
      code.textContent = el.textContent; pre.appendChild(code);
      el.innerHTML = ''; el.appendChild(pre);
    });
    return;
  }
  mermaid.initialize({ startOnLoad: false, securityLevel: 'loose', theme: 'neutral',
    fontFamily: 'inherit', flowchart: { useMaxWidth: true, htmlLabels: true },
    state: { useMaxWidth: true } });
  nodes.forEach(function (el, i) {
    mermaid.render('mmd-' + i, el.textContent.trim()).then(function (r) {
      el.innerHTML = r.svg;
    }).catch(function (e) {
      el.innerHTML = '<p class="warn">该图渲染失败：' + e.message + '</p>';
      var pre = document.createElement('pre'), code = document.createElement('code');
      code.textContent = el.dataset.src || ''; pre.appendChild(code); el.appendChild(pre);
    });
  });
})();
"""

FIELD_LABELS = ["核心讲解", "关键结论速记", "示意图", "易错点", "真题示例"]


# ---------------------------------------------------------------------------
# Markdown → HTML（重组为语义化组件）
# ---------------------------------------------------------------------------
def _clean_html(body):
    """去掉 python-markdown 给块级元素套的多余 <p>；表格包进可滚动容器。"""
    for tag in ("div", "table", "pre", "blockquote", "details", "ul", "ol", "h1", "h2", "h3"):
        body = body.replace("<p><%s" % tag, "<%s" % tag)
        body = re.sub(r"</%s></p>" % tag, "</%s>" % tag, body)
    body = body.replace("<p></p>\n", "").replace("<p></p>", "")
    body = re.sub(r"<table>", '<div class="tw"><table>', body)
    body = re.sub(r"</table>", "</table></div>", body)
    return body


def _style_fields(body):
    """把模板字段重组成语义化组件。"""
    # 考频统计 → 信息条
    body = re.sub(r"<p><strong>考频统计</strong>[：:]\s*(.*?)</p>",
                  r'<p class="freq"><b>考频</b>　\1</p>', body, flags=re.S)
    # 其余字段标签 → .lab 小标题
    for lab in FIELD_LABELS:
        for tail in ("：", ":"):
            body = body.replace("<p><strong>%s</strong>%s</p>" % (lab, tail),
                                '<p class="lab">%s</p>' % lab)
        body = body.replace("<p><strong>%s</strong></p>" % lab, '<p class="lab">%s</p>' % lab)
        # 标签与内容同段的情况：拆成标题 + 内容
        body = re.sub(r"<p><strong>%s</strong>[：:]\s*" % lab,
                      '<p class="lab">%s</p><p>' % lab, body)
    # 列表加 class（按最近的字段标题归属）
    parts = re.split(r'(<p class="lab">[^<]+</p>)', body)
    out = []
    for chunk in parts:
        m = re.fullmatch(r'<p class="lab">([^<]+)</p>', chunk or "")
        out.append(chunk)
        if m:
            lab = m.group(1)
            if lab == "关键结论速记":
                out.append("\x00FACTS\x00")
            elif lab == "易错点":
                out.append("\x00ERRS\x00")
    body = "".join(out)
    body = re.sub(r"\x00FACTS\x00\s*<ul>", '<ul class="facts">', body)
    body = re.sub(r"\x00ERRS\x00\s*<ul>", '<ul class="errs">', body)
    body = body.replace("\x00FACTS\x00", "").replace("\x00ERRS\x00", "")
    # 真题示例：题干段落标出来源行
    body = re.sub(r"<p>(\s*<strong>((?:19|20)\d{2}\s*年[^<]*)</strong>)",
                  r'<p class="q-stem"><span class="q-src">\2</span>', body)
    return body


def md_to_html(text):
    blocks = []

    def stash(m):
        lang = (m.group(1) or "").lower()
        code = m.group(2)
        if lang == "mermaid":
            blocks.append(
                '<div class="fig"><div class="mermaid" data-src="%s">%s</div>'
                '<details><summary>查看该图 mermaid 源码</summary>'
                '<pre><code>%s</code></pre></details></div>'
                % (html.escape(code, quote=True), html.escape(code), html.escape(code)))
        else:
            cls = "codebox ascii" if lang == "text" else "codebox"
            label = "ASCII 示意图" if lang == "text" else (lang or "代码")
            blocks.append('<div class="%s"><div class="bar"><span>%s</span>'
                          '<button type="button">复制</button></div>'
                          '<pre><code>%s</code></pre></div>'
                          % (cls, label, html.escape(code)))
        return "\x00B%d\x00" % (len(blocks) - 1)

    text = re.sub(r"```(\w*)\n(.*?)```", stash, text, flags=re.S)
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc", "sane_lists"])
    for i, b in enumerate(blocks):
        body = body.replace("<p>\x00B%d\x00</p>" % i, b).replace("\x00B%d\x00" % i, b)
    return _style_fields(_clean_html(body))


# ---------------------------------------------------------------------------
# 页面骨架
# ---------------------------------------------------------------------------
def page(title, sidebar, body, mermaid_src, subtitle=""):
    head = "<h1>%s</h1>" % html.escape(subtitle) if subtitle else ""
    return """<!DOCTYPE html>
<html lang="zh-CN" data-theme="light"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title><style>%s</style>
<script src="%s"></script></head>
<body>
<div id="bar"></div>
<button id="menu" type="button" aria-label="目录">☰</button>
<div id="wrap"><nav>%s</nav><main>%s%s</main></div>
<button class="totop" type="button" aria-label="回到顶部">↑</button>
<button id="theme" type="button" aria-label="切换深浅色">☾</button>
<script>%s</script>
<script>%s</script>
</body></html>""" % (html.escape(title), CSS, html.escape(mermaid_src), sidebar, head, body,
                     JS, MERMAID_INIT)


def sidebar_for(subject_key=None, current=None, single_page=False):
    prefix = "" if subject_key is None else "../"
    out = ['<div class="brand">408 速成复习资料'
           '<small>四科 · 26 个知识点 · 离线可读</small></div>',
           '<input id="q" placeholder="筛选知识点…" autocomplete="off">']
    if single_page:
        out.append('<a class="home" href="#top">⌂ 回到顶部</a>')
    else:
        out.append('<a class="home" href="%sindex.html">⌂ 全科单页合集</a>' % prefix)
    for k in T.ORDER:
        s = T.SUBJECTS[k]
        opened = " open" if (single_page or subject_key == k) else ""
        out.append('<details class="grp"%s><summary><span>%s</span>'
                   '<span class="n">%d 分 · %d 点</span></summary>'
                   % (opened, s["name"], s["score"], len(T.TOPICS[k])))
        for t in T.TOPICS[k]:
            if single_page:
                href, attr = "#%s-%s" % (k, t[6]), ' data-anchor="%s-%s"' % (k, t[6])
            else:
                href, attr = "%s%s/%s.html" % (prefix, s["dir"], t[6]), ""
            cls = "item cur" if (current == t[6] and subject_key == k) else "item"
            out.append('<a class="%s" href="%s"%s>%s</a>' % (cls, href, attr, t[0]))
        out.append("</details>")
    return "\n".join(out)


def build():
    chapters, overviews = {}, {}
    for k in T.ORDER:
        os.makedirs(os.path.join(SITE, T.SUBJECTS[k]["dir"]), exist_ok=True)
    for k in T.ORDER:
        s = T.SUBJECTS[k]
        src = os.path.join(DOCS, s["dir"])      # 读：Markdown 归档
        out = os.path.join(SITE, s["dir"])      # 写：仓库根站点
        # 科目总览不在 TOPICS 注册表里（它不是知识点），需单独载入
        with open(os.path.join(src, "00-科目总览.md"), encoding="utf-8") as f:
            overviews[k] = md_to_html(f.read())
        for t in T.TOPICS[k]:
            with open(os.path.join(src, t[6] + ".md"), encoding="utf-8") as f:
                body = md_to_html(f.read())
            chapters[(k, t[6])] = body
            # 单章页面：给知识点标题加锚点，便于目录高亮
            body = re.sub(r"<h2([^>]*)>", r'<h2\1 id="kp">', body, count=1)
            with open(os.path.join(out, t[6] + ".html"), "w", encoding="utf-8") as f:
                f.write(page("%s · %s" % (s["name"], t[0]), sidebar_for(k, t[6]), body,
                             "../mermaid.min.js",
                             subtitle="%s ｜ %s" % (s["name"], t[0])))
        with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
            f.write(page("%s · 科目总览" % s["name"], sidebar_for(k, None), overviews[k],
                         "../mermaid.min.js", subtitle=s["name"]))

    # 全科单页合集
    parts = ['<a id="top"></a>', "<h1>408 全科速成复习资料</h1>",
             '<p class="warn">本页把四科全部内容合并为单页：左侧目录可折叠与筛选，'
             '右下角可切换深浅色，支持 Ctrl+F 全文检索。</p>']
    for k in T.ORDER:
        s = T.SUBJECTS[k]
        parts.append('<h1 style="margin:2.4em 0 0;font-size:26px">%s'
                     '<span class="tag" style="margin-left:10px">%d 分</span></h1>'
                     % (s["name"], s["score"]))
        parts.append(overviews[k])
        for t in T.TOPICS[k]:
            parts.append('<section class="kp" id="%s-%s">' % (k, t[6]))
            parts.append(chapters[(k, t[6])])
            parts.append("</section>")
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(page("408 全科速成复习资料", sidebar_for(None, None, single_page=True),
                     "\n".join(parts), "mermaid.min.js"))
    rp = os.path.join(DOCS, "00-总览.md")
    if os.path.exists(rp):
        with open(rp, encoding="utf-8") as f:
            body = md_to_html(f.read())
        with open(os.path.join(SITE, "README.html"), "w", encoding="utf-8") as f:
            f.write(page("408 总览", sidebar_for(None, None), body, "mermaid.min.js"))
    return len(chapters)


def build_redirect_stubs():
    """在 408/<科目>/ 内写同名 .md.html 跳转页：点到 md 想看渲染版时用得上。"""
    made = 0
    for k in T.ORDER:
        s = T.SUBJECTS[k]
        for t in T.TOPICS[k]:
            url = "%s.html" % t[6]
            with open(os.path.join(SITE, s["dir"], t[6] + ".md.html"), "w",
                      encoding="utf-8") as f:
                f.write('<!DOCTYPE html><meta charset="utf-8">'
                        '<meta http-equiv="refresh" content="0;url=%s">'
                        '<link rel="canonical" href="%s">' % (url, url))
            made += 1
    return made


def copy_mermaid_runtime():
    src = os.path.join(ROOT, ".tools", "node_modules", "mermaid", "dist", "mermaid.min.js")
    if not os.path.exists(src):
        print("! 未找到 mermaid.min.js（请先 npm install --prefix .tools mermaid jsdom）")
        return False
    data = open(src, "rb").read()
    open(os.path.join(SITE, "mermaid.min.js"), "wb").write(data)
    print("  已复制 mermaid 运行时 %.1f MB → mermaid.min.js" % (len(data) / 1048576))
    return True


def main():
    copy_mermaid_runtime()
    n = build()
    stubs = build_redirect_stubs()
    print("已生成 %d 个章节 HTML + 4 个科目首页 + 1 个全科单页 + %d 个跳转页" % (n, stubs))


if __name__ == "__main__":
    main()
