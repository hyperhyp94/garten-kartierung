// Fotos und Videos in Formularen: aufnehmen, verkleinern, kennzeichnen. Dazu das Zeichnen ins Bild.

import { abschicken, alsJpeg, ladeBild, meldung, verkleinere } from './werkzeug.js';

const MAX_VIDEO = 200 * 1024 * 1024;
const MARKEN = ['', 'vorher', 'nachher'];
const felder = new Map(); // Formular -> Funktion, die ein fertiges Bild hinzufügt

export function richteFotoFelderEin() {
  for (const feld of document.querySelectorAll('[data-foto-feld]')) richteEin(feld);
  for (const knopf of document.querySelectorAll('[data-zeichnen]')) {
    knopf.addEventListener('click', async () => {
      const bild = await zeichneInsBild(knopf.dataset.zeichnen);
      if (bild) felder.get(knopf.closest('form'))?.(bild);
    });
  }
}

function richteEin(feld) {
  const form = feld.closest('form');
  const liste = feld.querySelector('[data-liste]');
  const mitMarke = feld.hasAttribute('data-kennzeichen');
  // Beim Erledigen einer Aufgabe ist ein neues Foto ein Nachher-Foto.
  const startMarke = mitMarke && form.querySelector('[name="aufgabe_id"]') ? 'nachher' : '';
  const bilder = []; // { bild, vorschau, adresse, marke }
  const videos = [];

  function zeichne() {
    liste.hidden = bilder.length + videos.length === 0;
    liste.replaceChildren(
      ...bilder.map((b, nr) => {
        const punkt = document.createElement('li');
        const img = document.createElement('img');
        img.src = b.adresse;
        img.alt = `Foto ${nr + 1}`;
        punkt.append(img);
        if (mitMarke) {
          const marke = document.createElement('button');
          marke.type = 'button';
          marke.className = `foto-marke${b.marke ? ' ist-an' : ''}`;
          marke.textContent = b.marke || 'ohne';
          marke.setAttribute('aria-label', `Kennzeichen: ${b.marke || 'ohne'}. Tippen zum Wechseln.`);
          marke.addEventListener('click', () => {
            b.marke = MARKEN[(MARKEN.indexOf(b.marke) + 1) % MARKEN.length];
            zeichne();
          });
          punkt.append(marke);
        }
        punkt.append(wegKnopf(() => {
          URL.revokeObjectURL(b.adresse);
          bilder.splice(nr, 1);
          zeichne();
        }));
        return punkt;
      }),
      ...videos.map((v, nr) => {
        const punkt = document.createElement('li');
        punkt.className = 'ist-video';
        punkt.textContent = `Video · ${Math.round(v.size / 1024 / 1024)} MB`;
        punkt.append(wegKnopf(() => {
          videos.splice(nr, 1);
          zeichne();
        }));
        return punkt;
      }),
    );
  }

  function nimm(bild, vorschau, marke = startMarke) {
    bilder.push({ bild, vorschau, adresse: URL.createObjectURL(vorschau), marke });
    zeichne();
  }

  feld.addEventListener('change', async (ereignis) => {
    const eingabe = ereignis.target;
    if (!eingabe.files?.length) return;
    if (eingabe.matches('[data-bilder]')) {
      feld.classList.add('laedt');
      for (const datei of eingabe.files) {
        try {
          const { bild, vorschau } = await verkleinere(datei);
          nimm(bild, vorschau);
        } catch (fehler) {
          meldung(fehler.message, { fehler: true });
        }
      }
      feld.classList.remove('laedt');
      // Ein Vorher-Foto wird sofort gespeichert, ohne weiteren Tipper.
      if (form.hasAttribute('data-sofort') && bilder.length) abschicken(form);
    } else if (eingabe.matches('[data-video]')) {
      const datei = eingabe.files[0];
      if (datei.size > MAX_VIDEO) meldung('Das Video ist größer als 200 MB.', { fehler: true });
      else {
        videos.push(datei);
        zeichne();
      }
    }
    eingabe.value = '';
  });

  form.addEventListener('sammeln', (ereignis) => {
    const daten = ereignis.detail;
    for (const b of bilder) {
      daten.append('bild', b.bild, 'foto.jpg');
      daten.append('vorschau', b.vorschau, 'vorschau.jpg');
      daten.append('kennzeichen', b.marke);
    }
    for (const v of videos) daten.append('video', v, v.name);
  });

  felder.set(form, async (blob) => {
    const adresse = URL.createObjectURL(blob);
    try {
      nimm(blob, await alsJpeg(await ladeBild(adresse), 480, 0.75), '');
    } finally {
      URL.revokeObjectURL(adresse);
    }
  });
  zeichne();
}

