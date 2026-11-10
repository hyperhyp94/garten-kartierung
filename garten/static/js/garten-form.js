/* global L */
// Garten anlegen oder ändern. Schritt 1: Name. Schritt 2: Flurstücke auf der Karte antippen.

import { alsLatLng, beschrifte, erstelleKarte } from './karte-basis.js';
import { api, flaeche, meldung, seitenDaten } from './werkzeug.js';

const daten = seitenDaten();
const form = document.getElementById('garten-form');
const schritt1 = document.getElementById('schritt-1');
const schritt2 = document.getElementById('schritt-2');
const nameFeld = document.getElementById('name');
const adresseFeld = document.getElementById('adresse');
const auswahlText = document.getElementById('auswahl-text');
const auswahlListe = document.getElementById('auswahl-liste');
const speichern = document.getElementById('speichern');
const tafel = document.querySelector('.tafel');

function stil() {
  // Weiße Linien auf dem Luftbild, dunkle auf der hellen Straßenkarte.
  const farbe = basis?.grund() === 'strasse' ? '#34443a' : '#ffffff';
  return { color: farbe, weight: 1.2, opacity: 0.9, fillColor: '#ffffff', fillOpacity: 0.04 };
}
const STIL_GEWAEHLT = { color: '#f2b705', weight: 3.5, opacity: 1, fillColor: '#f2b705', fillOpacity: 0.38 };

const gewaehlt = new Map(); // Kennzeichen -> { merkmal, ebene }
let basis = null;
const vorauswahl = new Set(daten.garten?.flurstuecke ?? []);
const ebenen = new Map(); // Kennzeichen -> Ebene auf der Karte
let sammlung = null;

// ----- Schritt 1 -----

document.getElementById('angaben').addEventListener('submit', (ereignis) => {
  ereignis.preventDefault();
  if (!nameFeld.value.trim()) {
    meldung('Bitte gib dem Garten einen Namen.', { fehler: true });
    nameFeld.focus();
    return;
  }
  zeigeSchritt(2);
});
document.getElementById('zurueck').addEventListener('click', () => zeigeSchritt(1));

function zeigeSchritt(nummer) {
  schritt1.hidden = nummer !== 1;
  schritt2.hidden = nummer !== 2;
  if (nummer === 2) {
    if (basis) basis.karte.invalidateSize();
    else starteKarte();
    merkeTafelhoehe();
  }
}

// ----- Schritt 2 -----

function merkeTafelhoehe() {
  // Die Knöpfe auf der Karte sitzen immer knapp über der Tafel, egal wie hoch sie ist.
  form.style.setProperty('--tafel', `${tafel.offsetHeight}px`);
}

async function starteKarte() {
  basis = erstelleKarte('karte', daten);
  const { karte, gebiet } = basis;
  karte.fitBounds(gebiet);

  document.getElementById('ebenen-knopf').addEventListener('click', () => {
    basis.setzeGrund(basis.grund() === 'luftbild' ? 'strasse' : 'luftbild');
  });
  basis.beiGrundwechsel(() => {
    for (const [k, ebene] of ebenen) if (!gewaehlt.has(k)) ebene.setStyle(stil());
  });

  try {
    sammlung = await basis.holeFlurstuecke();
  } catch (fehler) {
    meldung(fehler.message, { fehler: true });
    return;
  }

  L.geoJSON(sammlung, {
    renderer: L.canvas({ padding: 0.3, tolerance: 6 }),
    style: stil,
    onEachFeature(merkmal, ebene) {
      ebenen.set(merkmal.properties.k, ebene);
      ebene.on('click', () => schalteUm(merkmal));
    },
  }).addTo(karte);
  beschrifte(karte, sammlung.features);

  for (const f of sammlung.features) {
    if (vorauswahl.has(f.properties.k)) schalteUm(f, false);
  }
  if (gewaehlt.size) {
    zeigeMerkmale([...gewaehlt.values()].map((e) => e.merkmal), false);
  } else {
    // Ohne Auswahl startet die Karte im Ort, also dort, wo die kleinen Grundstücke liegen.
    const mitten = sammlung.features.filter((f) => f.properties.m2 < 2000).map((f) => f.mitte);
    const mittel = (werte) => werte.sort((a, b) => a - b)[Math.floor(werte.length / 2)];
    karte.setView([mittel(mitten.map((m) => m[0])), mittel(mitten.map((m) => m[1]))], 16.5, { animate: false });
  }
  zeigeAuswahl();
  richteStandortEin();
}

function schalteUm(merkmal, neuZeichnen = true) {
  const k = merkmal.properties.k;
  const ebene = ebenen.get(k);
  if (gewaehlt.has(k)) {
    gewaehlt.delete(k);
    ebene.setStyle(stil());
  } else {
    gewaehlt.set(k, { merkmal, ebene });
    ebene.setStyle(STIL_GEWAEHLT).bringToFront();
  }
  if (neuZeichnen) zeigeAuswahl();
}

