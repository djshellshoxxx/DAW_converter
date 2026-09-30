'use strict';
/* Rackcheck front end. Plain JS, no build step, no remote assets (SPEC-03 section 2, SPEC-07).
   All project-derived text is inserted with textContent / createTextNode, never as HTML. */

/* ------------------------------------------------------------------ helpers */
const $ = (sel, root) => (root || document).querySelector(sel);

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'value' || k === 'checked' || k === 'disabled' || k === 'selected') el[k] = v;
    else el.setAttribute(k, v === true ? '' : String(v));
  }
  const add = (kid) => {
    if (kid === null || kid === undefined || kid === false) return;
    if (Array.isArray(kid)) kid.forEach(add);
    else if (kid instanceof Node) el.appendChild(kid);
    else el.appendChild(document.createTextNode(String(kid)));
  };
  kids.forEach(add);
  return el;
}
const btn = (label, onclick, cls, extra) =>
  h('button', Object.assign({ type: 'button', class: 'btn ' + (cls || ''), onclick }, extra || {}), label);
const linkBtn = (label, onclick, extra) =>
  h('button', Object.assign({ type: 'button', class: 'link', onclick }, extra || {}), label);

const isObj = (v) => v !== null && typeof v === 'object';
const fmtDate = (iso) => { if (!iso) return ''; const d = new Date(iso); return isNaN(d) ? String(iso) : d.toLocaleString(); };
const fmtBytes = (n) => {
  if (n === null || n === undefined) return '';
  const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0; let v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return (i === 0 ? v : v.toFixed(1)) + ' ' + u[i];
};
const fmtDur = (s) => {
  if (s === null || s === undefined) return '';
  const m = Math.floor(s / 60); const r = (s - m * 60).toFixed(1);
  return m + ':' + (r < 10 ? '0' : '') + r;
};
const basename = (p) => String(p || '').split(/[\\/]/).filter(Boolean).pop() || String(p || '');
const dirname = (p) => String(p || '').replace(/[\\/][^\\/]*$/, '');
const plural = (n, a, b) => n + ' ' + (n === 1 ? a : b);
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

function fmtVal(v) {
  if (v === null || v === undefined || v === '') return h('span', { class: 'na' }, '—');
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (Array.isArray(v) && v.every((x) => !isObj(x))) return v.length ? v.join(', ') : h('span', { class: 'na' }, '—');
  if (isObj(v)) return h('span', { class: 'mono' }, JSON.stringify(v));
  return String(v);
}

/* ------------------------------------------------------------------ bridge */
const apiReady = new Promise((resolve) => {
  if (window.pywebview && window.pywebview.api) resolve();
  else window.addEventListener('pywebviewready', () => resolve());
});
async function call(name, ...args) {
  await apiReady;
  try {
    const fn = window.pywebview.api[name];
    return await fn(...args);
  } catch (e) {
    return { error: { code: 'BRIDGE_ERROR', message: 'The app could not reach its engine. Try restarting Rackcheck.', details: {} } };
  }
}
const isErr = (r) => isObj(r) && isObj(r.error) && typeof r.error.code === 'string';

/* ------------------------------------------------------------------ state */
const S = {
  view: 'home', info: null, settings: {}, recent: [], inv: null, invProgress: null, folders: [],
  scan: null, cur: null, tab: 'plugins', picker: null, errorView: null,
  pFilter: 'all', pSearch: '', pSort: { key: 'status', dir: 1 }, pGroup: 'none', pView: 'unique', idFilter: null,
  warnAll: false, invFilter: { search: '', format: '', arch: '', dupes: false },
};

const STATUS = {
  installed_same_format: { icon: '✓', text: 'Installed', cls: 'ok', rank: 3 },
  installed_other_format: { icon: '⇄', text: 'Installed in another format', cls: 'other', rank: 1 },
  not_installed: { icon: '✕', text: 'Not installed on this computer', cls: 'missing', rank: 0 },
  stock: { icon: '◆', text: 'Built in (needs the DAW)', cls: 'stock', rank: 4 },
  unknown: { icon: '?', text: 'Unknown', cls: 'unknown', rank: 2 },
  inventory_unavailable: { icon: '?', text: 'Installed status unknown', cls: 'unknown', rank: 2 },
};
const statusOf = (state) => STATUS[state] || STATUS.unknown;

const LINK_SRC = {
  kb_plugin: 'Official link from our plugin database',
  kb_vendor: 'Vendor homepage from our plugin database',
  moduleinfo: 'Link declared by the installed plugin',
  clap_descriptor: 'Link declared by the installed plugin',
  bundle_id_heuristic: 'Guessed from the plugin identifier, may be wrong',
  search: 'Search for it (no official link known)',
};
const LINK_ICON = { kb_plugin: '★', kb_vendor: '★', moduleinfo: '◎', clap_descriptor: '◎', bundle_id_heuristic: '≈', search: '🔍' };

/* ------------------------------------------------------------------ toasts, menus */
function toast(message, action) {
  const t = h('div', { class: 'toast', role: 'status' }, h('span', null, message),
    action ? h('button', { type: 'button', class: 'link', onclick: () => { action.run(); t.remove(); } }, action.label) : null);
  $('#toasts').appendChild(t);
  setTimeout(() => t.remove(), 9000);
}
function showError(err) { toast(err && err.message ? err.message : 'Something went wrong.'); }

function closeMenus() {
  $('#menu').hidden = true;
  document.querySelectorAll('.popmenu').forEach((m) => m.remove());
}
document.addEventListener('click', (e) => { if (!e.target.closest('.popmenu, .ctxmenu, [data-popper]')) closeMenus(); });
function contextMenu(e, items) {
  e.preventDefault();
  const m = $('#menu'); m.textContent = '';
  items.forEach(([label, fn]) => m.appendChild(h('button', { type: 'button', onclick: () => { closeMenus(); fn(); } }, label)));
  m.hidden = false;
  m.style.left = Math.min(e.clientX, window.innerWidth - 230) + 'px';
  m.style.top = Math.min(e.clientY, window.innerHeight - 40 * items.length - 10) + 'px';
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast('Copied.'); return; } catch (e) { /* fall through */ }
  const ta = h('textarea', { class: 'sr' }); ta.value = text; document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); toast('Copied.'); } catch (e) { toast('Copying isn\'t available here.'); }
  ta.remove();
}
async function openUrl(url) {
  const r = await call('open_url', url);
  if (isErr(r)) showError(r.error);
}
async function reveal(path) {
  const r = await call('reveal_path', path);
  if (isErr(r)) showError(r.error);
}

/* ------------------------------------------------------------------ friendly errors */
function friendly(err) {
  const d = (err && err.details) || {};
  const det = d.detection || {};
  const fmt = d.format || det.format;
  const hintFor = () => {
    const entry = ((S.info && S.info.supported_formats) || []).find((f) => (f.formats || []).includes(fmt));
    return entry && entry.hint;
  };
  switch (err && err.code) {
    case 'UNSUPPORTED_FORMAT':
      return { title: 'We can\'t read this file type yet.', body: d.reason ? 'What we saw: ' + d.reason : '', hint: hintFor() };
    case 'READER_NOT_AVAILABLE':
      if (fmt === 'protools_ptx' || fmt === 'protools_text') {
        return { title: 'Pro Tools sessions need one extra step for now.', steps: [
          'In Pro Tools, choose File > Export > Session Info as Text.',
          'Save the text file anywhere.',
          'Drop the text file here.'], body: fmt === 'protools_text' ? 'Reading Session Info text exports isn\'t available in this version yet.' : '' };
      }
      return { title: err.message, body: '', hint: hintFor() };
    case 'CORRUPT_PROJECT':
      return { title: 'This project file looks damaged or incomplete.', body: err.message };
    case 'NO_PROJECT_FOUND': return { title: err.message, body: 'Try dropping the project file itself, or a folder that contains one.' };
    case 'ARCHIVE_REJECTED': return { title: 'We couldn\'t safely open that zip.', body: err.message };
    case 'PATH_NOT_FOUND': return { title: err.message, body: 'It may have been moved or deleted.' };
    case 'BUSY': return { title: err.message, body: '' };
    case 'REPORT_INVALID': return { title: err.message, body: 'Only reports exported from Rackcheck (JSON) can be viewed.' };
    default: return { title: err ? err.message : 'Something went wrong.', body: err && err.code ? '(' + err.code + ')' : '' };
  }
}

/* ------------------------------------------------------------------ events from Python */
window.addEventListener('rackcheck', (e) => onEvent(e.detail.event, e.detail.payload || {}));

function onEvent(name, p) {
  if (name === 'app.dropped') return handlePaths(p.paths || []);
  if (name === 'inventory.updated') return onInventoryUpdated(p);
  if (!name.startsWith('job.')) return;
  if (p.kind === 'inventory') return onInventoryJob(name, p);
  const sc = S.scan;
  if (!sc) return;
  if (!sc.jobId && sc.awaiting) sc.jobId = p.job_id;
  if (p.job_id !== sc.jobId) return;
  if (name === 'job.progress') {
    sc.stage = p.stage; sc.message = p.message; sc.percent = p.percent;
    if (S.view === 'scanning') renderScanning();
  } else if (name === 'job.done') {
    sc.ids.push(...(p.report_ids || [p.report_id]));
    (p.errors || []).forEach((er) => sc.errors.push(er));
    sc.jobId = null; nextInQueue();
  } else if (name === 'job.failed') {
    sc.errors.push(p.error); sc.jobId = null; nextInQueue();
  } else if (name === 'job.cancelled') {
    S.scan = null; toast('Scan cancelled.'); goto('home');
  }
}

