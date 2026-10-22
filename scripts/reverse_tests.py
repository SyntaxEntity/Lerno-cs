#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验器的反向测试：**每条规则都故意造一个反例，确认它真的会报错**。

为什么必须做
------------
不做反向测试的校验等于自我安慰。本站就吃过两次亏：
  · `check_mermaid.mjs` 的扫描目录指向重组前的死路径 `408/`，脚本一跑就崩，
    而**没有任何地方调用它**，于是"52 张图的真实校验"从来没跑过；
  · F24 首版用了当前解释器的 markdown（本地 3.10.3 vs CI 3.11.1），
    本地全绿、CI 红。
两次的共同点是"校验项看起来在跑，其实在自欺"。本脚本把"规则真的能失败"这件事
固化成可复现的产物——当年是手工注入反例、只在报告里写了一句，下一个人无法复跑。

用法
----
    python3 scripts/reverse_tests.py            # 跑全部反向测试
    python3 scripts/reverse_tests.py -v         # 打印每条反例触发的报错细节
    python3 scripts/reverse_tests.py --list     # 只列出覆盖了哪些规则

设计
----
每个用例是 `case(code, 名称, 目标文件, 变换函数, 期望关键字, mode, mermaid)`：
读原文 → 写坏文 → 跑校验 → **无论成败都还原**。
判据是"注入之后**新出现**的、属于该规则码的报错"——见 baseline_errors 的说明。

覆盖完整性由 `validate.py` 的 **F27 元校验**强制（规则集合 ≡ 覆盖集合，
用集合比较、不假设编号连续）。**新增规则却不加反例，门禁会红。**
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOCS = os.path.join(ROOT, ".docs")
PARTS = os.path.join(ROOT, "parts")
SITE = ROOT

# 必须用**带 markdown 的解释器**跑校验器：否则 F14/F24 的内容源层会失效，
# 反向测试就会把"依赖缺失"误判成"规则失效"。优先用仓库自带 venv（锁定版本）。
_VENV = os.path.join(ROOT, ".tools", "venv", "bin", "python")
PY = _VENV if os.path.exists(_VENV) else sys.executable
VALIDATE = os.path.join(HERE, "validate.py")
CHECKER = os.path.join(HERE, "check_mermaid.mjs")

CASES = []
ERROR_LINE = re.compile(r"\[F\d+\]")
_BASELINE = {}


def case(code, name, target, mutate, expect_kw=None, mode="full", mermaid=False,
         expect_pass=False):
    """mermaid=True 的用例会**不跳过**真实解析器跑校验（用于验 F3 的解析器层）。

    其余用例一律带 `--no-mermaid`：不是为了省事，而是因为若反例破坏了围栏闭合，
    解析器层的报错会**盖过**被测规则本来要报的那个错，反而看不出规则是否生效。

    expect_pass=True 是**否定用例**：注入后该规则**不得**报错。用来钉住"不许误报"——
    例如 F29 必须先剥注释再数花括号，若退化成朴素计数，一份完全正确的 CSS
    （注释里有 `{}`）就会被判错。这类用例与"必须报错"同等重要，所以显式建模，
    而不是塞进 expect_kw 里靠约定。
    """
    CASES.append((code, name, target, mutate, expect_kw, mode, mermaid, expect_pass))


def run_validate(mode, allow_mermaid=False):
    cmd = [PY, VALIDATE] + (["--parts"] if mode == "parts" else [])
    if not allow_mermaid:
        cmd.append("--no-mermaid")
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900)
    return r.stdout + r.stderr


def baseline_errors(mode, allow_mermaid):
    """未注入反例时，该模式下已有的报错行集合。

    **为什么必须做基线差分**：若判据是"输出里出现 [Fxx]"，那么一条本来就有既存
    报错的规则，即使反例完全没生效也会"通过"——那是"校验器是摆设"的另一种形态。
    只认**注入之后新出现**的报错行，用例就不可能蒙对。
    """
    key = (mode, allow_mermaid)
    if key not in _BASELINE:
        out = run_validate(mode, allow_mermaid=allow_mermaid)
        _BASELINE[key] = {ln.strip() for ln in out.split("\n") if ERROR_LINE.search(ln)}
        print("  · 基线（%s%s）：已有 %d 条报错"
              % (mode, "，含真实解析器" if allow_mermaid else "", len(_BASELINE[key])))
    return _BASELINE[key]


