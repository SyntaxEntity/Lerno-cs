#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""408 复习资料校验器。

校验项（F1—F17）：
  F1 每个 ## 小节必须含 6 个模板字段，且顺序为
     考频统计→核心讲解→关键结论速记→示意图→易错点→真题示例
  F2 考频统计行必须与 scripts/topics.py 的权威数据逐字一致
  F3 代码围栏必须成对闭合，示意图必须带语言标签（text/mermaid）；
     mermaid 除静态规则外**必须交给官方解析器真解析**（scripts/check_mermaid.mjs），
     解析失败、解析器不在、node 或 .tools 依赖缺失、一张图都没扫到——全是 error，
     不静默跳过（离线时须显式加 --no-mermaid）
  F4 禁止占位符（TODO / 待补充讲解 / XXX / 略 等）
  F5 ASCII 示意图不得混入全角/中文字符（会破坏等宽对齐），不得含制表符
  F6 真题示例必须标注年份，且年份落在 2009—2025 区间
  F7 高频标记 [高频] 必须出现在小节标题中
  F8 每个知识点必须有 ≥1 个 ASCII 图，且 ≥1 个 Mermaid 图（复杂流程）
  F9 核心讲解 句数（中文句号/分号切分）不少于 3 句
  F10 易错点 条目数 2—4 条
  F11 关键结论速记 条目数落在规范区间
  F12 README 声明的"已核对原题"清单必须与正文标注逐条一致
  F13 Markdown 结构 lint：块级元素之间必须有空行
  F14 用真实 Markdown 渲染器确认模板字段各自独立成段
  F15 文档内所有相对链接必须能从仓库根解析
  F16 HTML 产物完整性与组件完整性（防渲染器静默退化）
  F17 站点与归档里的每一个相对链接都必须真实可达（含跳转页目标）
用法： python3 scripts/validate.py [--stats]
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import topics as T  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 仓库根
DOCS = os.path.join(ROOT, ".docs")                                   # Markdown 归档
SITE = ROOT                                                          # HTML 站点就在仓库根

MERMAID_CHECKER = os.path.join(ROOT, "scripts", "check_mermaid.mjs")
NODE_DEPS_HINT = ("装依赖：npm install --prefix .tools --cache /tmp/npm-cache "
                  "--no-audit --no-fund mermaid@12.1.0 jsdom@30.1.2"
                  "（版本见 scripts/tools-package.json）；"
                  "实在离线可加 --no-mermaid 显式跳过")
PY_DEPS_HINT = ("装依赖：python3 -m venv .tools/venv && "
                ".tools/venv/bin/python -m pip install -r scripts/requirements.txt"
                "（F14 用真实 Markdown 渲染器，缺它这项校验无法进行）")
# 六段字段 → 锚点 id（契约钦定，必须与 build_html.py 的 SECS 一致，见 F22）
SEC_IDS_FOR_CHECK = [
    ("考频统计", "sec-freq"),
    ("核心讲解", "sec-core"),
    ("关键结论速记", "sec-key"),
    ("示意图", "sec-fig"),
    ("易错点", "sec-err"),
    ("真题示例", "sec-real"),
]
# F24：公式区间里的 `*` 是合法的（如 A^{*}），统计字面 `**` 前要先把公式挖掉
INLINE_MATH = re.compile(r"(?<!\$)\$([^$\n]+?)\$(?!\$)")
DISPLAY_MATH = re.compile(r"\$\$.+?\$\$", re.S)
ALLOW_NO_MERMAID = "--no-mermaid" in sys.argv
# 防止 F14 换解释器重跑时无限递归（见 render_check）
NO_REEXEC = "--no-reexec" in sys.argv

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

    # 校验每个小节的字段。科目总览是元文件；其余文件的每个 ## 小节都必须齐备 6 个模板字段
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
        # 本进程 import 失败是**确定的事实**（不是"探测不到"），所以这里直接换用
        # 仓库内的 .tools/venv 重跑自己：静默 return 会让 F14 悄悄失效，
        # 出现"校验全绿其实少跑了一项"。venv 见 scripts/requirements.txt。
        venv = os.path.join(ROOT, ".tools", "venv", "bin", "python")
        if (not NO_REEXEC and os.path.exists(venv)
                and os.path.abspath(venv) != os.path.abspath(sys.executable)):
            r = subprocess.run([venv, os.path.abspath(__file__)] + sys.argv[1:] + ["--no-reexec"],
                               capture_output=True, text=True)
            sys.stdout.write(r.stdout)
            sys.stderr.write(r.stderr)
            sys.exit(r.returncode)
        err(rel, 0, "F14", "当前解释器缺少 markdown，无法做渲染验证。%s" % PY_DEPS_HINT)
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
                # 允许三种落点：与所在 md 同目录、相对归档根、或站点里的跳转页
                cands = [os.path.join(os.path.dirname(f), target),
                         os.path.join(DOCS, target),
                         os.path.join(SITE, target + ".html")]
                if target.endswith(".md"):
                    cands.append(os.path.join(SITE, target[:-3] + ".md.html"))
                if not any(os.path.exists(c) for c in cands):
                    err(rel, 0, "F15", "相对链接解析失败（同目录 / 408/ 根均无此文件）：%s" % target)