/* ------------------------------------------------------------------ navigation */
function goto(view) {
  S.view = view; closePanel(); render();
}
function render() {
  document.querySelectorAll('.nav').forEach((b) => {
    b.classList.toggle('active', b.dataset.view === S.view || (S.view === 'report' && b.dataset.view === 'home'));
  });
  const fn = { home: renderHome, recent: renderRecent, installed: renderInstalled, settings: renderSettings,
    firstrun: renderFirstRun, scanning: renderScanning, report: renderReport, picker: renderPicker, error: renderErrorView }[S.view];
  const main = $('#main'); const top = main.scrollTop;
  main.textContent = ''; (fn || renderHome)(main);
  if (S.view === 'report') main.scrollTop = top;
  renderSideStatus();
}
document.querySelectorAll('.nav').forEach((b) => b.addEventListener('click', () => {
  const v = b.dataset.view;
  if (v === 'installed') loadInstalled();
  if (v === 'recent' || v === 'home') refreshRecent();
  if (v === 'settings') loadFolders();
  goto(v);
}));

function renderSideStatus() {
  const el = $('#side-status'); el.textContent = '';
  if (S.invProgress) el.textContent = 'Scanning plugins… ' + (S.invProgress.percent != null ? Math.round(S.invProgress.percent * 100) + '%' : '');
  else if (S.inv && S.inv.scanned_at) el.textContent = plural(S.inv.plugins.length, 'plugin', 'plugins') + ' found on this computer';
  else el.textContent = 'Plugins not scanned yet';
  if (S.scan && S.view !== 'scanning') el.appendChild(h('div', null, 'Scanning a project…'));
}

