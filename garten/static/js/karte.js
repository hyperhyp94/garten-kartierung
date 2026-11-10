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
blatt.addEventListener('click', (ereignis) => {
  // Ein Tipp neben das Blatt schließt es. Ein Tipp zwischen zwei Knöpfen im Blatt nicht.
  if (ereignis.target !== blatt) return;
  const rahmen = blatt.getBoundingClientRect();
  if (ereignis.clientY < rahmen.top || ereignis.clientX < rahmen.left || ereignis.clientX > rahmen.right) {
    blatt.close();
  }
});

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
