// Läuft auf jeder Seite. Meldet den Service Worker an, damit sich die App
// installieren lässt und ohne Netz eine verständliche Seite zeigt.

if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.register('/sw.js').catch(() => {
    // Ohne Service Worker läuft die App normal weiter.
  });
}
