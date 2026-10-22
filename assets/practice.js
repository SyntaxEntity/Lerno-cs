/* 练习页（408 特有页面，PLAN-对齐与改版 §2.3.1.A）——路由骨架。
 *
 * M2 范围：hash 路由 + 8 个视图的空壳 + 题库就绪状态展示。
 * M3 接入：今日计划、组卷、答题判分、错题本、模拟考、学习报告、设置与导出。
 *
 * 约定：
 *   - 不写 fetch/XHR/WebSocket（整站离线，且 F32 会静态断言）；
 *   - 数据只来自 window.LERNO_QUIZ（assets/quiz-data.js），状态在 M3 才写 localStorage；
 *   - 样式全在 assets/practice.css，本文件不注入 <style>。
 */
(function () {
  'use strict';

  var VIEWS = {
    today: '今日',
    practice: '刷题',
    quiz: '答题',
    result: '结果',
    wrong: '错题本',
    mock: '模拟考',
    stats: '学习报告',
    settings: '设置'
  };

  var SITE_NAME = '408 速成复习资料';

  /** 题库（未加载时返回 null，由视图显式报出来，不静默） */
  function bank() {
    var data = window.LERNO_QUIZ;
    return (data && Array.isArray(data.questions)) ? data.questions : null;
  }

  function bankLine() {
    var qs = bank();
    if (!qs) {
      return '<p class="pv-alert">题库数据未加载（assets/quiz-data.js 缺失或解析失败）。' +
        '请运行 <code>python3 scripts/build_quiz.py</code> 后刷新。</p>';
    }
    var topics = {};
    qs.forEach(function (q) {
      if (q && q.topic) topics[q.topic] = true;
    });
    return '<p class="pv-note">题库已就绪：<strong>' + qs.length + '</strong> 题，覆盖 ' +
      '<strong>' + Object.keys(topics).length + '</strong> 个知识点。</p>';
  }

  function card(title, text, extra) {
    return '<section class="pv-card"><h2 class="pv-h2">' + title + '</h2>' +
      '<p class="pv-text">' + text + '</p>' + (extra || '') + '</section>';
  }

  function viewHtml(name) {
    switch (name) {
      case 'today':
        return card('今日计划', '每天只做三件事：完成 5 道热身题、精读 2 个知识点、做 1 组练习。', 
          bankLine() +
          '<ul class="pv-list">' +
          '<li>完成 5 道热身题 —— 先让手感回来</li>' +
          '<li>精读 2 个知识点 —— 从侧栏或全科合集进入</li>' +
          '<li>完成 1 组练习 —— 按知识点或范围组卷</li>' +
          '</ul>' +
          '<p class="pv-note">今日进度、连续天数与热力图将在 M3 接入。</p>');
      case 'practice':
        return card('刷题', '按科目、知识点、题量与范围组卷；答完即时判分，答错自动进错题本。',
          '<p class="pv-note">组卷表单与判分将在 M3 接入。</p>');
      case 'quiz':
        return card('答题', '题干、选项、即时反馈（练习）或交卷后统一解析（模拟）。',
          '<p class="pv-note">答题界面将在 M3 接入。</p>');
      case 'result':
        return card('结果', '得分、正确率、用时与逐题回顾。',
          '<p class="pv-note">结果页将在 M3 接入。</p>');
      case 'wrong':
        return card('错题本', '答错的题自动收录；连续答对 2 次自动标记为已掌握。',
          '<p class="pv-note">错题本将在 M3 接入。</p>');
      case 'mock':
        return card('模拟考', '限时、无即时反馈、交卷后统一解析。',
          '<p class="pv-note">三种模拟模式（全科 20 题 / 单科 15 题 / 薄弱点 10 题）将在 M3 接入。</p>');
      case 'stats':
        return card('学习报告', '连续天数、累计作答、正确率、四科掌握度与 12 周热力图。',
          '<p class="pv-note">统计图表将在 M3 接入。</p>');
      case 'settings':
        return card('设置', '称呼、考试日期、每日目标，以及导出 / 导入 / 清空本机数据。',
          '<p class="pv-note">设置与数据管理将在 M3 接入；数据只保存在本机浏览器。</p>');
      default:
        return card('今日计划', '每天只做三件事。', bankLine());
    }
  }

  function routeName() {
    var raw = (window.location.hash || '').replace(/^#\/?/, '');
    var name = raw.split('?')[0].split('/')[0];
    return Object.prototype.hasOwnProperty.call(VIEWS, name) ? name : 'today';
  }

  function setActive(name) {
    var links = document.querySelectorAll('.site-sidebar .sb-chap[data-view]');
    Array.prototype.forEach.call(links, function (a) {
      var on = a.getAttribute('data-view') === name;
      if (on) {
        a.classList.add('cur');
        a.setAttribute('aria-current', 'page');
      } else {
        a.classList.remove('cur');
        a.removeAttribute('aria-current');
      }
    });
  }

  function render() {
    var host = document.getElementById('practice-view');
    if (!host) {
      return;                       // 不是练习页（脚本被别的页面引入时直接退出）
    }
    var name = routeName();
    host.innerHTML = viewHtml(name);
    setActive(name);
    document.title = VIEWS[name] + ' · 练习 · ' + SITE_NAME;
  }

  function start() {
    if (!document.getElementById('practice-view')) {
      return;
    }
    if (!window.location.hash) {
      // 默认视图用 replaceState，避免在浏览历史里塞一条多余记录
      try {
        window.history.replaceState(null, '', '#/today');
      } catch (e) { /* file:// 下历史 API 受限，忽略即可，路由仍可用 */ }
    }
    window.addEventListener('hashchange', render);
    render();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
