#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 .docs/ 下的 Markdown 渲染成「为阅读而设计」的 HTML 站点。

与普通 Markdown→HTML 的区别（这就是本文件存在的理由）：
  1. 不做「Markdown 原样搬进网页」，而是把模板结构**重组成语义化组件**：
     考频统计 → 信息条；结论速记 → 公式卡；易错点 → 卡片；真题解析 → 引用块。
  2. 六段字段包成 `<section class="sec sec-*" id="sec-*">`，可直接锚点跳转。
  3. ASCII 示意图用深色面板 + 复制按钮；Mermaid 用本地运行时渲染（离线可用）。
  4. 统一外壳：顶栏面包屑 + 侧栏目录（分组 + 当前章六段锚点 + 筛选）+ 章节
     prev/next + 页脚；样式与行为外置为 assets/site.css 与 assets/site.js。
     外壳的 DOM 与 class 名与 Lerno-math 共用同一份契约
     （见 ../PLAN-对齐与改版.md 2.3/2.4），改类名前先改契约。

产出：
  <科目>/<章节>.html      每章一页
  <科目>/index.html       科目首页
  index.html              全科单页合集（四科全部内容）
  README.html             总览
  assets/site.css|site.js 外壳样式与行为
  mermaid.min.js          本地 mermaid 运行时

