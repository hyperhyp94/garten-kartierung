// Kleine Helfer, die jede Seite braucht.

const csrf = document.querySelector('meta[name="csrf"]')?.content ?? '';
let meldungsUhr = null;

/** Zeigt kurz eine Meldung am unteren Rand. */
export function meldung(text, { fehler = false, oben = false, dauer = 4500 } = {}) {
  const feld = document.getElementById('meldung');
  if (!feld) return;
  // Im geöffneten Blatt liegt die Meldung sonst dahinter.
  const offen = document.querySelector('dialog[open]');
  (offen ?? document.body).append(feld);
  feld.textContent = text;
  feld.classList.toggle('ist-fehler', fehler);
  feld.classList.toggle('ist-oben', oben);
  feld.hidden = false;
  clearTimeout(meldungsUhr);
  meldungsUhr = setTimeout(() => {
    feld.hidden = true;
  }, dauer);
}

/** Spricht mit dem Server. Wirft einen Fehler mit einem Text, den man dem Nutzer zeigen kann. */
export async function api(methode, adresse, daten) {
  let antwort;
  try {
    antwort = await fetch(adresse, {
      method: methode,
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: daten === undefined ? undefined : JSON.stringify(daten),
    });
  } catch {
    throw new Error('Keine Verbindung. Bitte noch einmal versuchen.');
  }
  let inhalt = null;
  try {
    inhalt = await antwort.json();
  } catch {
    // Antwort ohne Inhalt
  }
  if (antwort.status === 401) {
    location.href = `/anmelden?weiter=${encodeURIComponent(location.pathname)}`;
    throw new Error('Bitte neu anmelden.');
  }
  if (!antwort.ok) {
    throw new Error(inhalt?.fehler ?? 'Das hat nicht geklappt. Bitte noch einmal versuchen.');
  }
  return inhalt;
}

/** 1317 wird zu „1.317 m²“. */
export function flaeche(m2) {
  return `${Math.round(m2).toLocaleString('de-DE')} m²`;
}

export function seitenDaten() {
  return JSON.parse(document.getElementById('daten').textContent);
}