def check_site_links():
    """F17: 站点与归档里的每一个相对链接都必须真实可达。

    为什么需要：同一段 Markdown 会在两个位置渲染（科目目录内 / 根目录合集页），
    链接深度必须按渲染位置修正；`.md` 与 `.md.html` 的落点也不同。
    这类错误只在点击时暴露，必须机器兜住。
    """
    from urllib.parse import unquote

    def visible(h):
        h = re.sub(r"<pre>.*?</pre>", "", h, flags=re.S)
        return re.sub(r'data-src="[^"]*"', "", h)

    def ok(base, target):
        t = unquote(target.split("#")[0].split("?")[0])
        if not t or t.startswith(("http", "mailto:", "javascript:", "data:", "#")):
            return True
        return os.path.exists(os.path.normpath(os.path.join(base, t)))

    for f in glob.glob(os.path.join(SITE, "**", "*.html"), recursive=True):
        d = os.path.dirname(os.path.abspath(f))
        with open(f, encoding="utf-8") as fh:
            body = visible(fh.read())
        for attr, val in re.findall(r'(href|src)="([^"]+)"', body):
            if not ok(d, val):
                err(os.path.relpath(f, ROOT), 0, "F17",
                    "链接不可达（%s）：%s" % (attr, val[:60]))
    for f in glob.glob(os.path.join(SITE, "**", "*.md.html"), recursive=True):
        d = os.path.dirname(os.path.abspath(f))
        with open(f, encoding="utf-8") as fh:
            m = re.search(r'url=([^"\'>]+)', fh.read())
        if m and not ok(d, m.group(1)):
            err(os.path.relpath(f, ROOT), 0, "F17", "跳转页目标不存在：%s" % m.group(1))
    for f in glob.glob(os.path.join(DOCS, "**", "*.md"), recursive=True):
        d = os.path.dirname(os.path.abspath(f))
        with open(f, encoding="utf-8") as fh:
            for m in re.finditer(r"\]\(([^)\s]+)\)", fh.read()):
                if "assets/" in m.group(1):
                    continue          # 示例路径（写作规范里的占位）
                if not ok(d, m.group(1)) and not ok(SITE, m.group(1)):
                    err(os.path.relpath(f, ROOT), 0, "F17",
                        "Markdown 链接不可达：%s" % m.group(1))


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


