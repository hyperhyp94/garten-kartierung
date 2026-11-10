/* global L */
// Die Karte des Gartens: Grenze, gemerkter Ausschnitt, Kartengrund und Flurstücke.

import { alsLatLng, beschrifte, erstelleKarte } from './karte-basis.js';
import { api, meldung, seitenDaten } from './werkzeug.js';

const MERKER_FLUR = 'garten.flurstuecke';
const daten = seitenDaten();
const garten = daten.garten;
const { karte, grund, setzeGrund, beiGrundwechsel, holeFlurstuecke } = erstelleKarte('karte', daten);

// ----- Grenze: alles außerhalb wird leicht abgedunkelt, der Rand leuchtet -----

const flaechen = garten.grenze.coordinates.map((polygon) => alsLatLng(polygon[0]));
const welt = [
  [-85, -180],
  [-85, 180],
  [85, 180],
  [85, -180],
];
const umfeld = L.polygon([welt, ...flaechen], {
  stroke: false,
  fillColor: '#0c1810',
  interactive: false,
}).addTo(karte);

// Auf dem dunklen Luftbild darf das Umfeld stärker zurücktreten als auf der hellen Straßenkarte.
function passeAnGrundAn(name) {
  umfeld.setStyle({ fillOpacity: name === 'luftbild' ? 0.4 : 0.16 });
  flurEbene?.setStyle(flurStil(name));
}

// Gibt es eine eigene Fläche, bleiben die Flurstücke als dünne Linie zur Orientierung sichtbar.
L.polyline(garten.umriss_flurstuecke.map(alsLatLng), { color: '#ffffff', weight: 1.5, dashArray: '5 6', opacity: 0.8, interactive: false }).addTo(karte);
const rand = garten.umriss.map(alsLatLng);
L.polyline(rand, { color: '#ffffff', weight: 7, opacity: 0.95, lineCap: 'round', interactive: false }).addTo(karte);
L.polyline(rand, { color: '#f2b705', weight: 3.5, lineCap: 'round', interactive: false }).addTo(karte);

// ----- Ausschnitt: gemerkte Ansicht oder der ganze Garten -----

const grenzen = L.latLngBounds(flaechen.flat());
let ansicht = garten.ansicht;

function zeigeGarten(animiert) {
  if (ansicht) {
    karte.setView([ansicht.lat, ansicht.lon], ansicht.zoom, { animate: animiert });
  } else {
    karte.fitBounds(grenzen, {
      paddingTopLeft: [28, 96],
      paddingBottomRight: [28, 36],
      maxZoom: 21,
      animate: animiert,
    });
  }
}

zeigeGarten(false);
document.getElementById('zum-garten').addEventListener('click', () => zeigeGarten(true));

// ----- Blatt „Karte“ -----

const blatt = document.getElementById('ebenen');
const flurSchalter = document.getElementById('flur-schalter');
const ansichtText = document.getElementById('ansicht-text');
const zurueckKnopf = document.getElementById('ansicht-zurueck');

document.getElementById('ebenen-knopf').addEventListener('click', () => blatt.showModal());

function zeigeGrundwahl(name) {
  for (const feld of blatt.querySelectorAll('input[name="grund"]')) feld.checked = feld.value === name;
}
zeigeGrundwahl(grund());
beiGrundwechsel(zeigeGrundwahl);
beiGrundwechsel(passeAnGrundAn);
blatt.addEventListener('change', (ereignis) => {
  if (ereignis.target.name === 'grund') setzeGrund(ereignis.target.value);
});

function zeigeAnsichtStand() {
  ansichtText.textContent = ansicht
    ? 'Beim Öffnen zeigt die Karte den gemerkten Ausschnitt.'
    : 'Beim Öffnen zeigt die Karte den ganzen Garten.';
  zurueckKnopf.hidden = !ansicht;
}
zeigeAnsichtStand();

