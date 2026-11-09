// Karte eines Gartens: Flurstücke, Zeichnen, GPS, Objekte
(async () => {
  const gid = window.GARDEN_ID;
  const role = window.GARDEN_ROLE;
  const canPlan = role === 'owner' || role === 'meister';
  const isOwner = role === 'owner';
  const info = document.getElementById('mapInfo');

  const map = L.map('map', { zoomControl: true }).setView([52.2842, 9.3884], 16);
  // Basiskarte: OSM-Kacheln (nur zur Anzeige)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 20, attribution: '© OpenStreetMap'
  }).addTo(map);

  const flstLayer = L.geoJSON(null, {
    style: { color: '#7a5a3a', weight: 1.5, fillOpacity: 0.04 },
    onEachFeature: (f, l) => {
      const p = f.properties;
      l.bindTooltip(`Flst. ${p.flurstueck} · Flur ${p.flur}`, { sticky: true });
      l.on('click', () => toggleFlst(f, l));
    }
  });
  let flstVisible = true;
  const selected = new Set();
  function toggleFlst(f, l) {
    const key = f.properties.kennzeichen;
    if (!canPlan) return;
    if (selected.has(key)) { selected.delete(key); l.setStyle({ color: '#7a5a3a', fillOpacity: 0.04 }); }
    else { selected.add(key); l.setStyle({ color: '#2f5d3a', fillOpacity: 0.25 }); }
    info.textContent = selected.size ? `${selected.size} Flurstück(e) ausgewählt` : 'Flurstücke antippen, um sie dem Garten zuzuordnen';
  }
  try {
    const flst = await api('/api/flurstuecke');
    flstLayer.addData(flst);
    flstLayer.addTo(map);
  } catch (e) { info.textContent = 'Flurstücke konnten nicht geladen werden.'; }

  const objLayer = L.layerGroup().addTo(map);
  const garden = await api(`/api/gaerten/${gid}`);
  if (garden.polygon) {
    const poly = L.geoJSON(JSON.parse(garden.polygon), { style: { color: '#2f5d3a', weight: 3, fillOpacity: 0.15 } }).addTo(map);
    map.fitBounds(poly.getBounds(), { padding: [20, 20] });
  }

  async function reloadObjects() {
    objLayer.clearLayers();
    const objs = await api(`/api/gaerten/${gid}/objekte`);
    for (const o of objs) {
      if (!o.geometrie) continue;
      const geo = JSON.parse(o.geometrie);
      const layer = L.geoJSON(geo, {
        pointToLayer: (f, ll) => L.marker(ll, { icon: L.divIcon({ className: 'obj-pin', html: o.typ === 'pflanze' ? '🌱' : '🧱', iconSize: [28, 28] }) }),
        style: { color: '#7a5a3a', weight: 2, fillOpacity: 0.2 }
      });
      layer.bindTooltip(o.name);
      layer.on('click', () => { location.href = `/objekte/${o.id}`; });
      layer.addTo(objLayer);
    }
    renderList(objs);
  }

  function renderList(objs) {
    const el = document.getElementById('objList');
    if (!objs.length) { el.innerHTML = '<p class="muted">Noch keine Pflanzen oder Objekte. Lege die erste an.</p>'; return; }
    el.innerHTML = objs.map(o => `
      <a class="item" href="/objekte/${o.id}" style="display:block;color:inherit">
        <div class="row between"><strong>${escapeHtml(o.name)}</strong>
          ${o.zustand ? `<span class="zustand z${o.zustand}">${o.zustand}/5</span>` : ''}</div>
        <div class="meta">${escapeHtml(o.kategorie || '')} · ${o.typ === 'pflanze' ? 'Pflanze' : 'Objekt'}</div>
      </a>`).join('');
  }

  // --- Flurstücke toggle
  document.getElementById('toggleFlst').onclick = () => {
    flstVisible = !flstVisible;
    flstVisible ? map.addLayer(flstLayer) : map.removeLayer(flstLayer);
  };
  document.getElementById('toggleObj').onclick = () => {
    map.hasLayer(objLayer) ? map.removeLayer(objLayer) : map.addLayer(objLayer);
  };

  // --- Garten zeichnen (einfacher Polygon-Modus)
  let drawing = false, drawPts = [], drawLine = null;
  const btnDraw = document.getElementById('btnDraw');
  btnDraw.onclick = () => {
    if (!canPlan && !isOwner) return toast('Nur Besitzer oder Meister dürfen zeichnen.');
    if (!drawing) {
      drawing = true; drawPts = []; btnDraw.textContent = '✔️ Fertig';
      info.textContent = 'Auf die Karte tippen, um die Ecken zu setzen. Dann „Fertig“.';
      map.on('click', drawClick);
    } else {
      finishDraw();
    }
  };
  function drawClick(e) {
    drawPts.push([e.latlng.lng, e.latlng.lat]);
    if (drawLine) map.removeLayer(drawLine);
    drawLine = L.polyline(drawPts.map(p => [p[1], p[0]]), { color: '#2f5d3a', weight: 3, dashArray: '6 6' }).addTo(map);
  }
  async function finishDraw() {
    map.off('click', drawClick);
    drawing = false; btnDraw.textContent = '✏️ Garten zeichnen';
    if (drawPts.length < 3) { toast('Mindestens 3 Ecken nötig'); if (drawLine) map.removeLayer(drawLine); return; }
    const ring = [...drawPts, drawPts[0]];
    const polygon = { type: 'Polygon', coordinates: [ring] };
    const r = await api('/api/messen/flaeche', { method: 'POST', body: { polygon } });
    if (!confirm(`Fläche: ${r.flaeche_m2.toFixed(1)} m², Umfang ${r.umfang_m.toFixed(1)} m\nAls Gartenfläche speichern?`)) return;
    await api(`/api/gaerten/${gid}`, { method: 'PUT', body: {
      name: garden.name, adresse: garden.adresse, notizen: garden.notizen,
      flurstuecke: [...selected], polygon
    }});
    location.reload();
  }

  // --- GPS
  const gpsOut = document.getElementById('gpsResult');
  function showGps(html) { gpsOut.hidden = false; gpsOut.innerHTML = html; }
  function needHttps() {
    if (!window.isSecureContext) {
      showGps('<strong>GPS gesperrt.</strong> Der Browser erlaubt Standort nur über HTTPS. Bitte die Tunnel-Adresse öffnen.');
      return true;
    }
    return false;
  }
  function getPosition(ms = 10000) {
    return new Promise((res, rej) => {
      if (!navigator.geolocation) return rej(new Error('Kein GPS verfügbar'));
      navigator.geolocation.getCurrentPosition(
        p => res(p), err => rej(err), { enableHighAccuracy: true, timeout: ms, maximumAge: 0 });
    });
  }

  document.getElementById('btnHere').onclick = async () => {
    if (needHttps()) return;
    try {
      const p = await getPosition();
      const { latitude: lat, longitude: lon, accuracy } = p.coords;
      map.setView([lat, lon], 19);
      L.circle([lat, lon], { radius: accuracy, color: '#3a7bd5', weight: 1 }).addTo(map);
      showGps(`📍 ${lat.toFixed(6)}, ${lon.toFixed(6)} · Genauigkeit ±${Math.round(accuracy)} m<br>
        <button class="btn primary small" id="gpsAdd">Pflanze/Objekt hier anlegen</button>`);
      document.getElementById('gpsAdd').onclick = () => openNewObject({ type: 'Point', coordinates: [lon, lat] });
    } catch (e) { showGps(`GPS fehlgeschlagen: ${e.message || e.code}`); }
  };

  document.getElementById('btnMeasure').onclick = async () => {
    if (needHttps()) return;
    showGps('Punkt A: Standort wird ermittelt…');
    try {
      const a = (await getPosition()).coords;
      showGps('Gehe zu Punkt B und tippe „Punkt B“.<br><button class="btn primary small" id="gpsB">Punkt B messen</button>');
      document.getElementById('gpsB').onclick = async () => {
        const b = (await getPosition()).coords;
        const r = await api('/api/messen/abstand', { method: 'POST', body: {
          a: { lat: a.latitude, lon: a.longitude }, b: { lat: b.latitude, lon: b.longitude } } });
        showGps(`Abstand: <strong>${r.abstand_m.toFixed(2)} m</strong><br><span class="hint">Orientierungsmessung, keine amtliche Vermessung.</span>`);
      };
    } catch (e) { showGps('GPS fehlgeschlagen: ' + (e.message || e.code)); }
  };

  // --- Neues Objekt (Formular)
  function openNewObject(geometrie = null) {
    if (!canPlan) return toast('Nur Meister und Besitzer dürfen anlegen.');
    const lex = null;
    const sheet = openSheet(`
      <h2>Neue Pflanze oder Objekt</h2>
      <form class="stack" id="newObjForm">
        <label>Art
          <select name="typ"><option value="pflanze">Pflanze</option><option value="objekt">Objekt</option></select>
        </label>
        <label>Name
          <input name="name" required placeholder="z. B. Apfelbaum Nord">
        </label>
        <label>Kategorie
          <select name="kategorie" id="kategorieSel"></select>
        </label>
        <label>Aus Lexikon übernehmen (optional)
          <select name="lexikon_key" id="lexSel"><option value="">– kein Lexikon-Eintrag –</option></select>
        </label>
        <label>Standort-Notiz
          <input name="standort_notiz" placeholder="z. B. hinten links am Zaun">
        </label>
        <label>Zustand (1 kritisch … 5 sehr gut)
          <select name="zustand"><option value="">–</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select>
        </label>
        <label>Geometrie
          <select name="geo"><option value="punkt">Punkt</option><option value="flaeche">Fläche (ohne Zeichnung – später)</option></select>
        </label>
        <button class="btn primary big" type="submit">Speichern</button>
        <button class="btn big" type="button" onclick="closeSheet()">Abbrechen</button>
      </form>`);
    const form = sheet.querySelector('#newObjForm');
    const typSel = form.querySelector('[name=typ]');
    const katSel = form.querySelector('#kategorieSel');
    const fillKat = () => {
      const list = typSel.value === 'pflanze' ? PFLANZE_KATS : OBJEKT_KATS;
      katSel.innerHTML = list.map(k => `<option>${k}</option>`).join('');
    };
    typSel.onchange = fillKat; fillKat();
    getLexikon().then(lex => {
      form.querySelector('#lexSel').insertAdjacentHTML('beforeend',
        lex.map(l => `<option value="${l.key}">${escapeHtml(l.name)}</option>`).join(''));
    });
    form.onsubmit = async (e) => {
      e.preventDefault();
      const fd = Object.fromEntries(new FormData(form).entries());
      const body = {
        typ: fd.typ, name: fd.name.trim(), kategorie: fd.kategorie,
        lexikon_key: fd.lexikon_key || null, standort_notiz: fd.standort_notiz || null,
        zustand: fd.zustand ? Number(fd.zustand) : null,
        geometrie: geometrie
      };
      try {
        const r = await api(`/api/gaerten/${gid}/objekte`, { method: 'POST', body });
        closeSheet(); toast('Gespeichert'); location.href = `/objekte/${r.id}`;
      } catch (err) { toast(err.message); }
    };
  }
  const PFLANZE_KATS = ['Baum','Strauch','Staude','Kletterpflanze','Gemüse','Rasen','Beet','Sonstiges'];
  const OBJEKT_KATS = ['Weg','Teich','Zaun','Gebäude','Terrasse','Sitzplatz','Sonstiges'];
  document.getElementById('btnNewObj').onclick = () => openNewObject(null);

  await reloadObjects();
  info.textContent = isOwner ? 'Flurstücke antippen und dann „Garten zeichnen“ nutzen.' : 'Karte aktuell.';
})().catch(e => { document.getElementById('mapInfo').textContent = 'Fehler: ' + e.message; });