def check_shell():
    """F22: 统一外壳完整性（契约 ../PLAN-对齐与改版.md 2.3/2.4）。

    与 math2-kaoyan 共用同一份 DOM 与 class 名，因此这里校验的是**契约**，
    不是 408 自己的偏好：顶栏（品牌 + 面包屑 + 搜索）、侧栏、main、页脚
    四件必须齐全，六段锚点 id 必须齐备，首页科目卡片数必须等于科目数。

    只查「章节页 + 科目首页」：仓库根的合集/总览是另一种页面形态
    （整站合并 + README），不套用章节骨架。
    """
    shell_pages = []
    for k in T.ORDER:
        s = T.SUBJECTS[k]
        shell_pages.append(("overview", k, None,
                            os.path.join(SITE, s["dir"], "index.html")))
        for t in T.TOPICS[k]:
            shell_pages.append(("chapter", k, t[6],
                                os.path.join(SITE, s["dir"], t[6] + ".html")))

    nav_pages = 0
    for kind, k, slug, fp in shell_pages:
        s = T.SUBJECTS[k]
        rel = os.path.relpath(fp, ROOT)
        if not os.path.exists(fp):
            err(rel, 0, "F22", "外壳页面缺失（先跑 scripts/build_html.py）")
            continue
        with open(fp, encoding="utf-8") as fh:
            body = fh.read()

        # ---- 四件套 ----
        for cls, what in (("site-topbar", "顶栏"), ("site-sidebar", "侧栏"),
                          ("site-footer", "页脚")):
            if 'class="%s"' % cls not in body:
                err(rel, 0, "F22", "缺少%s（.%s）" % (what, cls))
        for cls in ("tb-brand", "tb-crumbs", "tb-sep", "tb-search"):
            if 'class="%s"' % cls not in body:
                err(rel, 0, "F22", "顶栏缺少 .%s" % cls)
        if "<main>" not in body:
            err(rel, 0, "F22", "缺少 <main>")

        # ---- site.js 钩子（契约 2.4.1-A）：这些是脚本真正查询的名字，
        #      改名等于让行为静默失效（按钮点了没反应），所以逐条强制 ----
        for cls, what in (("theme-toggle", "主题切换按钮"), ("nav-toggle", "窄屏抽屉按钮"),
                          ("to-top", "回到顶部按钮"), ("read-progress", "阅读进度条"),
                          ("sb-filter", "侧栏筛选框"), ("sb-group", "侧栏分组"),
                          ("sb-group-t", "侧栏分组标题")):
            if 'class="%s"' % cls not in body:
                err(rel, 0, "F22", "缺少 site.js 钩子 .%s（%s）" % (cls, what))
        if not re.search(r'<a id="top">', body):
            err(rel, 0, "F22", '缺少 <a id="top"></a>（页脚「回到顶部」的目标，契约 2.4.1-B.6）')

        # ---- 面包屑：≥1 项、末项 aria-current、多于一项时必须有分隔符（2.4.1-B.7）----
        crumbs = re.search(r'<nav class="tb-crumbs".*?</nav>', body, re.S)
        if crumbs:
            seg = crumbs.group(0)
            n_item = len(re.findall(r"<a [^>]*>", seg)) + seg.count('aria-current="page"')
            n_sep = seg.count('class="tb-sep"')
            if n_item < 1:
                err(rel, 0, "F22", "面包屑至少要有 1 项")
            if n_sep != n_item - 1:
                err(rel, 0, "F22", "面包屑 %d 项应有 %d 个 .tb-sep，实为 %d"
                    % (n_item, n_item - 1, n_sep))
            if seg.count('aria-current="page"') != 1:
                err(rel, 0, "F22", "面包屑应恰有 1 个 aria-current=\"page\" 标记当前页")
            if kind == "chapter" and slug:
                # 科目那一层要指回科目首页
                if not re.search(r'<a href="index\.html">', seg):
                    err(rel, 0, "F22", "面包屑缺少指向科目首页的链接")
        else:
            err(rel, 0, "F22", "面包屑结构缺失")

        # ---- 六段锚点齐备（id 与 class 同名，契约钦定） ----
        for lab, sid in SEC_IDS_FOR_CHECK:
            if 'id="%s"' % sid not in body:
                err(rel, 0, "F22", "缺少六段锚点 #%s（%s）" % (sid, lab))
            if 'class="sec %s"' % sid not in body:
                err(rel, 0, "F22", "缺少六段容器 .sec.%s（%s）" % (sid, lab))

        # ---- 章节页专属：章节导航、翻章数据、侧栏六段锚点 ----
        if kind == "chapter" and slug:
            topics = [t[6] for t in T.TOPICS[k]]
            i = topics.index(slug)
            nav = re.search(r'<nav class="chapter-nav">.*?</nav>', body, re.S)
            if not nav:
                err(rel, 0, "F22", "章节页缺少 .chapter-nav")
            else:
                seg = nav.group(0)
                want_prev = i > 0
                want_next = i + 1 < len(topics)
                if want_prev and 'class="cn-prev"' not in seg:
                    err(rel, 0, "F22", "首章之外必须有 .cn-prev")
                if want_next and 'class="cn-next"' not in seg:
                    err(rel, 0, "F22", "末章之外必须有 .cn-next")
                if not want_prev and "cn-prev" in seg:
                    err(rel, 0, "F22", "第一章不应有 .cn-prev")
                if not want_next and "cn-next" in seg:
                    err(rel, 0, "F22", "最后一章不应有 .cn-next")
                # prev/next 的 href 必须指向真实存在的同科目章节页
                for cls in ("cn-prev", "cn-next"):
                    m = re.search(r'class="%s" href="([^"]+)"' % cls, seg)
                    if m:
                        tgt = os.path.normpath(os.path.join(os.path.dirname(fp),
                                                            m.group(1).split("#")[0]))
                        if not os.path.exists(tgt):
                            err(rel, 0, "F22", "%s 指向不存在的页面：%s" % (cls, m.group(1)))
            # 键盘翻章数据必须与 .chapter-nav 的可见链接一致（契约 2.4.1-B.5）
            mb = re.search(r"<body([^>]*)>", body)
            bp = re.search(r'data-prev="([^"]*)"', mb.group(1)) if mb else None
            bn = re.search(r'data-next="([^"]*)"', mb.group(1)) if mb else None
            if mb is None or bp is None or bn is None:
                err(rel, 0, "F22", "body 缺少 data-prev/data-next（键盘翻章目标）")
            else:
                want_p = "%s.html" % topics[i - 1] if i > 0 else ""
                want_n = "%s.html" % topics[i + 1] if i + 1 < len(topics) else ""
                if bp.group(1) != want_p:
                    err(rel, 0, "F22", "body data-prev 应为 %r，实为 %r"
                        % (want_p, bp.group(1)))
                if bn.group(1) != want_n:
                    err(rel, 0, "F22", "body data-next 应为 %r，实为 %r"
                        % (want_n, bn.group(1)))
            if '<div class="tocbox">' not in body:
                err(rel, 0, "F22", "侧栏缺少当前章六段锚点容器 .tocbox")
            for lab, sid in SEC_IDS_FOR_CHECK:
                if 'class="toclink" href="#%s"' % sid not in body:
                    err(rel, 0, "F22", "侧栏六段锚点缺少 #%s（%s）" % (sid, lab))
            nav_pages += 1

    # ---- 首页科目卡片：数量必须等于科目数 ----
    idx = os.path.join(SITE, "index.html")
    if os.path.exists(idx):
        with open(idx, encoding="utf-8") as fh:
            home = fh.read()
        cards = re.findall(r'class="hs-card" href="([^"]+)"', home)
        if len(cards) != len(T.ORDER):
            err("index.html", 0, "F22",
                "首页科目卡片 %d 张，应为 %d 张（每科一张）" % (len(cards), len(T.ORDER)))
        for href in cards:
            tgt = os.path.normpath(os.path.join(SITE, href.split("#")[0]))
            if not os.path.exists(tgt):
                err("index.html", 0, "F22", "科目卡片指向不存在的页面：%s" % href)
        for k in T.ORDER:
            s = T.SUBJECTS[k]
            if 'href="%s/index.html"' % s["dir"] not in home:
                err("index.html", 0, "F22", "首页缺少科目 %s 的卡片入口" % s["name"])
        if 'class="home-subjects"' not in home:
            err("index.html", 0, "F22", "首页缺少 .home-subjects 容器")
        # 卡片必须在单页合集之前
        if home.find('class="home-subjects"') > home.find('class="kp"'):
            err("index.html", 0, "F22", "科目卡片应排在单页合集之前")
    stats["shell_nav_pages"] = nav_pages

    # ---- 跳转桩必须保持极简（契约 2.3.1：只有科目首页/章节页套完整外壳）----
    # 注意 README.html **不在此列**：契约 2.3.1 的表里写「README.html 不加外壳」，
    # 但数学二的 deploy 产物里 README.html 是带完整外壳的（site-topbar/sidebar/
    # site.js 都在），其 F22 也是对全部页面强制外壳。以实际为准，
    # 故这里只对 .md 跳转桩做"不得套壳"的负向检查。
    for fp in glob.glob(os.path.join(SITE, "*", "*.md.html")):
        rel = os.path.relpath(fp, ROOT)
        with open(fp, encoding="utf-8") as fh:
            body = fh.read()
        for cls in ("site-topbar", "site-sidebar", "chapter-nav", "assets/site.js"):
            if cls in body:
                err(rel, 0, "F22", "跳转桩不应套用完整外壳（契约 2.3.1）")
                break


