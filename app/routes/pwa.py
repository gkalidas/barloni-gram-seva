"""Progressive Web App glue: web manifest, service worker, offline page.

The service worker is intentionally conservative about caching. It only stores
*public* pages and static assets so a shared device never serves another
resident's dashboard, documents, or admin pages from the cache. Navigations are
network-first with a cached/offline fallback; static assets are cache-first.
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from app.config import settings

router = APIRouter()

# Public, non-personal paths that are safe to serve from the cache offline.
_PUBLIC_CACHEABLE = ["/", "/schemes", "/help", "/officials"]


@router.get("/manifest.webmanifest")
async def manifest():
    data = {
        "name": f"{settings.VILLAGE_NAME} {settings.APP_NAME}",
        "short_name": settings.VILLAGE_NAME or settings.APP_NAME,
        "description": settings.BRAND_TAGLINE,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": settings.BRAND_PRIMARY,
        "icons": [
            {"src": "/static/icon.svg", "sizes": "any",
             "type": "image/svg+xml", "purpose": "any maskable"},
        ],
    }
    return Response(json.dumps(data),
                    media_type="application/manifest+json")


# The service worker is served from the site root so its scope covers the whole
# app (a worker can only control paths at or below its own URL).
_SERVICE_WORKER_JS = """
const CACHE = 'gramseva-v1';
const PRECACHE = [
  '/offline', '/static/css/style.css', '/static/js/main.js',
  '/static/icon.svg', '/manifest.webmanifest'
];
const PUBLIC_CACHEABLE = %s;

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      Promise.all(PRECACHE.map((url) => cache.add(url).catch(() => null)))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Static assets: cache-first (ignore the ?v= cache-busting query on match).
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(req, { ignoreSearch: true }).then((hit) =>
        hit || fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return res;
        })
      )
    );
    return;
  }

  // Page navigations: network-first; cache only public pages; fall back to
  // the cached copy, then to the offline page.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then((res) => {
        if (PUBLIC_CACHEABLE.includes(url.pathname)) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      }).catch(() =>
        caches.match(req).then((hit) => hit || caches.match('/offline'))
      )
    );
  }
});
""" % json.dumps(_PUBLIC_CACHEABLE)


@router.get("/sw.js")
async def service_worker():
    return Response(
        _SERVICE_WORKER_JS,
        media_type="application/javascript",
        # Allow the root scope even though many setups would serve it elsewhere.
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@router.get("/offline", response_class=HTMLResponse)
async def offline_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request, "offline.html", {"request": request, "user": None})
