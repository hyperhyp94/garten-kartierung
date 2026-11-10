/* global L */
// Karte mit Fadenkreuz. Damit legt man einen Punkt, eine Linie oder eine Fläche fest:
// Karte unter das Kreuz schieben, „Punkt setzen“ tippen. Flächen lassen sich auch mit GPS abgehen.

import { alsLatLng, erstelleKarte } from './karte-basis.js';
import { flaeche as alsFlaeche, meldung, strecke } from './werkzeug.js';

const ERDRADIUS = 6371008.8;
const GENAU_GENUG = 20; // Meter. Ungenauere GPS-Punkte werden beim Abgehen verworfen.
const SCHRITT = 3; // Meter zwischen zwei aufgezeichneten Punkten

const bogen = (grad) => (grad * Math.PI) / 180;

/** Entfernung zweier Punkte [Breite, Länge] in Metern. */
export function abstand(a, b) {
  const h =
    Math.sin(bogen(b[0] - a[0]) / 2) ** 2 +
    Math.cos(bogen(a[0])) * Math.cos(bogen(b[0])) * Math.sin(bogen(b[1] - a[1]) / 2) ** 2;
  return 2 * ERDRADIUS * Math.asin(Math.sqrt(h));
}

export function laenge(punkte) {
  let summe = 0;
  for (let i = 1; i < punkte.length; i += 1) summe += abstand(punkte[i - 1], punkte[i]);
  return summe;
}

export function flaecheVon(punkte) {
  const breite0 = bogen(punkte.reduce((s, p) => s + p[0], 0) / punkte.length);
  const eben = punkte.map((p) => [ERDRADIUS * bogen(p[1]) * Math.cos(breite0), ERDRADIUS * bogen(p[0])]);
  let summe = 0;
  for (let i = 0; i < eben.length; i += 1) {
    const [x1, y1] = eben[i];
    const [x2, y2] = eben[(i + 1) % eben.length];
    summe += x1 * y2 - x2 * y1;
  }
  return Math.abs(summe) / 2;
}