# ---------------------------------------------------------------------------
# 目标文件
# ---------------------------------------------------------------------------
D01 = os.path.join(DOCS, "数据结构", "01-线性表.md")
D04 = os.path.join(DOCS, "数据结构", "04-树与二叉树.md")
DOS = os.path.join(DOCS, "操作系统", "01-操作系统概述与运行机制.md")
P01 = os.path.join(PARTS, "ds", "01-线性表.md")
C01H = os.path.join(SITE, "数据结构", "01-线性表.html")
C04H = os.path.join(SITE, "数据结构", "04-树与二叉树.html")
IDXH = os.path.join(SITE, "index.html")
SUBH = os.path.join(SITE, "数据结构", "index.html")
STUB = os.path.join(SITE, "数据结构", "01-线性表.md.html")
READMEH = os.path.join(SITE, "README.html")
SITEJS = os.path.join(SITE, "assets", "site.js")
SITECSS = os.path.join(SITE, "assets", "site.css")
WF = os.path.join(ROOT, ".github", "workflows", "pages.yml")
TOTAL = os.path.join(DOCS, "00-总览.md")

FENCE = "```"
FIELD = "**核心讲解**"
FREQ = "**考频统计**"


def _sub(old, new, count=1):
    """生成一个"把 old 换成 new"的变换函数。"""
    def f(text):
        return text.replace(old, new, count)
    return f


# ---------------------------------------------------------------------------
# F0：章节文件 / 半成品文件必须存在且登记
#   —— 这一条无法用"改内容"触发（它针对文件是否存在），故用 mode="parts" 下
#      临时改名一个半成品文件来实现；见 CASE_FILES 机制（下方执行器支持）。
# ---------------------------------------------------------------------------
case("F0", "parts 半成品文件缺失", P01, lambda t: t, mode="parts", expect_kw="缺少半成品")

# F1：六段模板字段齐全且顺序正确
case("F1", "改坏「关键结论速记」字段标签", D01,
     lambda t: t.replace("**关键结论速记**：", "**关键结论速记XX**："), expect_kw="关键结论速记")

# F2：考频统计行必须与 meta.py 逐字一致
case("F2", "改坏考频统计行", D01,
     lambda t: re.sub(r"^\*\*考频统计\*\*.*$",
                      "**考频统计**：考察次数 999 次（篡改）", t, count=1, flags=re.M),
     expect_kw="考频统计与权威数据不一致")

# F3：代码围栏闭合 + mermaid 真解析（两层）
case("F3", "mermaid 节点文本含未加引号的圆括号", D01,
     lambda t: t.replace("flowchart TD", 'flowchart TD\n    X[未加引号(的括号)]', 1),
     expect_kw="圆括号")
case("F3", "mermaid 真实解析器拒绝该图", D01,
     lambda t: t.replace("flowchart TD", "flowchart TD\n    A -->|未闭合", 1),
     expect_kw=None, mermaid=True)

# F4：禁止占位符
case("F4", "正文出现 TODO 占位符", P01,
     lambda t: t.replace("线性表", "线性表 TODO", 1), mode="parts", expect_kw="占位符")

# F5：ASCII 图不得含全角/制表符
case("F5", "ASCII 图混入全角字符", P01,
     lambda t: t.replace("```text", "```text\n＋ ＋ ＋", 1), mode="parts", expect_kw="全角")

# F6：真题年份必须落在 2009—2025
case("F6", "真题年份超出区间", P01,
     lambda t: re.sub(r"(\*\*)(19|20)\d{2}( 年)", r"\g<1>1999\g<3>", t, count=1),
     mode="parts", expect_kw="超出")

# F7：[高频] 必须出现在小节标题
case("F7", "小节标题去掉 [高频]", D01,
     lambda t: t.replace("## 线性表 [高频]", "## 线性表", 1), expect_kw="高频")

# F8：每个知识点必须同时有 ASCII 图与 Mermaid 图
case("F8", "删掉全部 mermaid 图", D01,
     lambda t: re.sub(r"```mermaid.*?```", "", t, flags=re.S), expect_kw="Mermaid")

# F9：核心讲解句数下限
case("F9", "核心讲解只剩一句话", P01,
     lambda t: re.sub(r"(# 核心讲解\n)(.*?)(\n# )", r"\1短句。\3", t, flags=re.S),
     mode="parts", expect_kw="句")

