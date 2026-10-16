/* 来源：Lerno-math/数学二/assets/site.js（冻结于 9fec899），**逐字复制**。
 *
 * 这是两个项目共用的行为契约实现（PLAN-对齐与改版 §2.4.1）。
 * 正文（本注记之后的全部内容）必须与上游**逐字节一致**：
 *   sha256 = c368945915d805ec1b43c849f653ae1d197fb0b0fcb3338276db3968306bbbab
 * 校验由 validate.py 的 F25 强制：改了正文而没同步上游，会直接报错。
 * 不要在这里单独改行为——要改先改契约，再同步两个项目。
 */
/* 外壳行为脚本 —— 数学二与 408 两个项目**共用同一份**（PLAN-对齐与改版 §2.4）。
 *
 * 为什么单独成文件
 * ----------------
 * 以前这些代码内联在每个页面里（19 页 × 4.3 KB ≈ 82 KB 冗余），而且两个项目
 * 各写一套、改一处忘一处。抽成外置文件后：页面只引一次，两个项目共用同一份实现。
 *
 * 引入方式
 * --------
 *   <head> 里**同步**引入（不要 defer）：主题类要在首屏绘制前就定下来，否则会闪白。
 *   路径按页面深度现算：章节页写 ../assets/site.js，根页写 assets/site.js。
 *
 * 契约（只依赖下面这些类名/属性，不依赖任何项目特有的 id）
 * --------------------------------------------------------
 *   html.dark                  深色模式开关（类名必须逐字一致；配色由各项目 token 决定）
 *   localStorage['kaoyan-theme']  主题记忆：'dark' / 'light'；没存过则跟随系统
 *   .theme-toggle              主题切换按钮
 *   .nav-toggle                移动端目录抽屉开关（点击给 <body> 加 .navopen）
 *   .read-progress             顶部阅读进度条
 *   .to-top                    回到顶部按钮
 *   .site-sidebar              侧栏容器
 *   .sb-filter                 侧栏关键词筛选输入框
 *   .sb-group / .sb-group-t    侧栏分组与组标题
 *   .sb-chap                   侧栏里的章节链接（筛选的对象）
 *   .site-sidebar .toclink     侧栏小节锚点（滚动高亮 + 平滑跳转）
 *   .tb-search                 顶栏搜索按钮
 *   body[data-prev|data-next]  键盘翻章目标（← / k 上一章，→ / j 下一章）
 *   .mermaid / window.mermaid  mermaid 图容器与运行时
 *   window.renderMathInElement KaTeX auto-render（缺失时页面明确提示）
 *
 * 两个项目都按这份契约写 DOM；改本文件等于同时改两个项目，改完必须重跑
 * `数学二/scripts/test_site_js.mjs`（jsdom 行为测试）确认没把契约改坏。
 */
