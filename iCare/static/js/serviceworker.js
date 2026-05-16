var staticCacheName = "RoBosForx-pwa-v" + new Date().getTime();
var apiCacheName = "RoBosForx-api-v1";

// Files to cache
var filesToCache = [
    '/offline/',
    '/static/images/icons/icon-72x72.png',
    '/static/images/icons/icon-96x96.png',
    '/static/images/icons/icon-128x128.png',
    '/static/images/icons/icon-144x144.png',
    '/static/images/icons/icon-152x152.png',
    '/static/images/icons/icon-192x192.png',
    '/static/images/icons/icon-384x384.png',
    '/static/images/icons/icon-512x512.png',
    '/static/css/main.css',
    '/dashboard/',
    '/trade/',
    '/',
    '/offline/'
];

// API endpoints to cache (GET requests only)
var apiEndpoints = [
    '/api/user/balance/',
    '/api/rates/',
    '/api/notifications/'
];

// Cache on install
self.addEventListener("install", event => {
    console.log('[ServiceWorker] Install');
    this.skipWaiting();
    event.waitUntil(
        caches.open(staticCacheName)
            .then(cache => {
                console.log('[ServiceWorker] Caching app shell');
                return cache.addAll(filesToCache);
            })
            .catch(err => {
                console.log('[ServiceWorker] Cache addAll error:', err);
            })
    );
});

// Clear old caches on activate
self.addEventListener('activate', event => {
    console.log('[ServiceWorker] Activate');
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames
                    .filter(cacheName => {
                        return (cacheName.startsWith("RoBosForx-pwa-") && cacheName !== staticCacheName) ||
                               (cacheName.startsWith("RoBosForx-api-") && cacheName !== apiCacheName);
                    })
                    .map(cacheName => {
                        console.log('[ServiceWorker] Removing old cache:', cacheName);
                        return caches.delete(cacheName);
                    })
            );
        })
    );
    return self.clients.claim();
});

// Network first strategy for API, cache first for static assets
self.addEventListener("fetch", event => {
    const requestUrl = new URL(event.request.url);
    
    // Handle API requests (Network First)
    if (requestUrl.pathname.startsWith('/api/') && event.request.method === 'GET') {
        event.respondWith(
            fetch(event.request)
                .then(response => {
                    // Cache successful responses
                    if (response.status === 200) {
                        const responseClone = response.clone();
                        caches.open(apiCacheName).then(cache => {
                            cache.put(event.request, responseClone);
                        });
                    }
                    return response;
                })
                .catch(() => {
                    // Return cached API response if offline
                    return caches.match(event.request).then(cachedResponse => {
                        if (cachedResponse) {
                            return cachedResponse;
                        }
                        // Return a default error response
                        return new Response(JSON.stringify({ error: 'You are offline' }), {
                            status: 503,
                            headers: { 'Content-Type': 'application/json' }
                        });
                    });
                })
        );
        return;
    }
    
    // Handle navigation requests (HTML pages)
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request)
                .then(response => {
                    // Cache the page for offline use
                    const responseClone = response.clone();
                    caches.open(staticCacheName).then(cache => {
                        cache.put(event.request, responseClone);
                    });
                    return response;
                })
                .catch(() => {
                    // Return cached page or offline page
                    return caches.match(event.request)
                        .then(cachedResponse => {
                            if (cachedResponse) {
                                return cachedResponse;
                            }
                            return caches.match('/offline/');
                        });
                })
        );
        return;
    }
    
    // Handle static assets (Cache First)
    if (event.request.url.match(/\.(css|js|png|jpg|jpeg|gif|svg|ico|webp)$/)) {
        event.respondWith(
            caches.match(event.request)
                .then(cachedResponse => {
                    if (cachedResponse) {
                        // Return cached version and update in background
                        fetch(event.request).then(response => {
                            if (response.status === 200) {
                                caches.open(staticCacheName).then(cache => {
                                    cache.put(event.request, response);
                                });
                            }
                        }).catch(() => {});
                        return cachedResponse;
                    }
                    return fetch(event.request);
                })
        );
        return;
    }
    
    // Default: Network with cache fallback
    event.respondWith(
        fetch(event.request)
            .catch(() => {
                return caches.match(event.request);
            })
    );
});

// Background sync for failed requests
self.addEventListener('sync', event => {
    if (event.tag === 'sync-transactions') {
        event.waitUntil(syncTransactions());
    }
});

async function syncTransactions() {
    // Implement background sync for failed transactions
    const cache = await caches.open('pending-transactions');
    const requests = await cache.keys();
    
    for (const request of requests) {
        try {
            const response = await fetch(request);
            if (response.ok) {
                await cache.delete(request);
            }
        } catch (error) {
            console.log('Failed to sync transaction:', error);
        }
    }
}

// Push notifications
self.addEventListener('push', event => {
    const data = event.data.json();
    
    const options = {
        body: data.body,
        icon: '/static/images/icons/icon-192x192.png',
        badge: '/static/images/icons/icon-72x72.png',
        vibrate: [200, 100, 200],
        data: {
            url: data.url || '/'
        },
        actions: [
            {
                action: 'open',
                title: 'Open'
            },
            {
                action: 'close',
                title: 'Close'
            }
        ]
    };
    
    event.waitUntil(
        self.registration.showNotification(data.title || 'RoBosForx', options)
    );
});

self.addEventListener('notificationclick', event => {
    event.notification.close();
    
    if (event.action === 'open') {
        const urlToOpen = event.notification.data.url;
        event.waitUntil(
            clients.matchAll({ type: 'window', includeUncontrolled: true })
                .then(windowClients => {
                    for (let client of windowClients) {
                        if (client.url === urlToOpen && 'focus' in client) {
                            return client.focus();
                        }
                    }
                    if (clients.openWindow) {
                        return clients.openWindow(urlToOpen);
                    }
                })
        );
    }
});