# F10：易错点条数区间（下限 2 条）
def _drop_items(header, keep=None):
    """把 `header` 段落下的 `- ` 条目删到只剩 keep 条（keep=0 表示全删）。

    用**按行处理**而不是正则：正文里有中文弯引号、反引号、括号，正则很容易
    匹配不到（第一版就在 F10/F11 上栽了：表现为"反例未改变内容"被跳过，
    那不是规则失效，是用例写错）。
    """
    def f(text):
        lines = text.split("\n")
        out, i, hit = [], 0, 0
        while i < len(lines):
            out.append(lines[i])
            if lines[i].strip() == header:
                i += 1
                items = []
                # ⚠️ 标题与首条之间**有空行**（本项目正文都是这个形状）。早期版本
                #    直接从标题后收 `- ` 行，于是一条都收不到、变换后原文没变，
                #    用例被当成"失效"跳过——不是规则坏，是用例坏。空行必须跳过。
                while i < len(lines):
                    if not lines[i].strip():
                        i += 1
                        continue
                    if lines[i].startswith("- "):
                        items.append(lines[i])
                        i += 1
                        continue
                    break
                out.extend(items if keep is None else items[:keep])
                hit += 1
                continue
            i += 1
        return "\n".join(out) if hit else text
    return f


case("F10", "易错点只剩一条", P01,
     _drop_items("# 易错点", keep=1), mode="parts", expect_kw="易错点")

# F11：关键结论速记条数区间
case("F11", "关键结论速记清空", P01,
     _drop_items("# 关键结论速记", keep=0), mode="parts",
     expect_kw="关键结论速记")

# F12：README 声明的原题清单与正文标注双向一致
case("F12", "总览里删掉一条已核对原题声明", TOTAL,
     lambda t: t.replace("| `2014` 第 `41` 题 |", "| `2014` 第 `99` 题 |", 1),
     expect_kw="未在 README 声明")

# F13：块级元素之间必须有空行（判据是"标题/表格/引用/围栏前后"）
case("F13", "标题紧贴上一段（缺空行）", D01,
     lambda t: t.replace("。\n\n**关键结论速记**", "。\n## 反例小节\n**关键结论速记**", 1),
     expect_kw="空行")

# F14：真实渲染器确认六段各自独立成段
#   触发条件是"标签出现在段落**中间**"，所以标签前后的空行都要去掉，
#   否则它仍会独立成段（只去前面那一处不够——第一版就是这么错的）。
case("F14", "字段标签被上一段吞并", D01,
     lambda t: t.replace("\n\n**关键结论速记**：\n\n", "\n**关键结论速记**：\n", 1),
     expect_kw="并入上一段")

# F15：文档内相对链接必须可解析
case("F15", "总览里改成不存在的相对链接", TOTAL,
     lambda t: t.replace("](数据结构/01-线性表.md)", "](数据结构/99-不存在.md)", 1),
     expect_kw="解析失败")

# F16：HTML 产物完整性与组件完整性
case("F16", "章节页删掉结论卡组件", C01H,
     lambda t: t.replace('<ul class="facts">', '<ul class="factsXX">', 1),
     expect_kw="缺少组件")

# F17：站点与归档的每个相对链接真实可达
case("F17", "章节页改出死链", C01H,
     lambda t: t.replace('href="02-顺序表与链表.html"', 'href="02-不存在.html"', 1),
     expect_kw="不可达")

# F22：统一外壳完整性（顶栏/侧栏/页脚/六段锚点/翻章数据/首页卡片）
case("F22", "删掉顶栏", C01H,
     lambda t: t.replace('<header class="site-topbar">', '<header class="x">', 1),
     expect_kw="顶栏")
case("F22", "删掉六段锚点 sec-err", C01H,
     lambda t: t.replace('id="sec-err"', 'id="sec-XXX"', 1), expect_kw="sec-err")
case("F22", "site.js 钩子改名（主题按钮）", C01H,
     lambda t: t.replace('class="theme-toggle"', 'class="theme-toggleXX"', 1),
     expect_kw="theme-toggle")
case("F22", "body 翻章数据与可见链接不一致", C04H,
     lambda t: re.sub(r'data-next="[^"]*"', 'data-next="99-错.html"', t, count=1),
     expect_kw="data-next")
case("F22", "首页科目卡片数量不对", IDXH,
     lambda t: re.sub(r'<a class="hs-card"', '<a class="hs-cardXX"', t, count=1),
     expect_kw="科目卡片")

# F23：外置资源可达（存在 / 被引用 / 无内联样式 / head 内且不 defer）
case("F23", "页面未引用 site.css", C01H,
     lambda t: t.replace('<link rel="stylesheet" href="../assets/site.css">', '', 1),
     expect_kw="site.css")
