#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""408 复习资料校验器。

校验项：
  F1 每个 ## 小节必须含 5 个模板字段，且顺序为 考频统计→核心讲解→示意图→易错点→真题示例
  F2 考频统计行必须与 scripts/topics.py 的权威数据逐字一致
  F3 代码围栏必须成对闭合，且示意图必须带语言标签（text/mermaid）
  F4 禁止占位符（TODO / 待补充讲解 / XXX / 略 等）
  F5 ASCII 示意图不得混入全角/中文字符（会破坏等宽对齐），不得含制表符
  F6 真题示例必须标注年份，且年份落在 2009—2025 区间
  F7 高频标记 [高频] 必须出现在小节标题中
  F8 每个知识点必须有 ≥1 个 ASCII 图，且 ≥1 个 Mermaid 图（复杂流程）
  F9 核心讲解 句数（中文句号/分号切分）不少于 3 句
  F10 易错点 条目数 2—4 条
用法： python3 scripts/validate.py [--stats]
"""
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import topics as T  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 仓库根
DOCS = os.path.join(ROOT, ".docs")                                   # Markdown 归档
SITE = ROOT                                                          # HTML 站点就在仓库根

FIELD_ORDER = ["**考频统计**", "**核心讲解**", "**关键结论速记**", "**示意图**", "**易错点**", "**真题示例**"]
FENCE_LANGS = ("text", "mermaid")
# ASCII 图内允许的制表符白名单（与 scripts/PARTS_FORMAT.md 第二节一致）
ALLOWED_BOX = set("─│┌┐└┘├┤┬┴┼▲▼→←↑↓")
PLACEHOLDER = re.compile(r"TODO|FIXME|待补充讲解|此处省略|XXX|\bTBD\b|略\s*$", re.M)
YEAR_RE = re.compile(r"(19|20)\d{2}\s*年")

errors = []
warnings = []
stats = defaultdict(int)
per_file = {}


def err(path, line, code, msg):
    errors.append("%s:%s [%s] %s" % (path, line, code, msg))


def warn(path, line, code, msg):
    warnings.append("%s:%s [%s] %s" % (path, line, code, msg))


def char_width(ch):
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def check_mermaid_block(path, lineno, block):
    """Mermaid 语法静态检查：常见致命写法。"""
    body = [ln for ln in block if ln.strip()]
    if not body:
        err(path, lineno, "F3", "mermaid 代码块为空")
        return
    head = body[0].strip()
    if not re.match(r"^(flowchart (TD|TB|LR|RL|BT)|stateDiagram-v2|graph (TD|TB|LR|RL))\b", head):
        err(path, lineno, "F3", "mermaid 首行必须是 flowchart/stateDiagram-v2 声明，实为 %r" % head[:40])
    for i, ln in enumerate(block, start=lineno):
        s = ln.strip()
        if s in ("{", "}", "end{"):
            err(path, i, "F3", "mermaid 出现孤立花括号（会导致解析失败），应写成 A -->|label| A")
    # 圆括号必须用双引号包裹，否则 mermaid 直接解析失败（已由真实解析器复现）
    for i, ln in enumerate(block, start=lineno):
        seg = ln.strip()
        if seg.startswith("%%"):
            continue
        for m in re.finditer(r"\[([^\]]*)\]|\{([^}]*)\}|\(([^)]*)\)", ln):
            inner = m.group(1) or m.group(2) or m.group(3) or ""
            if ('(' in inner or ')' in inner) and '"' not in inner:
                err(path, i, "F3", "mermaid 节点文本含圆括号但未用双引号包裹: %s" % ln.strip()[:52])
                break
        parts = ln.split("|")
        for k in range(1, len(parts), 2):          # 奇数段即边标签内容
            if ('(' in parts[k] or ')' in parts[k]) and '"' not in parts[k]:
                err(path, i, "F3", "mermaid 边标签含圆括号但未用双引号包裹: %s" % ln.strip()[:52])
                break

    # 逐行安全检查：HTML 标签、双引号成对、行内分号
    for i, ln in enumerate(block, start=lineno):
        if re.search(r"</?[A-Za-z][A-Za-z0-9]*\s*/?>", ln):
            err(path, i, "F3", "mermaid 行内含 HTML 标签（会破坏解析）: %s" % ln.strip()[:50])
        if ln.count('"') % 2 == 1:
            err(path, i, "F3", "mermaid 行内双引号不成对: %s" % ln.strip()[:50])
        if ";" in ln:
            err(path, i, "F3", "mermaid 行内含分号（语句分隔符）: %s" % ln.strip()[:50])


def check_ascii_block(path, lineno, block):
    """ASCII 图对齐检查：不得含全角字符/制表符。"""
    for i, ln in enumerate(block, start=lineno):
        if "\t" in ln:
            err(path, i, "F5", "ASCII 示意图含制表符，会破坏等宽对齐")
        for ch in ln:
            if ord(ch) < 128 or ch in ALLOWED_BOX:
                continue
            if unicodedata.east_asian_width(ch) in ("W", "F"):
                err(path, i, "F5", "ASCII 示意图含全角字符 %r（破坏对齐），请外移为正文注释" % ch)
                break


def validate_file(path, subject_key, is_overview=False):
    rel = os.path.relpath(path, ROOT)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.split("\n")

    if not text.strip():
        err(rel, 1, "F0", "文件为空")
        return

    # ---- 分节 ----
    sections = []  # (title_line_idx, title)
    for i, ln in enumerate(lines):
        m = re.match(r"^## (?!#)(.*)$", ln)
        if m:
            sections.append((i, m.group(1).strip()))
    if not sections:
        err(rel, 1, "F0", "未找到任何 '## 知识点' 小节")
        return

    stats["sections"] += len(sections)

    # 校验每个小节的字段。科目总览是元文件；其余文件的每个 ## 小节都必须齐备五段式
    for idx, (start, title) in enumerate(sections):
        if is_overview:
            continue
        if not title.endswith("[高频]"):
            err(rel, start + 1, "F1", "## 小节《%s》不是知识点小节（标题未以 [高频] 结尾），每个 ## 小节都必须是知识点" % title)
        end = sections[idx + 1][0] if idx + 1 < len(sections) else len(lines)
        body = lines[start:end]
        body_text = "\n".join(body)

        # F1 顺序与存在性（按字段名定位，避免字段增删导致下标错位）
        pos_by_field = {}
        for fld in FIELD_ORDER:
            pos = [k for k, ln in enumerate(body) if ln.startswith(fld)]
            if not pos:
                err(rel, start + 1, "F1", "小节《%s》缺少字段 %s" % (title, fld))
            else:
                pos_by_field[fld] = pos[0]
        order_idx = [pos_by_field[f] for f in FIELD_ORDER if f in pos_by_field]
        if order_idx != sorted(order_idx):
            err(rel, start + 1, "F1", "小节《%s》字段顺序错误，应为 %s" % (title, " → ".join(FIELD_ORDER)))

        def seg(fld):
            """返回该字段起到下一个字段之前的正文行。"""
            if fld not in pos_by_field:
                return []
            i = pos_by_field[fld]
            ends = [v for v in pos_by_field.values() if v > i]
            return body[i:(min(ends) if ends else len(body))]

        # F2 考频统计一致性
        freq_lines = [ln for ln in body if ln.startswith("**考频统计**")]
        if freq_lines:
            expect = None
            for t in T.TOPICS.get(subject_key, []):
                if t[0] in title:
                    expect = T.freq_line(subject_key, t[0])
                    break
            if expect is None:
                # 小节标题不与注册表知识点名匹配
                err(rel, start + 1, "F2", "小节《%s》无法在 topics.py 中匹配到知识点" % title)
            elif freq_lines[0].strip() != expect:
                err(rel, start + 1, "F2", "考频统计与权威数据不一致\n    实际: %s\n    期望: %s"
                    % (freq_lines[0].strip(), expect))

        # F4 占位符
        for k, ln in enumerate(body):
            if PLACEHOLDER.search(ln):
                err(rel, start + 1 + k, "F4", "疑似占位符: %s" % ln.strip()[:60])

        # F6 真题年份
        tr_idx = pos_by_field.get("**真题示例**")
        if tr_idx is not None:
            tr_block = "\n".join(body[tr_idx:])
            years = [int(m.group(0)[:4]) for m in YEAR_RE.finditer(tr_block)]
            if not years:
                err(rel, start + 1 + tr_idx, "F6", "真题示例未标注年份")
            for y in years:
                if not (2009 <= y <= 2025):
                    err(rel, start + 1 + tr_idx, "F6", "真题年份 %d 超出 2009—2025 区间" % y)

        # F7 高频标记
        if "[高频]" in title:
            stats["hot"] += 1
        else:
            warn(rel, start + 1, "F7", "小节《%s》标题未标记 [高频]" % title)

        # F9 核心讲解句数
        cp_idx = pos_by_field.get("**核心讲解**")
        if cp_idx is not None:
            cp = "".join(seg("**核心讲解**"))
            cp = cp.replace("**核心讲解**", "").replace("：", "。", 1)
            sent = [s for s in re.split(r"[。；;]", cp) if len(s.strip()) >= 4]
            if len(sent) < 3:
                err(rel, start + 1 + cp_idx, "F9", "核心讲解不足 3 句（实为 %d）" % len(sent))

        # F10 易错点条数
        ec_idx = pos_by_field.get("**易错点**")
        if ec_idx is not None:
            bullets = [ln for ln in seg("**易错点**") if re.match(r"^\s*[-*·]\s+\S", ln)]
            if not (2 <= len(bullets) <= 4):
                err(rel, start + 1 + ec_idx, "F10", "易错点应为 2—4 条，实为 %d 条" % len(bullets))

    # ---- Markdown 结构 lint 与渲染验证 ----
    lint_markdown(rel, lines)
    if not is_overview:
        render_check(rel, text)

    # ---- 代码围栏 ----
    ascii_cnt, mermaid_cnt = scan_fences(rel, lines)

    # F8 图表数量
    if ascii_cnt == 0:
        err(rel, 1, "F8", "全文没有任何 ASCII(text) 示意图")
    if mermaid_cnt == 0:
        err(rel, 1, "F8", "全文没有任何 Mermaid 流程图")

    per_file[rel] = {
        "sections": len(sections),
        "ascii": ascii_cnt,
        "mermaid": mermaid_cnt,
        "chars": len(text),
    }
    stats["ascii"] += ascii_cnt
    stats["mermaid"] += mermaid_cnt
    stats["chars"] += len(text)


def scan_fences(rel, lines):
    """扫描代码围栏：校验语言标签、ASCII 对齐、mermaid 语法，返回 (ascii 数, mermaid 数)。"""
    ascii_cnt = mermaid_cnt = 0
    in_fence = False
    fence_lang = ""
    fence_start = 0
    buf = []
    for i, ln in enumerate(lines, start=1):
        m = re.match(r"^\s*```(\w*)\s*$", ln)
        if m and not in_fence:
            in_fence = True
            fence_lang = m.group(1)
            fence_start = i
            buf = []
            if fence_lang not in FENCE_LANGS:
                err(rel, i, "F3", "代码块缺少语言标签或标签非法（%r），示意图仅允许 text/mermaid" % fence_lang)
        elif ln.strip() == "```" and in_fence:
            in_fence = False
            if fence_lang == "text":
                ascii_cnt += 1
                check_ascii_block(rel, fence_start + 1, buf)
            elif fence_lang == "mermaid":
                mermaid_cnt += 1
                check_mermaid_block(rel, fence_start + 1, buf)
            buf = []
        elif in_fence:
            buf.append(ln)
    if in_fence:
        err(rel, fence_start, "F3", "代码围栏未闭合（起始 %s，语言 %s）" % (fence_start, fence_lang))
    return ascii_cnt, mermaid_cnt


def validate_partial(subject_key, topic, path):
    """校验 parts/<科目>/<slug>.md 半成品：段落齐全、图合规、易错点条数、真题年份。"""
    rel = os.path.relpath(path, ROOT)
    name, times, years, ratio, qtype, hot, slug = topic
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.split("\n")
    segs = {}
    cur = None
    for i, ln in enumerate(lines, start=1):
        m = re.match(r"^# (\S.*?)\s*$", ln)
        if m:
            cur = m.group(1)
            segs[cur] = []
            continue
        if cur:
            segs[cur].append(ln)
    need = ["核心讲解", "关键结论速记", "示意图", "易错点", "真题示例"]
    for k in need:
        if k not in segs or not "".join(segs[k]).strip():
            err(rel, 1, "F1", "缺少段落 # %s" % k)
    if "示意图" not in segs:
        return

    # 段落顺序
    order = [k for k in segs if k in need]
    if order != [k for k in need if k in order]:
        err(rel, 1, "F1", "段落顺序错误：%s" % " / ".join(order))

    # 图
    ascii_cnt, mermaid_cnt = scan_fences(rel, lines)
    if ascii_cnt == 0:
        err(rel, 1, "F8", "缺少 ASCII(text) 示意图")
    if mermaid_cnt == 0:
        err(rel, 1, "F8", "缺少 mermaid 流程图")

    # 核心讲解句数
    cp = "".join(segs.get("核心讲解", []))
    main_sent = [x for x in re.split(r"[。！？]", cp) if len(x.strip()) >= 4]
    if not (3 <= len(main_sent) <= 10):
        err(rel, 1, "F9", "核心讲解主句数 %d，应在 3—8 句量级（按句号切分）" % len(main_sent))

    # 速记条数
    kb = [ln for ln in segs.get("关键结论速记", []) if re.match(r"^\s*[-*]\s+\S", ln)]
    if not (3 <= len(kb) <= 8):
        err(rel, 1, "F11", "关键结论速记应 3—8 条，实为 %d" % len(kb))

    # 易错点条数
    ec = [ln for ln in segs.get("易错点", []) if re.match(r"^\s*[-*]\s+\S", ln)]
    if not (2 <= len(ec) <= 4):
        err(rel, 1, "F10", "易错点应 2—4 条，实为 %d" % len(ec))

    # 真题年份
    tr = "".join(segs.get("真题示例", []))
    yrs = [int(m.group(0)[:4]) for m in YEAR_RE.finditer(tr)]
    if not yrs:
        err(rel, 1, "F6", "真题示例未标注年份")
    for y in yrs:
        if not (2009 <= y <= 2025):
            err(rel, 1, "F6", "真题年份 %d 超出 2009—2025" % y)

    # 占位符与考频数字越权
    for i, ln in enumerate(lines, start=1):
        if PLACEHOLDER.search(ln):
            err(rel, i, "F4", "疑似占位符: %s" % ln.strip()[:60])
        if re.search(r"考察次数|分数占比", ln):
            err(rel, i, "F2", "parts 文件不得自带考频数字（由 build.py 注入）")

    stats["sections"] += 1
    stats["ascii"] += ascii_cnt
    stats["mermaid"] += mermaid_cnt
    stats["chars"] += len(text)
    per_file[rel] = {"sections": 1, "ascii": ascii_cnt, "mermaid": mermaid_cnt, "chars": len(text)}


def lint_markdown(rel, lines):
    """F13: Markdown 结构 lint —— 块级元素之间必须有空行。

    为什么重要：Markdown 中单换行不产生换行。块级元素（标题、引用块、表格块、
    列表、代码围栏）与相邻段落之间若只隔一个换行，渲染时会粘连成一整段。
    本资料初版即因此把五个模板字段渲染成一坨。
    """
    def is_head(l):
        return bool(re.match(r"^#{1,6} ", l.strip()))

    def is_fence(l):
        return l.strip().startswith("```")

    def is_quote(l):
        return l.strip().startswith(">")

    def is_table_row(l):
        s = l.strip()
        return s.startswith("|") or (s and set(s) <= set("-|: ") and "-" in s)

    # 标出代码围栏的开/闭角色
    fence_role, in_fence = {}, False
    for i, l in enumerate(lines):
        if is_fence(l):
            if not in_fence:
                fence_role[i] = "open"; in_fence = True
            else:
                fence_role[i] = "close"; in_fence = False

    # 表格块（连续表格行）与引用块（连续 > 行）——都必须排除代码块内部
    inner = set()
    ins = False
    for i, l in enumerate(lines):
        if is_fence(l):
            ins = not ins
            inner.add(i)
            continue
        if ins:
            inner.add(i)

    tbl, qte = {}, {}
    i = 0
    while i < len(lines):
        if i not in inner and is_table_row(lines[i]):
            j = i
            while j + 1 < len(lines) and j + 1 not in inner and is_table_row(lines[j + 1]):
                j += 1
            for x in range(i, j + 1):
                tbl[x] = (x == i, x == j)
            i = j + 1
        else:
            i += 1
    i = 0
    while i < len(lines):
        if i not in inner and is_quote(lines[i]):
            j = i
            while j + 1 < len(lines) and j + 1 not in inner and is_quote(lines[j + 1]):
                j += 1
            for x in range(i, j + 1):
                qte[x] = (x == i, x == j)
            i = j + 1
        else:
            i += 1

    def need_blank_before(i):
        l = lines[i]
        if not l.strip():
            return False
        if i in fence_role:
            return fence_role[i] == "open"        # 关闭围栏内不能有空行
        if i in tbl:
            return tbl[i][0]
        if i in qte:
            return qte[i][0]
        return is_head(l)

    def need_blank_after(i):
        l = lines[i]
        if i in fence_role:
            return fence_role[i] == "close"       # 开启围栏后紧接代码内容
        if i in tbl:
            return tbl[i][1]
        if i in qte:
            return qte[i][1]
        return is_head(l)

    for i in range(len(lines)):
        if not lines[i].strip() or i in inner:
            continue
        if need_blank_before(i) and i > 0 and lines[i - 1].strip():
            err(rel, i + 1, "F13", "「%s」之前缺少空行（渲染时会与上一段粘连）" % lines[i].strip()[:36])
        if need_blank_after(i) and i + 1 < len(lines) and lines[i + 1].strip():
            err(rel, i + 1, "F13", "「%s」之后缺少空行" % lines[i].strip()[:36])
    for i in range(1, len(lines)):
        if not lines[i].strip() and not lines[i - 1].strip():
            err(rel, i + 1, "F13", "连续空行")


def render_check(rel, text):
    """F14: 用真实 Markdown 渲染器确认模板字段各自独立成段。

    这条是 F13 的"效果验证"：F13 检查空行是否规范，F14 直接渲染并断言
    六个字段标签落在不同的 <p> 里，防止再次出现"五个字段糊成一坨"。
    """
    try:
        import markdown
    except ImportError:
        return
    labels = ["考频统计", "核心讲解", "关键结论速记", "示意图", "易错点", "真题示例"]
    html = markdown.markdown(text, extensions=["tables", "fenced_code"])
    paras = re.findall(r"<p>(.*?)</p>", html, re.S)
    seen = {}
    for lab in labels:
        tag = "<strong>%s</strong>" % lab
        # 必须"位于段首"才算独立成段；出现在段落中间即为被上一段吞并
        for i, para in enumerate(paras):
            head = para.strip()[:len(tag) + 8]
            if tag in head:
                if lab in seen:
                    err(rel, 0, "F14", "字段 %s 出现在多个段落中" % lab)
                seen[lab] = i
                break
        else:
            where = [i for i, para in enumerate(paras) if tag in para]
            if where:
                err(rel, 0, "F14", "字段 %s 被并入上一段（出现在第 %d 段中间）" % (lab, where[0]))
            else:
                err(rel, 0, "F14", "字段 %s 未渲染出来" % lab)
    idx = [seen[l] for l in labels if l in seen]
    shared = [k for k in set(idx) if idx.count(k) > 1]
    if shared:
        bad = [l for l in labels if seen.get(l) in shared]
        err(rel, 0, "F14", "字段 %s 被渲染进同一段落（模板粘连）" % "、".join(bad))


def check_links():
    """F15: 文档内所有相对链接必须能从仓库根解析（统一口径，避免搬家后失效）。"""
    import glob as _g
    files = _g.glob(os.path.join(DOCS, "*", "*.md")) + [os.path.join(DOCS, "00-总览.md")]
    for f in files:
        rel = os.path.relpath(f, ROOT)
        with open(f, encoding="utf-8") as fh:
            for m in re.finditer(r"\]\(([^)\s]+)\)", fh.read()):
                target = m.group(1)
                if target.startswith(("http", "#", "mailto:")):
                    continue
                # 允许两种口径：与所在 md 同目录，或相对 408/ 根
                cands = [os.path.join(os.path.dirname(f), target),
                         os.path.join(DOCS, target)]
                if not any(os.path.exists(c) for c in cands):
                    err(rel, 0, "F15", "相对链接解析失败（同目录 / 408/ 根均无此文件）：%s" % target)


def check_html():
    """F16: HTML 产物完整性与组件完整性。

    分两层：
      (a) 完整性——章节页/锚点/资源不静默缺失；
      (b) 组件完整性——模板字段必须被重组成对应组件（F17 的核心内容也在此校验），
          防止「渲染器退化回裸 Markdown」而无人发觉。
    """
    # ---- 组件完整性：每一章都必须产出各字段对应的组件 ----
    need_cls = ['class="freq"', '<ul class="facts">', '<ul class="errs">', 'class="q-stem"']
    for k in T.ORDER:
        s = T.SUBJECTS[k]
        for t in T.TOPICS[k]:
            fp = os.path.join(SITE, s["dir"], t[6] + ".html")
            if not os.path.exists(fp):
                continue
            with open(fp, encoding="utf-8") as fh:
                body = fh.read()
            for cls in need_cls:
                if cls not in body:
                    err("408/%s/%s.html" % (s["dir"], t[6]), 0, "F16",
                        "缺少组件 %s（渲染器可能退化为裸 Markdown）" % cls)
            if "codebox ascii" not in body and 'class="fig"' not in body:
                err("408/%s/%s.html" % (s["dir"], t[6]), 0, "F16", "图文组件均缺失")
    # ---- 结构完整性 ----

    idx = os.path.join(SITE, "index.html")
    if not os.path.exists(idx):
        err("408/index.html", 0, "F16", "缺少全科单页合集（先跑 scripts/build_html.py）")
        return
    with open(idx, encoding="utf-8") as f:
        page = f.read()
    n_topics = 0
    for k in T.ORDER:
        s = T.SUBJECTS[k]
        d = os.path.join(SITE, s["dir"])
        if not os.path.exists(os.path.join(d, "index.html")):
            err("408/%s" % s["dir"], 0, "F16", "缺少科目首页 index.html")
        if ("本科目章节索引" in page) and (s["name"] not in page):
            err("408/index.html", 0, "F16", "合集缺少科目 %s 的内容" % s["name"])
        for t in T.TOPICS[k]:
            n_topics += 1
            fp = os.path.join(d, t[6] + ".html")
            if not os.path.exists(fp):
                err("408/%s" % s["dir"], 0, "F16", "缺少章节 HTML：%s.html" % t[6])
            if 'id="%s-%s"' % (k, t[6]) not in page:
                err("408/index.html", 0, "F16", "合集缺少锚点 %s-%s" % (k, t[6]))
    if page.count('class="mermaid"') < n_topics:
        err("408/index.html", 0, "F16",
            "合集 mermaid 容器数 %d 少于知识点数 %d" % (page.count('class="mermaid"'), n_topics))
    for sub in T.ORDER:
        if "本科目章节索引" not in page:
            err("408/index.html", 0, "F16", "合集未并入科目总览（章节索引）")
            break
    if not os.path.exists(os.path.join(SITE, "mermaid.min.js")):
        warn("408/mermaid.min.js", 0, "F16", "缺少 mermaid 运行时，HTML 里的图将回退为源码")
    # 跳转页的 url 目标必须真实存在
    import glob as _g
    for f in (_g.glob(os.path.join(ROOT, "*", "*.md.html"))
              + _g.glob(os.path.join(SITE, "*", "*.md.html"))
              + _g.glob(os.path.join(ROOT, "*.html"))):
        rel = os.path.relpath(f, ROOT)
        with open(f, encoding="utf-8") as fh:
            head = fh.read()
        m = re.search(r'url=([^"]+)', head)
        if m:
            url = m.group(1)
            if url.startswith(("/", "file:", "http")):
                err(rel, 0, "F16", "跳转页必须用相对路径（换机器会失效）：%s" % url)
            elif not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(f), url))):
                err(rel, 0, "F16", "跳转页目标不存在：%s" % url)

    # 每个 HTML 页面引用的本地脚本/样式必须真实存在
    for f in _g.glob(os.path.join(SITE, "*", "*.html")) + [idx]:
        rel = os.path.relpath(f, ROOT)
        with open(f, encoding="utf-8") as fh:
            body = fh.read()
        for ref in re.findall(r'<script src="([^"]+)"', body):
            if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(f), ref))):
                err(rel, 0, "F16", "引用的脚本不存在：%s" % ref)


def main():
    parts_mode = "--parts" in sys.argv
    if parts_mode:
        for key in T.ORDER:
            for t in T.TOPICS[key]:
                p = os.path.join(ROOT, "parts", key, t[6] + ".md")
                if not os.path.exists(p):
                    err("parts/%s" % key, 0, "F0", "缺少半成品 %s.md" % t[6])
                    continue
                validate_partial(key, t, p)
        return report("parts 半成品校验报告")

    for key in T.ORDER:
        d = os.path.join(DOCS, T.SUBJECTS[key]["dir"])
        if not os.path.isdir(d):
            err(T.SUBJECTS[key]["dir"], 0, "F0", "科目目录不存在")
            continue
        files = sorted(f for f in os.listdir(d) if f.endswith(".md"))
        got_slugs = {os.path.splitext(f)[0] for f in files}
        want_slugs = {t[6] for t in T.TOPICS[key]}
        for s in sorted(want_slugs - got_slugs):
            err(T.SUBJECTS[key]["dir"], 0, "F0", "缺少章节文件 %s.md" % s)
        for s in sorted(got_slugs - want_slugs - {"00-科目总览"}):
            warn(T.SUBJECTS[key]["dir"], 0, "F0", "存在未登记章节文件 %s.md" % s)
        for f in files:
            validate_file(os.path.join(d, f), key, is_overview=f.startswith("00-"))

    check_readme_citations()
    check_links()
    check_html()
    return report("408 复习资料校验报告")


def check_readme_citations():
    """F12: README 声明的"已核对原题"清单必须与正文标注逐条一致。"""
    import glob
    actual = set()
    for f in glob.glob(os.path.join(ROOT, "parts", "*", "*.md")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^\*\*((?:19|20)\d{2}) 年 408 第 (\d+) 题", line.strip())
                if m:
                    actual.add((m.group(1), m.group(2)))
    rp = os.path.join(DOCS, "00-总览.md")
    with open(rp, encoding="utf-8") as fh:
        readme = fh.read()
    declared = set(re.findall(r"\| `(\d{4})` 第 `(\d+)` 题", readme))
    for item in sorted(declared - actual):
        err("README.md", 0, "F12", "声明为已核对原题但正文未标注：%s 年第 %s 题" % item)
    for item in sorted(actual - declared):
        err("README.md", 0, "F12", "正文标注为原题但未在 README 声明清单中：%s 年第 %s 题" % item)
    stats["orig"] = len(actual)


def report(title):
    print("=" * 74)
    print(title)
    print("=" * 74)
    for k, v in sorted(per_file.items()):
        print("  %-46s 知识点 %2d | ASCII 图 %2d | Mermaid %2d | %6d 字"
              % (k, v["sections"], v["ascii"], v["mermaid"], v["chars"]))
    print("-" * 74)
    print("  文件 %d 个 | 知识点 %d 个 | ASCII 图 %d | Mermaid 图 %d | 总计 %d 字"
          % (len(per_file), stats["sections"], stats["ascii"], stats["mermaid"], stats["chars"]))
    print("  高频标记 %d 个 | 真题原题 %d 道" % (stats["hot"], stats.get("orig", 0)))
    print("-" * 74)
    if errors:
        print("  ✗ 错误 %d 条：" % len(errors))
        for e in errors[:80]:
            print("    " + e)
        if len(errors) > 80:
            print("    ... 其余 %d 条省略" % (len(errors) - 80))
    else:
        print("  ✓ 全部强制校验项通过")
    if warnings:
        print("  ! 警告 %d 条：" % len(warnings))
        for w in warnings[:30]:
            print("    " + w)
    print("=" * 74)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
