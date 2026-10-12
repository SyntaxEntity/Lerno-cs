#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown 空行规范化器。

为什么需要它：Markdown 中**单换行不产生换行**。块级元素（标题、代码围栏、
引用块、表格、列表）之间若只隔一个换行，渲染时会与相邻段落粘连成一段。
本资料初版就因此把「核心讲解 / 关键结论速记 / 示意图 / 易错点 / 真题示例」
五个模板字段渲染成一整坨。

本脚本做两件事，且**幂等**（重复运行结果不变）：
  1. 在块级元素前后保证恰好一个空行；
  2. 折叠连续空行（代码围栏内部一律不动）。

用法： python3 scripts/normalize_md.py            # 规范化 parts/（内容源）
       python3 scripts/normalize_md.py --check    # 只报告需要改动的位置
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = os.path.join(ROOT, "parts")

TABLE_SEP = re.compile(r"^\|?[\s:\-|]+\|[\s:\-|]*$")


def is_table_line(s):
    return s.startswith("|") or bool(TABLE_SEP.match(s) and "-" in s)


def split_blocks(lines):
    """把文档切成块：整个代码围栏算一块；连续的表格行/列表行/引用行各算一块。"""
    blocks, i, n = [], 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if s.startswith("```"):
            buf = [lines[i]]
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            if i < n:
                buf.append(lines[i]); i += 1          # 闭合围栏
            blocks.append(("fence", buf))
            continue
        if not s:
            i += 1
            continue                                   # 空行不产生块，后面统一补
        if is_table_line(s):
            kind = "table"
        elif s.startswith(">"):
            kind = "quote"
        elif re.match(r"^#{1,6} ", s):
            kind = "head"
        elif re.match(r"^([-*+]|\d+\.)\s", s):
            kind = "list"
        else:
            kind = "text"
        buf = [lines[i]]; i += 1
        while i < n:
            t = lines[i].strip()
            if not t:
                break
            same = (
                (kind == "table" and is_table_line(t)) or
                (kind == "quote" and t.startswith(">")) or
                (kind == "list" and re.match(r"^([-*+]|\d+\.)\s", t)) or
                (kind == "text" and not is_table_line(t) and not t.startswith(">")
                 and not re.match(r"^#{1,6} ", t) and not t.startswith("```")
                 and not re.match(r"^([-*+]|\d+\.)\s", t))
            )
            if not same:
                break
            buf.append(lines[i]); i += 1
        blocks.append((kind, buf))
    return blocks


def normalize(text):
    lines = text.split("\n")
    blocks = split_blocks(lines)
    out = []
    for kind, buf in blocks:
        if out:
            out.append("")                             # 块间恰好一个空行
        if kind == "fence":
            out.extend(buf)
        else:
            out.extend(buf)
    return "\n".join(out).rstrip("\n") + "\n"


def main():
    check = "--check" in sys.argv
    changed = 0
    for f in sorted(glob.glob(os.path.join(PARTS, "*", "*.md"))):
        src = open(f, encoding="utf-8").read()
        dst = normalize(src)
        if src != dst:
            changed += 1
            rel = os.path.relpath(f, ROOT)
            if check:
                print("需规范化:", rel)
            else:
                open(f, "w", encoding="utf-8").write(dst)
                print("已规范化:", rel)
    print(("需要规范化 %d 个文件" if check else "已规范化 %d 个文件") % changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