(function () {
  'use strict';

  var THEME_KEY = 'kaoyan-theme';
  var root = document.documentElement;

  // ------------------------------------------------------------------
  // 1) 主题：同步执行，必须在首屏绘制前定下来
  // ------------------------------------------------------------------
  function storedTheme() {
    try { return localStorage.getItem(THEME_KEY); } catch (e) { return null; }
  }

  function systemTheme() {
    return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)
      ? 'dark' : 'light';
  }

  function applyTheme(t) {
    root.classList.toggle('dark', t === 'dark');
  }

  applyTheme(storedTheme() || systemTheme());

  // 用户没手动选过时，跟随系统变化
  try {
    if (window.matchMedia) {
      var mq = window.matchMedia('(prefers-color-scheme: dark)');
      var onSys = function () { if (!storedTheme()) applyTheme(systemTheme()); };
      if (mq.addEventListener) mq.addEventListener('change', onSys);
      else if (mq.addListener) mq.addListener(onSys);
    }
  } catch (e) { /* 老浏览器：忽略，主题仍可用 */ }

  // ------------------------------------------------------------------
  // 其余行为等 DOM 就绪
  // ------------------------------------------------------------------
  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }

  ready(function () {
    var d = document;

    // 2) 主题切换
    Array.prototype.forEach.call(d.querySelectorAll('.theme-toggle'), function (btn) {
      btn.addEventListener('click', function () {
        var next = root.classList.contains('dark') ? 'light' : 'dark';
        applyTheme(next);
        try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
      });
    });

    // 3) 移动端目录抽屉
    Array.prototype.forEach.call(d.querySelectorAll('.nav-toggle'), function (btn) {
      btn.addEventListener('click', function () { d.body.classList.toggle('navopen'); });
    });

    // 4) 阅读进度条
    var bar = d.querySelector('.read-progress');
    if (bar) {
      var upd = function () {
        var h = root.scrollHeight - window.innerHeight;
        bar.style.width = (h > 0 ? (window.scrollY / h) * 100 : 0) + '%';
      };
      window.addEventListener('scroll', upd, { passive: true });
      window.addEventListener('resize', upd);
      upd();
    }

    // 5) 回到顶部
    Array.prototype.forEach.call(d.querySelectorAll('.to-top'), function (btn) {
      btn.addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
      var show = function () { btn.style.display = window.scrollY > 500 ? '' : 'none'; };
      window.addEventListener('scroll', show, { passive: true });
      show();
    });

    // 6) 侧栏关键词筛选：按 .sb-chap 的文本过滤，整组都空了就把组标题也收起来
    var filter = d.querySelector('.sb-filter');
    if (filter) {
      var groups = d.querySelectorAll('.sb-group');
      filter.addEventListener('input', function () {
        var v = filter.value.trim().toLowerCase();
        Array.prototype.forEach.call(groups, function (g) {
          var shown = 0;
          Array.prototype.forEach.call(g.querySelectorAll('.sb-chap'), function (a) {
            var hit = !v || (a.textContent || '').toLowerCase().indexOf(v) !== -1;
            a.style.display = hit ? '' : 'none';
            if (hit) shown++;
          });
          g.style.display = (v && !shown) ? 'none' : '';
        });
      });
    }

    // 7) 侧栏滚动高亮当前小节
    var links = [].slice.call(d.querySelectorAll('.site-sidebar a.toclink'));
    if (links.length) {
      var targets = links.map(function (a) {
        return d.getElementById((a.getAttribute('href') || '').slice(1));
      });
      var sync = function () {
        var y = window.scrollY + 120, best = -1;
        targets.forEach(function (t, i) { if (t && t.offsetTop <= y) best = i; });
        links.forEach(function (a, i) { a.classList.toggle('cur', i === best); });
      };
      window.addEventListener('scroll', sync, { passive: true });
      window.addEventListener('resize', sync);
      sync();
    }

    // 8) 键盘翻章：← / k 上一章，→ / j 下一章
    var prev = d.body.getAttribute('data-prev');
    var next = d.body.getAttribute('data-next');
    d.addEventListener('keydown', function (e) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      var t = e.target;
      if (t && t.matches && t.matches('input, textarea, select, [contenteditable]')) return;
      if (e.key === 'ArrowLeft' || e.key === 'k') { if (prev) location.href = prev; }
      if (e.key === 'ArrowRight' || e.key === 'j') { if (next) location.href = next; }
    });

    // 9) 顶栏搜索按钮：P2 先聚焦侧栏筛选框（不做一个点了没反应的死按钮）。
    //    P3 的离线全文检索落地后，把这里换成检索面板即可，按钮类名不变。
    Array.prototype.forEach.call(d.querySelectorAll('.tb-search'), function (btn) {
      btn.addEventListener('click', function () {
        var f = d.querySelector('.sb-filter');
        if (f) { f.focus(); f.select && f.select(); return; }
        // 侧栏被抽屉收起时先展开，再聚焦
        d.body.classList.add('navopen');
        var f2 = d.querySelector('.sb-filter');
        if (f2) f2.focus();
      });
    });

    // 10) KaTeX：渲染公式；运行时缺失就明确提示，而不是留一堆 $...$
    if (typeof window.renderMathInElement !== 'function') {
      // 用 textContent 而不是 innerText：后者在部分环境（含无头测试用的 jsdom）
      // 不存在，会让"该提示却没提示"变成静默失效——正是本项目最忌讳的那种失败。
      var hasMath = /\$[^$\n]+\$/.test(d.body.textContent || '');
      var host = d.querySelector('main') || d.body;
      if (hasMath) {
        var p = d.createElement('p');
        p.className = 'missing';
        p.textContent = '未加载到公式渲染器（katex/），页面里的 LaTeX 公式以源码显示。'
          + '请确认 katex/ 目录与 assets/site.js 的相对路径正确。';
        host.insertBefore(p, host.firstChild);
      }
    } else {
      window.renderMathInElement(d.body, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '$', right: '$', display: false }
        ],
        throwOnError: false,
        ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']
      });
    }

    // 11) mermaid：逐图渲染；运行时缺失或单图失败都要看得见
    var nodes = d.querySelectorAll('.mermaid');
    if (nodes.length) {
      if (!window.mermaid) {
        Array.prototype.forEach.call(nodes, function (el) {
          el.insertAdjacentHTML('beforebegin',
            '<p class="missing">未加载到 mermaid 运行时（assets/mermaid.min.js 不在预期位置），'
            + '下图暂以源码显示，可复制到任意 mermaid 编辑器查看。</p>');
          var pre = d.createElement('pre');
          var code = d.createElement('code');
          code.textContent = el.textContent;
          pre.appendChild(code);
          el.innerHTML = '';
          el.appendChild(pre);
        });
      } else {
        window.mermaid.initialize({
          startOnLoad: false, securityLevel: 'loose', theme: 'neutral',
          flowchart: { useMaxWidth: true }, state: { useMaxWidth: true }
        });
        Array.prototype.forEach.call(nodes, function (el, i) {
          window.mermaid.render('mmd-' + i, el.textContent.trim()).then(function (r) {
            el.innerHTML = r.svg;
          }).catch(function (e) {
            el.innerHTML = '<p class="missing">该图渲染失败：' + e.message + '</p>';
          });
        });
      }
    }
  });
})();