function wegKnopf(tun) {
  const knopf = document.createElement('button');
  knopf.type = 'button';
  knopf.className = 'foto-weg';
  knopf.setAttribute('aria-label', 'Entfernen');
  knopf.innerHTML = '<svg class="symbol" aria-hidden="true"><use href="#s-x"/></svg>';
  knopf.addEventListener('click', tun);
  return knopf;
}

/** Öffnet ein Foto zum Hineinzeichnen. Gibt das fertige Bild zurück oder null bei Abbruch. */
export async function zeichneInsBild(adresse) {
  let bild;
  try {
    bild = await ladeBild(adresse);
  } catch {
    meldung('Das Foto konnte nicht geladen werden.', { fehler: true });
    return null;
  }
  const fenster = document.createElement('dialog');
  fenster.className = 'zeichnen';
  fenster.setAttribute('aria-label', 'Ins Bild zeichnen');
  fenster.innerHTML = `
    <canvas></canvas>
    <div class="zeichnen-leiste">
      <button type="button" class="farbe ist-an" data-farbe="#ff3b30" aria-label="Rot"></button>
      <button type="button" class="farbe" data-farbe="#ffd60a" aria-label="Gelb"></button>
      <button type="button" class="knopf ist-klein" data-tun="zurueck">Zurück</button>
      <button type="button" class="knopf ist-klein" data-tun="abbrechen">Abbrechen</button>
      <button type="button" class="knopf ist-klein ist-haupt" data-tun="fertig">Übernehmen</button>
    </div>`;
  document.body.append(fenster);

  const flaeche = fenster.querySelector('canvas');
  const faktor = Math.min(1, 1600 / Math.max(bild.naturalWidth, bild.naturalHeight));
  flaeche.width = Math.round(bild.naturalWidth * faktor);
  flaeche.height = Math.round(bild.naturalHeight * faktor);
  const stift = flaeche.getContext('2d');
  const dicke = Math.max(6, flaeche.width / 110);
  const striche = [];
  let farbe = '#ff3b30';
  let aktiv = null;

  function male() {
    stift.drawImage(bild, 0, 0, flaeche.width, flaeche.height);
    stift.lineCap = stift.lineJoin = 'round';
    for (const strich of striche) {
      // Weißer Rand, damit die Linie auf jedem Untergrund zu sehen ist.
      for (const [breite, ton] of [[dicke * 1.7, '#ffffff'], [dicke, strich.farbe]]) {
        stift.lineWidth = breite;
        stift.strokeStyle = ton;
        stift.beginPath();
        strich.punkte.forEach(([x, y], nr) => (nr ? stift.lineTo(x, y) : stift.moveTo(x, y)));
        if (strich.punkte.length === 1) stift.lineTo(strich.punkte[0][0] + 0.1, strich.punkte[0][1]);
        stift.stroke();
      }
    }
  }
  const stelle = (e) => {
    const rahmen = flaeche.getBoundingClientRect();
    return [((e.clientX - rahmen.left) * flaeche.width) / rahmen.width, ((e.clientY - rahmen.top) * flaeche.height) / rahmen.height];
  };
  flaeche.addEventListener('pointerdown', (e) => {
    flaeche.setPointerCapture(e.pointerId);
    aktiv = { farbe, punkte: [stelle(e)] };
    striche.push(aktiv);
    male();
  });
  flaeche.addEventListener('pointermove', (e) => {
    if (!aktiv) return;
    aktiv.punkte.push(stelle(e));
    male();
  });
  for (const art of ['pointerup', 'pointercancel']) flaeche.addEventListener(art, () => (aktiv = null));
  male();
  fenster.showModal();

  return new Promise((fertig) => {
    const schliesse = (ergebnis) => {
      fenster.close();
      fenster.remove();
      fertig(ergebnis);
    };
    fenster.addEventListener('cancel', (e) => {
      e.preventDefault();
      schliesse(null);
    });
    fenster.addEventListener('click', (e) => {
      const farbKnopf = e.target.closest('[data-farbe]');
      if (farbKnopf) {
        farbe = farbKnopf.dataset.farbe;
        for (const k of fenster.querySelectorAll('[data-farbe]')) k.classList.toggle('ist-an', k === farbKnopf);
        return;
      }
      const tun = e.target.closest('[data-tun]')?.dataset.tun;
      if (tun === 'zurueck') {
        striche.pop();
        male();
      } else if (tun === 'abbrechen') {
        schliesse(null);
      } else if (tun === 'fertig') {
        if (!striche.length) {
          meldung('Zeichne zuerst etwas ins Bild.', { oben: true });
          return;
        }
        flaeche.toBlob((blob) => schliesse(blob), 'image/jpeg', 0.88);
      }
    });
  });
}
