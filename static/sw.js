const CACHE_NAME = 'matdata-mitra-v1';
const urlsToCache = [
  '/',
  '/static/index.html',
  '/static/manifest.json',
  'https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;700&family=Rajdhani:wght@500;600;700&display=swap',
  'https://cdn.jsdelivr.net/npm/chart.js',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(urlsToCache);
      })
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Cache hit - return response
        if (response) {
          return response;
        }
        return fetch(event.request).then(
          function(response) {
            // Check if we received a valid response
            if(!response || response.status !== 200 || response.type !== 'basic') {
              return response;
            }

            // IMPORTANT: Clone the response. A response is a stream
            // and because we want the browser to consume the response
            // as well as the cache consuming the response, we need
            // to clone it so we have two streams.
            var responseToCache = response.clone();

            caches.open(CACHE_NAME)
              .then(function(cache) {
                // Don't cache API calls aggressively here, maybe just static assets
                if (!event.request.url.includes('/api/')) {
                   cache.put(event.request, responseToCache);
                }
              });

            return response;
          }
        );
      }).catch(() => {
          // If fetch fails (offline), return cached index.html for navigation
          if (event.request.mode === 'navigate') {
              return caches.match('/static/index.html');
          }
      })
  );
});