def check_assets():
    """F23: 外置资源可达（assets/site.css 与 assets/site.js）。

    契约要求样式与行为外置；这两份是**手写源**（不是生成物），
    所以漏提交、改名、引用路径写错都必须在这里报出来，而不是等页面变成裸 HTML。
    """
    css = os.path.join(SITE, "assets", "site.css")
    js = os.path.join(SITE, "assets", "site.js")
    for fp, what in ((css, "样式"), (js, "行为")):
        if not os.path.exists(fp):
            err("assets/%s" % os.path.basename(fp), 0, "F23",
                "缺少外置%s文件（手写源，必须入库）" % what)
        elif os.path.getsize(fp) < 500:
            err("assets/%s" % os.path.basename(fp), 0, "F23",
                "外置%s文件过小（%d 字节），疑似被清空或截断"
                % (os.path.basename(fp), os.path.getsize(fp)))
    # 每个站点页面都必须引用它们（相对层级随页面深度变化）
    pages = []
    for k in T.ORDER:
        s = T.SUBJECTS[k]
        d = os.path.join(SITE, s["dir"])
        pages.append(os.path.join(d, "index.html"))
        for t in T.TOPICS[k]:
            pages.append(os.path.join(d, t[6] + ".html"))
    pages += [os.path.join(SITE, "index.html"), os.path.join(SITE, "README.html")]
    for fp in pages:
        if not os.path.exists(fp):
            continue
        rel = os.path.relpath(fp, ROOT)
        with open(fp, encoding="utf-8") as fh:
            body = fh.read()
        if "assets/site.css" not in body:
            err(rel, 0, "F23", "页面未引用 assets/site.css")
        if "assets/site.js" not in body:
            err(rel, 0, "F23", "页面未引用 assets/site.js")
        else:
            # 契约 2.4.1-B.4：必须在 <head> 里**同步**引入，不可 defer。
            # 主题类要在首屏绘制前定下来，defer 会闪白。
            head_seg = body[:body.find("</head>")] if "</head>" in body else ""
            m = re.search(r'<script[^>]*assets/site\.js[^>]*>', body)
            if m and m.group(0) not in head_seg:
                err(rel, 0, "F23", "assets/site.js 必须在 <head> 内引入（否则首屏闪白）")
            if m and re.search(r'\bdefer\b', m.group(0)):
                err(rel, 0, "F23", "assets/site.js 不得用 defer（主题类须在首屏前生效）")
        # 页面内不得再有内联 <style>（外置的意义就是消除每页 9 KB 冗余）
        if "<style>" in body:
            err(rel, 0, "F23", "页面仍有内联 <style>，样式未真正外置")
        # 引用的资源必须真实存在
        for m in re.finditer(r'<link rel="stylesheet" href="([^"]+)"', body):
            tgt = os.path.normpath(os.path.join(os.path.dirname(fp), m.group(1)))
            if not os.path.exists(tgt):
                err(rel, 0, "F23", "样式表不可达：%s" % m.group(1))
        for m in re.finditer(r'<script src="([^"]+)"', body):
            tgt = os.path.normpath(os.path.join(os.path.dirname(fp), m.group(1)))
            if not os.path.exists(tgt):
                err(rel, 0, "F23", "脚本不可达：%s" % m.group(1))


