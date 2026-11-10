// Läuft auf jeder Seite: Formulare senden, Blätter öffnen, Fotos groß zeigen, Listen filtern,
// Abgelegtes nachsenden und den Service Worker anmelden.

import { richteFotoFelderEin } from './medien.js';
import { abschicken, ausgangAnzahl, meldung, neueKennung, sende, sendeAusgang } from './werkzeug.js';

if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.register('/sw.js').catch(() => {
    // Ohne Service Worker läuft die App normal weiter.
  });
}

richteFotoFelderEin();

// ----- Formulare -----

document.addEventListener('submit', async (ereignis) => {
  const form = ereignis.target;
  if (!form.matches('form[data-senden]')) return;
  ereignis.preventDefault();
  if (form.dataset.laeuft) return;
  if (form.dataset.frage && !confirm(form.dataset.frage)) return;

  const daten = new FormData(form);
  // Bleibt beim erneuten Tippen dieselbe, damit ein Eintrag nie doppelt entsteht.
  form.dataset.kennung ??= neueKennung();
  daten.set('_schluessel', form.dataset.kennung);
  form.dispatchEvent(new CustomEvent('sammeln', { detail: daten }));
  const knopf = form.querySelector('button[type="submit"]');
  form.dataset.laeuft = '1';
  knopf?.classList.add('laedt');
  try {
    // Löschen und Ähnliches wird nicht abgelegt. Das soll man bewusst noch einmal tun.
    const antwort = await sende(form.action, daten, { ablegen: !form.dataset.frage });
    if (antwort?.wartet) {
      zeigeAbgelegt(form);
      return;
    }
    location.replace(antwort?.weiter ?? location.href);
  } catch (fehler) {
    meldung(fehler.message, { fehler: true });
    delete form.dataset.laeuft;
    knopf?.classList.remove('laedt');
  }
});

function zeigeAbgelegt(form) {
  const hinweis = document.createElement('div');
  hinweis.className = 'inhalt';
  hinweis.innerHTML = `
    <section class="leer">
      <span class="leer-symbol"><svg class="symbol" aria-hidden="true"><use href="#s-wolke"/></svg></span>
      <h2>Auf dem Handy gespeichert</h2>
      <p class="leise">Gerade ist kein Netz da. Der Eintrag wird gesendet, sobald die Verbindung zurück ist. Du musst nichts noch einmal eingeben.</p>
      <a class="knopf ist-haupt" href="/heute">Weiter</a>
    </section>`;
  form.replaceWith(hinweis);
  zeigeAusgang();
}

// Ein Tipper auf den Zustand speichert sofort (Rundgang).
document.addEventListener('change', (ereignis) => {
  if (ereignis.target.matches('[data-auto-senden]')) abschicken(ereignis.target.form);
});

// Freiwillige Auswahl lässt sich durch nochmaliges Antippen wieder abwählen.
document.addEventListener('click', (ereignis) => {
  const feld = ereignis.target.closest('.zustand-wahl input[type="radio"], .chip input[type="radio"]');
  if (!feld || feld.hasAttribute('data-auto-senden')) return;
  if (feld.dataset.gewaehlt) {
    feld.checked = false;
    delete feld.dataset.gewaehlt;
  } else {
    for (const anderes of feld.form.querySelectorAll(`input[name="${feld.name}"]`)) delete anderes.dataset.gewaehlt;
    feld.dataset.gewaehlt = '1';
  }
});

// Eine Anleitung füllt Titel und Abstand der Aufgabe vor.
const anleitungWahl = document.getElementById('anleitung-wahl');
anleitungWahl?.addEventListener('change', () => {
  const wahl = anleitungWahl.selectedOptions[0];
  const titel = document.getElementById('aufgabe-titel');
  const bekannt = [...anleitungWahl.options].some((o) => o.dataset.titel === titel.value);
  if (wahl.dataset.titel && (!titel.value || bekannt)) titel.value = wahl.dataset.titel;
  if (wahl.value) document.getElementById('aufgabe-intervall').value = wahl.dataset.intervall;
});

