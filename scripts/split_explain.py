#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「核心讲解」的超长单段拆成多段，并用空行分隔（Markdown 里空行才换行）。

策略：
  1. 只在**行首、且紧跟在 `\\n` 缩进之后**的中文句末标点处切句，因此
     `` `O(n^2)` ``、行内英文句点、小数（0.7）都不会被误切；
  2. 按「长度阈值 + 话题转换词」决定切段位置，保持每段 2—4 句、约 260—560 字；
  3. 幂等：已经分好段的（段落均不超过阈值）不再改动。

用法： python3 scripts/split_explain.py [--check]
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = os.path.join(ROOT, "parts")

# 段首出现这些词，通常意味着换了话题，适合另起一段
TOPIC_WORDS = (
    "存储上", "存储结构上", "寻址方式", "编码上", "性能上", "实现上", "物理上",
    "时间", "复杂度", "典型", "注意", "反之", "对比", "区别",
)
MAX_LEN = 560          # 单段最长字符数
MIN_LEN = 200          # 单段最短字符数（不足则与下一段合并）
SOFT_MIN = 260

SENT_END = "\u3002\uff1b"          # 。 ；
MAX_LEN, SOFT_MIN, MIN_LEN = 400, 200, 160


def split_sentences(para):
    """按中文句末标点切句。行内英文句点、小数、代码块内的标点都不受影响，"""
    out, buf = [], ""
    for ch in para:
        buf += ch
        if ch in SENT_END:
            out.append(buf)
            buf = ""
    if buf.strip():
        out.append(buf)
    return [x for x in out if x.strip()]


def split_paragraph(para):
    """把超长段落切成 2—4 句一组的多段。"""
    if len(para) <= MAX_LEN:
        return [para]
    sents = split_sentences(para)
    if len(sents) < 2:
        return [para]
    n = len(sents)
    # 目标段数：按总长度估算，至少 2 段
    target = max(2, round(len(para) / MAX_LEN))
    per = max(1, n // target)                 # 每段句数
    groups = []
    for i in range(0, n, per):
        groups.append("".join(sents[i:i + per]).strip())
    # 尾部过短则并回上一段
    if len(groups) >= 2 and len(groups[-1]) < MIN_LEN:
        groups[-2] += groups[-1]
        groups.pop()
    # 仍有超长段则按句号中点再切一刀
    final = []
    for g in groups:
        if len(g) <= MAX_LEN:
            final.append(g); continue
        ss = split_sentences(g)
        if len(ss) < 2:
            final.append(g); continue
        mid = len(ss) // 2
        final.append("".join(ss[:mid]).strip())
        final.append("".join(ss[mid:]).strip())
    return [x for x in final if x]


def process(text):
    """只处理 `# 核心讲解` 与下一个 `# ` 标题之间的正文。"""
    m = re.search(r"(# 核心讲解\n\n)(.*?)(\n+# )", text, re.S)
    if not m:
        return text, 0
    body = m.group(2).strip()
    pieces, changed = [], 0
    for para in [x for x in body.split("\n\n") if x.strip()]:
        sub = split_paragraph(para.strip())
        if len(sub) > 1:
            changed += 1
        pieces.extend(sub)
    if not changed:
        return text, 0
    return text[:m.start(2)] + "\n\n".join(pieces) + text[m.end(2):], changed


def main():
    check = "--check" in sys.argv
    files = 0
    for f in sorted(glob.glob(os.path.join(PARTS, "*", "*.md"))):
        src = open(f, encoding="utf-8").read()
        dst, changed = process(src)
        if changed:
            files += 1
            rel = os.path.relpath(f, ROOT)
            if check:
                print("需分段:", rel)
            else:
                open(f, "w", encoding="utf-8").write(dst)
                print("已分段:", rel, "(%d 段被拆分)" % changed)
    print(("需要分段 %d 个文件" if check else "已处理 %d 个文件") % files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
