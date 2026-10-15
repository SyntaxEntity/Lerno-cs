#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 parts/<科目>/<slug>.md 的半成品内容组装为最终 Markdown 资料。

职责划分（保证全局一致性）：
  - 模板骨架（**考频统计** 行、**核心讲解** 标题、**示意图** 标题等）由本脚本生成；
  - 考频数据来自 scripts/meta.py（唯一数据源），作者只写内容不写数字；
  - 作者写 parts/<slug>.md，格式见 PARTS_FORMAT。

parts 文件格式（顺序固定）：
  # 核心讲解
  <3—8 句）
  # 关键结论速记
  - `公式/结论` —— 一句话说明（3—6 条）
  # 示意图
  <text 代码块 / mermaid 代码块，至少各一，可交错>
  # 易错点
  - 2—4 条
  # 真题示例
  **20XX 年 408 第 N 题（选择题/综合应用题，X 分）**
  题干…
  > 解析：…
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meta as T  # noqa: E402
import normalize_md as NM  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 仓库根
DOCS = os.path.join(ROOT, ".docs")                                   # Markdown 归档（四科目录 + README）

BANNER = "> 本资料为速成复习用途：**考频数据为基于 2009—2025 年真题的公开考频表统计整理，非官方发布**，\n" \
         "> 用于确定复习优先级，不作为命题预测。数据口径与来源见 `README.md`。"

# ---------------------------------------------------------------------------
# 各科目卷首说明（数据来自官方大纲与试卷结构）
# ---------------------------------------------------------------------------
FRONT = {
    "ds": """## 本科目在 408 中的位置

| 项目 | 内容 |
| --- | --- |
| 分值 | **45 分 / 150 分**（占 30%） |
| 单选题 | {choice} |
| 综合应用题 | {comprehensive} |
| 命题特点 | 选择题重"过程推演"（出栈序列、遍历序列、判定树）；大题重"算法设计 + 复杂度分析"，41 题常为树、42 题常为图 |

**复习优先级（按分值 × 稳定性排序）**：树与二叉树 → 图 → 排序 → 查找 → 栈与队列 → 线性表。
其中 **树、图两章合计约 30 分**，是本科目绝对核心；线性表独立命题少，但作为链表代码基础必须熟练。
""",
    "co": """## 本科目在 408 中的位置

| 项目 | 内容 |
| --- | --- |
| 分值 | **45 分 / 150 分**（占 30%） |
| 单选题 | {choice} |
| 综合应用题 | {comprehensive} |
| 命题特点 | 选择题重"位级/字节级计算"（补码、IEEE 754、Cache 标记、总线带宽）；大题重"地址划分 + 数据通路/流水线时空图" |

**复习优先级**：存储系统 → 中央处理器 → 数据表示与运算 → 指令系统 → 输入输出系统 → 总线。
**存储系统与 CPU 两章合计约 40 分**；总线章节分值最低但公式固定，属于"必拿分"。
""",
    "os": """## 本科目在 408 中的位置

| 项目 | 内容 |
| --- | --- |
| 分值 | **35 分 / 150 分**（占 23.3%） |
| 单选题 | {choice} |
| 综合应用题 | {comprehensive} |
| 命题特点 | 45 题几乎固定为 **PV 操作（同步互斥）**；46 题常为 **页表/地址翻译/页面置换 + 文件系统容量计算**；选择题重概念辨析与小型计算 |

**复习优先级**：内存管理 → 同步与互斥 → 进程与线程 → 处理机调度与死锁 → 文件管理 → 输入输出管理 → 概述。
**内存管理 + 同步互斥两章合计约 16 分**，且大题命中率最高，必须做到"闭卷可推导"。
""",
    "net": """## 本科目在 408 中的位置

| 项目 | 内容 |
| --- | --- |
| 分值 | **25 分 / 150 分**（占 16.7%），四科中最低但**性价比最高**（考点集中、公式固定） |
| 单选题 | {choice} |
| 综合应用题 | {comprehensive} |
| 命题特点 | 47 题常为"IP 分片 / 子网划分与路由聚合 / TCP 拥塞窗口与吞吐量"计算；选择题重层次归属与协议细节 |

**复习优先级**：网络层 → 传输层 → 数据链路层 → 应用层 → 物理层 → 体系结构。
**网络层 + 传输层合计约 13 分**，且计算题模板化程度最高，是本资料中"投入产出比"最高的一章。
""",
}