// ----- Blätter und Großbild -----

document.addEventListener('click', (ereignis) => {
  const oeffner = ereignis.target.closest('[data-oeffnet]');
  if (oeffner) {
    document.getElementById(oeffner.dataset.oeffnet)?.showModal();
    return;
  }
  const bild = ereignis.target.closest('a[data-bild]');
  if (bild) {
    ereignis.preventDefault();
    const gross = document.getElementById('grossbild');
    gross.querySelector('img').src = bild.href;
    gross.showModal();
    return;
  }
  const fenster = ereignis.target.closest('dialog');
  if (!fenster || ereignis.target !== fenster) {
    if (ereignis.target.closest('#grossbild img')) fenster.close();
    return;
  }
  // Ein Tipp neben das Blatt schließt es. Ein Tipp zwischen zwei Knöpfen im Blatt nicht.
  const rahmen = fenster.getBoundingClientRect();
  const daneben = ereignis.clientY < rahmen.top || ereignis.clientX < rahmen.left || ereignis.clientX > rahmen.right;
  if (daneben || fenster.id === 'grossbild') fenster.close();
});

// ----- Listen filtern -----

for (const leiste of document.querySelectorAll('[data-filter]')) {
  const liste = document.querySelector(leiste.dataset.filter);
  if (!liste) continue;
  const zeilen = [...liste.children];
  const leer = liste.parentElement.querySelector('[data-filter-leer]');
  const filtere = () => {
    const text = leiste.querySelector('[data-filter-text]')?.value.trim().toLowerCase() ?? '';
    const wert = leiste.querySelector('[data-filter-wert]:checked')?.value ?? '';
    const sortiert = leiste.querySelector('[data-filter-sortieren]')?.checked ?? false;
    let sichtbar = 0;
    for (const zeile of zeilen) {
      const passt = (!text || zeile.dataset.text.includes(text)) && (!wert || zeile.dataset.wert === wert);
      zeile.hidden = !passt;
      if (passt) sichtbar += 1;
    }
    const folge = sortiert ? [...zeilen].sort((a, b) => a.dataset.rang - b.dataset.rang) : zeilen;
    liste.append(...folge);
    if (leer) leer.hidden = sichtbar > 0;
  };
  leiste.addEventListener('input', filtere);
  leiste.addEventListener('change', filtere);
}

// ----- Ausgang: was wegen fehlendem Netz noch auf dem Handy liegt -----

async function zeigeAusgang() {
  const balken = document.getElementById('ausgang');
  if (!balken) return 0;
  const anzahl = await ausgangAnzahl();
  balken.hidden = anzahl === 0;
  document.getElementById('ausgang-text').textContent =
    anzahl === 1 ? '1 Eintrag wartet auf das Senden' : `${anzahl} Einträge warten auf das Senden`;
  return anzahl;
}

async function leereAusgang(laut) {
  const { gesendet, abgelehnt } = await sendeAusgang();
  const rest = await zeigeAusgang();
  if (abgelehnt.length) meldung(`Nicht gespeichert: ${abgelehnt[0]}`, { fehler: true, dauer: 8000 });
  else if (gesendet && !rest) {
    meldung(gesendet === 1 ? 'Der wartende Eintrag ist gesendet.' : `${gesendet} wartende Einträge sind gesendet.`);
    if (!document.querySelector('form[data-senden] textarea, form[data-senden] input[type="file"]')) {
      setTimeout(() => location.reload(), 1200);
    }
  } else if (laut && rest) meldung('Noch kein Netz. Die Einträge bleiben auf dem Handy.', { fehler: true });
}

document.getElementById('ausgang-senden')?.addEventListener('click', () => leereAusgang(true));
window.addEventListener('online', () => leereAusgang(false));
zeigeAusgang().then((anzahl) => {
  if (anzahl && navigator.onLine) leereAusgang(false);
});
