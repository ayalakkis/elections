/* Election portal: one small script, no libraries. Each page has its own section below. */
(function () {
  'use strict';

  // Helpers

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const csrf = () => (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  const short = (hash, n = 10) => (hash ? hash.slice(0, n) + '…' : '');
  const fmtTime = (ts) => (ts ? new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) : 'Genesis');
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + 's'}`;
  const joinAnd = (xs) => (xs.length < 2 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1]);
  const readJSON = (id) => { const el = document.getElementById(id); return el ? JSON.parse(el.textContent) : null; };

  async function api(url, options = {}) {
    const opts = Object.assign({ headers: {} }, options);
    opts.headers['Accept'] = 'application/json';
    if (opts.body && typeof opts.body !== 'string') {
      opts.body = JSON.stringify(opts.body);
      opts.headers['Content-Type'] = 'application/json';
    }
    if ((opts.method || 'GET') !== 'GET') opts.headers['X-CSRFToken'] = csrf();
    opts.credentials = 'same-origin';
    const res = await fetch(url, opts);
    let data = {};
    try { data = await res.json(); } catch (e) { /* not JSON */ }
    data._status = res.status;
    return data;
  }

  function toast(message, kind = 'info') {
    const colors = { info: 'var(--brand)', ok: 'var(--ok)', bad: 'var(--bad)', warn: 'var(--warn)' };
    const el = document.createElement('div');
    el.className = 'toast';
    el.innerHTML = `<span class="ti" style="background:${colors[kind]}"></span><div>${esc(message)}</div>`;
    $('#toasts').appendChild(el);
    setTimeout(() => { el.style.transition = 'opacity .3s'; el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 4200);
  }

  // Polls a function, pausing while the tab is hidden.
  function poll(fn, ms) {
    let timer;
    const tick = async () => {
      clearTimeout(timer);
      if (!document.hidden) { try { await fn(); } catch (e) { console.warn(e); } }
      timer = setTimeout(tick, ms);
    };
    document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
    tick();
    return { now: tick };
  }

  function countTo(el, value, suffix = '') {
    if (!el) return;
    const from = parseFloat(el.dataset.v || '0');
    el.dataset.v = value;
    if (from === value || matchMedia('(prefers-reduced-motion: reduce)').matches) { el.textContent = value + suffix; return; }
    const start = performance.now(), dur = 600;
    const step = (t) => {
      const p = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(from + (value - from) * e) + suffix;
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function avatar(c, cls = '') {
    const img = c.photo ? `<img src="${esc(c.photo)}" alt="" loading="lazy" onerror="this.remove()">` : '';
    return `<div class="avatar ${cls}" style="background:${esc(c.color)}" aria-hidden="true">${esc(c.initials)}${img}</div>`;
  }

  function modal({ title, body, confirm = 'Confirm', danger = false }) {
    return new Promise((resolve) => {
      const wrap = document.createElement('div');
      wrap.className = 'overlay';
      wrap.innerHTML = `<div class="card modal" role="dialog" aria-modal="true" aria-labelledby="m-title">
        <h2 id="m-title">${esc(title)}</h2><p class="muted">${body}</p>
        <div class="row"><button class="btn btn-ghost" data-a="no">Cancel</button>
        <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-a="yes">${esc(confirm)}</button></div></div>`;
      const close = (v) => { wrap.remove(); document.removeEventListener('keydown', onKey); resolve(v); };
      const onKey = (e) => { if (e.key === 'Escape') close(false); };
      wrap.addEventListener('click', (e) => { if (e.target === wrap) close(false); const a = e.target.closest('[data-a]'); if (a) close(a.dataset.a === 'yes'); });
      document.addEventListener('keydown', onKey);
      document.body.appendChild(wrap);
      $('[data-a="yes"]', wrap).focus();
    });
  }

  // Theme
  (function theme() {
    const btn = $('#theme-toggle');
    if (!btn) return;
    const current = () => document.documentElement.getAttribute('data-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    const paint = () => { const d = current() === 'dark'; $('.when-light', btn).style.display = d ? 'none' : ''; $('.when-dark', btn).style.display = d ? '' : 'none'; };
    btn.addEventListener('click', () => {
      const next = current() === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('portal-theme', next); } catch (e) { /* private mode */ }
      paint();
    });
    paint();
  })();

  // Shared widgets

  const NODE_POS = { interior: [210, 92], commission: [80, 286], delegates: [340, 286] };
  const SHORT = { interior: 'Ministry', commission: 'Commission', delegates: 'Delegates' };

  function renderNetwork(svg, data) {
    if (!svg || !data) return;
    const sig = JSON.stringify(data.nodes.map((n) => [n.name, n.status, n.blocks])) + data.confirmed;
    if (svg.dataset.sig === sig) return;
    svg.dataset.sig = sig;
    const nodes = data.nodes;
    const byName = Object.fromEntries(nodes.map((n) => [n.name, n]));
    const names = nodes.map((n) => n.name);
    let edges = '', packets = '';
    for (let i = 0; i < names.length; i++) {
      for (let j = i + 1; j < names.length; j++) {
        const a = NODE_POS[names[i]] || [0, 0], b = NODE_POS[names[j]] || [0, 0];
        const off = byName[names[i]].status === 'DOWN' || byName[names[j]].status === 'DOWN';
        const d = `M${a[0]} ${a[1]}L${b[0]} ${b[1]}`;
        edges += `<path class="edge ${off ? 'off' : ''}" d="${d}"/>`;
        if (!off) {
          const back = `M${b[0]} ${b[1]}L${a[0]} ${a[1]}`;
          packets += `<circle class="packet" r="4"><animateMotion dur="2.8s" begin="-${(i + j) * 0.45}s" repeatCount="indefinite" path="${d}"/></circle>`;
          packets += `<circle class="packet" r="3" opacity=".6"><animateMotion dur="3.4s" begin="-${(i + j) * 0.7}s" repeatCount="indefinite" path="${back}"/></circle>`;
        }
      }
    }
    const groups = nodes.map((n) => {
      const [x, y] = NODE_POS[n.name] || [0, 0];
      const labelY = n.name === 'interior' ? y - 60 : y + 70;
      const status = n.status === 'VALID' ? 'Valid' : n.status === 'TAMPERED' ? 'Tampered' : 'Offline';
      const tone = n.status === 'VALID' ? 'var(--ok)' : n.status === 'TAMPERED' ? 'var(--bad)' : 'var(--ink-3)';
      return `<g class="state-${n.status}">
        <circle class="ring" cx="${x}" cy="${y}" r="44"/>
        <circle class="node-circle" cx="${x}" cy="${y}" r="44"/>
        <text class="node-count" x="${x}" y="${y + 2}">${n.status === 'DOWN' ? '—' : n.blocks}</text>
        <text class="node-sub" x="${x}" y="${y + 19}">${n.status === 'DOWN' ? 'offline' : 'blocks'}</text>
        <text class="node-label" x="${x}" y="${labelY}">${esc(SHORT[n.name] || n.name)} <tspan fill="${tone}">· ${status}</tspan></text></g>`;
    }).join('');
    const agree = data.majority ? data.majority.length : 0;
    const center = data.confirmed ? `${agree} of ${nodes.length} copies agree` : 'No majority';
    svg.innerHTML = edges + packets + groups + `<text class="center" x="210" y="228">${center}</text>`;
  }

  function chainHTML(blocks, selected) {
    if (!blocks.length) return '<div class="empty" style="width:100%">No valid copy of the chain is reachable right now.</div>';
    return blocks.map((b, i) => {
      const n = b.votes.length;
      const link = i < blocks.length - 1 ? `<div class="link" aria-hidden="true">${icon('link')}</div>` : '';
      return `<button type="button" class="block ${b.index === 0 ? 'genesis' : ''}" data-i="${b.index}" aria-pressed="${b.index === selected}" id="block-${b.index}">
          <div class="idx">Block<b>#${b.index}</b></div>
          <div class="h">${esc(short(b.hash, 14))}</div>
          <div class="meta">${b.index === 0 ? 'Start of the chain' : plural(n, 'ballot')} · ${fmtTime(b.timestamp)}</div>
        </button>${link}`;
    }).join('');
  }

  // Page: overview

  function pageHome() {
    const svg = $('#network'), chip = $('#net-status'), strip = $('#chain-strip');
    let lastBlocks = -1;
    poll(async () => {
      const d = await api('/api/overview/');
      if (d._status !== 200) return;
      renderNetwork(svg, d);
      const s = d.stats;
      countTo($('[data-k="turnout"]'), s.voters ? Math.round((100 * s.ballots_ledger) / s.voters) : 0, '%');
      countTo($('[data-k="ballots"]'), s.ballots_ledger);
      countTo($('[data-k="blocks"]'), s.blocks);
      $('[data-k="nodes"]').textContent = `${d.majority ? d.majority.length : 0} / ${d.nodes.length}`;
      chip.className = 'chip ' + (d.confirmed ? (s.valid_nodes === d.nodes.length ? 'chip-ok' : 'chip-warn') : 'chip-bad');
      chip.innerHTML = `<span class="dot live"></span> ${d.confirmed ? (s.valid_nodes === d.nodes.length ? 'All copies healthy' : 'Majority holds') : 'No majority'}`;
      if (s.blocks !== lastBlocks) {
        lastBlocks = s.blocks;
        const c = await api('/api/chain/');
        const blocks = (c.blocks || []).slice(-6);
        strip.innerHTML = chainHTML(blocks, -1);
        strip.scrollLeft = strip.scrollWidth;
        $$('.block', strip).forEach((b) => b.addEventListener('click', () => { location.href = '/explorer/#block-' + b.dataset.i; }));
      }
    }, 3000);
  }

  // Page: ballot

  function pageVote() {
    const ballot = readJSON('ballot-data') || [];
    const picks = Object.fromEntries(ballot.map((p) => [p.id, []]));
    let step = 0;
    const total = ballot.length + 1; // positions + review
    const stage = $('#stage'), nav = $('#steps');

    const pickedNames = (p) => picks[p.id].map((id) => p.candidates.find((c) => c.id === id)).filter(Boolean);

    function renderNav() {
      nav.innerHTML = ballot.map((p, i) => {
        const done = picks[p.id].length > 0;
        const names = pickedNames(p).map((c) => c.name).join(', ');
        return `<li class="${done ? 'done' : ''}"><button type="button" data-step="${i}" ${i === step ? 'aria-current="step"' : ''}>
          <span class="bullet">${done ? icon('check') : i + 1}</span>
          <span class="lbl"><b>${esc(p.name)}</b><span>${done ? esc(names) : i < step ? 'Skipped' : p.max_vote > 1 ? 'Choose up to ' + p.max_vote : 'Choose one'}</span></span></button></li>`;
      }).join('') + `<li><button type="button" data-step="${ballot.length}" ${step === ballot.length ? 'aria-current="step"' : ''}>
          <span class="bullet">${icon('key')}</span><span class="lbl"><b>Review and sign</b><span>Seal your ballot</span></span></button></li>`;
      $('#progress').style.width = (100 * step) / (total - 1) + '%';
      $$('[data-step]', nav).forEach((b) => b.addEventListener('click', () => go(+b.dataset.step)));
    }

    function go(i) {
      step = Math.max(0, Math.min(total - 1, i));
      render();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function renderPosition(p) {
      const chosen = picks[p.id];
      const full = chosen.length >= p.max_vote;
      const cards = p.candidates.map((c) => {
        const sel = chosen.includes(c.id);
        const locked = !sel && full && p.max_vote > 1;
        return `<button type="button" class="cand ${sel ? 'selected' : ''} ${locked ? 'locked' : ''}" role="${p.max_vote > 1 ? 'checkbox' : 'radio'}" aria-checked="${sel}" data-c="${c.id}">
          <span class="check">${icon('check')}</span>
          ${avatar(c)}
          <div><h3>${esc(c.name)}</h3><p class="bio" style="margin-top:6px">${esc(c.bio)}</p></div>
        </button>`;
      }).join('');
      const next = step + 1 < ballot.length ? 'Next: ' + ballot[step + 1].name : 'Review my ballot';
      const instruction = p.max_vote > 1 ? `Choose up to ${p.max_vote} candidates.` : 'Choose one candidate.';
      stage.innerHTML = `
        <div class="pos-head"><div class="section-title" style="margin-bottom:8px">Position ${step + 1} of ${ballot.length}</div>
          <h1>${esc(p.name)}</h1><p>${instruction} <span class="faint">${chosen.length} of ${p.max_vote} selected</span></p></div>
        <div class="cands" ${p.max_vote > 1 ? '' : 'role="radiogroup"'} aria-label="${esc(p.name)} candidates">${cards}</div>
        <div class="ballot-actions">
          <div>${step > 0 ? `<button class="btn btn-ghost" data-nav="back">${icon('left')} Back</button>` : ''}</div>
          <div class="row wrap-ok">${chosen.length ? '' : '<span class="hint">You can leave a position blank.</span>'}
            <button class="btn btn-primary" data-nav="next">${chosen.length ? esc(next) : 'Skip this position'} ${icon('right')}</button></div>
        </div>`;
      $$('.cand', stage).forEach((el) => el.addEventListener('click', () => {
        const id = +el.dataset.c;
        const list = picks[p.id];
        if (list.includes(id)) picks[p.id] = list.filter((x) => x !== id);
        else if (p.max_vote === 1) picks[p.id] = [id];
        else if (list.length < p.max_vote) list.push(id);
        else { toast(`You can choose up to ${p.max_vote} for ${p.name}. Remove one first.`, 'warn'); return; }
        render(true);
      }));
    }

    function renderReview() {
      const any = ballot.some((p) => picks[p.id].length);
      const rows = ballot.map((p, i) => {
        const chosen = pickedNames(p);
        const who = chosen.length ? chosen.map((c) => `<span class="pick">${avatar(c, 'sm')}${esc(c.name)}</span>`).join('') : '<span class="pick empty">No choice</span>';
        return `<div class="card review-item"><div class="pos">${esc(p.name)}</div><div class="who-list">${who}</div>
          <button class="btn btn-ghost btn-sm" data-edit="${i}">${icon('edit')} Change</button></div>`;
      }).join('');
      stage.innerHTML = `
        <div class="pos-head"><div class="section-title" style="margin-bottom:8px">Last step</div><h1>Review and sign</h1>
          <p>Check your choices. When you sign, your ballot is sealed with your key and sent to all three nodes. It cannot be changed afterwards.</p></div>
        <div class="review-list">${rows}</div>
        <div class="ballot-actions">
          <button class="btn btn-ghost" data-nav="back">${icon('left')} Back</button>
          <button class="btn btn-primary btn-lg" id="cast" ${any ? '' : 'disabled'}>${icon('key')} Sign and cast my ballot</button>
        </div>`;
      $$('[data-edit]', stage).forEach((b) => b.addEventListener('click', () => go(+b.dataset.edit)));
      $('#cast').addEventListener('click', cast);
    }

    function render(keepScroll) {
      renderNav();
      if (step < ballot.length) renderPosition(ballot[step]); else renderReview();
      const back = $('[data-nav="back"]', stage), next = $('[data-nav="next"]', stage);
      if (back) back.addEventListener('click', () => go(step - 1));
      if (next) next.addEventListener('click', () => go(step + 1));
      if (!keepScroll) { const h = $('h1', stage); if (h) h.setAttribute('tabindex', '-1'); }
    }

    async function cast() {
      const nodeNames = ['interior', 'commission', 'delegates'];
      const labels = { interior: 'Ministry of Interior', commission: 'Supervisory Commission', delegates: "Candidates' Delegates" };
      const wrap = document.createElement('div');
      wrap.className = 'overlay';
      wrap.innerHTML = `<div class="card cast" role="dialog" aria-modal="true" aria-labelledby="cast-title">
        <h2 id="cast-title">Casting your ballot</h2><p class="muted" style="margin-bottom:8px">Please keep this page open.</p>
        <div class="phase active" id="ph1"><span class="ic"><span class="spinner"></span></span><div><b>Signing with your private key</b><div class="sub mono" id="sigline">&nbsp;</div></div></div>
        <div class="phase" id="ph2"><span class="ic">${icon('send')}</span><div style="flex:1"><b>Sending to three independent nodes</b>
          <div class="lanes">${nodeNames.map((n) => `<div class="lane" id="lane-${n}"><span style="width:170px">${labels[n]}</span><span class="track"><i></i></span><span class="res faint">Waiting</span></div>`).join('')}</div></div></div>
        <div class="phase" id="ph3"><span class="ic">${icon('cube')}</span><div><b id="ph3-title">Chaining into a block</b><div class="sub" id="ph3-sub">Linked to the previous block by its hash</div></div></div>
        <div class="row" id="cast-actions" style="justify-content:flex-end;margin-top:12px"></div></div>`;
      document.body.appendChild(wrap);

      // Phase 1: a short signing animation while the request is prepared.
      const hex = '0123456789abcdef';
      const sigline = $('#sigline');
      const scramble = setInterval(() => { sigline.textContent = Array.from({ length: 48 }, () => hex[Math.floor(Math.random() * 16)]).join(''); }, 45);
      const ballotPayload = Object.fromEntries(Object.entries(picks).filter(([, v]) => v.length).map(([k, v]) => [k, v.map(String)]));
      const request = api('/api/vote/', { method: 'POST', body: { ballot: ballotPayload } });
      await sleep(1100);
      clearInterval(scramble);
      sigline.textContent = 'Signed with Ed25519 · ' + sigline.textContent.slice(0, 24) + '…';
      setPhase('ph1', 'done');
      setPhase('ph2', 'active');
      nodeNames.forEach((n) => { $(`#lane-${n} .track i`).style.width = '60%'; });

      let res;
      try { res = await request; } catch (e) { res = { ok: false, message: 'The website could not be reached. Your vote was not recorded.', answers: [] }; }
      const answers = Object.fromEntries((res.answers || []).map(([n, status, info]) => [n, [status, info]]));
      for (const n of nodeNames) {
        await sleep(380);
        const lane = $(`#lane-${n}`), out = $('.res', lane);
        const [status, info] = answers[n] || ['down', null];
        $('.track i', lane).style.width = '';
        if (status === 'accepted') { lane.classList.add('ok'); out.textContent = 'Stored in block ' + info; out.style.color = 'var(--ok)'; }
        else if (status === 'rejected' && info === 'already voted' && res.ok) { lane.classList.add('ok'); out.textContent = 'Copied from a peer'; out.style.color = 'var(--ok)'; }
        else if (status === 'down') { lane.classList.add('down'); out.textContent = res.ok ? 'Offline, catches up later' : 'Offline'; out.style.color = 'var(--warn)'; }
        else { lane.classList.add('bad'); out.textContent = info || 'Rejected'; out.style.color = 'var(--bad)'; }
      }
      await sleep(350);
      const actions = $('#cast-actions');
      if (res.ok) {
        setPhase('ph2', 'done');
        setPhase('ph3', 'done');
        $('#ph3-title').textContent = 'Recorded in block #' + res.block;
        $('#ph3-sub').textContent = 'Your ballot is now part of the chain on every reachable node.';
        actions.innerHTML = `<a class="btn btn-primary" href="/receipt/?fresh=1">View my receipt ${icon('right')}</a>`;
        $('a', actions).focus();
      } else {
        setPhase('ph2', 'fail');
        setPhase('ph3', 'fail');
        $('#ph3-title').textContent = 'Not recorded';
        $('#ph3-sub').textContent = res.message || 'Something went wrong.';
        const already = /already/.test(res.message || '');
        actions.innerHTML = already ? `<a class="btn btn-primary" href="/receipt/">See my receipt</a>` : `<button class="btn btn-ghost" id="close-cast">Back to my ballot</button>`;
        const c = $('#close-cast'); if (c) c.addEventListener('click', () => wrap.remove());
      }
    }

    function setPhase(id, state) {
      const el = $('#' + id);
      el.classList.remove('active', 'done', 'fail');
      el.classList.add(state);
      const ic = $('.ic', el);
      if (state === 'done') ic.innerHTML = icon('check');
      else if (state === 'fail') ic.innerHTML = icon('x');
      else if (state === 'active') ic.innerHTML = '<span class="spinner"></span>';
    }

    render();
  }

  // Page: receipt

  function pageReceipt() {
    const r = readJSON('receipt-data');
    const name = readJSON('voter-name');
    const root = $('#receipt-root');
    const fresh = new URLSearchParams(location.search).has('fresh');
    const when = r.time ? new Date(r.time).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '';
    const groups = (r.public_key || '').match(/.{1,4}/g) || [];
    const byPos = {};
    r.choices.forEach((c) => { (byPos[c.position] = byPos[c.position] || []).push(c.candidate); });
    const choices = Object.entries(byPos).map(([pos, list]) => `<div class="review-item" style="padding:10px 0;border-bottom:1px solid var(--line)">
        <div class="pos">${esc(pos)}</div><div class="who-list">${list.map((c) => `<span class="pick">${avatar(c, 'sm')}${esc(c.name)}</span>`).join('')}</div></div>`).join('');
    root.innerHTML = `
      ${fresh ? `<div class="banner ok" style="margin-bottom:20px"><span class="bi">${icon('check')}</span><div><b>Thank you, ${esc(name)}. Your ballot is recorded.</b><span>Keep this receipt. You can come back any time to check it against every copy.</span></div></div>` : ''}
      <article class="card ticket">
        <div class="ticket-top"><div class="label">Ballot receipt</div><div class="big">Block #${r.block == null ? '?' : r.block}</div>
          <div class="sub">${esc(name)} · ${esc(when)}</div></div>
        <div style="height:24px"></div><div class="perf" aria-hidden="true"></div>
        <div class="ticket-body stack">
          <div><div class="section-title">Your choices</div>${choices}</div>
          <dl class="kv">
            <dt>Your public key</dt><dd class="fingerprint">${groups.slice(0, 16).join(' ')}</dd>
            <dt>What it proves</dt><dd class="muted">Only your private key could have signed this ballot. If anyone changed a single character, the signature would no longer match.</dd>
          </dl>
        </div>
      </article>
      <section class="card card-pad" style="margin-top:20px">
        <div class="spread" style="margin-bottom:16px"><div><h3 style="font-size:18px">Check your ballot on every copy</h3>
          <p class="muted" style="margin-top:4px">We download each node's chain and look for your signed ballot.</p></div>
          <div class="row"><span id="verify-chip"></span><button class="btn btn-ghost btn-sm" id="reverify">${icon('refresh')} Check again</button></div></div>
        <div id="verify">${['interior', 'commission', 'delegates'].map((n) => `<div class="verify-row" id="v-${n}"><span class="vi"><span class="spinner"></span></span>
          <div class="vt"><b>${esc(r.labels[n] || n)}</b><span>Checking…</span></div></div>`).join('')}</div>
      </section>
      <div class="row wrap-ok" style="margin-top:20px">
        <a class="btn btn-primary" href="/explorer/#block-${r.block}">${icon('cube')} See block #${r.block} in the explorer</a>
        <a class="btn btn-ghost" href="/results/">Live results</a>
      </div>`;

    async function verify() {
      ['interior', 'commission', 'delegates'].forEach((n) => {
        const row = $('#v-' + n); row.className = 'verify-row';
        $('.vi', row).innerHTML = '<span class="spinner"></span>'; $('.vt span', row).textContent = 'Checking…';
      });
      const d = await api('/api/verify/');
      if (!d.ok) { toast(d.message || 'Could not check right now.', 'bad'); return; }
      let good = 0;
      for (const n of d.nodes) {
        await sleep(250);
        const row = $('#v-' + n.name);
        if (!row) continue;
        row.classList.add(n.status);
        const text = {
          verified: `Found in block #${n.block}. The chain and your signature check out.`,
          tampered: `Your ballot is in block #${n.block}, but this copy was changed. The other copies decide.`,
          missing: 'Your ballot is not in this copy yet. It copies missing blocks from its peers within seconds.',
          down: 'This node is offline right now. It catches up when it comes back.',
        }[n.status];
        $('.vi', row).innerHTML = icon(n.status === 'verified' ? 'check' : n.status === 'down' ? 'alert' : 'x');
        $('.vt span', row).textContent = text;
        if (n.status === 'verified') good++;
      }
      const chip = $('#verify-chip');
      chip.className = 'chip ' + (good >= 2 ? 'chip-ok' : 'chip-bad');
      chip.innerHTML = `${icon(good >= 2 ? 'shield' : 'alert')} Verified on ${good} of ${d.nodes.length}`;
    }
    $('#reverify').addEventListener('click', verify);
    verify();
  }

  // Page: results

  function pageResults() {
    const root = $('#results'), chips = $('#result-chips'), turnout = $('#turnout-card');
    let shape = '';
    poll(async () => {
      const d = await api('/api/overview/');
      if (d._status !== 200) return;
      const s = d.stats;
      chips.innerHTML = `<span class="chip ${d.confirmed ? 'chip-ok' : 'chip-bad'}">${icon(d.confirmed ? 'shield' : 'alert')} ${d.confirmed ? 'Confirmed by ' + joinAnd(d.majority.map((m) => SHORT[m] || m)) : 'No majority: result not confirmed'}</span>
        <span class="chip chip-neutral"><span class="dot live" style="color:var(--ok)"></span> Updated ${esc(d.time)}</span>`;
      const pct = s.voters ? Math.round((100 * s.ballots_ledger) / s.voters) : 0;
      const C = 2 * Math.PI * 46;
      if (!$('.ring-chart', turnout)) {
        turnout.innerHTML = `<div class="spread"><div class="turnout">
            <svg class="ring-chart" viewBox="0 0 112 112" role="img" aria-label="Turnout"><circle class="bg" cx="56" cy="56" r="46" stroke-width="12" fill="none"/>
            <circle class="fg" cx="56" cy="56" r="46" stroke-width="12" fill="none" stroke-linecap="round" transform="rotate(-90 56 56)" stroke-dasharray="${C}" stroke-dashoffset="${C}"/>
            <text x="56" y="63" text-anchor="middle" id="pct">0%</text></svg>
            <div><h2 style="font-size:22px">Turnout</h2><p class="muted" id="turnout-text"></p></div></div>
            <div class="row wrap-ok"><div class="kpi"><b id="r-blocks">0</b><span>Blocks</span></div><div class="kpi"><b id="r-nodes">0</b><span>Healthy copies</span></div></div></div>`;
      }
      $('.ring-chart .fg', turnout).style.strokeDashoffset = C * (1 - pct / 100);
      countTo($('#pct'), pct, '%');
      $('#turnout-text').textContent = `${s.ballots_ledger} of ${s.voters} registered voters have cast a ballot.`;
      countTo($('#r-blocks'), s.blocks);
      $('#r-nodes').textContent = `${s.valid_nodes} / ${d.nodes.length}`;

      const newShape = JSON.stringify(d.positions.map((p) => [p.id, p.candidates.map((c) => c.id)]));
      if (newShape !== shape) {
        shape = newShape;
        root.innerHTML = d.positions.map((p) => `<section class="card" data-p="${p.id}">
          <div class="card-head"><h3>${esc(p.name)}</h3><span class="faint" style="font-size:13px">${p.max_vote > 1 ? p.max_vote + ' seats' : '1 seat'}</span></div>
          <div style="padding:6px 24px 12px">${p.candidates.map((c) => `<div class="result-row" data-c="${c.id}">
            ${avatar(c, 'sm')}<div><div class="name">${esc(c.name)} <span class="lead-chip"></span></div><div class="bar"><i style="background:${esc(c.color)}"></i></div></div>
            <div class="count"><span class="v">0</span><small class="share">0%</small></div></div>`).join('')}</div></section>`).join('');
      }
      d.positions.forEach((p) => {
        const card = $(`[data-p="${p.id}"]`, root);
        const total = p.candidates.reduce((a, c) => a + (c.ledger || 0), 0);
        const ranked = [...p.candidates].sort((a, b) => (b.ledger || 0) - (a.ledger || 0));
        const cutoff = ranked[p.max_vote - 1] ? ranked[p.max_vote - 1].ledger || 0 : 0;
        const tiedAtCut = ranked.filter((c) => (c.ledger || 0) === cutoff).length > 1 && ranked.slice(p.max_vote).some((c) => (c.ledger || 0) === cutoff);
        const body = card.querySelector('div[style]');
        ranked.forEach((c) => {
          const row = $(`[data-c="${c.id}"]`, card);
          body.appendChild(row); // keeps the leader on top
          const v = c.ledger == null ? 0 : c.ledger;
          countTo($('.v', row), v);
          $('.share', row).textContent = total ? Math.round((100 * v) / total) + '%' : '0%';
          $('.bar i', row).style.width = total ? (100 * v) / total + '%' : '0';
          const lead = v > 0 && v >= cutoff;
          $('.lead-chip', row).innerHTML = lead ? `<span class="chip ${tiedAtCut && v === cutoff ? 'chip-warn' : 'chip-ok'}">${tiedAtCut && v === cutoff ? 'Tied' : 'Leading'}</span>` : '';
        });
      });
    }, 3000);
  }

  // Page: explorer

  function pageExplorer() {
    const chainEl = $('#chain'), detail = $('#detail'), find = $('#find');
    let blocks = [], selected = null, lastSig = '';
    const fromHash = () => { const m = location.hash.match(/block-(\d+)/); return m ? +m[1] : null; };
    selected = fromHash();

    function select(i, scroll = true) {
      selected = i;
      history.replaceState(null, '', '#block-' + i);
      $$('.block', chainEl).forEach((b) => b.setAttribute('aria-pressed', String(+b.dataset.i === i)));
      const el = $('#block-' + i);
      if (el && scroll) el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
      renderDetail();
    }

    function renderDetail() {
      const b = blocks.find((x) => x.index === selected);
      if (!b) { detail.innerHTML = '<div class="empty">Select a block above.</div>'; return; }
      const votes = b.votes.map((v) => `<div class="vote-entry">
          <div class="hash-line"><span class="k">Voter key</span><code>${esc(v.voter)}</code></div>
          <div class="hash-line" style="margin-top:6px"><span class="k">Signature</span><code>${esc(short(v.signature, 64))}</code></div>
          <div style="margin-top:12px;display:grid;gap:6px">${v.choices.map((c) => `<div class="row wrap-ok"><span class="faint" style="width:120px;font-size:13.5px">${esc(c.position)}</span><b style="font-size:14.5px">${esc(c.candidates.join(', '))}</b></div>`).join('')}</div></div>`).join('');
      detail.innerHTML = `
        <div class="spread"><div><div class="section-title" style="margin-bottom:4px">Block</div><h2 style="font-size:28px">#${b.index}</h2></div>
          <div class="row wrap-ok"><span class="chip chip-neutral">${b.index === 0 ? 'Genesis block' : plural(b.votes.length, 'ballot')}</span>${b.index === 0 ? '' : `<span class="chip chip-neutral">${fmtTime(b.timestamp)}</span>`}</div></div>
        <div style="margin-top:18px;display:grid;gap:8px">
          <div class="hash-line"><span class="k">Hash</span><code>${esc(b.hash)}</code></div>
          <div class="hash-line"><span class="k">Previous hash</span>${b.index > 0 ? `<a href="#block-${b.index - 1}" data-go="${b.index - 1}"><code>${esc(b.prev_hash)}</code></a>` : `<code>${esc(b.prev_hash)}</code>`}</div>
        </div>
        ${b.index === 0 ? '<p class="muted" style="margin-top:18px">The genesis block is the same on every node. Every other block points back to it through the chain of hashes.</p>' : votes}
        <p class="faint" style="margin-top:18px;font-size:13px">The hash is a SHA-256 fingerprint of this block's number, time, ballots and the previous hash. Changing anything here would change it, and the next block would no longer point to it.</p>`;
      const g = $('[data-go]', detail);
      if (g) g.addEventListener('click', (e) => { e.preventDefault(); select(+g.dataset.go); });
    }

    poll(async () => {
      const d = await api('/api/chain/');
      const list = d.blocks || [];
      const sig = list.map((b) => b.hash).join();
      if (sig === lastSig) return;
      const grew = blocks.length && list.length > blocks.length;
      lastSig = sig; blocks = list;
      if (selected == null || !blocks.some((b) => b.index === selected)) selected = blocks.length ? blocks[blocks.length - 1].index : null;
      chainEl.innerHTML = chainHTML(blocks, selected);
      $$('.block', chainEl).forEach((b) => b.addEventListener('click', () => select(+b.dataset.i)));
      if (grew) { const last = $$('.block', chainEl).pop(); last.classList.add('new'); toast('A new block was added to the chain.', 'ok'); }
      if (selected != null) select(selected, true);
    }, 4000);

    find.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      const q = find.value.trim().toLowerCase().replace(/^#/, '');
      if (!q) return;
      let hit = /^\d+$/.test(q) ? blocks.find((b) => b.index === +q) : blocks.find((b) => b.hash.startsWith(q) || b.votes.some((v) => v.voter.includes(q)));
      if (hit) select(hit.index); else toast('No block matches “' + find.value + '”.', 'warn');
    });
    window.addEventListener('hashchange', () => { const i = fromHash(); if (i != null && i !== selected) select(i); });
  }

  // Page: control room

  function pageControl() {
    const labels = readJSON('labels-data') || {};
    const feed = $('#feed');
    let prev = null;

    function log(text, color) {
      const li = document.createElement('li');
      li.innerHTML = `<time>${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}</time><span class="fi" style="background:${color}"></span><span>${text}</span>`;
      feed.prepend(li);
      while (feed.children.length > 40) feed.lastChild.remove();
    }

    async function tamper(node, rehash) {
      const ok = await modal({
        title: `Tamper with the ${labels[node] || node} copy?`,
        body: rehash
          ? 'This changes one stored ballot in that node\'s memory <b>and recomputes every hash</b>, like a careful attacker would. The signature check still catches it. Restart the node to restore its copy from disk.'
          : 'This changes one stored ballot in that node\'s memory to show how the system detects it. Restart the node to restore its copy from disk.',
        confirm: 'Tamper with this copy', danger: true,
      });
      if (!ok) return;
      const r = await api('/api/tamper/', { method: 'POST', body: { node, rehash } });
      if (r.ok) { toast('Demonstration: a ballot was changed in the ' + (labels[node] || node) + ' copy.', 'warn'); p.now(); }
      else toast(r.message || 'Could not reach the node.', 'bad');
    }

    const p = poll(async () => {
      const d = await api('/api/overview/');
      if (d._status !== 200) return;
      const s = d.stats;
      const allOk = s.valid_nodes === d.nodes.length;
      const banner = $('#banner');
      const kind = !d.confirmed ? 'bad' : allOk ? 'ok' : 'warn';
      const title = !d.confirmed ? 'No majority: the result cannot be confirmed' : allOk ? 'All three copies agree' : `Result confirmed by ${joinAnd(d.majority.map((m) => labels[m] || m))}`;
      const sub = !d.confirmed ? 'Fewer than two valid copies agree. The system refuses to guess a result.'
        : allOk ? `${plural(s.blocks, 'block')} and ${plural(s.ballots_ledger, 'ballot')} on every node. The website database ${d.db_matches ? 'matches' : 'does not match'} the ledger.`
          : 'One copy needs attention, but the majority still decides the official result.';
      banner.innerHTML = `<div class="banner ${kind}"><span class="bi">${icon(kind === 'ok' ? 'shield' : 'alert')}</span><div><b>${esc(title)}</b><span>${esc(sub)}</span></div></div>`;

      $('#nodes').innerHTML = d.nodes.map((n) => `<article class="card node-card ${n.status}">
          <div class="spread"><div><h3>${esc(n.label)}</h3><div class="faint mono" style="font-size:12px;margin-top:2px">${esc(n.url)}</div></div>
            <span class="chip ${n.status === 'VALID' ? 'chip-ok' : n.status === 'TAMPERED' ? 'chip-bad' : 'chip-warn'}"><span class="dot ${n.status === 'DOWN' ? '' : 'live'}"></span> ${n.status === 'VALID' ? 'Valid' : n.status === 'TAMPERED' ? 'Tampered' : 'Offline'}</span></div>
          <div class="stats"><div class="stat"><b>${n.status === 'DOWN' ? '—' : n.blocks}</b><span>Blocks</span></div><div class="stat"><b>${n.status === 'DOWN' ? '—' : n.ballots}</b><span>Ballots</span></div></div>
          <p class="reason">${esc(n.status === 'DOWN' ? 'Not reachable. Votes keep flowing to the other two; this node catches up when it restarts.' : n.reason)}${n.tip ? `<br><span class="faint mono" style="font-size:12px">Last block ${esc(n.tip)}…</span>` : ''}</p>
          <div class="actions">${n.status === 'DOWN' ? '' : `<button class="btn btn-danger btn-sm" data-t="${n.name}">Tamper a ballot</button><button class="btn btn-ghost btn-sm" data-t="${n.name}" data-r="1">Tamper and rehash</button>`}</div>
        </article>`).join('');
      $$('[data-t]').forEach((b) => b.addEventListener('click', () => tamper(b.dataset.t, !!b.dataset.r)));
      renderNetwork($('#network'), d);

      const rows = [];
      d.positions.forEach((p) => p.candidates.forEach((c) => rows.push({ p: p.name, c, same: c.ledger === c.website })));
      $('#compare').innerHTML = `<thead><tr><th>Position</th><th>Candidate</th><th>Ledger (official)</th><th>Website database</th><th>Check</th></tr></thead><tbody>${rows.map((r) => `<tr class="${d.confirmed && !r.same ? 'diff' : ''}">
          <td>${esc(r.p)}</td><td><div class="row">${avatar(r.c, 'sm')}<b>${esc(r.c.name)}</b></div></td><td class="num"><b>${r.c.ledger == null ? '—' : r.c.ledger}</b></td><td class="num">${r.c.website}</td>
          <td>${r.c.ledger == null ? '<span class="chip chip-neutral">No majority</span>' : r.same ? `<span class="chip chip-ok">${icon('check')} Same</span>` : `<span class="chip chip-bad">${icon('x')} Different</span>`}</td></tr>`).join('')}</tbody>`;
      $('#match-chip').innerHTML = d.confirmed ? (d.db_matches ? `<span class="chip chip-ok">${icon('check')} Website matches the ledger</span>` : `<span class="chip chip-bad">${icon('alert')} Website differs from the ledger</span>`) : '';
      $('#updated').innerHTML = `<span class="dot live" style="color:var(--ok)"></span> Live · ${esc(d.time)}`;

      if (prev) {
        d.nodes.forEach((n) => {
          const before = prev.nodes.find((x) => x.name === n.name);
          if (before && before.status !== n.status) {
            const color = n.status === 'VALID' ? 'var(--ok)' : n.status === 'TAMPERED' ? 'var(--bad)' : 'var(--warn)';
            const what = n.status === 'VALID' ? 'is valid again' : n.status === 'TAMPERED' ? 'copy was tampered with: ' + esc(n.reason) : 'went offline';
            log(`<b>${esc(n.label)}</b> ${what}`, color);
          }
        });
        if (s.blocks > prev.stats.blocks) log(`<b>Block #${s.blocks - 1}</b> added · ${plural(s.ballots_ledger, 'ballot')} on the ledger`, 'var(--brand)');
        if (s.voted_website !== prev.stats.voted_website) log(`Website database now counts <b>${s.voted_website}</b> voters`, 'var(--ink-3)');
        if (d.db_matches !== prev.db_matches && d.confirmed) log(d.db_matches ? 'Website database matches the ledger again' : '<b>Website database no longer matches the ledger</b>', d.db_matches ? 'var(--ok)' : 'var(--bad)');
        if (d.confirmed !== prev.confirmed) log(d.confirmed ? 'A majority of copies agree again' : '<b>No majority</b>: the result cannot be confirmed', d.confirmed ? 'var(--ok)' : 'var(--bad)');
      } else {
        log(`Watching ${d.nodes.length} nodes · ${plural(s.blocks, 'block')} · ${plural(s.ballots_ledger, 'ballot')}`, 'var(--brand)');
      }
      prev = d;
    }, 2000);
  }

  const pages = { home: pageHome, vote: pageVote, receipt: pageReceipt, results: pageResults, explorer: pageExplorer, control: pageControl };
  const run = pages[document.body.dataset.page];
  if (run) run();
})();