/** form: 'punkt', 'linie', 'flaeche' oder 'messen' (nichts wird gespeichert). */
export function erstelleEditor(daten, { form = 'punkt' } = {}) {
  const wurzel = document.getElementById('editor');
  const teil = (name) => wurzel.querySelector(`[data-editor="${name}"]`);
  const basis = erstelleKarte('editor-karte', daten);
  const { karte, gebiet } = basis;
  let punkte = []; // [Breite, Länge]

  if (daten.garten?.umriss?.length) {
    L.polyline(daten.garten.umriss.map(alsLatLng), { color: '#f2b705', weight: 2.5, interactive: false }).addTo(karte);
  }
  const fuellung = L.polygon([], { stroke: false, fillColor: '#ff5a36', fillOpacity: 0.28, interactive: false }).addTo(karte);
  const rand = L.polyline([], { color: '#ffffff', weight: 6, interactive: false }).addTo(karte);
  const strich = L.polyline([], { color: '#ff5a36', weight: 3.5, interactive: false }).addTo(karte);
  const gummi = L.polyline([], { color: '#ffffff', weight: 2, dashArray: '6 7', interactive: false }).addTo(karte);
  const ecken = L.layerGroup().addTo(karte);

  // ----- Startansicht -----
  const g = daten.geometrie;
  if (g?.type === 'Point') {
    karte.setView([g.coordinates[1], g.coordinates[0]], 21, { animate: false });
  } else if (g) {
    punkte = alsLatLng(g.type === 'Polygon' ? g.coordinates[0].slice(0, -1) : g.coordinates);
    karte.fitBounds(L.latLngBounds(punkte), { padding: [36, 36], maxZoom: 21, animate: false });
  } else if (daten.start) {
    karte.setView([daten.start.lat, daten.start.lon], daten.start.zoom, { animate: false });
  } else if (daten.garten?.ansicht) {
    karte.setView([daten.garten.ansicht.lat, daten.garten.ansicht.lon], daten.garten.ansicht.zoom, { animate: false });
  } else if (daten.garten?.grenze) {
    const alle = daten.garten.grenze.coordinates.flatMap((p) => alsLatLng(p[0]));
    karte.fitBounds(L.latLngBounds(alle), { padding: [16, 16], maxZoom: 21, animate: false });
  } else {
    karte.fitBounds(gebiet);
  }

  // ----- Zeichnen -----
  let genauigkeit = null;

  function zeichne() {
    const geschlossen = form === 'flaeche' && punkte.length >= 3;
    fuellung.setLatLngs(geschlossen || (form === 'messen' && punkte.length >= 3) ? punkte : []);
    const zug = geschlossen ? [...punkte, punkte[0]] : punkte;
    rand.setLatLngs(form === 'punkt' ? [] : zug);
    strich.setLatLngs(form === 'punkt' ? [] : zug);
    ecken.clearLayers();
    if (form !== 'punkt') {
      for (const p of punkte) {
        L.circleMarker(p, { radius: 5, color: '#14281c', weight: 2, fillColor: '#ffffff', fillOpacity: 1, interactive: false }).addTo(ecken);
      }
    }
    zeichneGummi();
    teil('punkte').hidden = form === 'punkt';
    teil('zurueck').disabled = punkte.length === 0;
    teil('wert').textContent = wertText();
  }

  function zeichneGummi() {
    const mitte = karte.getCenter();
    gummi.setLatLngs(form !== 'punkt' && punkte.length && !aufzeichnung ? [punkte[punkte.length - 1], [mitte.lat, mitte.lng]] : []);
  }

  function wertText() {
    const gps = genauigkeit === null ? '' : ` · GPS auf ${Math.round(genauigkeit)} m genau`;
    if (form === 'punkt') return 'Schiebe die Karte, bis das Kreuz genau auf der Stelle liegt.';
    if (form === 'linie') {
      return punkte.length < 2 ? 'Setze mindestens zwei Punkte.' + gps : `Länge ${strecke(laenge(punkte))}${gps}`;
    }
    if (form === 'flaeche') {
      if (punkte.length < 3) return 'Setze mindestens drei Punkte.' + gps;
      return `Fläche ${alsFlaeche(flaecheVon(punkte))} · Umfang ${strecke(laenge([...punkte, punkte[0]]))}${gps}`;
    }
    if (punkte.length < 2) return 'Setze zwei Punkte, um einen Abstand zu messen.';
    const teile = [`Strecke ${strecke(laenge(punkte))}`];
    if (punkte.length >= 3) teile.push(`umschlossene Fläche ${alsFlaeche(flaecheVon(punkte))}`);
    return teile.join(' · ');
  }

  karte.on('move', zeichneGummi);

  teil('setzen').addEventListener('click', () => {
    const mitte = karte.getCenter();
    punkte.push([mitte.lat, mitte.lng]);
    zeichne();
  });
  teil('zurueck').addEventListener('click', () => {
    punkte.pop();
    zeichne();
  });
  teil('grund').addEventListener('click', () => basis.setzeGrund(basis.grund() === 'luftbild' ? 'strasse' : 'luftbild'));

  // ----- GPS (nur über HTTPS verfügbar) -----
  let aufzeichnung = null;
  let ichPunkt = null;

  function zeigeMich(stelle) {
    ichPunkt?.remove();
    ichPunkt = L.marker(stelle, { interactive: false, icon: L.divIcon({ className: 'ich-bin-hier', iconSize: [18, 18] }) }).addTo(karte);
  }

  if (window.isSecureContext && navigator.geolocation) {
    const ortKnopf = teil('standort');
    ortKnopf.hidden = false;
    ortKnopf.addEventListener('click', () => {
      ortKnopf.classList.add('ist-an');
      navigator.geolocation.getCurrentPosition(
        (ort) => {
          ortKnopf.classList.remove('ist-an');
          const stelle = [ort.coords.latitude, ort.coords.longitude];
          if (!gebiet.contains(stelle)) {
            meldung('Du bist gerade nicht in Feggendorf.');
            return;
          }
          zeigeMich(stelle);
          karte.setView(stelle, Math.max(karte.getZoom(), 20));
          meldung(`Standort auf etwa ${Math.round(ort.coords.accuracy)} m genau. Schiebe die Karte nach, bis es passt.`);
        },
        () => {
          ortKnopf.classList.remove('ist-an');
          meldung('Dein Standort ist gerade nicht verfügbar.', { fehler: true });
        },
        { enableHighAccuracy: true, timeout: 12000, maximumAge: 3000 },
      );
    });

    const gehKnopf = teil('abgehen');
    gehKnopf.hidden = false;
    gehKnopf.addEventListener('click', () => {
      if (aufzeichnung !== null) {
        navigator.geolocation.clearWatch(aufzeichnung);
        aufzeichnung = null;
        genauigkeit = null;
        gehKnopf.classList.remove('ist-haupt');
        gehKnopf.querySelector('span').textContent = 'Mit GPS abgehen';
        zeichne();
        return;
      }
      gehKnopf.classList.add('ist-haupt');
      gehKnopf.querySelector('span').textContent = 'Aufzeichnung beenden';
      meldung('Geh jetzt langsam die Grenze ab. Die App setzt die Punkte von selbst.');
      aufzeichnung = navigator.geolocation.watchPosition(
        (ort) => {
          const stelle = [ort.coords.latitude, ort.coords.longitude];
          genauigkeit = ort.coords.accuracy;
          zeigeMich(stelle);
          karte.panTo(stelle);
          const letzter = punkte[punkte.length - 1];
          if (genauigkeit <= GENAU_GENUG && gebiet.contains(stelle) && (!letzter || abstand(letzter, stelle) >= SCHRITT)) {
            punkte.push(stelle);
          }
          zeichne();
        },
        () => meldung('Das GPS-Signal ist gerade weg. Bleib kurz stehen.', { fehler: true }),
        { enableHighAccuracy: true, maximumAge: 1000 },
      );
      zeichne();
    });
  }

  zeichne();

  return {
    karte,
    anzahl: () => punkte.length,
    setzeForm(neu) {
      form = neu;
      zeichne();
    },
    /** Die festgelegte Lage als GeoJSON oder null, wenn noch Punkte fehlen. */
    geometrie() {
      const xy = punkte.map(([lat, lon]) => [lon, lat]);
      if (form === 'punkt') {
        const mitte = karte.getCenter();
        return { type: 'Point', coordinates: [mitte.lng, mitte.lat] };
      }
      if (form === 'linie') return xy.length >= 2 ? { type: 'LineString', coordinates: xy } : null;
      if (form === 'flaeche') return xy.length >= 3 ? { type: 'Polygon', coordinates: [[...xy, xy[0]]] } : null;
      return null;
    },
  };
}
