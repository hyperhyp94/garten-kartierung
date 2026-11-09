// Aufgabenliste mit Erledigen und Anlegen
(async () => {
  const gid = window.GARDEN_ID;
  const canPlan = window.GARDEN_ROLE === 'owner' || window.GARDEN_ROLE === 'meister';
  const list = document.getElementById('taskList');

  async function load() {
    const tasks = await api(`/api/gaerten/${gid}/aufgaben`);
    if (!tasks.length) { list.innerHTML = '<p class="muted">Keine Aufgaben. Lege eine an oder übernimm eine Anleitung.</p>'; return; }
    const groups = { 1: 'Hoch', 2: 'Mittel', 3: 'Niedrig' };
    list.innerHTML = [1, 2, 3].map(p => {
      const items = tasks.filter(t => t.prioritaet === p && t.status === 'offen');
      if (!items.length) return '';
      return `<h2>Priorität ${p} · ${groups[p]}</h2>` + items.map(t => `
        <div class="item prio-${t.prioritaet}" id="task-${t.id}">
          <div class="row between">
            <div class="grow"><strong>${escapeHtml(t.titel)}</strong>
              <div class="meta">${t.faellig_am ? 'fällig ' + fmtDate(t.faellig_am) : 'ohne Termin'}${t.ueberfaellig ? ' · <span style="color:var(--rot)">überfällig</span>' : ''}${t.intervall_monate ? ' · alle ' + t.intervall_monate + ' Mon.' : ''}</div>
            </div>
            <button class="btn small primary" data-done="${t.id}">Erledigt</button>
          </div>
          ${t.anleitung ? `<details><summary class="small">Anleitung</summary><div class="anl">${escapeHtml(t.anleitung).replace(/\n/g,'<br>')}</div></details>` : ''}
        </div>`).join('');
    }).join('') || '<p class="muted">Alles erledigt. 🎉</p>';

    list.querySelectorAll('[data-done]').forEach(btn => btn.onclick = () => openDone(Number(btn.dataset.done)));
  }

  function openDone(tid) {
    const sheet = openSheet(`
      <h2>Aufgabe erledigt</h2>
      <form class="stack" id="doneForm">
        <label>Datum <input type="date" name="datum" value="${todayIso()}"></label>
        <label>Was wurde gemacht?
          <textarea name="beschreibung" placeholder="z. B. Krone ausgelichtet, Totholz entfernt"></textarea></label>
        <label>Zustand danach (optional)
          <select name="zustand_nach"><option value="">–</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select></label>
        <label>Foto vorher (optional)
          <input type="file" name="vorher" accept="image/*,video/*" capture="environment"></label>
        <label>Foto nachher (optional)
          <input type="file" name="nachher" accept="image/*,video/*" capture="environment"></label>
        <button class="btn primary big" type="submit">Protokoll speichern</button>
        <button class="btn big" type="button" onclick="closeSheet()">Abbrechen</button>
      </form>`);
    sheet.querySelector('#doneForm').onsubmit = async (e) => {
      e.preventDefault();
      const f = e.target;
      const body = {
        datum: f.datum.value, beschreibung: f.beschreibung.value,
        zustand_nach: f.zustand_nach.value ? Number(f.zustand_nach.value) : null
      };
      try {
        await api(`/api/aufgaben/${tid}/erledigen`, { method: 'POST', body });
        // Fotos an das Ereignis hängen ist v2 – Bilder sind über das Objekt erreichbar
        closeSheet(); toast('Erledigt – Folgetermin gesetzt, wenn wiederkehrend'); load();
      } catch (err) { toast(err.message); }
    };
  }

  if (canPlan) {
    document.getElementById('btnNewTask')?.addEventListener('click', () => {
      const sheet = openSheet(`
        <h2>Neue Aufgabe</h2>
        <form class="stack" id="taskForm">
          <label>Titel <input name="titel" required placeholder="z. B. Apfelbaum schneiden"></label>
          <label>Anleitung (Markdown möglich)
            <textarea name="anleitung" placeholder="Schritt für Schritt…"></textarea></label>
          <label>Fällig am <input type="date" name="faellig_am" value="${todayIso()}"></label>
          <label>Intervall in Monaten (leer = einmalig)
            <input type="number" name="intervall_monate" min="1" max="120"></label>
          <label>Saison (Monate 1–12, z. B. 2,3)
            <input name="saison" placeholder="2,3"></label>
          <label>Priorität (leer = automatisch)
            <select name="prio_manuell"><option value="">automatisch</option><option value="1">1 hoch</option><option value="2">2 mittel</option><option value="3">3 niedrig</option></select></label>
          <button class="btn primary big" type="submit">Speichern</button>
          <button class="btn big" type="button" onclick="closeSheet()">Abbrechen</button>
        </form>`);
      sheet.querySelector('#taskForm').onsubmit = async (e) => {
        e.preventDefault();
        const f = e.target;
        const body = {
          titel: f.titel.value.trim(), anleitung: f.anleitung.value || null,
          faellig_am: f.faellig_am.value || null,
          intervall_monate: f.intervall_monate.value ? Number(f.intervall_monate.value) : null,
          saison: f.saison.value || null,
          prio_manuell: f.prio_manuell.value ? Number(f.prio_manuell.value) : null
        };
        try { await api(`/api/gaerten/${gid}/aufgaben`, { method: 'POST', body }); closeSheet(); toast('Aufgabe angelegt'); load(); }
        catch (err) { toast(err.message); }
      };
    });
  }

  document.getElementById('btnTaskCal')?.addEventListener('click', () => {
    location.href = `/api/gaerten/${gid}/kalender.ics`;
  });

  await load();
})().catch(e => { document.getElementById('taskList').textContent = 'Fehler: ' + e.message; });