用法： python3 scripts/build_html.py
"""
import glob
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meta as T  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, ".docs")     # Markdown 归档（输入）
SITE = ROOT                            # HTML 站点（输出，仓库根即可被静态托管）

try:
    import markdown
except ImportError:
    sys.exit("需要 python-markdown：pip install markdown")

# ---------------------------------------------------------------------------
# 外壳资源：assets/ 下的源文件是**手写源**（不是生成物），必须入库
# ---------------------------------------------------------------------------
ASSETS = os.path.join(SITE, "assets")

# 六段字段的锚点 id / class（契约钦定，与 Lerno-math 逐字一致）
SECS = [
    ("考频统计", "sec-freq"),
    ("核心讲解", "sec-core"),
    ("关键结论速记", "sec-key"),
    ("示意图", "sec-fig"),
    ("易错点", "sec-err"),
    ("真题示例", "sec-real"),
]

FIELD_LABELS = ["核心讲解", "关键结论速记", "示意图", "易错点", "真题示例"]

# 六段标题栏（统一版 site.css 的 .sec-h）：图标 + 标题 + 右侧说明。
# 色相由 `.sec-xxx .sec-h` 规则决定，**不写内联 style**（数学二的 4 条要求之一）。
SEC_ICON = {
    "考频统计": ("📊", "历年考察次数与题型"),
    "核心讲解": ("📖", "逐个考点讲清"),
    "关键结论速记": ("🔑", "考前扫读"),
    "示意图": ("🗺", "结构 / 流程"),
    "易错点": ("⚠️", "踩过的坑"),
    "真题示例": ("✍️", "自测用"),
}


def sec_h(label):
    """六段标题栏：`<div class="sec-h">` + .ic/.tt/.hint。"""
    ic, hint = SEC_ICON.get(label, ("•", ""))
    return ('<div class="sec-h"><span class="ic" aria-hidden="true">%s</span>'
            '<h2 class="tt">%s</h2>'
            '<span class="hint">%s</span></div>' % (ic, label, hint))


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
    # ⚠️ 必须放在**列表归属之后**：上一步靠 `<p class="lab">` 标记给 ul 挂 .facts/.errs。
    # 先替换成占位就会让那一步认不出标签，速记/易错点会丢掉列表样式。
    # 换成占位是因为统一版 site.css 已删掉 .lab，改由 _wrap_sections 产出 .sec-h。
    for lab, _sid in SECS:
        body = body.replace('<p class="lab">%s</p>' % lab, "\x00H:%s\x00" % lab)
    # 真题示例：题干段落标出来源行
    body = re.sub(r"<p>(\s*<strong>((?:19|20)\d{2}\s*年[^<]*)</strong>)",
                  r'<p class="q-stem"><span class="q-src">\2</span>', body)
    return _wrap_sections(body)


# 六段字段 → 锚点 id（契约钦定）
SEC_IDS = dict(SECS)


def _wrap_sections(body):
    """把六段字段包成统一版的结构：

        <section class="sec sec-xxx" id="sec-xxx">
          <div class="sec-h">…图标 + 标题 + 说明…</div>
          <div class="box">…正文…</div>
        </section>

    `_style_fields` 已把字段标签换成了 `\x00H:<字段>\x00` 占位，这里负责切分、
    换成 `.sec-h`、并给正文套 `.box`（统一版 site.css 的 `.sec>.box` 承担内边距）。

    必须在列表归属处理**之后**做：那一步靠标签顺序给 ul 挂 .facts/.errs，
    先包 section 会把标记隔开。
    """
    labs = "|".join(re.escape(lab) for lab, _ in SECS)
    # 切分点两类：其余五段的 `\x00H:标签\x00` 占位，以及考频统计的信息条
    # ——考频的标签已被 _style_fields 换成 `<p class="freq">`，不再是 .lab 占位，
    # 所以必须单独认；漏了它整段考频就落在第一个 section 之外、没有标题栏。
    parts = re.split(r'(\x00H:(?:%s)\x00|<p class="freq">)' % labs, body)
    out, open_sec = [], False
    # parts[0] 是第一个字段之前的内容（知识点标题等），留在 section 之外
    if parts and parts[0].strip():
        out.append(parts[0])
    i = 1
    while i < len(parts):
        tag = parts[i]
        chunk = parts[i + 1] if i + 1 < len(parts) else ""
        if tag.startswith('<p class="freq">'):
            lab = "考频统计"
        else:
            lab = re.fullmatch(r"\x00H:(.*?)\x00", tag).group(1)
        sid = SEC_IDS.get(lab)
        if sid:
            if open_sec:
                out.append("</div></section>")
            out.append('<section class="sec %s" id="%s">%s<div class="box">'
                       % (sid, sid, sec_h(lab)))
            open_sec = True
        out.append(chunk)
        i += 2
    if open_sec:
        out.append("</div></section>")
    return "".join(out)


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
    body = _clean_html(body)
    # 站点不发布 .md 本身，只发布 .html 与同名跳转页 xx.md.html：
    # 把指向 .md 的链接改指跳转页，避免网页里点出 404
    body = re.sub(r'href="([^"]+?)\.md(?![.\w])',
                  lambda m: 'href="%s.md.html"' % m.group(1), body)
    return _style_fields(body)


# ---------------------------------------------------------------------------
# 页面骨架（统一外壳：顶栏 / 侧栏 / main / 章节导航 / 页脚）
#
# class 名与 DOM 层级由 ../PLAN-对齐与改版.md 2.3/2.4 钦定，与 Lerno-math 共用，
# 改任何类名前先改契约——两边分叉的代价远大于等待。
# ---------------------------------------------------------------------------
def asset_prefix(page):
    """外壳资源（assets/、mermaid.min.js）相对当前页面的前缀。

    章节页与科目首页都在 <科目>/ 下一层，根页面（合集/总览）在仓库根。
    """
    return "../" if page in ("chapter", "overview") else ""


def crumbs_for(page, subject_key=None, chapter=None):
    """面包屑：首页 › 科目 › 章节。"""
    prefix = asset_prefix(page)
    out = ['<a href="%sindex.html">首页</a>' % prefix]
    if subject_key:
        s = T.SUBJECTS[subject_key]
        out.append('<span class="tb-sep">›</span>')
        if chapter:
            out.append('<a href="index.html">%s</a>' % html.escape(s["name"]))
            out.append('<span class="tb-sep">›</span>')
            out.append('<span aria-current="page">%s</span>' % html.escape(chapter))
        else:
            out.append('<span aria-current="page">%s</span>' % html.escape(s["name"]))
    else:
        out.append('<span class="tb-sep">›</span>')
        out.append('<span aria-current="page">全科单页合集</span>')
    return '<nav class="tb-crumbs" aria-label="面包屑">%s</nav>' % "".join(out)


def topbar_for(page, subject_key=None, chapter=None, brand="408 速成复习资料",
               crumb_label=None):
    """顶栏。`crumb_label` 给非章节页用（如练习页：首页 › 今日练习）。"""
    if crumb_label:
        crumbs = ('<nav class="tb-crumbs" aria-label="面包屑">'
                  '<a href="%sindex.html">首页</a><span class="tb-sep">›</span>'
                  '<span aria-current="page">%s</span></nav>'
                  % (asset_prefix(page), html.escape(crumb_label)))
    else:
        crumbs = crumbs_for(page, subject_key, chapter)
    return """<header class="site-topbar">
