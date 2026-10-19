# website/Lerno-cs —— 408 速成复习资料

本目录是一个**独立 git 仓库**（分支 `main`）。上游工作区说明见
[`../../AGENTS.md`](../../AGENTS.md)（若你的项目根是本目录，该文件不会被自动加载，
故要点在此复述）。

📋 **跨项目的对齐与改版规格见 [`../PLAN-对齐与改版.md`](../PLAN-对齐与改版.md)**——
它同时约束本仓库与 `../Lerno-math/`，涉及外壳结构、类名、分期与验收。
发现规格有问题请回报管理会话改那份文件，**不要在本仓库里自行发明例外**。

## 一、路径提醒（2026-10-15 工作区重组）

| 旧路径（已失效） | 现在的实际位置 |
| --- | --- |
| `UCAS/408-kaoyan/` | **`UCAS/website/Lerno-cs/`**（就是本目录） |
| `UCAS/408-new/` | `UCAS/website/Lerno-math/`（**数学二**项目，不是 408） |

⚠️ `408-new/` 这个目录名**已废弃**：它原本是本 408 项目的仓库，408 内容搬走后
被数学二项目接管，现已改名为 `website/Lerno-math/`。
若历史会话记录或旧文档里出现 `408-new/`，一律按下表换算：

- `408-new/scripts/…` → `website/Lerno-cs/scripts/…`
- `408-new/PLAYBOOK-速成资料工程化.md` → `website/Lerno-cs/PLAYBOOK-速成资料工程化.md`
- `408-new/408/…` → 该层中间目录已取消，成品现在直接在仓库根的四科目录下


## 一点五、目录改名（2026-10-16）—— 零符号链接

本仓库目录已改名为**与远端仓库同名**：

| 旧目录名 | 现目录名（真实、唯一） |
| --- | --- |
| `website/408-kaoyan/` | `website/Lerno-cs/` |

**无符号链接、无兼容路径。** 本 agent 会话的 cwd 已同步改写：
DSH 把 cwd 存在会话文件第一行的 `cwd` 字段，且这是唯一权威来源
（`dsh-api-session-controller/lib/types/agent.js` L286/L470 是 header 对 header 的比较）。

> ⚠️ **不要**把目录 `mv` 回旧名，也不要建符号链接 —— 两者都会让会话失组。
> 将来若必须再改名，**同步改会话 header**。

本文档里仍出现的旧目录名（如历史迁移表）**保持原样不动**，它们记录的是当时的事实。

## 二、目录职责

```
website/Lerno-cs/
├── .github/workflows/pages.yml  Pages 工作流：validate.py 门禁 → 上传仓库根
├── index.html                   落地页 / 部署首屏（四科卡片 + 全科单页合集）
├── 数据结构/ 计算机组成原理/ 操作系统/ 计算机网络/
│                                静态站点：index.html、01-….html、01-….md.html
├── assets/                      ★ 外壳样式与行为（手写源，必须入库）
│   ├── site.css                 外壳样式（与 Lerno-math **逐字节相同**，勿就地改）
│   ├── site.js                  外壳行为（与 Lerno-math **逐字节相同**，勿就地改）
│   └── quiz-data.js             题库产物（**生成物**：build_quiz.py 从 parts/quiz/ 生成）
├── README.html                  总览页（站点版 ＝ .docs/00-总览.md 渲染）
├── README.md                    仓库说明（部署 / 许可 / 数据可信度口径）
├── mermaid.min.js               本地 Mermaid 运行时（离线渲染）
├── .docs/                       Markdown 归档 ← 生成物，勿手改
│                                ⚠️ 例外：`00-总览.md` 是**手工维护**的总览页
│                                （只有考频总表由 gen_summary.py 注入），
│                                它渲染成 README.html，改口径要连 README.md 一起改
├── parts/                       内容源，只写这里：ds/ os/ co/ net/（+ quiz/ 题库源）
├── scripts/                     生成与校验工具链
├── LICENSE
├── PLAYBOOK-速成资料工程化.md
└── PROMPT-数学二速成资料.md
```

> 页面外壳（DOM 与 class 名）与 `../Lerno-math/` 共用同一份契约，见
> [`../PLAN-对齐与改版.md`](../PLAN-对齐与改版.md) 2.3/2.4。
> 契约钦定：`.site-topbar`/`.tb-*`、`.site-sidebar`、`#sec-freq`…`#sec-real`、
> `.chapter-nav`/`.cn-prev`/`.cn-next`、`.site-footer`、`.home-subjects`/`.hs-*`、
> `html.dark`、`←/→ j/k` 翻章。**改类名前先改契约**，不要在本仓库发明例外。
>
> 另有 `site.js` **钩子契约**（§2.4.1；这些是脚本真正查询的名字，改名会让行为
> 静默失效）：`.theme-toggle` `.nav-toggle` `.to-top` `.read-progress`
> `.sb-filter` `.sb-group` `.sb-group-t` `.sb-chap` `.tocbox` `.toclink`
> `.tb-search`、`localStorage['kaoyan-theme']`、`body[data-prev|data-next]`、
> `<a id="top">`。`site.js` 必须在 `<head>` **同步**引入（不可 `defer`），
> 页面不得有内联 `<style>`/`<script>`。