def check_render_leftovers():
    """F24: 渲染后不得残留字面 Markdown 记号（`**`）。

    为什么要有：`**错在…。**正确做法` 这类写法里，闭合定界符后面紧跟汉字/标点，
    按 CommonMark 的侧翼规则**无法闭合**，页面上会直接露出 `**`。这种错误在源文件里
    看起来完全正常，只有渲染出来才看得见——所以既查成品 HTML，也查内容源。

    两侧判据等价（契约 §2.4.1-D）：数学二的 F24 同样是"渲染后统计字面 `**`"。
    与本站生成器无关，是内容/渲染层面的缺陷，两个项目都可能有。
    """
    # ---- 成品 HTML：只看 <main> 内，且排除代码块 ----
    pages = [os.path.join(SITE, "index.html"), os.path.join(SITE, "README.html")]
    for k in T.ORDER:
        s = T.SUBJECTS[k]
        d = os.path.join(SITE, s["dir"])
        pages.append(os.path.join(d, "index.html"))
        for t in T.TOPICS[k]:
            pages.append(os.path.join(d, t[6] + ".html"))
    for fp in pages:
        if not os.path.exists(fp):
            continue
        rel = os.path.relpath(fp, ROOT)
        with open(fp, encoding="utf-8") as fh:
            text = fh.read()
        body = re.sub(r"<pre.*?</pre>|<code.*?</code>|<script.*?</script>|<style.*?</style>",
                      "", text, flags=re.S)
        if "<main>" in body:
            body = body[body.find("<main>"):]
        # 行内公式区间里的 `*` 是合法的（如 A^{*}）
        body = DISPLAY_MATH.sub("", body)
        body = INLINE_MATH.sub("", body)
        n = body.count("**")
        if n:
            err(rel, 0, "F24", "渲染后残留字面 `**` %d 处（加粗定界符没闭合，"
                               "页面上会直接显示星号）" % n)

    # ---- 内容源：按真实流水线渲染一遍，让写手在 build 前就看到 ----
    try:
        import markdown as _md
    except ImportError:
        return
    for f in sorted(glob.glob(os.path.join(ROOT, "parts", "*", "*.md"))):
        rel = os.path.relpath(f, ROOT)
        with open(f, encoding="utf-8") as fh:
            raw = fh.read()
        # 只检查会被渲染成正文的段落：代码围栏里的 `**` 是合法内容
        raw = re.sub(r"```.*?```", "", raw, flags=re.S)
        body = _md.markdown(raw, extensions=["tables", "fenced_code", "sane_lists"])
        body = DISPLAY_MATH.sub("", body)
        body = INLINE_MATH.sub("", body)
        n = body.count("**")
        if n:
            err(rel, 0, "F24", "内容源渲染后残留字面 `**` %d 处" % n)


