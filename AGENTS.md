# website/408-kaoyan —— 408 速成复习资料

本目录是一个**独立 git 仓库**（分支 `main`）。上游工作区说明见
[`../../AGENTS.md`](../../AGENTS.md)（若你的项目根是本目录，该文件不会被自动加载，
故要点在此复述）。

📋 **跨项目的对齐与改版规格见 [`../PLAN-对齐与改版.md`](../PLAN-对齐与改版.md)**——
它同时约束本仓库与 `../math2-kaoyan/`，涉及外壳结构、类名、分期与验收。
发现规格有问题请回报管理会话改那份文件，**不要在本仓库里自行发明例外**。

## 一、路径提醒（2026-10-15 工作区重组）

| 旧路径（已失效） | 现在的实际位置 |
| --- | --- |
| `UCAS/408-kaoyan/` | **`UCAS/website/408-kaoyan/`**（就是本目录） |
| `UCAS/408-new/` | `UCAS/website/math2-kaoyan/`（**数学二**项目，不是 408） |

⚠️ `408-new/` 这个目录名**已废弃**：它原本是本 408 项目的仓库，408 内容搬走后
被数学二项目接管，现已改名为 `website/math2-kaoyan/`。
若历史会话记录或旧文档里出现 `408-new/`，一律按下表换算：

- `408-new/scripts/…` → `website/408-kaoyan/scripts/…`
- `408-new/PLAYBOOK-速成资料工程化.md` → `website/408-kaoyan/PLAYBOOK-速成资料工程化.md`
- `408-new/408/…` → 该层中间目录已取消，成品现在直接在仓库根的四科目录下

## 二、目录职责

```
website/408-kaoyan/
├── .github/workflows/pages.yml  Pages 工作流：validate.py 门禁 → 上传仓库根
├── index.html                   落地页 / 部署首屏（四科卡片 + 全科单页合集）
├── 数据结构/ 计算机组成原理/ 操作系统/ 计算机网络/
│                                静态站点：index.html、01-….html、01-….md.html
├── assets/                      ★ 外壳样式与行为（手写源，必须入库）
│   ├── site.css                 站点外壳样式（配色 token 本项目自定）
│   └── site.js                  站点外壳行为（暂为占位，待逐字替换为数学二版本）
├── README.html                  总览页（站点版 ＝ .docs/00-总览.md 渲染）
├── README.md                    仓库说明（部署 / 许可 / 数据可信度口径）
├── mermaid.min.js               本地 Mermaid 运行时（离线渲染）
├── .docs/                       Markdown 归档 ← 生成物，勿手改
├── parts/                       内容源，只写这里：ds/ os/ co/ net/
├── scripts/                     生成与校验工具链
├── LICENSE
├── PLAYBOOK-速成资料工程化.md
└── PROMPT-数学二速成资料.md
```

> 页面外壳（DOM 与 class 名）与 `../math2-kaoyan/` 共用同一份契约，见
> [`../PLAN-对齐与改版.md`](../PLAN-对齐与改版.md) 2.3/2.4。
> 契约钦定：`.site-topbar`/`.tb-*`、`.site-sidebar`、`#sec-freq`…`#sec-real`、
> `.chapter-nav`/`.cn-prev`/`.cn-next`、`.site-footer`、`.home-subjects`/`.hs-*`、
> `html.dark`、`←/→ j/k` 翻章。**改类名前先改契约**，不要在本仓库发明例外。

## 三、再生成与校验（在本目录内执行）

```bash
# 依赖（版本锁定在 scripts/requirements.txt 与 scripts/tools-package.json）
python3 -m venv .tools/venv
.tools/venv/bin/python -m pip install -r scripts/requirements.txt
npm install --prefix .tools --cache /tmp/npm-cache --no-audit --no-fund \
  mermaid@12.1.0 jsdom@30.1.2

python3 scripts/run_all.py         # 一键跑通全链（推荐）；--quick 跳过规范化与分段
python3 scripts/normalize_md.py    # Markdown 空行规范化（幂等）
python3 scripts/split_explain.py   # 长段落自动分段
python3 scripts/build.py           # parts/ + topics.py → .docs/ 的 Markdown
python3 scripts/gen_summary.py     # 刷新 .docs/00-总览.md 的考频总表
python3 scripts/build_html.py      # .docs/ → 仓库根的静态站点
python3 scripts/validate.py        # 校验 F1—F23（含 mermaid 真实解析，缺依赖即报错）
python3 scripts/validate.py --parts   # 校验 parts/ 半成品（写内容时的内层循环）
```

> `mermaid` 的真实解析（`scripts/check_mermaid.mjs`）已并入 `validate.py` 的 F3，
> **不再是"可选"**：缺 node 或 `.tools` 依赖会报 error 而不是跳过。
> 确实要离线跑，须显式加 `--no-mermaid`。

## 四、硬性约定

- **改内容只改 `parts/`**，然后重跑脚本。`.docs/` 和所有 `.html` 都是生成物，
  手工改会在下次生成时被覆盖。
- `assets/site.css` 与 `assets/site.js` 是**手写源**（不是生成物），必须入库；
  但页面外壳的 DOM 与 class 名是**跨项目契约**，改类名/锚点 id 前先改
  `../PLAN-对齐与改版.md`，再同步两个项目。`site.js` 目前是占位实现，
  待数学二抽出后**整体逐字替换**，不要两边各维护一份。
- `scripts/topics.py` 是**考频数字的唯一数据源**，正文里的数字由 `build.py` 注入，
  不要在两处各写一份。
- 考频/真题数据凡不能核实的，标注「考频待补充」或「真题改编」，**不许编造**。
  数据口径与可信度分级见 `README.md` 第三节。
- 站点是完全离线的纯静态页，改完直接用浏览器打开 `index.html` 验证，无需起服务器。
- 临时依赖放 `.tools/`（已 gitignore），不要提交 `__pycache__/`。
