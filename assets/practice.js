/* 练习闭环（408 特有页面，PLAN-对齐与改版 §2.3.1.A）
 *
 * M3：今日计划 / 组卷 / 答题判分 / 错题本 / 掌握度 / 学习报告 / 设置与导出导入。
 *
 * 约定（与契约和 D-06 一致）：
 *   - 不写 fetch / XHR / WebSocket：整站离线，数据只来自 window.LERNO_QUIZ；
 *   - 状态只写本机 localStorage（键 lerno-quiz-v1）；不可用时降级为内存并**明示**；
 *   - 不静默失败：题库缺失、数据损坏、存储不可用、导入非法，都会在页面上说出来；
 *   - 掌握度用**累计**答对（≥4 掌握、≥2 复习中），错题用**连续**答对 2 次判掌握——
 *     两者语义不同，文案里写清楚（照抄原型会把「累计」写成「连续」）。
 */
(function () {
  'use strict';

  // =====================================================================
  // 常量
  // =====================================================================
  var KEY = 'lerno-quiz-v1';
  var CORRUPT_KEY = 'lerno-quiz-v1.corrupt';
  var MAX_ATTEMPTS = 3000;
  var MAX_SESSIONS = 50;
  var LEVEL_LABEL = ['未开始', '学习中', '复习中', '已掌握'];
  var MODE_LABEL = { practice: '练习', mock: '模拟' };
  var MOCK_MODES = {
    all: { title: '全科模拟', count: 20, duration: 30 * 60, desc: '四科交叉组卷，模拟真实考试的切换节奏。' },
    subject: { title: '单科冲刺', count: 15, duration: 20 * 60, desc: '聚焦一科，适合考前集中突破。' },
    weak: { title: '薄弱点挑战', count: 10, duration: 15 * 60, desc: '从最薄弱的考点抽题，专门补短板。' }
  };
  var DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

  // =====================================================================
  // 小工具
  // =====================================================================
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function dateKey(d) {
    d = d || new Date();
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }
  function addDays(d, n) {
    var x = new Date(d.getTime());
    x.setDate(x.getDate() + n);
    return x;
  }
  function parseDate(s) {
    var p = String(s || '').split('-');
    return new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
  }
  function daysUntil(s) {
    return Math.round((parseDate(s) - parseDate(dateKey())) / 86400000);
  }
  function clamp(n, lo, hi) { return Math.min(hi, Math.max(lo, n)); }
  function pct(a, b) { return b ? Math.round(a * 100 / b) : 0; }
  function nowIso() { return new Date().toISOString(); }
  function fmtClock(sec) {
    sec = Math.max(0, Math.floor(sec));
    return pad(Math.floor(sec / 60)) + ':' + pad(sec % 60);
  }
  function fmtDuration(sec) {
    sec = Math.max(0, Math.round(sec));
    if (sec < 60) return sec + ' 秒';
    return Math.floor(sec / 60) + ' 分 ' + (sec % 60) + ' 秒';
  }
  function shuffle(list) {
    var a = list.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = a[i]; a[i] = a[j]; a[j] = t;
    }
    return a;
  }

  // =====================================================================
  // 存储
  // =====================================================================
  var notices = [];
  var storageOK = true;
  try {
    window.localStorage.setItem('__lerno_probe', '1');
    window.localStorage.removeItem('__lerno_probe');
  } catch (e) {
    storageOK = false;
    notices.push('浏览器禁用了 localStorage：本次数据只保存在内存里，刷新会丢失；请用「设置 → 导出」备份。');
  }

  function defaultState() {
    return {
      v: 1,
      profile: { name: '', examDate: '2026-12-19', dailyGoal: 20 },
      points: {},
      attempts: [],
      wrong: {},
      activity: {},
      sessions: []
    };
  }

  function migrate(raw) {
    var s = defaultState();
    if (!raw || typeof raw !== 'object') return s;
    if (raw.profile && typeof raw.profile === 'object') {
      s.profile.name = String(raw.profile.name || '');
      s.profile.examDate = DATE_RE.test(String(raw.profile.examDate || '')) ? raw.profile.examDate : s.profile.examDate;
      s.profile.dailyGoal = clamp(Number(raw.profile.dailyGoal) || 20, 5, 100);
    }
    if (raw.points && typeof raw.points === 'object') s.points = raw.points;
    if (Array.isArray(raw.attempts)) s.attempts = raw.attempts.slice(-MAX_ATTEMPTS);
    if (raw.wrong && typeof raw.wrong === 'object') s.wrong = raw.wrong;
    if (raw.activity && typeof raw.activity === 'object') s.activity = raw.activity;
    if (Array.isArray(raw.sessions)) s.sessions = raw.sessions.slice(0, MAX_SESSIONS);
    return s;
  }

  function load() {
    if (!storageOK) return defaultState();
    var raw = null;
    try {
      raw = window.localStorage.getItem(KEY);
    } catch (e) {
      storageOK = false;
      notices.push('读取本地数据失败，已切换为内存模式。');
      return defaultState();
    }
    if (!raw) return defaultState();
    try {
      return migrate(JSON.parse(raw));
    } catch (e) {
      // 不静默丢弃：先把原始串备份到另一个键，再按空数据启动；备份失败也要如实说明
      var backedUp = false;
      try {
        window.localStorage.setItem(CORRUPT_KEY, raw);
        window.localStorage.removeItem(KEY);
        backedUp = true;
      } catch (e2) {
        backedUp = false;
      }
      notices.push('本地数据无法解析' +
        (backedUp ? '（原数据已备份到 ' + CORRUPT_KEY + '）' : '（备份也失败，原数据已被清掉）') +
        '，已按空数据启动。');
      return defaultState();
    }
  }

  function save() {
    if (!storageOK) return;
    try {
      window.localStorage.setItem(KEY, JSON.stringify(state));
    } catch (e) {
      storageOK = false;
      notices.push('保存失败（本地存储已满或被禁用）：之后的改动只在内存里。');
    }
  }

  var state = load();

  // =====================================================================
  // 题库与元数据
  // =====================================================================
  var qmap = null;

  function bank() {
    var d = window.LERNO_QUIZ;
    return (d && Array.isArray(d.questions)) ? d.questions : null;
  }
  function subjectsMeta() {
    var d = window.LERNO_QUIZ;
    return (d && Array.isArray(d.subjects)) ? d.subjects : null;
  }
  function questionById(id) {
    if (!qmap) {
      qmap = {};
      var qs = bank() || [];
      for (var i = 0; i < qs.length; i++) qmap[qs[i].id] = qs[i];
    }
    return qmap[id] || null;
  }
  function subjectName(key) {
    var s = (subjectsMeta() || []).filter(function (x) { return x.key === key; })[0];
    return s ? s.name : key;
  }
  function topicTitle(subjectKey, slug) {
    var list = subjectsMeta() || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i].key !== subjectKey) continue;
      for (var j = 0; j < list[i].topics.length; j++) {
        if (list[i].topics[j].slug === slug) return list[i].topics[j].title;
      }
    }
    return slug;
  }
  function topicHref(subjectKey, slug) {
    var s = (subjectsMeta() || []).filter(function (x) { return x.key === subjectKey; })[0];
    return s ? s.dir + '/' + slug + '.html' : 'index.html';
  }

  // =====================================================================
  // 状态模型
  // =====================================================================
  function pointKey(subject, topic) { return subject + '/' + topic; }

  function pointState(key) {
    var p = state.points[key];
    if (!p || typeof p !== 'object') {
      p = state.points[key] = { level: 0, correct: 0, wrong: 0, lastSeen: null, lastReviewed: null };
    }
    p.level = clamp(Number(p.level) || 0, 0, 3);
    p.correct = Number(p.correct) || 0;
    p.wrong = Number(p.wrong) || 0;
    return p;
  }

  function touchActivity(field, n) {
    var k = dateKey();
    var a = state.activity[k];
    if (!a || typeof a !== 'object') a = state.activity[k] = { answered: 0, reviews: 0, sessions: 0 };
    a[field] = (Number(a[field]) || 0) + n;
    return a;
  }

  function todayActivity() {
    var a = state.activity[dateKey()];
    return {
      answered: Number(a && a.answered) || 0,
      reviews: Number(a && a.reviews) || 0,
      sessions: Number(a && a.sessions) || 0
    };
  }

  function streakDays() {
    var n = 0;
    var d = new Date();
    while (n < 3650) {
      var a = state.activity[dateKey(d)];
      if (!a || (!Number(a.answered) && !Number(a.reviews))) break;
      n += 1;
      d = addDays(d, -1);
    }
    return n;
  }

  function markReviewed(key) {
    pointState(key).lastReviewed = dateKey();
    touchActivity('reviews', 1);
    save();
    toast('已标记「已复习」：' + key.split('/')[1]);
    render();
  }

  /**
   * 记录一次作答。selected 为 null 表示未作答（模拟考跳过）：
   * 只进 attempts 供统计，不计入知识点掌握，也不进错题本。
   */
  function recordAnswer(q, selected, mode) {
    var answered = typeof selected === 'number';
    var ok = answered && selected === q.answer;
    state.attempts.push({
      qid: q.id, subject: q.subject, topic: q.topic, selected: answered ? selected : null,
      correct: ok, mode: mode, at: nowIso()
    });
    if (state.attempts.length > MAX_ATTEMPTS) {
      state.attempts.splice(0, state.attempts.length - MAX_ATTEMPTS);
    }
    if (answered) {
      var ps = pointState(pointKey(q.subject, q.topic));
      ps.lastSeen = nowIso();
      if (ok) {
        ps.correct += 1;
        // 累计（不是连续）：≥4 次 → 已掌握；≥2 次 → 复习中
        ps.level = Math.max(ps.level, ps.correct >= 4 ? 3 : ps.correct >= 2 ? 2 : 1);
      } else {
        ps.wrong += 1;
        ps.level = Math.min(ps.level, 1);
      }
      var w = state.wrong[q.id];
      if (ok) {
        if (w && !w.mastered) {
          w.streak = (Number(w.streak) || 0) + 1;
          w.lastAt = nowIso();
          w.lastSelected = selected;
          if (w.streak >= 2) w.mastered = true;
        }
      } else {
        state.wrong[q.id] = {
          count: ((w && Number(w.count)) || 0) + 1,
          streak: 0,
          mastered: false,
          lastAt: nowIso(),
          lastSelected: selected
        };
      }
      touchActivity('answered', 1);
    }
    save();
    return ok;
  }

  function recordSession(sess, answered, correct) {
    state.sessions.unshift({
      id: 's' + Date.now(),
      mode: sess.mode,
      startedAt: new Date(sess.startedAt).toISOString(),
      endedAt: nowIso(),
      answered: answered,
      correct: correct,
      total: sess.ids.length,
      durationSec: Math.max(1, Math.round((Date.now() - sess.startedAt) / 1000)),
      questionIds: sess.ids.slice()
    });
    if (state.sessions.length > MAX_SESSIONS) state.sessions.length = MAX_SESSIONS;
    touchActivity('sessions', 1);
    save();
  }

  // =====================================================================
  // 组卷
  // =====================================================================
  function poolBy(filters) {
    return (bank() || []).filter(function (q) {
      if (filters.subject && filters.subject !== 'all' && q.subject !== filters.subject) return false;
      if (filters.topic && filters.topic !== 'all' && q.topic !== filters.topic) return false;
      return true;
    });
  }

  function weakRank(q) {
    var ps = pointState(pointKey(q.subject, q.topic));
    // 越小越弱：等级低、答对少、答错多、很久没做
    return ps.level * 1000 + ps.correct * 10 - ps.wrong * 20 - (ps.lastSeen ? 1 : 50);
  }

  function buildPractice(filters) {
    var pool = poolBy(filters);
    var picked = [];
    if (filters.scope === 'wrong') {
      picked = Object.keys(state.wrong)
        .filter(function (id) { return !state.wrong[id].mastered; })
        .map(questionById).filter(Boolean)
        .filter(function (q) {
          if (filters.subject !== 'all' && q.subject !== filters.subject) return false;
          if (filters.topic !== 'all' && q.topic !== filters.topic) return false;
          return true;
        });
    } else if (filters.scope === 'coverage') {
      var seen = {};
      pool.forEach(function (q) { seen[q.subject + '/' + q.topic] = true; });
      Object.keys(seen).forEach(function (key) {
        var group = pool.filter(function (q) { return q.subject + '/' + q.topic === key; });
        if (group.length) picked.push(group[Math.floor(Math.random() * group.length)]);
      });
    } else if (filters.scope === 'weak') {
      picked = pool.slice().sort(function (a, b) { return weakRank(a) - weakRank(b); }).slice(0, filters.count);
    } else {
      picked = pool.slice().slice(0, filters.count);
    }
    if (filters.scope !== 'coverage') {
      if (filters.order === 'random') picked = shuffle(picked);
      else picked.sort(function (a, b) { return a.id < b.id ? -1 : 1; });
    } else if (filters.order === 'random') {
      picked = shuffle(picked);
    }
    return picked.map(function (q) { return q.id; });
  }

  function buildMock(mode, subject) {
    var cfg = MOCK_MODES[mode];
    var pool = poolBy({ subject: mode === 'subject' ? subject : 'all', topic: 'all' });
    var picked = mode === 'weak'
      ? pool.slice().sort(function (a, b) { return weakRank(a) - weakRank(b); })
      : shuffle(pool);
    return { ids: picked.slice(0, cfg.count).map(function (q) { return q.id; }), duration: cfg.duration };
  }

  // =====================================================================
  // 会话
  // =====================================================================
  var session = null;
  var lastResult = null;
  var timerId = null;
  var ui = {
    practice: { subject: 'all', topic: 'all', count: 10, scope: 'all', order: 'random' },
    wrong: { tab: 'pending', subject: 'all' },
    mock: { mode: 'all', subject: 'ds' }
  };

  function clearTimer() {
    if (timerId) { window.clearInterval(timerId); timerId = null; }
  }

  function startSession(mode, ids, durationSec) {
    if (!ids.length) { toast('没有可用的题目'); return; }
    clearTimer();
    session = {
      mode: mode, ids: ids, index: 0, answers: {}, flags: {},
      startedAt: Date.now(), durationSec: durationSec || 0
    };
    lastResult = null;
    go('quiz');
  }

  function currentQuestion() {
    return session ? questionById(session.ids[session.index]) : null;
  }

  function answeredCount() {
    return session ? session.ids.filter(function (id) { return typeof session.answers[id] === 'number'; }).length : 0;
  }

  function remainingSeconds() {
    if (!session || !session.durationSec) return 0;
    return Math.max(0, session.durationSec - Math.round((Date.now() - session.startedAt) / 1000));
  }

  function pickOption(i) {
    if (!session) return;
    var q = currentQuestion();
    if (!q) return;
    if (session.mode === 'practice' && session.answers[q.id] !== undefined) return;
    if (i < 0 || i >= q.options.length) return;
    session.answers[q.id] = i;
    if (session.mode === 'practice') recordAnswer(q, i, 'practice');
    render();
  }

  function nextQuestion() {
    if (!session) return;
    if (session.index + 1 < session.ids.length) {
      session.index += 1;
      render();
      var host = document.getElementById('practice-view');
      if (host) host.scrollIntoView({ block: 'start' });
    } else if (session.mode === 'practice') {
      finishPractice();
    }
  }

  function prevQuestion() {
    if (session && session.index > 0) { session.index -= 1; render(); }
  }

  function finishPractice() {
    if (!session) return;
    var answered = 0, correct = 0;
    session.ids.forEach(function (id) {
      var q = questionById(id);
      if (!q) return;
      var sel = session.answers[id];
      if (typeof sel === 'number') { answered += 1; if (sel === q.answer) correct += 1; }
    });
    recordSession(session, answered, correct);
    lastResult = {
      mode: session.mode, ids: session.ids.slice(), answers: Object.assign({}, session.answers),
      correct: correct, total: session.ids.length, startedAt: session.startedAt, endedAt: Date.now()
    };
    session = null;
    clearTimer();
    go('result');
  }

  function submitMock(auto) {
    if (!session) return;
    var unanswered = session.ids.length - answeredCount();
    if (!auto && unanswered > 0 &&
        !window.confirm('还有 ' + unanswered + ' 题未作答，未作答按错误计分。确定交卷？')) {
      return;
    }
    var correct = 0;
    session.ids.forEach(function (id) {
      var q = questionById(id);
      if (!q) return;
      var sel = typeof session.answers[id] === 'number' ? session.answers[id] : null;
      if (recordAnswer(q, sel, 'mock')) correct += 1;
    });
    recordSession(session, answeredCount(), correct);
    lastResult = {
      mode: session.mode, ids: session.ids.slice(), answers: Object.assign({}, session.answers),
      correct: correct, total: session.ids.length, startedAt: session.startedAt, endedAt: Date.now()
    };
    session = null;
    clearTimer();
    go('result');
  }

  function exitQuiz() {
    if (!session) { go('practice'); return; }
    var msg = session.mode === 'practice'
      ? '退出本次练习？已答过的题目已计入统计。'
      : '退出本次模拟？本次成绩不会记录。';
    if (!window.confirm(msg)) return;
    session = null;
    clearTimer();
    go('practice');
  }

  // =====================================================================
  // 渲染小部件
  // =====================================================================
  function noticeHtml() {
    var out = '';
    if (!bank()) {
      out += '<div class="pv-alert">题库未加载（assets/quiz-data.js 缺失或解析失败）：刷题、错题与统计不可用。' +
        '请运行 <code>python3 scripts/build_quiz.py</code> 后刷新。</div>';
    }
    if (notices.length) out += '<div class="pv-alert">' + esc(notices.slice(-2).join(' ')) + '</div>';
    return out;
  }

  function metric(value, label) {
    return '<div class="pv-metric"><b>' + esc(value) + '</b><span>' + esc(label) + '</span></div>';
  }

  function progressBar(value, max) {
    var p = max ? clamp(Math.round(value * 100 / max), 0, 100) : 0;
    return '<div class="pv-progress" role="progressbar" aria-valuenow="' + p +
      '" aria-valuemin="0" aria-valuemax="100"><i style="width:' + p + '%"></i></div>';
  }

  function heatmapHtml() {
    var cells = [];
    var end = new Date();
    for (var i = 83; i >= 0; i--) {
      var d = addDays(end, -i);
      var a = state.activity[dateKey(d)];
      var n = Number(a && a.answered) || 0;
      var level = n === 0 ? 0 : n < 5 ? 1 : n < 10 ? 2 : n < 20 ? 3 : 4;
      cells.push('<i data-level="' + level + '" title="' + dateKey(d) + '：' + n + ' 题"></i>');
    }
    return '<div class="pv-heat">' + cells.join('') + '</div>' +
      '<p class="pv-legend">最近 12 周，颜色越深当天做题越多（0 / 1–4 / 5–9 / 10–19 / 20+）</p>';
  }

  function barsHtml() {
    var days = [];
    var max = 1;
    for (var i = 6; i >= 0; i--) {
      var d = addDays(new Date(), -i);
      var a = state.activity[dateKey(d)];
      var n = Number(a && a.answered) || 0;
      days.push({ d: d, n: n });
      if (n > max) max = n;
    }
    return '<div class="pv-bars">' + days.map(function (x) {
      var h = Math.round(x.n * 100 / max);
      return '<div><i style="height:' + Math.max(2, h) + '%"></i><span>' +
        (x.d.getMonth() + 1) + '/' + x.d.getDate() + '</span></div>';
    }).join('') + '</div>';
  }

  function subjectBars() {
    return (subjectsMeta() || []).map(function (s) {
      var total = s.topics.length;
      var mastered = s.topics.filter(function (t) {
        return pointState(pointKey(s.key, t.slug)).level === 3;
      }).length;
      return '<div class="pv-subject-row"><div class="pv-subject-head"><span>' + esc(s.name) +
        '</span><span>' + mastered + '/' + total + ' 已掌握</span></div>' + progressBar(mastered, total) + '</div>';
    }).join('');
  }

  function recoHtml() {
    var list = [];
    (subjectsMeta() || []).forEach(function (s) {
      s.topics.forEach(function (t) {
        var ps = pointState(pointKey(s.key, t.slug));
        if (ps.level >= 3) return;
        list.push({ s: s, t: t, ps: ps });
      });
    });
    list.sort(function (a, b) {
      if (a.ps.level !== b.ps.level) return a.ps.level - b.ps.level;
      if (a.ps.wrong !== b.ps.wrong) return b.ps.wrong - a.ps.wrong;
      return (a.ps.lastSeen || '') < (b.ps.lastSeen || '') ? -1 : 1;
    });
    var top = list.slice(0, 5);
    if (!top.length) return '<p class="pv-empty">全部考点都已掌握。</p>';
    return '<ul class="pv-reco">' + top.map(function (x) {
      var key = pointKey(x.s.key, x.t.slug);
      return '<li><span class="pv-reco-main">' +
        '<span class="pv-reco-title"><a href="' + esc(topicHref(x.s.key, x.t.slug)) + '">' + esc(x.t.title) + '</a></span>' +
        '<span class="pv-reco-meta">' + esc(x.s.name) + ' · ' + LEVEL_LABEL[x.ps.level] +
        (x.ps.wrong ? ' · 错 ' + x.ps.wrong + ' 次' : '') + '</span></span>' +
        '<button class="pv-btn pv-btn-quiet pv-btn-sm" type="button" data-action="review-topic" data-key="' +
        esc(key) + '">标记已复习</button></li>';
    }).join('') + '</ul>';
  }

  function taskListHtml() {
    var a = todayActivity();
    var goal = clamp(Number(state.profile.dailyGoal) || 20, 5, 100);
    var tasks = [
      { title: '完成 5 道热身题', meta: '先让手感回来，再进入难点', done: a.answered >= 5, now: Math.min(a.answered, 5), need: 5 },
      { title: '精读 2 个知识点', meta: '点开知识点，回来在推荐清单里标记已复习', done: a.reviews >= 2, now: Math.min(a.reviews, 2), need: 2 },
      { title: '完成 1 组练习', meta: '一组 5–20 题，或一次限时模拟', done: a.sessions >= 1, now: Math.min(a.sessions, 1), need: 1 }
    ];
    var done = tasks.filter(function (t) { return t.done; }).length;
    return '<h2 class="pv-h2">今日三件事 <span class="pv-tag">' + done + ' / 3 已完成</span></h2>' +
      '<ul class="pv-tasks">' + tasks.map(function (t) {
        return '<li class="pv-task' + (t.done ? ' done' : '') + '">' +
          '<span class="pv-task-mark" aria-hidden="true">' + (t.done ? '✓' : '○') + '</span>' +
          '<span class="pv-task-main"><span class="pv-task-title">' + esc(t.title) + '</span>' +
          '<span class="pv-task-meta">' + esc(t.meta) + ' · ' + t.now + '/' + t.need + '</span></span></li>';
      }).join('') + '</ul>' +
      '<p class="pv-note">今日目标：' + a.answered + ' / ' + goal + ' 题</p>' + progressBar(a.answered, goal);
  }

  // =====================================================================
  // 视图
  // =====================================================================
  function renderToday() {
    var days = daysUntil(state.profile.examDate);
    var countdown = days > 0 ? days + ' 天' : days === 0 ? '就是今天' : '已结束';
    var mastered = 0, totalTopics = 0;
    (subjectsMeta() || []).forEach(function (s) {
      s.topics.forEach(function (t) {
        totalTopics += 1;
        if (pointState(pointKey(s.key, t.slug)).level === 3) mastered += 1;
      });
    });
    var attempts = state.attempts.length;
    var right = state.attempts.filter(function (x) { return x.correct; }).length;
    return noticeHtml() +
      '<h2 class="pv-h2">' + (days > 0 ? '距离初试还有 ' + days + ' 天' : '今日') + '</h2>' +
      '<p class="pv-note" style="margin:0 0 12px">按每日目标推进：今天做完三件事就够。</p>' +
      '<div class="pv-hero">' +
      metric(countdown, '距离初试（' + state.profile.examDate + '）') +
      metric(streakDays() + ' 天', '连续学习') +
      metric(todayActivity().answered, '今日已答') +
      metric(mastered + ' / ' + totalTopics, '已掌握考点') +
      '</div>' +
      '<section class="pv-card">' + taskListHtml() + '</section>' +
      '<section class="pv-card"><h2 class="pv-h2">四科掌握度</h2>' + subjectBars() +
      '<p class="pv-note">掌握度来自考点标记与答题表现：**累计**答对 4 次自动升为「已掌握」，答错会降回「学习中」。</p></section>' +
      '<section class="pv-card"><h2 class="pv-h2">最该补的几个点</h2>' + recoHtml() + '</section>' +
      '<section class="pv-card"><h2 class="pv-h2">学习节奏</h2>' + heatmapHtml() + '</section>' +
      '<section class="pv-card"><h2 class="pv-h2">408 考场结构</h2>' +
      '<div class="pv-kv"><div><b>150 分</b>总分</div><div><b>180 分钟</b>考试时长</div>' +
      '<div><b>40 题 × 2 分</b>单项选择题</div><div><b>7 题 · 70 分</b>综合应用题</div></div>' +
      '<p class="pv-note">四科分值：数据结构 45、计算机组成原理 45、操作系统 35、计算机网络 25。</p></section>' +
      '<p class="pv-note">题库 ' + ((bank() || []).length) + ' 题，覆盖 ' + totalTopics +
      ' 个知识点；累计作答 ' + attempts + ' 题，正确率 ' + pct(right, attempts) + '%。</p>';
  }

  function renderPractice() {
    var metas = subjectsMeta();
    if (!metas) return noticeHtml() + '<section class="pv-card"><h2 class="pv-h2">刷题</h2></section>';
    var p = ui.practice;
    var subjectOptions = '<option value="all">全科混合</option>' + metas.map(function (s) {
      return '<option value="' + esc(s.key) + '"' + (p.subject === s.key ? ' selected' : '') + '>' + esc(s.name) + '</option>';
    }).join('');
    var topics = [];
    metas.forEach(function (s) {
      if (p.subject !== 'all' && s.key !== p.subject) return;
      s.topics.forEach(function (t) { topics.push({ s: s, t: t }); });
    });
    var topicOptions = '<option value="all">不限章节</option>' + topics.map(function (x) {
      return '<option value="' + esc(x.t.slug) + '"' + (p.topic === x.t.slug ? ' selected' : '') + '>' +
        esc((p.subject === 'all' ? x.s.name + ' · ' : '') + x.t.title) + '</option>';
    }).join('');
    var counts = [5, 10, 15, 20].map(function (n) {
      return '<option value="' + n + '"' + (p.count === n ? ' selected' : '') + '>' + n + ' 题</option>';
    }).join('');
    var scopes = [['all', '综合练习'], ['weak', '薄弱强化'], ['wrong', '错题重练'], ['coverage', '全章覆盖']].map(function (x) {
      return '<option value="' + x[0] + '"' + (p.scope === x[0] ? ' selected' : '') + '>' + x[1] + '</option>';
    }).join('');
    var orders = [['random', '随机出题'], ['seq', '顺序出题']].map(function (x) {
      return '<option value="' + x[0] + '"' + (p.order === x[0] ? ' selected' : '') + '>' + x[1] + '</option>';
    }).join('');
    var wrongCount = Object.keys(state.wrong).filter(function (id) { return !state.wrong[id].mastered; }).length;
    return noticeHtml() +
      '<section class="pv-card"><h2 class="pv-h2">组卷</h2>' +
      '<div class="pv-form">' +
      '<label class="pv-field">科目<select data-role="practice-subject">' + subjectOptions + '</select></label>' +
      '<label class="pv-field">章节<select data-role="practice-topic">' + topicOptions + '</select></label>' +
      '<label class="pv-field">题量<select data-role="practice-count">' + counts + '</select></label>' +
      '<label class="pv-field">范围<select data-role="practice-scope">' + scopes + '</select></label>' +
      '<label class="pv-field">顺序<select data-role="practice-order">' + orders + '</select></label>' +
      '</div>' +
      '<div class="pv-actions"><button class="pv-btn" type="button" data-action="start-practice">开始练习</button>' +
      '<span class="pv-note">错题待复盘 ' + wrongCount + ' 题</span></div></section>' +
      '<section class="pv-card"><h2 class="pv-h2">说明</h2><ul class="pv-list">' +
      '<li>练习模式：选完立即判分并显示解析，答错自动进错题本。</li>' +
      '<li>薄弱强化：按考点掌握度、答对/答错次数排序，先练最弱的。</li>' +
      '<li>错题重练：只抽未掌握的错题；连续答对 2 次自动标记为已掌握。</li>' +
      '<li>全章覆盖：每个知识点至少抽 1 题。</li></ul></section>';
  }

  function renderQuiz() {
    if (!session) {
      return noticeHtml() + '<section class="pv-card"><h2 class="pv-h2">答题</h2>' +
        '<p class="pv-text">没有进行中的练习。先到「刷题」选一组，或从错题本开始重练。</p>' +
        '<div class="pv-actions"><a class="pv-btn" href="#/practice">去刷题</a></div></section>';
    }
    var q = currentQuestion();
    if (!q) {
      return noticeHtml() + '<section class="pv-card"><p class="pv-alert">当前题目在题库中找不到（数据可能已更新），请退出重开一组。</p>' +
        '<div class="pv-actions"><button class="pv-btn" type="button" data-action="exit-quiz">退出</button></div></section>';
    }
    var sel = session.answers[q.id];
    var showAnswer = session.mode === 'practice' && typeof sel === 'number';
    var total = session.ids.length;
    var idx = session.index + 1;
    var timerHtml = session.mode === 'mock' && session.durationSec
      ? '<span class="pv-timer" id="pv-timer">' + fmtClock(remainingSeconds()) + '</span>' : '';
    var opts = q.options.map(function (text, i) {
      var cls = 'pv-opt';
      if (showAnswer) {
        if (i === q.answer) cls += ' ok';
        else if (i === sel) cls += ' bad';
      } else if (typeof sel === 'number' && i === sel) {
        cls += ' on';
      }
      var disabled = showAnswer ? ' disabled' : '';
      return '<button class="' + cls + '" type="button" data-action="pick" data-index="' + i + '"' + disabled +
        ' aria-pressed="' + (typeof sel === 'number' && i === sel) + '">' +
        '<span class="pv-opt-key">' + 'ABCD'.charAt(i) + '</span><span>' + esc(text) + '</span></button>';
    }).join('');
    var explain = showAnswer ? '<div class="pv-explain"><b>解析：</b>' + esc(q.explanation) + '</div>' : '';
    var actions;
    if (session.mode === 'practice') {
      actions = showAnswer
        ? '<button class="pv-btn" type="button" data-action="next">' + (idx === total ? '看结果' : '下一题') + '</button>'
        : '<span class="pv-note">点选项作答，答完立即看解析</span>';
    } else {
      actions = '<button class="pv-btn pv-btn-quiet" type="button" data-action="prev"' + (session.index === 0 ? ' disabled' : '') + '>上一题</button>' +
        '<button class="pv-btn pv-btn-quiet" type="button" data-action="next"' + (idx === total ? ' disabled' : '') + '>下一题</button>' +
        '<button class="pv-btn pv-btn-quiet" type="button" data-action="flag">' + (session.flags[q.id] ? '取消标记' : '标记拿不准') + '</button>' +
        '<button class="pv-btn" type="button" data-action="submit-mock">交卷</button>';
    }
    var sheet = '';
    if (session.mode === 'mock') {
      sheet = '<section class="pv-card"><h3 class="pv-h3">答题卡（' + answeredCount() + ' / ' + total + '）</h3><div class="pv-sheet">' +
        session.ids.map(function (id, i) {
          var cls = (typeof session.answers[id] === 'number' ? 'done' : '') + (session.flags[id] ? ' flag' : '');
          return '<button type="button" class="' + cls + '" data-action="sheet" data-index="' + i + '">' + (i + 1) + '</button>';
        }).join('') + '</div></section>';
    }
    return noticeHtml() +
      '<section class="pv-card">' +
      '<div class="pv-quiz-head"><button class="pv-btn pv-btn-quiet pv-btn-sm" type="button" data-action="exit-quiz">退出</button>' +
      '<span>第 ' + idx + ' / ' + total + ' 题</span>' +
      '<span>' + (session.mode === 'mock' ? '限时模拟 · 交卷后统一解析' : '即时反馈 · 答错自动收录') + '</span>' +
      timerHtml + '</div>' +
      '<div class="pv-qmeta"><span>' + esc(subjectName(q.subject)) + ' · ' + esc(topicTitle(q.subject, q.topic)) + '</span>' +
      (q.difficulty ? '<span>难度 ' + '●●●'.slice(0, q.difficulty) + '○○○'.slice(0, 3 - q.difficulty) + '</span>' : '') +
      (q.tags && q.tags.length ? '<span>' + esc(q.tags.join(' / ')) + '</span>' : '') + '</div>' +
      '<p class="pv-stem">' + esc(q.stem) + '</p>' +
      (q.code ? '<pre class="pv-code">' + esc(q.code) + '</pre>' : '') +
      '<div class="pv-opts">' + opts + '</div>' + explain +
      '<div class="pv-actions">' + actions + '</div>' +
      '</section>' + sheet;
  }

  function renderResult() {
    if (!lastResult) {
      return noticeHtml() + '<section class="pv-card"><h2 class="pv-h2">结果</h2>' +
        '<p class="pv-text">还没有结果。完成一组练习或一次模拟后会显示在这里。</p>' +
        '<div class="pv-actions"><a class="pv-btn" href="#/practice">去刷题</a></div></section>';
    }
    var r = lastResult;
    var accuracy = pct(r.correct, r.total);
    var dur = Math.round((r.endedAt - r.startedAt) / 1000);
    var rows = r.ids.map(function (id, i) {
      var q = questionById(id);
      if (!q) return '';
      var sel = r.answers[id];
      var ok = typeof sel === 'number' && sel === q.answer;
      var your = typeof sel === 'number' ? 'ABCD'.charAt(sel) : '未作答';
      return '<div class="pv-row"><div class="pv-row-head"><b>' + (i + 1) + '.</b><span>' + esc(q.stem) + '</span></div>' +
        '<div class="pv-row-body">你的答案：<span class="' + (ok ? 'pv-ok' : 'pv-bad') + '">' + your + '</span>' +
        '　正确答案：' + 'ABCD'.charAt(q.answer) +
        (ok ? '' : '　<span class="pv-bad">已收录错题本</span>') + '</div>' +
        '<div class="pv-row-body">' + esc(q.explanation) + '</div></div>';
    }).join('');
    return noticeHtml() +
      '<section class="pv-card"><h2 class="pv-h2">' + (r.mode === 'mock' ? '模拟结果' : '练习结果') + '</h2>' +
      '<div class="pv-score"><b>' + accuracy + '%</b><span class="pv-note">正确 ' + r.correct + ' / ' + r.total +
      ' 题 · 用时 ' + fmtDuration(dur) + '</span></div>' +
      '<div class="pv-actions"><a class="pv-btn" href="#/practice">再练一组</a>' +
      '<a class="pv-btn pv-btn-ghost" href="#/wrong">去错题本</a></div></section>' +
      '<section class="pv-card"><h2 class="pv-h2">逐题回顾</h2>' + rows + '</section>';
  }

  function renderWrong() {
    var tab = ui.wrong.tab;
    var subject = ui.wrong.subject;
    var entries = Object.keys(state.wrong).map(function (id) {
      var q = questionById(id);
      return q ? { q: q, w: state.wrong[id] } : null;
    }).filter(Boolean);
    var counts = {
      pending: entries.filter(function (x) { return !x.w.mastered; }).length,
      mastered: entries.filter(function (x) { return x.w.mastered; }).length,
      all: entries.length
    };
    if (tab === 'pending') entries = entries.filter(function (x) { return !x.w.mastered; });
    else if (tab === 'mastered') entries = entries.filter(function (x) { return x.w.mastered; });
    if (subject !== 'all') entries = entries.filter(function (x) { return x.q.subject === subject; });
    var tabs = [['pending', '待复盘'], ['mastered', '已掌握'], ['all', '全部']].map(function (x) {
      return '<button class="pv-tab' + (tab === x[0] ? ' on' : '') + '" type="button" data-action="wrong-tab" data-tab="' +
        x[0] + '">' + x[1] + '（' + counts[x[0]] + '）</button>';
    }).join('');
    var subjectOptions = '<option value="all">全部科目</option>' + (subjectsMeta() || []).map(function (s) {
      return '<option value="' + esc(s.key) + '"' + (subject === s.key ? ' selected' : '') + '>' + esc(s.name) + '</option>';
    }).join('');
    var list = entries.map(function (x) {
      return '<div class="pv-row"><div class="pv-row-head"><span>' + esc(x.q.stem) + '</span></div>' +
        '<div class="pv-row-body">' + esc(subjectName(x.q.subject)) + ' · ' + esc(topicTitle(x.q.subject, x.q.topic)) +
        ' · 错 ' + (x.w.count || 0) + ' 次 · 连对 ' + (x.w.streak || 0) + '/2 · ' +
        (x.w.mastered ? '已掌握' : '待复盘') + '</div>' +
        '<div class="pv-actions" style="margin-top:6px">' +
        '<button class="pv-btn pv-btn-quiet pv-btn-sm" type="button" data-action="retry-wrong" data-qid="' +
        esc(x.q.id) + '">重练这题</button></div></div>';
    }).join('');
    return noticeHtml() +
      '<section class="pv-card"><h2 class="pv-h2">错题本</h2>' +
      '<div class="pv-tabs">' + tabs + '</div>' +
      '<label class="pv-field" style="max-width:220px">科目<select data-role="wrong-subject">' + subjectOptions + '</select></label>' +
      '<div class="pv-actions" style="margin:12px 0"><button class="pv-btn" type="button" data-action="retry-wrong-all"' +
      (entries.length ? '' : ' disabled') + '>重练本页 ' + entries.length + ' 题</button>' +
      '<span class="pv-note">连续答对 2 次自动标记为已掌握</span></div>' +
      (list || '<p class="pv-empty">这里还没有错题。做完一组练习，答错的题会自动进来。</p>') +
      '</section>';
  }

  function renderMock() {
    var cards = Object.keys(MOCK_MODES).map(function (key) {
      var m = MOCK_MODES[key];
      return '<button class="pv-opt' + (ui.mock.mode === key ? ' on' : '') + '" type="button" data-action="mock-mode" data-mode="' + key + '">' +
        '<span class="pv-opt-key">' + (key === 'all' ? '全' : key === 'subject' ? '单' : '弱') + '</span>' +
        '<span><strong>' + esc(m.title) + '</strong><br><span class="pv-note">' + esc(m.desc) + ' ' +
        m.count + ' 题 · ' + (m.duration / 60) + ' 分钟</span></span></button>';
    }).join('');
    var subjectOptions = (subjectsMeta() || []).map(function (s) {
      return '<option value="' + esc(s.key) + '"' + (ui.mock.subject === s.key ? ' selected' : '') + '>' + esc(s.name) + '</option>';
    }).join('');
    var recent = state.sessions.filter(function (s) { return s.mode === 'mock'; }).slice(0, 5).map(function (s) {
      return '<div class="pv-row"><div class="pv-row-head">模拟 · ' + (s.answered || 0) + ' 题 · 正确 ' + (s.correct || 0) +
        ' / ' + (s.total || 0) + '</div><div class="pv-row-body">' +
        esc(String(s.endedAt || '').replace('T', ' ').slice(0, 16)) + ' · 用时 ' + fmtDuration(s.durationSec || 0) + '</div></div>';
    }).join('');
    var cfg = MOCK_MODES[ui.mock.mode];
    return noticeHtml() +
      '<section class="pv-card"><h2 class="pv-h2">限时模拟</h2>' +
      '<p class="pv-text">限时、无即时反馈、交卷后统一解析。倒计时结束会自动交卷，未作答按错误计分。</p>' +
      '<div class="pv-opts">' + cards + '</div>' +
      (ui.mock.mode === 'subject' ? '<label class="pv-field" style="max-width:220px">科目<select data-role="mock-subject">' +
        subjectOptions + '</select></label>' : '') +
      '<div class="pv-actions" style="margin-top:12px"><button class="pv-btn" type="button" data-action="start-mock">开始 ' +
      esc(cfg.title) + '（' + cfg.count + ' 题 · ' + (cfg.duration / 60) + ' 分钟）</button></div></section>' +
      '<section class="pv-card"><h2 class="pv-h2">考场规则</h2><ul class="pv-list">' +
      '<li>倒计时结束自动交卷，未作答按错误计分。</li><li>答题过程中不显示对错，交卷后统一查看解析。</li>' +
      '<li>拿不准的题先标记，最后再回来检查。</li><li>当前题库为精选样例，并非完整真题卷；真实 408 另含 70 分综合题。</li></ul>' +
      (recent ? '<h3 class="pv-h3">最近的模拟</h3>' + recent : '<p class="pv-note">还没有模拟记录。</p>') +
      '</section>';
  }

  function renderStats() {
    var attempts = state.attempts;
    var right = attempts.filter(function (x) { return x.correct; }).length;
    var mastered = 0, totalTopics = 0;
    (subjectsMeta() || []).forEach(function (s) {
      s.topics.forEach(function (t) {
        totalTopics += 1;
        if (pointState(pointKey(s.key, t.slug)).level === 3) mastered += 1;
      });
    });
    var sessions = state.sessions.slice(0, 8).map(function (s) {
      return '<div class="pv-row"><div class="pv-row-head">' + (MODE_LABEL[s.mode] || s.mode) + ' · ' +
        (s.answered || 0) + '/' + (s.total || 0) + ' 题 · 正确 ' + (s.correct || 0) + '</div>' +
        '<div class="pv-row-body">' + esc(String(s.endedAt || '').replace('T', ' ').slice(0, 16)) +
        ' · 用时 ' + fmtDuration(s.durationSec || 0) + '</div></div>';
    }).join('');
    return noticeHtml() +
      '<section class="pv-card"><h2 class="pv-h2">学习报告</h2>' +
      '<div class="pv-hero">' + metric(streakDays() + ' 天', '连续学习') +
      metric(attempts.length + ' 题', '累计作答') + metric(pct(right, attempts.length) + '%', '总体正确率') +
      metric(mastered + ' / ' + totalTopics, '已掌握考点') + '</div></section>' +
      '<section class="pv-card"><h2 class="pv-h2">四科掌握度</h2>' + subjectBars() + '</section>' +
      '<section class="pv-card"><h2 class="pv-h2">近 7 天答题量</h2>' + barsHtml() +
      '<h3 class="pv-h3">最近 12 周</h3>' + heatmapHtml() + '</section>' +
      '<section class="pv-card"><h2 class="pv-h2">最近的学习记录</h2>' +
      (sessions || '<p class="pv-empty">还没有练习记录。先完成第一组题吧。</p>') + '</section>';
  }

  function renderSettings() {
    var p = state.profile;
    var size = '?';
    try { size = (JSON.stringify(state).length / 1024).toFixed(1); } catch (e) { size = '?'; }
    return noticeHtml() +
      '<section class="pv-card"><h2 class="pv-h2">学习设置</h2>' +
      '<div class="pv-form">' +
      '<label class="pv-field">称呼<input type="text" data-role="set-name" maxlength="20" value="' + esc(p.name) + '" placeholder="可留空"></label>' +
      '<label class="pv-field">考试日期<input type="date" data-role="set-date" value="' + esc(p.examDate) + '"></label>' +
      '<label class="pv-field">每日刷题目标<input type="number" data-role="set-goal" min="5" max="100" step="5" value="' +
      esc(p.dailyGoal) + '"></label>' +
      '</div>' +
      '<div class="pv-actions"><button class="pv-btn" type="button" data-action="save-settings">保存设置</button></div></section>' +
      '<section class="pv-card"><h2 class="pv-h2">数据</h2>' +
      '<p class="pv-text">数据只保存在本机浏览器（localStorage 键 <code>' + KEY + '</code>），不上传任何服务器。' +
      '换设备或清理浏览器数据前请先导出备份。</p>' +
      '<p class="pv-note">当前存储：' + (storageOK ? '可用' : '不可用（内存模式）') + ' · 数据约 ' + size + ' KB</p>' +
      '<div class="pv-actions" style="margin-top:12px">' +
      '<button class="pv-btn" type="button" data-action="export-data">导出备份</button>' +
      '<button class="pv-btn pv-btn-ghost" type="button" data-action="import-trigger">导入备份</button>' +
      '<button class="pv-btn pv-btn-quiet" type="button" data-action="clear-data">清空学习数据</button>' +
      '<input type="file" id="pv-import" data-role="import-file" accept="application/json" hidden>' +
      '</div><p class="pv-note">导入会覆盖当前数据；导出的 JSON 里不含任何个人信息。</p></section>' +
      '<section class="pv-card"><h2 class="pv-h2">关于</h2><p class="pv-note">纯前端离线实现；题库 ' +
      ((bank() || []).length) + ' 题，覆盖 ' +
      ((subjectsMeta() || []).reduce(function (n, s) { return n + s.topics.length; }, 0)) +
      ' 个知识点。</p></section>';
  }

  function renderRoute() {
    switch (route()) {
      case 'practice': return renderPractice();
      case 'quiz': return renderQuiz();
      case 'result': return renderResult();
      case 'wrong': return renderWrong();
      case 'mock': return renderMock();
      case 'stats': return renderStats();
      case 'settings': return renderSettings();
      default: return renderToday();
    }
  }

  // =====================================================================
  // 路由
  // =====================================================================
  var VIEWS = ['today', 'practice', 'quiz', 'result', 'wrong', 'mock', 'stats', 'settings'];
  var NAV_FOR = { quiz: 'practice', result: 'practice' };
  var TITLES = {
    today: '今日练习', practice: '刷题', quiz: '答题', result: '结果',
    wrong: '错题本', mock: '模拟考', stats: '学习报告', settings: '设置'
  };

  function route() {
    var raw = (window.location.hash || '').replace(/^#\/?/, '');
    var name = raw.split('?')[0].split('/')[0] || 'today';
    return VIEWS.indexOf(name) >= 0 ? name : 'today';
  }

  function go(path) {
    var target = '#/' + path;
    if (window.location.hash === target) { render(); return; }
    window.location.hash = target;
  }

  function toast(msg) {
    var el = document.createElement('div');
    el.className = 'pv-toast';
    el.textContent = msg;
    document.body.appendChild(el);
    window.setTimeout(function () { el.classList.add('show'); }, 10);
    window.setTimeout(function () {
      el.classList.remove('show');
      window.setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 250);
    }, 2200);
  }

  function applyActive() {
    var active = NAV_FOR[route()] || route();
    var links = document.querySelectorAll('.site-sidebar .sb-chap[data-view]');
    Array.prototype.forEach.call(links, function (a) {
      var on = a.getAttribute('data-view') === active;
      if (on) { a.classList.add('cur'); a.setAttribute('aria-current', 'page'); }
      else { a.classList.remove('cur'); a.removeAttribute('aria-current'); }
    });
  }

  function startTimer() {
    clearTimer();
    if (!session || session.mode !== 'mock') return;
    timerId = window.setInterval(function () {
      if (!session) { clearTimer(); return; }
      var left = remainingSeconds();
      var el = document.getElementById('pv-timer');
      if (el) {
        el.textContent = fmtClock(left);
        if (left <= 60) el.classList.add('warn');
      }
      if (left <= 0) {
        clearTimer();
        toast('时间到，自动交卷');
        submitMock(true);
      }
    }, 1000);
  }

  function render() {
    var host = document.getElementById('practice-view');
    if (!host) return;                    // 不是练习页（脚本被其它页面引入时直接退出）
    if (session && session.mode === 'mock') startTimer();
    else clearTimer();
    host.innerHTML = renderRoute();
    applyActive();
    document.title = (TITLES[route()] || '练习') + ' · 408 速成复习资料';
  }

  // =====================================================================
  // 事件
  // =====================================================================
  function onClick(e) {
    var el = e.target && e.target.closest ? e.target.closest('[data-action]') : null;
    if (!el) return;
    var action = el.getAttribute('data-action');
    switch (action) {
      case 'pick': pickOption(Number(el.getAttribute('data-index'))); break;
      case 'next': nextQuestion(); break;
      case 'prev': prevQuestion(); break;
      case 'submit-mock': submitMock(false); break;
      case 'exit-quiz': exitQuiz(); break;
      case 'flag': {
        if (!session) break;
        var q = currentQuestion();
        if (q) { session.flags[q.id] = !session.flags[q.id]; render(); }
        break;
      }
      case 'sheet': {
        if (!session) break;
        session.index = clamp(Number(el.getAttribute('data-index')), 0, session.ids.length - 1);
        render();
        break;
      }
      case 'start-practice': {
        var ids = buildPractice(ui.practice);
        if (!ids.length) { toast('当前条件下没有题目'); break; }
        startSession('practice', ids);
        break;
      }
      case 'mock-mode': ui.mock.mode = el.getAttribute('data-mode'); render(); break;
      case 'start-mock': {
        var built = buildMock(ui.mock.mode, ui.mock.subject);
        if (!built.ids.length) { toast('当前条件下没有题目'); break; }
        startSession('mock', built.ids, built.duration);
        break;
      }
      case 'review-topic': markReviewed(el.getAttribute('data-key')); break;
      case 'retry-wrong': {
        var id = el.getAttribute('data-qid');
        if (id) startSession('practice', [id]);
        break;
      }
      case 'retry-wrong-all': {
        var tab = ui.wrong.tab;
        var subject = ui.wrong.subject;
        var ids2 = Object.keys(state.wrong).filter(function (wid) {
          var w = state.wrong[wid];
          if (tab === 'pending' && w.mastered) return false;
          if (tab === 'mastered' && !w.mastered) return false;
          var q2 = questionById(wid);
          if (!q2) return false;
          if (subject !== 'all' && q2.subject !== subject) return false;
          return true;
        });
        if (!ids2.length) { toast('本页没有可重练的错题'); break; }
        startSession('practice', ids2);
        break;
      }
      case 'wrong-tab': ui.wrong.tab = el.getAttribute('data-tab'); render(); break;
      case 'save-settings': saveSettings(); break;
      case 'export-data': exportData(); break;
      case 'import-trigger': {
        var input = document.getElementById('pv-import');
        if (input) input.click();
        break;
      }
      case 'clear-data': clearData(); break;
      default: break;
    }
  }

  function onChange(e) {
    var el = e.target;
    var role = el && el.getAttribute ? el.getAttribute('data-role') : null;
    if (!role) return;
    switch (role) {
      case 'practice-subject':
        ui.practice.subject = el.value;
        ui.practice.topic = 'all';
        render();
        break;
      case 'practice-topic': ui.practice.topic = el.value; render(); break;
      case 'practice-count': ui.practice.count = Number(el.value) || 10; render(); break;
      case 'practice-scope': ui.practice.scope = el.value; render(); break;
      case 'practice-order': ui.practice.order = el.value; render(); break;
      case 'wrong-subject': ui.wrong.subject = el.value; render(); break;
      case 'mock-subject': ui.mock.subject = el.value; render(); break;
      case 'import-file': importFile(el); break;
      default: break;
    }
  }

  function saveSettings() {
    var nameEl = document.querySelector('[data-role="set-name"]');
    var dateEl = document.querySelector('[data-role="set-date"]');
    var goalEl = document.querySelector('[data-role="set-goal"]');
    if (!nameEl || !dateEl || !goalEl) return;
    var date = String(dateEl.value || '').trim();
    if (!DATE_RE.test(date) || isNaN(parseDate(date).getTime())) {
      toast('考试日期格式不对（应为 YYYY-MM-DD）');
      return;
    }
    var goal = Number(goalEl.value);
    if (!goal || goal < 5 || goal > 100) {
      toast('每日目标应在 5–100 题之间');
      return;
    }
    state.profile.name = String(nameEl.value || '').slice(0, 20);
    state.profile.examDate = date;
    state.profile.dailyGoal = Math.round(goal);
    save();
    toast('设置已保存');
    render();
  }

  function exportData() {
    try {
      var text = JSON.stringify(state, null, 1);
      var blob = new Blob([text], { type: 'application/json' });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = '408-练习数据-' + dateKey() + '.json';
      document.body.appendChild(a);
      a.click();
      window.setTimeout(function () {
        URL.revokeObjectURL(a.href);
        if (a.parentNode) a.parentNode.removeChild(a);
      }, 500);
      toast('已导出备份');
    } catch (e) {
      toast('导出失败：' + (e && e.message ? e.message : e));
    }
  }

  function importFile(input) {
    var file = input.files && input.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function () {
      var data;
      try {
        data = JSON.parse(String(reader.result || ''));
      } catch (e) {
        toast('导入失败：不是合法 JSON');
        return;
      }
      if (!data || data.v !== 1 || !Array.isArray(data.attempts) || typeof data.points !== 'object') {
        toast('导入失败：文件结构不是本页导出的备份');
        return;
      }
      if (!window.confirm('导入会覆盖当前数据（现有 ' + state.attempts.length + ' 条作答记录）。继续？')) return;
      state = migrate(data);
      save();
      toast('已导入备份');
      render();
    };
    reader.onerror = function () { toast('导入失败：读取文件出错'); };
    reader.readAsText(file);
  }

  function clearData() {
    if (!window.confirm('清空全部学习数据（作答记录、错题、掌握度）？此操作不可撤销，建议先导出备份。')) return;
    state = defaultState();
    save();
    session = null;
    lastResult = null;
    clearTimer();
    toast('已清空学习数据');
    render();
  }

  function onKey(e) {
    if (!session || route() !== 'quiz') return;
    var tag = (e.target && e.target.tagName) || '';
    if (/INPUT|SELECT|TEXTAREA/.test(tag)) return;
    if (e.key >= '1' && e.key <= '4') {
      pickOption(Number(e.key) - 1);
      e.preventDefault();
    } else if (e.key === 'Enter') {
      if (session.mode === 'practice') {
        var q = currentQuestion();
        if (q && session.answers[q.id] !== undefined) nextQuestion();
      } else {
        nextQuestion();
      }
      e.preventDefault();
    } else if (e.key === 'ArrowRight') {
      nextQuestion(); e.preventDefault();
    } else if (e.key === 'ArrowLeft') {
      prevQuestion(); e.preventDefault();
    } else if (e.key === 'Escape') {
      exitQuiz();
    }
  }

  // =====================================================================
  // 启动
  // =====================================================================
  function start() {
    var host = document.getElementById('practice-view');
    if (!host) return;                    // 不是练习页
    if (!window.location.hash) {
      try { window.history.replaceState(null, '', '#/today'); } catch (e) { /* file:// 下忽略 */ }
    }
    document.addEventListener('click', onClick);
    document.addEventListener('change', onChange);
    document.addEventListener('keydown', onKey);
    window.addEventListener('hashchange', render);
    render();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
