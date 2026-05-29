const CACHE_NAME = 'pyspotify-v1';
const ASSETS = [
  './',
  './index.html',
  './app.js'
];

// Instala o app no armazenamento interno do navegador do celular
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
  );
});

// Ativa o modo offline interceptando requisições de rede
self.addEventListener('fetch', (e) => {
  e.respondWith(
    caches.match(e.request).then((response) => response || fetch(e.request))
  );
});