def check_site_js_pin():
    """F25: assets/site.js 必须是上游的逐字复制（契约 §2.4.1-D）。

    该文件是两个项目共用的行为契约实现。文件头注记里钉了上游正文的 sha256，
    这里核对"注记之后的全部内容"是否等于该哈希——所以任何对正文的本地改动
    都会失败，逼着改动走契约而不是就地分叉。

    若同工作区存在上游文件，再额外做一次**逐字节**比对（更直接）。
    """
    fp = os.path.join(SITE, "assets", "site.js")
    if not os.path.exists(fp):
        err("assets/site.js", 0, "F25", "缺少共用行为脚本")
        return
    with open(fp, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"sha256\s*=\s*([0-9a-f]{64})", text)
    if not m:
        err("assets/site.js", 0, "F25",
            "文件头缺少上游 sha256 注记（无法证明是逐字复制）")
        return
    pinned = m.group(1)
    if "*/\n" not in text:
        err("assets/site.js", 0, "F25", "文件头注记格式异常（缺少 */ 收尾）")
        return
    body = text.split("*/\n", 1)[1]
    got = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if got != pinned:
        err("assets/site.js", 0, "F25",
            "正文与上游不一致（本地 sha256 %s…，注记 %s…）——"
            "不要就地改这个共用件，先改契约再同步两个项目" % (got[:12], pinned[:12]))
    # 同工作区能读到上游时，直接逐字节比对
    upstream = os.path.join(os.path.dirname(ROOT), "math2-kaoyan", "数学二", "assets", "site.js")
    if os.path.exists(upstream):
        with open(upstream, encoding="utf-8") as fh:
            up = fh.read()
        if up != body:
            err("assets/site.js", 0, "F25",
                "与上游 math2-kaoyan/数学二/assets/site.js 不是逐字节一致")
        stats["site_js_identical"] = 1


