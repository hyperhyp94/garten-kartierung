// Lexikon: Suche und Ausklappen
(async () => {
  const list = document.getElementById('lexList');
  const search = document.getElementById('lexSearch');
  const data = await getLexikon();
  function render(q = '') {
    const s = q.trim().toLowerCase();
    const items = data.filter(l => !s || (l.name + ' ' + l.latein + ' ' + l.typ).toLowerCase().includes(s));
    list.innerHTML = items.length ? items.map(l => `
      <details class="lex-item">
        <summary>${escapeHtml(l.name)} <span class="muted small">${escapeHtml(l.typ)}</span></summary>
        <dl class="grid">
          <dt>Lateinisch</dt><dd><em>${escapeHtml(l.latein)}</em></dd>
          <dt>Standort</dt><dd>${escapeHtml(l.standort)}</dd>
          <dt>Boden</dt><dd>${escapeHtml(l.boden)}</dd>
          <dt>Wuchshöhe</dt><dd>${escapeHtml(l.wuchshoehe)}</dd>
          <dt>Blüte</dt><dd>${escapeHtml(l.blute)}</dd>
          <dt>Schnitt</dt><dd>${escapeHtml(l.schnitt)}</dd>
          <dt>Pflege</dt><dd>${escapeHtml(l.pflege)}</dd>
          <dt>Krankheiten</dt><dd>${escapeHtml(l.krankheiten)}</dd>
          <dt>Lebensdauer</dt><dd>${escapeHtml(l.lebenserwartung)}</dd>
          <dt>Hinweise</dt><dd>${escapeHtml(l.hinweise)}</dd>
        </dl>
        <p class="hint">Richtwert, vor Ort prüfen.</p>
      </details>`).join('') : '<p class="muted">Kein Treffer.</p>';
  }
  search.addEventListener('input', () => render(search.value));
  render();
})().catch(e => { document.getElementById('lexList').textContent = 'Fehler: ' + e.message; });
