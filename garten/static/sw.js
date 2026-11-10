// Service Worker: macht die App installierbar und zeigt ohne Netz eine verständliche Seite.
// Gartendaten werden hier nicht gespeichert. Nur die Hülle der App und die Luftbildkacheln.

const HUELLE = 'garten-huelle-1';
const KACHELN = 'garten-kacheln-1';
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
  ereignis.waitUntil(
    caches
      .keys()
      .then((namen) => Promise.all(namen.filter((n) => n !== HUELLE && n !== KACHELN).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (ereignis) => {
  const anfrage = ereignis.request;
  const adresse = new URL(anfrage.url);
  if (anfrage.method !== 'GET' || adresse.origin !== self.location.origin) return;

  if (adresse.pathname.startsWith('/kacheln/')) {
    // Luftbild ändert sich nicht: einmal geladen, bleibt es auf dem Handy.
    ereignis.respondWith(
      caches.open(KACHELN).then(async (speicher) => {
        const treffer = await speicher.match(anfrage);
        if (treffer) return treffer;
        const antwort = await fetch(anfrage);
        if (antwort.ok) speicher.put(anfrage, antwort.clone());
        return antwort;
      }),
    );
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
