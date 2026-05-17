// static/js/serviceworker.js
var staticCacheName = "RoBosForx-pwa-v" + new Date().getTime() + "-v5";

// Files to cache - Only cache public, unauthenticated routes!
// Caching protected routes causes redirects, which Chrome rejects in cache.addAll()
var filesToCache = [
    '/',              // Root - your login page
    '/core/offline/', // Public offline page
    '/static/imgs/icons/icon-192x192.png',
    '/static/imgs/icons/icon-72x72.png'
];

// Install
self.addEventListener("install", event => {
    console.log('[ServiceWorker] Install');
    self.skipWaiting();
    event.waitUntil(
        caches.open(staticCacheName)
            .then(cache => {
                console.log('[ServiceWorker] Caching files');
                return cache.addAll(filesToCache);
            })
            .catch(err => console.log('Cache error:', err))
    );
});

// Activate
self.addEventListener('activate', event => {
    console.log('[ServiceWorker] Activate');
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.filter(cn => cn !== staticCacheName).map(cn => caches.delete(cn))
            );
        })
    );
    return self.clients.claim();
});

// Fetch event - bypass webpush
self.addEventListener("fetch", event => {
    const url = new URL(event.request.url);
    
    // CRITICAL: Never intercept webpush API calls
    if (url.pathname.startsWith('/webpush/')) {
        console.log('[ServiceWorker] Bypassing webpush:', url.pathname);
        return;
    }
    
    // Skip non-GET requests
    if (event.request.method !== 'GET') {
        return;
    }
    
    // For HTML navigation, try network first then cache
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request)
                .then(response => {
                    // Cache the page for offline
                    const responseClone = response.clone();
                    caches.open(staticCacheName).then(cache => {
                        cache.put(event.request, responseClone);
                    });
                    return response;
                })
                .catch(async () => {
                    const cachedResponse = await caches.match(event.request);
                    if (cachedResponse) {
                        return cachedResponse;
                    }
                    return caches.match('/core/offline/');
                })
        );
        return;
    }
    
    // For static assets, try cache first
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                if (response) {
                    return response;
                }
                return fetch(event.request);
            })
            .catch(() => {
                return new Response('Offline', { status: 503 });
            })
    );
});

// Push notifications
self.addEventListener('push', function(event) {
    console.log('[ServiceWorker] Push Received');
    let data = { 
        head: 'RoBosForx', 
        body: 'New notification',
        url: '/'  // Changed to root
    };
    if (event.data) {
        try { 
            data = event.data.json(); 
        } catch(e) { 
            data.body = event.data.text(); 
        }
    }
    
    const title = data.head || data.title || 'RoBosForx';
    
    event.waitUntil(
        self.registration.showNotification(title, {
            body: data.body,
            icon: data.icon || '/static/imgs/icons/icon-192x192.png',
            badge: '/static/imgs/icons/icon-72x72.png',
            data: { url: data.url || '/' },
            vibrate: [200, 100, 200],
            actions: [
                { action: 'open', title: 'Open App' },
                { action: 'close', title: 'Dismiss' }
            ]
        })
    );
});

// Notification click
self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    if (event.action === 'open') {
        event.waitUntil(clients.openWindow(event.notification.data.url));
    }
});