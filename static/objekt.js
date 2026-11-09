// Objektseite: Wissen, Protokoll, Beobachtungen, Bilder, Aufgaben
(async () => {
  const oid = window.OBJ_ID, gid = window.GARDEN_ID, role = window.GARDEN_ROLE;
  const canPlan = role === 'owner' || role === 'meister';

  // Tabs
  document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.toggle('on', x === t));
    document.querySelectorAll('.tabpanel').forEach(p => p.hidden = p.id !== 'tab-' + t.dataset.tab);
    loaders[t.dataset.tab]?.();
  });

  const loaders = {
    wissen: loadWissen, protokoll: loadProtokoll, beob: loadBeob, bilder: loadBilder, aufgaben: loadAufgaben
  };

  async function loadWissen() {
    const el = document.getElementById('tab-wissen');
    const items = await api(`/api/objekte/${oid}/wissen`);
    el.innerHTML = `<div class="row between"><h2>Wissen</h2>
      <button class="btn small primary" id="addWissen">+ Eintrag</button></div>` +
      (items.length ? items.map(k => `<div class="item"><strong>${escapeHtml(k.titel)}</strong>
        <div class="meta">${escapeHtml(k.kategorie || '')} · ${fmtDate(k.created_at)}</div>
        <div class="anl">${escapeHtml(k.text || '').replace(/\n/g, '<br>')}</div></div>`).join('')
        : '<p class="muted">Noch kein Wissen hinterlegt.</p>');
    el.querySelector('#addWissen').onclick = () => {
      const s = openSheet(`<h2>Wissen hinzufügen</h2>
        <form class="stack" id="wForm">
          <label>Titel <input name="titel" required></label>
          <label>Kategorie <select name="kategorie"><option>Pflege</option><option>Standort</option><option>Krankheit</option><option>Sorte</option><option>Sonstiges</option></select></label>
          <label>Text <textarea name="text"></textarea></label>
          <button class="btn primary big" type="submit">Speichern</button>
          <button class="btn big" type="button" onclick="closeSheet()">Abbrechen</button></form>`);
      s.querySelector('#wForm').onsubmit = async (e) => { e.preventDefault(); const f = e.target;
        try { await api(`/api/objekte/${oid}/wissen`, { method: 'POST', body: { titel: f.titel.value, kategorie: f.kategorie.value, text: f.text.value } });
          closeSheet(); loadWissen(); } catch (err) { toast(err.message); } };
    };
  }

  async function loadProtokoll() {
    const el = document.getElementById('tab-protokoll');
    const items = await api(`/api/objekte/${oid}/ereignisse`);
    el.innerHTML = `<div class="row between"><h2>Protokoll</h2>
      <button class="btn small primary" id="addEv">+ Ereignis</button></div>` +
      (items.length ? items.map(e => `<div class="item"><strong>${fmtDate(e.datum)} · ${escapeHtml(e.typ)}</strong>
        <div class="meta">${e.zustand_nach ? 'Zustand danach ' + e.zustand_nach + '/5' : ''}</div>
        <div>${escapeHtml(e.beschreibung || '')}</div></div>`).join('')
        : '<p class="muted">Noch keine Einträge.</p>');
    el.querySelector('#addEv').onclick = () => {
      const s = openSheet(`<h2>Ereignis</h2>
        <form class="stack" id="evForm">
          <label>Datum <input type="date" name="datum" value="${todayIso()}"></label>
          <label>Art <select name="typ">${EVENTS.map(t => `<option>${t}</option>`).join('')}</select></label>
          <label>Beschreibung <textarea name="beschreibung"></textarea></label>
          <label>Zustand danach (optional) <select name="zustand_nach"><option value="">–</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select></label>
          <label>Foto vorher <input type="file" name="vorher" accept="image/*,video/*" capture="environment"></label>
          <label>Foto nachher <input type="file" name="nachher" accept="image/*,video/*" capture="environment"></label>
          <button class="btn primary big" type="submit">Speichern</button>
          <button class="btn big" type="button" onclick="closeSheet()">Abbrechen</button></form>`);
      s.querySelector('#evForm').onsubmit = async (e) => { e.preventDefault(); const f = e.target;
        try {
          const r = await api(`/api/objekte/${oid}/ereignisse`, { method: 'POST', body: {
            datum: f.datum.value, typ: f.typ.value, beschreibung: f.beschreibung.value,
            zustand_nach: f.zustand_nach.value ? Number(f.zustand_nach.value) : null } });
          await uploadIfSet(f, { event_id: r.id });
          closeSheet(); loadProtokoll(); toast('Gespeichert');
        } catch (err) { toast(err.message); } };
    };
  }

  async function loadBeob() {
    const el = document.getElementById('tab-beob');
    const items = await api(`/api/objekte/${oid}/beobachtungen`);
    const jahre = {};
    items.forEach(b => { const y = b.datum.slice(0, 4); (jahre[y] ||= []).push(b); });
    el.innerHTML = `<div class="row between"><h2>Watch-Kalender</h2>
      <button class="btn small primary" id="addBeob">+ Beobachtung</button></div>
      <p class="muted small">Triebe, Knospen, Blüte – über die Jahre vergleichbar.</p>` +
      (Object.keys(jahre).length ? Object.keys(jahre).sort().reverse().map(y => `
        <h3 style="margin:.6rem 0 .2rem">${y}</h3>` + jahre[y].map(b => `
          <div class="item"><strong>${fmtDate(b.datum)} · ${escapeHtml(b.phase)}</strong>
          <div>${escapeHtml(b.notiz || '')}</div></div>`).join('')).join('')
        : '<p class="muted">Noch keine Beobachtungen.</p>');
    el.querySelector('#addBeob').onclick = () => {
      const s = openSheet(`<h2>Beobachtung</h2>
        <form class="stack" id="bForm">
          <label>Datum <input type="date" name="datum" value="${todayIso()}"></label>
          <label>Phase <select name="phase">${PHASEN.map(p => `<option>${p}</option>`).join('')}</select></label>
          <label>Notiz <textarea name="notiz"></textarea></label>
          <label>Foto <input type="file" name="datei" accept="image/*,video/*" capture="environment"></label>
          <button class="btn primary big" type="submit">Speichern</button>
          <button class="btn big" type="button" onclick="closeSheet()">Abbrechen</button></form>`);
      s.querySelector('#bForm').onsubmit = async (e) => { e.preventDefault(); const f = e.target;
        try {
          const r = await api(`/api/objekte/${oid}/beobachtungen`, { method: 'POST', body: { datum: f.datum.value, phase: f.phase.value, notiz: f.notiz.value } });
          await uploadIfSet(f, { observation_id: r.id });
          closeSheet(); loadBeob(); toast('Gespeichert');
        } catch (err) { toast(err.message); } };
    };
  }

  async function loadBilder() {
    const el = document.getElementById('tab-bilder');
    const items = await api(`/api/objekte/${oid}/medien`);
    el.innerHTML = `<div class="row between"><h2>Bilder & Videos</h2>
      <button class="btn small primary" id="addMedia">+ Hochladen</button></div>
      <p class="muted small">Bilder bis 10 MB, Videos bis 200 MB. Vorher/Nachher bitte in der Notiz vermerken.</p>
      <div class="grid-media">` +
      items.map(m => m.art === 'bild'
        ? `<a href="/uploads/${m.pfad}" target="_blank"><img src="/uploads/${m.thumb_pfad || m.pfad}" alt="" loading="lazy"></a>`
        : `<video src="/uploads/${m.pfad}" controls preload="none"></video>`).join('') + '</div>';
    el.querySelector('#addMedia').onclick = () => {
      const s = openSheet(`<h2>Hochladen</h2>
        <form class="stack" id="mForm">
          <label>Datei <input type="file" name="datei" accept="image/*,video/*" capture="environment" required></label>
          <label>Typ <select name="typ_tag"><option value="allgemein">allgemein</option><option value="vorher">vorher</option><option value="nachher">nachher</option></select></label>
          <button class="btn primary big" type="submit">Hochladen</button>
          <button class="btn big" type="button" onclick="closeSheet()">Abbrechen</button></form>`);
      s.querySelector('#mForm').onsubmit = async (e) => { e.preventDefault();
        try { await uploadIfSet(e.target, { object_id: oid }, 'datei'); closeSheet(); loadBilder(); toast('Hochgeladen'); }
        catch (err) { toast(err.message); } };
    };
  }

  async function loadAufgaben() {
    const el = document.getElementById('tab-aufgaben');
    const all = await api(`/api/gaerten/${gid}/aufgaben`);
    const mine = all.filter(t => t.object_id === oid);
    el.innerHTML = `<div class="row between"><h2>Aufgaben</h2>
      ${canPlan ? '<button class="btn small primary" id="addTask">+ Aufgabe</button>' : ''}</div>` +
      (mine.length ? mine.map(t => `<div class="item prio-${t.prioritaet}">
        <strong>${escapeHtml(t.titel)}</strong>
        <div class="meta">Prio ${t.prioritaet} · ${t.faellig_am ? 'fällig ' + fmtDate(t.faellig_am) : 'ohne Termin'} · ${t.status}</div></div>`).join('')
        : '<p class="muted">Keine Aufgaben für dieses Objekt.</p>');
  }

  // Hilfsfunktion: Datei aus Formular hochladen, falls vorhanden
  async function uploadIfSet(form, extra, fieldName) {
    const names = fieldName ? [fieldName] : ['vorher', 'nachher', 'datei'];
    for (const n of names) {
      const input = form.querySelector(`[name="${n}"]`);
      if (!input || !input.files || !input.files.length) continue;
      const fd = new FormData();
      fd.append('datei', input.files[0]);
      if (n === 'vorher' || n === 'nachher') fd.append('typ_tag', n);
      for (const [k, v] of Object.entries(extra)) fd.append(k, v);
      await api('/api/medien', { method: 'POST', body: fd });
    }
  }

  await loadWissen();
})().catch(e => { document.getElementById('tab-wissen').textContent = 'Fehler: ' + e.message; });
