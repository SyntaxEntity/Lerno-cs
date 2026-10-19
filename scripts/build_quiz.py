#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 parts/quiz/*.json 的题库源打包成 assets/quiz-data.js（供练习页在 file:// 下加载）。

为什么是 JS 而不是 JSON：站点承诺「双击 index.html 就能用」。`fetch('quiz.json')`
在 file:// 下会被 CORS 拦掉，只有 <script> 能稳定加载数据（PLAN-对齐与改版 §2.3.1.A）。

产物是**生成物**（和站点 HTML 一样入库），头部钉源哈希：
    sourceSha256 = <四份源文件按固定顺序拼接后的 sha256>
    count        = <题数>
validate.py 的 F31 会重算这个哈希并比对——手改产物、改了源却忘记重跑，都会报错。

幂等：不带时间戳，同样的源必然产出同样的字节。
用法：python3 scripts/build_quiz.py
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC_DIR = os.path.join(ROOT, "parts", "quiz")
OUT = os.path.join(ROOT, "assets", "quiz-data.js")
SUBJECTS = ["ds", "co", "os", "net"]          # 固定顺序：哈希与产物都依赖它


def source_files():
    """按固定顺序返回四份源文件的路径（缺一份就报错，不静默少读）。"""
    paths = []
    for k in SUBJECTS:
        fp = os.path.join(SRC_DIR, "%s.json" % k)
        if not os.path.exists(fp):
            sys.exit("缺少题库源：%s" % os.path.relpath(fp, ROOT))
        paths.append(fp)
    return paths


def source_sha256(paths=None):
    """源哈希：四份文件按固定顺序的原始字节拼接后取 sha256。

    ⚠️ 不用「解析后重新序列化再哈希」：那样格式变化（缩进）不影响哈希，
    会出现「源改了、哈希没变」的漏洞。直接哈希字节，改任何一处都算改源。
    """
    if paths is None:
        paths = source_files()
    h = hashlib.sha256()
    for fp in paths:
        h.update(os.path.basename(fp).encode("utf-8"))
        h.update(b"\0")
        with open(fp, "rb") as fh:
            h.update(fh.read())
        h.update(b"\0")
    return h.hexdigest()


def load_questions(paths=None):
    """读出全部题目（跨科目按 id 排序），并做最小结构检查。"""
    if paths is None:
        paths = source_files()
    questions = []
    for fp in paths:
        with open(fp, encoding="utf-8") as fh:
            data = json.load(fh)
        for q in data.get("questions") or []:
            questions.append(q)
    questions.sort(key=lambda q: q["id"])
    return questions


def build(out_path=OUT):
    paths = source_files()
    questions = load_questions(paths)
    sha = source_sha256(paths)
    payload = {"version": 1, "sourceSha256": sha, "questions": questions}
    body = "window.LERNO_QUIZ = " + json.dumps(payload, ensure_ascii=False,
                                               separators=(",", ":")) + ";\n"
    header = (
        "/* 由 scripts/build_quiz.py 从 parts/quiz/*.json 生成，**勿手改**。\n"
        " *\n"
        " * 源（固定顺序，缺一不可）：parts/quiz/ds.json、co.json、os.json、net.json\n"
        " * sourceSha256 = %s\n"
        " * count = %d\n"
        " *\n"
        " * 校验：validate.py 的 F31 会重算源哈希与条数并比对；\n"
        " * 手改本文件、或改了源却没重跑构建，都会报错。\n"
        " */\n" % (sha, len(questions))
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(header + body)
    return sha, len(questions)


def main():
    sha, n = build()
    size = os.path.getsize(OUT)
    print("题库产物：%d 题 → assets/quiz-data.js（%.1f KB，源哈希 %s…）"
          % (n, size / 1024.0, sha[:12]))
    # 覆盖情况：每个知识点各有多少题（0 题的会在 validate.py 的 F30 里告警）
    from collections import Counter
    topics = Counter(q["topic"] for q in load_questions())
    print("  覆盖 %d 个知识点；每个知识点 %d—%d 题"
          % (len(topics), min(topics.values()), max(topics.values())))


if __name__ == "__main__":
    main()