QUICK = """## 使用说明（30 秒读完）

1. **先看 `[高频]` 标记**：每节标题带 `[高频]` 的是历年反复命题的考点，时间紧张时只看这些。
2. **每节固定六段式**：考频统计 → 核心讲解 → 关键结论速记 → 示意图 → 易错点 → 真题示例，可直接跳跃到你缺的那一段。
3. **图形约定**：`text` 代码块为 **ASCII 图**（用于结构布局、位域划分、地址格式）；`mermaid` 代码块为 **流程图/状态机**（用于算法流程、协议交互、状态转换）。
4. **考频口径**：统计区间 2009—2025 年共 17 套真题；"考察次数"按题次计，一道综合题串联多个考点时各自计 1 次。
5. **自检方式**：本资料由脚本生成，`python3 scripts/validate.py` 会校验模板完整性、考频数字一致性、ASCII 图对齐与真题年份合法性。

""" + BANNER + "\n"


def parse_partial(path):
    """解析作者提交的 parts 文件，返回各段内容。"""
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    segs = {}
    cur = None
    for ln in lines:
        m = re.match(r"^# (\S.*?)\s*$", ln)
        if m and not ln.startswith("## "):
            cur = m.group(1)
            segs[cur] = []
            continue
        if cur is not None:
            segs[cur].append(ln)
    return {k: "\n".join(v).strip() for k, v in segs.items()}


def build_topic(subject_key, topic, partial):
    name, times, years, ratio, qtype, hot, slug = topic
    need = ["核心讲解", "关键结论速记", "示意图", "易错点", "真题示例"]
    for k in need:
        if k not in partial or not partial[k]:
            raise SystemExit("[%s/%s] parts 缺少段落：%s" % (subject_key, slug, k))

    title = "## %s %s" % (name, "[高频]" if hot else "")
    # 每个字段之间用空行分隔：Markdown 中单换行不换行，若不留空行五个字段会糊成一段
    out = [
        title.strip(), "",
        T.freq_line(subject_key, name), "",
        "**核心讲解**：", "", partial["核心讲解"], "",
        "**关键结论速记**：", "", partial["关键结论速记"], "",
        "**示意图**：", "", partial["示意图"], "",
        "**易错点**：", "", partial["易错点"], "",
        "**真题示例**：", "", partial["真题示例"], "",
        "---", "",
    ]
    return "\n".join(out)


def subject_index(subject_key, topics):
    sub = T.SUBJECTS[subject_key]
    rows = ["| # | 知识点 | 考察次数 | 分值占比 | 高频 |", "| --- | --- | --- | --- | --- |"]
    for i, (name, times, years, ratio, qtype, hot, slug) in enumerate(topics, 1):
        # 归档里链接指向同目录的 .md（归档内自洽、在 GitHub/编辑器里可点开）；
        # 网页版由 build_html.py 在渲染时把 .md 改指同名跳转页 .md.html
        rows.append("| %d | [%s](%s.md) | %s | %s | %s |"
                    % (i, name, slug,
                       (T.PENDING if times == T.PENDING else "%d 次" % times),
                       ratio, "**是**" if hot else "否"))
    return "\n".join(rows)


def build_subject(subject_key):
    sub = T.SUBJECTS[subject_key]
    topics = T.TOPICS[subject_key]
    head = [
        "# %s · 408 速成复习资料" % sub["name"],
        "",
        "**科目分值**：%d 分 / 150 分　|　**章节数**：%d　|　**统计区间**：2009—2025 年 408 统考真题（17 套）" % (sub["score"], len(topics)),
        "",
        "## 本科目章节索引",
        "",
        subject_index(subject_key, topics),
        "",
        FRONT[subject_key].format(choice=sub["choice"], comprehensive=sub["comprehensive"]),
        QUICK,
    ]
    body = []
    for t in topics:
        p = os.path.join(ROOT, "parts", subject_key, t[6] + ".md")
        if not os.path.exists(p):
            raise SystemExit("缺少 parts 文件：%s" % p)
        body.append(build_topic(subject_key, t, parse_partial(p)))
    text = "\n".join(head) + "\n".join(body)
    out = os.path.join(DOCS, sub["dir"], "00-科目总览.md")
    # 章节文件
    for t in topics:
        p = os.path.join(ROOT, "parts", subject_key, t[6] + ".md")
        content = "# %s · %s\n\n" % (sub["name"], t[0]) + build_topic(subject_key, t, parse_partial(p))
        fp = os.path.join(DOCS, sub["dir"], t[6] + ".md")
        with open(fp, "w", encoding="utf-8") as f:
            f.write(NM.normalize(content))
    with open(out, "w", encoding="utf-8") as f:
        f.write(NM.normalize(text))
    return out


def main():
    keys = sys.argv[1:] or T.ORDER
    for k in keys:
        print("生成:", build_subject(k))


if __name__ == "__main__":
    main()