/* ------------------------------------------------------------------ drop handling / scan flow */
const dz = { depth: 0 };
const hasFiles = (e) => !!(e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files'));
window.addEventListener('dragenter', (e) => { e.preventDefault(); if (!hasFiles(e)) return; dz.depth++; $('#dropveil').hidden = false; });
window.addEventListener('dragover', (e) => e.preventDefault());
window.addEventListener('dragleave', () => { dz.depth = Math.max(0, dz.depth - 1); if (!dz.depth) $('#dropveil').hidden = true; });
window.addEventListener('drop', (e) => { e.preventDefault(); dz.depth = 0; $('#dropveil').hidden = true; });
document.addEventListener('click', (e) => {
  const a = e.target.closest('a[href]');
  if (a) { e.preventDefault(); openUrl(a.href); }
});

async function browse() {
  const r = await call('choose_files');
  if (isErr(r)) return showError(r.error);
  if (r.paths) handlePaths(r.paths);
}
async function browseFolder() {
  const r = await call('choose_folder');
  if (isErr(r)) return showError(r.error);
  if (r.paths) handlePaths(r.paths);
}

async function handlePaths(paths) {
  $('#dropveil').hidden = true;
  if (!paths.length) return toast('Nothing to scan. Try Browse instead.');
  if (S.scan) return toast('A scan is already running. Wait for it or cancel it first.');
  const res = await call('detect', paths);
  if (isErr(res)) return showError(res.error);
  const items = [];
  const failures = [];
  for (const e of res) {
    if (e.error) { failures.push(e.error); continue; }
    if (!e.projects_found.length) { failures.push(e.format === 'unsupported' ? { code: 'UNSUPPORTED_FORMAT', message: 'We can\'t read this file type yet.', details: { reason: e.reason, format: e.format, detection: e } } : { code: 'NO_PROJECT_FOUND', message: e.format === 'generic_zip' ? 'No project files found in this zip.' : 'No project files found here.', details: {} }); continue; }
    for (const p of e.projects_found) items.push({ path: e.path, rel: p.rel_path, info: p });
  }
  if (!items.length) { S.errorView = failures[0] || null; if (S.errorView) goto('error'); return; }
  if (items.length === 1) {
    if (items[0].info.is_report) return openReportFile(items[0].path);
    return startQueue([items[0]]);
  }
  S.picker = { items: items.map((it) => Object.assign({ on: !it.info.is_backup && it.info.readable }, it)), failures };
  goto('picker');
}

async function openReportFile(path) {
  const r = await call('open_report_file', path);
  if (isErr(r)) { S.errorView = r.error; return goto('error'); }
  refreshRecent();
  openReport(r.report_id);
}

function startQueue(items) {
  S.scan = { queue: items, index: -1, ids: [], errors: [], jobId: null, awaiting: false, stage: 'detect', message: 'Starting…', percent: null, name: basename(items[0].path) };
  goto('scanning');
  nextInQueue();
}
async function nextInQueue() {
  const sc = S.scan; if (!sc) return;
  sc.index++;
  if (sc.index >= sc.queue.length) {
    S.scan = null;
    refreshRecent();
    if (sc.ids.length) { await openReport(sc.ids[0], sc.ids, sc.errors); return; }
    S.errorView = sc.errors[sc.errors.length - 1]; goto('error'); return;
  }
  const it = sc.queue[sc.index];
  sc.name = basename(it.rel || it.path); sc.stage = 'detect'; sc.message = 'Starting…'; sc.percent = null;
  sc.awaiting = true; sc.jobId = null;
  if (S.view === 'scanning') renderScanning();
  const r = await call('start_scan', it.path, { use_inventory: true, projects: [it.rel] });
  sc.awaiting = false;
  if (isErr(r)) { sc.errors.push(r.error); return nextInQueue(); }
  if (!sc.jobId) sc.jobId = r.job_id;
}

async function rescan(quiet) {
  const c = S.cur; if (!c || c.imported || !c.input_path) return;
  if (S.scan) { if (!quiet) toast('A scan is already running.'); return; }
  const prevBatch = c.batch;
  if (quiet) {
    // Refresh in place without leaving the report (used when the plugin inventory finishes).
    S.scan = { queue: [{ path: c.input_path, rel: c.rel_path }], index: -1, ids: [], errors: [], jobId: null, awaiting: false, stage: 'detect', message: '', percent: null, silent: true };
    nextInQueue(); return;
  }
  startQueue([{ path: c.input_path, rel: c.rel_path }]);
  S.scan.prevBatch = prevBatch;
}

async function openReport(id, batchIds, batchErrors) {
  const r = await call('get_report', id);
  if (isErr(r)) { S.errorView = r.error; return goto('error'); }
  const prev = S.cur;
  S.cur = r;
  S.cur.batch = batchIds && batchIds.length > 1 ? batchIds : (prev && prev.batch && prev.batch.includes(id) ? prev.batch : null);
  S.cur.batchErrors = batchErrors || [];
  S.idFilter = null; S.warnAll = false;
  if (!(prev && prev.report_id === id)) S.tab = 'plugins';
  S.view = 'report'; closePanel(); render();
}

/* ------------------------------------------------------------------ home */
async function refreshRecent() {
  const r = await call('list_recent');
  if (!isErr(r)) { S.recent = r; if (['home', 'recent'].includes(S.view)) render(); }
}
function dot(score) {
  const map = { green: ['✓', 'Ready'], yellow: ['!', 'Check'], red: ['✕', 'Problems'] };
  const m = map[score] || ['–', 'Unknown'];
  return h('span', { class: 'dot ' + (map[score] ? score : 'none'), title: 'Send-ready: ' + m[1] }, m[0] + ' ' + m[1]);
}
function recentItem(e) {
  return h('button', { type: 'button', class: 'item', onclick: () => openReport(e.report_id) },
    h('span', { class: 'grow' }, e.project_name || '(unnamed)'),
    h('span', { class: 'muted small' }, e.daw || ''),
    h('span', { class: 'muted small' }, fmtDate(e.scanned_at)),
    dot(e.send_ready));
}
function renderHome(root) {
  const daws = ((S.info && S.info.supported_formats) || []);
  const zone = h('div', { class: 'dropzone', id: 'dropzone' },
    h('div', { class: 'big' }, 'Drop a project file, folder, or zip here'),
    h('div', { class: 'muted' }, 'You can also drop a report you exported earlier (.json) to view it.'),
    h('div', { class: 'row' }, btn('Browse files', browse, 'primary'), btn('Browse for a folder', browseFolder)));
  const list = h('div', { class: 'daws' }, daws.map((d) => {
    const soon = !d.readable;
    return h('span', { class: 'daw' + (soon ? ' soon' : ''), title: d.hint || (soon ? 'Recognised, but can\'t be read in this version yet.' : 'Supported'), tabindex: d.hint ? '0' : null },
      d.daw_name, soon ? h('span', { class: 'note' }, ' (not yet)') : null);
  }));
  const hints = daws.filter((d) => d.hint);
  root.append(h('h1', null, 'Check a project'), zone,
    h('div', { class: 'muted small', style: null }, 'Reads the project file only; nothing is changed and nothing leaves your computer.'), list,
    hints.length ? h('div', { class: 'muted small' }, hints.map((d) => h('div', null, h('b', null, d.daw_name + ': '), d.hint))) : null,
    h('h2', null, 'Recent scans'),
    S.recent.length ? h('div', { class: 'list' }, S.recent.slice(0, 10).map(recentItem)) : h('p', { class: 'muted' }, 'Nothing yet. Drop a project above to get started.'));
}
function renderRecent(root) {
  root.append(h('div', { class: 'row spread' }, h('h1', null, 'Recent scans'),
    S.recent.length ? btn('Clear list', async () => { const r = await call('clear_recent'); if (isErr(r)) return showError(r.error); S.recent = []; render(); toast('Recent scans cleared.'); }) : null),
  S.recent.length ? h('div', { class: 'list' }, S.recent.map(recentItem)) : h('p', { class: 'muted' }, 'No saved scans yet.'));
}

/* ------------------------------------------------------------------ picker */
function renderPicker(root) {
  const pk = S.picker;
  root.append(h('h1', null, 'More than one project found'), h('p', { class: 'muted' }, 'Pick the ones you want to scan. Backups are unticked by default.'),
    h('div', { class: 'card checks' }, pk.items.map((it) => h('label', null,
      h('input', { type: 'checkbox', checked: it.on, disabled: !it.info.readable, onchange: (e) => { it.on = e.target.checked; } }),
      h('span', null, it.info.name), h('span', { class: 'muted small' }, ' ' + (it.info.daw_name || it.info.format) + (it.info.is_backup ? ' (backup)' : '') + (it.info.readable ? '' : ' (can\'t be read yet)') + (it.info.from_archive ? ' from ' + basename(it.info.from_archive) : ''))))),
    pk.failures.length ? h('p', { class: 'muted' }, plural(pk.failures.length, 'dropped item', 'dropped items') + ' had no projects.') : null,
    h('div', { class: 'row' }, btn('Scan selected', () => {
      const chosen = pk.items.filter((i) => i.on);
      if (!chosen.length) return toast('Tick at least one project.');
      const reports = chosen.filter((i) => i.info.is_report);
      if (reports.length === 1 && chosen.length === 1) return openReportFile(reports[0].path);
      startQueue(chosen.filter((i) => !i.info.is_report));
    }, 'primary'), btn('Cancel', () => goto('home'))));
}

/* ------------------------------------------------------------------ scanning */
const STEPS = [['detect', 'Detecting'], ['read', 'Reading project'], ['build', 'Matching plugins and building report']];
function renderScanning(root) {
  const main = root || $('#main'); main.textContent = '';
  const sc = S.scan;
  if (!sc) return goto('home');
  const cur = STEPS.findIndex((s) => s[0] === sc.stage);
  main.append(h('h1', null, 'Scanning ' + (sc.name || 'project')),
    sc.queue.length > 1 ? h('p', { class: 'muted' }, 'Project ' + Math.min(sc.index + 1, sc.queue.length) + ' of ' + sc.queue.length) : null,
    h('ul', { class: 'stages' }, STEPS.map((s, i) => h('li', { class: i < cur ? 'done' : i === cur ? 'active' : '' }, (i < cur ? '✓ ' : i === cur ? '▸ ' : '   ') + s[1]))),
    (() => { const b = h('div', { class: 'bar' + (sc.percent == null ? ' indeterminate' : '') }, h('div')); if (sc.percent != null) b.firstChild.style.width = Math.round(sc.percent * 100) + '%'; return b; })(),
    h('p', { class: 'muted', 'aria-live': 'polite' }, sc.message || ''),
    btn('Cancel', async () => { if (sc.jobId) { const r = await call('cancel_job', sc.jobId); if (isErr(r)) showError(r.error); } else { S.scan = null; goto('home'); } }));
}

/* ------------------------------------------------------------------ error view */
function renderErrorView(root) {
  const f = friendly(S.errorView || {});
  root.append(h('div', { class: 'card errcard' }, h('h1', null, f.title),
    f.body ? h('p', null, f.body) : null, f.hint ? h('p', null, f.hint) : null,
    f.steps ? h('ol', { class: 'steps' }, f.steps.map((s) => h('li', null, s))) : null),
  h('div', { class: 'row' }, btn('Back to Home', () => goto('home'), 'primary'), btn('Browse files', browse)));
}

/* ------------------------------------------------------------------ report */
function trackName(r, id) { const t = (r.tracks || []).find((x) => x.id === id); return t ? t.name : id; }
function pluginGroups(c) {
  const r = c.report; const by = {};
  for (const p of r.plugins) { const k = (c.plugin_keys || {})[p.id] || p.id; (by[k] = by[k] || []).push(p); }
  return (r.plugin_summary || []).map((s) => ({ s, members: by[s.key] || [], first: (by[s.key] || [])[0] || null }));
}
function pluginIsInstrument(g) {
  return g.members.some((m) => m.role === 'instrument') || (g.first && g.first.kb && /^instrument/.test(g.first.kb.category || ''));
}
function isHeuristic(p) { return (p.flags || []).includes('heuristic') || p.confidence === 'heuristic'; }
function heurMark(p) {
  return isHeuristic(p) ? h('span', { class: 'hmark', title: 'Heuristic result: this came from string scanning or weak matching (' + (p.confidence || 'unknown') + ' confidence) and may be wrong.', 'aria-label': 'Heuristic result' }, 'H') : null;
}
function groupLinkInfo(g) {
  const hp = g.first && g.first.links && g.first.links.homepage;
  return hp && hp.url ? hp : null;
}
function linkButton(link, label) {
  if (!link || !link.url) return h('span', { class: 'na' }, '—');
  const lbl = link.source === 'search' ? 'Search for it' : (label || 'Homepage');
  return h('button', { type: 'button', class: 'btn small', title: (LINK_SRC[link.source] || 'Link') + '\n' + link.url, 'aria-label': lbl + ' (opens in your browser)', onclick: (e) => { e.stopPropagation(); openUrl(link.url); } },
    (LINK_ICON[link.source] || '↗') + ' ' + lbl);
}

function verdictSentence(r) {
  const s = r.summary; const sr = s.send_ready || {};
  if (s.missing_plugins > 0) return plural(s.missing_plugins, 'plugin is missing.', 'plugins are missing.').replace(/^(\d+) plugin is/, '$1 plugin is');
  if (s.opens_on && s.opens_on.windows === false) return 'This project needs a Mac.';
  if (s.opens_on && s.opens_on.mac === false) return 'This project needs Windows.';
  if (sr.score === 'green') return 'Opens fine on this computer.';
  const reason = (sr.reasons || [])[0];
  return reason ? cap(reason) + '.' : 'Check the warnings below.';
}
function summaryText(c) {
  const r = c.report; const s = r.summary;
  const lines = [r.project.name + ' (' + (r.source.daw_name || r.source.format) + (r.source.daw_version ? ' ' + r.source.daw_version : '') + ')', verdictSentence(r),
    'Plugins: ' + s.unique_plugins + ' unique, ' + s.plugin_instances + ' instances, ' + s.missing_plugins + ' missing'];
  (r.warnings || []).forEach((w) => lines.push('[' + w.severity + '] ' + w.message));
  pluginGroups(c).forEach((g) => lines.push('- ' + g.s.name + (g.s.vendor ? ' (' + g.s.vendor + ')' : '') + ' x' + g.s.instances + ' [' + statusOf(g.s.resolution_state).text + ']'));
  return lines.join('\n');
}

function renderReport(root) {
  const c = S.cur; if (!c) return goto('home');
  const r = c.report; const s = r.summary; const sr = s.send_ready || {};
  const score = ['green', 'yellow', 'red'].includes(sr.score) ? sr.score : 'yellow';
  const icon = { green: '✓', yellow: '!', red: '✕' }[score];
  const word = { green: 'Ready', yellow: 'Check', red: 'Problems' }[score];

  // A. header
  const exportWrap = h('div', { class: 'relwrap' });
  const exportBtn = btn('Export ▾', () => toggleExportMenu(exportWrap, c), '', { 'data-popper': '1', id: 'export-btn', 'aria-haspopup': 'menu' });
  exportWrap.append(exportBtn);
  const moreWrap = h('div', { class: 'relwrap' });
  moreWrap.append(btn('⋯', () => toggleMore(moreWrap, c), '', { 'data-popper': '1', 'aria-label': 'More actions', 'aria-haspopup': 'menu' }));
  const srcPath = c.source_path || r.source.path;
  const header = h('div', { class: 'row spread' },
    h('div', null, h('h1', null, r.project.name || basename(r.source.path)),
      h('div', { class: 'muted' }, (r.source.daw_name || r.source.format) + (r.source.daw_version ? ' ' + r.source.daw_version : '') + ' · scanned ' + fmtDate(r.generated_at)),
      h('div', { class: 'small' }, srcPath ? linkBtn(srcPath, () => reveal(srcPath), { title: 'Show in file manager', class: 'link mono' }) : null)),
    h('div', { class: 'row' }, exportWrap, c.imported ? null : btn('Rescan', () => rescan(false)), moreWrap));

  const banners = [];
  if (c.batch) {
    banners.push(h('div', { class: 'banner info' }, h('span', null, 'This scan included ' + c.batch.length + ' projects.'),
      h('label', null, 'Show: ', h('select', { 'aria-label': 'Switch project', onchange: (e) => openReport(e.target.value) },
        c.batch.map((id, i) => h('option', { value: id, selected: id === c.report_id }, 'Project ' + (i + 1) + (id === c.report_id ? ' (this one)' : '')))))));
  }
  (c.batchErrors || []).forEach((er) => banners.push(h('div', { class: 'banner error' }, friendly(er).title)));
  if (c.stale) banners.push(h('div', { class: 'banner warning' }, h('span', null, 'The project file has changed since this scan.'), btn('Rescan', () => rescan(false))));
  if (c.imported) banners.push(h('div', { class: 'banner info' }, 'You\'re viewing a saved report. Installed status is from the computer that made it. Its links are untrusted until you click them, and links open in your browser.'));
  else if (!(r.machine && r.machine.inventory_scanned_at)) {
    banners.push(h('div', { class: 'banner warning' }, h('span', null, 'Scan your plugins to see what\'s installed.'),
      btn('Scan my plugins', () => startInventory(null), 'small', { disabled: !!S.invProgress })));
  }

  // B. verdict
  const opens = s.opens_on || {};
  const oo = (label, v) => h('span', null, label + ' ' + (v === false ? '✕' : '✓'), h('span', { class: 'sr' }, v === false ? ' (no)' : ' (yes)'));
  const tracksTotal = Object.values(s.track_counts || {}).reduce((a, b) => a + b, 0);
  const tile = (n, l) => h('div', { class: 'tile' }, h('div', { class: 'n' }, n), h('div', { class: 'l' }, l));
  const verdict = h('div', { class: 'card verdict ' + score },
    h('div', { class: 'badge', 'aria-hidden': 'true' }, icon),
    h('div', null, h('div', { class: 'sr' }, 'Send-ready: ' + word),
      h('div', { class: 'sentence' }, verdictSentence(r)),
      h('div', { class: 'opens muted' }, 'Opens on: ', oo('Windows', opens.windows), oo('Mac', opens.mac)),
      (sr.reasons || []).length ? h('div', { class: 'muted small' }, 'Because: ' + sr.reasons.join('; ')) : null),
    h('div', { class: 'tiles' }, tile(s.unique_plugins + ' / ' + s.plugin_instances, 'Plugins (unique / instances)'),
      tile(s.missing_plugins, 'Missing plugins'), tile(tracksTotal, 'Tracks'), tile(s.media_files, 'Media files'), tile(s.missing_media, 'Missing media')));

  // C. warnings
  const order = { error: 0, warning: 1, info: 2 };
  const warns = (r.warnings || []).slice().sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3));
  const shown = S.warnAll ? warns : warns.slice(0, 5);
  const wbox = warns.length ? h('div', { class: 'card' }, h('h2', { style: null }, 'Warnings'),
    shown.map((w) => {
      const ids = w.related_ids || [];
      const kind = ids.length && ids.every((x) => /^p/.test(x)) ? 'plugins' : ids.length && ids.every((x) => /^m/.test(x)) ? 'media' : null;
      return h('div', { class: 'warn' }, h('span', { class: 'sev ' + w.severity }, w.severity),
        h('span', null, w.message + (ids.length > 1 ? ' (' + ids.length + ')' : '')),
        kind ? linkBtn('Show', () => { S.idFilter = { ids, label: w.message }; S.tab = kind; render(); }) : null);
    }),
    warns.length > 5 ? linkBtn(S.warnAll ? 'Show fewer' : 'Show all ' + warns.length, () => { S.warnAll = !S.warnAll; render(); }) : null) : null;

  // D. tabs
  const tabs = [['plugins', 'Plugins'], ['tracks', 'Tracks'], ['media', 'Media'], ['project', 'Project']];
  if ((r.special_content || []).length) tabs.push(['special', 'Special']);
  tabs.push(['raw', 'Raw']);
  if (!tabs.some((t) => t[0] === S.tab)) S.tab = 'plugins';
  const tabbar = h('div', { class: 'tabs', role: 'tablist' }, tabs.map(([k, label]) =>
    h('button', { type: 'button', role: 'tab', class: 'tab' + (S.tab === k ? ' active' : ''), 'aria-selected': S.tab === k, onclick: () => { S.tab = k; closePanel(); render(); } }, label)));
  const body = h('div', { id: 'tabbody' });
  root.append(header, ...banners, verdict, wbox, tabbar, body);
  ({ plugins: tabPlugins, tracks: tabTracks, media: tabMedia, project: tabProject, special: tabSpecial, raw: tabRaw }[S.tab])(body, c);
}