<a class="tb-brand" href="%sindex.html">%s</a>
%s
<button class="tb-search" type="button" aria-label="搜索">搜索</button>
</header>""" % (asset_prefix(page), html.escape(brand), crumbs)


PRACTICE_FILE = "练习.html"          # 408 特有页面（PLAN §2.3.1.A）


def footer_for(page):
    """页脚：内容包在 .sf-inner 里（统一版把页脚列宽也放在 .sf-inner 上）。

    2026-10-20 裁定（D-03 ①）：页脚加「今日练习」入口，零改共用件；
    练习页自身不加（避免自链接）。
    """
    prefix = asset_prefix(page)
    practice = "" if page == "practice" else (
        '<span class="ft-sep">·</span>\n<a href="%s%s">今日练习</a>' % (prefix, PRACTICE_FILE))
    return """<footer class="site-footer">
<div class="sf-inner">
<span>原创讲解 / 图示 / 代码：CC BY-NC-SA 4.0</span>
<span class="ft-sep">·</span>
<a href="%sREADME.html">数据口径与来源</a>
<span class="ft-sep">·</span>
<a href="%sLICENSE">许可协议</a>%s
<a class="ft-top" href="#">回到顶部 ↑</a>
</div>
</footer>""" % (prefix, prefix, practice)


def sidebar_for(subject_key=None, current=None, single_page=False, page="chapter"):
    """侧栏目录：四科分组 + 当前章的六段锚点 + 关键词筛选。

    DOM 与钩子类名严格照 Lerno-math 的 assets/site.js 契约（PLAN 2.4.1）：
    .sb-head/.sb-title/.sb-home/.sb-filter/.sb-group/.sb-group-t/.sb-chap/
    .tocbox/.toclink —— site.js 只认这一套，改名前先改契约。

    page: "chapter" 章节页 | "overview" 科目首页 | "root" 仓库根页面。
    """
    prefix = asset_prefix(page)
    out = ['<div class="sb-head"><span class="sb-title">408 速成复习资料</span>'
           '<a class="sb-home" href="%sindex.html">全科合集</a></div>' % prefix,
           '<input class="sb-filter" type="search" placeholder="筛选章节（输入即过滤）"'
           ' aria-label="筛选章节">']
    for k in T.ORDER:
        s = T.SUBJECTS[k]
        out.append('<div class="sb-group"><div class="sb-group-t">%s（%d 分 · %d 个知识点）</div>'
                   % (s["name"], s["score"], len(T.TOPICS[k])))
        for t in T.TOPICS[k]:
            if single_page:
                href, attr = "#%s-%s" % (k, t[6]), ' data-anchor="%s-%s"' % (k, t[6])
            else:
                # 规则：本科目页面（章节页与科目首页都在该科目目录内）→ 同目录直链；
                #       其他科目 → 上一层再进该科目目录；根目录页面 → 直接进科目目录
                if page in ("chapter", "overview") and k == subject_key:
                    href = "%s.html" % t[6]
                elif page in ("chapter", "overview"):
                    href = "../%s/%s.html" % (s["dir"], t[6])
                else:
                    href = "%s/%s.html" % (s["dir"], t[6])
                attr = ""
            cls = "sb-chap cur" if (current == t[6] and subject_key == k) else "sb-chap"
            # D-09：没有考频数据（PENDING）就不标高频，侧栏也不能替它打标签
            hot_tag = ' <span class="tag">高频</span>' if t[5] else ""
            out.append('<a class="%s" href="%s"%s>%s%s</a>'
                       % (cls, href, attr, t[0], hot_tag))
            # 当前章的六段锚点：直接跳到「只看易错点」那一段
            if current == t[6] and subject_key == k:
                out.append('<div class="tocbox">')
                for lab, sid in SECS:
                    out.append('<a class="toclink" href="#%s">%s</a>' % (sid, lab))
                out.append("</div>")
        out.append("</div>")
    return '<nav class="site-sidebar">%s</nav>' % "\n".join(out)


def chapter_nav(subject_key, slug):
    """章节 prev/next：按 meta.py 的 TOPICS 顺序（也就是阅读顺序）。

    `.cn-prev`/`.cn-next` 是**样式用**类名（PLAN 2.4.1 明确保留）；
    键盘翻章由 body[data-prev|data-next] 驱动，见 page()。
    """
    topics = T.TOPICS[subject_key]
    idx = next((i for i, t in enumerate(topics) if t[6] == slug), None)
    if idx is None:
        return ""
    out = ['<nav class="chapter-nav">']
    if idx > 0:
        p = topics[idx - 1]
        out.append('<a class="cn-prev" href="%s.html"><span class="cn-dir">← 上一章</span>'
                   '<span class="cn-title">%s</span></a>' % (p[6], p[0]))
    if idx + 1 < len(topics):
        n = topics[idx + 1]
        out.append('<a class="cn-next" href="%s.html"><span class="cn-dir">下一章 →</span>'
                   '<span class="cn-title">%s</span></a>' % (n[6], n[0]))
    out.append("</nav>")
    return "".join(out)


def nav_targets(subject_key, slug):
    """键盘翻章目标（body[data-prev|data-next]，契约 2.4.1-B.5）。"""
    topics = T.TOPICS[subject_key]
    idx = next((i for i, t in enumerate(topics) if t[6] == slug), None)
    if idx is None:
        return "", ""
    prev = "%s.html" % topics[idx - 1][6] if idx > 0 else ""
    nxt = "%s.html" % topics[idx + 1][6] if idx + 1 < len(topics) else ""
    return prev, nxt


def page(title, sidebar, body, page_kind="chapter", subject_key=None, chapter=None,
         extra="", head_extra="", with_mermaid=True, crumb_label=None):
    """渲染一个完整页面。

    page_kind 决定外壳资源的相对前缀（见 asset_prefix）与 body 上的翻章数据；
    site.js 在 <head> 里**同步**引入（不可 defer）——主题类要在首屏绘制前定下来。
    """
    p = asset_prefix(page_kind)
    head = "<h1>%s</h1>" % html.escape(chapter) if chapter else ""
    prev, nxt = ("", "")
    if page_kind == "chapter" and subject_key and chapter:
        prev, nxt = nav_targets(subject_key, _slug_of(subject_key, chapter))
    body_attr = ' data-prev="%s" data-next="%s"' % (prev, nxt) if page_kind == "chapter" else ""
    mermaid_tag = ('<script src="%smermaid.min.js"></script>\n' % p) if with_mermaid else ""
    extra_head = ("\n" + head_extra) if head_extra else ""
    return """<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title>