document.getElementById('ansicht-merken').addEventListener('click', async (ereignis) => {
  const knopf = ereignis.currentTarget;
  const mitte = karte.getCenter();
  knopf.classList.add('laedt');
  try {
    const antwort = await api('PUT', `/api/gaerten/${garten.id}/ansicht`, {
      lat: mitte.lat,
      lon: mitte.lng,
      zoom: karte.getZoom(),
    });
    ansicht = antwort.ansicht;
    zeigeAnsichtStand();
    meldung('Gemerkt. So öffnet sich die Karte ab jetzt.');
  } catch (fehler) {
    meldung(fehler.message, { fehler: true });
  } finally {
    knopf.classList.remove('laedt');
  }
});

zurueckKnopf.addEventListener('click', async () => {
  try {
    await api('DELETE', `/api/gaerten/${garten.id}/ansicht`);
    ansicht = null;
    zeigeAnsichtStand();
    zeigeGarten(true);
    blatt.close();
  } catch (fehler) {
    meldung(fehler.message, { fehler: true });
  }
});

// ----- Flurstücke als zuschaltbare Ebene -----

let flurEbene = null;
let flurNummern = null;

function flurStil(name) {
  return { color: name === 'luftbild' ? '#ffffff' : '#34443a', weight: 1.2, opacity: 0.85, fill: false };
}

async function zeigeFlurstuecke(an) {
  if (!an) {
    flurEbene?.remove();
    flurNummern?.entferne();
    flurEbene = flurNummern = null;
    return;
  }
  try {
    const sammlung = await holeFlurstuecke();
    if (!flurSchalter.checked || flurEbene) return;
    flurEbene = L.geoJSON(sammlung, {
      renderer: L.canvas({ padding: 0.3 }),
      interactive: false,
      style: flurStil(grund()),
    }).addTo(karte);
    flurNummern = beschrifte(karte, sammlung.features);
  } catch (fehler) {
    flurSchalter.checked = false;
    meldung(fehler.message, { fehler: true });
  }
}

flurSchalter.addEventListener('change', () => {
  try {
    localStorage.setItem(MERKER_FLUR, flurSchalter.checked ? '1' : '0');
  } catch {
    // ohne Merken
  }
  zeigeFlurstuecke(flurSchalter.checked);
});

try {
  flurSchalter.checked = localStorage.getItem(MERKER_FLUR) === '1';
} catch {
  flurSchalter.checked = false;
}
if (flurSchalter.checked) zeigeFlurstuecke(true);
passeAnGrundAn(grund());

// ----- Bestand: Pflanzen und Objekte in der Farbe ihres Zustands -----

const FARBEN = { 0: '#8a938c', 1: '#b3261e', 2: '#e0701a', 3: '#e0b400', 4: '#7cb342', 5: '#2e7d32' };
const bestandEbene = L.layerGroup().addTo(karte);
const aufgabenSchalter = document.getElementById('aufgaben-schalter');
const zettel = document.getElementById('zettel');
const formen = new Map(); // id -> Form auf der Karte

function zeichneBestand() {
  bestandEbene.clearLayers();
  formen.clear();
  for (const b of daten.bestand) {
    if (aufgabenSchalter.checked && !b.offen) continue;
    const farbe = FARBEN[b.zustand ?? 0];
    let form;
    if (b.form === 'linie') {
      const zug = alsLatLng(b.geometrie.coordinates);
      L.polyline(zug, { color: '#ffffff', weight: 8, opacity: 0.9, interactive: false }).addTo(bestandEbene);
      form = L.polyline(zug, { color: farbe, weight: 5 });
    } else if (b.form === 'flaeche') {
      form = L.polygon(alsLatLng(b.geometrie.coordinates[0]), { color: farbe, weight: 3, fillColor: farbe, fillOpacity: 0.3 });
    } else if (b.art === 'objekt') {
      form = L.marker([b.lat, b.lon], {
        keyboard: false,
        icon: L.divIcon({ className: 'objekt-marke', iconSize: [22, 22], html: `<span style="background:${farbe}"></span>` }),
      });
    } else {
      form = L.circleMarker([b.lat, b.lon], { radius: 11, color: '#ffffff', weight: 3, fillColor: farbe, fillOpacity: 1 });
    }
    form.on('click', (ereignis) => {
      L.DomEvent.stopPropagation(ereignis);
      zeigeZettel(b);
    });
    form.addTo(bestandEbene);
    formen.set(b.id, form);
  }
}