function filterNote(then) {
  if (!S.idFilter) return null;
  return h('div', { class: 'banner info' }, h('span', null, 'Filtered: ' + S.idFilter.label), linkBtn('Clear filter', () => { S.idFilter = null; then(); }));
}

/* ---- export */
function toggleExportMenu(wrap, c) {
  if (wrap.querySelector('.popmenu')) return closeMenus();
  closeMenus();
  const items = [['json', 'Full report (JSON)'], ['csv_full', 'Full report (CSV)'], ['csv_plugins', 'Plugin list (CSV)'], ['csv_missing', 'Missing plugins only (CSV)']];
  const redact = h('input', { type: 'checkbox', checked: !!S.settings.redact_paths, onchange: async (e) => { await saveSetting({ redact_paths: e.target.checked }); } });
  wrap.append(h('div', { class: 'popmenu', role: 'menu' }, items.map(([k, label]) => h('button', { type: 'button', role: 'menuitem', onclick: () => { closeMenus(); doExport(c, k); } }, label)),
    h('label', { class: 'small', style: null }, redact, ' Redact file paths')));
}
async function doExport(c, format) {
  const pick = await call('choose_export_path', c.report_id, format);
  if (isErr(pick)) return showError(pick.error);
  if (pick.cancelled) return;
  const res = await call('export_report', c.report_id, format, pick.path, { redact_paths: !!S.settings.redact_paths, csv_delimiter: S.settings.csv_delimiter || ',' });
  if (isErr(res)) return showError(res.error);
  toast('Saved to ' + dirname(res.path), { label: 'Show in folder', run: () => reveal(res.path) });
}
function toggleMore(wrap, c) {
  if (wrap.querySelector('.popmenu')) return closeMenus();
  closeMenus();
  const folder = c.source_path ? dirname(c.source_path) : (c.report.project.folder || {}).path;
  wrap.append(h('div', { class: 'popmenu', role: 'menu' },
    folder && !c.imported ? h('button', { type: 'button', role: 'menuitem', onclick: () => { closeMenus(); reveal(c.source_path || folder); } }, 'Open project folder') : null,
    h('button', { type: 'button', role: 'menuitem', onclick: () => { closeMenus(); copyText(summaryText(c)); } }, 'Copy summary as text')));
}

/* ---- plugins tab */
const P_FILTERS = [['all', 'All'], ['missing', 'Missing'], ['instrument', 'Instruments'], ['effect', 'Effects'], ['ilok', 'iLok'], ['free', 'Free'], ['stock', 'Stock'], ['heuristic', 'Heuristic']];
function groupMatchesFilter(g) {
  const ms = g.members.length ? g.members : [];
  switch (S.pFilter) {
    case 'missing': return g.s.resolution_state === 'not_installed';
    case 'instrument': return pluginIsInstrument(g);
    case 'effect': return g.s.resolution_state !== 'stock' && !pluginIsInstrument(g);
    case 'ilok': return ms.some((m) => (m.flags || []).includes('ilok') || ((m.kb || {}).licensing || []).includes('ilok'));
    case 'free': return ms.some((m) => (m.kb || {}).price_model === 'free');
    case 'stock': return g.s.resolution_state === 'stock';
    case 'heuristic': return ms.some(isHeuristic);
    default: return true;
  }
}
function pluginRowsData(c) {
  const r = c.report; const q = S.pSearch.trim().toLowerCase();
  const idset = S.idFilter ? new Set(S.idFilter.ids) : null;
  let groups = pluginGroups(c).filter((g) => groupMatchesFilter(g) && (!idset || g.members.some((m) => idset.has(m.id)))
    && (!q || (g.s.name || '').toLowerCase().includes(q) || (g.s.vendor || '').toLowerCase().includes(q)));
  const keyFn = {
    status: (g) => statusOf(g.s.resolution_state).rank * 1e6 - g.s.instances, name: (g) => (g.s.name || '').toLowerCase(), vendor: (g) => (g.s.vendor || '').toLowerCase(),
    format: (g) => g.members.map((m) => m.format).sort().join(','), instances: (g) => g.s.instances,
    tracks: (g) => g.s.track_ids.length, licensing: (g) => (((g.first || {}).kb || {}).licensing || []).join(','),
  }[S.pSort.key] || (() => 0);
  groups.sort((a, b) => { const x = keyFn(a), y = keyFn(b); return (x < y ? -1 : x > y ? 1 : 0) * S.pSort.dir; });
  return { groups, r, idset };
}
function tabPlugins(body, c) {
  const search = h('input', { type: 'search', id: 'search-box', placeholder: 'Search name or vendor', 'aria-label': 'Search plugins', value: S.pSearch, oninput: (e) => { S.pSearch = e.target.value; fillRows(); } });
  const chipsBox = h('div', { class: 'chips', role: 'group', 'aria-label': 'Filter' });
  const tableBox = h('div');
  const drawChips = () => { chipsBox.textContent = ''; P_FILTERS.forEach(([k, l]) => chipsBox.append(h('button', { type: 'button', class: 'chip' + (S.pFilter === k ? ' on' : ''), 'aria-pressed': S.pFilter === k, onclick: () => { S.pFilter = k; drawChips(); fillRows(); } }, l))); };
  const groupSel = h('select', { 'aria-label': 'Group by', onchange: (e) => { S.pGroup = e.target.value; fillRows(); } },
    [['none', 'No grouping'], ['vendor', 'Group by vendor'], ['track', 'Group by track'], ['format', 'Group by format']].map(([v, l]) => h('option', { value: v, selected: S.pGroup === v }, l)));
  const viewBtn = btn(S.pView === 'unique' ? 'Show per instance' : 'Show unique plugins', () => { S.pView = S.pView === 'unique' ? 'instance' : 'unique'; render(); });
  const fillRows = () => { tableBox.textContent = ''; tableBox.append(S.pView === 'unique' ? uniqueTable(c) : instanceTable(c)); };
  drawChips(); fillRows();
  body.append(filterNote(() => render()), h('div', { class: 'toolbar' }, search, groupSel, viewBtn), chipsBox, tableBox);
}
function sortHeader(key, label) {
  const on = S.pSort.key === key;
  return h('th', { 'aria-sort': on ? (S.pSort.dir === 1 ? 'ascending' : 'descending') : 'none' },
    h('button', { type: 'button', onclick: () => { S.pSort = { key, dir: on ? -S.pSort.dir : 1 }; render(); } }, label + (on ? (S.pSort.dir === 1 ? ' ▲' : ' ▼') : '')));
}
function statusCell(state, p) {
  const st = statusOf(state);
  return h('span', { class: 'status ' + st.cls }, st.icon + ' ' + st.text, p ? heurMark(p) : null);
}
function fmtBadges(ms) { return [...new Set(ms.map((m) => m.format))].map((f) => h('span', { class: 'fmt' }, f)); }
function licBadges(g) { return (((g.first || {}).kb || {}).licensing || []).map((l) => h('span', { class: 'badge2' }, l === 'ilok' ? 'iLok' : l.replace(/_/g, ' '))); }