function zeigeAuswahl() {
  const eintraege = [...gewaehlt.values()].map((e) => e.merkmal.properties);
  const summe = eintraege.reduce((s, e) => s + e.m2, 0);
  if (eintraege.length === 0) {
    auswahlText.textContent = 'Tippe dein Grundstück auf der Karte an.';
  } else {
    const wort = eintraege.length === 1 ? 'Flurstück' : 'Flurstücke';
    auswahlText.textContent = `${eintraege.length} ${wort} · ${flaeche(summe)}`;
  }
  auswahlListe.replaceChildren(
    ...eintraege.map((e) => {
      const punkt = document.createElement('li');
      const knopf = document.createElement('button');
      knopf.type = 'button';
      knopf.className = 'marke';
      knopf.setAttribute('aria-label', `Flurstück ${e.nr} in Flur ${e.flur} abwählen`);
      knopf.innerHTML = '<span></span><svg class="symbol" aria-hidden="true"><use href="#s-x"/></svg>';
      knopf.firstChild.textContent = `${e.nr} · Flur ${e.flur}`;
      knopf.addEventListener('click', () => schalteUm(gewaehlt.get(e.k).merkmal));
      punkt.append(knopf);
      return punkt;
    }),
  );
  speichern.disabled = eintraege.length === 0;
  merkeTafelhoehe();
}

function zeigeMerkmale(merkmale, animiert = true) {
  const punkte = merkmale.flatMap((f) => f.geometry.coordinates.flatMap((p) => alsLatLng(p[0])));
  basis.karte.fitBounds(L.latLngBounds(punkte), {
    paddingTopLeft: [40, 110],
    paddingBottomRight: [40, tafel.offsetHeight + 30],
    maxZoom: 20,
    animate: animiert,
  });
}

// ----- Suche nach Flurstücksnummer -----

let letzteSuche = '';
let trefferNr = 0;

document.getElementById('suche').addEventListener('submit', (ereignis) => {
  ereignis.preventDefault();
  const feld = document.getElementById('suchtext');
  const text = feld.value.replace(/\s+/g, '').toLowerCase();
  if (!text || !sammlung) return;
  let treffer = sammlung.features.filter((f) => f.properties.nr.toLowerCase() === text);
  if (!treffer.length) treffer = sammlung.features.filter((f) => f.properties.nr.toLowerCase().startsWith(text));
  if (!treffer.length) {
    meldung(`Kein Flurstück „${feld.value.trim()}“ in Feggendorf gefunden.`, { oben: true });
    return;
  }
  trefferNr = text === letzteSuche ? (trefferNr + 1) % treffer.length : 0;
  letzteSuche = text;
  const f = treffer[trefferNr];
  zeigeMerkmale([f]);
  blinke(f);
  feld.blur();
  if (treffer.length > 1) {
    meldung(`Treffer ${trefferNr + 1} von ${treffer.length}: ${f.properties.nr} in Flur ${f.properties.flur}. Noch einmal suchen zeigt den nächsten.`, { oben: true });
  }
});

function blinke(merkmal) {
  const ring = L.polygon(merkmal.geometry.coordinates.map((p) => alsLatLng(p[0])), {
    color: '#ffffff',
    weight: 5,
    fill: false,
    interactive: false,
  }).addTo(basis.karte);
  setTimeout(() => ring.remove(), 1600);
}

// ----- Eigener Standort (braucht HTTPS) -----

function richteStandortEin() {
  const knopf = document.getElementById('standort');
  if (!window.isSecureContext || !navigator.geolocation) return;
  knopf.hidden = false;
  let punkt = null;
  knopf.addEventListener('click', () => {
    knopf.classList.add('ist-an');
    navigator.geolocation.getCurrentPosition(
      (ort) => {
        knopf.classList.remove('ist-an');
        const stelle = L.latLng(ort.coords.latitude, ort.coords.longitude);
        if (!basis.gebiet.contains(stelle)) {
          meldung('Du bist gerade nicht in Feggendorf.', { oben: true });
          return;
        }
        punkt?.remove();
        punkt = L.marker(stelle, {
          interactive: false,
          icon: L.divIcon({ className: 'ich-bin-hier', iconSize: [18, 18] }),
        }).addTo(basis.karte);
        basis.karte.setView(stelle, 19);
      },
      () => {
        knopf.classList.remove('ist-an');
        meldung('Dein Standort ist gerade nicht verfügbar.', { oben: true });
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 5000 },
    );
  });
}

// ----- Speichern -----

speichern.addEventListener('click', async () => {
  speichern.classList.add('laedt');
  try {
    const antwort = await api(form.dataset.methode, form.dataset.ziel, {
      name: nameFeld.value,
      adresse: adresseFeld.value,
      flurstuecke: [...gewaehlt.keys()],
    });
    location.href = antwort.weiter;
  } catch (fehler) {
    speichern.classList.remove('laedt');
    meldung(fehler.message, { fehler: true, oben: true });
  }
});