function zeigeZettel(b) {
  zettel.href = b.adresse;
  document.getElementById('zettel-name').textContent = b.name;
  const teile = [b.kategorie];
  if (b.offen) teile.push(b.offen === 1 ? '1 Aufgabe' : `${b.offen} Aufgaben`);
  document.getElementById('zettel-text').textContent = teile.join(' · ');
  const marke = document.getElementById('zettel-zustand');
  marke.className = `zustand z${b.zustand ?? 0}`;
  marke.textContent = b.zustand ?? '?';
  const bild = document.getElementById('zettel-bild');
  bild.replaceChildren();
  if (b.bild) {
    const img = document.createElement('img');
    img.src = b.bild;
    img.alt = '';
    bild.append(img);
  }
  zettel.hidden = false;
}

karte.on('click', () => {
  zettel.hidden = true;
});
aufgabenSchalter.addEventListener('change', () => {
  zettel.hidden = true;
  zeichneBestand();
});
zeichneBestand();

// Von einer Pflanze aus: „Auf der Karte zeigen“.
const zeige = Number(new URLSearchParams(location.search).get('zeige'));
const gesucht = daten.bestand.find((b) => b.id === zeige);
if (gesucht) {
  const form = formen.get(gesucht.id);
  if (form?.getBounds) karte.fitBounds(form.getBounds(), { padding: [60, 120], maxZoom: 21, animate: false });
  else karte.setView([gesucht.lat, gesucht.lon], 21, { animate: false });
  zeigeZettel(gesucht);
}

// „Neue Pflanze“ aus dem Plus-Blatt beginnt an der Stelle, die die Karte gerade zeigt.
document.addEventListener('click', (ereignis) => {
  if (!ereignis.target.closest('[data-oeffnet="plus-blatt"]')) return;
  const mitte = karte.getCenter();
  for (const verweis of document.querySelectorAll('#plus-blatt [data-mit-ort]')) {
    const adresse = new URL(verweis.href);
    adresse.searchParams.set('lat', mitte.lat.toFixed(7));
    adresse.searchParams.set('lon', mitte.lng.toFixed(7));
    adresse.searchParams.set('zoom', Math.max(karte.getZoom(), 20));
    verweis.href = adresse;
  }
});

// ----- Eigener Standort (braucht HTTPS) -----

const ortKnopf = document.getElementById('standort');
if (window.isSecureContext && navigator.geolocation) {
  ortKnopf.hidden = false;
  let beobachtung = null;
  let punkt = null;
  let kreis = null;
  let zentriert = false;
  const stoppe = () => {
    navigator.geolocation.clearWatch(beobachtung);
    beobachtung = null;
    punkt?.remove();
    kreis?.remove();
    punkt = kreis = null;
    ortKnopf.classList.remove('ist-an');
  };
  ortKnopf.addEventListener('click', () => {
    if (beobachtung !== null) {
      stoppe();
      return;
    }
    zentriert = false;
    ortKnopf.classList.add('ist-an');
    beobachtung = navigator.geolocation.watchPosition(
      (ort) => {
        const stelle = [ort.coords.latitude, ort.coords.longitude];
        punkt?.remove();
        kreis?.remove();
        kreis = L.circle(stelle, { radius: ort.coords.accuracy, color: '#1a73e8', weight: 1, fillOpacity: 0.12, interactive: false }).addTo(karte);
        punkt = L.marker(stelle, { interactive: false, icon: L.divIcon({ className: 'ich-bin-hier', iconSize: [18, 18] }) }).addTo(karte);
        if (!zentriert) {
          zentriert = true;
          karte.setView(stelle, Math.max(karte.getZoom(), 19));
          meldung(`Dein Standort, auf etwa ${Math.round(ort.coords.accuracy)} m genau.`);
        }
      },
      () => {
        stoppe();
        meldung('Dein Standort ist gerade nicht verfügbar.', { fehler: true });
      },
      { enableHighAccuracy: true, maximumAge: 2000 },
    );
  });
}
