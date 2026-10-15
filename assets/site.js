/* 408 速成复习资料 · 站点外壳行为
 * ---------------------------------------------------------------------------
 * ⚠️ 临时实现（占位）：契约要求本文件与 math2-kaoyan 的 assets/site.js **逐字一致**。
 *    math2 尚未抽出该文件，故此处按同一份契约（../PLAN-对齐与改版.md 2.4）先实现
 *    站点必需的行为，等数学二抽出后**整体逐字替换本文件**，不要在此长期维护两份。
 *
 * 本文件承担的行为（契约钦定）：
 *   - 侧栏关键词筛选、滚动高亮当前章节（.cur）
 *   - 当前章六段锚点高亮
 *   - 顶栏「搜索」按钮 → 聚焦侧栏筛选框
 *   - 进度条、回到顶部、代码复制
 *   - 深色模式：切换 html.dark，选择存 localStorage
 *   - 键盘翻章：← / k 上一章，→ / j 下一章
 */
(function () {
  'use strict';

  var root = document.documentElement;

  /* ---------- 侧栏筛选 ---------- */
  var q = document.getElementById('q');
  var filter = function (v) {
    v = (v || '').trim().toLowerCase();
    document.querySelectorAll('.site-sidebar details.grp').forEach(function (d) {
      var any = false;
      d.querySelectorAll('a.item').forEach(function (a) {
        var hit = !v || a.textContent.toLowerCase().indexOf(v) >= 0;
        a.style.display = hit ? '' : 'none';
        if (hit) any = true;
      });
      d.style.display = (any || !v) ? '' : 'none';
      if (v && any) d.open = true;
    });
  };
  if (q) q.addEventListener('input', function () { filter(this.value); });

  /* 顶栏搜索按钮：聚焦侧栏筛选框（窄屏先把抽屉打开） */
  var tbSearch = document.querySelector('.tb-search');
  if (tbSearch) tbSearch.addEventListener('click', function () {
    var sb = document.querySelector('.site-sidebar');
    if (sb && window.innerWidth <= 1000) sb.classList.add('open');
    if (q) { q.focus(); q.select(); }
  });

  /* ---------- 进度条 + 回到顶部 ---------- */
  var bar = document.getElementById('bar'), top = document.querySelector('.totop');
  function onScroll() {
    var h = root, y = h.scrollTop || document.body.scrollTop || 0;
    var max = h.scrollHeight - h.clientHeight;
    if (bar) bar.style.width = (max > 0 ? (y / max) * 100 : 0) + '%';
    if (top) top.classList.toggle('on', y > 500);
  }
  addEventListener('scroll', onScroll, { passive: true });
  onScroll();
  if (top) top.addEventListener('click', function () {
    scrollTo({ top: 0, behavior: 'smooth' });
  });

  /* ---------- 代码复制 ---------- */
  document.querySelectorAll('.codebox').forEach(function (box) {
    var btn = box.querySelector('button'), pre = box.querySelector('pre');
    if (!btn || !pre) return;
    btn.addEventListener('click', function () {
      var t = pre.innerText;
      var done = function () {
        btn.textContent = '已复制';
        setTimeout(function () { btn.textContent = '复制'; }, 1200);
      };
      if (navigator.clipboard) navigator.clipboard.writeText(t).then(done, done);
      else {
        var ta = document.createElement('textarea');
        ta.value = t; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); } catch (e) {}
        ta.remove(); done();
      }
    });
  });

  /* ---------- 深色模式（html.dark + localStorage） ---------- */
  var tb = document.getElementById('theme'), saved = null;
  try { saved = localStorage.getItem('dsh-408-theme'); } catch (e) {}
  /* 用 typeof 守卫：matchMedia 在旧浏览器/无头环境缺失时，裸引用会抛
     ReferenceError，把本文件后面所有行为（主题、抽屉、翻章）一起带崩。 */
  if (!saved && typeof matchMedia === 'function'
      && matchMedia('(prefers-color-scheme:dark)').matches) saved = 'dark';
  if (saved === 'dark') root.classList.add('dark');
  function syncThemeBtn() {
    if (tb) tb.textContent = root.classList.contains('dark') ? '☀' : '☾';
  }
  syncThemeBtn();
  if (tb) tb.addEventListener('click', function () {
    var dark = root.classList.toggle('dark');
    syncThemeBtn();
    try { localStorage.setItem('dsh-408-theme', dark ? 'dark' : 'light'); } catch (e) {}
  });

  /* ---------- 窄屏抽屉 ---------- */
  var mb = document.getElementById('menu'), sb = document.querySelector('.site-sidebar');
  if (mb && sb) {
    mb.addEventListener('click', function () { sb.classList.toggle('open'); });
    sb.addEventListener('click', function (e) {
      if (e.target.tagName === 'A' && window.innerWidth <= 1000) sb.classList.remove('open');
    });
  }

  /* ---------- 目录高亮：当前章节 + 当前六段 ---------- */
  (function () {
    var items = [].slice.call(document.querySelectorAll('.site-sidebar a.item'));
    if (!items.length) return;
    var secLinks = [].slice.call(document.querySelectorAll('.site-sidebar a.sec-link'));
    var secs = secLinks.map(function (a) {
      return document.getElementById((a.getAttribute('href') || '').split('#')[1] || '');
    });
    function mark() {
      var y = scrollY + 130, best = -1;
      secs.forEach(function (el, i) {
        if (el && (el.offsetTop <= y || i === 0)) best = i;
      });
      secLinks.forEach(function (a, i) { a.classList.toggle('cur', i === best); });
      items.forEach(function (a) { a.classList.add('cur'); });
    }
    if (secs.some(Boolean)) {
      addEventListener('scroll', mark, { passive: true });
      mark();
    }
  })();

  /* ---------- 键盘翻章：← / k 上一章，→ / j 下一章 ---------- */
  (function () {
    var prev = document.querySelector('.chapter-nav .cn-prev');
    var next = document.querySelector('.chapter-nav .cn-next');
    addEventListener('keydown', function (e) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      var t = e.target || {};
      var tag = (t.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || t.isContentEditable) return;
      var key = e.key;
      if (key === 'ArrowLeft' || key === 'k') {
        if (prev) { location.href = prev.getAttribute('href'); }
      } else if (key === 'ArrowRight' || key === 'j') {
        if (next) { location.href = next.getAttribute('href'); }
      }
    });
  })();
})();