<link rel="stylesheet" href="%sassets/site.css">
%s<script src="%sassets/site.js"></script>%s</head>
<body%s>
<a id="top"></a>
<div class="read-progress"></div>
%s
<button class="nav-toggle" type="button" aria-label="目录">☰</button>
<div class="site-body">
%s
<main><div class="inner">%s%s%s</div></main>
</div>
%s
<button class="to-top" type="button" aria-label="回到顶部">↑</button>
<button class="theme-toggle" type="button" aria-label="切换深浅色">☾</button>
</body></html>""" % (html.escape(title), p, mermaid_tag, p, extra_head, body_attr,
                     topbar_for(page_kind, subject_key, chapter, crumb_label=crumb_label),
                     sidebar,
                     head, body, extra,
                     footer_for(page_kind))


def _slug_of(subject_key, chapter_name):
    for t in T.TOPICS[subject_key]:
        if t[0] == chapter_name:
            return t[6]
    return ""



def relink(body, prefix_re, prefix_out):
    """把正文里的相对链接按「输出位置」重写深度。

    同一段 Markdown 会在两个位置渲染：科目目录内（同目录相对）与根目录的
    合集页（需带科目子目录）。链接必须按渲染位置修正，否则总览里的章节索引
    在合集页里会 404。
    """
    def fix(m):
        href = m.group(2)
        if re.match(r"^(https?:|mailto:|#|/|data:)", href):
            return m.group(0)
        if not re.search(prefix_re, href):
            return m.group(0)
        return '%s="%s%s"' % (m.group(1), prefix_out, href)
    return re.sub(r'(href|src)="([^"]+)"', fix, body)


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
            # 去掉章节正文自带的 h1 与 h2：
            #   h1 —— Markdown 归档顶部那一行 "数据结构 · 线性表"，章名已由 page()
            #         的 <h1>{章名}</h1> 给出，重复渲染会让读者看到同一标题连出三次；
            #   h2 —— "线性表 [高频]"，同上（`[高频]` 只出现在有考频数据的章节，已无区分度，
            #         而它带来的 `id="_2" id="kp"` 还是**重复 id 属性**，非法 HTML）。
            # 旧写法 `re.sub(r"<h2([^>]*)>", r'<h2\1 id="kp">', …)` 更糟：给一个已经
            # 有 id 的 h2 再插一个 id，等于把非法 HTML 固化下来。
            # 做法照抄数学二 build_html.py 的同一处理（剥掉第一个 h1 与 h2）。
            # ⚠️ 必须匹配带属性的形式：渲染器开着 markdown 的 `toc` 扩展，
            # 产出的其实是 `<h1 id="_1">` / `<h2 id="_2">`。只写 `<h1>` 会一条都
            # 匹配不到、标题照样重复（第一版就是这么错的，靠断言才发现）。
            body = re.sub(r"<h1\b[^>]*>.*?</h1>", "", body, count=1, flags=re.S)
            body = re.sub(r"<h2\b[^>]*>.*?</h2>", "", body, count=1, flags=re.S)
            with open(os.path.join(out, t[6] + ".html"), "w", encoding="utf-8") as f:
                f.write(page("%s · %s" % (s["name"], t[0]),
                             sidebar_for(k, t[6], page="chapter"), body,
                             page_kind="chapter", subject_key=k, chapter=t[0],
                             extra=chapter_nav(k, t[6])))
        # 科目首页：既是该科入口，也是章节页面包屑的中间一层。
        # 同样剥掉总览自带的 h1（`# 数据结构 · 408 速成复习资料`）——页面的
        # `<h1>{科目名}</h1>` 已经给出，否则又出现"同一标题连着两次"。
        ov_body = re.sub(r"<h1\b[^>]*>.*?</h1>", "", overviews[k], count=1, flags=re.S)
        with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
            f.write(page("%s · 科目首页" % s["name"],
                         sidebar_for(k, None, page="overview"), ov_body,
                         page_kind="overview", subject_key=k, chapter=s["name"]))

    # 落地页统计数字：从 .docs 实际内容与 meta 现算，避免补章节后写死的数字过期
    ascii_n = mer_n = 0
    for f in glob.glob(os.path.join(DOCS, "*", "*.md")):
        if os.path.basename(f).startswith("00-"):
            continue                      # 科目总览页是章节内容的汇总副本，不重复计数
        with open(f, encoding="utf-8") as fh:
            txt = fh.read()
        ascii_n += len(re.findall(r"^```text\s*$", txt, re.M))
        mer_n += len(re.findall(r"^```mermaid\s*$", txt, re.M))
    topic_n = sum(len(v) for v in T.TOPICS.values())

    # 全科单页合集（落地页）
    parts = ['<a id="top"></a>',
             '<h1 style="font-size:32px;margin-bottom:10px">408 计算机学科专业基础综合'
             '<span class="tag" style="margin-left:12px;font-size:12px">速成复习资料</span></h1>',
             '<p style="color:var(--fg2);font-size:15px;margin-bottom:18px">'
             '数据结构 · 计算机组成原理 · 操作系统 · 计算机网络</p>',
             home_subject_cards(),
             # D-03 ①：练习入口放在 .home-subjects **之外**，不改变卡片数（F22）
             '<p style="margin:16px 0 6px;font-size:15px">'
             '<a href="%s" style="font-weight:600">今日练习 →</a> '
             '<span style="color:var(--fg2)">按今日计划刷题、记录错题与掌握度'
             '（数据只存在本机浏览器）</span></p>' % PRACTICE_FILE,
             ('<div class="tw" style="margin:18px 0 26px"><table><thead><tr>'
              '<th>4 个科目</th><th>%d 个知识点</th><th>%d 张 ASCII 图</th>'
              '<th>%d 张 Mermaid 图</th><th>完全离线可用</th>'
              '</tr></thead></table></div>') % (topic_n, ascii_n, mer_n),
             '<p class="warn">本页把四科全部内容合并为单页：左侧目录可折叠与筛选，'
             '右下角可切换深浅色，支持 Ctrl+F 全文检索；每个知识点均按'
             '「考频统计 → 核心讲解 → 关键结论速记 → 示意图 → 易错点 → 真题示例」组织。</p>']
    for k in T.ORDER:
        s = T.SUBJECTS[k]
        parts.append('<h1 style="margin:2.4em 0 0;font-size:26px">%s'
                     '<span class="tag" style="margin-left:10px">%d 分</span></h1>'
                     % (s["name"], s["score"]))
        # 合集页在仓库根渲染，总览里的章节索引需补上科目子目录
        parts.append(relink(overviews[k], r"\.md\.html", s["dir"] + "/"))
        for t in T.TOPICS[k]:
            parts.append('<section class="kp" id="%s-%s">' % (k, t[6]))
            parts.append(chapters[(k, t[6])])
            parts.append("</section>")
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(page("408 全科速成复习资料",
                     sidebar_for(None, None, single_page=True, page="root"),
                     "\n".join(parts), page_kind="root"))
    rp = os.path.join(DOCS, "00-总览.md")
    if os.path.exists(rp):
        with open(rp, encoding="utf-8") as f:
            body = md_to_html(f.read())
        with open(os.path.join(SITE, "README.html"), "w", encoding="utf-8") as f:
            f.write(page("408 总览", sidebar_for(None, None, page="root"), body,
                         page_kind="root"))
    return len(chapters)


def home_subject_cards():
    """首页科目卡片入口（契约 2.5.1）：类名与 Lerno-math 逐字一致。"""
    out = ['<nav class="home-subjects">']
    for k in T.ORDER:
        s = T.SUBJECTS[k]
        out.append('<a class="hs-card" href="%s/index.html">'
                   '<span class="hs-name">%s</span>'
                   '<span class="hs-meta">%d 个知识点 · %d 分</span></a>'
                   % (s["dir"], html.escape(s["name"]), len(T.TOPICS[k]), s["score"]))
    out.append("</nav>")
    return "".join(out)


def practice_sidebar():
    """练习页侧栏：练习视图导航（复用外壳类名；site.js 的筛选器此页不启用）。"""
    items = [("today", "今日"), ("practice", "刷题"), ("wrong", "错题本"),
             ("mock", "模拟考"), ("stats", "学习报告"), ("settings", "设置")]
    out = ['<div class="sb-head"><span class="sb-title">练习闭环</span>'
           '<a class="sb-home" href="index.html">全科合集</a></div>',
           '<div class="sb-group"><div class="sb-group-t">练习</div>']
    for key, label in items:
        out.append('<a class="sb-chap" href="#/%s" data-view="%s">%s</a>'
                   % (key, key, label))
    out.append("</div>")
    return '<nav class="site-sidebar">%s</nav>' % "\n".join(out)


def practice_body():
    """练习页主体：静态骨架 + 一个容器，路由与视图由 assets/practice.js 负责。"""
    return """<div class="pv">