function uniqueTable(c) {
  const { groups, r } = pluginRowsData(c);
  if (!groups.length) return h('p', { class: 'muted' }, r.plugins.length ? 'No plugins match this filter.' : 'No plugins were found in this project.');
  const groupOf = (g) => S.pGroup === 'vendor' ? (g.s.vendor || 'Unknown vendor') : S.pGroup === 'format' ? [...new Set(g.members.map((m) => m.format))].join(', ') || 'unknown' : S.pGroup === 'track' ? (g.s.track_ids.length ? trackName(r, g.s.track_ids[0]) : 'No track') : null;
  const rows = []; let last = null;
  const ordered = S.pGroup === 'none' ? groups : groups.slice().sort((a, b) => String(groupOf(a)).localeCompare(String(groupOf(b))));
  for (const g of ordered) {
    const gk = groupOf(g);
    if (gk !== last && gk !== null) { rows.push(h('tr', { class: 'grouprow' }, h('td', { colspan: 8 }, gk))); last = gk; }
    const tn = g.s.track_ids.map((t) => trackName(r, t));
    const rowText = () => [g.s.name, g.s.vendor, statusOf(g.s.resolution_state).text, g.s.instances + ' instances'].filter(Boolean).join(' | ');
    const open = () => openPluginPanel(c, g);
    rows.push(h('tr', { class: 'click' + (g.s.resolution_state === 'not_installed' ? ' missing' : ''), tabindex: '0', onclick: open, onkeydown: (e) => { if (e.key === 'Enter') open(); },
      oncontextmenu: (e) => contextMenu(e, [['Copy name', () => copyText(g.s.name)], groupLinkInfo(g) ? ['Copy link', () => copyText(groupLinkInfo(g).url)] : null, ['Copy row as text', () => copyText(rowText())]].filter(Boolean)) },
    h('td', null, statusCell(g.s.resolution_state, g.first)), h('td', null, h('b', null, g.s.name)), h('td', null, g.s.vendor || h('span', { class: 'na' }, '—')),
    h('td', null, fmtBadges(g.members)), h('td', null, g.s.instances + (g.s.bypassed_instances ? ' (' + g.s.bypassed_instances + ' bypassed)' : '')),
    h('td', null, tn.slice(0, 3).join(', ') + (tn.length > 3 ? ' +' + (tn.length - 3) : '')), h('td', null, licBadges(g)), h('td', null, linkButton(groupLinkInfo(g)))));
  }
  return h('div', { class: 'tablewrap' }, h('table', null, h('thead', null, h('tr', null,
    sortHeader('status', 'Status'), sortHeader('name', 'Plugin'), sortHeader('vendor', 'Vendor'), sortHeader('format', 'Format'), sortHeader('instances', 'Instances'),
    sortHeader('tracks', 'Tracks'), sortHeader('licensing', 'Licensing'), h('th', null, 'Link'))), h('tbody', null, rows)));
}
function instanceTable(c) {
  const { groups, r } = pluginRowsData(c);
  const rows = [];
  groups.forEach((g) => g.members.forEach((m) => {
    rows.push(h('tr', { class: 'click' + (m.resolution.state === 'not_installed' ? ' missing' : ''), tabindex: '0', onclick: () => openPluginPanel(c, g), onkeydown: (e) => { if (e.key === 'Enter') openPluginPanel(c, g); } },
      h('td', null, statusCell(m.resolution.state, m)), h('td', null, h('b', null, m.name)), h('td', null, m.vendor || h('span', { class: 'na' }, '—')), h('td', null, h('span', { class: 'fmt' }, m.format)),
      h('td', null, trackName(r, m.track_id)), h('td', null, m.slot_index === null || m.slot_index === undefined ? '' : String(m.slot_index + 1)), h('td', null, m.bypassed ? 'Bypassed' : 'Active')));
  }));
  if (!rows.length) return h('p', { class: 'muted' }, 'No plugin instances match this filter.');
  return h('div', { class: 'tablewrap' }, h('table', null, h('thead', null, h('tr', null, ['Status', 'Plugin', 'Vendor', 'Format', 'Track', 'Slot', 'State'].map((t) => h('th', null, t)))), h('tbody', null, rows)));
}

