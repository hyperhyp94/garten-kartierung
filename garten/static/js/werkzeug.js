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

async function lies(antwort) {
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
    const fehler = new Error(inhalt?.fehler ?? 'Das hat nicht geklappt. Bitte noch einmal versuchen.');
    fehler.status = antwort.status;
    throw fehler;
  }
  return inhalt;
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
  return lies(antwort);
}

/**
 * Schickt ein Formular samt Fotos ab. Ist gerade kein Netz da, wird die Eingabe auf dem Handy
 * abgelegt und später gesendet. Dann kommt { wartet: true } zurück.
 */
export async function sende(adresse, daten, { ablegen = true } = {}) {
  let antwort;
  try {
    antwort = await fetch(adresse, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': csrf },
      body: daten,
    });
  } catch {
    if (ablegen) {
      try {
        await legeAb(adresse, daten);
        return { wartet: true };
      } catch {
        // Ablegen nicht möglich, dann bleibt nur die Fehlermeldung.
      }
    }
    throw new Error('Keine Verbindung. Bitte noch einmal versuchen.');
  }
  return lies(antwort);
}

// ----- Ausgang: Eingaben, die noch nicht beim Server angekommen sind -----

function ausgang(modus, tun) {
  return new Promise((ok, fehler) => {
    const anfrage = indexedDB.open('garten-ausgang', 1);
    anfrage.onupgradeneeded = () => anfrage.result.createObjectStore('ausgang', { keyPath: 'id', autoIncrement: true });
    anfrage.onerror = () => fehler(anfrage.error);
    anfrage.onsuccess = () => {
      const db = anfrage.result;
      const vorgang = db.transaction('ausgang', modus);
      const ergebnis = tun(vorgang.objectStore('ausgang'));
      vorgang.oncomplete = () => {
        db.close();
        ok(ergebnis?.result);
      };
      vorgang.onerror = vorgang.onabort = () => {
        db.close();
        fehler(vorgang.error);
      };
    };
  });
}

async function legeAb(adresse, daten) {
  const felder = [];
  for (const [name, wert] of daten.entries()) {
    felder.push(wert instanceof Blob ? { name, blob: wert, datei: wert.name || 'datei' } : { name, wert });
  }
  await ausgang('readwrite', (s) => s.add({ adresse, felder, zeit: Date.now() }));
}

export async function ausgangAnzahl() {
  try {
    return (await ausgang('readonly', (s) => s.count())) ?? 0;
  } catch {
    return 0;
  }
}

let sendetGerade = null;

/** Versucht, alles Abgelegte zu senden. Gibt zurück, wie viel ankam und was der Server abgelehnt hat. */
export function sendeAusgang() {
  // Nie zweimal gleichzeitig, sonst ginge derselbe Eintrag doppelt raus.
  sendetGerade ??= leereAusgang().finally(() => {
    sendetGerade = null;
  });
  return sendetGerade;
}

async function leereAusgang() {
  const ergebnis = { gesendet: 0, abgelehnt: [] };
  let eintraege = [];
  try {
    eintraege = (await ausgang('readonly', (s) => s.getAll())) ?? [];
  } catch {
    return ergebnis;
  }
  for (const eintrag of eintraege) {
    const daten = new FormData();
    for (const f of eintrag.felder) {
      if (f.blob) daten.append(f.name, f.blob, f.datei);
      else daten.append(f.name, f.wert);
    }
    try {
      await sende(eintrag.adresse, daten, { ablegen: false });
      ergebnis.gesendet += 1;
    } catch (fehler) {
      // Kein Netz, nicht angemeldet oder Seite veraltet: später noch einmal. Alles andere kann nie gelingen.
      if (!fehler.status || fehler.status === 401 || fehler.status === 400) break;
      ergebnis.abgelehnt.push(fehler.message);
    }
    await ausgang('readwrite', (s) => s.delete(eintrag.id));
  }
  return ergebnis;
}

// ----- Fotos -----

function alsJpeg(bild, groesste, guete) {
  const faktor = Math.min(1, groesste / Math.max(bild.naturalWidth, bild.naturalHeight));
  const flaeche = document.createElement('canvas');
  flaeche.width = Math.round(bild.naturalWidth * faktor);
  flaeche.height = Math.round(bild.naturalHeight * faktor);
  flaeche.getContext('2d').drawImage(bild, 0, 0, flaeche.width, flaeche.height);
  return new Promise((ok, fehler) => {
    flaeche.toBlob((blob) => (blob ? ok(blob) : fehler(new Error('leer'))), 'image/jpeg', guete);
  });
}

export async function ladeBild(adresse) {
  const bild = new Image();
  bild.src = adresse;
  await bild.decode();
  return bild;
}

/**
 * Macht aus einem Foto vom Handy ein JPEG mit höchstens 2000 Bildpunkten Kantenlänge und ein
 * kleines Vorschaubild. So dauert der Upload Sekunden, und das Fotoformat des iPhones spielt keine Rolle.
 */
export async function verkleinere(datei) {
  const adresse = URL.createObjectURL(datei);
  try {
    const bild = await ladeBild(adresse);
    return { bild: await alsJpeg(bild, 2000, 0.85), vorschau: await alsJpeg(bild, 480, 0.75) };
  } catch {
    throw new Error('Dieses Foto kann das Handy nicht lesen. Bitte ein anderes wählen.');
  } finally {
    URL.revokeObjectURL(adresse);
  }
}

export { alsJpeg };

/** 1317 wird zu „1.317 m²“. */
export function flaeche(m2) {
  return `${Math.round(m2).toLocaleString('de-DE')} m²`;
}

/** 12.43 wird zu „12,4 m“. */
export function strecke(m) {
  return `${m.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} m`;
}

export function seitenDaten() {
  return JSON.parse(document.getElementById('daten').textContent);
}

/** Schickt ein Formular so ab, als hätte jemand auf Speichern getippt. */
/** Kennung für ein Formular. Der Server erkennt daran, wenn dasselbe Formular zweimal ankommt. */
export function neueKennung() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
}

export function abschicken(form) {
  if (form.requestSubmit) form.requestSubmit();
  else form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
}
