/* global L */
// Gemeinsame Grundlage für alle Karten: Luftbild, Straßenkarte, Flurstücke.

import { meldung } from './werkzeug.js';

const MERKER_GRUND = 'garten.kartengrund';
const ZOOM_NUMMERN = 18; // ab hier stehen die Flurstücksnummern auf der Karte

function gemerkt(schluessel) {
  try {
    return localStorage.getItem(schluessel);
  } catch {
    return null;
  }
}

function merke(schluessel, wert) {
  try {
    localStorage.setItem(schluessel, wert);
  } catch {
    // Privater Modus: dann eben ohne Merken.
  }
}

/** GeoJSON schreibt Länge vor Breite, Leaflet will es umgekehrt. */
export function alsLatLng(ring) {
  return ring.map(([lon, lat]) => [lat, lon]);
}

export function erstelleKarte(element, daten) {
  const [west, sued, ost, nord] = daten.gebiet;
  const gebiet = L.latLngBounds([sued, west], [nord, ost]);

  const karte = L.map(element, {
    zoomControl: false,
    minZoom: 13,
    maxZoom: 22,
    zoomSnap: 0.5,
    maxBounds: gebiet.pad(0.25),
    maxBoundsViscosity: 0.9,
    attributionControl: false,
  });
  L.control.attribution({ position: 'bottomleft', prefix: false }).addTo(karte);

  const gruende = {
    luftbild: L.tileLayer(daten.luftbild, {
      minZoom: 13,
      maxNativeZoom: 20,
      maxZoom: 22,
      attribution: daten.quellen.luftbild,
    }),
    strasse: L.tileLayer(daten.strasse, {
      maxNativeZoom: 19,
      maxZoom: 22,
      attribution: daten.quellen.strasse,
    }),
  };

  let aktiv = null;
  const hoerer = [];

  function setzeGrund(name, merken = true) {
    if (!gruende[name] || name === aktiv) return;
    if (aktiv) karte.removeLayer(gruende[aktiv]);
    aktiv = name;
    gruende[name].addTo(karte).bringToBack();
    if (merken) merke(MERKER_GRUND, name);
    hoerer.forEach((f) => f(name));
  }

  // Fällt das Luftbild aus, zeigt die Karte von selbst die Straßenkarte.
  let geladen = 0;
  let fehler = 0;
  gruende.luftbild.on('tileload', () => {
    geladen += 1;
  });
  gruende.luftbild.on('tileerror', () => {
    fehler += 1;
    if (aktiv === 'luftbild' && geladen === 0 && fehler === 4) {
      setzeGrund('strasse', false);
      meldung('Das Luftbild ist gerade nicht erreichbar. Du siehst die Straßenkarte.', { oben: true });
    }
  });

  setzeGrund(gemerkt(MERKER_GRUND) === 'strasse' ? 'strasse' : 'luftbild', false);

  let flurstuecke = null;
  async function holeFlurstuecke() {
    if (!flurstuecke) {
      const antwort = await fetch(daten.flurstuecke, { credentials: 'same-origin' });
      if (!antwort.ok) throw new Error('Die Flurstücke konnten nicht geladen werden.');
      flurstuecke = await antwort.json();
      for (const f of flurstuecke.features) f.mitte = mitte(f);
    }
    return flurstuecke;
  }

  return {
    karte,
    gebiet,
    grund: () => aktiv,
    setzeGrund,
    beiGrundwechsel: (f) => hoerer.push(f),
    holeFlurstuecke,
  };
}

function mitte(merkmal) {
  const ring = merkmal.geometry.coordinates[0][0];
  let x = 0;
  let y = 0;
  for (const [lon, lat] of ring) {
    x += lon;
    y += lat;
  }
  return [y / ring.length, x / ring.length];
}

/** Schreibt die Nummern der sichtbaren Flurstücke auf die Karte, sobald man nah genug dran ist. */
export function beschrifte(karte, merkmale) {
  const schicht = L.layerGroup().addTo(karte);
  function zeichne() {
    schicht.clearLayers();
    if (karte.getZoom() < ZOOM_NUMMERN) return;
    const sicht = karte.getBounds();
    let anzahl = 0;
    for (const f of merkmale) {
      if (!sicht.contains(f.mitte)) continue;
      if ((anzahl += 1) > 120) break;
      L.marker(f.mitte, {
        interactive: false,
        keyboard: false,
        icon: L.divIcon({ className: '', iconSize: [0, 0], html: `<span class="flur-nr">${f.properties.nr}</span>` }),
      }).addTo(schicht);
    }
  }
  karte.on('moveend', zeichne);
  zeichne();
  return {
    entferne() {
      karte.off('moveend', zeichne);
      schicht.remove();
    },
  };
}