def check_site_js_behavior():
    """F26: 外壳脚本的行为测试（jsdom，复用数学二的 12 条断言）。

    `assets/site.js` 是共用件，光"能解析"不够——主题类、筛选、键盘翻章这些
    行为必须在真实 DOM 上跑过。测试脚本由数学二提供并带 `--site-js` 参数，
    408 直接复用它跑自己的副本（契约 §2.4.1-D 要求两边都跑通）。

    缺 node / jsdom / 测试脚本都是 error，不是跳过：否则这条门禁会静默失效。
    """
    # 优先用本仓库的副本（CI 里只有本仓库）；没有就退回同工作区的上游原件
    local = os.path.join(ROOT, "scripts", "test_site_js.mjs")
    upstream = os.path.join(os.path.dirname(ROOT), "math2-kaoyan", "数学二",
                            "scripts", "test_site_js.mjs")
    tester = local if os.path.exists(local) else (upstream if os.path.exists(upstream) else None)
    if tester is None:
        err("scripts", 0, "F26",
            "找不到外壳行为测试脚本（scripts/test_site_js.mjs）；这是 408 的复用副本，必须入库")
        return
    if shutil.which("node") is None:
        err("site.js", 0, "F26", "找不到 node，无法跑外壳行为测试")
        return
    if _node_version("jsdom") is None:
        err("site.js", 0, "F26", "缺少 jsdom（见 scripts/tools-package.json）")
        return
    site_js = os.path.join(SITE, "assets", "site.js")
    try:
        r = subprocess.run(["node", tester, "--site-js", site_js, "--strict"],
                           cwd=ROOT, capture_output=True, text=True, timeout=300)
    except Exception as e:                                   # noqa: BLE001
        err("site.js", 0, "F26", "调用行为测试失败：%s" % e)
        return
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()
        err("site.js", 0, "F26", "外壳行为测试未通过：%s" % (tail[-1] if tail else "")[:200])
        return
    # 人读摘要走 stderr（JSON 走 stdout），两处都找一下
    m = re.search(r"(\d+)/(\d+)\s*通过", (r.stderr or "") + (r.stdout or ""))
    if m:
        stats["site_js_tests"] = int(m.group(1))
        stats["site_js_total"] = int(m.group(2))
    else:
        err("site.js", 0, "F26", "行为测试未产出可解析的通过计数，无法确认真的跑了")


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
        # 内层循环也要有图形校验：写手在这里就该看到自己刚写坏的 mermaid，
        # 而不是等 build 之后才暴露。所以 --parts 扫 parts/ 而不是 .docs/。
        run_mermaid_parser(os.path.join(ROOT, "parts"))
        # F24 同样在内容源阶段就跑：写手改完 parts 立刻能看到没闭合的 `**`
        check_render_leftovers()
        return report("parts 半成品校验报告", parts_mode=True)

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
    check_site_links()
    check_html()
    check_shell()
    check_assets()
    check_render_leftovers()
    check_site_js_pin()
    check_site_js_behavior()
    run_mermaid_parser(DOCS)
    return report("408 复习资料校验报告")


