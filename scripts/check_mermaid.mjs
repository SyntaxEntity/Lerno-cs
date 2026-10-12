// 用官方 mermaid 解析器校验所有 ```mermaid 代码块的真实语法
// 用法: node scripts/check_mermaid.mjs
// 依赖: 需先安装到 .tools （npm install --prefix .tools mermaid jsdom）
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';

const TOOLS = resolve('.tools/node_modules');
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

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (['.tools', 'node_modules', '.git', 'parts', 'scripts'].includes(name)) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (name.endsWith('.md')) out.push(p);
  }
  return out;
}

const files = walk('408');
let total = 0, failed = 0, notFlow = 0;
for (const f of files) {
  const lines = readFileSync(f, 'utf8').split('\n');
  let inBlock = false, buf = [], startLine = 0;
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (!inBlock && /^\s*```mermaid\s*$/.test(l)) { inBlock = true; buf = []; startLine = i + 2; continue; }
    if (inBlock && l.trim() === '```') {
      inBlock = false;
      total++;
      try {
        const r = await mermaid.parse(buf.join('\n'));
        if (!r || !r.diagramType) { failed++; console.log(`✗ ${f}:${startLine} 解析未返回 diagramType`); }
      } catch (e) {
        failed++;
        console.log(`✗ ${f}:${startLine} ${String(e.message || e).split('\n')[0].slice(0, 120)}`);
      }
      continue;
    }
    if (inBlock) buf.push(l);
  }
}
console.log(`\nmermaid 图总数 ${total}，解析失败 ${failed}`);
process.exit(failed ? 1 : 0);