<h1 class="pv-title">今日练习</h1>
<p class="pv-sub">按每日目标刷题、记录错题与掌握度。数据只保存在本机浏览器，不上传。</p>
<div id="practice-view" class="pv-view" aria-live="polite">
<section class="pv-card"><p class="pv-note">正在加载题库…</p></section>
</div>
<noscript><section class="pv-card"><p class="pv-note">练习功能需要启用 JavaScript。</p></section></noscript>
</div>"""


def build_practice():
    """写 练习.html（408 特有页面，契约 §2.3.1.A）。

    - 套完整外壳（顶栏 / 侧栏 / 页脚），但**不含**六段锚点、不进 prev/next；
    - 样式与行为全在 assets/practice.css / practice.js，site.css 与 site.js 零改动；
    - 本页不加载 mermaid 运行时（用不到，省 5.5 MB）。
    """
    head_extra = ('<link rel="stylesheet" href="assets/practice.css">\n'
                  '<script src="assets/quiz-data.js"></script>\n'
                  '<script src="assets/practice.js"></script>')
    html_text = page("今日练习 · 408 速成复习资料", practice_sidebar(), practice_body(),
                     page_kind="practice", head_extra=head_extra, with_mermaid=False,
                     crumb_label="今日练习")
    with open(os.path.join(SITE, PRACTICE_FILE), "w", encoding="utf-8") as f:
        f.write(html_text)
    return PRACTICE_FILE


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
    practice = build_practice()
    stubs = build_redirect_stubs()
    print("已生成 %d 个章节 HTML + 4 个科目首页 + 1 个全科单页 + 1 个练习页（%s）"
          " + %d 个跳转页" % (n, practice, stubs))


if __name__ == "__main__":
    main()
