#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把考频总表注入 .docs/00-总览.md 的标记区（保证 README 与 meta.py 数据一致）。

用法： python3 scripts/gen_summary.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meta as T  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 仓库根
DOCS = os.path.join(ROOT, ".docs")                                   # Markdown 归档（README 所在处）
BEGIN = "<!-- FREQ-TABLE-BEGIN 由 scripts/gen_summary.py 生成，请勿手工编辑 -->"
END = "<!-- FREQ-TABLE-END -->"


def build_table():
    rows = [
        "| 科目 | 章节 | 知识点 | 考察次数 | 分值占比 | 高频 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for k in T.ORDER:
        s = T.SUBJECTS[k]
        for i, (name, times, years, ratio, qtype, hot, slug) in enumerate(T.TOPICS[k], 1):
            rows.append("| %s | %d | [%s](%s/%s.md) | %s | %s | %s |" % (
                s["name"], i, name, s["dir"], slug,
                (T.PENDING if times == T.PENDING else "%d 次" % times),
                ratio, "**是**" if hot else "否"))
    return "\n".join(rows)


def main():
    path = os.path.join(DOCS, "00-总览.md")
    if not os.path.exists(path):
        raise SystemExit(".docs/00-总览.md 不存在")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < 0:
        raise SystemExit(".docs/00-总览.md 缺少 FREQ-TABLE 标记")
    new = text[:i] + BEGIN + "\n\n" + build_table() + "\n\n" + text[j:]
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    n = sum(len(T.TOPICS[k]) for k in T.ORDER)
    print("已注入考频总表：%d 个知识点" % n)


if __name__ == "__main__":
    main()
