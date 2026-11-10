// Service Worker: macht die App installierbar und zeigt ohne Netz eine verständliche Seite.
// Gartendaten werden hier nicht gespeichert. Nur die Hülle der App, die Luftbildkacheln und Fotos.

const HUELLE = 'garten-huelle-2';
const KACHELN = 'garten-kacheln-1';
const FOTOS = 'garten-fotos-1';
const OHNE_NETZ = '/offline';

self.addEventListener('install', (ereignis) => {
  ereignis.waitUntil(
    caches
      .open(HUELLE)
      .then((speicher) => speicher.addAll([OHNE_NETZ, '/static/app.css', '/static/icons/icon.svg']))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (ereignis) => {
  const behalten = [HUELLE, KACHELN, FOTOS];
  ereignis.waitUntil(
    caches
      .keys()
      .then((namen) => Promise.all(namen.filter((n) => !behalten.includes(n)).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

// Was sich nie ändert, wird einmal geholt und bleibt dann auf dem Handy.
function ausSpeicher(name, anfrage) {
  return caches.open(name).then(async (speicher) => {
    const treffer = await speicher.match(anfrage);
    if (treffer) return treffer;
    const antwort = await fetch(anfrage);
    if (antwort.status === 200) speicher.put(anfrage, antwort.clone());
    return antwort;
  });
}

self.addEventListener('fetch', (ereignis) => {
  const anfrage = ereignis.request;
  const adresse = new URL(anfrage.url);
  if (anfrage.method !== 'GET' || adresse.origin !== self.location.origin) return;

  if (adresse.pathname.startsWith('/kacheln/')) {
    ereignis.respondWith(ausSpeicher(KACHELN, anfrage));
    return;
  }

  // Fotos, aber keine Videos: die werden in Stücken abgerufen und wären zu groß.
  if (adresse.pathname.startsWith('/medien/') && adresse.pathname.endsWith('.jpg') && !anfrage.headers.has('range')) {
    ereignis.respondWith(ausSpeicher(FOTOS, anfrage));
    return;
  }

  if (adresse.pathname.startsWith('/static/')) {
    // Immer die neueste Fassung holen, ohne Netz die zuletzt gesehene nehmen.
    ereignis.respondWith(
      fetch(anfrage)
        .then((antwort) => {
          if (antwort.ok) {
            const kopie = antwort.clone();
            caches.open(HUELLE).then((speicher) => speicher.put(anfrage, kopie));
          }
          return antwort;
        })
        .catch(() => caches.match(anfrage).then((treffer) => treffer ?? Response.error())),
    );
    return;
  }

  if (anfrage.mode === 'navigate') {
    ereignis.respondWith(fetch(anfrage).catch(() => caches.match(OHNE_NETZ)));
  }
});
