// 用官方 mermaid 解析器校验所有 ```mermaid 代码块的真实语法。
//
// 为什么必须"真解析"：静态正则查不出「节点文本含圆括号未加引号」这类写法——
// 它会让 mermaid 直接解析失败、页面上的图静默变空白，而正则看起来一切正常。
//
// 用法:
//   node scripts/check_mermaid.mjs [--content <目录>]
//     默认扫描 .docs/（成品归档）；`validate.py --parts` 时传 parts/。
//
// 输出: 一行 JSON（供 validate.py 解析）
//   {"ok":N,"total":N,"failed":[{"file":..,"line":..,"error":..}],"nodes":N}
//   {"fatal":"...","hint":"..."}                        ← 依赖缺失等致命错误
//
// 退出码: 0 全部解析通过 | 1 有图解析失败 | 2 环境/依赖问题
//
// 依赖: 先装到 .tools （见 scripts/tools-package.json，版本须与仓库根
//       mermaid.min.js 一致，否则校验的语法与线上渲染的不是同一个版本）
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, resolve, relative } from 'node:path';

const TOOLS = resolve('.tools/node_modules');
const args = process.argv.slice(2);

function argValue(name, dflt) {
  const i = args.indexOf(name);
  return i >= 0 && i + 1 < args.length ? args[i + 1] : dflt;
}

const CONTENT = resolve(argValue('--content', '.docs'));
const HINT = '装依赖：npm install --prefix .tools --cache /tmp/npm-cache --no-audit --no-fund '
  + 'mermaid@12.1.0 jsdom@30.1.2（版本见 scripts/tools-package.json）';

/** 致命错误：始终以 JSON 形式报出，让调用方不必解析 stderr 文案。 */
function fatal(msg) {
  console.log(JSON.stringify({ fatal: msg, hint: HINT }));
  process.exit(2);
}

// ---- 依赖与扫描范围：两者任一不成立都必须立刻失败 ----------------------------
// 这里的失败路径必须是 fatal 而不是"扫到 0 张图"——后者会被误读成"全部通过"。
if (!existsSync(CONTENT) || !statSync(CONTENT).isDirectory()) {
  fatal(`扫描目录不存在：${relative(process.cwd(), CONTENT) || CONTENT}`);
}
if (!existsSync(join(TOOLS, 'jsdom')) || !existsSync(join(TOOLS, 'mermaid'))) {
  fatal(`缺少 .tools/node_modules 下的依赖（jsdom / mermaid）`);
}

// jsdom 提供 mermaid 需要的 DOM 环境（parse() 用它建临时容器）
const { JSDOM } = await import(join(TOOLS, 'jsdom/lib/api.js'));
const dom = new JSDOM('<!DOCTYPE html><body></body>', { pretendToBeVisual: true });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.DOMParser = dom.window.DOMParser;
globalThis.Node = dom.window.Node;
globalThis.Element = dom.window.Element;
globalThis.SVGElement = dom.window.SVGElement;
globalThis.HTMLElement = dom.window.HTMLElement;

const mermaid = (await import(join(TOOLS, 'mermaid/dist/mermaid.esm.mjs'))).default;
mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' });

// 只在内容目录里找 .md：工具链、依赖目录与临时目录一律不进
const SKIP_DIRS = new Set(['.git', '.tools', 'node_modules', '__pycache__']);

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (name.endsWith('.md')) out.push(p);
  }
  return out;
}

const files = walk(CONTENT);
const failed = [];
let total = 0;

for (const f of files) {
  const lines = readFileSync(f, 'utf8').split('\n');
  let inBlock = false, buf = [], startLine = 0;
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (!inBlock && /^\s*```mermaid\s*$/.test(l)) {
      inBlock = true; buf = []; startLine = i + 2; continue;
    }
    if (inBlock && l.trim() === '```') {
      inBlock = false;
      total++;
      try {
        const r = await mermaid.parse(buf.join('\n'));
        if (!r || !r.diagramType) {
          failed.push({ file: f, line: startLine, error: '解析未返回 diagramType' });
        }
      } catch (e) {
        failed.push({
          file: f,
          line: startLine,
          error: String(e && e.message ? e.message : e).split('\n')[0].slice(0, 200),
        });
      }
      continue;
    }
    if (inBlock) buf.push(l);
  }
}

console.log(JSON.stringify({ ok: total - failed.length, total, failed }));
process.exit(failed.length ? 1 : 0);