## 三、再生成与校验（在本目录内执行）

```bash
# 依赖（版本锁定在 scripts/requirements.txt 与 scripts/tools-package.json）
python3 -m venv .tools/venv
.tools/venv/bin/python -m pip install -r scripts/requirements.txt
# Node 侧版本只在 scripts/tools-package.json 里，命令里不写版本号
mkdir -p .tools && cp scripts/tools-package.json .tools/package.json
npm install --prefix .tools --cache /tmp/npm-cache --no-audit --no-fund

python3 scripts/run_all.py         # 一键跑通全链（推荐）；--quick 跳过规范化与分段
python3 scripts/normalize_md.py    # Markdown 空行规范化（幂等）
python3 scripts/split_explain.py   # 长段落自动分段
python3 scripts/build.py           # parts/ + meta.py → .docs/ 的 Markdown
python3 scripts/gen_summary.py     # 刷新 .docs/00-总览.md 的考频总表
python3 scripts/build_quiz.py      # parts/quiz/*.json → assets/quiz-data.js（练习页数据）
python3 scripts/build_html.py      # .docs/ → 仓库根的静态站点
python3 scripts/validate.py        # 校验形式层（含 mermaid 真解析与外壳行为测试）
python3 scripts/validate.py --parts   # 校验 parts/ 半成品（写内容时的内层循环）
python3 scripts/reverse_tests.py       # 反向测试：每条规则注入反例，确认真会报错
```

> **新增校验规则必须同时加反向测试**：元校验会比对"规则集合 ≡ 反向测试覆盖集合"
> （集合比较，编号有空洞不假设连续），漏了直接报错。扫描型规则还须上报受检对象数，
> 受检数为 0 同样报错（防止"什么都没检查却一片绿"）。

> `mermaid` 的真实解析（`scripts/check_mermaid.mjs`）已并入 `validate.py` 的 F3，
> **不再是"可选"**：缺 node 或 `.tools` 依赖会报 error 而不是跳过。
> 确实要离线跑，须显式加 `--no-mermaid`。

## 四、硬性约定

- **标题只在页面外壳出现一次**：Markdown 归档自带的 `h1`/`h2` 由 `build_html.py`
  剥掉（渲染器的 `toc` 扩展会给它们加 `id`，所以要匹配**带属性**的形式）。
  不剥会让读者看到同一标题连出三次，并产生 `id="_2" id="kp"` 这种**重复 id 属性**。
  `F22` 已强制"每页恰好 1 个 `<h1>`、无重复 id 属性"。
- **改内容只改 `parts/`**，然后重跑脚本。`.docs/` 和所有 `.html` 都是生成物，
  手工改会在下次生成时被覆盖（**唯一例外**：`.docs/00-总览.md` 是手工维护的
  总览页，它渲染成 `README.html`；改口径要连 `README.md` 一起改——两份高度重叠
  但各自独立维护，线上页面渲染的**不是** `README.md`）。
- `assets/site.css` 与 `assets/site.js` 是**共用件**（U1 起两者都是）：与
  `../Lerno-math` **逐字节相同**，各自在文件头钉上游 sha256，由**同一条**
  元校验（F25 的共用件清单）强制。**不要就地改这两份**——要改先改契约，
  由数学二产出统一版，408 再逐字节复制并重钉哈希。
  数学二的 `scripts/test_site_js.mjs` 同样来自上游，由外壳行为测试在门禁里跑。
- **目录改名时要同步 `scripts/validate.py` 的 `UPSTREAM_REPO` 常量**：它是兄弟
  仓库（上游）的目录名，共用件比对与外壳行为测试的备用路径都走它。写错**不会**
  报错——F25 的逐字节比对会静默跳过（2026-10-16 改名就踩过）。现在它会在报告里
  打印「逐字节比对 N/2 项」，并在同工作区发现「实际叫别的名字」时告警。
- 页面外壳的 DOM 与 class 名是**跨项目契约**，改类名/锚点 id 前先改
  `../PLAN-对齐与改版.md`，再同步两个项目。
- `assets/CSS-NOTES.md` 是 408 侧类选择器清单（U1 第 ① 步的交付物，
  供数学二合并统一版用），**它是手写文档，不是生成物**；统一版落地后仍可作为
  「哪个类归谁、为什么」的索引。
- `scripts/meta.py` 是**考频数字的唯一数据源**，正文里的数字由 `build.py` 注入，
  不要在两处各写一份。
- **题库只改 `parts/quiz/*.json`**，然后跑 `build_quiz.py` + `validate.py`；
  `assets/quiz-data.js` 是生成物（F31 会核对源哈希与题目内容，手改必报错）。
  题库字段、来源与授权见 `parts/quiz/README.md`。
- 考频/真题数据凡不能核实的，标注「考频待补充」或「真题改编」，**不许编造**。
  数据口径与可信度分级见 `README.md` 第三节。
- 站点是完全离线的纯静态页，改完直接用浏览器打开 `index.html` 验证，无需起服务器。
- 临时依赖放 `.tools/`（已 gitignore），不要提交 `__pycache__/`。