def _node_version(name):
    p = os.path.join(ROOT, ".tools", "node_modules", name, "package.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("version")
    except Exception:                                        # noqa: BLE001
        return None


def _bundled_mermaid_version():
    """从站点内置 mermaid.min.js 抠出版本号（须通读全文，见 run_all.py 的说明）。"""
    try:
        with open(os.path.join(ROOT, "mermaid.min.js"), encoding="utf-8",
                  errors="ignore") as f:
            text = f.read()
    except Exception:                                        # noqa: BLE001
        return None
    best = None
    for m in re.finditer(r'version\s*:\s*"(\d+)\.(\d+)\.(\d+)"', text):
        v = m.group(0).split('"')[1]
        if v == "0.0.0":                                     # 无关组件的占位版本
            continue
        if best is None or tuple(map(int, v.split("."))) > tuple(map(int, best.split("."))):
            best = v
    return best


def check_node_deps():
    """先决条件：.tools 下的 mermaid/jsdom 是否就位，且版本与站点运行时一致。

    返回 True/False。版本漂移必须报出来：F3 用 `mermaid` 解析、站点用仓库根的
    `mermaid.min.js` 渲染——两者版本不同，就会出现「校验通过但页面渲染不出来」
    这种最难查的情况。
    """
    problems = []
    for name in ("mermaid", "jsdom"):
        if _node_version(name) is None:
            problems.append("缺少 %s" % name)
    have = _node_version("mermaid")
    bundled = _bundled_mermaid_version()
    if have and bundled and have != bundled:
        problems.append("mermaid 与站点内置运行时不一致：.tools 是 %s，"
                        "仓库根 mermaid.min.js 是 %s" % (have, bundled))
    if problems:
        err("scripts", 0, "F3", "Node 依赖不可用：%s。%s" % ("；".join(problems), NODE_DEPS_HINT))
        return False
    return True


def run_mermaid_parser(scan_dir):
    """F3 的真实解析器层：调用 node + 官方 mermaid parse()。

    这里的**每一条失败路径都必须是 error 而不是 warning**：解析器不在、node 不在、
    装不起来、返回码非 0、一块图都没扫到——这些情况都会让 F3 退化成「永远通过」，
    而页面上的图会静默变空白。宁可整个校验失败，也不许它假装检查过了。
    真要离线跳过，必须显式加 `--no-mermaid`（命令行会留下痕迹）。

    `scan_dir` 跟着模式走：`--parts` 时扫内容源 `parts/`，成品模式扫 `.docs/`。
    否则写手在「改 parts → validate --parts」的内层循环里看不到自己刚写坏的
    mermaid，要等 build 之后才暴露——那就等于内层循环没有图形校验。
    """
    if ALLOW_NO_MERMAID:
        warn("mermaid", 0, "F3", "已按 --no-mermaid 跳过真实解析（命令行显式要求）")
        return
    if not os.path.exists(MERMAID_CHECKER):
        err("scripts", 0, "F3", "找不到 mermaid 解析器脚本 scripts/check_mermaid.mjs")
        return
    if shutil.which("node") is None:
        err("mermaid", 0, "F3", "找不到 node 可执行文件，无法做真实解析。%s" % NODE_DEPS_HINT)
        return
    if not check_node_deps():
        return
    try:
        r = subprocess.run(["node", MERMAID_CHECKER, "--content", scan_dir],
                           cwd=ROOT, capture_output=True, text=True, timeout=900)
    except Exception as e:                                   # noqa: BLE001
        err("mermaid", 0, "F3", "调用 mermaid 解析器失败：%s" % e)
        return
    try:
        data = json.loads((r.stdout or "").strip().splitlines()[-1])
    except Exception:                                        # noqa: BLE001
        err("mermaid", 0, "F3",
            "mermaid 解析器未产出 JSON（返回码 %d）：%s%s"
            % (r.returncode, (r.stderr or r.stdout or "")[-200:], NODE_DEPS_HINT))
        return
    if data.get("fatal"):
        err("mermaid", 0, "F3", "mermaid 解析器无法运行：%s" % str(data["fatal"])[:200])
        return
    if r.returncode != 0:
        err("mermaid", 0, "F3", "mermaid 解析器返回码 %d" % r.returncode)
        return
    stats["mermaid_parsed"] = data.get("ok", 0)
    stats["mermaid_blocks"] = data.get("total", 0)
    for f in data.get("failed", []):
        err(os.path.relpath(f["file"], ROOT), f.get("line", 0), "F3",
            "mermaid 真实解析器拒绝：%s" % str(f.get("error", ""))[:200])
    if data.get("total", 0) == 0:
        err("mermaid", 0, "F3",
            "在 %s 下没有任何 mermaid 图被解析——扫描范围为空，等于 F3 没生效"
            % os.path.relpath(scan_dir, ROOT))



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


def report(title, parts_mode=False):
    print("=" * 74)
    print(title)
    print("=" * 74)
    for k, v in sorted(per_file.items()):
        print("  %-46s 知识点 %2d | ASCII 图 %2d | Mermaid %2d | %6d 字"
              % (k, v["sections"], v["ascii"], v["mermaid"], v["chars"]))
    print("-" * 74)
    # 「知识点」的口径随模式走，两种模式必须各按各的算，否则会出现
    # 「逐文件说知识点 1、汇总说知识点 0」这种自相矛盾：
    #   成品模式：知识点 = 标题以 [高频] 结尾的小节（= 26）；
    #             其余 ## 小节是四科总览里的元小节，混进去会把 26 报成 64。
    #   parts 模式：一个半成品文件就是一个知识点，且文件里没有 [高频] 标题
    #             （高频标记由 build.py 注入），所以按文件数算。
    if parts_mode:
        kp = len(per_file)
    else:
        kp = stats["hot"]
    print("  文件 %d 个 | 知识点 %d | 小节 %d | ASCII 图 %d | Mermaid 图 %d | 总计 %d 字"
          % (len(per_file), kp, stats["sections"], stats["ascii"], stats["mermaid"],
             stats["chars"]))
    if not parts_mode:
        print("  高频标记 %d 个 | 真题原题 %d 道" % (stats["hot"], stats.get("orig", 0)))
    if stats.get("mermaid_blocks"):
        print("  Mermaid 真实解析 %d/%d 通过" % (stats.get("mermaid_parsed", 0),
                                                 stats["mermaid_blocks"]))
    if stats.get("site_js_tests"):
        print("  外壳行为测试 %d/%d 通过（jsdom，复用数学二）"
              % (stats["site_js_tests"], stats.get("site_js_total", 0)))
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