case("F23", "site.js 改用 defer", C01H,
     lambda t: t.replace('<script src="../assets/site.js">',
                         '<script src="../assets/site.js" defer>', 1),
     expect_kw="defer")
case("F23", "页面插入内联 <style>", C01H,
     lambda t: t.replace("<body", "<style>body{color:red}</style><body", 1),
     expect_kw="内联")

# F24：渲染后不得残留字面 `**`
case("F24", "成品 HTML 露出字面 **", C01H,
     lambda t: t.replace("<h1>线性表</h1>", "<h1>线性表</h1><p>未闭合**加粗。</p>", 1),
     expect_kw="字面")

# F25：assets/site.js 必须是上游的逐字复制
case("F25", "就地改共用件正文", SITEJS,
     lambda t: t.replace("kaoyan-theme", "408-theme", 1), expect_kw="上游")

# F26：外壳行为测试（jsdom 12 条）
case("F26", "破坏 site.js 的主题键，行为测试应失败", SITEJS,
     lambda t: t.replace("var THEME_KEY = 'kaoyan-theme';",
                         "var THEME_KEY = 'nope-theme';", 1),
     expect_kw=None)

# F27：元校验（规则集合 ≡ 覆盖集合 + 受检数 > 0）
#
# 反例怎么造（这里有**自指**的坑，值得写清楚）：
#   F27 校验的对象正是本文件，所以"删掉一条已有用例"会让 F27 在**正常情况下也报错**
#   ——基线里已经含了 F27 的报错，差集为空，用例反而显示"未报错"。
#   更阴的是：若替换串里写出完整字面量，`coverage_codes()` 的正则会扫到**本文件
#   自己这条替换串**，把它当成一条"真用例"——于是被删掉的那条规则仍显示"已覆盖"，
#   "删掉用例要报错"这件事**永远测不出来**（本项目真踩过：F7 一直假通过）。
#   所以：① 目标改 validate.py 来造"漏覆盖"；② 替换串一律用拼接绕开正则。
_DELETE_F7 = 'case(' + '"F7",'
_GHOST = 'case(' + '"F99",'
case("F27", "规则集合里多出一条没被覆盖的规则", VALIDATE,
     lambda t: t.replace('err("parts/%s" % key, 0, "F0"',
                         'err("parts/%s" % key, 0, "F98"', 1),
     expect_kw="没有任何反向测试覆盖")
case("F27", "反向测试引用了不存在的规则", os.path.abspath(__file__),
     lambda t: t.replace(_DELETE_F7, _GHOST, 1), expect_kw="不存在的规则")

# F29：site.css 语法自检
#   注意反例都注入在 CSS 的**真实代码区**（不能落在注释里）——F29 会先剥注释，
#   落在注释里的坏字符是"合法"的，用例会假失败。
SITECSS = os.path.join(SITE, "assets", "site.css")
case("F29", "花括号少一个（吃掉后续规则）", SITECSS,
     lambda t: t.replace(".site-topbar{", ".site-topbar ", 1),
     expect_kw="未配平")
case("F29", "选择器以裸 `-` 结尾", SITECSS,
     lambda t: t.replace(".site-topbar{", ".site-topbar-{", 1),
     expect_kw="裸 `-`")
case("F29", "注释里的 {} 不得误判（否定用例：应保持通过）", SITECSS,
     lambda t: t.replace("/* ---------- 基础元素 ---------- */",
                         "/* 说明：示例 .foo{bar} 与 \"x{y}\" 都合法 */\n"
                         "/* ---------- 基础元素 ---------- */", 1),
     expect_pass=True)
case("F29", "@media 块未闭合", SITECSS,
     lambda t: t.replace("@media (max-width:1080px){", "@media (max-width:1080px)", 1),
     expect_kw="配平")

# F28：文档/CI 不得硬编码规则范围
case("F28", "README 写死规则范围", os.path.join(ROOT, "README.md"),
     lambda t: t + "\n\n本仓库校验覆盖 F1—F26。\n", expect_kw="不得硬编码规则范围")

# F30：题库源完整性（parts/quiz/*.json）
#   反例注入在**真实题目**上，不是 pending——pending 走的是另一条校验路径。
QUIZ_DS = os.path.join(PARTS, "quiz", "ds.json")
QUIZ_JS = os.path.join(SITE, "assets", "quiz-data.js")
case("F30", "答案下标越界", QUIZ_DS,
     lambda t: t.replace('"answer": 0', '"answer": 9', 1),
     expect_kw="答案下标越界")

