// Pflanze oder Objekt erfassen: Lexikon-Auswahl und Lage auf der Karte.

import { erstelleEditor } from './editor.js';
import { seitenDaten } from './werkzeug.js';

const daten = seitenDaten();
const form = document.getElementById('bestand-form');
const formWahl = () => form.querySelector('input[name="form"]:checked').value;
const editor = erstelleEditor(daten, { form: formWahl() });
const nameFeld = document.getElementById('name');
const kategorie = document.getElementById('kategorie');

function waehleForm(neu) {
  form.querySelector(`input[name="form"][value="${neu}"]`).checked = true;
  editor.setzeForm(neu);
}

form.addEventListener('change', (ereignis) => {
  if (ereignis.target.name === 'form') editor.setzeForm(ereignis.target.value);
  // Ein Weg ist meist eine Linie, ein Beet eine Fläche. Solange noch nichts gezeichnet ist, schlägt die App das vor.
  if (ereignis.target === kategorie && !daten.geometrie && editor.anzahl() === 0) {
    waehleForm(kategorie.selectedOptions[0].dataset.form || 'punkt');
  }
});

form.addEventListener('sammeln', (ereignis) => {
  const lage = editor.geometrie();
  ereignis.detail.delete('form');
  ereignis.detail.set('geometrie', lage ? JSON.stringify(lage) : '');
});

// ----- Lexikon -----

const liste = document.getElementById('lexikon-liste');
if (liste) {
  const kennung = document.getElementById('lexikon-id');
  const zeile = document.getElementById('aufgaben-zeile');
  const anzahl = document.getElementById('aufgaben-anzahl');
  const chips = [...liste.children];
  let letzterName = chips.find((c) => c.classList.contains('ist-an'))?.dataset.name ?? '';

  document.getElementById('lexikon-suche').addEventListener('input', (ereignis) => {
    const text = ereignis.target.value.trim().toLowerCase();
    for (const chip of chips) chip.hidden = Boolean(text) && !chip.dataset.text.includes(text);
  });

  liste.addEventListener('click', (ereignis) => {
    const chip = ereignis.target.closest('.chip');
    if (!chip) return;
    const abwahl = chip.classList.contains('ist-an');
    for (const c of chips) c.classList.toggle('ist-an', c === chip && !abwahl);
    kennung.value = abwahl ? '' : chip.dataset.id;
    zeile.hidden = abwahl || chip.dataset.aufgaben === '0';
    anzahl.textContent = chip.dataset.aufgaben;
    // Den Namen nur überschreiben, wenn er leer ist oder noch vom Lexikon stammt.
    if (!abwahl && (!nameFeld.value || nameFeld.value === letzterName)) nameFeld.value = chip.dataset.name;
    if (!abwahl) {
      kategorie.value = chip.dataset.kategorie;
      letzterName = chip.dataset.name;
    }
  });
}
