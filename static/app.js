// Gemeinsame Helfer für alle Seiten
window.escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
window.fmtDate = (iso) => { if (!iso) return '–'; const [y,m,d] = iso.slice(0,10).split('-'); return `${d}.${m}.${y}`; };
window.todayIso = () => new Date().toISOString().slice(0,10);

window.toast = (msg, ms = 2600) => {
  const t = document.getElementById('toast');
  if (!t) return alert(msg);
  t.textContent = msg; t.hidden = false;
  clearTimeout(window._toastT); window._toastT = setTimeout(() => t.hidden = true, ms);
};

window.api = async (url, opts = {}) => {
  const init = { method: opts.method || 'GET', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.CSRF }, credentials: 'same-origin' };
  if (opts.body instanceof FormData) { delete init.headers['Content-Type']; init.body = opts.body; }
  else if (opts.body !== undefined) init.body = JSON.stringify(opts.body);
  const r = await fetch(url, init);
  let data = null; try { data = await r.json(); } catch (_) {}
  if (!r.ok) throw new Error((data && data.error) || `Fehler ${r.status}`);
  return data;
};

// Modal-Hilfe
window.openSheet = (html) => {
  let m = document.getElementById('modal');
  if (!m) {
    m = document.createElement('div'); m.id = 'modal'; m.className = 'modal';
    m.innerHTML = '<div class="sheet" id="sheet"></div>';
    m.addEventListener('click', e => { if (e.target === m) closeSheet(); });
    document.body.appendChild(m);
  }
  document.getElementById('sheet').innerHTML = html;
  m.hidden = false;
  return document.getElementById('sheet');
};
window.closeSheet = () => { const m = document.getElementById('modal'); if (m) m.hidden = true; };

// Service: Lexikon-Daten einmal laden
window.lexikonCache = null;
window.getLexikon = async () => {
  if (!window.lexikonCache) window.lexikonCache = await api('/api/lexikon');
  return window.lexikonCache;
};