# F31：题库产物一致性（源哈希 / 条数 / id 集合 / 题目内容，共 4 项）
case("F31", "产物正文被手改（内容与源不一致）", QUIZ_JS,
     lambda t: t.replace('"answer":0', '"answer":1', 1),
     expect_kw="产物题目内容与源不一致")
case("F31", "产物头部源哈希被改", QUIZ_JS,
     lambda t: t.replace("sourceSha256 = ", "sourceSha256 = 0", 1),
     expect_kw="源哈希不一致")

# F32：练习页行为测试（jsdom）
#   删掉「练习模式作答后写状态」这一行：页面看起来还能点、还能看解析，但统计/错题/
#   掌握度全部不再更新——正是"看起来能跑、其实坏了"的典型，必须被行为测试抓住。
PRACTICEJS = os.path.join(SITE, "assets", "practice.js")
case("F32", "删掉练习判分记录（闭环失效）", PRACTICEJS,
     lambda t: t.replace("recordAnswer(q, i, 'practice');", "", 1),
     expect_kw="练习行为测试未通过")


# ---------------------------------------------------------------------------
# 执行器
# ---------------------------------------------------------------------------
def _prepare(code, target, mutate):
    """返回 (还原函数, 改坏后的文本 or None)。

    F0 针对"文件不存在"，改内容触发不了，故用**临时改名**来造反例。
    """
    if code == "F0":
        tmp = target + ".reversetest-bak"
        os.rename(target, tmp)

        def restore():
            if os.path.exists(tmp):
                os.rename(tmp, target)
        return restore, None
    original = open(target, encoding="utf-8").read()

    def restore():
        with open(target, "w", encoding="utf-8") as f:
            f.write(original)
    return restore, mutate(original)


def main():
    verbose = "-v" in sys.argv
    if "--list" in sys.argv:
        rules = sorted({c for c, *_ in CASES}, key=lambda x: int(x[1:]))
        print("反向测试覆盖 %d 条规则：%s" % (len(rules), "、".join(rules)))
        return 0

    print("=" * 78)
    print("校验器反向测试：每条规则注入一个反例，确认它真的会报错")
    print("=" * 78)
    print("使用解释器：%s" % PY)
    passed = failed = 0
    covered = set()
    for code, name, target, mutate, _kw, mode, mermaid, expect_pass in CASES:
        rel = os.path.relpath(target, ROOT)
        if not os.path.exists(target):
            print("  ? %-5s %-40s 跳过（目标文件不存在：%s）" % (code, name, rel))
            failed += 1
            continue
        try:
            # ⚠️ 基线必须在**注入之前**取：若写在注入之后，基线里已经含了本用例
            # 注入的那条报错，差集恒为空、所有用例都会显示"未报错"。
            base = baseline_errors(mode, mermaid)
            original = (open(target, encoding="utf-8").read()
                        if code != "F0" else None)
            restore, broken = _prepare(code, target, mutate)
            if broken is not None and broken == original:
                print("  ? %-5s %-40s 跳过（反例未改变内容，用例失效）" % (code, name))
                failed += 1
                continue
            if broken is not None:
                with open(target, "w", encoding="utf-8") as f:
                    f.write(broken)
            out = run_validate(mode, allow_mermaid=mermaid)
            fresh = {ln.strip() for ln in out.split("\n") if ERROR_LINE.search(ln)} - base
            hit = [ln for ln in fresh if ("[%s]" % code) in ln]
            if expect_pass:
                # 否定用例：注入后该规则**不得**报错
                if hit:
                    failed += 1
                    print("  ✗ %-5s %-40s **误报（该规则本不该报错）**" % (code, name))
                else:
                    passed += 1
                    covered.add(code)
                    print("  ✓ %-5s %-40s 未误报" % (code, name))
                continue
            if hit:
                passed += 1
                covered.add(code)
                print("  ✓ %-5s %-40s 已报错" % (code, name))
                if verbose:
                    print("        " + hit[0][:150])
            else:
                failed += 1
                print("  ✗ %-5s %-40s **未报错（校验器失效！）**" % (code, name))
        finally:
            restore()
    print("-" * 78)
    print("  反向测试：%d 条通过 / %d 条用例，%d 条失败" % (passed, len(CASES), failed))
    print("  覆盖规则 %d 条：%s" % (len(covered),
                                   "、".join(sorted(covered, key=lambda x: int(x[1:])))))
    print("=" * 78)
    if failed:
        print("✗ 有校验规则未能被反例触发——这些规则实际处于失效状态，必须修。")
        return 1
    print("✓ 每条规则都能被反例触发（校验器确实在工作）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
