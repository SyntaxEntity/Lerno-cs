#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键跑通全流水线：规范化 → 分段 → 组装 → 总表 → 站点 → 校验。

顺序是有讲究的：
  1. `normalize_md.py`  先规范化内容源空行 —— 后面所有步骤都假定空行已规范；
  2. `split_explain.py` 长段落自动分段（同样只该在规范化之后做）；
  3. `build.py`         由 parts/ + meta.py 组装成 .docs/ 的 Markdown；
  4. `gen_summary.py`   把考频总表注入 .docs/00-总览.md（依赖上一步的产物）；
  5. `build_html.py`    由 .docs/ 生成仓库根的静态站点（依赖 3、4 的产物）；
  6. `validate.py`      校验成品：F1—F17，含链接可达与 mermaid 真实解析。

用法
----
    python3 scripts/run_all.py            # 全部跑一遍
    python3 scripts/run_all.py --quick    # 跳过规范化与分段（只重建 + 校验）

解释器：本流水线只需要标准库 + `markdown`（F14 用）。若当前解释器缺它，
本脚本会自动改用仓库内的 `.tools/venv/bin/python`（存在时）。
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENV = os.path.join(ROOT, ".tools", "venv", "bin", "python")

# 与站点内置运行时**逐字节一致**的版本；换版本会让校验的语法与线上渲染的不是同一个。
NODE_DEPS = {"mermaid": "12.1.0", "jsdom": "30.1.2"}
# 站点内置的 mermaid 运行时（仓库根），用来核对上面 mermaid 的版本
BUNDLED_MERMAID = os.path.join(ROOT, "mermaid.min.js")


def _pkg_version(name):
    p = os.path.join(ROOT, ".tools", "node_modules", name, "package.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("version")
    except Exception:                                        # noqa: BLE001
        return None


def _bundled_mermaid_version():
    """从内置 mermaid.min.js 里抠出版本号，用于和 tools-package.json 核对。

    ⚠️ 必须**通读全文**：这个 5.2 MB 的 bundle 里 `version:"0.0.0"` 出现在前部
    （约 747 KB 处，属无关组件），真正的 `version:"12.1.0"` 在约 4.4 MB 处。
    只读开头会抠到 0.0.0 或抠不到，从而把版本核对变成永远通过。
    """
    import re
    try:
        with open(BUNDLED_MERMAID, encoding="utf-8", errors="ignore") as f:
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
    """检查 .tools/node_modules 里的前端依赖是否就位、版本是否与站点运行时一致。

    版本漂移必须**在开跑前**报出来：F3 用 `mermaid` 解析、站点用仓库根的
    `mermaid.min.js` 渲染——两者版本不同，就会出现「校验通过但页面渲染不出来」
    这种最难查的情况。
    """
    install = ("npm install --prefix .tools --cache /tmp/npm-cache --no-audit --no-fund "
               + " ".join("%s@%s" % (n, v) for n, v in NODE_DEPS.items()))
    problems = []
    for name, want in NODE_DEPS.items():
        got = _pkg_version(name)
        if got is None:
            problems.append("缺少 %s" % name)
        elif want and got != want:
            problems.append("%s 版本不符：装的是 %s，要求 %s" % (name, got, want))
    bundled = _bundled_mermaid_version()
    have = _pkg_version("mermaid")
    if bundled and have and bundled != have:
        problems.append("mermaid 与站点内置运行时不一致：.tools 装的是 %s，"
                        "仓库根 mermaid.min.js 是 %s" % (have, bundled))
    if not problems:
        return True
    print("! Node 依赖有问题：%s" % "；".join(problems))
    print("  重装（版本必须与站点内置运行时一致）：")
    print("    %s" % install)
    return False


def need_deps():
    """返回一个能 import markdown 的解释器路径。"""
    for cand in (sys.executable, VENV):
        if not os.path.exists(cand):
            continue
        r = subprocess.run([cand, "-c", "import markdown"], capture_output=True, text=True)
        if r.returncode == 0:
            return cand
    print("! 找不到具备 markdown 的解释器（F14 需要它）。")
    print("  先运行：python3 -m venv .tools/venv && "
          ".tools/venv/bin/python -m pip install -r scripts/requirements.txt")
    sys.exit(1)


def run(title, args, cwd=ROOT):
    print("\n" + "=" * 78)
    print("▶ " + title)
    print("=" * 78)
    r = subprocess.run(args, cwd=cwd, text=True)
    return r.returncode


def main():
    quick = "--quick" in sys.argv
    PY = need_deps()
    print("使用解释器：%s" % PY)
    deps_ok = check_node_deps()
    fails = []

    if not quick:
        if run("规范化内容源空行", [PY, os.path.join(HERE, "normalize_md.py")]) != 0:
            fails.append("normalize_md")
        if run("长段落自动分段", [PY, os.path.join(HERE, "split_explain.py")]) != 0:
            fails.append("split_explain")

    if run("组装成品 Markdown", [PY, os.path.join(HERE, "build.py")]) != 0:
        fails.append("build")
    if run("刷新考频总表", [PY, os.path.join(HERE, "gen_summary.py")]) != 0:
        fails.append("gen_summary")
    if run("生成 HTML 站点", [PY, os.path.join(HERE, "build_html.py")]) != 0:
        fails.append("build_html")
    if run("校验成品（F1—F17，含 mermaid 真实解析）",
           [PY, os.path.join(HERE, "validate.py")]) != 0:
        fails.append("validate")

    print("\n" + "=" * 78)
    if not deps_ok:
        fails.append("node 依赖缺失")
    if fails:
        print("✗ 流水线有 %d 步失败：%s" % (len(fails), "、".join(fails)))
        return 1
    print("✓ 流水线全部通过")
    print("  成品入口：index.html（全科单页）、README.html（总览与数据口径）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