/* ---- tracks tab */
function tabTracks(body, c) {
  const r = c.report; const tracks = r.tracks || [];
  if (!tracks.length) return body.append(h('p', { class: 'muted' }, 'No tracks were found.'));
  const kids = {}; tracks.forEach((t) => { (kids[t.parent_id || ''] = kids[t.parent_id || ''] || []).push(t); });
  const byId = {}; (r.plugins || []).forEach((p) => { byId[p.id] = p; });
  const rows = []; const seen = new Set();
  const walk = (parent, depth) => (kids[parent] || []).forEach((t) => {
    if (seen.has(t.id)) return; seen.add(t.id);
    const chain = (t.device_ids || []).map((id) => byId[id]).filter(Boolean);
    rows.push(h('tr', { class: 'click', tabindex: '0', onclick: () => openTrackPanel(c, t), onkeydown: (e) => { if (e.key === 'Enter') openTrackPanel(c, t); } },
      h('td', null, h('span', { style: null }, '  '.repeat(depth)), h('b', null, t.name)), h('td', null, t.type),
      h('td', null, t.color ? swatch(t.color) : h('span', { class: 'na' }, '—')),
      h('td', null, [t.muted ? h('span', { class: 'badge2' }, 'Muted') : null, t.solo ? h('span', { class: 'badge2' }, 'Solo') : null, t.frozen ? h('span', { class: 'badge2' }, 'Frozen') : null, t.armed ? h('span', { class: 'badge2' }, 'Armed') : null]),
      h('td', null, h('div', { class: 'chain' }, chain.map((p) => h('span', { class: 'chip', title: statusOf(p.resolution.state).text }, statusOf(p.resolution.state).icon + ' ' + p.name)))),
      h('td', null, [(t.sends || []).length ? 'Sends: ' + t.sends.length : '', (t.sidechain_sources || []).length ? ' Sidechain' : ''].join(''))));
    walk(t.id, depth + 1);
  });
  walk('', 0);
  tracks.forEach((t) => { if (!seen.has(t.id)) { seen.add(t.id); walk(t.id, 0); } });
  body.append(h('div', { class: 'tablewrap' }, h('table', null, h('thead', null, h('tr', null, ['Track', 'Type', 'Colour', 'State', 'Plugin chain', 'Routing'].map((t) => h('th', null, t)))), h('tbody', null, rows))));
}
function swatch(color) { const s = h('span', { class: 'badge2', title: String(color) }, String(color)); if (/^#[0-9a-fA-F]{3,8}$/.test(String(color))) s.style.borderLeft = '10px solid ' + color; return s; }

/* ---- media tab */
function tabMedia(body, c) {
  const r = c.report; const pr = r.project || {};
  let media = r.media || [];
  if (S.idFilter) { const ids = new Set(S.idFilter.ids); media = media.filter((m) => ids.has(m.id)); }
  const status = (m) => (m.exists === false ? ['✕ Missing', 'missing'] : m.inside_project_folder === false ? ['! Outside project folder', 'other'] : m.exists === null ? ['? Unknown', 'unknown'] : ['✓ OK', 'ok']);
  const rows = media.map((m) => {
    const st = status(m); const a = m.audio || {};
    return h('tr', { class: m.exists === false ? 'missing' : '' }, h('td', { title: m.path }, h('b', null, basename(m.path))), h('td', null, h('span', { class: 'status ' + st[1] }, st[0])),
      h('td', null, a.format || (m.path.includes('.') ? m.path.split('.').pop() : '')),
      h('td', null, a.sample_rate ? [a.sample_rate + ' Hz', m.sample_rate_mismatch ? h('span', { class: 'hmark', title: 'Different from the project sample rate' + (pr.sample_rate ? ' (' + pr.sample_rate + ' Hz)' : '') }, 'MISMATCH') : null] : ''),
      h('td', null, fmtDur(a.duration_seconds)), h('td', null, fmtBytes(m.size_bytes)), h('td', null, m.source_hint ? fmtVal(m.source_hint) : ''), h('td', null, m.duplicate_of ? 'Duplicate of ' + m.duplicate_of : ''));
  });
  const unused = r.unused_media || []; const usedTotal = unused.reduce((a, u) => a + (u.size_bytes || 0), 0);
  body.append(filterNote(() => render()), media.length ? h('div', { class: 'tablewrap' }, h('table', null, h('thead', null, h('tr', null, ['File', 'Status', 'Format', 'Sample rate', 'Duration', 'Size', 'Source hint', 'Notes'].map((t) => h('th', null, t)))), h('tbody', null, rows))) : h('p', { class: 'muted' }, 'No media files are referenced by this project.'),
    h('h2', null, 'Unused files in project folder'),
    unused.length ? h('div', null, h('p', { class: 'muted' }, plural(unused.length, 'file', 'files') + ', ' + fmtBytes(usedTotal) + ' total'),
      h('div', { class: 'tablewrap' }, h('table', null, h('thead', null, h('tr', null, h('th', null, 'File'), h('th', null, 'Size'))), h('tbody', null, unused.map((u) => h('tr', null, h('td', { title: u.path }, basename(u.path)), h('td', null, fmtBytes(u.size_bytes)))))))) : h('p', { class: 'muted' }, pr.folder && pr.folder.file_count !== null ? 'None found.' : 'Not checked for this project location.'));
}

/* ---- project tab */
function tabProject(body, c) {
  const r = c.report; const p = r.project; const un = new Set(p.unavailable_fields || []); const src = r.source; const f = p.folder || {}; const mc = r.machine || {};
  const row = (label, v, key) => [h('dt', null, label), h('dd', null, (v === null || v === undefined || v === '' || (Array.isArray(v) && !v.length)) && key && un.has(key) ? h('span', { class: 'na' }, 'Not stored in this format') : fmtVal(v))];
  const tempos = (p.tempo_changes || []).map((t) => t.bpm + ' BPM at beat ' + t.position_beats).join('; ');
  const sigs = (p.time_signatures || []).map((t) => JSON.stringify(t)).join('; ');
  const markers = (p.markers || []).map((m) => (m.name || '') + (m.position_beats !== undefined ? ' @' + m.position_beats : '')).join('; ');
  const loop = p.loop && (p.loop.start_beats !== null || p.loop.end_beats !== null) ? p.loop.start_beats + ' to ' + p.loop.end_beats + ' beats' : null;
  body.append(h('h3', null, 'Project'), h('dl', { class: 'kv' },
    row('Name', p.name), row('Title', p.title, 'title'), row('Artist', p.artist, 'artist'), row('Genre', p.genre, 'genre'), row('Comments', p.comments, 'comments'),
    row('Tempo', p.tempo_bpm === null ? null : p.tempo_bpm + ' BPM', 'tempo_bpm'), row('Tempo changes', tempos, 'tempo_changes_after_start'),
    row('Time signatures', sigs, 'time_signature_changes_after_start'), row('Key', p.key, 'key'), row('Sample rate', p.sample_rate ? p.sample_rate + ' Hz' : null, 'sample_rate'),
    row('Bit depth', p.bit_depth, 'bit_depth'), row('Length', p.length_seconds === null ? null : fmtDur(p.length_seconds) + (p.length_bars ? ' (' + p.length_bars + ' bars)' : ''), 'length_seconds'),
    row('Markers', markers, 'markers'), row('Loop', loop, 'loop'), row('Alternatives', (p.alternatives || []).map((a) => JSON.stringify(a)).join('; '), 'alternatives')),
  h('h3', null, 'Project folder'), h('dl', { class: 'kv' }, row('Folder', f.path), row('Total size', f.total_size_bytes === null || f.total_size_bytes === undefined ? null : fmtBytes(f.total_size_bytes)),
    row('Files', f.file_count), row('Backups found', f.backup_count), row('Newest backup', f.newest_backup_at ? fmtDate(f.newest_backup_at) : null)),
  h('h3', null, 'File'), h('dl', { class: 'kv' }, row('Path', src.path), row('File size', src.file_size_bytes === null ? null : fmtBytes(src.file_size_bytes)), row('Created', src.created_at ? fmtDate(src.created_at) : null),
    row('Modified', src.modified_at ? fmtDate(src.modified_at) : null), row('Format', src.format), row('Detection', src.detection_confidence ? src.detection_confidence + ': ' + (src.detection_reason || '') : null),
    row('DAW', src.daw_name), row('DAW version', src.daw_version), row('Reader version', src.reader_version)),
  h('h3', null, 'This scan'), h('dl', { class: 'kv' }, row('Report format version', r.schema_version), row('Generated', fmtDate(r.generated_at)), row('App', r.app && r.app.name + ' ' + r.app.version),
    row('Knowledge base', r.app && r.app.kb_version), row('Computer', mc.os ? mc.os + ' (' + (mc.arch || '') + ')' : null), row('Plugins last scanned', mc.inventory_scanned_at ? fmtDate(mc.inventory_scanned_at) : null)),
  un.size ? h('p', { class: 'muted small' }, 'Fields shown as "Not stored in this format" can\'t be read from this kind of project.') : null);
}

/* ---- special + raw */
function tabSpecial(body, c) {
  body.append(...(c.report.special_content || []).map((s) => h('div', { class: 'card' }, h('b', null, (s.type || 'item').replace(/_/g, ' ') + (s.name ? ': ' + s.name : '')),
    h('dl', { class: 'kv' }, Object.entries(s).filter(([k]) => k !== 'type' && k !== 'name').map(([k, v]) => [h('dt', null, k.replace(/_/g, ' ')), h('dd', null, k === 'track_id' ? trackName(c.report, v) : fmtVal(v))])))));
}
function tabRaw(body, c) {
  const text = JSON.stringify(c.report, null, 2);
  body.append(h('div', { class: 'toolbar' }, btn('Copy JSON', () => copyText(text)), h('span', { class: 'muted small' }, 'The complete report, including every field shown elsewhere.')), h('pre', { class: 'pre', tabindex: '0' }, text));
}

/* ------------------------------------------------------------------ side panels */
function closePanel() { const p = $('#panel'); p.hidden = true; p.textContent = ''; }
function openPanel(...kids) {
  const p = $('#panel'); p.textContent = '';
  p.append(h('button', { type: 'button', class: 'btn small close', 'aria-label': 'Close details', onclick: closePanel }, '✕'), ...kids);
  p.hidden = false; const first = p.querySelector('h1'); if (first) { first.setAttribute('tabindex', '-1'); first.focus(); }
}
const dl = (pairs) => h('dl', { class: 'kv' }, pairs.filter(Boolean).map(([k, v]) => [h('dt', null, k), h('dd', null, v)]));

function openPluginPanel(c, g) {
  const r = c.report; const p = g.first || {}; const kb = p.kb; const res = p.resolution || {}; const inst = res.installed;
  const stateTxt = (() => {
    const s = g.s.resolution_state;
    if (s === 'installed_same_format') return 'Installed (' + String(p.format || '').toUpperCase() + (inst && inst.version ? ', version ' + inst.version : '') + ')';
    if (s === 'installed_other_format') return 'Installed as ' + (res.other_formats_installed || []).map((x) => x.toUpperCase()).join('/') + ', but the project uses ' + String(p.format || '').toUpperCase();
    return statusOf(s).text;
  })();
  const links = p.links || {};
  const linkRow = (label, l) => (l && l.url ? h('div', { class: 'row' }, linkButton(l, label), h('span', { class: 'muted small' }, LINK_SRC[l.source] || '')) : null);
  const inTracks = g.members.map((m) => h('li', null, trackName(r, m.track_id) + ', slot ' + (m.slot_index === null || m.slot_index === undefined ? '?' : m.slot_index + 1) + ' (' + m.format + ')' + (m.bypassed ? ' [bypassed]' : '') + (m.preset_name ? ', preset "' + m.preset_name + '"' : '') + (m.automated ? ', automated' : '') + (m.version_in_project ? ', saved with version ' + m.version_in_project : '')));
  const idn = p.identity || {};
  const idPairs = Object.entries(idn).filter(([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && !v.length)).map(([k, v]) => [k.replace(/_/g, ' '), h('span', { class: 'mono' }, isObj(v) ? JSON.stringify(v) : String(v))]);
  const kbFree = (kb && kb.free_alternatives) || [];
  openPanel(h('h1', null, g.s.name), h('div', { class: 'muted' }, [g.s.vendor || 'Unknown vendor', kb && kb.category ? ' · ' + kb.category : ''].join('')),
    h('div', { class: 'row' }, fmtBadges(g.members), heurMark(p)), h('p', null, statusCell(g.s.resolution_state), ' ', h('span', null, stateTxt)),
    (p.flags || []).length ? h('div', { class: 'chips' }, p.flags.map((f) => h('span', { class: 'chip' }, f.replace(/_/g, ' ')))) : null,
    h('h3', null, 'Links'), linkRow('Homepage', links.homepage) || h('p', { class: 'muted' }, 'No links known.'), linkRow('Manual', links.manual), linkRow('Support', links.support),
    h('h3', null, 'Used in this project'), h('ul', null, inTracks),
    h('h3', null, 'Your system'), inst ? dl([['Installed version', inst.version || '—'], ['Path', h('span', { class: 'mono' }, inst.path)], ['Architecture', inst.arch || '—'], ['Other formats installed', (res.other_formats_installed || []).join(', ') || 'None'], ['Matched by', (res.matched_by || '—') + (res.confidence ? ' (' + res.confidence + ')' : '')]]) : h('p', { class: 'muted' }, g.s.resolution_state === 'inventory_unavailable' ? 'Installed plugins haven\'t been checked yet.' : 'Not found on this computer.'),
    inst && inst.path && !c.imported ? btn('Show in folder', () => reveal(inst.path), 'small') : null,
    (r.warnings || []).filter((w) => (w.related_ids || []).some((id) => g.members.some((m) => m.id === id))).map((w) => h('div', { class: 'banner ' + (w.severity === 'error' ? 'error' : w.severity === 'warning' ? 'warning' : 'info') }, w.message)),
    h('h3', null, 'About this plugin'),
    kb ? [dl([['Licensing', (kb.licensing || []).join(', ') || '—'], ['Price model', kb.price_model || '—'], ['Platforms', (kb.platforms || []).join(', ') || '—'], ['Available formats', (kb.formats_available || []).join(', ') || '—'],
      ['Apple Silicon', kb.apple_silicon_native === null || kb.apple_silicon_native === undefined ? 'Unknown' : kb.apple_silicon_native ? 'Yes' : 'No'], ['Status', kb.status || '—'],
      ['Info last verified', kb.last_verified || (kb.verified ? '—' : 'Not verified yet')]]),
    !kb.verified ? h('p', { class: 'muted small' }, 'This information is a starting point that hasn\'t been checked against the vendor yet.') : null,
    kbFree.length ? h('div', null, h('b', null, 'Free alternatives: '), kbFree.map((a) => h('button', { type: 'button', class: 'link', style: null, onclick: () => openUrl('https://www.kvraudio.com/plugins/search?q=' + encodeURIComponent(a)) }, a + ' '))) : null] : h('p', { class: 'muted' }, 'We don\'t have information about this plugin yet.'),
    h('h3', null, 'Technical details'), h('details', null, h('summary', null, 'Identity, confidence and match'), dl([...idPairs, ['Confidence', p.confidence || '—'], ['Knowledge base match', kb ? (kb.kb_id + ' via ' + kb.matched_by + ' (' + kb.confidence + ')') : 'None'], ['Reason', res.matched_by || 'No installed match']])));
}
function openTrackPanel(c, t) {
  const r = c.report; const un = new Set((r.project.unavailable_fields || []));
  const val = (k, v, fn) => (v === null || v === undefined || (Array.isArray(v) && !v.length)) && un.has('tracks.' + k) ? h('span', { class: 'na' }, 'Not stored in this format') : (fn ? fn(v) : fmtVal(v));
  const chain = (t.device_ids || []).map((id) => (r.plugins || []).find((p) => p.id === id)).filter(Boolean);
  openPanel(h('h1', null, t.name), h('div', { class: 'muted' }, t.type),
    dl([['Colour', val('color', t.color)], ['Parent group', t.parent_id ? trackName(r, t.parent_id) : (un.has('tracks.parent_id') ? h('span', { class: 'na' }, 'Not stored in this format') : '—')],
      ['Muted', val('muted', t.muted)], ['Solo', val('solo', t.solo)], ['Armed', val('armed', t.armed)], ['Frozen', val('frozen', t.frozen)], ['Volume', val('volume_db', t.volume_db, (v) => v + ' dB')], ['Pan', val('pan', t.pan)]]),
    h('h3', null, 'Plugin chain'), chain.length ? h('div', { class: 'chain' }, chain.map((p) => h('button', { type: 'button', class: 'chip', onclick: () => { const g = pluginGroups(c).find((x) => x.members.some((m) => m.id === p.id)); if (g) openPluginPanel(c, g); } }, statusOf(p.resolution.state).icon + ' ' + p.name))) : h('p', { class: 'muted' }, 'No plugins on this track.'),
    h('h3', null, 'Routing'), dl([['Output', val('output', t.output)], ['Sends', val('sends', (t.sends || []).map((s) => JSON.stringify(s)).join('; '))], ['Sidechain sources', val('sidechain_sources', t.sidechain_sources)]]),
    h('h3', null, 'Content'), dl([['Clips', val('clip_count', t.clip_count)], ['MIDI', val('midi', t.midi)], ['Automated parameters', val('automated_parameters', t.automated_parameters)]]));
}

/* ------------------------------------------------------------------ inventory / installed screen */
async function loadInstalled() { const r = await call('get_inventory'); if (!isErr(r)) { S.inv = r; if (S.view === 'installed') render(); } }
async function startInventory(folders) {
  if (S.invProgress) return;
  const r = await call('start_inventory_scan', folders);
  if (isErr(r)) return showError(r.error);
  S.invProgress = { percent: null, message: 'Starting…', jobId: r.job_id }; render();
}
function onInventoryJob(name, p) {
  if (name === 'job.progress') { S.invProgress = Object.assign(S.invProgress || {}, { percent: p.percent, message: p.message, jobId: p.job_id }); }
  else { S.invProgress = null; if (name === 'job.failed') showError(p.error); if (name === 'job.cancelled') toast('Plugin scan cancelled.'); }
  if (['installed', 'settings', 'firstrun'].includes(S.view)) render(); else renderSideStatus();
}
async function onInventoryUpdated(p) {
  await loadInstalled();
  toast('Found ' + plural(p.count, 'plugin', 'plugins') + ' on this computer.');
  const c = S.cur;
  if (c && !c.imported && S.view === 'report' && !S.scan && (!c.report.machine || c.report.machine.inventory_scanned_at !== p.scanned_at)) rescan(true);
}
function renderInstalled(root) {
  const inv = S.inv || { plugins: [], scanned_at: null }; const f = S.invFilter;
  const head = h('div', { class: 'row spread' }, h('div', null, h('h1', null, 'Installed plugins'), h('div', { class: 'muted' }, inv.scanned_at ? 'Last scanned ' + fmtDate(inv.scanned_at) + ' · ' + plural(inv.plugins.length, 'plugin', 'plugins') : 'Not scanned yet')),
    h('div', { class: 'row' }, S.invProgress ? btn('Cancel scan', async () => { const r = await call('cancel_job', S.invProgress.jobId); if (isErr(r)) showError(r.error); }) : null,
      btn(S.invProgress ? 'Scanning…' : 'Rescan', () => startInventory(null), 'primary', { disabled: !!S.invProgress }), linkBtn('Manage folders', () => { loadFolders(); goto('settings'); })));
  const prog = S.invProgress ? h('div', null, h('div', { class: 'bar' + (S.invProgress.percent == null ? ' indeterminate' : '') }, (() => { const d = h('div'); if (S.invProgress.percent != null) d.style.width = Math.round(S.invProgress.percent * 100) + '%'; return d; })()), h('p', { class: 'muted small' }, S.invProgress.message || '')) : null;
  const norm = (n) => (n || '').toLowerCase().replace(/[^a-z0-9]+/g, '');
  const fmtSets = {}; inv.plugins.forEach((p) => { (fmtSets[norm(p.name)] = fmtSets[norm(p.name)] || new Set()).add(p.format); });
  const formats = [...new Set(inv.plugins.map((p) => p.format))].sort();
  const q = f.search.trim().toLowerCase();
  const rows = inv.plugins.filter((p) => (!f.format || p.format === f.format) && (!q || (p.name || '').toLowerCase().includes(q) || (p.vendor || '').toLowerCase().includes(q))
    && (!f.arch || (f.arch === 'intel' && (p.architectures || []).length && !(p.architectures || []).some((a) => /arm64/.test(a)))) && (!f.dupes || fmtSets[norm(p.name)].size > 1));
  const table = rows.length ? h('div', { class: 'tablewrap' }, h('table', null, h('thead', null, h('tr', null, ['Name', 'Vendor', 'Format', 'Version', 'Architecture', 'Path', 'Homepage'].map((t) => h('th', null, t)))),
    h('tbody', null, rows.map((p) => h('tr', null, h('td', null, h('b', null, p.name)), h('td', null, p.vendor || ''), h('td', null, h('span', { class: 'fmt' }, p.format)), h('td', null, p.version || ''), h('td', null, (p.architectures || []).join('/')),
      h('td', { class: 'mono' }, p.path), h('td', null, /^https?:\/\//.test(p.url || '') ? linkButton({ url: p.url, source: 'moduleinfo' }) : ''))))))
    : h('p', { class: 'muted' }, inv.plugins.length ? 'No plugins match these filters.' : 'No plugins found yet. Press Rescan to look in your plugin folders.');
  root.append(head, prog, h('div', { class: 'toolbar' }, h('input', { type: 'search', id: 'search-box', placeholder: 'Search name or vendor', 'aria-label': 'Search installed plugins', value: f.search, oninput: (e) => { f.search = e.target.value; refillInstalled(); } }),
    h('select', { 'aria-label': 'Format', onchange: (e) => { f.format = e.target.value; render(); } }, h('option', { value: '' }, 'All formats'), formats.map((x) => h('option', { value: x, selected: f.format === x }, x.toUpperCase()))),
    h('select', { 'aria-label': 'Architecture', onchange: (e) => { f.arch = e.target.value; render(); } }, h('option', { value: '' }, 'Any architecture'), h('option', { value: 'intel', selected: f.arch === 'intel' }, 'Intel-only (no Apple Silicon)')),
    h('label', null, h('input', { type: 'checkbox', checked: f.dupes, onchange: (e) => { f.dupes = e.target.checked; render(); } }), ' Installed in several formats')), h('div', { id: 'inst-table' }, table));
}
function refillInstalled() { const main = $('#main'); const y = main.scrollTop; const pos = $('#search-box') && $('#search-box').selectionStart; render(); const sb = $('#search-box'); if (sb) { sb.focus(); if (pos != null) sb.setSelectionRange(pos, pos); } main.scrollTop = y; }

/* ------------------------------------------------------------------ settings + first run */
async function saveSetting(patch) {
  const r = await call('set_settings', patch);
  if (isErr(r)) { showError(r.error); return false; }
  S.settings = r; applyTheme(); return true;
}
function applyTheme() {
  const a = S.settings.appearance;
  if (a === 'light' || a === 'dark') document.documentElement.setAttribute('data-theme', a); else document.documentElement.removeAttribute('data-theme');
}
async function loadFolders() { const r = await call('get_plugin_folders'); if (!isErr(r)) { S.folders = r.folders; if (['settings', 'firstrun'].includes(S.view)) render(); } }
function folderList(withRemove) {
  const s = S.settings;
  return h('div', { class: 'checks' }, S.folders.map((f) => h('label', { title: (f.formats || []).join(', ') },
    h('input', { type: 'checkbox', checked: f.enabled, disabled: !f.exists, onchange: async (e) => {
      const off = new Set(s.plugin_folders_disabled || []);
      if (e.target.checked) off.delete(f.path); else off.add(f.path);
      await saveSetting({ plugin_folders_disabled: [...off] }); loadFolders();
    } }),
    h('span', { class: 'mono' }, f.path), h('span', { class: 'muted small' }, ' ' + (f.exists ? (f.formats.length ? f.formats.join(', ').toUpperCase() : 'custom') : 'not found')),
    withRemove && f.custom ? btn('Remove', async (e) => { e.preventDefault(); await saveSetting({ plugin_folders_extra: (s.plugin_folders_extra || []).filter((x) => x !== f.path) }); loadFolders(); }, 'small') : null)));
}
async function addFolder() {
  const r = await call('choose_folder'); if (isErr(r)) return showError(r.error);
  if (!r.paths) return;
  const extra = [...new Set([...(S.settings.plugin_folders_extra || []), ...r.paths])];
  if (await saveSetting({ plugin_folders_extra: extra })) loadFolders();
}
function renderFirstRun(root) {
  root.append(h('div', { class: 'card' }, h('h1', null, 'Let\'s see what plugins you have.'), h('p', null, 'We\'ll scan your plugin folders once so we can tell you what\'s installed. Nothing leaves your computer.'),
    folderList(true), h('div', { class: 'row' }, btn('Add folder', addFolder)),
    h('div', { class: 'row', style: null }, btn('Scan my plugins', async () => { await saveSetting({ first_run_done: true }); await startInventory(null); goto('home'); }, 'primary'),
      btn('Skip for now', async () => { await saveSetting({ first_run_done: true }); goto('home'); })),
    h('p', { class: 'muted small' }, 'You can drop a project right away; install status fills in when the scan finishes.')));
}
function renderSettings(root) {
  const s = S.settings; const info = S.info || {};
  root.append(h('h1', null, 'Settings'),
    h('div', { class: 'card' }, h('h2', null, 'Plugin folders'), folderList(true), h('div', { class: 'row' }, btn('Add folder', addFolder), btn(S.invProgress ? 'Scanning…' : 'Rescan now', () => startInventory(null), '', { disabled: !!S.invProgress }))),
    h('div', { class: 'card' }, h('h2', null, 'Exports'),
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: !!s.redact_paths, onchange: (e) => saveSetting({ redact_paths: e.target.checked }) }), 'Redact file paths in exports'),
      h('label', { class: 'row' }, 'CSV delimiter ', h('select', { onchange: (e) => saveSetting({ csv_delimiter: e.target.value }) }, h('option', { value: ',', selected: s.csv_delimiter === ',' }, 'Comma (,)'), h('option', { value: ';', selected: s.csv_delimiter === ';' }, 'Semicolon (;), for European Excel'))),
      h('div', { class: 'row' }, h('span', null, 'Default export folder: '), h('span', { class: 'mono' }, s.default_export_dir || 'Ask every time'), btn('Choose…', async () => { const r = await call('choose_folder'); if (isErr(r)) return showError(r.error); if (r.paths && await saveSetting({ default_export_dir: r.paths[0] })) render(); }, 'small'),
        s.default_export_dir ? btn('Clear', async () => { if (await saveSetting({ default_export_dir: null })) render(); }, 'small') : null)),
    h('div', { class: 'card' }, h('h2', null, 'Appearance'), h('select', { 'aria-label': 'Appearance', onchange: (e) => saveSetting({ appearance: e.target.value }) },
      [['system', 'Follow my system'], ['light', 'Light'], ['dark', 'Dark']].map(([v, l]) => h('option', { value: v, selected: s.appearance === v }, l)))),
    h('div', { class: 'card' }, h('h2', null, 'Saved data'), h('p', { class: 'muted' }, 'Recent reports and your plugin list are stored only on this computer.'),
      btn('Clear recent scans', async () => { const r = await call('clear_recent'); if (isErr(r)) return showError(r.error); S.recent = []; toast('Recent scans cleared.'); })),
    h('div', { class: 'card' }, h('h2', null, 'Diagnostics'), h('div', { class: 'row' },
      btn('Open log folder', async () => { const r = await call('get_log_folder'); if (isErr(r)) return showError(r.error); reveal(r.path); }),
      btn('Create support bundle', async () => {
        const pick = await call('choose_bundle_path'); if (isErr(pick)) return showError(pick.error); if (pick.cancelled) return;
        const r = await call('create_support_bundle', pick.path); if (isErr(r)) return showError(r.error);
        toast('Saved to ' + dirname(r.path), { label: 'Show in folder', run: () => reveal(r.path) });
      })), h('p', { class: 'muted small' }, 'A support bundle has logs and version numbers only, never your project files.')),
    h('div', { class: 'card' }, h('h2', null, 'About'), dl([['Rackcheck', info.app_version], ['Engine', info.engine_version], ['Report format', info.schema_version], ['Knowledge base', info.kb_version || 'Bundled seed data (unverified)'], ['Saved data folder', h('span', { class: 'mono' }, info.data_dir || '')]]),
      h('p', { class: 'muted small' }, 'Rackcheck works fully offline. Knowledge base updates aren\'t available in this version.')));
}

/* ------------------------------------------------------------------ keyboard */
document.addEventListener('keydown', (e) => {
  const mod = e.ctrlKey || e.metaKey;
  if (e.key === 'Escape') { if (!$('#panel').hidden) closePanel(); closeMenus(); return; }
  if (!mod) return;
  const k = e.key.toLowerCase();
  if (k === 'o') { e.preventDefault(); browse(); }
  else if (k === 'e' && S.view === 'report') { e.preventDefault(); const b = $('#export-btn'); if (b) b.click(); }
  else if (k === 'f') { const sb = $('#search-box'); if (sb) { e.preventDefault(); sb.focus(); sb.select(); } }
});

/* ------------------------------------------------------------------ boot */
(async function boot() {
  render();
  const [info, settings] = await Promise.all([call('get_app_info'), call('get_settings')]);
  if (!isErr(info)) S.info = info;
  if (!isErr(settings)) S.settings = settings;
  applyTheme();
  const [recent, inv, folders] = await Promise.all([call('list_recent'), call('get_inventory'), call('get_plugin_folders')]);
  if (!isErr(recent)) S.recent = recent;
  if (!isErr(inv)) S.inv = inv;
  if (!isErr(folders)) S.folders = folders.folders;
  S.view = S.settings.first_run_done ? 'home' : 'firstrun';
  render();
}());
